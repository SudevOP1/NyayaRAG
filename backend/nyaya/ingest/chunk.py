"""Section-aware chunker (PLAN.md P1 "Chunker").

Rules, in order:
1. One chunk per section if header + body fits `max_tokens` (bge tokenizer, special tokens
   included).
2. Otherwise pack whole sub-sections greedily up to the limit.
3. A sub-section still over the limit splits at top-level clause boundaries (never inside a
   clause). Explanations, Exceptions and provisos stay with the clause / preamble they follow.
4. Illustrations go into their own `chunk_type="illustration"` chunks.
5. Every chunk starts with a header that is embedded with the text.

A sub-section that is not in force (BNS 106(2)) is never packed with in-force text, so the
payload flag stays exact. Anything that cannot be split cleanly falls back to paragraph and then
sentence boundaries; sentence-level splits of a clause are logged in `clause_splits`.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from nyaya.config import (
    CHUNK_STATS_PATH,
    CHUNKS_PATH,
    EMBED_MODEL_ID,
    MAP_PATH,
    MAX_CHUNK_TOKENS,
    SECTIONS_PATH,
)
from nyaya.ingest.schema import Chunk, ChunkType, MapRow, Section, read_jsonl, write_jsonl
from nyaya.ingest.text import paragraphs, split_blocks, split_illustrations

TokenCounter = Callable[[str], int]
MAX_OLD_REFS_IN_HEADER = 5
SENTENCE_RE = re.compile(r"(?<=[.;:])\s+")


def load_token_counter(model_id: str = EMBED_MODEL_ID, local_files_only: bool = False):
    """Token counter backed by the embedder's own `tokenizer.json` (special tokens counted)."""
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    path = hf_hub_download(model_id, "tokenizer.json", local_files_only=local_files_only)
    tok = Tokenizer.from_file(path)
    tok.no_truncation()
    tok.no_padding()
    return lambda text: len(tok.encode(text).ids)


def make_header(s: Section, old_refs: list[str]) -> str:
    parts = [f"[{s.act} {s.section}] {s.title}"]
    if s.chapter_no:
        chapter = f"Chapter {s.chapter_no}"
        if s.chapter_title:
            chapter += f": {s.chapter_title}"
        parts.append(chapter)
    if old_refs:
        shown = old_refs[:MAX_OLD_REFS_IN_HEADER]
        more = ", …" if len(old_refs) > MAX_OLD_REFS_IN_HEADER else ""
        parts.append("Formerly: " + ", ".join(shown) + more)
    return " | ".join(parts)


@dataclass
class _Unit:
    text: str
    subs: list[str]
    in_force: bool
    kind: ChunkType


@dataclass
class _Builder:
    section: Section
    header: str
    count: TokenCounter
    max_tokens: int
    old_refs: list[str]
    chunks: list[Chunk] = field(default_factory=list)
    clause_split: bool = False

    def fits(self, body: str) -> bool:
        return self.count(self.compose(body)) <= self.max_tokens

    def compose(self, body: str) -> str:
        return f"{self.header}\n{body}"

    def emit(self, body: str, subs: list[str], in_force: bool, kind: ChunkType) -> None:
        text = self.compose(body)
        s = self.section
        self.chunks.append(
            Chunk(
                chunk_id=f"{s.act}-{s.section}-c{len(self.chunks) + 1}",
                act=s.act,
                section=s.section,
                subsections=list(dict.fromkeys(subs)),
                title=s.title,
                chapter=s.chapter_no,
                chunk_type=kind,
                old_refs=self.old_refs,
                in_force=in_force,
                tokens=self.count(text),
                page=s.page_start,
                header=self.header,
                text=text,
            )
        )

    def pack(self, units: list[_Unit], prefix: str = "") -> None:
        """Greedy packing; breaks on in_force change and on kind change."""
        cur: list[_Unit] = []

        def body(us: list[_Unit]) -> str:
            return prefix + "\n".join(u.text for u in us)

        def flush() -> None:
            if cur:
                self.emit(body(cur), [n for u in cur for n in u.subs], cur[0].in_force, cur[0].kind)
                cur.clear()

        for u in units:
            if cur and (
                u.in_force != cur[0].in_force
                or u.kind != cur[0].kind
                or not self.fits(body([*cur, u]))
            ):
                flush()
            cur.append(u)
        flush()

    def split_to_fit(
        self,
        text: str,
        subs: list[str],
        in_force: bool,
        kind: ChunkType,
        is_clause: bool,
        prefix: str = "",
    ) -> list[_Unit]:
        """Split an oversized block at paragraphs, then sentences, then words."""
        if self.fits(prefix + text):
            return [_Unit(text, subs, in_force, kind)]
        paras = paragraphs(text)
        if len(paras) > 1:
            out: list[_Unit] = []
            for p in paras:
                out += self.split_to_fit(p, subs, in_force, kind, is_clause, prefix)
            return out
        if is_clause:
            self.clause_split = True
        pieces = [p for p in SENTENCE_RE.split(text) if p]
        if len(pieces) == 1:
            pieces = _halve_words(text)
            if len(pieces) == 1:  # a single word over the limit: give up honestly
                return [_Unit(text, subs, in_force, kind)]
        out = []
        for p in pieces:
            out += self.split_to_fit(p, subs, in_force, kind, is_clause, prefix)
        return out


def _halve_words(text: str) -> list[str]:
    words = text.split(" ")
    if len(words) < 2:
        return [text]
    mid = len(words) // 2
    return [" ".join(words[:mid]), " ".join(words[mid:])]


def chunk_section(
    s: Section,
    count_tokens: TokenCounter,
    max_tokens: int = MAX_CHUNK_TOKENS,
    old_refs: list[str] | None = None,
) -> list[Chunk]:
    return _chunk_section(s, count_tokens, max_tokens, old_refs or [])[0]


def _chunk_section(
    s: Section, count: TokenCounter, max_tokens: int, old_refs: list[str]
) -> tuple[list[Chunk], bool]:
    header = make_header(s, old_refs)
    b = _Builder(s, header, count, max_tokens, old_refs)
    subs = s.subsections or []

    # Separate main text and illustrations per sub-section.
    mains: list[tuple[str | None, str, bool, list]] = []
    illus: list[tuple[str | None, str, bool]] = []
    for sub in subs:
        blocks = split_blocks(sub.text)
        main_blocks = [bl for bl in blocks if bl.kind != "illustration"]
        mains.append(
            (sub.number, "\n".join(bl.text for bl in main_blocks), sub.in_force, main_blocks)
        )
        for bl in blocks:
            if bl.kind == "illustration":
                for item in split_illustrations(bl.text):
                    illus.append((sub.number, item, sub.in_force))

    def label(n: str | None) -> list[str]:
        return [n] if n else []

    mains = [m for m in mains if m[1].strip()]
    all_main = "\n".join(m[1] for m in mains)
    same_force = len({m[2] for m in mains}) <= 1
    if mains and same_force and b.fits(all_main):
        b.emit(all_main, [n for m in mains for n in label(m[0])], mains[0][2], "section")
    else:
        units: list[_Unit] = []
        for num, text, in_force, blocks in mains:
            if b.fits(text):
                units.append(_Unit(text, label(num), in_force, "subsections"))
                continue
            for bl in blocks:
                units += b.split_to_fit(
                    bl.text, label(num), in_force, "clauses", is_clause=bl.kind == "clause"
                )
        b.pack(units)

    if illus:
        prefix = "Illustrations\n"
        units = []
        for num, item, in_force in illus:
            units += b.split_to_fit(item, label(num), in_force, "illustration", False, prefix)
        b.pack(units, prefix=prefix)
    return b.chunks, b.clause_split


def chunk_sections(
    sections: Iterable[Section],
    count_tokens: TokenCounter,
    max_tokens: int = MAX_CHUNK_TOKENS,
    old_refs: dict[tuple[str, int], list[str]] | None = None,
) -> tuple[list[Chunk], dict]:
    old_refs = old_refs or {}
    chunks: list[Chunk] = []
    clause_splits: list[str] = []
    for s in sections:
        cs, split = _chunk_section(
            s, count_tokens, max_tokens, old_refs.get((s.act, s.section), [])
        )
        chunks += cs
        if split:
            clause_splits.append(s.ref)
    return chunks, chunk_stats(chunks, clause_splits)


def chunk_stats(chunks: list[Chunk], clause_splits: list[str]) -> dict:
    toks = sorted(c.tokens for c in chunks)

    def pct(p: float) -> int:
        return toks[min(len(toks) - 1, int(p * len(toks)))] if toks else 0

    hist = Counter((t // 50) * 50 for t in toks)
    return {
        "n_chunks": len(chunks),
        "n_sections": len({(c.act, c.section) for c in chunks}),
        "by_act": dict(Counter(c.act for c in chunks)),
        "by_type": dict(Counter(c.chunk_type for c in chunks)),
        "max_tokens": toks[-1] if toks else 0,
        "mean_tokens": round(sum(toks) / len(toks), 1) if toks else 0,
        "p50_tokens": pct(0.5),
        "p95_tokens": pct(0.95),
        "histogram_50": {f"{k}-{k + 49}": hist[k] for k in sorted(hist)},
        "clause_splits": clause_splits,
    }


def old_refs_from_map(rows: Iterable[MapRow]) -> dict[tuple[str, int], list[str]]:
    """`(BNS, n)` -> ["IPC 302", …] in table order, de-duplicated."""
    out: dict[tuple[str, int], list[str]] = {}
    for r in rows:
        if r.bns_section is None or not r.ipc:
            continue
        refs = out.setdefault(("BNS", r.bns_section), [])
        for ipc in r.ipc:
            ref = f"IPC {ipc}"
            if ref not in refs:
                refs.append(ref)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Chunk sections.jsonl into chunks.jsonl")
    ap.add_argument("--sections", default=str(SECTIONS_PATH))
    ap.add_argument("--out", default=str(CHUNKS_PATH))
    ap.add_argument("--stats", default=str(CHUNK_STATS_PATH))
    ap.add_argument("--no-enrich", action="store_true", help="omit 'Formerly: IPC …' headers")
    ap.add_argument("--max-tokens", type=int, default=MAX_CHUNK_TOKENS)
    args = ap.parse_args(argv)

    from pathlib import Path

    sections = list(read_jsonl(Path(args.sections), Section))
    refs: dict[tuple[str, int], list[str]] = {}
    if not args.no_enrich:
        if not MAP_PATH.exists():
            raise SystemExit(f"{MAP_PATH} missing: run `python -m nyaya.ingest.parse_mapping`")
        refs = old_refs_from_map(read_jsonl(MAP_PATH, MapRow))
    count = load_token_counter()
    chunks, stats = chunk_sections(sections, count, args.max_tokens, refs)
    stats["enrich_old_refs"] = not args.no_enrich
    stats["tokenizer"] = EMBED_MODEL_ID
    write_jsonl(Path(args.out), chunks)
    Path(args.stats).write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k != "histogram_50"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

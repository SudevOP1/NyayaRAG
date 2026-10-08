"""Parse the BNS, BNSS and BSA Gazette PDFs into `data/processed/sections.jsonl`.

Layout (see the P1 spike in DECISIONS.md): Gazette of India layout. A section starts with a bold
`N.` at the paragraph indent of the body column, and its heading is a marginal note in a narrow
side column (right margin on odd pages, left on even pages) at ~7.9 pt, top-aligned with the
section's first line. Running headers sit above y≈79. The extracted text drops some inter-word
spaces ("ThisAct maybe"), so lines are rebuilt from per-character boxes: a horizontal gap wider
than `SPACE_GAP` x font size between two non-space glyphs becomes a space.

Edge cases are fixed through `data/patches/acts.yaml`, never special-cased silently here.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from statistics import median

import pymupdf
import yaml

from nyaya.config import ACTS_DIR, EXPECTED_SECTIONS, PATCHES_DIR, SECTIONS_PATH
from nyaya.ingest.schema import Act, Section, SubSection, write_jsonl
from nyaya.ingest.text import smart_title, split_subsections

ACT_FILES: dict[Act, str] = {"BNS": "bns.pdf", "BNSS": "bnss.pdf", "BSA": "bsa.pdf"}
PATCHES_PATH = PATCHES_DIR / "acts.yaml"

# Geometry (points, A4 595 x 842), measured in the spike.
HEADER_BOTTOM = 79.0  # running header / page number / rule live above this
BODY_X_MIN, BODY_X_MAX = 112.0, 482.0  # body column; anything outside is the margin column
PARA_INDENT_MIN = 136.0  # paragraph-start indent (continuation lines start at ~117.6)
NESTED_LIST_X = 180.0  # "(1)" paragraphs indented this far are nested lists
MIN_FONT = 5.0  # ignore near-invisible glyphs
SPACE_GAP = 0.095  # x font size; measured: glued words 1.2-1.5 pt, kerning <= 0.8 pt at 10 pt
BASELINE_TOL = 2.0
PARA_GAP = 1.42  # x font size; leading is 10.8-12.9 pt, paragraph gaps >= 15.8 pt
TEXT_LEFT, TEXT_RIGHT = 117.6, 477.6  # text column edges
# Legacy-encoded Devanagari fonts used in the bilingual Gazette masthead.
HINDI_FONT_RE = re.compile(r"Vivek|Kruti|DevLys|Chanakya|Mangal", re.I)

CHAPTER_RE = re.compile(r"^CHAPTER\s*([IVXLC]+)$")
PART_RE = re.compile(r"^PART\s*([IVX]+)$")
SECTION_RE = re.compile(r"^(\d{1,3})\.\s*")
ENACTED_RE = re.compile(r"^BE\s*it\s*enacted", re.I)
STOP_RE = re.compile(r"^THE\s*(?:FIRST\s*|SECOND\s*)?SCHEDULE$|^[—–\-]{3,}$")
NEW_PARA_MARKER_RE = re.compile(
    r"^(\(\w{1,4}\)|Explanation|Exception|Provided|Illustrations?\b)", re.I
)
ACT_REF_NOTE_RE = re.compile(r"^\d+ of \d{4}\.?$")  # "45 of 1860." cites an Act, not a title
MARGIN_SEGMENT_GAP = 8.0  # pt; word gaps in notes are ~3 pt
TITLE_WINDOW = 25.0  # max |note y - section y| (notes get pushed when sections are close)
ILLUSTRATION_HEADING_RE = re.compile(r"^Illustrations?\.?$", re.I)


@dataclass
class Line:
    page: int  # 1-based
    x0: float
    x1: float
    y: float  # baseline
    size: float
    text: str
    bold_start: bool = False

    @property
    def centered(self) -> bool:
        """Equal left and right gaps inside the text column (clause lines are only indented)."""
        left, right = self.x0 - TEXT_LEFT, TEXT_RIGHT - self.x1
        if NEW_PARA_MARKER_RE.match(self.text) and not ILLUSTRATION_HEADING_RE.match(self.text):
            return False  # a short clause line that happens to sit mid-column
        if self.text[-1:] in ";,:—–" or self.text[:1].islower():
            return False  # clause ends / continuation lines are text, not headings
        return left > 30 and right > 30 and abs(left - right) < 12


@dataclass
class _Char:
    c: str
    x0: float
    x1: float
    y: float
    size: float
    bold: bool


def _chars(page: pymupdf.Page) -> list[_Char]:
    out: list[_Char] = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                size = span["size"]
                font = span["font"]
                if size < MIN_FONT or HINDI_FONT_RE.search(font):
                    continue  # drops the Hindi masthead (legacy-encoded fonts) and hairlines
                bold = "Bold" in font or bool(span["flags"] & 16)
                for ch in span["chars"]:
                    x0, y0, x1, _ = ch["bbox"]
                    if y0 < HEADER_BOTTOM:
                        continue
                    out.append(_Char(ch["c"], x0, x1, ch["origin"][1], size, bold))
    return out


def _build_line(chars: list[_Char], page: int) -> Line | None:
    chars = sorted(chars, key=lambda c: c.x0)
    parts: list[str] = []
    prev: _Char | None = None
    for ch in chars:
        if prev is not None and ch.c != " " and prev.c != " ":
            gap = ch.x0 - prev.x1
            if gap > SPACE_GAP * max(ch.size, prev.size):
                parts.append(" ")
        parts.append(ch.c)
        prev = ch
    text = re.sub(r"\s+", " ", "".join(parts)).strip()
    if not text:
        return None
    visible = [c for c in chars if c.c.strip()]
    return Line(
        page=page,
        x0=visible[0].x0,
        x1=visible[-1].x1,
        y=median(c.y for c in visible),
        size=median(c.size for c in visible),
        text=text,
        bold_start=visible[0].bold,
    )


def _cluster(chars: list[_Char], page: int, split_gap: float | None = None) -> list[Line]:
    """Group characters into lines by baseline (small caps and superscripts share it).

    With `split_gap`, a line is also cut where two glyphs are further apart than that, so an
    Act citation printed on a marginal note's baseline becomes its own line.
    """
    rows: list[list[_Char]] = []
    for ch in sorted(chars, key=lambda c: (c.y, c.x0)):
        if rows and abs(rows[-1][0].y - ch.y) <= BASELINE_TOL:
            rows[-1].append(ch)
        else:
            rows.append([ch])
    if split_gap is not None:
        split: list[list[_Char]] = []
        for r in rows:
            r = sorted(r, key=lambda c: c.x0)
            seg = [r[0]]
            for a, b in pairwise(r):
                if b.c.strip() and b.x0 - a.x1 > split_gap:
                    split.append(seg)
                    seg = []
                seg.append(b)
            split.append(seg)
        rows = split
    lines = [_build_line(r, page) for r in rows]
    return [ln for ln in lines if ln is not None]


def extract_lines(doc: pymupdf.Document) -> tuple[list[Line], list[Line]]:
    """Return (body lines, margin lines) in reading order."""
    body: list[Line] = []
    margin: list[Line] = []
    for page in doc:
        chars = _chars(page)
        in_body = [c for c in chars if BODY_X_MIN <= c.x0 <= BODY_X_MAX]
        in_margin = [c for c in chars if not BODY_X_MIN <= c.x0 <= BODY_X_MAX]
        body += _cluster(in_body, page.number + 1)
        for side in (
            [c for c in in_margin if c.x0 < BODY_X_MIN],
            [c for c in in_margin if c.x0 > BODY_X_MAX],
        ):
            for ln in _cluster(side, page.number + 1, split_gap=MARGIN_SEGMENT_GAP):
                if not ACT_REF_NOTE_RE.match(ln.text):  # "45 of 1860." cites an Act
                    margin.append(ln)
    margin.sort(key=lambda ln: (ln.page, ln.x0 > BODY_X_MAX, ln.y))
    return body, margin


@dataclass
class _MarginBlock:
    page: int
    y: float
    lines: list[str] = field(default_factory=list)


def margin_blocks(lines: list[Line]) -> list[_MarginBlock]:
    """Group margin lines into notes. Neighbouring notes often touch, so a line ending in "."
    followed by a capitalised line also starts a new note."""
    blocks: list[_MarginBlock] = []
    last: Line | None = None
    for ln in lines:
        same = (
            last is not None
            and ln.page == last.page
            and ln.y - last.y < 1.6 * ln.size
            and not (last.text.endswith(".") and ln.text[:1].isupper())
        )
        if same:
            blocks[-1].lines.append(ln.text)
        else:
            blocks.append(_MarginBlock(ln.page, ln.y, [ln.text]))
        last = ln
    return blocks


def join_lines(lines: list[str]) -> str:
    out = ""
    for t in lines:
        if not out:
            out = t
        elif out.endswith("-") and len(out) > 1 and out[-2].isalpha():
            out += t  # "sub-" + "section"
        else:
            out += " " + t
    return out


@dataclass
class _RawSection:
    number: int
    page: int
    y: float
    chapter_no: str | None
    chapter_title: str | None
    part: str | None
    paras: list[list[str]] = field(default_factory=list)
    para_x: list[float] = field(default_factory=list)  # x0 of each paragraph's first line


def parse_lines(body: list[Line], act: Act) -> list[_RawSection]:
    expected_total = EXPECTED_SECTIONS[act]
    sections: list[_RawSection] = []
    started = enacted = False
    chapter_no = chapter_title = part = None
    pending_title: list[str] | None = None  # collecting chapter title lines
    prev: Line | None = None
    for ln in body:
        t = ln.text
        if not enacted:
            enacted = bool(ENACTED_RE.match(t))
            continue
        if STOP_RE.match(t) and sections and sections[-1].number == expected_total:
            break
        m = CHAPTER_RE.match(t)
        if m:
            started = True
            chapter_no, chapter_title, pending_title = m.group(1), None, []
            prev = ln
            continue
        m = PART_RE.match(t)
        if m and ln.centered:
            part = m.group(1)
            prev = ln
            continue
        if not started:
            continue
        if pending_title is not None:
            if t.upper() == t and ln.x0 > TEXT_LEFT + 5 and not SECTION_RE.match(t):
                pending_title.append(t)
                chapter_title = join_lines(pending_title)
                prev = ln
                continue
            pending_title = None
        m = SECTION_RE.match(t)
        if (
            m
            and ln.bold_start
            and ln.x0 >= PARA_INDENT_MIN
            and int(m.group(1)) == (sections[-1].number + 1 if sections else 1)
        ):
            sections.append(
                _RawSection(
                    int(m.group(1)),
                    ln.page,
                    ln.y,
                    chapter_no,
                    chapter_title,
                    part,
                    [[t[m.end() :]]] if t[m.end() :] else [],
                    [ln.x0] if t[m.end() :] else [],
                )
            )
            prev = ln
            continue
        if not sections:
            prev = ln
            continue
        cur = sections[-1]
        if ln.centered and not ILLUSTRATION_HEADING_RE.match(t):
            # Chapter sub-heading ("Of offences affecting life"): not part of a section.
            prev = ln
            continue
        new_para = (
            not cur.paras
            or ILLUSTRATION_HEADING_RE.match(t)
            or (prev is not None and prev.centered)
            or (
                ln.x0 >= PARA_INDENT_MIN
                and not t[:1].islower()  # a lowercase line always continues a sentence
                and (
                    (
                        prev is not None
                        and ln.page == prev.page
                        and ln.y - prev.y > PARA_GAP * ln.size
                    )
                    or (prev is not None and ln.page != prev.page and NEW_PARA_MARKER_RE.match(t))
                )
            )
        )
        if new_para:
            cur.paras.append([t])
            cur.para_x.append(ln.x0)
        else:
            cur.paras[-1].append(t)
        prev = ln
    return sections


def attach_titles(raw: list[_RawSection], blocks: list[_MarginBlock]) -> dict[int, str]:
    """One-to-one, nearest-first matching of sections to notes on the same page."""
    pairs = sorted(
        (abs(b.y - s.y), i, j)
        for i, s in enumerate(raw)
        for j, b in enumerate(blocks)
        if b.page == s.page and abs(b.y - s.y) <= TITLE_WINDOW
    )
    titles: dict[int, str] = {}
    used: set[int] = set()
    for _, i, j in pairs:
        if raw[i].number in titles or j in used:
            continue
        titles[raw[i].number] = join_lines(blocks[j].lines).rstrip(" .").strip()
        used.add(j)
    return titles


def load_patches(path: Path = PATCHES_PATH) -> list[dict]:
    if not path.exists():
        return []
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def apply_patches(sections: list[Section], patches: list[dict]) -> list[Section]:
    by_key = {(s.act, s.section): s for s in sections}
    for p in patches:
        s = by_key.get((p["act"], p["section"]))
        if s is None:
            raise ValueError(f"patch for unknown section: {p}")
        fld = p["field"]
        if fld == "in_force" and p.get("subsection"):
            subs = [x for x in s.subsections if x.number == str(p["subsection"])]
            if len(subs) != 1:
                raise ValueError(f"patch sub-section not found: {p}")
            subs[0].in_force = bool(p["value"])
            s.in_force = all(x.in_force for x in s.subsections)
        elif fld in {"title", "text", "chapter_title"}:
            setattr(s, fld, p["value"])
            if fld == "text":
                s.subsections = [
                    SubSection(number=n, text=t) for n, t in split_subsections(p["value"])
                ]
        else:
            raise ValueError(f"unsupported patch field: {p}")
    return sections


def parse_act(path: Path, act: Act) -> list[Section]:
    doc = pymupdf.open(path)
    body, margin = extract_lines(doc)
    raw = parse_lines(body, act)
    titles = attach_titles(raw, margin_blocks(margin))
    out: list[Section] = []
    for r in raw:
        text = "\n".join(join_lines(p) for p in r.paras)
        may_start = [x < NESTED_LIST_X for x in r.para_x]
        subs = [SubSection(number=n, text=t) for n, t in split_subsections(text, may_start)]
        out.append(
            Section(
                act=act,
                section=r.number,
                title=titles.get(r.number, ""),
                chapter_no=r.chapter_no,
                chapter_title=smart_title(r.chapter_title) if r.chapter_title else None,
                part=r.part,
                text=text,
                subsections=subs,
                page_start=r.page,
                source="india_code",
            )
        )
    return out


def parse_all(acts_dir: Path = ACTS_DIR, patches: list[dict] | None = None) -> list[Section]:
    sections: list[Section] = []
    for act, fname in ACT_FILES.items():
        sections += parse_act(acts_dir / fname, act)
    return apply_patches(sections, load_patches() if patches is None else patches)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(SECTIONS_PATH))
    args = ap.parse_args(argv)
    sections = parse_all()
    counts = Counter(s.act for s in sections)
    for act, n in EXPECTED_SECTIONS.items():
        flag = "ok" if counts[act] == n else "MISMATCH"
        print(f"{act}: {counts[act]} sections (expected {n}) {flag}")
    missing = [s.ref for s in sections if not s.title]
    if missing:
        print(f"sections without a marginal-note title: {missing}")
    n = write_jsonl(Path(args.out), sections)
    print(f"wrote {n} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

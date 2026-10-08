"""IPC-to-BNS mapper (PLAN.md P1 "Mapper").

Source: a government-published correspondence table (CAPT Bhopal / UP Police "BNS_IPC_Comparative"),
read from its Kaggle CSV transcription (#5, `tanujsaxena/bns-ipc-mapping`), joined with IPC offence
names and punishments from Kaggle #7. The table is a reference document, not a statutory schedule.
Reviewed fixes live in `data/patches/mapping.yaml`; explanatory notes in
`data/patches/mapper_notes.yaml`.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import yaml
from pydantic import BaseModel, Field

from nyaya.config import GOLDEN_DIR, KAGGLE_DIR, MAP_PATH, MAP_REVERSE_PATH, PATCHES_DIR
from nyaya.ingest.schema import MapRow, read_jsonl, write_jsonl

TABLE_SOURCE = (
    "Government-published correspondence table, BNS 2023 to IPC 1860 (CAPT Bhopal; "
    "UP Police BNS_IPC_Comparative), via Kaggle tanujsaxena/bns-ipc-mapping. "
    "A reference document, not a statutory schedule."
)
NOTES_PATH = PATCHES_DIR / "mapper_notes.yaml"
AGREEMENT_PATH = GOLDEN_DIR / "MAPPER_AGREEMENT.md"
MAPPING_PATCHES_PATH = PATCHES_DIR / "mapping.yaml"
NO_EQUIVALENT = "no direct equivalent in BNS"

STATUS_MAP = {
    "": "carried_over",
    "change": "changed",
    "changed": "changed",
    "deleted": "deleted",
    "new section": "new_section",
    "new sub-section": "new_subsection",
    "new subsection": "new_subsection",
}

_IPC_REF_RE = re.compile(r"(\d{1,3})\s?(?:-\s?)?([A-Z]{1,2})?(?![a-z])((?:\(\d+\))*)")
_BNS_REF_RE = re.compile(r"^\s*(\d{1,3})\s*((?:\(\s*[0-9a-z]+\s*\))*)\s*$")
_NULLS = {"", "nan", "none", "-", "—", "na", "n/a"}


def _clean(v: object) -> str | None:
    s = re.sub(r"\s+", " ", str(v if v is not None else "")).strip()
    return None if s.lower() in _NULLS else s


def parse_ipc_refs(raw: str) -> list[str]:
    """`"299 & 300"` -> `["299", "300"]`, `"Sec. 34"` -> `["34"]`, `"498-A"` -> `["498A"]`."""
    s = _clean(raw)
    if not s:
        return []
    s = re.sub(r"(?i)\b(?:sections?|secs?\.?|s\.)\s*", " ", s)
    s = re.sub(r"\band\b|&", ",", s)
    out: list[str] = []
    for num, letters, subs in _IPC_REF_RE.findall(s):
        ref = f"{num}{letters or ''}{subs}"
        if ref not in out:
            out.append(ref)
    return out


def parse_bns_ref(raw: str) -> tuple[str | None, int | None]:
    s = _clean(raw)
    if not s:
        return None, None
    m = _BNS_REF_RE.match(s)
    if not m:
        raise ValueError(f"unparseable BNS ref: {raw!r}")
    subs = re.sub(r"\s+", "", m.group(2))
    return f"{int(m.group(1))}{subs}", int(m.group(1))


def normalise_ipc_query(q: str) -> str:
    """`"IPC 420"`, `"s. 498-a"`, `"ipc120b"` -> canonical `"420"`, `"498A"`, `"120B"`."""
    s = re.sub(r"(?i)\b(?:ipc|indian penal code|sections?|secs?\.?|s\.)", " ", q)
    s = re.sub(r"(?i)^\s*ipc", "", s.strip())
    m = re.search(r"(\d{1,3})\s*-?\s*([A-Za-z]{1,2})?\s*((?:\(\d+\))*)", s)
    if not m:
        return q.strip().upper()
    return f"{m.group(1)}{(m.group(2) or '').upper()}{m.group(3)}"


def load_ipc_details(path: Path) -> dict[str, tuple[str | None, str | None]]:
    """Kaggle #7: `IPC_302` -> ("Murder", "Death or …")."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.columns = [c.strip().lower() for c in df.columns]
    out: dict[str, tuple[str | None, str | None]] = {}
    for r in df.to_dict("records"):
        key = re.sub(r"(?i)^ipc_?", "", str(r["section"]).strip()).upper()
        if key and key not in out:
            out[key] = (_clean(r.get("offense")), _clean(r.get("punishment")))
    return out


def load_mapping_csv(
    path: Path,
    ipc_details: dict[str, tuple[str | None, str | None]] | None = None,
    source: str = TABLE_SOURCE,
) -> list[MapRow]:
    ipc_details = ipc_details or {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.columns = [c.strip().lower() for c in df.columns]
    rows: list[MapRow] = []
    for r in df.to_dict("records"):
        bns, bns_sec = parse_bns_ref(r.get("bns_section", ""))
        ipc = parse_ipc_refs(r.get("ipc_section", ""))
        status_raw = (_clean(r.get("status")) or "").lower()
        if status_raw not in STATUS_MAP:
            raise ValueError(f"unknown Status {status_raw!r} in row {r}")
        status = STATUS_MAP[status_raw]
        if bns is None and not ipc:
            continue  # blank spacer row
        offence = punishment = None
        if ipc:
            base = re.sub(r"\(.*", "", ipc[0])
            offence, punishment = ipc_details.get(base, (None, None))
        rows.append(
            MapRow(
                bns=bns,
                bns_section=bns_sec,
                ipc=ipc,
                bns_title=_clean(r.get("bns_title")),
                ipc_title=_clean(r.get("ipc_title")),
                status=status,
                ipc_offence=offence,
                ipc_punishment=punishment,
                source=source,
            )
        )
    return rows


def apply_patches(rows: list[MapRow], patches_path: Path = MAPPING_PATCHES_PATH) -> list[MapRow]:
    """Reviewed fixes: `{match: {bns?, ipc?}, set: {...}, reason, checked_against}` or `add`."""
    if not patches_path.exists():
        return rows
    patches = yaml.safe_load(patches_path.read_text(encoding="utf-8")) or []
    for p in patches:
        if "add" in p:
            rows.append(MapRow(**{"source": TABLE_SOURCE, **p["add"]}))
            continue
        match, new = p["match"], p["set"]
        hits = [
            i
            for i, r in enumerate(rows)
            if all((getattr(r, k) if k != "ipc" else r.ipc) == v for k, v in match.items())
        ]
        if len(hits) != 1:
            raise ValueError(f"patch {match} matched {len(hits)} rows (expected 1)")
        rows[hits[0]] = rows[hits[0]].model_copy(update=new)
    return rows


class MapMatch(BaseModel):
    bns: str
    bns_section: int
    bns_title: str | None
    status: str
    ipc_title: str | None
    ipc_offence: str | None
    ipc_punishment: str | None
    note: str | None = None


class MapResult(BaseModel):
    query: str
    ipc_section: str
    found: bool
    matches: list[MapMatch] = Field(default_factory=list)
    message: str
    source: str = TABLE_SOURCE


def _base(ref: str) -> str:
    return re.sub(r"\(.*", "", ref)


class Mapper:
    def __init__(self, rows: Iterable[MapRow], notes_path: Path = NOTES_PATH):
        self.rows = list(rows)
        self.index: dict[str, list[MapRow]] = {}
        for r in self.rows:
            for ref in r.ipc:
                for key in {ref, _base(ref)}:
                    self.index.setdefault(key, []).append(r)
        self.notes: dict[str, str] = {}
        if notes_path.exists():
            for n in yaml.safe_load(notes_path.read_text(encoding="utf-8")) or []:
                self.notes[str(n["ipc"]).upper()] = n["note"]

    @classmethod
    def load(cls, path: Path = MAP_PATH) -> Mapper:
        return cls(read_jsonl(path, MapRow))

    def ipc_to_bns(self, section: str) -> MapResult:
        key = normalise_ipc_query(section)
        rows = self.index.get(key) or self.index.get(_base(key)) or []
        note = self.notes.get(key) or self.notes.get(_base(key))
        matches = [
            MapMatch(
                bns=r.bns,
                bns_section=r.bns_section,
                bns_title=r.bns_title,
                status=r.status,
                ipc_title=r.ipc_title,
                ipc_offence=r.ipc_offence,
                ipc_punishment=r.ipc_punishment,
                note=note,
            )
            for r in rows
            if r.bns is not None and r.bns_section is not None
        ]
        if matches:
            refs = ", ".join(f"BNS {m.bns}" for m in matches)
            msg = f"IPC {key} corresponds to {refs}."
            if note:
                msg += f" Note: {note}"
            return MapResult(
                query=section, ipc_section=key, found=True, matches=matches, message=msg
            )
        if rows:  # only Deleted rows
            msg = f"IPC {key}: {NO_EQUIVALENT} (marked deleted in the correspondence table)."
            if note:
                msg += f" Note: {note}"
            return MapResult(query=section, ipc_section=key, found=False, message=msg)
        return MapResult(
            query=section,
            ipc_section=key,
            found=False,
            message=f"IPC {key} not found in the correspondence table.",
        )


def reverse_index(rows: Iterable[MapRow]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for r in rows:
        for ref in r.ipc:
            bucket = out.setdefault(ref, [])
            if r.bns and r.bns not in bucket:
                bucket.append(r.bns)
    return out


def agreement_with_reference(rows: Iterable[MapRow], ref_csv: Path) -> dict:
    """Section-level agreement with an independent BNS->IPC table (Kaggle #6).

    A reference row agrees when it says "New offence" and our table has no IPC predecessor for
    that BNS section, or when at least one of its IPC refs is among ours for that section.
    """
    ours: dict[int, set[str]] = {}
    for r in rows:
        if r.bns_section is not None:
            ours.setdefault(r.bns_section, set()).update(_base(i) for i in r.ipc)
    df = pd.read_csv(ref_csv, dtype=str, keep_default_na=False)
    n = agree = 0
    disagreements: list[dict] = []
    for r in df.to_dict("records"):
        if r.get("act", "BNS").strip() != "BNS":
            continue
        n += 1
        bns, sec = parse_bns_ref(r["section"])
        raw = r.get("ipc_equivalent", "")
        theirs = {_base(i) for i in parse_ipc_refs(raw.replace("IPC", " "))}
        new = "new offence" in raw.lower() or not theirs
        mine = ours.get(sec)
        ok = mine is not None and ((new and not mine) or bool(theirs & mine))
        if ok:
            agree += 1
        else:
            disagreements.append(
                {
                    "bns": bns,
                    "title": r.get("title"),
                    "reference_ipc": raw,
                    "table_ipc": sorted(mine) if mine is not None else None,
                }
            )
    return {
        "n": n,
        "agree": agree,
        "rate": round(agree / n, 4) if n else None,
        "disagreements": disagreements,
    }


def write_agreement_report(rep: dict, path: Path, ref_name: str) -> None:
    lines = [
        "# Mapper agreement with an independent correspondence table",
        "",
        f"Reference: {ref_name}. Generated by `python -m nyaya.ingest.parse_mapping`.",
        "Section-level comparison; a disagreement is not automatically an error in either table.",
        "",
        f"**Agreement: {rep['agree']}/{rep['n']} ({rep['rate']:.1%})**",
        "",
        "| BNS | Title | Reference IPC | Our table IPC | Verdict (developer) |",
        "|---|---|---|---|---|",
    ]
    for d in rep["disagreements"]:
        table = ", ".join(d["table_ipc"]) if d["table_ipc"] else "(none)"
        lines.append(f"| {d['bns']} | {d['title']} | {d['reference_ipc']} | {table} | |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mapping-csv", default=None)
    ap.add_argument("--ipc-csv", default=None)
    args = ap.parse_args(argv)

    mapping_csv = (
        Path(args.mapping_csv)
        if args.mapping_csv
        else next((KAGGLE_DIR / "bns_ipc_mapping").rglob("*.csv"))
    )
    ipc_csv = (
        Path(args.ipc_csv)
        if args.ipc_csv
        else next((KAGGLE_DIR / "ipc_sections_dev523").rglob("*.csv"))
    )
    rows = apply_patches(load_mapping_csv(mapping_csv, load_ipc_details(ipc_csv)))
    n = write_jsonl(MAP_PATH, rows)
    MAP_REVERSE_PATH.write_text(json.dumps(reverse_index(rows), indent=1), encoding="utf-8")
    from collections import Counter

    print(f"wrote {n} rows -> {MAP_PATH}")
    print("status:", dict(Counter(r.status for r in rows)))
    print("distinct BNS sections:", len({r.bns_section for r in rows if r.bns_section}))
    ref = KAGGLE_DIR / "bns_correspondence_sirjon" / "bns_correspondence.csv"
    if ref.exists():
        rep = agreement_with_reference(rows, ref)
        write_agreement_report(rep, AGREEMENT_PATH, "Kaggle sirjon/bns-correspondence (#6)")
        print(f"agreement with #6: {rep['agree']}/{rep['n']} -> {AGREEMENT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

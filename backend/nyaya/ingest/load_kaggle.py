"""Kaggle fast start (PLAN.md P1): convert the BNS / BSA CSVs (#2, #3) to the sections schema.

Output `data/processed/sections_kaggle.jsonl`, tagged `source="kaggle"`. Used for early chunking
and BM25 work and for the parser cross-check. **Never indexed in the final build.**
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from nyaya.config import KAGGLE_DIR, KAGGLE_SECTIONS_PATH
from nyaya.ingest.schema import Act, Section, SubSection, write_jsonl
from nyaya.ingest.text import drop_stray_footnotes, int_to_roman, normalise_text, split_subsections


def normalise_columns(cols: list[str]) -> list[str]:
    return [re.sub(r"\s+", "_", re.sub(r"\s*_\s*", "_", c.strip())).lower() for c in cols]


def clean_title(title: str) -> str:
    return normalise_text(str(title)).rstrip(" .—-").strip()


def find_kaggle_csv(folder: Path) -> Path:
    csvs = sorted(folder.rglob("*.csv"))
    if not csvs:
        raise FileNotFoundError(f"no CSV under {folder}")
    return csvs[0]


def load_kaggle_csv(path: Path, act: Act) -> tuple[list[Section], list[int]]:
    """Return (sections, section numbers whose description is empty)."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    df.columns = normalise_columns(list(df.columns))
    sections: list[Section] = []
    empty: list[int] = []
    for row in df.to_dict("records"):
        num = int(str(row["section"]).strip())
        text = drop_stray_footnotes(normalise_text(row.get("description", "")))
        if not text:
            empty.append(num)
            continue
        chap_raw = str(row.get("chapter", "")).strip()
        chapter_no = int_to_roman(int(chap_raw)) if chap_raw.isdigit() else (chap_raw or None)
        subs = [SubSection(number=n, text=t) for n, t in split_subsections(text)]
        sections.append(
            Section(
                act=act,
                section=num,
                title=clean_title(row.get("section_name", "")),
                chapter_no=chapter_no,
                chapter_title=normalise_text(row.get("chapter_name", "")) or None,
                text=text,
                subsections=subs,
                source="kaggle",
            )
        )
    return sections, empty


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(KAGGLE_SECTIONS_PATH))
    args = ap.parse_args(argv)
    rows: list[Section] = []
    for act, folder in (("BNS", "bns_nandr39"), ("BSA", "bsa_nandr39")):
        secs, empty = load_kaggle_csv(find_kaggle_csv(KAGGLE_DIR / folder), act=act)
        print(f"{act}: {len(secs)} sections, {len(empty)} empty descriptions {empty}")
        rows += secs
    n = write_jsonl(Path(args.out), rows)
    print(f"wrote {n} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

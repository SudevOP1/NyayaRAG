"""PDF layout spike (PLAN.md P1 step 5).

Dumps `get_text("dict")` spans (bbox, font, size, flags) for a few pages of each Act so the layout
(gazette marginal notes vs inline headings) and the running headers/footers can be identified.

    uv run python scripts/pdf_spike.py                 # pages 1-3 of the body of each Act
    uv run python scripts/pdf_spike.py --act bns --pages 30 31

Output: printed, and `data/raw/spike/<act>_p<N>.txt` (gitignored with the rest of raw/).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf

from nyaya.config import ACTS_DIR, RAW_DIR


def dump_page(doc: pymupdf.Document, pno: int) -> str:
    page = doc[pno]
    w, h = page.rect.width, page.rect.height
    lines = [f"=== page {pno + 1}  size {w:.0f}x{h:.0f} ==="]
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                x0, y0, x1, _y1 = span["bbox"]
                text = span["text"]
                if not text.strip():
                    continue
                lines.append(
                    f"x={x0:6.1f}-{x1:6.1f} y={y0:6.1f} size={span['size']:5.2f} "
                    f"flags={span['flags']:2d} font={span['font'][:22]:22s} | {text}"
                )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--act", choices=["bns", "bnss", "bsa"], action="append")
    ap.add_argument("--pages", type=int, nargs="*", help="1-based page numbers")
    args = ap.parse_args(argv)
    out_dir = RAW_DIR / "spike"
    out_dir.mkdir(parents=True, exist_ok=True)
    for act in args.act or ["bns", "bnss", "bsa"]:
        path: Path = ACTS_DIR / f"{act}.pdf"
        if not path.exists():
            print(f"{path} missing (see scripts/download.py)")
            continue
        doc = pymupdf.open(path)
        pages = [p - 1 for p in args.pages] if args.pages else [0, 1, doc.page_count // 2]
        print(f"##### {act}: {doc.page_count} pages")
        for p in pages:
            text = dump_page(doc, p)
            (out_dir / f"{act}_p{p + 1}.txt").write_text(text, encoding="utf-8")
            print(text[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

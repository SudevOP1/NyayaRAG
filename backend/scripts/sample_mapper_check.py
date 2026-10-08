"""Sample mapper rows for the developer's hand-check (PLAN.md P1 human task).

    uv run python scripts/sample_mapper_check.py            # 40 rows, seed 42

Writes `data/golden/MAPPER_HANDCHECK.md`: one row per sampled mapping with blank columns to fill
in against the UP Police / CAPT PDFs (`data/raw/gov/`) and NCRB Sankalan. Re-running with the same
seed reproduces the same sample and keeps anything already filled in.
"""

from __future__ import annotations

import argparse
import random
import re

from nyaya.config import GOLDEN_DIR, MAP_PATH
from nyaya.ingest.schema import MapRow, read_jsonl

OUT = GOLDEN_DIR / "MAPPER_HANDCHECK.md"
_ROW_RE = re.compile(r"^\| (\d+) \|")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)
    rows = list(read_jsonl(MAP_PATH, MapRow))
    idx = sorted(random.Random(args.seed).sample(range(len(rows)), args.n))
    kept: dict[int, str] = {}
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            m = _ROW_RE.match(line)
            if m:
                kept[int(m.group(1))] = line
    lines = [
        "# Mapper hand-check",
        "",
        f"{args.n} rows of `ipc_bns_map.jsonl` sampled with seed {args.seed} "
        "(`scripts/sample_mapper_check.py`).",
        "Check each against the UP Police / CAPT PDFs and NCRB Sankalan. Mark `PDF ok` and",
        "`Sankalan ok` as `y` / `n`; explain any `n` in Notes. Log the totals in `CHANGELOG.md`.",
        "",
        "| # | BNS | IPC | Status | BNS title | PDF ok | Sankalan ok | Notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i in idx:
        r = rows[i]
        if i in kept:
            lines.append(kept[i])
            continue
        ipc = ", ".join(r.ipc) or "-"
        lines.append(
            f"| {i} | {r.bns or '-'} | {ipc} | {r.status} | {r.bns_title or ''} |  |  |  |"
        )
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(idx)} rows -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

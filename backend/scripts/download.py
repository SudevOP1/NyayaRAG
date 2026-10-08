"""Thin wrapper: `uv run python scripts/download.py` (see `nyaya.ingest.download`)."""

import sys

from nyaya.ingest.download import main

if __name__ == "__main__":
    sys.exit(main())

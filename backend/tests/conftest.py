from __future__ import annotations

from pathlib import Path

import pytest

from nyaya.config import ACTS_DIR, KAGGLE_DIR, RAW_DIR

FIXTURES = Path(__file__).parent / "fixtures"


def word_count(text: str) -> int:
    """Stand-in token counter for fixture tests (no tokenizer download)."""
    return len(text.split())


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


def require_raw(*paths: Path) -> None:
    """Skip a data test with a clear reason when downloaded files are missing."""
    if not RAW_DIR.exists():
        pytest.skip("data/raw/ absent: run `uv run python scripts/download.py` (PLAN.md P1)")
    missing = [p for p in paths if not p.exists()]
    if missing:
        rel = ", ".join(str(p.relative_to(RAW_DIR)) for p in missing)
        pytest.skip(f"missing downloaded data: {rel} (see scripts/download.py)")


def act_pdfs() -> list[Path]:
    return [ACTS_DIR / f"{a}.pdf" for a in ("bns", "bnss", "bsa")]


def kaggle_path(*parts: str) -> Path:
    return KAGGLE_DIR.joinpath(*parts)

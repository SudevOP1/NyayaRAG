from __future__ import annotations

import pytest

from nyaya.ingest.load_kaggle import find_kaggle_csv, load_kaggle_csv, normalise_columns
from tests.conftest import kaggle_path


def test_normalise_columns_strips_stray_space():
    assert normalise_columns(["Chapter", "Section _name", "Description "]) == [
        "chapter",
        "section_name",
        "description",
    ]


def test_load_fixture(fixtures_dir):
    secs, empty = load_kaggle_csv(fixtures_dir / "kaggle_bns_sample.csv", act="BNS")
    by = {s.section: s for s in secs}
    assert set(by) == {1, 103, 104}
    assert empty == [200]
    s1 = by[1]
    assert s1.source == "kaggle"
    assert s1.title == "Short title and commencement"  # trailing full stop dropped
    assert "date1" not in s1.text and "such date as notified" in s1.text
    assert "\r" not in s1.text
    assert [x.number for x in s1.subsections] == ["1", "2"]
    assert by[103].chapter_no == "VI"
    assert [x.number for x in by[104].subsections] == [None]


@pytest.mark.data
@pytest.mark.parametrize(
    ("act", "folder", "n"), [("BNS", "bns_nandr39", 358), ("BSA", "bsa_nandr39", 170)]
)
def test_real_kaggle_counts(act, folder, n):
    d = kaggle_path(folder)
    if not d.exists():
        pytest.skip(f"Kaggle data absent: {d} (run scripts/download.py)")
    secs, empty = load_kaggle_csv(find_kaggle_csv(d), act=act)
    assert len(secs) + len(empty) == n

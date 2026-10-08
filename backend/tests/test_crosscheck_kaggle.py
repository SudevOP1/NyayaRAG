from __future__ import annotations

import pytest

from nyaya.config import DATA_QUALITY_PATH, KAGGLE_SECTIONS_PATH, SECTIONS_PATH
from nyaya.ingest.crosscheck import (
    THRESHOLD,
    compare,
    normalise_for_compare,
    read_verdicts,
    render_report,
)
from nyaya.ingest.schema import Section


def _s(act, n, title, text, source="india_code"):
    return Section(act=act, section=n, title=title, text=text, source=source)


def test_normalise_for_compare():
    assert normalise_for_compare("(1) “Act”—denotes;\nthe  ACT.") == "1 act denotes the act"


def test_compare_flags_low_similarity():
    ours = [
        _s("BNS", 1, "Short title", "(1) This Act may be called X."),
        _s("BNS", 2, "Definitions", "In this Sanhita, act denotes a series of acts."),
    ]
    theirs = {
        ("BNS", 1): ("Short title.", "(1) This Act may be called X."),
        ("BNS", 2): ("Definitions", "Something completely different here."),
    }
    rows = compare(ours, theirs)
    by = {r["section"]: r for r in rows}
    assert by[1]["title_score"] >= THRESHOLD and by[1]["body_score"] >= THRESHOLD
    assert by[2]["body_score"] < THRESHOLD and by[2]["flagged"]


def test_compare_missing_reference_is_flagged():
    rows = compare([_s("BSA", 26, "T", "body")], {("BSA", 26): ("T", "")})
    assert rows[0]["flagged"] and rows[0]["body_score"] is None


def test_verdicts_survive_regeneration(tmp_path):
    rows = [
        {
            "act": "BNS",
            "section": 2,
            "title_score": 100.0,
            "body_score": 50.0,
            "flagged": True,
            "hint": "",
            "title": "Definitions",
        }
    ]
    path = tmp_path / "DQ.md"
    path.write_text(render_report(rows, {}), encoding="utf-8")
    text = path.read_text(encoding="utf-8").replace(
        "| BNS 2 | Definitions | 100.0 | 50.0 |  |  |  |",
        "| BNS 2 | Definitions | 100.0 | 50.0 |  | Kaggle wrong | dup text |",
    )
    path.write_text(text, encoding="utf-8")
    verdicts = read_verdicts(path)
    assert verdicts[("BNS", 2)] == ("Kaggle wrong", "dup text")
    assert "Kaggle wrong | dup text" in render_report(rows, verdicts)


@pytest.mark.data
def test_report_generated_and_no_unresolved_parser_errors():
    if not (SECTIONS_PATH.exists() and KAGGLE_SECTIONS_PATH.exists()):
        pytest.skip("sections.jsonl / sections_kaggle.jsonl absent")
    if not DATA_QUALITY_PATH.exists():
        pytest.fail("DATA_QUALITY.md missing: run `uv run python -m nyaya.ingest.crosscheck`")
    verdicts = read_verdicts(DATA_QUALITY_PATH)
    unresolved = [
        k
        for k, (v, note) in verdicts.items()
        if v.lower() == "my parser wrong" and not note.lower().startswith(("fixed", "patched"))
    ]
    assert not unresolved, f"'my parser wrong' rows not fixed/patched: {unresolved}"

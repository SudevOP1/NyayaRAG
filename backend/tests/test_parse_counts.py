"""The only hard-coded counts in the project: 358 / 531 / 170 = 1,059 (PLAN.md §0.1 rule 5)."""

from __future__ import annotations

import pytest
from nyaya.ingest.parse_acts import parse_all

from nyaya.config import EXPECTED_SECTIONS, EXPECTED_TOTAL
from tests.conftest import act_pdfs, require_raw


@pytest.fixture(scope="module")
def sections():
    require_raw(*act_pdfs())
    return parse_all()


@pytest.mark.data
def test_total(sections):
    assert EXPECTED_TOTAL == 1059 == sum(EXPECTED_SECTIONS.values())
    assert len(sections) == EXPECTED_TOTAL


@pytest.mark.data
@pytest.mark.parametrize(("act", "n"), [("BNS", 358), ("BNSS", 531), ("BSA", 170)])
def test_contiguous(sections, act, n):
    nums = [s.section for s in sections if s.act == act]
    assert nums == list(range(1, n + 1))


@pytest.mark.data
def test_title_and_body_non_empty(sections):
    bad = [s.ref for s in sections if not s.title.strip() or not s.text.strip()]
    assert not bad, bad


@pytest.mark.data
def test_every_section_has_chapter_and_page(sections):
    bad = [s.ref for s in sections if not s.chapter_no or not s.chapter_title or not s.page_start]
    assert not bad, bad[:20]


@pytest.mark.data
def test_bns_106_2_not_in_force(sections):
    s106 = next(s for s in sections if s.act == "BNS" and s.section == 106)
    flags = {sub.number: sub.in_force for sub in s106.subsections}
    assert flags.get("2") is False
    assert flags.get("1") is True
    others = [
        f"{s.ref}({sub.number})"
        for s in sections
        for sub in s.subsections
        if not sub.in_force and not (s.act == "BNS" and s.section == 106)
    ]
    assert not others, others


@pytest.mark.data
def test_subsections_sequential(sections):
    for s in sections:
        nums = [int(x.number) for x in s.subsections if x.number]
        assert nums == list(range(1, len(nums) + 1)), s.ref


@pytest.mark.data
def test_no_running_headers_leak(sections):
    leaks = [s.ref for s in sections if "GAZETTE OF INDIA" in s.text.upper()]
    assert not leaks, leaks

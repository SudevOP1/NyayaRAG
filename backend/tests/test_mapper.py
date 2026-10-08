from __future__ import annotations

import pytest

from nyaya.config import MAP_PATH
from nyaya.ingest.parse_mapping import (
    Mapper,
    load_ipc_details,
    load_mapping_csv,
    normalise_ipc_query,
    parse_bns_ref,
    parse_ipc_refs,
)
from nyaya.ingest.schema import MapRow, read_jsonl


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("302", ["302"]),
        ("304B", ["304B"]),
        ("52A", ["52A"]),
        ("299 & 300", ["299", "300"]),
        ("Sec. 34", ["34"]),
        ("498-A", ["498A"]),
        ("120 B", ["120B"]),
        ("376(2)", ["376(2)"]),
        ("302, 303 and 304", ["302", "303", "304"]),
        ("", []),
        ("nan", []),
        ("-", []),
    ],
)
def test_parse_ipc_refs(raw, expected):
    assert parse_ipc_refs(raw) == expected


@pytest.mark.parametrize(
    ("raw", "ref", "sec"),
    [
        ("103(1)", "103(1)", 103),
        ("2(8)", "2(8)", 2),
        ("152", "152", 152),
        ("5(a)", "5(a)", 5),
        ("", None, None),
        (" 318 (4) ", "318(4)", 318),
    ],
)
def test_parse_bns_ref(raw, ref, sec):
    assert parse_bns_ref(raw) == (ref, sec)


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("420", "420"),
        ("IPC 420", "420"),
        ("s. 498-a", "498A"),
        ("Section 304 B", "304B"),
        ("ipc120b", "120B"),
        ("376(2)", "376(2)"),
    ],
)
def test_normalise_ipc_query(q, expected):
    assert normalise_ipc_query(q) == expected


@pytest.fixture
def fixture_mapper(fixtures_dir) -> Mapper:
    details = load_ipc_details(fixtures_dir / "ipc_details_sample.csv")
    rows = load_mapping_csv(fixtures_dir / "mapping_sample.csv", details, source="fixture")
    return Mapper(rows, notes_path=fixtures_dir / "mapper_notes.yaml")


def test_statuses(fixture_mapper):
    st = {(r.bns, tuple(r.ipc)): r.status for r in fixture_mapper.rows}
    assert st[("103(1)", ("302",))] == "carried_over"
    assert st[("2(8)", ("29",))] == "changed"
    assert st[(None, ("29A",))] == "deleted"
    assert st[("86", ())] == "new_section"


def test_ipc_details_joined(fixture_mapper):
    r = fixture_mapper.ipc_to_bns("302")
    assert r.found
    m = r.matches[0]
    assert m.bns == "103(1)" and m.ipc_offence == "Murder"
    assert m.ipc_punishment.startswith("Death")
    # "nan" becomes missing.
    assert fixture_mapper.ipc_to_bns("34").matches[0].ipc_punishment is None


def test_many_to_many(fixture_mapper):
    assert [m.bns for m in fixture_mapper.ipc_to_bns("299").matches] == ["100"]
    assert [m.bns for m in fixture_mapper.ipc_to_bns("300").matches] == ["100"]


def test_no_equivalent(fixture_mapper):
    r = fixture_mapper.ipc_to_bns("IPC 377")
    assert not r.found
    assert "no direct equivalent in BNS" in r.message
    assert r.source


def test_unknown_section(fixture_mapper):
    r = fixture_mapper.ipc_to_bns("999")
    assert not r.found and "not found" in r.message


def test_note_attached(fixture_mapper):
    r = fixture_mapper.ipc_to_bns("124A")
    assert r.matches[0].bns == "152"
    assert "not a re-enactment" in r.matches[0].note


# ---- Real data -------------------------------------------------------------------------

# Widely reported pairs (PLAN.md P1), confirmed against the government table (UP Police
# BNS_IPC_Comparative PDF, data/raw/gov/) before committing; see DECISIONS.md. The table maps
# IPC 302 to BNS 103 at section level (not 103(1)), and lists IPC 124A as Deleted with BNS 152 a
# New Section, so 124A is tested below as "no direct equivalent" plus the closest-provision note.
KNOWN_PAIRS: list[tuple[str, set[str]]] = [
    ("302", {"103"}),
    ("420", {"318(4)"}),
    ("307", {"109"}),
    ("376", {"64"}),
    ("498A", {"85", "86"}),
    ("304B", {"80"}),
    ("34", {"3(5)"}),
    ("120B", {"61(2)"}),
]


@pytest.fixture(scope="module")
def real_mapper() -> Mapper:
    if not MAP_PATH.exists():
        pytest.skip("ipc_bns_map.jsonl absent: run `uv run python -m nyaya.ingest.parse_mapping`")
    return Mapper(list(read_jsonl(MAP_PATH, MapRow)))


def _matches(mapper: Mapper, ipc: str) -> set[str]:
    out = set()
    for m in mapper.ipc_to_bns(ipc).matches:
        out.add(m.bns)
        out.add(str(m.bns_section))
    return out


@pytest.mark.data
def test_every_bns_section_appears(real_mapper):
    secs = {r.bns_section for r in real_mapper.rows if r.bns_section is not None}
    missing = sorted(set(range(1, 359)) - secs)
    assert not missing, f"BNS sections absent from the map: {missing}"


@pytest.mark.data
@pytest.mark.parametrize(("ipc", "expected"), KNOWN_PAIRS)
def test_known_pairs(real_mapper, ipc, expected):
    got = _matches(real_mapper, ipc)
    assert expected <= got, f"IPC {ipc}: expected {expected}, got {sorted(got)}"


@pytest.mark.data
def test_124a_no_equivalent_but_closest_provision_named(real_mapper):
    r = real_mapper.ipc_to_bns("124A")
    assert not r.found and "no direct equivalent in BNS" in r.message
    assert "BNS 152" in r.message and "not a re-enactment" in r.message


@pytest.mark.data
def test_377_no_equivalent(real_mapper):
    r = real_mapper.ipc_to_bns("377")
    assert not r.found and "no direct equivalent in BNS" in r.message


# Kaggle #6's "commonly confused" regression fixture (HIGH_CONFUSION_PAIRS in the dataset's
# starter notebook), as IPC -> expected BNS. Section level unless the fixture names a sub-section.
CONFUSED_PAIRS: list[tuple[str, str]] = [
    ("406", "316"),  # criminal breach of trust, not cheating
    ("420", "318"),  # cheating is 318, not 316
    ("447", "329"),  # criminal trespass
    ("443", "330"),  # lurking house-trespass: definitions only
    ("454", "331"),  # house-breaking punishment is 331
    ("468", "336(3)"),  # forgery for cheating, not 336(4)
    ("376", "64"),  # punishment for rape; 63 is the definition
    ("302", "103"),
    ("304A", "106"),
]


@pytest.mark.data
@pytest.mark.parametrize(("ipc", "bns"), CONFUSED_PAIRS)
def test_commonly_confused_pairs(real_mapper, ipc, bns):
    got = _matches(real_mapper, ipc)
    assert bns in got, f"IPC {ipc}: expected BNS {bns}, got {sorted(got)}"


def test_agreement_logic(fixture_mapper, tmp_path):
    from nyaya.ingest.parse_mapping import agreement_with_reference

    ref = tmp_path / "ref.csv"
    ref.write_text(
        "act,section,title,ipc_equivalent\n"
        "BNS,103(1),Murder,IPC 302\n"  # agrees (section level)
        "BNS,318(4),Cheating,IPC 415\n"  # disagrees: table has 420
        "BNS,86,Cruelty,New offence\n"  # agrees: new section
        "BNS,999,Bogus,IPC 1\n",  # BNS section not in table
        encoding="utf-8",
    )
    rep = agreement_with_reference(fixture_mapper.rows, ref)
    assert rep["n"] == 4
    assert rep["agree"] == 2
    assert {d["bns"] for d in rep["disagreements"]} == {"318(4)", "999"}


@pytest.mark.data
def test_agreement_report_written(real_mapper):
    from nyaya.config import KAGGLE_DIR
    from nyaya.ingest.parse_mapping import agreement_with_reference

    ref = KAGGLE_DIR / "bns_correspondence_sirjon" / "bns_correspondence.csv"
    if not ref.exists():
        pytest.skip("Kaggle #6 absent")
    rep = agreement_with_reference(real_mapper.rows, ref)
    assert rep["n"] > 0
    assert 0 <= rep["agree"] <= rep["n"]

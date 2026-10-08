from __future__ import annotations

import re

import pytest

from nyaya.config import CHUNKS_PATH, MAX_CHUNK_TOKENS, SECTIONS_PATH
from nyaya.ingest.chunk import chunk_section, chunk_sections, make_header
from nyaya.ingest.schema import Chunk, Section, SubSection, read_jsonl
from tests.conftest import word_count


def _sec(section: int, subs: list[tuple[str | None, str]], **kw) -> Section:
    text = "\n".join(t for _, t in subs)
    return Section(
        act=kw.pop("act", "BNS"),
        section=section,
        title=kw.pop("title", "Punishment for murder"),
        chapter_no=kw.pop("chapter_no", "VI"),
        chapter_title=kw.pop("chapter_title", "Of Offences Affecting the Human Body"),
        text=text,
        subsections=[
            SubSection(number=n, text=t, in_force=kw.get(f"in_force_{n}", True)) for n, t in subs
        ],
    )


def test_header_format_with_old_refs():
    s = _sec(103, [("1", "(1) Whoever commits murder shall be punished with death.")])
    assert make_header(s, ["IPC 302"]) == (
        "[BNS 103] Punishment for murder | Chapter VI: Of Offences Affecting the Human Body"
        " | Formerly: IPC 302"
    )
    assert make_header(s, []) == (
        "[BNS 103] Punishment for murder | Chapter VI: Of Offences Affecting the Human Body"
    )


def test_short_section_single_chunk():
    s = _sec(103, [("1", "(1) Whoever commits murder."), ("2", "(2) When a group of five.")])
    chunks = chunk_section(s, count_tokens=word_count, max_tokens=50, old_refs=["IPC 302"])
    assert len(chunks) == 1
    c = chunks[0]
    assert c.chunk_id == "BNS-103-c1"
    assert c.chunk_type == "section"
    assert c.subsections == ["1", "2"]
    assert c.old_refs == ["IPC 302"]
    assert c.text.startswith(c.header + "\n")
    assert c.tokens == word_count(c.text)


def test_long_section_packs_subsections_greedily():
    filler = " ".join(["word"] * 20)
    subs = [(str(i), f"({i}) {filler}") for i in range(1, 6)]
    s = _sec(64, subs)
    chunks = chunk_section(s, count_tokens=word_count, max_tokens=60)
    assert all(c.tokens <= 60 for c in chunks)
    assert all(c.chunk_type == "subsections" for c in chunks)
    covered = [n for c in chunks for n in c.subsections]
    assert covered == ["1", "2", "3", "4", "5"]  # each sub-section exactly once, in order
    assert len(chunks) == 3  # header ~16 words + 2 x 21 fits 60


def test_oversized_subsection_splits_at_clauses_never_inside():
    clauses = "\n".join(f"({c}) {' '.join(['def'] * 15)};" for c in "abcdefgh")
    s = _sec(
        2,
        [(None, "In this Sanhita, unless the context otherwise requires,—\n" + clauses)],
        title="Definitions",
        chapter_no="I",
        chapter_title="Preliminary",
    )
    chunks = chunk_section(s, count_tokens=word_count, max_tokens=60)
    assert len(chunks) > 1
    assert all(c.chunk_type == "clauses" for c in chunks)
    assert all(c.tokens <= 60 for c in chunks)
    # Every clause appears whole in exactly one chunk.
    for c in "abcdefgh":
        holders = [ch for ch in chunks if f"({c}) " in ch.text]
        assert len(holders) == 1
        assert holders[0].text.count("def") % 15 == 0


def test_illustrations_get_own_typed_chunks():
    body = "(1) Whoever cheats shall be punished.\nIllustrations\n(a) A cheats B.\n(b) C cheats D."
    s = _sec(318, [("1", body)], title="Cheating")
    chunks = chunk_section(s, count_tokens=word_count, max_tokens=200)
    types = [c.chunk_type for c in chunks]
    assert types == ["section", "illustration"]
    ill = chunks[1]
    assert ill.text.startswith(ill.header)
    assert "(a) A cheats B." in ill.text and "(b) C cheats D." in ill.text
    assert "Illustrations" not in chunks[0].text


def test_explanations_stay_with_subsection():
    body = "(1) Whoever does X.\nExplanation.—X includes Y."
    s = _sec(5, [("1", body)])
    chunks = chunk_section(s, count_tokens=word_count, max_tokens=200)
    assert len(chunks) == 1 and "Explanation.—X includes Y." in chunks[0].text


def test_not_in_force_subsection_isolated():
    s = Section(
        act="BNS",
        section=106,
        title="Causing death by negligence",
        chapter_no="VI",
        chapter_title="Of Offences Affecting the Human Body",
        text="(1) Whoever causes death.\n(2) Whoever drives rashly and escapes.",
        subsections=[
            SubSection(number="1", text="(1) Whoever causes death."),
            SubSection(number="2", text="(2) Whoever drives rashly and escapes.", in_force=False),
        ],
    )
    chunks = chunk_section(s, count_tokens=word_count, max_tokens=200)
    assert [c.subsections for c in chunks] == [["1"], ["2"]]
    assert [c.in_force for c in chunks] == [True, False]


def test_ids_unique_across_sections():
    secs = [_sec(i, [("1", f"({1}) text {i}")]) for i in range(1, 6)]
    chunks, stats = chunk_sections(secs, count_tokens=word_count, max_tokens=50)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    assert stats["n_chunks"] == len(chunks)
    assert stats["max_tokens"] <= 50


# ---- Real data (skips until the parser has produced sections.jsonl / chunks.jsonl) ----


@pytest.fixture(scope="module")
def real_chunks() -> list[Chunk]:
    if not CHUNKS_PATH.exists():
        pytest.skip("chunks.jsonl absent: run `uv run python -m nyaya.ingest.chunk`")
    return list(read_jsonl(CHUNKS_PATH, Chunk))


@pytest.mark.data
def test_real_chunks_within_limit(real_chunks):
    over = [c.chunk_id for c in real_chunks if c.tokens > MAX_CHUNK_TOKENS]
    assert not over, f"{len(over)} chunks over {MAX_CHUNK_TOKENS}: {over[:10]}"


@pytest.mark.data
def test_real_chunks_recount_with_bge_tokenizer(real_chunks):
    from nyaya.ingest.chunk import load_token_counter

    try:
        count = load_token_counter(local_files_only=True)
    except Exception as e:  # not in local HF cache
        pytest.skip(f"bge tokenizer not cached locally: {e}")
    bad = [c.chunk_id for c in real_chunks if count(c.text) != c.tokens]
    assert not bad, f"stored token counts differ from tokenizer: {bad[:10]}"


@pytest.mark.data
def test_real_chunks_headers_ids_types(real_chunks):
    ids = [c.chunk_id for c in real_chunks]
    assert len(ids) == len(set(ids))
    for c in real_chunks:
        assert c.text.startswith(c.header)
        assert re.match(rf"^\[{c.act} {c.section}\] ", c.header)
        assert re.match(rf"^{c.act}-{c.section}-c\d+$", c.chunk_id)
    assert any(c.chunk_type == "illustration" for c in real_chunks)


@pytest.mark.data
def test_real_chunks_cover_every_section(real_chunks):
    if not SECTIONS_PATH.exists():
        pytest.skip("sections.jsonl absent")
    secs = {(s.act, s.section) for s in read_jsonl(SECTIONS_PATH, Section)}
    covered = {(c.act, c.section) for c in real_chunks}
    assert secs == covered


@pytest.mark.data
def test_real_chunks_no_clause_split(real_chunks):
    """No clause was cut mid-way (the chunker logs any sentence-level split it had to make)."""
    import json

    from nyaya.config import CHUNK_STATS_PATH

    stats = json.loads(CHUNK_STATS_PATH.read_text(encoding="utf-8"))
    assert stats["clause_splits"] == [], stats["clause_splits"]


def test_clause_too_big_is_logged_not_silent():
    huge = "(a) " + " ".join(["x."] * 80)
    s = _sec(2, [(None, "Defs,—\n" + huge + "\n(b) short;")], title="Definitions")
    chunks, stats = chunk_sections([s], count_tokens=word_count, max_tokens=40)
    assert all(c.tokens <= 40 for c in chunks)
    assert stats["clause_splits"] == ["BNS 2"]

from nyaya.ingest.text import (
    drop_stray_footnotes,
    normalise_text,
    split_blocks,
    split_illustrations,
    split_subsections,
)


def test_normalise_text_crlf_and_spaces():
    assert normalise_text("a  b\r\n\r\n c\t d \r\n") == "a b\nc d"


def test_drop_stray_footnotes():
    assert drop_stray_footnotes("from such date1 as the Government") == (
        "from such date as the Government"
    )
    # Real numbers survive.
    assert drop_stray_footnotes("section 498A and 302, IPC 34") == "section 498A and 302, IPC 34"


def test_split_subsections_sequential_only():
    text = "(1) Whoever commits murder.\nas in sub-section (1) above\n(3) out of order\n(2) Second."
    units = split_subsections(text)
    assert [u[0] for u in units] == ["1", "2"]
    assert "(3) out of order" in units[0][1]


def test_split_subsections_unnumbered():
    assert split_subsections("Whoever does X shall be punished.") == [
        (None, "Whoever does X shall be punished.")
    ]


def test_split_subsections_preamble_kept():
    units = split_subsections("Intro text\n(1) first")
    assert units == [(None, "Intro text"), ("1", "(1) first")]


def test_split_blocks_clauses_and_nested_roman():
    text = (
        "In this Sanhita,—\n(a) first;\n(i) nested one;\n(ii) nested two;\n(b) second;\n"
        "Explanation.—about b.\n(c) third;\n(d) fourth;\n(e) e;\n(f) f;\n(g) g;\n(h) h;\n(i) i;"
    )
    blocks = split_blocks(text)
    kinds = [(b.kind, b.label) for b in blocks]
    assert kinds[0] == ("preamble", None)
    labels = [b.label for b in blocks if b.kind == "clause"]
    assert labels == ["a", "b", "c", "d", "e", "f", "g", "h", "i"]
    a = next(b for b in blocks if b.label == "a")
    assert "(ii) nested two;" in a.text
    b = next(b for b in blocks if b.label == "b")
    assert "Explanation.—about b." in b.text


def test_split_blocks_illustrations_then_explanation():
    text = (
        "Whoever does X.\nIllustrations\n(a) A does X.\n(b) B does X.\nExplanation.—X includes Y."
    )
    blocks = split_blocks(text)
    assert [b.kind for b in blocks] == ["preamble", "illustration", "preamble"]
    assert split_illustrations(blocks[1].text) == ["(a) A does X.", "(b) B does X."]

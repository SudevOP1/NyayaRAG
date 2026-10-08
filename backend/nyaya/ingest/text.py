"""Text helpers shared by the PDF parser, the Kaggle loader and the chunker.

Statute text is kept as newline-separated paragraphs. Structural markers are only recognised at
the start of a paragraph, and numbered markers only when they continue the running sequence
(`(1)`, `(2)`, … or `(a)`, `(b)`, …), so a cross-reference such as "under sub-section (1)" or a
nested `(i)` inside clause `(c)` never starts a new unit.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass

SUBSECTION_RE = re.compile(r"^\((\d{1,3})\)\s*")
CLAUSE_RE = re.compile(r"^\(([a-z]{1,3})\)\s*")
ILLUSTRATION_RE = re.compile(r"^Illustrations?\b\.?\s*$|^Illustrations?\s*[.:—–-]", re.I)
# Markers that end an illustration block and return to the main text.
MAIN_RESUME_RE = re.compile(r"^(Explanation|Exception|Provided\b|\(\d{1,3}\)\s)", re.I)
STRAY_FOOTNOTE_RE = re.compile(r"(?<=[a-z]{3})\d{1,2}(?=[\s.,;:)]|$)")


def normalise_text(text: str) -> str:
    """Normalise line breaks and spaces; keep one paragraph per line."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = text.replace("—", "—").replace("﻿", "")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def drop_stray_footnotes(text: str) -> str:
    """Remove footnote digits glued to words ("date1" -> "date")."""
    return STRAY_FOOTNOTE_RE.sub("", text)


def paragraphs(text: str) -> list[str]:
    return [p for p in text.split("\n") if p.strip()]


def _letter_index(label: str) -> int | None:
    """`a`->1 … `z`->26, `aa`->27 (statutes continue with doubled letters)."""
    if len(set(label)) == 1 and label[0] in string.ascii_lowercase:
        return (len(label) - 1) * 26 + string.ascii_lowercase.index(label[0]) + 1
    return None


def split_subsections(
    text: str, may_start: list[bool] | None = None
) -> list[tuple[str | None, str]]:
    """Split a section body into `(number, text)` units.

    The text before `(1)` (if any) is a unit with number `None`. A section with no numbered
    sub-sections returns one `(None, text)` unit. `may_start[i]` (from the PDF indent) can veto
    paragraph `i` as a sub-section start, e.g. a nested "(1) Rigorous" list inside a clause.
    """
    units: list[tuple[str | None, list[str]]] = [(None, [])]
    expected = 1
    for i, para in enumerate(paragraphs(text)):
        m = SUBSECTION_RE.match(para)
        allowed = may_start is None or may_start[i]
        if m and allowed and int(m.group(1)) == expected:
            units.append((m.group(1), [para]))
            expected += 1
        else:
            units[-1][1].append(para)
    out = [(num, "\n".join(ps)) for num, ps in units if ps]
    return out


@dataclass
class Block:
    """A run of paragraphs inside one sub-section."""

    kind: str  # "preamble" | "clause" | "illustration"
    label: str | None
    text: str


def split_blocks(text: str) -> list[Block]:
    """Split one sub-section into preamble, top-level clauses and illustration blocks.

    Explanations, Exceptions and provisos stay attached to the clause or preamble they follow.
    Inside an illustration block, `(a)`, `(b)` … are individual illustrations, not clauses.
    """
    blocks: list[Block] = []
    cur_kind: str = "preamble"
    cur_label: str | None = None
    cur: list[str] = []
    expected_clause = 1

    def flush() -> None:
        if cur:
            blocks.append(Block(cur_kind, cur_label, "\n".join(cur)))

    for para in paragraphs(text):
        if ILLUSTRATION_RE.match(para):
            flush()
            cur_kind, cur_label, cur = "illustration", None, [para]
            continue
        if cur_kind == "illustration":
            if MAIN_RESUME_RE.match(para):
                flush()
                cur_kind, cur_label, cur = "preamble", None, [para]
            else:
                cur.append(para)
            continue
        m = CLAUSE_RE.match(para)
        if m and _letter_index(m.group(1)) == expected_clause:
            flush()
            cur_kind, cur_label, cur = "clause", m.group(1), [para]
            expected_clause += 1
            continue
        cur.append(para)
    flush()
    return blocks


def split_illustrations(text: str) -> list[str]:
    """Split an illustration block into individual illustrations (`(a)`, `(b)` …)."""
    paras = paragraphs(text)
    if paras and ILLUSTRATION_RE.match(paras[0]):
        paras = paras[1:]
    items: list[list[str]] = []
    expected = 1
    for para in paras:
        m = CLAUSE_RE.match(para)
        if m and _letter_index(m.group(1)) == expected:
            items.append([para])
            expected += 1
        elif items:
            items[-1].append(para)
        else:
            items.append([para])
    return ["\n".join(i) for i in items]


_ROMAN = [
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
]


def int_to_roman(n: int) -> str:
    out = []
    for value, sym in _ROMAN:
        while n >= value:
            out.append(sym)
            n -= value
    return "".join(out)


def roman_to_int(s: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total, prev = 0, 0
    for ch in reversed(s.upper()):
        v = vals[ch]
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return total


_SMALL_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "into",
    "from",
}


def smart_title(s: str) -> str:
    """ "OF OFFENCES AGAINST THE STATE" -> "Of Offences against the State"-style title case."""
    words = s.lower().split()
    out = []
    for i, w in enumerate(words):
        if i > 0 and w in _SMALL_WORDS:
            out.append(w)
        else:
            out.append("-".join(p[:1].upper() + p[1:] for p in w.split("-")))
    return " ".join(out)

"""Row schemas shared by the parser, the Kaggle loader, the chunker and the mapper."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel, Field

Act = Literal["BNS", "BNSS", "BSA"]
Source = Literal["india_code", "kaggle"]
ChunkType = Literal["section", "subsections", "clauses", "illustration"]


class SubSection(BaseModel):
    """A numbered sub-section `(1)`, or the unnumbered body of a section (`number=None`)."""

    number: str | None = None
    text: str
    in_force: bool = True


class Section(BaseModel):
    act: Act
    section: int
    title: str
    chapter_no: str | None = None  # Roman numeral as printed, e.g. "VI"
    chapter_title: str | None = None
    part: str | None = None  # BSA has Parts
    text: str
    subsections: list[SubSection] = Field(default_factory=list)
    page_start: int | None = None  # 1-based PDF page
    in_force: bool = True  # False only if *every* sub-section is not in force
    source: Source = "india_code"

    @property
    def ref(self) -> str:
        return f"{self.act} {self.section}"


class Chunk(BaseModel):
    chunk_id: str
    act: Act
    section: int
    subsections: list[str] = Field(default_factory=list)
    title: str
    chapter: str | None = None
    chunk_type: ChunkType
    old_refs: list[str] = Field(default_factory=list)
    in_force: bool = True
    tokens: int
    page: int | None = None
    header: str
    text: str  # header + body, exactly what gets embedded


class MapRow(BaseModel):
    bns: str | None  # e.g. "103(1)"; None for IPC sections with no successor
    bns_section: int | None
    ipc: list[str] = Field(default_factory=list)  # e.g. ["302"], ["299", "300"]
    bns_title: str | None = None
    ipc_title: str | None = None
    status: Literal["carried_over", "changed", "deleted", "new_section", "new_subsection"]
    ipc_offence: str | None = None
    ipc_punishment: str | None = None
    source: str


M = TypeVar("M", bound=BaseModel)


def write_jsonl(path: Path, rows: Iterable[BaseModel]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(r.model_dump_json() + "\n")
            n += 1
    return n


def read_jsonl(path: Path, model: type[M]) -> Iterator[M]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield model.model_validate(json.loads(line))

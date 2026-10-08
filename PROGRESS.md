# Progress log

One note per finished phase, appended at the end of each phase (see `CLAUDE.md` → Phase workflow).
Status summary lives in `PLAN.md` §0.0.

Template:

```
## P<N>: <name> (<YYYY-MM-DD>)
**Shipped:** ...
**Deferred:** ... (why)
**Tests:** pytest x passed / tsc ok / lint ok
**Measured numbers:** ... (results JSON paths)
**Human tasks remaining:** ...
**Notes / decisions:** ... (also in DECISIONS.md)
```

---

## P1: Foundation: repo, data, parser, chunker, mapper (2026-10-08)
**Shipped:**
- Repo setup: `.gitignore`, MIT `LICENSE`, `.env.example`, §6 folder skeleton, `DECISIONS.md`, `Makefile`, `backend/pyproject.toml` + `uv.lock` (Python 3.11), CI skeleton (`.github/workflows/ci.yml`: uv sync, ruff check/format, pytest).
- `scripts/download.py` (`nyaya/ingest/download.py`): 3 Act PDFs (MHA-hosted Gazette copies; India Code blocks downloads), CAPT BNS→IPC, CAPT BNSS→CrPC, UP Police comparative PDFs, 8 Kaggle datasets; SHA-256 manifest. Accepts `kaggle.json` or `access_token` (UTF-16 safe).
- `scripts/pdf_spike.py`: layout spike. All three Acts are Gazette layout (a); details in `DECISIONS.md`.
- `nyaya/ingest/parse_acts.py`: glyph-level line rebuild (fixes glued words), marginal-note titles, chapters/parts, sub-sections by indent, patches from `data/patches/acts.yaml` (BNS 106(2) `in_force=false`).
- `nyaya/ingest/load_kaggle.py` (fast start, `sections_kaggle.jsonl`), `nyaya/ingest/crosscheck.py` (`data/golden/DATA_QUALITY.md`).
- `nyaya/ingest/chunk.py`: section-aware chunker with bge tokenizer, typed illustration chunks, `Formerly:` headers.
- `nyaya/ingest/parse_mapping.py`: IPC→BNS mapper + reverse index, reviewed notes, agreement report vs Kaggle #6 (`data/golden/MAPPER_AGREEMENT.md`); `scripts/sample_mapper_check.py` for the 40-row hand-check.
**Deferred:** BNSS/BSA Schedules (stretch, as planned). Per-sub-section `Formerly:` refs in chunk headers (revisit with P2 enrich ablation).
**Tests:** pytest 96 passed (with data; data tests skip cleanly without it) / ruff check + format ok.
**Measured numbers:**
- Sections: BNS 358, BNSS 531, BSA 170 = 1,059 (`data/processed/sections.jsonl`).
- Chunks: 1,464 (BNS 523, BNSS 689, BSA 252); types: section 909, subsections 284, illustration 171, clauses 100; tokens max 350, mean 176.4, p50 157, p95 331; 0 clause splits (`data/processed/chunk_stats.json`).
- Cross-check: 9/1,059 sections below 90 (BNS 4, BNSS 1, BSA 4), all pending developer verdicts; 3 parser title bugs found by the check and fixed.
- Mapper: 578 rows (carried over 405, changed 136, deleted 19, new section 10, new sub-section 8); all 358 BNS sections covered; agreement with Kaggle #6: 150/150 section level; 9 known pairs + 9 "commonly confused" pairs pass.
**Human tasks remaining:** verdicts for the 9 rows in `DATA_QUALITY.md`; 40-row mapper hand-check (`MAPPER_HANDCHECK.md`) against the government PDFs and NCRB Sankalan, totals in `data/golden/CHANGELOG.md`; read the spike output and confirm the layout call; rotate the Kaggle token (see note in session); confirm CAPT Bhopal's affiliation on bprd.nic.in before README.
**Notes / decisions:** IPC 302→BNS 103 (section level) and IPC 124A→no direct equivalent (+ BNS 152 closest-provision note) follow the government table; see `DECISIONS.md`.

# CLAUDE.md

Guidance for Claude Code working in this repo.

## Project

**NyayaRAG**: citation-grounded legal Q&A over all 1,059 sections of India's new criminal laws
(BNS 358, BNSS 531, BSA 170), with hybrid BM25 + dense retrieval (Qdrant, RRF), a fine-tuned
bge-small embedder, a cross-encoder reranker, an IPC-to-BNS mapper, a LangGraph tool-calling agent,
a citation validator, a scikit-learn answerability gate, a QLoRA-tuned Qwen2.5-1.5B, a streaming
FastAPI + Docker service, Langfuse tracing, an MCP server, a React UI and a CI eval gate.

It backs four resume bullets (`PLAN.md` §10). **The resume is the spec**: every feature and number
there must become true and be measured honestly (`PLAN.md` §9).

## Key files

| File | Purpose |
|---|---|
| `PLAN.md` | Source of truth. §0.0 phase status table, §0.1 ground rules, §7 phase overview, §8 per-phase tasks, §9 metric definitions |
| `PROGRESS.md` | Append-only log, one note per finished phase |
| `DECISIONS.md` | What was chosen and why (create in P1, append whenever a non-obvious choice is made) |

## Repo layout

- `backend/`: Python 3.11, `uv`-managed. Package `nyaya/` (ingest, retrieval, generation, agent, api,
  mcp_server, tracing), plus `scripts/`, `training/`, `eval/`, `configs/`, `data/`, `tests/`.
  All Python paths in `PLAN.md` are relative to `backend/`.
- `web/`: Vite + React + TypeScript + Tailwind chat UI (built in P5).
- Root: `docker-compose.yml`, `Makefile`, `.env.example`, `.github/workflows/`, docs.

## Phase workflow

When prompted `implement the phase N from PLAN.md` (or similar), follow this order every time:

1. **Ask first.** Read `PLAN.md` + `PROGRESS.md`, then ask any clarifying questions up front
   (`AskUserQuestion`) before writing code. Skip only if nothing is genuinely ambiguous.
2. **Implement the entire phase** in one pass: all backend work and all UI screens listed for it in
   `PLAN.md` §8. This supersedes any "stop after each step/screen for verification" loop, including
   the older milestone-by-milestone wording; `PLAN.md` §0.1 rule 3 already reflects this.
3. **Run all relevant tests** and fix failures before finishing:
   - Frontend (once `web/` exists): `npx tsc --noEmit` and `npm run lint` from `web/`.
   - Backend (whenever backend code is touched): `uv run pytest` from `backend/` (also
     `uv run ruff check .`, which CI runs).
   Tests yes; **the app and dev servers no** (see "Do not run" below).
4. **Finish with a summary**: what shipped, what was deferred (and why), then step-by-step
   manual-testing instructions with the exact commands the developer should run and what to check
   (on screen, in output files or in reports). List the phase's 🧑 human tasks that remain.
   Also append the phase note to `PROGRESS.md` and update the `PLAN.md` §0.0 status table.

## Do not run (give the developer the command instead)

- Dev servers or the app: `uvicorn`, `npm run dev`, `docker compose up`, the MCP server.
- Docker image builds.
- Paid or rate-limited LLM jobs: Groq bulk calls (synthetic queries, OOD generation, RAGAS judge,
  SFT teacher). Small mocked/fixture calls in tests are fine; real network calls in tests are not.
- GPU training (embedder fine-tune, QLoRA): these run on Colab/Kaggle. Write the scripts/notebook.
- Anything that pushes: `git push`, HF Hub uploads, publishing. Commit only when asked.

## Non-negotiables

- **India Code text is the only ground truth.** Kaggle data is for fast start, cross-checks and
  external test slices; never index it in the final build or cite it as the law.
- **Never hard-code expected metric values.** The only hard-coded counts are the parser assertions
  358 / 531 / 170 / 1,059. Numbers in `PLAN.md` §3 are sanity checks.
- **Dev/test discipline.** Tune on the golden dev split only. Never read test results to choose
  hyperparameters, prompts or thresholds.
- **Human-only tasks stay human.** Do not write golden questions, verification passes, hand labels,
  hand grades or judge-agreement labels with an LLM. Build the tooling; leave the content to the
  developer.
- **Tests before code**; never skip, weaken or delete a test to make it pass. Tests that need
  downloaded data skip with a clear reason when `backend/data/raw/` is absent.
- **No secrets or raw data in git.** `.env`, `kaggle.json`, `backend/data/raw/`, share-alike derived
  slices (`backend/data/external/*.jsonl`), `mlruns/`, model caches stay ignored.
- **Disclaimer everywhere** (UI banner, API responses, MCP tool descriptions, README). Text is in
  `PLAN.md` header. BNS 106(2) is `in_force=false` and answers citing it carry a warning.
- **Citation format** is exactly `[BNS 103(1)]`, `[BNSS 173]`, `[BSA 63]`.
- Model IDs and providers live in `configs/`, never in code (Groq model IDs churn; see `PLAN.md` §3c).
- Every results JSON carries git SHA, config, split, n, metrics and CIs.

## Conventions

- Python: ruff (lint + format), type hints, pydantic for schemas, `pathlib`, config via
  `nyaya/config.py` reading `.env`. Small pure functions for anything with math (RRF, metrics,
  bootstrap) so they are unit-testable.
- Retrieval goes through one entry point (`nyaya/retrieval/pipeline.py: search`) shared by the
  agent, API, MCP server and CI gate.
- Tests use small fixtures and local-mode Qdrant (`QdrantClient(path=...)` or `":memory:"`), and fake
  LLMs; no network.
- TypeScript: strict mode, typed API client in `web/src/api.ts`, SSE parsing in its own module.
- Shell: the developer is on Windows (PowerShell). Give manual-testing commands that work there
  (e.g. `cd backend; uv run pytest`), and note POSIX equivalents only where they differ.
- Keep Markdown code identifiers in backticks.

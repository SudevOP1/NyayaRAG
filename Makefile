# Targets run from the repo root. On Windows without make, run the commands under each target
# from backend/ in PowerShell.
.PHONY: data parse chunks map crosscheck test lint

data:            ## download PDFs + Kaggle datasets, hash into MANIFEST.json
	cd backend && uv run python scripts/download.py

parse:           ## Act PDFs -> data/processed/sections.jsonl
	cd backend && uv run python -m nyaya.ingest.parse_acts && uv run python -m nyaya.ingest.load_kaggle

map:             ## correspondence table -> ipc_bns_map.jsonl + agreement report
	cd backend && uv run python -m nyaya.ingest.parse_mapping

chunks: map      ## sections.jsonl -> chunks.jsonl + chunk_stats.json
	cd backend && uv run python -m nyaya.ingest.chunk

crosscheck:      ## parser vs Kaggle -> data/golden/DATA_QUALITY.md
	cd backend && uv run python -m nyaya.ingest.crosscheck

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .

"""Project paths and settings. Secrets come from `.env` (repo root or `backend/`)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
ACTS_DIR = RAW_DIR / "acts"
GOV_DIR = RAW_DIR / "gov"
KAGGLE_DIR = RAW_DIR / "kaggle"
PATCHES_DIR = DATA_DIR / "patches"
PROCESSED_DIR = DATA_DIR / "processed"
GOLDEN_DIR = DATA_DIR / "golden"
CONFIGS_DIR = BACKEND_DIR / "configs"

SECTIONS_PATH = PROCESSED_DIR / "sections.jsonl"
KAGGLE_SECTIONS_PATH = PROCESSED_DIR / "sections_kaggle.jsonl"
CHUNKS_PATH = PROCESSED_DIR / "chunks.jsonl"
CHUNK_STATS_PATH = PROCESSED_DIR / "chunk_stats.json"
MAP_PATH = PROCESSED_DIR / "ipc_bns_map.jsonl"
MAP_REVERSE_PATH = PROCESSED_DIR / "ipc_to_bns_index.json"
MANIFEST_PATH = RAW_DIR / "MANIFEST.json"
DATA_QUALITY_PATH = GOLDEN_DIR / "DATA_QUALITY.md"

# The only hard-coded counts in the project (PLAN.md §0.1 rule 5).
EXPECTED_SECTIONS: dict[str, int] = {"BNS": 358, "BNSS": 531, "BSA": 170}
EXPECTED_TOTAL = 1059

ACT_FULL_NAMES: dict[str, str] = {
    "BNS": "Bharatiya Nyaya Sanhita, 2023",
    "BNSS": "Bharatiya Nagarik Suraksha Sanhita, 2023",
    "BSA": "Bharatiya Sakshya Adhiniyam, 2023",
}

EMBED_MODEL_ID = "BAAI/bge-small-en-v1.5"
MAX_CHUNK_TOKENS = 350

DISCLAIMER = (
    "NyayaRAG gives general information about the text of the BNS, BNSS and BSA. "
    "It is not legal advice, may be wrong or out of date, and is no substitute for a "
    "qualified lawyer. Always read the official Act text."
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str = ""
    llm_provider: str = "groq"
    ollama_base_url: str = "http://localhost:11434"
    qdrant_url: str = "http://localhost:6333"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    mlflow_tracking_uri: str = "file:./mlruns"
    kaggle_username: str = ""
    kaggle_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""Fetch the Act PDFs, the government correspondence tables and the Kaggle datasets.

Everything lands in `data/raw/` (gitignored) and gets a SHA-256 entry in `data/raw/MANIFEST.json`.
India Code blocks scripted (and often browser) downloads, so the Act PDFs come from the Gazette of
India copies hosted by the Ministry of Home Affairs (same enacted text). If a download fails, save
the file by hand to the path printed below and re-run with `--hash-only` so the manifest records it.
"""

from __future__ import annotations

import argparse
import codecs
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import requests

from nyaya.config import ACTS_DIR, GOV_DIR, KAGGLE_DIR, MANIFEST_PATH, RAW_DIR

USER_AGENT = "Mozilla/5.0 (NyayaRAG data fetcher; +https://github.com/SudevOP1/NyayaRAG)"
KAGGLE_TOKEN_MSG = "Kaggle token not found: see PLAN.md §0.2"


@dataclass(frozen=True)
class PdfSource:
    name: str
    url: str
    dest: Path
    note: str = ""


PDF_SOURCES: list[PdfSource] = [
    PdfSource(
        "BNS",
        "https://www.mha.gov.in/sites/default/files/250883_english_01042024.pdf",
        ACTS_DIR / "bns.pdf",
        "Bharatiya Nyaya Sanhita, 2023 (Act 45 of 2023), Gazette of India copy hosted by MHA. "
        "India Code: https://www.indiacode.nic.in/handle/123456789/20062",
    ),
    PdfSource(
        "BNSS",
        "https://www.mha.gov.in/sites/default/files/250884_2_english_01042024.pdf",
        ACTS_DIR / "bnss.pdf",
        "Bharatiya Nagarik Suraksha Sanhita, 2023 (Act 46 of 2023), Gazette of India copy hosted "
        "by MHA. India Code: https://indiacode.nic.in/handle/123456789/20099",
    ),
    PdfSource(
        "BSA",
        "https://www.mha.gov.in/sites/default/files/250882_english_01042024.pdf",
        ACTS_DIR / "bsa.pdf",
        "Bharatiya Sakshya Adhiniyam, 2023 (Act 47 of 2023), Gazette of India copy hosted by MHA. "
        "India Code: https://indiacode.nic.in/handle/123456789/20063",
    ),
    PdfSource(
        "CAPT_BNS_IPC",
        "https://www.keralaprisons.gov.in/userfiles/act-and-rules/comparison_summary_BNS_to_IPC.pdf",
        GOV_DIR / "capt_bns_to_ipc.pdf",
        "Correspondence Table and Comparison Summary, BNS 2023 to IPC 1860 (CAPT Bhopal)",
    ),
    PdfSource(
        "CAPT_BNSS_CRPC",
        "https://keralaprisons.gov.in/userfiles/act-and-rules/comparison_summary_BNSS_to_CrPC.pdf",
        GOV_DIR / "capt_bnss_to_crpc.pdf",
        "Comparison Summary, BNSS 2023 to CrPC 1973 (CAPT Bhopal)",
    ),
    PdfSource(
        "UPP_BNS_IPC",
        "https://uppolice.gov.in/site/writereaddata/siteContent/Three%20New%20Major%20Acts/"
        "202406281710564823BNS_IPC_Comparative.pdf",
        GOV_DIR / "uppolice_bns_ipc_comparative.pdf",
        "UP Police BNS_IPC_Comparative",
    ),
]

# (local folder name, Kaggle ref). PLAN.md §3 numbers in comments.
KAGGLE_DATASETS: list[tuple[str, str]] = [
    ("bns_nandr39", "nandr39/bharatiya-nyaya-sanhita-dataset-bns"),  # 2
    ("bsa_nandr39", "nandr39/bharatiya-sakshya-adhiniyam-dataset-bsa"),  # 3
    ("bnss_tanujsaxena", "tanujsaxena/the-bharatiya-nagarik-suraksha-sanhita-2023"),  # 4
    ("bns_ipc_mapping", "tanujsaxena/bns-ipc-mapping"),  # 5
    ("bns_correspondence_sirjon", "sirjon/bns-correspondence"),  # 6
    ("ipc_sections_dev523", "dev523/indian-penal-code-ipc-sections-information"),  # 7
    ("oldlaw_qa_akshatgupta7", "akshatgupta7/llm-fine-tuning-dataset-of-indian-legal-texts"),  # 8
    ("indiclegalqa", "kmldas/indiclegalqa-dataset"),  # 9
]


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk_size):
            h.update(block)
    return h.hexdigest()


def kaggle_token_available(env: dict[str, str] | None = None, home: Path | None = None) -> bool:
    env = dict(os.environ) if env is None else env
    if env.get("KAGGLE_USERNAME") and env.get("KAGGLE_KEY"):
        return True
    if env.get("KAGGLE_API_TOKEN"):
        return True
    config_dir = env.get("KAGGLE_CONFIG_DIR")
    home = Path.home() if home is None else home
    # Legacy kaggle.json or the newer single-token `access_token` file (kaggle >= 1.7).
    names = ("kaggle.json", "access_token")
    candidates = [home / ".kaggle" / n for n in names]
    if config_dir:
        candidates = [Path(config_dir) / n for n in names] + candidates
    return any(p.is_file() for p in candidates)


def build_manifest(raw_dir: Path, sources: dict[str, str] | None = None) -> dict:
    """Hash every file under `raw_dir` (except the manifest itself)."""
    sources = sources or {}
    files = {}
    for p in sorted(raw_dir.rglob("*")):
        if not p.is_file() or p.name == MANIFEST_PATH.name:
            continue
        rel = p.relative_to(raw_dir).as_posix()
        files[rel] = {"sha256": sha256_file(p), "bytes": p.stat().st_size}
        if rel in sources:
            files[rel]["source"] = sources[rel]
    return {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "files": files}


def download_pdf(src: PdfSource, timeout: int = 120, force: bool = False) -> bool:
    if src.dest.exists() and not force:
        print(f"  [skip] {src.name}: {src.dest} exists")
        return True
    src.dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(src.url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        r.raise_for_status()
        if not r.content.startswith(b"%PDF"):
            raise ValueError("response is not a PDF")
    except Exception as e:  # network errors, HTTP errors, HTML block pages
        print(f"  [FAIL] {src.name}: {e}")
        print(f"         Download manually from {src.url}")
        print(f"         and save it as {src.dest}, then re-run with --hash-only.")
        return False
    src.dest.write_bytes(r.content)
    print(f"  [ok]   {src.name}: {len(r.content):,} bytes -> {src.dest}")
    return True


def read_token_file(path: Path) -> str:
    """Read a token file whatever its encoding (PowerShell `>` writes UTF-16 with a BOM)."""
    raw = path.read_bytes()
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig")
    return text.strip()


def _export_access_token() -> None:
    """Pass `~/.kaggle/access_token` to the client via `KAGGLE_API_TOKEN`, cleaned of BOMs."""
    if os.environ.get("KAGGLE_API_TOKEN"):
        return
    path = Path(os.environ.get("KAGGLE_CONFIG_DIR", Path.home() / ".kaggle")) / "access_token"
    if path.is_file():
        os.environ["KAGGLE_API_TOKEN"] = read_token_file(path)


def download_kaggle(force: bool = False) -> bool:
    if not kaggle_token_available():
        print(f"  [FAIL] {KAGGLE_TOKEN_MSG}")
        return False
    _export_access_token()
    from kaggle.api.kaggle_api_extended import KaggleApi  # import authenticates; keep it lazy

    api = KaggleApi()
    api.authenticate()
    ok = True
    for folder, ref in KAGGLE_DATASETS:
        dest = KAGGLE_DIR / folder
        if dest.exists() and any(dest.iterdir()) and not force:
            print(f"  [skip] {ref}: {dest} not empty")
            continue
        dest.mkdir(parents=True, exist_ok=True)
        try:
            api.dataset_download_files(ref, path=str(dest), unzip=True, quiet=True)
            print(f"  [ok]   {ref} -> {dest}")
        except Exception as e:
            ok = False
            print(f"  [FAIL] {ref}: {e}")
            print("         Open the dataset page once in a browser and accept its terms.")
    return ok


def write_manifest() -> Path:
    sources = {
        s.dest.relative_to(RAW_DIR).as_posix(): s.url for s in PDF_SOURCES if s.dest.exists()
    }
    for folder, ref in KAGGLE_DATASETS:
        for p in (KAGGLE_DIR / folder).rglob("*"):
            if p.is_file():
                sources[p.relative_to(RAW_DIR).as_posix()] = f"kaggle:{ref}"
    manifest = build_manifest(RAW_DIR, sources)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Manifest: {len(manifest['files'])} files -> {MANIFEST_PATH}")
    return MANIFEST_PATH


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-pdfs", action="store_true")
    ap.add_argument("--skip-kaggle", action="store_true")
    ap.add_argument("--hash-only", action="store_true", help="only (re)write MANIFEST.json")
    ap.add_argument("--force", action="store_true", help="re-download existing files")
    args = ap.parse_args(argv)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ok = True
    if not args.hash_only:
        if not args.skip_pdfs:
            print("PDFs:")
            ok &= all([download_pdf(s, force=args.force) for s in PDF_SOURCES])
        if not args.skip_kaggle:
            print("Kaggle:")
            ok &= download_kaggle(force=args.force)
    write_manifest()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

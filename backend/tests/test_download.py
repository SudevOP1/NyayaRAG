from pathlib import Path

from nyaya.ingest.download import build_manifest, kaggle_token_available, sha256_file


def test_token_missing(tmp_path: Path):
    assert not kaggle_token_available(env={}, home=tmp_path)


def test_token_env():
    assert kaggle_token_available(env={"KAGGLE_USERNAME": "u", "KAGGLE_KEY": "k"}, home=Path("/x"))


def test_token_files(tmp_path: Path):
    for name in ("kaggle.json", "access_token"):
        home = tmp_path / name.replace(".", "_")
        (home / ".kaggle").mkdir(parents=True)
        (home / ".kaggle" / name).write_text("x")
        assert kaggle_token_available(env={}, home=home)


def test_manifest_hashes(tmp_path: Path):
    (tmp_path / "a").mkdir()
    f = tmp_path / "a" / "x.txt"
    f.write_bytes(b"abc")
    m = build_manifest(tmp_path, {"a/x.txt": "src"})
    assert m["files"]["a/x.txt"]["sha256"] == sha256_file(f)
    assert m["files"]["a/x.txt"]["sha256"].startswith("ba7816bf")
    assert m["files"]["a/x.txt"]["source"] == "src"


def test_read_token_file_encodings(tmp_path: Path):
    from nyaya.ingest.download import read_token_file

    for enc, data in [
        ("utf-16", "TOK\n".encode("utf-16")),
        ("utf-8-sig", b"\xef\xbb\xbfTOK\n"),
        ("utf-8", b"TOK\r\n"),
    ]:
        f = tmp_path / enc
        f.write_bytes(data)
        assert read_token_file(f) == "TOK"

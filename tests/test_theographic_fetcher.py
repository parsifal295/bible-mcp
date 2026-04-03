import hashlib
import json
from pathlib import Path
from urllib.error import URLError

import pytest

from bible_mcp.config import TheographicConfig
from bible_mcp.vendor.theographic_fetcher import (
    REQUIRED_FILENAMES,
    fetch_theographic_snapshot,
)


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_fetch_theographic_snapshot_writes_raw_files_and_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = "example/theographic"
    ref = "test-ref"
    resolved_commit = "a" * 40
    raw_payloads = {
        "people.json": b'{"people": [{"id": "abraham"}]}',
        "places.json": b'{"places": [{"id": "jerusalem"}]}',
        "events.json": b'{"events": [{"id": "exodus"}]}',
        "verses.json": b'{"verses": [{"id": "genesis-1-1"}]}',
    }

    def fake_urlopen(request):
        url = request.full_url if hasattr(request, "full_url") else request
        if url == f"https://api.github.com/repos/{repo}/commits/{ref}":
            payload = json.dumps({"sha": resolved_commit}).encode("utf-8")
            return _FakeResponse(payload)
        for filename, body in raw_payloads.items():
            expected = (
                f"https://raw.githubusercontent.com/{repo}/{resolved_commit}/json/{filename}"
            )
            if url == expected:
                return _FakeResponse(body)
        raise AssertionError(f"unexpected URL requested: {url}")

    monkeypatch.setattr(
        "bible_mcp.vendor.theographic_fetcher.urllib.request.urlopen",
        fake_urlopen,
    )

    config = TheographicConfig(repo=repo, ref=ref, vendor_dir=tmp_path / "vendor")
    snapshot_dir = fetch_theographic_snapshot(config)

    assert snapshot_dir == config.vendor_dir / resolved_commit
    raw_dir = snapshot_dir / "raw"
    for filename in REQUIRED_FILENAMES:
        payload = raw_payloads[filename]
        path = raw_dir / filename
        assert path.exists()
        assert path.read_bytes() == payload

    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_repo"] == repo
    assert manifest["source_ref"] == ref
    assert manifest["resolved_commit"] == resolved_commit
    assert manifest["license"] == "CC BY-SA 4.0"
    assert "fetched_at" in manifest
    assert sorted(manifest["files"]) == sorted(REQUIRED_FILENAMES)
    for filename, payload in raw_payloads.items():
        assert manifest["files"][filename]["sha256"] == hashlib.sha256(payload).hexdigest()


def test_fetch_theographic_snapshot_cleans_staging_dir_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = "example/theographic"
    ref = "test-ref"
    resolved_commit = "b" * 40
    existing_dir = tmp_path / "vendor" / resolved_commit
    (existing_dir / "raw").mkdir(parents=True)
    (existing_dir / "raw" / "people.json").write_text("{}", encoding="utf-8")
    (existing_dir / "manifest.json").write_text("{}", encoding="utf-8")

    def fake_urlopen(request):
        url = request.full_url if hasattr(request, "full_url") else request
        if url == f"https://api.github.com/repos/{repo}/commits/{ref}":
            payload = json.dumps({"sha": resolved_commit}).encode("utf-8")
            return _FakeResponse(payload)
        if url.endswith("/json/people.json"):
            return _FakeResponse(b'{"people": []}')
        raise URLError("simulated fetch error")

    monkeypatch.setattr(
        "bible_mcp.vendor.theographic_fetcher.urllib.request.urlopen",
        fake_urlopen,
    )
    config = TheographicConfig(repo=repo, ref=ref, vendor_dir=tmp_path / "vendor")

    with pytest.raises(RuntimeError, match="Failed to fetch Theographic snapshot"):
        fetch_theographic_snapshot(config)

    assert existing_dir.exists()
    staging_dirs = [
        path for path in config.vendor_dir.iterdir() if path.is_dir() and ".staging-" in path.name
    ]
    assert staging_dirs == []

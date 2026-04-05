import hashlib
import json
import shutil
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from bible_mcp.config import TheographicConfig

REQUIRED_FILENAMES = (
    "people.json",
    "places.json",
    "events.json",
    "verses.json",
)
THEOGRAPHIC_LICENSE = "CC BY-SA 4.0"
GITHUB_API_BASE = "https://api.github.com"
RAW_GITHUB_BASE = "https://raw.githubusercontent.com"
_REQUEST_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "bible-mcp-theographic-fetcher",
}


def fetch_theographic_snapshot(
    config: TheographicConfig,
    ref: str | None = None,
) -> Path:
    requested_ref = ref or config.ref
    resolved_commit = _resolve_commit(config.repo, requested_ref)
    snapshot_dir = config.vendor_dir / resolved_commit
    staging_dir = config.vendor_dir / f".staging-{resolved_commit}-{uuid4().hex}"
    config.vendor_dir.mkdir(parents=True, exist_ok=True)

    try:
        raw_dir = staging_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        file_entries: dict[str, dict[str, str | int]] = {}
        for filename in REQUIRED_FILENAMES:
            source_url = f"{RAW_GITHUB_BASE}/{config.repo}/{resolved_commit}/json/{filename}"
            payload = _download_raw_file(config.repo, resolved_commit, filename)
            target_file = raw_dir / filename
            target_file.write_bytes(payload)
            file_entries[filename] = {
                "url": source_url,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }

        manifest = {
            "source_repo": config.repo,
            "source_ref": requested_ref,
            "resolved_commit": resolved_commit,
            "license": THEOGRAPHIC_LICENSE,
            "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "files": file_entries,
        }
        (staging_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        _replace_snapshot(snapshot_dir, staging_dir)
        return snapshot_dir
    except Exception as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise RuntimeError("Failed to fetch Theographic snapshot") from exc


def resolve_theographic_snapshot_dir(
    config: TheographicConfig,
    ref: str | None = None,
) -> Path:
    requested_ref = ref or config.ref
    candidate = config.vendor_dir / requested_ref
    if candidate.is_dir():
        return candidate

    if not config.vendor_dir.is_dir():
        raise FileNotFoundError(
            "No Theographic snapshot found. Run fetch-theographic first."
        )

    matched: list[tuple[Path, str | None]] = []
    for snapshot_dir in config.vendor_dir.iterdir():
        if not snapshot_dir.is_dir() or snapshot_dir.name.startswith("."):
            continue
        manifest_path = snapshot_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        source_ref = manifest.get("source_ref")
        resolved_commit = manifest.get("resolved_commit")
        if source_ref == requested_ref or resolved_commit == requested_ref:
            fetched_at = manifest.get("fetched_at")
            matched.append((snapshot_dir, fetched_at if isinstance(fetched_at, str) else None))

    if not matched:
        raise FileNotFoundError(
            "No Theographic snapshot found. Run fetch-theographic first."
        )
    if len(matched) == 1:
        return matched[0][0]

    dated_matches: list[tuple[Path, datetime]] = []
    for snapshot_dir, fetched_at in matched:
        if not fetched_at:
            raise RuntimeError(
                f"Multiple Theographic snapshots match ref '{requested_ref}'. "
                "Run fetch-theographic or remove stale snapshots."
            )
        try:
            parsed = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise RuntimeError(
                f"Multiple Theographic snapshots match ref '{requested_ref}' but fetched_at is invalid."
            ) from exc
        dated_matches.append((snapshot_dir, parsed))

    dated_matches.sort(key=lambda item: item[1], reverse=True)
    return dated_matches[0][0]


def _resolve_commit(repo: str, ref: str) -> str:
    encoded_ref = urllib.parse.quote(ref, safe="")
    url = f"{GITHUB_API_BASE}/repos/{repo}/commits/{encoded_ref}"
    payload = _read_json(url)
    commit = payload.get("sha")
    if not isinstance(commit, str) or not commit:
        raise RuntimeError("GitHub commits API response missing sha")
    return commit


def _download_raw_file(repo: str, commit: str, filename: str) -> bytes:
    url = f"{RAW_GITHUB_BASE}/{repo}/{commit}/json/{filename}"
    request = urllib.request.Request(url, headers=_REQUEST_HEADERS)
    with urllib.request.urlopen(request) as response:
        return response.read()


def _read_json(url: str) -> dict:
    request = urllib.request.Request(url, headers=_REQUEST_HEADERS)
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def _replace_snapshot(snapshot_dir: Path, staging_dir: Path) -> None:
    if not snapshot_dir.exists():
        staging_dir.rename(snapshot_dir)
        return

    backup_dir = snapshot_dir.parent / f".backup-{snapshot_dir.name}-{uuid4().hex}"
    snapshot_dir.rename(backup_dir)
    try:
        staging_dir.rename(snapshot_dir)
    except Exception:
        if backup_dir.exists():
            backup_dir.rename(snapshot_dir)
        raise
    else:
        shutil.rmtree(backup_dir, ignore_errors=True)

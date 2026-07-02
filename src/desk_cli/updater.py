#!/usr/bin/env python3
"""Version-aware self-update + passive update notice for the ``desk`` CLI.

No git involved. The installed version is the bundled ``__version__``; the latest
version comes from the **public** GitHub repo (the published Release, else the
highest ``vX.Y.Z`` tag) via the REST API. Updating downloads that tag's source
archive over HTTPS, extracts it, and copies it over the install directory.

Two entry points:
  * ``run(...)``          — the ``desk update`` / ``--check`` command: compare and
    (unless check-only) download + apply the latest release.
  * ``maybe_notify(...)`` — called after every other command: if a newer version
    exists, print a one-line upgrade hint. Cached to one network check per day,
    short-timeout, and wrapped so it can NEVER break a command.

Stdlib only (``urllib`` + ``tarfile``); every network/IO failure degrades to a
clear message or silence, never a traceback.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_SLUG = "rundesk-ai/desk-cli"
RELEASES_LATEST_URL = f"https://api.github.com/repos/{REPO_SLUG}/releases/latest"
TAGS_URL = f"https://api.github.com/repos/{REPO_SLUG}/tags"
ARCHIVE_URL = "https://github.com/{slug}/archive/refs/tags/{tag}.tar.gz"
HTTP_TIMEOUT = 2         # version checks — the notice runs after the command, once/day
DOWNLOAD_TIMEOUT = 60    # the update archive download
USER_AGENT = "desk-cli-updater"
CHECK_INTERVAL_SECONDS = 24 * 60 * 60
_DISABLE_ENV = "DESK_NO_UPDATE_CHECK"

_VERSION_RE = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")


# ── Version parsing / comparison ───────────────────────────────────────────
def parse_version(value: str) -> tuple[int, int, int] | None:
    """Parse ``vX.Y.Z`` (or ``X.Y``/``X``) into a 3-int tuple; None if unparseable."""
    match = _VERSION_RE.match((value or "").strip())
    if not match:
        return None
    return tuple(int(part) if part else 0 for part in match.groups())  # type: ignore[return-value]


def is_newer(latest: str, local: str) -> bool:
    latest_v, local_v = parse_version(latest), parse_version(local)
    if latest_v is None or local_v is None:
        return False
    return latest_v > local_v


def _pretty(version: str) -> str:
    return "v" + (version or "").lstrip("v")


# ── Latest-version discovery (public GitHub API) ───────────────────────────
def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def _github_json(url: str):
    try:
        with urllib.request.urlopen(_request(url), timeout=HTTP_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError):
        return None


def _highest(names) -> str | None:
    best: tuple[int, int, int] | None = None
    best_name: str | None = None
    for name in names:
        version = parse_version(name)
        if version and (best is None or version > best):
            best, best_name = version, name
    return best_name


def _latest_from_releases() -> str | None:
    data = _github_json(RELEASES_LATEST_URL)
    tag = data.get("tag_name") if isinstance(data, dict) else None
    return tag or None


def _latest_from_tags() -> str | None:
    data = _github_json(TAGS_URL)
    if not isinstance(data, list):
        return None
    return _highest(item.get("name", "") for item in data if isinstance(item, dict))


def latest_version_online() -> str | None:
    """Latest version from the public GitHub repo: newest Release, else tag."""
    return _latest_from_releases() or _latest_from_tags()


# ── `desk update` ──────────────────────────────────────────────────────────
def run(repo_root: Path, current_version: str, check_only: bool = False) -> int:
    """Check for and (unless ``check_only``) apply an update by downloading the
    latest release archive. Returns a process exit code."""
    latest = latest_version_online()
    if latest is None:
        print("Could not determine the latest version (no published release yet, or no network).")
        return 1

    print(f"installed: {_pretty(current_version)}   latest: {_pretty(latest)}")
    if not is_newer(latest, current_version):
        print("Already up to date.")
        _write_cache(latest)
        return 0

    print(f"Update available: {_pretty(current_version)} → {_pretty(latest)}")
    if check_only:
        print("Run `desk update` to install it.")
        return 0

    if not os.access(repo_root, os.W_OK):
        print(f"Cannot update: {repo_root} is not writable.")
        return 1

    print(f"Downloading {_pretty(latest)} …")
    return _download_and_apply(repo_root, latest)


def _download_and_apply(repo_root: Path, tag: str) -> int:
    url = ARCHIVE_URL.format(slug=REPO_SLUG, tag=tag)
    try:
        with urllib.request.urlopen(_request(url), timeout=DOWNLOAD_TIMEOUT) as response:
            payload = response.read()
    except (urllib.error.URLError, OSError) as exc:
        print(f"Download failed: {exc}. Update manually from https://github.com/{REPO_SLUG}/releases")
        return 1

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            archive = tmp / "release.tar.gz"
            archive.write_bytes(payload)
            with tarfile.open(archive) as tar:
                _safe_extract(tar, tmp)
            roots = [p for p in tmp.iterdir() if p.is_dir()]
            if not roots:
                print("Downloaded archive was empty.")
                return 1
            _copy_over(roots[0], repo_root)
    except (tarfile.TarError, OSError) as exc:
        print(f"Update failed while unpacking: {exc}")
        return 1

    shim = repo_root / "desk"
    if shim.exists():
        try:
            shim.chmod(0o755)
        except OSError:
            pass
    _write_cache(tag)
    print(f"Updated to {_pretty(tag)}. Run `desk --version` to confirm.")
    return 0


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    """Extract, rejecting any member that would escape ``dest`` (path traversal)."""
    dest_resolved = dest.resolve()
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if target != dest_resolved and dest_resolved not in target.parents:
            raise tarfile.TarError(f"unsafe path in archive: {member.name}")
    tar.extractall(dest)


def _copy_over(src: Path, dst: Path) -> None:
    """Copy the extracted tree over the install dir, overwriting existing files."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


# ── Passive update notice (cached, failsafe) ───────────────────────────────
def _cache_path() -> Path:
    import profiles

    return profiles.config_dir() / "update-check.json"


def _read_cache() -> dict:
    try:
        return json.loads(_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_cache(latest: str | None) -> None:
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"latest": latest, "checked_at": int(time.time())}), encoding="utf-8")
    except OSError:
        pass


def _cached_or_refresh_latest() -> str | None:
    cache = _read_cache()
    age = time.time() - cache.get("checked_at", 0)
    if age < CHECK_INTERVAL_SECONDS:
        return cache.get("latest")  # fresh enough — no network (may be None)
    latest = latest_version_online()
    _write_cache(latest if latest else cache.get("latest"))  # stamp even on failure
    return latest if latest else cache.get("latest")


def maybe_notify(current_version: str, stream=None) -> None:
    """Print a one-line upgrade hint if a newer version exists. Cached to at most
    one network check per day, and wrapped so it can never raise."""
    import sys

    if os.environ.get(_DISABLE_ENV):
        return
    stream = stream if stream is not None else sys.stderr
    try:
        latest = _cached_or_refresh_latest()
        if latest and is_newer(latest, current_version):
            print(
                f"\nA new version of desk is available: {_pretty(current_version)} → {_pretty(latest)}."
                "\nRun `desk update` to upgrade.",
                file=stream,
            )
    except Exception:
        pass  # failsafe: a broken notifier must not break the CLI

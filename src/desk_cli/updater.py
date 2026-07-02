#!/usr/bin/env python3
"""Version-aware self-update + passive update notice for the ``desk`` CLI.

The installed version is the bundled ``__version__``; the latest version comes
from the **public** GitHub repo — the published Release, else the highest
``vX.Y.Z`` tag (via the GitHub API, and as a last resort ``git ls-remote``).

Two entry points:
  * ``run(...)``          — the explicit ``desk update`` / ``--check`` command:
    compare, and (unless check-only) fast-forward the git checkout to the latest
    tag, refusing on a dirty tree.
  * ``maybe_notify(...)`` — called after every other command: if a newer version
    exists, print a one-line upgrade hint. It is cached (at most one network
    check per day), short-timeout, and wrapped so it can NEVER break a command —
    the failsafe the CLI depends on.

Stdlib only (``urllib`` + git via ``subprocess``); every network/git failure
degrades to a clear message or silence, never a traceback.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_SLUG = "rundesk-ai/desk-cli"
RELEASES_LATEST_URL = f"https://api.github.com/repos/{REPO_SLUG}/releases/latest"
TAGS_URL = f"https://api.github.com/repos/{REPO_SLUG}/tags"
HTTP_TIMEOUT = 2  # short: the passive notice runs after the command, once/day
USER_AGENT = "desk-cli-updater"
CHECK_INTERVAL_SECONDS = 24 * 60 * 60  # passive notice checks GitHub at most once/day
_DISABLE_ENV = "DESK_NO_UPDATE_CHECK"  # set to any value to silence the passive notice

_VERSION_RE = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")


# ── Version parsing / comparison ───────────────────────────────────────────
def parse_version(value: str) -> tuple[int, int, int] | None:
    """Parse ``vX.Y.Z`` (or ``X.Y``/``X``) into a 3-int tuple; None if unparseable."""
    match = _VERSION_RE.match((value or "").strip())
    if not match:
        return None
    return tuple(int(part) if part else 0 for part in match.groups())  # type: ignore[return-value]


def is_newer(latest: str, local: str) -> bool:
    """True when ``latest`` is a strictly higher version than ``local``."""
    latest_v, local_v = parse_version(latest), parse_version(local)
    if latest_v is None or local_v is None:
        return False
    return latest_v > local_v


def _pretty(version: str) -> str:
    return "v" + (version or "").lstrip("v")


# ── GitHub / git version discovery ─────────────────────────────────────────
def _github_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError):
        return None


def _latest_from_releases() -> str | None:
    data = _github_json(RELEASES_LATEST_URL)
    tag = data.get("tag_name") if isinstance(data, dict) else None
    return tag or None


def _latest_from_github_tags() -> str | None:
    data = _github_json(TAGS_URL)
    if not isinstance(data, list):
        return None
    return _highest((item.get("name", "") for item in data if isinstance(item, dict)))


def _highest(names) -> str | None:
    best: tuple[int, int, int] | None = None
    best_name: str | None = None
    for name in names:
        version = parse_version(name)
        if version and (best is None or version > best):
            best, best_name = version, name
    return best_name


def _latest_from_git_tags(repo_root: Path) -> str | None:
    result = _git(repo_root, "ls-remote", "--tags", "origin", capture=True)
    if result is None:
        return None
    return _highest(line.rsplit("/", 1)[-1].replace("^{}", "") for line in result.splitlines())


def latest_version_online() -> str | None:
    """Latest version from the public GitHub repo — no local checkout needed."""
    return _latest_from_releases() or _latest_from_github_tags()


def latest_version(repo_root: Path) -> str | None:
    """Latest version for the ``update`` command, with a git fallback."""
    return latest_version_online() or _latest_from_git_tags(repo_root)


# ── git helpers ────────────────────────────────────────────────────────────
def _git(repo_root: Path, *args: str, capture: bool = False) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return completed.stdout if capture else ""


def _is_git_checkout(repo_root: Path) -> bool:
    return (repo_root / ".git").exists()


def _is_dirty(repo_root: Path) -> bool:
    status = _git(repo_root, "status", "--porcelain", capture=True)
    return bool(status and status.strip())


# ── `desk update` ──────────────────────────────────────────────────────────
def run(repo_root: Path, current_version: str, check_only: bool = False) -> int:
    """Check for and (unless ``check_only``) apply an update. Returns a process
    exit code: 0 = up-to-date or updated, non-zero = a problem the user should see."""
    if not _is_git_checkout(repo_root):
        print(f"desk is installed at {repo_root}, which is not a git checkout.")
        print("Update it however you installed it (e.g. re-run install.sh from a fresh clone).")
        return 1

    latest = latest_version(repo_root)
    if latest is None:
        print("Could not determine the latest version (no network / GitHub release, and no remote tags).")
        return 1

    print(f"installed: {_pretty(current_version)}   latest: {_pretty(latest)}")
    if not is_newer(latest, current_version):
        print("Already up to date.")
        _write_cache(latest)  # keep the passive-notice cache in sync
        return 0

    print(f"Update available: {_pretty(current_version)} → {_pretty(latest)}")
    if check_only:
        print("Run `desk update` to install it.")
        return 0

    if _is_dirty(repo_root):
        print(f"Refusing to update: {repo_root} has local changes.")
        print("Commit or discard them, then run `desk update` again.")
        return 1

    print(f"Updating {repo_root} …")
    if _git(repo_root, "fetch", "--tags", "--force", "origin") is None:
        print("git fetch failed. Update manually with `git pull` in the install directory.")
        return 1
    if _git(repo_root, "checkout", "--quiet", latest) is None:
        print(f"git checkout {latest} failed. Update manually in the install directory.")
        return 1

    shim = repo_root / "desk"  # the symlinked shim may lose +x across a checkout
    if shim.exists():
        shim.chmod(0o755)

    _write_cache(latest)
    print(f"Updated to {_pretty(latest)}. Run `desk --version` to confirm.")
    return 0


# ── Passive update notice (cached, failsafe) ───────────────────────────────
def _cache_path() -> Path:
    # Local import to avoid a hard import cycle at module load.
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
    # Always stamp checked_at (even on failure) so we don't hammer GitHub every run.
    _write_cache(latest if latest else cache.get("latest"))
    return latest if latest else cache.get("latest")


def maybe_notify(current_version: str, stream=None) -> None:
    """Print a one-line upgrade hint if a newer version exists. Cached to at most
    one network check per day, and wrapped so it can never raise — running it must
    never change the outcome of the command the user actually asked for."""
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

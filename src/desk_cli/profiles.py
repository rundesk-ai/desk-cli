#!/usr/bin/env python3
"""Local multi-profile credential store for the ``desk`` CLI.

A single shared ``.env`` binds one key to one desk. On a personal machine we
instead keep any number of named profiles — each a ``base_url`` + ``api_key`` —
in a ``chmod 600`` JSON file under the user's config dir, with one marked default.
This module owns that file and the rule for turning "which profile?" into concrete
credentials; ``cli.py`` builds a ``RundeskClient`` from what ``resolve_credentials``
returns.

Rundesk-injected named skill profiles are deliberately separate: an explicit
``--env-profile NAME`` reads only ``RUNDESK_API_KEY__NAME`` and the optional
matching URL, never a saved or unsuffixed fallback.

File: ``${XDG_CONFIG_HOME:-~/.config}/desk/config.json``
```json
{ "version": 1, "default": "work",
  "profiles": { "work": {"base_url": "https://rundesk.ai", "api_key": "..."} } }
```
Never printed in full — ``mask_key`` shows only the last four characters.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Reuse the REST client's typed error / exit-code model — no new error type.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from client import RundeskError  # noqa: E402

DEFAULT_BASE_URL = "https://rundesk.ai"
CONFIG_VERSION = 1

# A per-directory profile selector (like .nvmrc): a `.desk-profile` file whose
# `profile=<name>` line (a bare `<name>` also works) picks the profile for commands
# run in that directory or any subdirectory. Lets agents that share one environment
# but run in different directories each use their own profile without an env var.
LOCAL_PROFILE_FILENAME = ".desk-profile"
# Matches `profile=name` / `profile: name` (also DESK_PROFILE=…), case-insensitive.
_LOCAL_PROFILE_RE = re.compile(r"^(?:desk_)?profile\s*[:=]\s*(.+)$", re.IGNORECASE)
_ENV_PROFILE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class ConfigConflict(RundeskError):
    """The profile file changed after it was loaded; callers must retry."""

    def __init__(self) -> None:
        super().__init__("usage", "profile config changed concurrently; retry the command.")


class _Config(dict):
    """A config mapping carrying the exact bytes it was loaded from."""

    def __init__(self, *args: Any, revision: bytes | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.revision = revision


# ── File location ──────────────────────────────────────────────────────────
def config_dir() -> Path:
    """The desk config directory, honoring XDG_CONFIG_HOME (default ~/.config)."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base).expanduser() / "desk"


def config_path() -> Path:
    return config_dir() / "config.json"


# ── Load / save ────────────────────────────────────────────────────────────
def _empty_config() -> dict[str, Any]:
    return _Config(
        {"version": CONFIG_VERSION, "default": None, "profiles": {}},
        revision=None,
    )


def load_config() -> dict[str, Any]:
    """Read the config file, returning an empty skeleton when it is absent or
    unreadable. Always returns a dict with `default` and a `profiles` mapping."""
    path = config_path()
    if not path.exists():
        return _empty_config()
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise RundeskError("usage", f"config at {path} is not readable JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RundeskError("usage", f"config at {path} is malformed (expected an object).")
    loaded = _Config(data, revision=raw)
    loaded.setdefault("version", CONFIG_VERSION)
    loaded.setdefault("default", None)
    saved_profiles = loaded.get("profiles")
    loaded["profiles"] = saved_profiles if isinstance(saved_profiles, dict) else {}
    return loaded


def save_config(cfg: dict[str, Any]) -> None:
    """Write the config atomically with owner-only permissions (dir 0700,
    file 0600) so the API keys are never group/world readable."""
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    path = config_path()
    tmp = path.with_name(path.name + ".tmp")
    lock_path = path.with_name(path.name + ".lock")
    serialized = json.dumps(cfg, indent=2, sort_keys=True) + "\n"
    encoded = serialized.encode("utf-8")
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.fchmod(lock_fd, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        current = path.read_bytes() if path.exists() else None
        expected = getattr(cfg, "revision", current)
        if current != expected:
            raise ConfigConflict()

        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            # An old interrupted temp file could have broader permissions.
            # Tighten the descriptor before writing the first credential byte.
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as handle:
                fd = -1
                handle.write(encoded)
        finally:
            if fd >= 0:
                os.close(fd)
        os.replace(tmp, path)
        if isinstance(cfg, _Config):
            cfg.revision = encoded
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


# ── Mutations (operate on an in-memory cfg; caller saves) ──────────────────
def add_profile(cfg: dict[str, Any], name: str, base_url: str, api_key: str) -> None:
    cfg["profiles"][name] = {"base_url": base_url.rstrip("/"), "api_key": api_key}


def remove_profile(cfg: dict[str, Any], name: str) -> None:
    cfg["profiles"].pop(name, None)
    if cfg.get("default") == name:
        cfg["default"] = next(iter(sorted(cfg["profiles"])), None)


def set_default(cfg: dict[str, Any], name: str) -> None:
    cfg["default"] = name


# ── Display helper ─────────────────────────────────────────────────────────
def mask_key(key: str) -> str:
    """A safe-to-print rendering of an API key — only the last four chars."""
    if not key:
        return "(none)"
    if len(key) <= 4:
        return "•" * len(key)
    return "…" + key[-4:]


def dir_profile(start: str | os.PathLike[str] | None = None) -> str | None:
    """The profile named by a ``.desk-profile`` file in ``start`` (default cwd) or
    the nearest ancestor. The file's first meaningful line may be ``profile=<name>``
    (the documented form) or a bare ``<name>``; comments (``#``) and blanks are
    skipped. Returns the profile name, or None if no file/value is found."""
    try:
        path = Path(start).resolve() if start else Path.cwd()
    except OSError:
        return None
    for directory in [path, *path.parents]:
        candidate = directory / LOCAL_PROFILE_FILENAME
        if candidate.is_file():
            try:
                lines = candidate.read_text(encoding="utf-8").splitlines()
            except OSError:
                return None
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                match = _LOCAL_PROFILE_RE.match(line)
                value = (match.group(1) if match else line).strip().strip('"').strip("'")
                if value:
                    return value
            return None  # present but empty → no selection
    return None


# ── The core rule: which credentials for this invocation? ──────────────────
def resolve_credentials(
    name: str | None = None,
    env_profile: str | None = None,
) -> tuple[str, str]:
    """Resolve ``(base_url, api_key)`` for this command, in precedence order:

    1. an explicit ``--profile NAME`` (error if unknown),
    2. the ``DESK_PROFILE`` env var naming a saved profile,
    3. a ``.desk-profile`` file in the current directory or an ancestor — lets
       agents that share one environment but run in different directories each
       pick their own profile automatically,
    4. ``RUNDESK_API_KEY`` (+ optional ``RUNDESK_BASE_URL``) in the process env —
       the CI / one-off escape hatch (an explicitly-set env var always wins),
    5. the saved ``default`` profile.

    A distinct ``env_profile`` selects Rundesk-injected suffixed variables:
    ``RUNDESK_API_KEY__NAME`` and optional ``RUNDESK_BASE_URL__NAME``. It never
    consults the saved/default resolution chain or unsuffixed variables.

    Raises ``RundeskError('no_key', …)`` pointing at ``desk profile add`` when
    nothing resolves, so a fresh machine gets a friendly message, not a traceback.
    """
    if name and env_profile:
        raise RundeskError("usage", "--profile and --env-profile cannot be combined.")

    if env_profile is not None:
        suffix = env_profile.strip().upper()
        if not _ENV_PROFILE_RE.fullmatch(suffix):
            raise RundeskError(
                "usage",
                "--env-profile must start with a letter and contain only letters, digits, or underscores.",
            )
        key_name = f"RUNDESK_API_KEY__{suffix}"
        url_name = f"RUNDESK_BASE_URL__{suffix}"
        api_key = os.environ.get(key_name, "")
        if not api_key:
            raise RundeskError(
                "no_key",
                f"Named environment profile {env_profile.strip()!r} has no {key_name}.",
            )
        base_url = os.environ.get(url_name) or DEFAULT_BASE_URL
        return base_url.rstrip("/"), api_key

    cfg = load_config()
    profiles = cfg.get("profiles", {})

    def _lookup(profile_name: str, source: str) -> tuple[str, str]:
        prof = profiles.get(profile_name)
        if not prof:
            raise RundeskError("usage", f"{source} names {profile_name!r} but no such saved profile (see `desk profile list`).")
        return prof["base_url"], prof["api_key"]

    if name:
        return _lookup(name, "--profile")

    env_name = os.environ.get("DESK_PROFILE")
    if env_name:
        return _lookup(env_name, "DESK_PROFILE")

    local_name = dir_profile()
    if local_name:
        return _lookup(local_name, f"{LOCAL_PROFILE_FILENAME}")

    env_key = os.environ.get("RUNDESK_API_KEY")
    if env_key:
        return os.environ.get("RUNDESK_BASE_URL", DEFAULT_BASE_URL).rstrip("/"), env_key

    default = cfg.get("default")
    if default and default in profiles:
        prof = profiles[default]
        return prof["base_url"], prof["api_key"]

    raise RundeskError("no_key", "No Rundesk profile configured. Run `desk profile add` to create one.")

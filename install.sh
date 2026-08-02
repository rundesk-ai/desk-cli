#!/usr/bin/env bash
# Install (or uninstall) the `desk` CLI. Zero runtime dependencies, no git — desk
# runs on the system python3 (>=3.9) and the stdlib only.
#
# One-command install (downloads the latest release, no clone):
#   curl -fsSL https://github.com/rundesk-ai/desk-cli/releases/latest/download/install.sh | bash
#
# From a local checkout, `./install.sh` symlinks THAT checkout (for development).
#
# Uninstall:
#   curl -fsSL https://github.com/rundesk-ai/desk-cli/releases/latest/download/install.sh | bash -s -- --uninstall [--purge]
#   ./install.sh --uninstall [--purge]
#
# Env overrides: DESK_INSTALL_DIR (default ~/.desk), DESK_BIN_DIR, DESK_REPO_SLUG.
set -euo pipefail

REPO_SLUG="${DESK_REPO_SLUG:-rundesk-ai/desk-cli}"
INSTALL_DIR="${DESK_INSTALL_DIR:-$HOME/.desk}"

# Directory this script lives in — empty when piped from curl (read from stdin).
SCRIPT_DIR=""
_src="${BASH_SOURCE[0]:-}"
if [[ -n "$_src" && -f "$_src" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "$_src")" && pwd)"
fi

# True when this script sits inside a checkout (next to the shim + package).
is_local_checkout() {
  [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/desk" && -d "$SCRIPT_DIR/src/desk_cli" ]]
}

choose_bindir() {
  if [[ -n "${DESK_BIN_DIR:-}" ]]; then
    echo "$DESK_BIN_DIR"
  elif [[ -d /usr/local/bin && -w /usr/local/bin ]]; then
    echo /usr/local/bin
  else
    echo "$HOME/.local/bin"
  fi
}

die() { echo "error: $*" >&2; exit 1; }

# ── Uninstall ──────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--uninstall" ]]; then
  removed=0
  for dir in /usr/local/bin "$HOME/.local/bin" "${DESK_BIN_DIR:-}"; do
    [[ -z "$dir" ]] && continue
    link="$dir/desk"
    if [[ -L "$link" ]]; then
      target="$(readlink "$link")"
      if [[ "$target" == "$INSTALL_DIR/desk" || ( -n "$SCRIPT_DIR" && "$target" == "$SCRIPT_DIR/desk" ) ]]; then
        rm -f "$link"; echo "removed $link"; removed=1
      fi
    fi
  done
  [[ "$removed" == 0 ]] && echo "No desk symlink pointing at a desk install was found on PATH."

  config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/desk"
  if [[ "${2:-}" == "--purge" && -d "$config_dir" ]]; then
    rm -rf "$config_dir"; echo "purged saved profiles at $config_dir"
  elif [[ -d "$config_dir" ]]; then
    echo "Saved profiles in $config_dir were left untouched (add --purge to delete them)."
  fi

  # Remove the managed install dir we created (never a local dev checkout).
  if [[ -d "$INSTALL_DIR" ]] && ! is_local_checkout; then
    rm -rf "$INSTALL_DIR"; echo "removed $INSTALL_DIR"
  fi
  echo "Uninstalled."
  exit 0
fi

# ── Require python3 >= 3.9 (desk's only runtime need) ──────────────────────
command -v python3 >/dev/null 2>&1 || die "python3 not found. Install Python 3.9+ (macOS ships it, or Xcode CLT/Homebrew)."
python3 -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 9) else 1)' || die "python3 is older than 3.9. Please upgrade."

# ── Resolve the code to install: local checkout, else download latest release ─
if is_local_checkout; then
  REPO_ROOT="$SCRIPT_DIR"
else
  command -v curl >/dev/null 2>&1 || die "curl not found."
  command -v tar  >/dev/null 2>&1 || die "tar not found."

  latest_tag() {
    # Newest published release, else the highest tag. Robust to 404/empty.
    local tag
    tag="$(curl -fsSL "https://api.github.com/repos/$REPO_SLUG/releases/latest" 2>/dev/null \
           | python3 -c 'import sys,json
try: print((json.load(sys.stdin) or {}).get("tag_name") or "")
except Exception: print("")' 2>/dev/null || true)"
    if [[ -z "$tag" ]]; then
      tag="$(curl -fsSL "https://api.github.com/repos/$REPO_SLUG/tags" 2>/dev/null \
             | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); print(d[0]["name"] if d else "")
except Exception: print("")' 2>/dev/null || true)"
    fi
    echo "$tag"
  }

  TAG="$(latest_tag)"
  [[ -n "$TAG" ]] || die "no published release found for $REPO_SLUG."

  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  echo "Downloading desk $TAG …"
  curl -fsSL "https://github.com/$REPO_SLUG/archive/refs/tags/$TAG.tar.gz" -o "$tmp/desk.tar.gz" \
    || die "failed to download release $TAG."
  tar -xzf "$tmp/desk.tar.gz" -C "$tmp"
  extracted="$(find "$tmp" -maxdepth 1 -type d -name 'desk-cli-*' | head -1)"
  [[ -n "$extracted" ]] || die "unexpected archive layout."
  rm -rf "$INSTALL_DIR"
  mkdir -p "$(dirname "$INSTALL_DIR")"
  mv "$extracted" "$INSTALL_DIR"
  REPO_ROOT="$INSTALL_DIR"
fi

# ── Symlink the shim onto PATH ─────────────────────────────────────────────
SHIM="$REPO_ROOT/desk"
BINDIR="$(choose_bindir)"
mkdir -p "$BINDIR"
chmod +x "$SHIM"
ln -sf "$SHIM" "$BINDIR/desk"
echo "Installed: $BINDIR/desk -> $SHIM"
echo "Version:   $("$SHIM" --version)"

if ! command -v desk >/dev/null 2>&1; then
  echo
  echo "note: $BINDIR is not on your PATH. Add this to your shell profile:"
  echo "    export PATH=\"$BINDIR:\$PATH\""
fi

echo
echo "Next: run  desk profile add  to store your Rundesk API key, then  desk show"

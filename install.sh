#!/usr/bin/env bash
# Install (or uninstall) the `desk` command by symlinking this repo's `desk` shim
# onto your PATH. Zero dependencies — desk runs on the system python3 (>=3.9) and
# the stdlib only. Credentials live in ~/.config/desk/ (see `desk profile add`).
#
# Usage:
#   ./install.sh              # install / re-point the symlink
#   ./install.sh --uninstall  # remove the symlink (leaves your profiles intact)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
SHIM="$REPO_ROOT/desk"

# Pick a bin dir already meant for user commands: prefer /usr/local/bin when
# writable, else ~/.local/bin (created + PATH-hinted if needed).
choose_bindir() {
  if [[ -d /usr/local/bin && -w /usr/local/bin ]]; then
    echo /usr/local/bin
  else
    echo "$HOME/.local/bin"
  fi
}

BINDIR="$(choose_bindir)"
TARGET="$BINDIR/desk"

if [[ "${1:-}" == "--uninstall" ]]; then
  # Remove any desk symlink that points back into this repo, wherever it lives.
  found=0
  for dir in /usr/local/bin "$HOME/.local/bin"; do
    link="$dir/desk"
    if [[ -L "$link" && "$(readlink "$link")" == "$SHIM" ]]; then
      rm -f "$link"
      echo "removed $link"
      found=1
    fi
  done
  [[ "$found" == 0 ]] && echo "No desk symlink pointing at this checkout was found on PATH."

  config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/desk"
  if [[ "${2:-}" == "--purge" ]]; then
    if [[ -d "$config_dir" ]]; then
      rm -rf "$config_dir"
      echo "purged saved profiles at $config_dir"
    fi
  else
    echo "Your profiles in $config_dir were left untouched (add --purge to delete them)."
  fi
  echo
  echo "The desk files remain at $REPO_ROOT. To remove them completely, run:"
  echo "    rm -rf \"$REPO_ROOT\""
  exit 0
fi

# Require python3 >= 3.9.
if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 not found. Install Python 3.9+ (macOS ships it, or use Xcode CLT/Homebrew)." >&2
  exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 9) else 1)'; then
  echo "error: python3 is older than 3.9. Please upgrade." >&2
  exit 1
fi

chmod +x "$SHIM"
mkdir -p "$BINDIR"
ln -sf "$SHIM" "$TARGET"
echo "Installed: $TARGET -> $SHIM"
echo "Version:   $("$SHIM" --version)"

if ! command -v desk >/dev/null 2>&1; then
  echo
  echo "note: $BINDIR is not on your PATH. Add this to your shell profile:"
  echo "    export PATH=\"$BINDIR:\$PATH\""
fi

echo
echo "Next: run  desk profile add  to store your Rundesk API key, then  desk whoami"

# AGENTS

Rules for every AI coding agent working in this repository. These rules are law; where they conflict with your general habits, this file wins.

This is a **distributed command-line tool**. It is installed onto strangers' machines via `curl | bash`, holds their API credentials, and is invoked by scripts and agents that parse its output. The zero-dependency promise, the command surface, and the stored file formats are all contracts — every change here lands on machines you will never see.

---

## Before You Work

1. Read [`BRIEF.md`](./.ai/BRIEF.md) (scope), [`CODEMAP.md`](./.ai/CODEMAP.md) (structure), and [`MEMORY.md`](./.ai/MEMORY.md) (lessons) before your first edit.
2. Read every file before editing it.
3. Search the codebase before writing new logic. If it exists — reuse, extend, or refactor. Never duplicate.
4. When the user raises a concern, investigate before contradicting. Contradict only with evidence from the codebase.

## Hard Gates — Require Explicit User Approval

- **Command surface & output contracts.** Renaming or removing a command or flag, changing the shape of default text output, or changing what `--json` emits breaks every script and agent that parses it. Never do it without approval.
- **Stored formats.** The `config.json` schema, the `.desk-profile` file format, and the install layout under `~/.desk` already exist on users' machines. Any change to what is written, where, or in what shape must be confirmed before proceeding.
- **Dependencies & the Python floor.** The tool runs on the system `python3` (3.9+) and the standard library — that is the product promise. Adding any dependency, vendoring any library, or raising the version floor requires approval. No exceptions.
- **Installer & updater.** `install.sh` and the `desk update` path run unattended on user machines over the network. Do not change either without approval.
- **Deletions.** Do not delete files or directories outside the immediate scope of the task without approval.
- **This file.** Never modify `AGENTS.md` without approval. If a rule seems wrong or missing, raise it.

## Never

- Never commit credentials, real API keys, or real account data — not in code, tests, fixtures, help text, or docs. This repository is public; committed examples use synthetic data only.
- Never import outside the standard library. When your instincts reach for `requests`, `httpx`, `click`, `typer`, `rich`, or `pydantic` — stop; the stdlib equivalent is the answer here, always.
- Never print an API key in full — not in output, errors, prompts, or `--json`. Masking is a security invariant, not a display preference.
- Never call the real Rundesk API from an automated test. Tests run offline against the fake transport, nothing else.
- Never leave `breakpoint()`, `pdb`, print-debugging, or commented-out code in completed work.
- Never write outside the sanctioned paths: the config store (`${XDG_CONFIG_HOME:-~/.config}/desk/`), the install directory (`~/.desk`), and an explicitly requested `.desk-profile` in the working directory. The config file is written `chmod 600` — never weaken it.

## Documentation Duties

This repository has two documentation surfaces with different audiences. Both are your responsibility, not the user's.

**Runtime docs (`.ai/`, agent-facing):**

- Restructured directories or moved files → update `CODEMAP.md` in the same task.
- Learned something that would have saved you time (a trap, a non-obvious constraint, a tooling quirk) → append it to `MEMORY.md`.
- Do not add rationale, maintainer commentary, or history to these files. They address the next agent doing work, nothing else.

**Consumer docs (`README.md` + `desk help`):**

- Help text in the code is the source of truth for command usage; the README summarizes the surface and owns install, profiles, and update.
- Added, renamed, or removed a command or flag → update its help text and the README command listing in the same task. Every command in the README exists; every command appears in `desk help`.
- Changed install, update, profile, or resolution behavior → the README section that documents it changes in the same task.

---

## Architecture

Three modules, one direction. A request travels down, never sideways or up:

```
cli.py       entry point — profiles, update, help, the desk whoami / desk inbox surface
   ↓
rundesk.py   full-API command tree — parse args, call the client, render output
   ↓
client.py    REST client — auth, transport, request/response
```

- **`client.py` knows nothing above it.** No commands, no profiles, no rendering, no `sys.exit`. It takes credentials, speaks HTTP, and returns parsed responses or raises.
- **Commands are thin.** A command in `rundesk.py` parses its arguments, makes client calls, and renders the result. HTTP details never appear in command code, and rendering never appears in the client.
- **The client's request path is the test seam.** All HTTP funnels through the client's single `request`/`_send` chokepoint (one `urllib.request.urlopen` call) — that is what `tests/test_cli.py` monkeypatches to walk every command offline. Never bypass it with a direct `urllib` call in command code.
- **Credential resolution has one home.** The profile store and the five-step resolution order live in `profiles.py` (`resolve_credentials`); `cli.py` calls it to build the client, and no command module re-implements it. The resolution order documented in the README is a contract — never add a source or reorder it.

## CLI Conventions

- **stdout is payload, stderr is diagnostics.** Scripts pipe stdout; anything that isn't the answer goes to stderr. Exit `0` on success, non-zero on any failure.
- **Expected failures get one actionable line.** Auth rejection, network errors, missing arguments, and API 4xx are predictable — they produce a single stderr message that tells the user what to do next, and never a traceback.

```python
# ✅ Expected failure — actionable, on stderr, non-zero exit
except AuthError:
    print("desk: API key rejected — run `desk profile add` to update it", file=sys.stderr)
    return 1
```

```python
# ❌ Diagnostics on stdout, generic message, no exit code
except Exception as e:
    print(f"Something went wrong: {e}")   # pollutes piped output; caller sees success
```

- **Default read output is compact, stable text.** One entity per line for lists, only the fields needed to decide the next action, stable column order. No banners, no boilerplate repeated per row.
- **`--json` is pure.** It emits the raw API payload and nothing else on stdout — no headers, no labels, no reshaping. It is the debugging and scripting escape hatch, not a pretty-printer.
- **Destructive operations require `--confirm`.** Without it, the command refuses and says exactly what flag to add. Never make a destructive call on the user's behalf.
- **Key validation is an invariant.** A profile is saved only if its key authenticates. A bad key is an error, not a stored-but-broken profile.
- **Portability.** Resolve home via `Path.home()`/`expanduser` and honor `XDG_CONFIG_HOME`. No hardcoded users, homes, or absolute paths anywhere.

---

## Code Rules

- **The floor is Python 3.9.** No `match` statements, no 3.10+ syntax, no stdlib modules newer than 3.9 (`tomllib` is 3.11 — off limits). If you are unsure when a feature landed, check before using it.
- PEP 8, 4-space indentation. Type hints on every function signature.
- Expected failures raise dedicated exception types that the entry point converts into the one-line stderr messages above. Unexpected bugs may traceback — predictable failures never do.
- Functions stay short with early returns; no global mutable state; if a function needs something, it arrives as a parameter.
- The same parsing, rendering, or validation logic in 3+ commands gets consolidated. "Almost identical" code is a bug signal — inspect the difference.

## Testing

Tests are standard library only — `python3 tests/<file>.py`, no pytest, no fixtures framework, no network.

- `tests/test_profiles.py` — profile store, credential resolution, updater.
- `tests/test_cli.py` — walks every command against the fake transport.
- `tests/test_rundesk.py` — the REST client's request/response suite.

Every new or changed command is covered by the `test_cli.py` walk; every new or changed client method is covered in `test_rundesk.py`; profile, resolution, or updater changes land in `test_profiles.py`. All test data is synthetic.

## Release & Updater Compatibility

- Cut a release by bumping `__version__` in `src/desk_cli/__init__.py` and tagging `vX.Y.Z`. The two must always match.
- Existing installs upgrade via `desk update`, which downloads the release archive and replaces the install in place. **The old updater must always be able to install the new version** — never change the archive layout, entry-point location, or install paths in a way a previous release's `desk update` cannot survive.

---

## Definition of Done

A task is done when the change is verified against its stated requirement — never based on effort — and:

1. All three test suites pass: `python3 tests/test_profiles.py && python3 tests/test_cli.py && python3 tests/test_rundesk.py`.
2. Documentation reflects the change, per Documentation Duties.
3. Every rule in this file was upheld. This file is the checklist — re-read it, do not restate it.

**When creating task lists or plans, the final step is always:** _"Re-read `AGENTS.md` and verify Definition of Done."_

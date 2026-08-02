# Codemap - desk-cli

Structural inventory of the `desk` CLI. A Python stdlib-only package: a thin executable shim, a five-module package under `src/desk_cli/`, three offline test suites, and an installer. Request flow is one direction: `cli.py` → `rundesk.py` → `client.py`.

## Entry Points

- `desk` — executable shim the installer symlinks onto PATH. Resolves its real location through the symlink, puts `src/desk_cli/` on `sys.path`, hands off to `cli.main`. Owns no logic.
- `src/desk_cli/cli.py` (`main`) — the real `desk` surface: wraps the full-API parser, adds profiles/update/uninstall/help and the desk-bound `show`/`inbox`/`mentions` commands, resolves credentials, dispatches.
- `src/desk_cli/rundesk.py` (`main`) — standalone debug CLI over the client (single-`.env` model, no profiles). Reused by `cli.py` for its parser, `--confirm` gating, and error→exit-code contract.
- `install.sh` — install/uninstall. Local checkout → symlinks it; piped from curl → downloads the latest GitHub release, unpacks to `~/.desk`, symlinks the shim.

## Package (`src/desk_cli/` — 5 modules)

| Module | Purpose |
|---|---|
| `__init__.py` | Package doc + `__version__` — single source of truth for `desk --version` and release tagging. |
| `cli.py` | Installable command surface: profile store commands, update/uninstall/help, `show`/`inbox`/`mentions`, credential resolution + dispatch, passive update notice. |
| `rundesk.py` | Full-API command tree — one `argparse` group per resource; parse args → call client → render. |
| `client.py` | Importable bearer REST client — auth, transport, request/response, typed errors. Knows nothing above it. |
| `profiles.py` | Local multi-profile credential store + the five-step resolution order. |
| `updater.py` | Version-aware self-update and cached, failsafe update notice (no git). |

## REST Client (`client.py`)

- `RundeskClient` — bearer client; 64 public methods (test gate asserts ≥60) covering account/changelog, the desk read surface (`/desk`, `/desk/inbox`, `/desk/mentions`), projects, pages (+search), tasks (+deadline/recurring/move/comments), weeks, assets (get/search/list/upload/rename/delete), owner desk management. Constructed with explicit `base_url`/`api_key` by `cli.py`, or resolves from env/`.env` when built bare.
- `Paths` — every REST path relative to `/api/v1`, the single place paths are defined (42 members). Nothing else hardcodes a path.
- `RundeskError(kind, message)` — typed failure; `.exit_code` maps `kind` to a stable process code via `KIND_EXIT`. `STATUS_KIND` maps HTTP status → kind.
- Exit codes: `0` ok · `2` usage/no_key/pending · `3` 401 · `4` 403 · `5` 404 · `6` 422 · `7` network · `1` unknown.
- Test seam: all HTTP funnels through `request`/`_send` (one `urllib.request.urlopen`); `_post_multipart` shares `_send`. `_safe_extract`-style path checks are in the updater, not here.

## Command Tree (`rundesk.py`)

- Top-level groups: `account`, `changelog`, `projects`, `page`, `tasks`, `week`, `weeks`, `asset`, `desks`. Built in `build_parser`; each `cmd_*` handler renders. There is no desk-bound group here — that surface lives in `cli.py`.
- `_emit` — prints text as-is, or pretty JSON for non-str payloads / `--json`.
- `_CONFIRM_GATED` — the 8 `(command, action)` pairs that hard-delete and require `--confirm` (projects/page/tasks/desks delete, tasks comment-delete, asset delete-task/-project/-page).
- `cli.py` extends this tree with the desk-bound surface — `show` (`GET /desk`), `inbox` (`GET /desk/inbox`), `mentions` (`GET /desk/mentions`), plus `whoami` as a hidden alias of `show` — and hides `--env-file`.

## Credentials & Profiles (`profiles.py`)

- Store: `${XDG_CONFIG_HOME:-~/.config}/desk/config.json`, written atomically (dir `0700`, file `0600`), `version`/`default`/`profiles` schema.
- `resolve_credentials(name)` — five-step order: `--profile` → `DESK_PROFILE` → `.desk-profile` file (cwd or ancestor) → `RUNDESK_API_KEY`(+`RUNDESK_BASE_URL`) → saved default. Raises `no_key` pointing at `desk profile add` when nothing resolves.
- `dir_profile` — reads `.desk-profile` (a `.nvmrc`-style per-directory selector). `mask_key` — renders only the last four chars.

## Updater (`updater.py`)

- `run` — `desk update`/`--check`: latest version from GitHub Releases (else highest tag), download source archive, `_safe_extract` (rejects path traversal), copy over the install dir.
- `maybe_notify` — one-line upgrade hint after other commands; cached to one network check/day (`update-check.json` in the config dir), 2s timeout, wrapped so it can never break the CLI. Disabled by `DESK_NO_UPDATE_CHECK`.

## Tests (`tests/` — 3, stdlib `unittest`, offline)

- `test_cli.py` — auto-discovers every leaf command and walks it through `cli.main()` against a monkeypatched `urllib.request.urlopen`; asserts exit 0 + credentialed request (36 tests, 65 endpoints). Gate: every public client method is referenced from the command tree — the gate greps BOTH `rundesk.py` and `cli.py`, since the desk-bound surface lives in `cli.py`.
- `test_rundesk.py` — the REST client's request/response suite (122 tests).
- `test_profiles.py` — profile store, credential resolution, updater (38 tests).

## CI / Release (`.github/workflows/`)

- `build.yml` — CI: runs the three suites (README build badge).
- `release.yml` — cuts a release; `desk update` and `install.sh` consume its archive. Release = bump `__version__` + tag `vX.Y.Z` (the two must match).

## Consumer Docs

- `README.md` — install, profiles, resolution order, update, uninstall; summarizes the command surface. `desk help` (code help text) is the source of truth for command usage.

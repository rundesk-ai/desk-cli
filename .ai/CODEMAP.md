# Codemap - desk-cli

Structural inventory of the `desk` CLI. A Python stdlib-only package: a thin executable shim, a five-module package under `src/desk_cli/`, three offline test suites, an installer, and a Rundesk skill catalog. Request flow is one direction: `cli.py` → `rundesk.py` → `client.py`.

## Entry Points

- `desk` — executable shim the installer symlinks onto PATH. Resolves its real location through the symlink, puts `src/desk_cli/` on `sys.path`, hands off to `cli.main`. Owns no logic.
- `src/desk_cli/cli.py` (`main`) — the real `desk` surface: wraps the full-API parser, adds profiles/update/uninstall/help and the desk-bound `show`/`inbox`/`mentions` commands, resolves credentials, dispatches.
- `src/desk_cli/rundesk.py` (`main`) — standalone debug CLI over the client (single-`.env` model, no profiles). Reused by `cli.py` for its parser, `--confirm` gating, and error→exit-code contract.
- `install.sh` — install/uninstall. Local checkout → symlinks it; piped from curl → downloads the latest GitHub release, unpacks to `~/.desk`, symlinks the shim.

## Package (`src/desk_cli/` — 6 modules)

| Module | Purpose |
|---|---|
| `__init__.py` | Package doc + `__version__` — single source of truth for `desk --version` and release tagging. |
| `cli.py` | Installable command surface: profile store commands, update/uninstall/help, `show`/`inbox`/`mentions`, credential resolution + dispatch, passive update notice. |
| `rundesk.py` | Full-API command tree — one `argparse` group per resource; parse args → call client → render. |
| `client.py` | Importable bearer REST client — auth, transport, request/response, typed errors. Knows nothing above it. |
| `profiles.py` | Local multi-profile credential store + the five-step resolution order. |
| `updater.py` | Version-aware self-update and cached, failsafe update notice (no git). |

## REST Client (`client.py`)

- `RundeskClient` — bearer client; 76 command-facing methods (test gate asserts ≥60) covering account/changelog, desk and human mention inboxes, projects, pages (+search/grep/hierarchical reorder), tasks (+deadline/recurring/move/comments), weeks, unified and parent-scoped assets (get/search/list/update/upload/rename/delete), and owner desk management. Constructed with explicit `base_url`/`api_key` by `cli.py`, or resolves from env/`.env` when built bare.
- `Paths` — every REST path relative to `/api/v1`, the single place paths are defined (50 members). Nothing else hardcodes a path.
- `RundeskError(kind, message)` — typed failure; `.exit_code` maps `kind` to a stable process code via `KIND_EXIT`. `STATUS_KIND` maps HTTP status → kind.
- Exit codes: `0` ok · `2` usage/no_key/pending · `3` 401 · `4` 403 · `5` 404 · `6` 422 · `7` network · `1` unknown.
- Test seam: all HTTP funnels through `request`/`_send` (one `urllib.request.urlopen`); `_post_multipart` shares `_send`. `_safe_extract`-style path checks are in the updater, not here.

## Command Tree (`rundesk.py`)

- Top-level groups: `account`, `changelog`, `user-mentions`, `projects`, `page`, `tasks`, `week`, `weeks`, `asset`, `desks`. Built in `build_parser`; each `cmd_*` handler renders. There is no desk-bound group here — that surface lives in `cli.py`.
- `_emit` — prints text as-is, or pretty JSON for non-str payloads / `--json`.
- `_CONFIRM_GATED` — the 8 `(command, action)` pairs that hard-delete and require `--confirm` (projects/page/tasks/desks delete, tasks comment-delete, asset delete-task/-project/-page).
- `cli.py` extends this tree with the desk-bound surface — `show` (`GET /desk`), `inbox` (`GET /desk/inbox`), `mentions` (`GET /desk/mentions`), plus `whoami` as a hidden alias of `show` — and hides `--env-file`.

## Credentials & Profiles (`profiles.py`)

- Store: `${XDG_CONFIG_HOME:-~/.config}/desk/config.json`, written atomically (dir `0700`, file `0600`) with a `0600` lock file and snapshot compare-and-swap, `version`/`default`/`profiles` schema.
- `resolve_credentials(name, env_profile)` — `--env-profile` is a distinct isolated path over `RUNDESK_API_KEY__NAME` (+ optional matching URL), with no saved/unsuffixed fallback. Without it, the five-step order remains `--profile` → `DESK_PROFILE` → `.desk-profile` file (cwd or ancestor) → `RUNDESK_API_KEY`(+`RUNDESK_BASE_URL`) → saved default. Raises `no_key` when nothing resolves.
- `dir_profile` — reads `.desk-profile` (a `.nvmrc`-style per-directory selector). `mask_key` — renders only the last four chars.

## Updater (`updater.py`)

- `run` — `desk update`/`--check`: latest version from GitHub Releases (else highest tag), download source archive, `_safe_extract` (rejects path traversal), copy over the install dir.
- `maybe_notify` — one-line upgrade hint after other commands; cached to one network check/day (`update-check.json` in the config dir), 2s timeout, wrapped so it can never break the CLI. Disabled by `DESK_NO_UPDATE_CHECK`.

## Tests (`tests/` — 3, stdlib `unittest`, offline)

- `test_cli.py` — auto-discovers every leaf command and walks it through `cli.main()` against a monkeypatched `urllib.request.urlopen`; asserts exit 0 + credentialed request (74 endpoints). Gate: every public client method is referenced from the command tree — the gate greps BOTH `rundesk.py` and `cli.py`, since the desk-bound surface lives in `cli.py`. Also holds `CatalogManifestTests` (the skill catalog contract).
- `test_rundesk.py` — the REST client's request/response suite (166 tests).
- `test_profiles.py` — profile store, credential resolution, updater (44 tests).

## CI / Release (`.github/workflows/`)

- `build.yml` — CI: runs the three suites (README build badge).
- `release.yml` — cuts a release; `desk update` and `install.sh` consume its archive. Release = bump `__version__` + tag `vX.Y.Z` (the two must match).

## Skill Catalog (`manifest.json` + `skills/`)

- The repository doubles as a Rundesk skill catalog: `manifest.json` at the root declares `schema`/`name`/`version`/`description`; every `skills/*/SKILL.md` package is discovered. `rundesk skills install <repo-url>` reads it; rundesk fetches the **default branch** tarball, so `main` is the catalog — a GitHub release is needed for the `desk` binary, not for the skill.
- `skills/managing-your-desk/SKILL.md` — choose an exact injected profile, probe desk versus human mode, run the Desk-owned weekly commitment top-down, hydrate task/page/asset context, and guard writes. `rundesk.json` declares the API key; references hold conditional queue adoption/task-brief examples, identity, task, project/page/asset, and owner desk-management detail.
- `manifest.json`'s `version` tracks `__version__`; `CatalogManifestTests` validates discovered packages, frontmatter, and `rundesk.json`. Rundesk *silently* ignores a package a brain cannot index, so the contract is checked here instead.
- Nothing in `src/` reads these files. `install.sh` (`mv` of the extracted tree) and `updater._copy_over` (iterates `src.iterdir()`) carry new top-level entries automatically — no archive-layout change.

## Consumer Docs

- `README.md` — install, profiles, resolution order, update, uninstall, the skill catalog; summarizes the command surface. `desk help` (code help text) is the source of truth for command usage.

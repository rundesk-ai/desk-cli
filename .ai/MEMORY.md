# Memory - desk-cli

## Lessons

- **The desk-bound surface lives in `cli.py`, not `rundesk.py`.** `show` (`GET /desk`), `inbox`, and `mentions` are registered by `cli._reshape_desk_surface`; `rundesk.py` has no desk group at all. `whoami` survives only as a hidden alias of `show` for installed agents.
- **No orphan client methods.** `test_cli.py` asserts every public `RundeskClient` method is referenced from the command tree, so adding an endpoint is a two-file change (client + command) or the suite fails. The gate greps `rundesk.py` AND `cli.py` — a desk-surface method referenced only from `cli.py` is still covered.

## Preferences

- **A blank list argument means "omitted", never an empty array.** `_parse_id_list` returns `None` for blank `--project-ids` so it can't silently detach every project. Keep this for any array-valued flag.

## Known Traps / Gotchas

- **The 3.9 floor rides on `from __future__ import annotations`.** `X | None` hints only parse on 3.9 because every module imports it; a new module needs the same import, and a `X | Y` union used outside an annotation (or `match`/`tomllib`) breaks the floor silently.
- **A test that drives a full command must set `DESK_NO_UPDATE_CHECK=1`** — `cli.main` runs `updater.maybe_notify` after each command, which can hit the network.
- **Desk assignment wire names are not the display-language owner names.** `/desks` accepts `assignee_type` / `assignee_actor_id` for who sits at the desk and `owner_id` for the responsible human on an agent desk. The CLI's released `--owner-*` spellings are aliases only; never send those names to the API.
- **Page reorder is hierarchy-scoped.** `/projects/{id}/pages/reorder` accepts `scopes: [{parent_page_id, ids}]`, not the old flat `ids` payload. Each affected sibling scope must be complete; use multiple scopes for a cross-parent move.
- **`help=argparse.SUPPRESS` does NOT hide a subcommand.** `add_parser(..., help=SUPPRESS)` still creates a pseudo-action, and argparse prints it as a literal `==SUPPRESS==` row. Hiding one takes two more steps: drop the pseudo-action from `sub._choices_actions` (`cli._hide_subcommand`) AND set `sub.metavar`, because the usage line's `{a,b,c}` brace is built from `action.choices`, which the alias must stay in to keep working.
- **The CLI endpoint walker cannot synthesize a required mutually exclusive option group.** Add one valid selector to `EXTRA_ARGS` in `tests/test_cli.py` for any leaf such as `move-week` whose required choice is made entirely of optional flags; otherwise the walk exits in argparse before reaching the fake transport.
- **rundesk-cli's `./dev` wrapper forces its repository-local `.scratch/rundesk-home`.** Exporting a temporary `RUNDESK_HOME` does not isolate catalog validation because the wrapper overwrites it. Validate there only after confirming the scratch home is disposable, then remove the exact synthetic agent, profile, grant, and catalog through Rundesk commands.
- **A repository-root `import desk_cli` needs `PYTHONPATH=src`.** The package is not installed into the development interpreter; use `PYTHONPATH=src python3 ...` for release/version probes instead of treating an import failure as a package defect.
- **Profile writes are compare-and-swap operations.** `load_config()` carries the bytes it read; `save_config()` locks `config.json.lock` and raises `ConfigConflict` if another process replaced the file. A workflow spanning an API call must reload and retry its mutation instead of saving the stale pre-request mapping.

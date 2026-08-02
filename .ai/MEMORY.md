# Memory - desk-cli

## Lessons

- **The desk-bound surface lives in `cli.py`, not `rundesk.py`.** `show` (`GET /desk`), `inbox`, and `mentions` are registered by `cli._reshape_desk_surface`; `rundesk.py` has no desk group at all. `whoami` survives only as a hidden alias of `show` for installed agents.
- **No orphan client methods.** `test_cli.py` asserts every public `RundeskClient` method is referenced from the command tree, so adding an endpoint is a two-file change (client + command) or the suite fails. The gate greps `rundesk.py` AND `cli.py` — a desk-surface method referenced only from `cli.py` is still covered.

## Preferences

- **A blank list argument means "omitted", never an empty array.** `_parse_id_list` returns `None` for blank `--project-ids` so it can't silently detach every project. Keep this for any array-valued flag.

## Known Traps / Gotchas

- **The 3.9 floor rides on `from __future__ import annotations`.** `X | None` hints only parse on 3.9 because every module imports it; a new module needs the same import, and a `X | Y` union used outside an annotation (or `match`/`tomllib`) breaks the floor silently.
- **A test that drives a full command must set `DESK_NO_UPDATE_CHECK=1`** — `cli.main` runs `updater.maybe_notify` after each command, which can hit the network.
- **`help=argparse.SUPPRESS` does NOT hide a subcommand.** `add_parser(..., help=SUPPRESS)` still creates a pseudo-action, and argparse prints it as a literal `==SUPPRESS==` row. Hiding one takes two more steps: drop the pseudo-action from `sub._choices_actions` (`cli._hide_subcommand`) AND set `sub.metavar`, because the usage line's `{a,b,c}` brace is built from `action.choices`, which the alias must stay in to keep working.

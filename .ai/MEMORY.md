# Memory - desk-cli

## Lessons

- **`whoami` differs between the two entry points.** In `rundesk.py` it's the account `/me` one-liner; the installed `desk` (`cli.py`) reshapes the tree so `desk whoami` is the desk identity (`GET /desk`) and the account record moves to `desk account`.
- **No orphan client methods.** `test_cli.py` asserts every public `RundeskClient` method is reachable from the command tree, so adding an endpoint is a two-file change (client + command) or the suite fails.

## Preferences

- **A blank list argument means "omitted", never an empty array.** `_parse_id_list` returns `None` for blank `--project-ids` so it can't silently detach every project. Keep this for any array-valued flag.

## Known Traps / Gotchas

- **The 3.9 floor rides on `from __future__ import annotations`.** `X | None` hints only parse on 3.9 because every module imports it; a new module needs the same import, and a `X | Y` union used outside an annotation (or `match`/`tomllib`) breaks the floor silently.
- **A test that drives a full command must set `DESK_NO_UPDATE_CHECK=1`** — `cli.main` runs `updater.maybe_notify` after each command, which can hit the network.

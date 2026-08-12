# Brief - desk-cli

## Story

`desk` is a zero-dependency, installable command-line client for the Rundesk API. It is distributed to strangers' machines via `curl | bash`, stores their API credentials locally, and exposes the full Rundesk REST surface — account, the desk read surface (identity, inbox, mentions), projects, pages, tasks, weeks, assets, and owner desk management — as plain subcommands with stable, parseable output. Its skill catalog separately supports owner-assigned passive task handling and delegated active queue management. It runs on the system `python3` (3.9+) and the standard library only, and self-updates over HTTPS without git. The outcome: anyone with Python can drive Rundesk from a terminal or a script in about a minute.

## Users / ICP

- **Rundesk users at the terminal** — want to read and edit their projects, pages, and tasks without opening the web app; value zero setup and compact, greppable output.
- **Scripts and AI agents** — parse `desk` output (or `--json`) and depend on the command surface, exit codes, and stored formats staying stable across releases.
- **Multi-identity operators** — run several desks/keys on one machine (one per agent, one per project) and switch between them per shell, per directory, or per command.
- Shared qualities that matter most: no dependencies to install, credentials stored safely (`chmod 600`, keys never printed in full), and a command/output contract that does not break under them.

## Scope

- **Active areas:**
  - Full-API command tree over the Rundesk REST surface (`rundesk.py` + `client.py`).
  - Local multi-profile credential store with a five-step resolution order (`profiles.py`).
  - The installable `desk` command surface — profiles, help, `show`/`inbox`/`mentions`, uninstall (`cli.py`).
  - One-command installer and git-free self-update (`install.sh`, `updater.py`).
- **Out of scope:** the Rundesk calendar pass-through, asset-embed resolution, and admin/feedback routes (not mirrored by the client); any third-party runtime dependency; any Python older than 3.9.

## External Systems

- `Rundesk REST API` (`/api/v1`) — the product this tool drives; bearer-authenticated, one key per workspace/desk actor.
- `GitHub Releases / Tags API` — version discovery and the source archive downloaded by `desk update` and the installer (no git required).
- `Local filesystem config store` — named profiles in a `chmod 600` JSON file under `${XDG_CONFIG_HOME:-~/.config}/desk/`; install tree under `~/.desk`; optional `.desk-profile` selector files in working directories.

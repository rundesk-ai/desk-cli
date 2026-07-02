# desk

[![Build](https://github.com/rundesk-ai/desk-cli/actions/workflows/build.yml/badge.svg)](https://github.com/rundesk-ai/desk-cli/actions/workflows/build.yml)

`desk` is a lightweight command-line client for the [Rundesk](https://rundesk.ai) API.
It stores your Rundesk API key locally (with support for multiple named profiles)
and gives you the full Rundesk API from your terminal — projects, pages, tasks,
weeks, assets, jobs, and the desk agent surface.

No dependencies: it runs on the system `python3` (3.9+) and the standard library only.

## Install

One command — it downloads the latest release and puts `desk` on your PATH:

```bash
curl -fsSL https://raw.githubusercontent.com/rundesk-ai/desk-cli/main/install.sh | bash
```

That's it. Then set up a profile and you're ready:

```bash
desk profile add     # prompts for a name, base URL, and API key (validated on save)
desk whoami          # confirm it works
```

<sub>The installer downloads into `~/.desk` and symlinks `desk` into `/usr/local/bin`
(or `~/.local/bin`). No git, no clone. If `~/.local/bin` isn't on your PATH, the
installer tells you the one line to add.</sub>

## Updating

`desk` checks for new versions and tells you when one is available. To upgrade:

```bash
desk update           # download + install the latest release
desk update --check   # just check, don't change anything
desk --version        # current version
```

Updates download the latest release archive over HTTPS and replace the install in
place — no git required.

## Profiles

Credentials live in a `chmod 600` file at `${XDG_CONFIG_HOME:-~/.config}/desk/config.json`.
Keys are never shown in full. A profile is saved **only if its key authenticates**
against the API — a bad key is an error, not a stored-but-broken profile. The base
URL is optional and defaults to `https://rundesk.ai`.

| Command | What it does |
|---|---|
| `desk profile add [name]` | Add a profile interactively (name, base URL, API key), validating the key. |
| `desk profile list` | List saved profiles (keys masked); `*` marks the default. |
| `desk profile use <name>` | Set the default profile. |
| `desk profile show [name]` | Show a profile's details (key masked). |
| `desk profile remove <name>` | Delete a saved profile. |
| `desk profile local [name]` | Bind the current directory to a profile via a `.desk-profile` file (`--clear` to remove). |

**Which profile a command uses** is resolved in this order:

1. `--profile NAME` on the command line (before the subcommand: `desk --profile work tasks list`),
2. the `DESK_PROFILE` environment variable,
3. a `.desk-profile` file in the current directory or an ancestor,
4. `RUNDESK_API_KEY` (+ optional `RUNDESK_BASE_URL`) in the environment,
5. the saved **default** profile.

## Multiple agents on one machine

Several agents (or people) can share one install and each use their own identity —
no one has to touch the shared default:

- **Per session:** `export DESK_PROFILE=agent-a` — every `desk` command in that
  session uses `agent-a`.
- **Per directory** (same environment, different working dirs): drop a
  `.desk-profile` file in each agent's directory:
  ```bash
  cd /work/agent-a && desk profile local agent-a   # writes ./.desk-profile  (profile=agent-a)
  cd /work/agent-b && desk profile local agent-b
  ```
- **Per command:** `desk --profile agent-b tasks list`.
- **Full isolation:** give each agent its own `XDG_CONFIG_HOME` (separate config).

## Commands

Every Rundesk endpoint is a subcommand. Reads print compact text by default;
add `--json` for the raw payload. Destructive deletes require `--confirm`.

```
desk whoami                     # this desk's identity: brief, rules, jobs, projects
desk account | changelog        # the account behind the key
desk inbox [--week N | --unscheduled]   # this desk's to-do (tasks + mentions)
desk jobs    list | get | create | update | delete
desk projects list | get | create | update | archive | unarchive | delete
desk page    list | get | create | update | patch | delete | reorder | search
desk tasks   list | get | create | update | complete | uncomplete | restore |
             delete | move-week | move-project | deadline-set | deadline-remove |
             recur-set | recur-update | recur-remove | comments | comment | …
desk week | weeks
desk asset   get | search | list-project | list-page | upload-* | rename-* | delete-*
desk desks   list | get | create | update | delete | retire | unretire |
             attach | detach | mint-key
```

Run `desk help` for the full list, or `desk help <command>` (e.g. `desk help tasks`).
The surface available depends on your key: a **desk-bound** key uses `desk whoami`
and `desk inbox`; an **owner** key manages desks via `desk desks …`.

## Uninstall

```bash
desk uninstall            # remove the desk command
desk uninstall --purge    # also delete saved profiles
```

## Development

Clone the repo and run `./install.sh` from it — that symlinks your checkout
instead of downloading a release. Tests are standard-library only:

- `python3 tests/test_profiles.py` — profile store, credential resolution, updater.
- `python3 tests/test_cli.py` — walks every command against a fake transport.
- `python3 tests/test_rundesk.py` — the REST client's request/response suite.

Layout: `src/desk_cli/client.py` (REST client), `rundesk.py` (full-API command
tree), `cli.py` (profiles, update, help, and the `desk whoami` / `desk inbox`
surface). Cut a release by bumping `__version__` in `src/desk_cli/__init__.py`
and tagging `vX.Y.Z`.

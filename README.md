# desk

A lightweight, installable command-line client for the [Rundesk](https://rundesk.ai) API.

`desk` stores your Rundesk API credentials locally as one or more named **profiles**
and gives you the full Rundesk API surface from your terminal — projects, pages,
tasks, weeks, assets, jobs, and the desk agent surface. Zero third-party
dependencies: it runs on the system `python3` (3.9+) and the standard library only.

## Install

```bash
git clone https://github.com/rundesk-ai/desk-cli.git
cd desk-cli
./install.sh
```

`install.sh` symlinks the `desk` command into `/usr/local/bin` (or `~/.local/bin`
if that isn't writable) and prints the installed version. To remove it later:

```bash
./install.sh --uninstall   # leaves your saved profiles untouched
```

## Quick start

```bash
desk profile add        # prompts for a name, base URL, and API key (hidden),
                        # then verifies the key before saving
desk whoami             # confirm the key resolves to your account
desk projects list
desk tasks list
```

## Profiles

Credentials live in a `chmod 600` JSON file at
`${XDG_CONFIG_HOME:-~/.config}/desk/config.json`. Keys are never printed in full —
`list`/`show` mask everything but the last four characters.

| Command | What it does |
|---|---|
| `desk profile add [name]` | Add a profile interactively (name, base URL, API key). Verifies the key, then offers to make it the default. |
| `desk profile list` | List saved profiles (keys masked); `*` marks the default. |
| `desk profile use <name>` | Set the default profile. |
| `desk profile show [name]` | Show a profile's details (key masked). Defaults to the current default. |
| `desk profile remove <name>` | Delete a saved profile. |
| `desk profile local [name]` | Bind the current directory to a profile via a `.desk-profile` file (`--clear` to remove). |

**Which profile a command uses** is resolved in this order:

1. `--profile NAME` on the command line (place it before the subcommand:
   `desk --profile work tasks list`),
2. the `DESK_PROFILE` environment variable,
3. `RUNDESK_API_KEY` (+ optional `RUNDESK_BASE_URL`) in the environment — a handy
   escape hatch for CI or a one-off,
4. the saved **default** profile.

## Multiple agents / profiles on one machine

Several agents (or people) can share one install and each use their **own**
Rundesk identity. Credentials are selected per invocation, so an agent never has
to touch the shared `default`. In precedence order:

1. **`--profile NAME` flag** — `desk --profile agent-b tasks list` (one command).
2. **`DESK_PROFILE` env var** — set once in an agent's session; every `desk`
   command that process runs uses it: `export DESK_PROFILE=agent-a`.
3. **`.desk-profile` file in the working directory** — see below.
4. **`RUNDESK_API_KEY`** (+ optional `RUNDESK_BASE_URL`) in the env — direct key
   injection, bypasses the store (handy for CI / ephemeral agents).
5. The saved **`default`** profile.

### Same environment, different directories

If agents share one environment (same user, same env vars) and differ only by
**working directory**, put a `.desk-profile` file in each agent's directory. Any
`desk` command run there (or in a subdirectory) uses that profile automatically:

```bash
cd /work/agent-a && desk profile local agent-a   # writes ./.desk-profile
cd /work/agent-b && desk profile local agent-b
```

The file just holds a `profile` variable (a bare name also works):

```ini
# /work/agent-a/.desk-profile
profile=agent-a
```

`desk profile local` (no argument) shows which profile the current directory
resolves to; `desk profile local --clear` removes the file.

### Full isolation

Give each agent its own config entirely by pointing `XDG_CONFIG_HOME` at a
per-agent dir — each then has a separate `config.json`:

```bash
XDG_CONFIG_HOME=~/agents/a/.config desk profile add
XDG_CONFIG_HOME=~/agents/b/.config desk profile add
```

Notes: `desk profile use <name>` changes the shared **default** everyone sees, so
in a multi-agent setup prefer `DESK_PROFILE` / `--profile` / `.desk-profile`. The
config file is written atomically, so concurrent updates won't corrupt it. When
adding a profile, the **base URL is optional** — press Enter to accept the default
`https://rundesk.ai`; only enter one if your Rundesk lives elsewhere. A profile is
saved **only if its key authenticates** against `/me`; a bad key is an error, not
a stored-but-broken profile.

## API commands

Every Rundesk endpoint is available as a subcommand. Text-capable reads print
compact pipe-delimited rows by default; pass `--json` for the raw payload.
Destructive deletes require `--confirm`.

```
desk whoami                     # this desk's identity: brief, rules, jobs, projects
desk account | changelog        # the account record behind the key
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

Run `desk <command> --help` for the full options of any command. The available
surface depends on your key: a **desk-bound** key uses `desk desk …`; an **owner**
key manages desks via `desk desks …` (the other returns a clear 403).

## Updating

```bash
desk --version          # the installed version
desk update --check     # is a newer release available?
desk update             # fast-forward the checkout to the latest release tag
```

`update` compares the bundled version against the latest GitHub release, then
updates the git checkout in place (it refuses if you have local changes). If you
installed some other way, update however you installed it.

## Development

- `python3 tests/test_profiles.py` — profile store, credential resolution, updater logic.
- `python3 tests/test_cli.py` — walks **every** command through the CLI against a
  fake transport, proving all endpoints are wired and credentialed; plus the
  local `profile` / `update` / `uninstall` / `help` commands.
- `python3 tests/test_rundesk.py` — the REST client's request/response suite.

Layout: `src/desk_cli/client.py` is the Rundesk REST client, `rundesk.py` builds
the full-API command tree, and `cli.py` layers the profile / update / help surface
and the `desk show` / `desk inbox` commands on top. Standard library only — no
third-party dependencies.

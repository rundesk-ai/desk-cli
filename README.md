# desk

[![Build](https://github.com/rundesk-ai/desk-cli/actions/workflows/build.yml/badge.svg)](https://github.com/rundesk-ai/desk-cli/actions/workflows/build.yml)

**The full [Rundesk](https://rundesk.ai) API, from your terminal.** Projects, pages, tasks, weeks, assets, jobs, and the desk agent surface — all as simple subcommands, with your API keys stored safely on your machine.

No dependencies. If you have `python3` (3.9+), you're ready.

## Get started in 60 seconds

**1. Install** — one command downloads the latest release and puts `desk` on your PATH:

```bash
curl -fsSL https://github.com/rundesk-ai/desk-cli/releases/latest/download/install.sh | bash
```

**2. Add your API key:**

```bash
desk profile add
```

You'll be prompted for a name, base URL (just press Enter for `https://rundesk.ai`), and your API key. The key is validated against the API before it's saved — so if it works, you're in.

**3. Confirm it works:**

```bash
desk whoami
```

That's it. You're connected.

<sub>The installer downloads into `~/.desk` and symlinks `desk` into `/usr/local/bin` (or `~/.local/bin`). No git, no clone. If `~/.local/bin` isn't on your PATH, the installer tells you the one line to add.</sub>

## Everyday use

Every Rundesk endpoint is a subcommand. Reads print compact, human-friendly text by default — add `--json` when you want the raw payload. Anything destructive requires `--confirm`, so you can't delete something by accident.

```
desk whoami                     # this desk's identity: brief, rules, jobs, projects
desk inbox                      # this desk's to-do (tasks + mentions)
desk inbox --week 3             # ...for a specific week
desk inbox --unscheduled        # ...just the unscheduled items
desk account | changelog        # the account behind the key
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

Not sure what a command does? `desk help` lists everything, and `desk help <command>` (e.g. `desk help tasks`) goes deeper.

**What you can do depends on your key.** A **desk-bound** key works from a desk's point of view (`desk whoami`, `desk inbox`); an **owner** key manages desks themselves (`desk desks …`).

## Profiles

A profile is a saved API key with a name. You can have as many as you like — one for work, one for a side project, one per agent — and switch between them freely.

| Command | What it does |
|---|---|
| `desk profile add [name]` | Add a profile interactively (name, base URL, API key). The key is validated before saving. |
| `desk profile list` | List saved profiles (keys masked); `*` marks the default. |
| `desk profile use <name>` | Set the default profile. |
| `desk profile show [name]` | Show a profile's details (key masked). |
| `desk profile remove <name>` | Delete a saved profile. |
| `desk profile local [name]` | Bind the current directory to a profile via a `.desk-profile` file (`--clear` to remove). |

Your credentials live in a `chmod 600` file at `${XDG_CONFIG_HOME:-~/.config}/desk/config.json`, and keys are never shown in full.

**Which profile does a command use?** First match wins:

1. `--profile NAME` on the command line (before the subcommand: `desk --profile work tasks list`)
2. the `DESK_PROFILE` environment variable
3. a `.desk-profile` file in the current directory or an ancestor
4. `RUNDESK_API_KEY` (+ optional `RUNDESK_BASE_URL`) in the environment
5. your saved **default** profile

## Multiple agents, one machine

Several agents (or people) can share a single install, each with their own identity — nobody has to touch the shared default. Pick whichever fits your setup:

- **Per session:** `export DESK_PROFILE=agent-a` — every `desk` command in that shell uses `agent-a`.
- **Per directory:** give each agent a working directory and bind it once:
  ```bash
  cd /work/agent-a && desk profile local agent-a   # writes ./.desk-profile
  cd /work/agent-b && desk profile local agent-b
  ```
- **Per command:** `desk --profile agent-b tasks list`.
- **Full isolation:** give each agent its own `XDG_CONFIG_HOME` for a completely separate config.

## Staying up to date

`desk` checks for new versions and lets you know when one is available. Upgrading is one command:

```bash
desk update           # download + install the latest release
desk update --check   # just check, don't change anything
desk --version        # what you're running now
```

Updates download the latest release archive over HTTPS and replace the install in place — no git required.

## Uninstall

```bash
desk uninstall            # remove the desk command
desk uninstall --purge    # also delete saved profiles
```

## Development

Clone the repo and run `./install.sh` from inside it — that symlinks your checkout instead of downloading a release.

Tests are standard-library only:

- `python3 tests/test_profiles.py` — profile store, credential resolution, updater.
- `python3 tests/test_cli.py` — walks every command against a fake transport.
- `python3 tests/test_rundesk.py` — the REST client's request/response suite.

Layout: `src/desk_cli/client.py` (REST client), `rundesk.py` (full-API command tree), `cli.py` (profiles, update, help, and the `desk whoami` / `desk inbox` surface).

To cut a release: bump `__version__` in `src/desk_cli/__init__.py` and tag `vX.Y.Z`.

# desk

[![Build](https://github.com/rundesk-ai/desk-cli/actions/workflows/build.yml/badge.svg)](https://github.com/rundesk-ai/desk-cli/actions/workflows/build.yml)

**The full [Rundesk](https://rundesk.ai) API, from your terminal.** Projects, pages, tasks, weeks, assets, and your desk — all as simple subcommands, with your API keys stored safely on your machine.

No dependencies. If you have `python3` (3.9+), you're ready.

`desk` complements [Rundesk CLI](https://github.com/rundesk-ai/rundesk-cli): Rundesk CLI runs the
agents, while `desk` gives those agents a scoped command-line connection to Rundesk tasks, mentions,
projects, and files. Install the `desk` executable once per machine, then install this repository's
skill catalog in Rundesk CLI for the agents that should use it.

## Get started in 60 seconds

**1. Install** — one command downloads the latest release and puts `desk` on your PATH:

```bash
curl -fsSL https://get.rundesk.ai/desk | bash
```

**2. Add your API key:**

```bash
desk profile add
```

You'll be prompted for a name, base URL (just press Enter for `https://rundesk.ai`), and your API key. The key is validated against the API before it's saved — so if it works, you're in.

**3. Confirm it works:**

```bash
desk show
```

That's it. You're connected.

<sub>The installer downloads into `~/.desk` and symlinks `desk` into `/usr/local/bin` (or `~/.local/bin`). No git, no clone. If `~/.local/bin` isn't on your PATH, the installer tells you the one line to add.</sub>

### Give Rundesk agents the desk skill

[Rundesk CLI](https://github.com/rundesk-ai/rundesk-cli) installs and grants the compact
`managing-your-desk` skill from this repository:

```bash
"$RUNDESK_COMMAND" skills install https://github.com/rundesk-ai/desk-cli
"$RUNDESK_COMMAND" skills install https://github.com/rundesk-ai/desk-cli --confirm
"$RUNDESK_COMMAND" skills grant <agent> desk-cli/managing-your-desk
```

The first install command previews the catalog; the confirmed command installs it. Install the
`desk` executable once on the machine, then keep one named desk profile per agent so each agent
uses its own scoped identity.

## Everyday use

Every Rundesk endpoint is a subcommand. Reads print compact, human-friendly text by default — add `--json` when you want the raw payload. Anything destructive requires `--confirm`, so you can't delete something by accident.

```
desk show                       # this desk: identity, owner, and projects
desk inbox                      # this desk's to-do (tasks + mentions)
desk inbox --week 3             # ...for a specific week
desk inbox --unscheduled        # ...just the unscheduled items
desk mentions                   # unread mentions on this desk's tasks
desk account | changelog        # the account behind the key
desk projects list | get | create | update | archive | unarchive | delete
desk page    list | get | create | update | patch | delete | reorder | search | grep
desk tasks   list | get | create | update | complete | uncomplete | restore |
             delete | move-week | move-project | deadline-set | deadline-remove |
             recur-set | recur-update | recur-remove | comments | comment | …
desk week | weeks
desk asset   get | list | update | search | list-project | list-page | upload-* |
             rename-* | delete-*
desk desks   list | get | create | update | delete | retire | unretire |
             attach | detach | mint-key --save-profile NAME
```

Not sure what a command does? `desk help` lists everything, and hierarchical help reaches any leaf:
`desk help tasks move-week` is equivalent to `desk tasks move-week --help`.

**What you can do depends on your key and workspace role.** A **desk-bound** key works from a desk's point of view (`desk show`, `desk inbox`, `desk mentions`). Owner/admin keys additionally manage desks (`desk desks …`) and target account-wide work. The advanced `desk user-mentions …` group is only for a non-desk member key acting as the signed-in human; it is separate from the desk agent's `desk mentions` inbox.

Project page indexing is automatic on create and can be changed with
`desk projects update <id> --index-pages|--no-index-pages`. The released
`--hidden` project flag is retained only to return an actionable retirement
error. Desk assignment uses `--assignee-type`, `--assignee-actor-id`, and—for an
agent desk—`--owner-id`; the old `--owner-type`/`--owner-actor-id` spellings are
compatible aliases.

Desk `--brief`, `--rules`, and `--memory` fields remain API-write-compatible, but do not configure
an agent; rundesk-cli keeps agent instructions and memory in that agent's home.
`desks mint-key` writes the one-time credential directly into a new protected local profile and
prints only its masked suffix. It refuses an existing destination before minting; if another process
claims that name during the request, it preserves both profiles under a unique `-minted` name.

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

Rundesk can also inject named skill profiles as suffixed environment variables. Select one explicitly
with `desk --env-profile NAME <command>`. It reads only `RUNDESK_API_KEY__NAME` and the optional matching
`RUNDESK_BASE_URL__NAME`; it never borrows an unsuffixed or saved value. `--env-profile` and the saved
`--profile` selector are mutually exclusive.

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
- **Rundesk skill profile:** `desk --env-profile agent_b tasks list` reads the complete injected
  `__AGENT_B` environment set without consulting saved profiles.
- **Full isolation:** give each agent its own `XDG_CONFIG_HOME` for a completely separate config.

## Teaching an agent to use it

This repository is also a **Rundesk skill catalog** for
[Rundesk CLI](https://github.com/rundesk-ai/rundesk-cli). The executable and skill are separate:
install `desk` with the command at the top of this README, then install the catalog through Rundesk
CLI and grant it to each agent that should manage a desk:

```bash
"$RUNDESK_COMMAND" skills install https://github.com/rundesk-ai/desk-cli            # preview
"$RUNDESK_COMMAND" skills install https://github.com/rundesk-ai/desk-cli --confirm  # install
"$RUNDESK_COMMAND" skills grant <agent> desk-cli/managing-your-desk
```

`managing-your-desk` teaches a Desk-owning agent to select its exact Rundesk environment profile and
self-manage an ordered weekly commitment: promote handleable inbox/mention work, keep active tasks as
compact briefs, preserve GitHub as implementation truth, schedule real follow-up, and complete only
with proof. It also includes an authority-gated standing-rule snippet for persistent queue owners;
bounded specialist agents do not adopt it. Non-desk profiles can manage the signed-in human's mention
inbox; owner/admin profiles can explicitly target and administer desks; desk profiles read their own
desk actor's mentions.

Installing the catalog does not install `desk` itself — do that first, with the one-liner at the top of this README.

## Upgrading from 0.2

The saved profile format remains version 1; existing profiles continue to load unchanged. Two command
changes are intentional:

- `desk desks mint-key` now requires `--save-profile NAME`. The one-time credential is written directly
  to the protected profile store and is never printed in full.
- The retired project `--hidden` flag now returns an actionable error. Use `projects archive` or
  `projects unarchive` instead; hidden and archived are not treated as interchangeable states.

Update scripts that use either command before upgrading. Other existing profile selectors and command
aliases remain supported.

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

Layout: `src/desk_cli/client.py` (REST client), `rundesk.py` (full-API command tree), `cli.py` (profiles, update, help, and the `desk show` / `desk inbox` / `desk mentions` surface).

To cut a release: bump `__version__` in `src/desk_cli/__init__.py` and tag `vX.Y.Z`.

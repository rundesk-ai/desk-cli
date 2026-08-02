---
name: managing-your-desk
description: Work a Rundesk desk from the command line with `desk`. Use whenever you are asked what is on your plate, what is due this week, or what somebody said to you on a task — and whenever you need to create, schedule, update, complete, or comment on a task, or read the project pages and files behind one. Your desk is the shared record your owner sees: it is where work is given to you and where you report back. Not for your own rules, memory, or identity.
---

# Managing your desk

A **desk** is your place in your owner's Rundesk workspace: the tasks assigned to you, the
projects you cover, and the people who reach you there. `desk` is how you read it and how you
change it.

**A question about your work is a `desk` command, not a guess.** You have a shell. `desk help`
and `desk help <command>` are generated from the command itself and cannot be out of date —
where anything here disagrees with them, the command is right.

## The boundary that matters

Your desk holds **work**. It does not hold **you**.

- Tasks, weeks, projects, pages, files, and what people said to you → the desk. Use `desk`.
- Your rules, your memory, your identity → `AGENTS.md`, `MEMORY.md`, `SOUL.md` in your own
  home. Never look for them on the desk, and never write them there.

## First, know where you are

```sh
desk show        # this desk: identity, owner, and projects
```

It names the desk you are keyed to, the owner to escalate to, and the projects you cover. Run
it before answering anything about "your" work — the desk your key opens is the only one you
can see, and it is not always the one somebody means.

**If `desk --version` fails, `desk` is not installed here.** Say so plainly rather than
improvising. It installs with:

```sh
curl -fsSL https://github.com/rundesk-ai/desk-cli/releases/latest/download/install.sh | bash
```

## The work

| Need | Command |
|---|---|
| This week's tasks, with their latest comments | `desk inbox` |
| A specific week | `desk inbox --week <id>` |
| The unscheduled backlog | `desk inbox --unscheduled` |
| The week buckets — ids, dates, progress | `desk weeks` · `desk week` |
| One task in full — body, comments, files | `desk tasks get <id> --json` |
| Find tasks | `desk tasks list [--project-id N] [--status todo\|done] [--week-id N] [--inbox]` |

**Start at `desk inbox`.** It is this week's tasks *and* what has been said to you in one call
— the read that answers "what am I doing" without four commands.

## What was said to you

```sh
desk mentions              # unread mentions on this desk's tasks, newest first
desk mentions --limit 5
```

Somebody `@`-mentioning you on a task is how work reaches you between assignments. **Answering
is replying on the task** — a comment of yours clears the mention as a side effect of handling
it. There is no "mark as read": handle it, or leave it standing.

## Changing things

```sh
desk tasks create --title "…" [--body "…"] [--project-id N] [--week-id N]
desk tasks update <id> …
desk tasks complete <id>
desk tasks move-week <id> --week-id <id>        # or --inbox to send it back to the backlog
desk tasks comment <id> "…"                     # report back; @handle the owner for a decision
```

Omit `--week-id` on create and the task lands in the backlog. **Do not guess a schedule.** An
explicit signal — "this week", a date, a deadline — resolves to a week id through `desk weeks`.
No signal means the backlog. An ambiguous batch means ask, rather than scattering tasks across
weeks on your own reading of a sentence.

## The material behind a task

A task is rarely the whole story. `desk tasks get <id> --json` returns its `assets[]`; each one
is `desk asset get <asset_id>` — text comes back inline, a binary comes back as a short-lived
`download_url` to fetch and open. `desk projects get <id>` and `desk page list <project_id>`
are the project's own pages and files.

**Never answer about a task with attachments without opening them.**

## Several agents, one machine

Each agent uses its own key. Bind a working directory to yours once, and every `desk` command
run from there uses it:

```sh
desk profile local <profile-name>       # writes ./.desk-profile
```

`DESK_PROFILE=<name>` scopes a shell; `desk --profile <name> …` scopes a single command.

## Gotchas

- **Your key decides what you can see.** `desk show`, `desk inbox`, and `desk mentions` need a
  desk-bound key. An owner key manages desks and is refused on all three.
- **Reads are text; `--json` is the payload.** Default output is compact and meant to be read.
  Parse `--json`. `page` and `asset` are always JSON.
- **Anything destructive needs `--confirm`**, and every one of them is your owner's decision,
  not yours. Deleting is never how you finish a task — completing is.
- **A comment is how you report.** What you did belongs on the task, where your owner will look
  for it, not only in the conversation you are having.

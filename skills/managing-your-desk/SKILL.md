---
name: managing-your-desk
description: Manage your desk's rundesk tasks with `desk`. Use for anything about this desk's work — what is on the plate for this week, what is due, what is unanswered, and creating, mentioned, completing or commenting on tasks.
---

# Managing desk tasks

Your work is on a desk in Rundesk. The desk is resolved from your key: there is no id to
pass and no other desk you can reach.

## Start here

```sh
desk inbox        # this week's tasks, their latest comments, and your unread mentions
```

One call, and the answer to "what am I working on". Do not rebuild it out of
`desk tasks list`. `desk show` names the desk, its owner, and its projects.

## Weeks are buckets, not dates

A task sits in exactly one week — Mon–Sun, numbered — or in none, which is the backlog.

| Need | Command |
|---|---|
| Week ids and their dates | `desk weeks` |
| Another week's tasks | `desk inbox --week <id>` |
| The backlog | `desk inbox --unscheduled` |
| Move one | `desk tasks move-week <id> --week-id <id>`, or `--inbox` |

`desk tasks create --title "…"` with no `--week-id` lands in the **backlog**, not this week.

**Do not guess a week.** "This week" or a date resolves through `desk weeks`; no timing
signal means the backlog; a batch that could span weeks is a question for your owner. A
task filed into the wrong week is invisible until somebody goes looking for it.

## Mentions are how work reaches you

```sh
desk mentions
```

There is no mark-as-read. **Commenting on the task is what clears its mention** — so one
you decide not to answer stays unanswered, and stays visible.

## Reporting back

```sh
desk tasks comment <id> "…"      # body is positional, not a flag
desk tasks complete <id>
```

The comment is where your owner looks for what you did; the conversation you are having is
not. `@handle` them when you need a decision — `desk show` names them.

## Going further

- Read `references/task-verbs.md` for a deadline, a repeat, editing or deleting a comment,
  reopening or restoring a task, or moving one between projects.
- Read `references/projects-and-files.md` when you need the material behind a task, or when
  you have a title or phrase instead of an id.

`desk help <command>` is generated from the command itself, so it is right when anything
here is not.

## Gotchas

- **`desk tasks get <id> --json` carries `assets[]`**, and the actual requirement is often
  in there rather than in the body. Open each with `desk asset get <id>` before answering:
  text comes back inline, a binary comes back as a short-lived `download_url`.
- **Your rules and memory are not on the desk.** They are `AGENTS.md` and `MEMORY.md` in
  your own home. The desk carries tasks and projects and nothing about you, so do not go
  looking there for how you are meant to work.
- **Completing is how you finish a task, never deleting.** Every destructive verb needs
  `--confirm` and is your owner's call, not yours.

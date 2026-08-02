# Task verbs beyond the core

`desk help tasks` and `desk help tasks <verb>` are generated from the command and are
authoritative for exact flags. This file is the intent index the help output is not.

## Deadlines

A deadline is separate from the week a task sits in. A task can be scheduled into a week
and have no deadline, or have one and sit in the backlog.

```sh
desk tasks deadline-set <id> --due-at 2026-08-14T17:00:00Z   # --all-day for a date only
desk tasks deadline-remove <id>
```

## Repeats

```sh
desk tasks recur-set <id> --frequency daily|weekly|monthly|yearly --interval N \
    --end-type never|count|date [--end-count N] [--end-date YYYY-MM-DD] \
    [--days-of-week mon,wed] [--day-of-month N] [--start-at …] [--due-time …] [--due-weekday …]
desk tasks recur-update <id> …     # same flags; changes the rule going forward
desk tasks recur-remove <id>       # stops future occurrences, keeps what exists
```

Set the recurrence on the task it should repeat from. `recur-remove` does not delete the
occurrences already created.

## Comments

```sh
desk tasks comments <id>                          # the whole thread
desk tasks comment-edit <id> <comment_id> "…"     # yours only
desk tasks comment-delete <id> <comment_id> --confirm
```

Editing or deleting a comment does not re-raise a mention it cleared.

## Undo and moving

```sh
desk tasks uncomplete <id>                        # reopen a completed task
desk tasks restore <id>                           # bring back a deleted one
desk tasks move-project <id> --project-id N       # or --none to detach it
desk tasks delete <id> --confirm
```

`restore` exists because a delete is soft — but a delete is still your owner's call, and
completing is how you finish work.

## Filtering

```sh
desk tasks list --status todo|done --project-id N --week-id N --inbox --json
```

`--week-id` and `--inbox` are mutually exclusive; the API rejects both together.

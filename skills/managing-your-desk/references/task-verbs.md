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
desk tasks recur-set <id> --frequency daily|weekly|monthly --interval N \
    --end-type never|count|date [--end-count N] [--end-date YYYY-MM-DD] \
    [--days-of-week 1 3] [--day-of-month N] [--start-at YYYY-MM-DD] \
    [--due-time HH:MM | --due-all-day] [--due-weekday 1]
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

## Mentions

Desk-bound profiles use `desk mentions`; posting the task reply clears the desk actor's waiting
mention. Non-desk profiles use the signed-in human inbox:

```sh
desk user-mentions count
desk user-mentions list --unread
desk user-mentions entity task <id>
desk user-mentions search --q "alex" --types actor
desk user-mentions read <mention_id>
desk user-mentions read-all
```

`read` and `read-all` change shared read state. Use them only when explicitly authorized or after
the requested mention has been handled; inspecting a mention does not authorize clearing it.

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
desk tasks list [--desk-id N] [--status todo|done] [--project-id N] \
    [--week-id N | --inbox] [--recurring-template | --not-recurring-template] \
    [--flagged | --not-flagged] [--sort FIELD] [--sort-order -1|1] \
    [--page N] [--per-page N] [--json]
```

`--week-id` and `--inbox` are mutually exclusive; the API rejects both together.

## Scheduling and owner targeting

Weeks are Monday–Sunday buckets with numeric ids. Resolve dates with `desk weeks`; move with exactly
one destination: `tasks move-week <id> --week-id <id>` or `--inbox`. No timing signal means inbox;
ask when timing is ambiguous.

A non-desk credential targets only a desk returned by `desks list --json` and passes `--desk-id` when
listing or creating desk work. Owner/admin roles may see several desks; a Member may see only its assigned
desk or none. A desk-bound credential is already scoped and cannot act for another desk.

## Write authority

Create, update, move, comment, complete, deadline, and recurrence verbs change shared Rundesk state;
run only the changes the request authorizes. Delete and comment-delete additionally require
`--confirm` and explicit owner authorization.

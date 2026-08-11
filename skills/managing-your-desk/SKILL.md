---
name: managing-your-desk
description: Use when operating Rundesk tasks, inbox work, mentions, or the persistent operational queue for a Desk-owning agent or its owner, including related project work. It supplies the identity-safe desk-cli workflow for prioritizing commitments while project files and GitHub remain implementation truth. Do not use it for bounded specialists without persistent queues or to operate Rundesk agents, gateways, channels, and skill catalogs.
---

# Manage Rundesk work

Use `desk` for the Rundesk API. If `command -v desk` fails or `desk --version` is below 0.4.0,
stop and tell the owner to install or update desk-cli.

## Use the matching identity

```sh
"$RUNDESK_COMMAND" skills profiles desk-cli/managing-your-desk
```

Select a complete named profile matching `$RUNDESK_AGENT` case-insensitively. Use another only when
the request names it or the owner selects it; never fall back to an owner profile. Run commands as
`desk --env-profile <name> …`. Use plain `desk` only when the owner explicitly selected the default.

Before the first write in a turn, run `show --json` with that prefix and confirm the returned desk.
If `show` is forbidden, or the request requires a human/owner profile, read
[profiles and identity](references/profiles-and-identity.md) before continuing.

## Own the desk queue

```sh
desk --env-profile <name> inbox                  # this week, ordered + mentions
desk --env-profile <name> inbox --unscheduled    # backlog
desk --env-profile <name> mentions               # unread desk mentions
desk --env-profile <name> tasks get <id> --json  # full task, comments, and assets
```

Use the inbox instead of rebuilding it from task lists. Treat **This week** as the ordered
commitment and work top-down. This queue belongs to the agent to organize and move toward done; do
not make the Desk owner micromanage routine prioritization. Keep active work in This week and keep
the week ordered.

If This week is empty, inspect both the unscheduled inbox and mentions. Select handleable work and
move it into This week before starting. Add authorized owner-requested work and tasks derived from
owned goals to the queue. Split a large goal into independently completable chunks, each with its own
observable, measurable done criteria and required proof; do not use one indefinite umbrella task as
the execution unit.

Make every active task a compact brief containing:

- the outcome;
- scope and limits;
- observable, measurable definition of done;
- required proof; and
- the current next action, or blocker when one exists.

GitHub or the project repository is the implementation source of truth. Desk tracks operational
commitment, ordering, and concise resumable state; do not copy changing implementation detail into
the task. Read [queue adoption and brief examples](references/queue-adoption.md) only when the owner
authorizes adopting standing queue rules or when a compact brief/comment example is needed. Ordinary
queue operation never edits an agent home or rule file. Bounded specialist agents do not adopt or
own persistent queues.

For a task, read its body, comments, project, week, deadline, and every `assets[]` item. Fetch each
attachment with `asset get <asset_id>`; read text inline and open a binary's short-lived
`download_url` immediately.

Comment sparingly and briefly: record only durable decisions, blockers, handoffs or PRs, exact
resumable state, and exact verification. A desk mention clears when its task receives a reply. Mark
done only after the outcome is delivered and the task criteria plus applicable project definition
of done are verified:

```sh
desk --env-profile <name> tasks comment <id> "<decision, blocker, handoff, state, or proof>"
desk --env-profile <name> tasks complete <id>
```

At every queue review, give each active task an executable next action or explicit blocker. Once it
is no longer active, complete it after proof, re-scope it, or assign a real future week, deadline, or
recurrence; never leave it indefinitely stale.

When an owned item genuinely requires future observation or action, assign a real future week,
deadline, or recurrence instead of writing a vague reminder. Do not defer work that can be completed
now. Contact or mention the Desk owner only for a blocker or missing material scope/authority; make
routine queue decisions yourself.

Without an explicit timing signal, create new work in the backlog. Read
[task verbs](references/task-verbs.md) only for moving work into a week, deadlines, recurrence,
filtering, comment maintenance, or restore.
Read [projects, pages, and assets](references/projects-and-files.md) only when locating or changing
project material or attachments. Read [owner desk management](references/owner-and-desks.md) only
for an authorized owner/admin desk change; agents never mint credentials.

## Guard writes

Reads are safe. Run create, update, move, comment, complete, archive, upload, rename, or recurrence
verbs only when the current request or adopted standing rules authorize that shared-state change.
Hard deletes require `--confirm` and explicit owner authorization. Use `desk help <group> <verb>`
for current flags.

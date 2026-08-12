---
name: handling-assigned-desk-work
description: Use when the owner asks an agent to handle, inspect, continue, or report on named Rundesk Desk tasks without delegating queue management. It supplies a passive, identity-safe workflow for fetching only owner-requested work and posting one compact owner-mentioned handoff. Do not use it to choose work from an inbox, manage task priority or lifecycle, or self-create work.
---

# Handle assigned Desk work

Use `desk` only as the scoped connection to work the owner named. If `command -v desk` fails or
`desk --version` is below 0.5.0, stop and tell the owner to install or update desk-cli.

## Use the matching identity

```sh
"$RUNDESK_COMMAND" skills profiles desk-cli/handling-assigned-desk-work
```

Select one complete named profile matching `$RUNDESK_AGENT` case-insensitively. Use another only
when the owner names it. Run every Desk command as `desk --env-profile <name> …`; never fall back to
an owner/default profile.

Read the Desk owner's exact handle before the terminal handoff; never infer it from a name:

```sh
desk --env-profile <name> show --json
```

Do not use this skill when the same agent holds `managing-your-desk`. The two skills grant conflicting
authority: one is passive assigned-work handling and the other delegates queue management.

## Work only what the owner names

An explicit task ID from the owner authorizes reading and handling that task within its recorded
scope. If the owner explicitly says to handle all assigned Desk tasks, work only the tasks returned
for that request; the instruction creates no standing queue authority. Inbox presence, assignment,
priority, a mention, or discovering related work does not authorize starting it. Listing the inbox
answers what is assigned; it never selects the next task.

```sh
desk --env-profile <name> inbox
desk --env-profile <name> tasks get <id> --json
```

For each named task, read its body, comments, project, week, deadline, and `assets[]`. Fetch relevant
attachments with `asset get <asset_id>`. Use the applicable project and specialist skills to execute
the work; Desk remains the assignment and review surface, not the implementation source of truth.

Never create a task or change its title, body, project, priority, week, deadline, recurrence, status,
or deletion state. Never complete, reopen, restore, or choose another task. The owner reviews and
closes the work.

## Leave one short terminal comment

Post no start, progress, plan, resume, investigation, or narrative-summary comments. When the named
work reaches a terminal handoff, post exactly one compact comment. Prefix it with the exact
`owner.handle` from `desk show --json`; bare `@handle` mentions resolve server-side:

```text
@<owner-handle> Ready for review: <authoritative link>
@<owner-handle> Blocked: <specific decision, authority, or missing input>
@<owner-handle> Verified: <one short proof when no review link exists>
```

Prefer `Ready for review` with the PR, document, report, or other review URL. A link is enough; do not
repeat its title, task scope, implementation summary, test log, or checks already visible there. Use
`Verified` only when no reviewable link exists, and keep it to one check and result. Use `Blocked`
only when work cannot safely advance, naming the one thing needed.

```sh
desk --env-profile <name> tasks comment <id> "@<owner-handle> Ready for review: <url>"
```

If the owner requests corrections, do them against the same task and post one new terminal comment
only when there is materially new review evidence. Never edit or delete old comments to make the
thread look cleaner.

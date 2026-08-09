---
name: managing-your-desk
description: Use when handling Rundesk tasks, inbox work, mentions, or related project material for a desk or its owner. It supplies the identity-safe desk-cli workflow for reading context, managing the operational queue, and completing work with proof. Do not use it to operate Rundesk agents, gateways, channels, or skill catalogs.
---

# Manage Rundesk work

Use `desk` for the Rundesk API. If `command -v desk` fails or `desk --version` is below 0.3.0,
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

## Run the desk queue

```sh
desk --env-profile <name> inbox                 # current-week commitments + mentions
desk --env-profile <name> inbox --unscheduled   # backlog
desk --env-profile <name> mentions              # unread desk mentions
desk --env-profile <name> tasks get <id> --json # full task, comments, and assets
```

Use the inbox instead of rebuilding it from task lists. The current week is committed execution;
`--unscheduled` is backlog. Keep operational task state in Rundesk rather than mirroring it into a
local task file.

For a task, read its body, comments, project, week, deadline, and every `assets[]` item. Fetch each
attachment with `asset get <asset_id>`; read text inline and open a binary's short-lived
`download_url` immediately.

Comment only meaningful state: an outcome, blocker, decision, handoff, or completion proof. A desk
mention clears when its task receives a reply. Complete only after the task criteria and the
applicable project definition of done are proven:

```sh
desk --env-profile <name> tasks comment <id> "<outcome or proof>"
desk --env-profile <name> tasks complete <id>
```

Without an explicit timing signal, create work in the backlog. Read [task verbs](references/task-verbs.md)
only for moving work into a week, deadlines, recurrence, filtering, comment maintenance, or restore.
Read [projects, pages, and assets](references/projects-and-files.md) only when locating or changing
project material or attachments. Read [owner desk management](references/owner-and-desks.md) only
for an authorized owner/admin desk change; agents never mint credentials.

## Guard writes

Reads are safe. Run create, update, move, comment, complete, archive, upload, rename, or recurrence
verbs only when the request authorizes that shared-state change. Hard deletes require `--confirm`
and explicit owner authorization. Use `desk help <group> <verb>` for current flags.

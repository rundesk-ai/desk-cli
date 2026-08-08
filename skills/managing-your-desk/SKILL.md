---
name: managing-your-desk
description: Use when managing Rundesk work for a desk or its owner: tasks or tickets, inbox, mentions, weeks, projects, pages, page search or grep, assets, comments, deadlines, and recurring work. It supplies the profile-safe desk-cli workflow for finding full context, acting with the correct desk or owner identity, and reporting outcomes. Do not use it to install, configure, or operate the Rundesk gateway, agents, channels, or skill catalogs.
---

# Manage Rundesk work

Use `desk` for the Rundesk API. The skill catalog does not install that binary; if
`command -v desk` fails or `desk --version` is below 0.3.0, stop and tell the owner to install or
update desk-cli.

## Select the identity first

```sh
"$RUNDESK_COMMAND" skills profiles desk-cli/managing-your-desk
```

Prefer a complete named profile matching `$RUNDESK_AGENT` case-insensitively. Use another profile
only when the request names it or the owner selects it. If several remain plausible, ask; never
silently fall back to an owner profile. Read [profiles and identity](references/profiles-and-identity.md)
for profile selection, the required account/show probes, or owner-mode targeting.

For the commands below, use `desk --env-profile <name>` for a named Rundesk profile. Use plain
`desk` only when the owner explicitly selected the complete default profile.

## Orient and collect full context

Run `account --json`, then probe `show --json` with the selected command prefix:

- `show` succeeds: desk mode. Start with `inbox`; use `mentions` for unread mentions.
- The account succeeds but `show` is forbidden: human/user mode. Read `workspace.role` from
  `account --json`, then use `desks list --json` to discover only desks visible to that role.
  Owner/admin profiles may target any returned desk; a Member profile may act only through its one
  assigned desk, and a deskless Member has mention access but no task/project desk scope. Use
  `user-mentions list --unread` for the signed-in human's inbox. This is separate from mentions
  addressed directly to the API-token actor.

When given a task or ticket id, run `tasks get <id> --json`. Read its body, comments, project,
week, deadline, and every `assets[]` item. Run `asset get <asset_id>` for each attachment; read text
content inline and immediately download/open a binary's short-lived `download_url`. Do not answer
about attached requirements without opening them.

## Work and report

- In desk mode, `inbox` is the current week's task/mention view; `inbox --unscheduled` is the
  backlog. Do not rebuild that view from task lists.
- In human/user mode, target only a desk returned by `desks list --json`; pass its id to
  desk-targetable task, project, and week commands. Never read or create work against an implicit desk.
- In human/user mode, use `user-mentions count|list|entity|search` to inspect the human inbox. Mark
  one or all mentions read only when the request authorizes that state change.
- Search before fetching when no id is given. Fetch the selected task/page/asset in full before
  editing it.
- Comment the outcome with `tasks comment <id> "…"`, then complete the task only when the requested
  work is actually finished. Commenting is what clears a desk mention; there is no mark-read verb.
- Resolve explicit timing through `weeks`; without a timing signal create in the inbox. Ask rather
  than guess when a batch could span weeks.

Read [task verbs](references/task-verbs.md) for scheduling, deadlines, recurrence, filtering,
comments, moves, restores, and write authority. Read [projects, pages, and assets](references/projects-and-files.md)
when locating or changing project material, using page search/grep/patch, or replacing an asset.
Read [owner desk management](references/owner-and-desks.md) before creating, assigning, retiring,
or deleting desks. Never mint credentials from an agent turn; ask the owner to run that credential
operation locally.

## Guard writes

Reads are safe. Run create/update/patch/move/comment/complete/archive/upload/rename/recurrence
verbs only when the request authorizes the corresponding change. Hard deletes require `--confirm`
and explicit owner authorization. Completing is how work finishes; deleting is not. Use
`desk help <group> <verb>` for the exact current flags.

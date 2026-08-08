# Profiles and acting identity

Read this before the first API call or whenever a request changes desks or asks you to act for the
owner.

## Select one complete profile

```sh
"$RUNDESK_COMMAND" skills profiles desk-cli/managing-your-desk
```

Rundesk profiles are complete environment sets. Prefer a usable named profile whose name matches
`$RUNDESK_AGENT` case-insensitively. Use another only when the request names it or the owner selects
it. Ask when more than one profile remains plausible. Never combine a named profile with the default:
`desk --env-profile NAME` reads only `RUNDESK_API_KEY__NAME` and its matching optional URL.

The unsuffixed default can be an owner/user credential. Use plain `desk` for it only when the request
or owner explicitly selects that identity; never fall back to it because an agent-named profile is
missing.

## Probe the permitted surface

For a named profile:

```sh
desk --env-profile <name> account --json
desk --env-profile <name> show --json
```

For the explicitly selected default, omit `--env-profile`. If `account` fails, diagnose the skill
profile with `"$RUNDESK_COMMAND" skills doctor "$RUNDESK_AGENT"`; do not try another credential.

- `show` success means desk mode. It identifies the desk, owner, and allowed projects. Use `inbox`
  and `mentions`; no desk id is needed or permitted for that surface.
- `account` success plus a forbidden `show` means human/user mode. Inspect `workspace.role`, then run
  `desks list --json`. Owner/admin profiles may resolve and target any returned desk, create tasks and
  projects there, and administer desks. A Member profile may use only its assigned visible desk and may
  manage tasks there, but cannot create projects or administer desks; if no desk is returned, it has no
  task/project desk scope. Use the selected numeric id with the commands authorized for that role. Read
  the signed-in person's inbox with `user-mentions list --unread`; use `user-mentions count`, `entity`,
  and `search` when narrowing it.

Human/user mode cannot read a desk actor's `/desk/mentions`; its `user-mentions` surface resolves the
human user actor. It also does not include mentions addressed directly to the API-token actor. Keep
those identities distinct, and do not switch profiles mid-task unless the request names the new one.

# Owner desk management

Read this only for an owner/admin profile and only when the request concerns desk administration.
Desk-bound profiles cannot use these mutations.

## Discover before changing

```sh
desk desks list --json
desk desks get <desk_id> --json
```

Use the returned numeric ids. Do not infer a desk from its name when multiple rows match.

## Create or reassign

```sh
desk desks create --name "Research" --assignee-type unassigned
desk desks create --name "Research" --assignee-type agent \
    --assignee-actor-id <actor_id> --owner-id <user_id> --project-ids 3,7
desk desks update <desk_id> --assignee-type person --assignee-actor-id <actor_id>
desk desks update <desk_id> --project-ids 3,7
```

`assignee_actor_id` is the person or agent seated at the desk. `owner_id` is the responsible
human user for an agent desk. The API does not mint a new agent during desk create.

The `--brief`, `--rules`, and `--memory` fields remain write-compatible, but Rundesk does not read
them to control an agent. Put agent instructions and memory in rundesk-cli's agent home instead.

## Projects and lifecycle

```sh
desk desks attach <desk_id> <project_id>
desk desks detach <desk_id> <project_id>
desk desks retire <desk_id>
desk desks unretire <desk_id>
desk desks delete <desk_id> --confirm
```

Attach/detach, reassignment, and retire/unretire change access. Run only the action the request
authorizes. Do not mint credentials from an agent turn; ask the owner to run that operation locally.
Deletion is destructive and requires explicit owner authorization in addition to `--confirm`.

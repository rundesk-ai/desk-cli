# Projects, pages, and files

`desk help <command>` is generated from the command and is authoritative for exact flags.
This file is the intent index it is not.

## Finding something when you have no id

Every read takes a numeric id. When you have a title or a phrase instead:

```sh
desk projects list --search "…"                          # → project id
desk page search --q "…" --project-type professional     # searches page CONTENT
desk asset search --q "…"                                # searches FILENAMES, not content
desk tasks list --project-id N                           # → task id
```

`page search` reads the body of pages; `asset search` only matches filenames. Looking for a
phrase inside an attached document, neither will find it — open the asset and read it.

## Projects

```sh
desk projects list [--search S] [--type professional|personal] [--archived] [--json]
desk projects get <id>
```

`desk show` lists the projects your desk covers. A project outside that set is not yours to
act in.

## Pages

Pages are a project's written material — briefs, notes, specs.

```sh
desk page list <project_id> [--role R] [--body]     # --body inlines content, else titles only
desk page get <project_id> <page_id>
desk page update <project_id> <page_id> --body "…" | --body-file path
desk page patch <project_id> <page_id> --mode replace --old-str "…" --new-str "…"
```

Prefer `page patch` over `page update` when changing part of a page: `update` replaces the
whole body, so a concurrent edit by somebody else is silently overwritten.

## Files

```sh
desk asset get <asset_id>                    # text → content inline; binary → download_url
desk asset list-project <project_id>
desk asset list-page <project_id> <page_id>
desk asset upload-task <task_id> <file>
```

A `download_url` is presigned and short-lived — fetch it immediately, do not store it.

Uploads exist for project and page scope too (`upload-project`, `upload-page`), as do
`rename-*` and `delete-*` per scope. Deletes need `--confirm`.

# Projects, pages, and files

`desk help <command>` is generated from the command and is authoritative for exact flags.
This file is the intent index it is not.

## Finding something when you have no id

Every read takes a numeric id. When you have a title or a phrase instead:

```sh
desk projects list --search "…"                          # → project id
desk page search --q "…" --project-type professional     # searches page CONTENT
desk page grep <project_id> --pattern "…"                 # exact regex follow-up
desk asset list --filename "…"                            # every asset parent type
desk asset search --q "…"                                # searches FILENAMES, not content
desk tasks list --project-id N                           # → task id
```

`page search` reads the body of pages; `asset search` only matches filenames. Looking for a
phrase inside an attached document, neither will find it — open the asset and read it.

## Projects

```sh
desk projects list [--desk-id N] [--search S] [--type professional|personal] \
    [--archived] [--sort FIELD] [--sort-order -1|1] [--page N] [--per-page N] [--json]
desk projects get <id>
desk projects create --name "…" [--desk-id N]
desk projects update <id> [--name "…"] [--index-pages | --no-index-pages]
desk projects archive|unarchive <id>
```

`desk show` lists the projects your desk covers. A project outside that set is not yours to
act in. New projects always begin with page indexing enabled. The retained `--hidden` flag is
retired and returns a usage error instead of pretending the project changed.

## Pages

Pages are a project's written material — briefs, notes, specs.

```sh
desk page list <project_id> [--search S] [--role R] [--meta JSON] \
    [--body] [--body-chars N] [--page N] [--per-page N]
desk page get <project_id> <page_id>
desk page update <project_id> <page_id> --body "…" | --body-file path
desk page update <project_id> <page_id> --parent N | --top-level [--sort-order N]
desk page grep <project_id> --pattern "…" [--page-id N] [--context N]
desk page patch <project_id> <page_id> --mode replace --old-str "…" --new-str "…"
desk page reorder <project_id> <sibling_ids...> [--parent N]
desk page reorder <project_id> --scopes '[{"parent_page_id":null,"ids":[1,2]}]'
```

Use `page search` first to discover the right project/page. Use `page grep` only after that when you
need every literal occurrence or an exact `old_str` anchor. Fetch the full page, then prefer `page
patch` over `page update` when changing part of it: `update` replaces the whole body and can overwrite
a concurrent edit.

## Files

```sh
desk asset get <asset_id>                    # text → content inline; binary → download_url
desk asset list [--filename S] [--task-id N | --project-id N | --page-id N] [--json]
desk asset list-project <project_id>
desk asset list-page <project_id> <page_id>
desk asset upload-task <task_id> <file>
desk asset update <asset_id> [--filename NAME] [--content TEXT | --content-file PATH] \
    [--encoding utf8|base64]
```

A `download_url` is presigned and short-lived — fetch it immediately, do not store it.

Uploads exist for project and page scope too (`upload-project`, `upload-page`), as do
`rename-*` and `delete-*` per scope. Deletes need `--confirm`.

`asset update` preserves the existing extension. Use `--encoding base64` for binary replacement;
with `--content-file`, desk-cli encodes the bytes. Fetch the updated asset again to verify content.

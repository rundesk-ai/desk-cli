#!/usr/bin/env python3
"""Thin CLI over the Rundesk REST client for direct calls and debugging.

Usage:
  desk [--env-file PATH] <command> ...
  desk account [--json]
  desk changelog [--limit N] [--all]
  desk projects list [--search S] [--type professional|personal] [--archived] [--json]
  desk projects get <id> [--json]
  desk projects create --name N [--short-code C] [--color #hex] [--type T]
  desk projects update <id> [--name ...] | archive <id> | unarchive <id> | delete <id> --confirm
  desk page list <project_id> [--role R] [--meta JSON] [--body]
  desk page get <project_id> <page_id> [--frontmatter-only]
  desk page create <project_id> (--body TEXT | --body-file F) [--parent N] [--sort-order N]
  desk page update <project_id> <page_id> [--body-file F] [--frontmatter F] [--description D]
  desk page patch <project_id> <page_id> --mode replace|append|prepend [--old-str ..] [--new-str ..] [--content ..]
  desk page delete <project_id> <page_id> --confirm
  desk page search --q Q --project-type professional|personal [--project-id N] [--limit N]
  desk tasks list [--status todo|done] [--project-id N] [--week-id N] [--inbox] [--json]
  desk tasks get <id> | create --title T [...] | update <id> [...] | complete|uncomplete|restore <id>
  desk tasks comments <id> | comment <id> <body> | comment-edit <id> <comment_id> <body> | comment-delete <id> <comment_id> --confirm
  desk tasks delete <id> --confirm | move-week <id> [--week-id N|--inbox] | move-project <id> [--project-id N|--none]
  desk tasks deadline-set <id> --due-at ISO [--all-day] | deadline-remove <id>
  desk tasks recur-set|recur-update <id> --frequency F --interval N --end-type T [...] | recur-remove <id>
  desk week [--date YYYY-MM-DD] [--json]      weeks [--past N] [--future N] [--json]
  desk asset get <id> | search --q Q | list-project <pid> | list-page <pid> <page> | upload-* | rename-* | delete-*
  desk desks list|get|create|update|delete|retire|unretire|attach|detach|mint-key

Inputs:
  Reads RUNDESK_BASE_URL and RUNDESK_API_KEY from process env / local .env
  via client.py's dotenv-reuse loader (an already-set env var always wins). One
  key = one Rundesk workspace/desk actor (a workspace is provisioned per desk),
  so there is no profile selection. The KEY decides the surface: only an owner
  key may use the `desks` MANAGEMENT verbs (a desk-bound key gets 403); `desks
  list|get` are read-only discovery any caller may use. The desk's own surface
  (`show`/`inbox`/`mentions`) lives on the installed `desk` CLI in cli.py.

Outputs:
  Compact pipe-delimited text where the API wires ?format=text; pages/desk JSON
  are JSON. Pass --json to force raw parsed payload where text mode exists. On a
  RundeskError the CLI prints one stderr line and exits with the mapped code
  (0 ok · 2 no key/usage · 3 401 · 4 403 · 5 404 · 6 422 · 7 network). Mutations
  that hard-delete require --confirm.

This is a debugging seam; programmatic callers import client.RundeskClient.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from client import (  # noqa: E402
    RundeskClient,
    RundeskError,
)


def _emit(value, as_json: bool = False) -> None:
    """Print text as-is, or pretty JSON for any non-str payload / when --json."""
    if as_json or not isinstance(value, str):
        print(json.dumps(value, indent=2, sort_keys=True, default=str))
    else:
        print(value.rstrip("\n"))


def _wants_json(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "json", False))


def _read_body(args: argparse.Namespace) -> str | None:
    """Resolve a body from --body or --body-file (file wins if given)."""
    body_file = getattr(args, "body_file", None)
    if body_file:
        try:
            return Path(body_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise RundeskError("usage", f"--body-file not readable: {body_file}: {exc}") from exc
    return getattr(args, "body", None)


def _parse_id_list(value: str | None) -> list[int] | None:
    """Parse a comma-separated `--project-ids` string into a list of ints (the
    API field is an int array). None when the flag is omitted."""
    if value is None:
        return None
    try:
        ids = [int(item) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise RundeskError("usage", f"--project-ids must be comma-separated integers: {exc}") from exc
    # An empty/blank value is treated as "not provided" (omitted), never as an
    # empty array — so it can't silently detach every project from the desk.
    return ids or None


# ── Account / changelog ──────────────────────────────────────────────────────
def cmd_account(args, client: RundeskClient) -> int:
    _emit(client.get_account(as_text=not _wants_json(args)), _wants_json(args))
    return 0


def cmd_changelog(args, client: RundeskClient) -> int:
    _emit(client.get_changelog(limit=args.limit, all=args.all), True)
    return 0


# ── Projects ─────────────────────────────────────────────────────────────────
def cmd_projects(args, client: RundeskClient) -> int:
    action = args.projects_action
    if action == "list":
        is_archived = 1 if args.archived else None
        _emit(
            client.list_projects(
                search=args.search, type=args.type, is_archived=is_archived, as_text=not _wants_json(args)
            ),
            _wants_json(args),
        )
    elif action == "get":
        _emit(client.get_project(args.project_id, as_text=not _wants_json(args)), _wants_json(args))
    elif action == "create":
        _emit(
            client.create_project(
                name=args.name, short_code=args.short_code, color=args.color, type=args.type,
                is_hidden=args.hidden, index_pages=args.index_pages,
            ),
            True,
        )
    elif action == "update":
        _emit(
            client.update_project(
                args.project_id, name=args.name, short_code=args.short_code, color=args.color,
                type=args.type, is_hidden=args.hidden, index_pages=args.index_pages,
            ),
            True,
        )
    elif action == "archive":
        _emit(client.archive_project(args.project_id), True)
    elif action == "unarchive":
        _emit(client.unarchive_project(args.project_id), True)
    elif action == "delete":
        client.delete_project(args.project_id)
        print(f"deleted project {args.project_id}")
    return 0


# ── Project pages ────────────────────────────────────────────────────────────
def cmd_page(args, client: RundeskClient) -> int:
    action = args.page_action
    if action == "list":
        meta = None
        if args.meta:
            try:
                meta = json.loads(args.meta)
            except json.JSONDecodeError as exc:
                raise RundeskError("usage", f"--meta is not valid JSON: {exc}") from exc
        elif args.role:
            meta = {"page_role": args.role}
        _emit(client.get_pages(args.project_id, meta=meta, include_body=args.body), True)
    elif action == "get":
        _emit(client.get_page(args.project_id, args.page_id, frontmatter_only=args.frontmatter_only), True)
    elif action == "create":
        _emit(
            client.create_page(
                args.project_id, _read_body(args), parent_page_id=args.parent, sort_order=args.sort_order
            ),
            True,
        )
    elif action == "update":
        _emit(
            client.update_page(
                args.project_id, args.page_id, body=_read_body(args),
                frontmatter=args.frontmatter, description=args.description,
            ),
            True,
        )
    elif action == "patch":
        _emit(
            client.patch_page(
                args.project_id, args.page_id, mode=args.mode, old_str=args.old_str,
                new_str=args.new_str, content=args.content, description=args.description,
            ),
            True,
        )
    elif action == "delete":
        client.delete_page(args.project_id, args.page_id)
        print(f"deleted page {args.page_id}")
    elif action == "reorder":
        _emit(client.reorder_pages(args.project_id, [int(i) for i in args.ids]), True)
    elif action == "search":
        _emit(
            client.search_pages(
                q=args.q, project_type=args.project_type, project_id=args.project_id, limit=args.limit
            ),
            True,
        )
    return 0


# ── Tasks ────────────────────────────────────────────────────────────────────
def cmd_tasks(args, client: RundeskClient) -> int:
    action = args.tasks_action
    if action == "list":
        _emit(
            client.list_tasks(
                status=args.status, project_id=args.project_id, task_week_id=args.week_id,
                inbox=1 if args.inbox else None, as_text=not _wants_json(args),
            ),
            _wants_json(args),
        )
    elif action == "get":
        _emit(client.get_task(args.task_id, as_text=not _wants_json(args)), _wants_json(args))
    elif action == "create":
        _emit(
            client.create_task(
                title=args.title, body=args.body, project_id=args.project_id, task_week_id=args.week_id
            ),
            True,
        )
    elif action == "update":
        _emit(
            client.update_task(
                args.task_id, title=args.title, body=args.body, project_id=args.project_id
            ),
            True,
        )
    elif action == "comments":
        _emit(client.list_task_comments(args.task_id), True)
    elif action == "comment":
        _emit(client.create_task_comment(args.task_id, args.body), True)
    elif action == "comment-edit":
        _emit(client.update_task_comment(args.task_id, args.comment_id, args.body), True)
    elif action == "comment-delete":
        client.delete_task_comment(args.task_id, args.comment_id)
        print(f"deleted comment {args.comment_id} on task {args.task_id}")
    elif action == "complete":
        _emit(client.complete_task(args.task_id), True)
    elif action == "uncomplete":
        _emit(client.uncomplete_task(args.task_id), True)
    elif action == "restore":
        _emit(client.restore_task(args.task_id), True)
    elif action == "delete":
        client.delete_task(args.task_id)
        print(f"deleted task {args.task_id}")
    elif action == "move-week":
        week_id = None if args.inbox else args.week_id
        _emit(client.move_task_week(args.task_id, week_id), True)
    elif action == "move-project":
        project_id = None if args.none else args.project_id
        _emit(client.move_task_project(args.task_id, project_id), True)
    elif action == "deadline-set":
        is_all_day = True if args.all_day else None
        _emit(client.set_task_deadline(args.task_id, due_at=args.due_at, is_all_day_due=is_all_day), True)
    elif action == "deadline-remove":
        client.remove_task_deadline(args.task_id)
        print(f"removed deadline on task {args.task_id}")
    elif action in {"recur-set", "recur-update"}:
        days = [int(d) for d in args.days_of_week] if args.days_of_week else None
        fn = client.set_task_recurring if action == "recur-set" else client.update_task_recurring
        _emit(
            fn(
                args.task_id, frequency=args.frequency, interval=args.interval, end_type=args.end_type,
                days_of_week=days, day_of_month=args.day_of_month, end_count=args.end_count,
                end_date=args.end_date, start_at=args.start_at, due_time=args.due_time,
                due_weekday=args.due_weekday,
            ),
            True,
        )
    elif action == "recur-remove":
        client.remove_task_recurring(args.task_id)
        print(f"removed recurring on task {args.task_id}")
    return 0


# ── Weeks ────────────────────────────────────────────────────────────────────
def cmd_week(args, client: RundeskClient) -> int:
    _emit(client.get_week(date=args.date, as_text=not _wants_json(args)), _wants_json(args))
    return 0


def cmd_weeks(args, client: RundeskClient) -> int:
    _emit(client.list_weeks(past=args.past, future=args.future, as_text=not _wants_json(args)), _wants_json(args))
    return 0


# ── Assets ───────────────────────────────────────────────────────────────────
def cmd_asset(args, client: RundeskClient) -> int:
    action = args.asset_action
    if action == "get":
        _emit(client.get_asset(args.asset_id), True)
    elif action == "search":
        _emit(client.search_project_assets(q=args.q, sort=args.sort, limit=args.limit), True)
    elif action == "list-project":
        _emit(client.list_project_assets(args.project_id, search=args.search, sort=args.sort, page=args.page), True)
    elif action == "list-page":
        _emit(
            client.list_page_assets(args.project_id, args.page_id, search=args.search, sort=args.sort, page=args.page),
            True,
        )
    elif action == "upload-task":
        _emit(client.upload_task_asset(args.task_id, args.file), True)
    elif action == "upload-project":
        _emit(client.upload_project_asset(args.project_id, args.file), True)
    elif action == "upload-page":
        _emit(client.upload_page_asset(args.project_id, args.page_id, args.file), True)
    elif action == "rename-task":
        _emit(client.rename_task_asset(args.task_id, args.asset_id, args.filename), True)
    elif action == "rename-project":
        _emit(client.rename_project_asset(args.project_id, args.asset_id, args.filename), True)
    elif action == "rename-page":
        _emit(client.rename_page_asset(args.project_id, args.page_id, args.asset_id, args.filename), True)
    elif action == "delete-task":
        _emit(client.delete_task_asset(args.task_id, args.asset_id), True)
    elif action == "delete-project":
        _emit(client.delete_project_asset(args.project_id, args.asset_id), True)
    elif action == "delete-page":
        _emit(client.delete_page_asset(args.project_id, args.page_id, args.asset_id), True)
    return 0


# ── Owner desk management ────────────────────────────────────────────────────
def cmd_desks(args, client: RundeskClient) -> int:
    action = args.desks_action
    if action == "list":
        _emit(
            client.list_desks(include_retired=args.include_retired, as_text=not _wants_json(args)),
            _wants_json(args),
        )
    elif action == "get":
        _emit(client.get_desk_by_id(args.desk_id, as_text=not _wants_json(args)), _wants_json(args))
    elif action == "create":
        _emit(
            client.create_desk(
                name=args.name, owner_type=args.owner_type, owner_actor_id=args.owner_actor_id,
                project_ids=_parse_id_list(args.project_ids),
            ),
            True,
        )
    elif action == "update":
        _emit(
            client.update_desk(
                args.desk_id, name=args.name, owner_type=args.owner_type,
                owner_actor_id=args.owner_actor_id,
                project_ids=_parse_id_list(args.project_ids),
            ),
            True,
        )
    elif action == "delete":
        client.delete_desk(args.desk_id)
        print(f"deleted desk {args.desk_id}")
    elif action == "retire":
        _emit(client.retire_desk(args.desk_id), True)
    elif action == "unretire":
        _emit(client.unretire_desk(args.desk_id), True)
    elif action == "attach":
        _emit(client.attach_project(args.desk_id, args.project_id), True)
    elif action == "detach":
        _emit(client.detach_project(args.desk_id, args.project_id), True)
    elif action == "mint-key":
        _emit(client.create_desk_key(args.desk_id, name=args.name, expires_at=args.expires_at), True)
    return 0


def _confirm_or_abort(args) -> None:
    if not getattr(args, "confirm", False):
        raise RundeskError("usage", "This is a hard delete. Re-run with --confirm to proceed.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Direct/debug CLI over the Rundesk REST client.")
    parser.add_argument("--env-file", help="Path to dotenv file. Defaults to the local .env.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_json(p):
        p.add_argument("--json", action="store_true", help="Print raw JSON instead of text rows.")

    # account / changelog
    p = sub.add_parser("account", help="Show the account record.")
    add_json(p)
    p.set_defaults(handler=cmd_account)

    p = sub.add_parser("changelog", help="Show release notes (newest first).")
    p.add_argument("--limit", type=int, help="1–50, default 3.")
    p.add_argument("--all", action="store_true", help="Return every entry.")
    p.set_defaults(handler=cmd_changelog)

    # projects
    projects = sub.add_parser("projects", help="Projects (list/get/create/update/archive/delete).")
    pj = projects.add_subparsers(dest="projects_action", required=True)
    pl = pj.add_parser("list", help="List projects.")
    pl.add_argument("--search", help="Name-scoped search filter.")
    pl.add_argument("--type", choices=["professional", "personal"], help="Filter by type.")
    pl.add_argument("--archived", action="store_true", help="Only archived projects.")
    add_json(pl)
    pg = pj.add_parser("get", help="Single project + asset list.")
    pg.add_argument("project_id")
    add_json(pg)

    def add_project_fields(sp):
        sp.add_argument("--short-code", dest="short_code", help="≤20 chars.")
        sp.add_argument("--color", help="Hex, e.g. #ff0000.")
        sp.add_argument("--type", choices=["professional", "personal"], help="Project type.")
        sp.add_argument("--hidden", action="store_true", default=None, help="Mark hidden.")
        sp.add_argument("--index-pages", dest="index_pages", action="store_true", default=None, help="Enable indexing.")

    pc = pj.add_parser("create", help="Create a project (auto-seeds a starter page).")
    pc.add_argument("--name", required=True, help="≤255 chars.")
    add_project_fields(pc)
    pu = pj.add_parser("update", help="Partial update of a project.")
    pu.add_argument("project_id")
    pu.add_argument("--name", help="≤255 chars.")
    add_project_fields(pu)
    for name in ("archive", "unarchive"):
        sp = pj.add_parser(name, help=f"{name.capitalize()} a project.")
        sp.add_argument("project_id")
    pd = pj.add_parser("delete", help="PERMANENT delete (requires --confirm).")
    pd.add_argument("project_id")
    pd.add_argument("--confirm", action="store_true")
    projects.set_defaults(handler=cmd_projects)

    # pages
    page = sub.add_parser("page", help="Project pages (JSON-only endpoints).")
    pa = page.add_subparsers(dest="page_action", required=True)
    pll = pa.add_parser("list", help="List pages.")
    pll.add_argument("project_id")
    pll.add_argument("--role", help="Filter by frontmatter page_role.")
    pll.add_argument("--meta", help="Frontmatter containment filter as JSON.")
    pll.add_argument("--body", action="store_true", help="Include body_preview.")
    pgg = pa.add_parser("get", help="Single page (full body + children).")
    pgg.add_argument("project_id")
    pgg.add_argument("page_id")
    pgg.add_argument("--frontmatter-only", dest="frontmatter_only", action="store_true")
    pcc = pa.add_parser("create", help="Create a page.")
    pcc.add_argument("project_id")
    pcc.add_argument("--body", help="Page body markdown.")
    pcc.add_argument("--body-file", dest="body_file", help="Read body from a file.")
    pcc.add_argument("--parent", help="parent_page_id for nesting.")
    pcc.add_argument("--sort-order", dest="sort_order", type=int)
    puu = pa.add_parser("update", help="Full page update (body / frontmatter).")
    puu.add_argument("project_id")
    puu.add_argument("page_id")
    puu.add_argument("--body", help="Body markdown.")
    puu.add_argument("--body-file", dest="body_file", help="Read body from a file.")
    puu.add_argument("--frontmatter", help="YAML (no --- fences); '' clears.")
    puu.add_argument("--description", help="Version-row label (≤255).")
    ppp = pa.add_parser("patch", help="Surgical page edit.")
    ppp.add_argument("project_id")
    ppp.add_argument("page_id")
    ppp.add_argument("--mode", required=True, choices=["replace", "append", "prepend"])
    ppp.add_argument("--old-str", dest="old_str")
    ppp.add_argument("--new-str", dest="new_str")
    ppp.add_argument("--content")
    ppp.add_argument("--description")
    pdd = pa.add_parser("delete", help="Delete a page (requires --confirm).")
    pdd.add_argument("project_id")
    pdd.add_argument("page_id")
    pdd.add_argument("--confirm", action="store_true")
    prr = pa.add_parser("reorder", help="Reorder all pages.")
    prr.add_argument("project_id")
    prr.add_argument("ids", nargs="+", help="Page ids in desired order.")
    pss = pa.add_parser("search", help="Content search across pages.")
    pss.add_argument("--q", required=True, help="Free-text query (3–500 chars).")
    pss.add_argument("--project-type", dest="project_type", required=True, choices=["professional", "personal"])
    pss.add_argument("--project-id", dest="project_id", help="Narrow to one project.")
    pss.add_argument("--limit", type=int, help="1–25, default 5.")
    page.set_defaults(handler=cmd_page)

    # tasks
    tasks = sub.add_parser("tasks", help="Tasks (full CRUD + deadline/recurring/move).")
    ta = tasks.add_subparsers(dest="tasks_action", required=True)
    tl = ta.add_parser("list", help="List tasks.")
    tl.add_argument("--status", choices=["todo", "done"])
    tl.add_argument("--project-id", dest="project_id")
    tl.add_argument("--week-id", dest="week_id")
    tl.add_argument("--inbox", action="store_true", help="Only the desk's no-week inbox tasks (excludes --week-id; API rejects both).")
    add_json(tl)
    tg = ta.add_parser("get", help="Single task.")
    tg.add_argument("task_id")
    add_json(tg)
    tc = ta.add_parser("create", help="Create a task.")
    tc.add_argument("--title", required=True, help="≤500 chars.")
    tc.add_argument("--body")
    tc.add_argument("--project-id", dest="project_id")
    tc.add_argument("--week-id", dest="week_id", help="Omit for inbox.")
    tu = ta.add_parser("update", help="Partial update (week moves go through move-week).")
    tu.add_argument("task_id")
    tu.add_argument("--title")
    tu.add_argument("--body")
    tu.add_argument("--project-id", dest="project_id")
    tcl = ta.add_parser("comments", help="List a task's comment timeline (JSON).")
    tcl.add_argument("task_id")
    tcm = ta.add_parser("comment", help="Post a comment on a task.")
    tcm.add_argument("task_id")
    tcm.add_argument("body")
    tce = ta.add_parser("comment-edit", help="Edit a comment (author-only).")
    tce.add_argument("task_id")
    tce.add_argument("comment_id")
    tce.add_argument("body")
    tcd = ta.add_parser("comment-delete", help="Delete a comment, author-only (requires --confirm).")
    tcd.add_argument("task_id")
    tcd.add_argument("comment_id")
    tcd.add_argument("--confirm", action="store_true")
    for name in ("complete", "uncomplete", "restore"):
        sp = ta.add_parser(name, help=f"{name.capitalize()} a task.")
        sp.add_argument("task_id")
    td = ta.add_parser("delete", help="Soft delete (requires --confirm).")
    td.add_argument("task_id")
    td.add_argument("--confirm", action="store_true")
    tmw = ta.add_parser("move-week", help="Move to a week (or --inbox).")
    tmw.add_argument("task_id")
    tmw.add_argument("--week-id", dest="week_id")
    tmw.add_argument("--inbox", action="store_true", help="Move to inbox (null week).")
    tmp = ta.add_parser("move-project", help="Move to a project (or --none).")
    tmp.add_argument("task_id")
    tmp.add_argument("--project-id", dest="project_id")
    tmp.add_argument("--none", action="store_true", help="Uncategorized (null project).")
    tds = ta.add_parser("deadline-set", help="Set/update a deadline.")
    tds.add_argument("task_id")
    tds.add_argument("--due-at", dest="due_at", required=True, help="ISO-8601 UTC.")
    tds.add_argument("--all-day", dest="all_day", action="store_true")
    tdr = ta.add_parser("deadline-remove", help="Clear the deadline.")
    tdr.add_argument("task_id")
    for name in ("recur-set", "recur-update"):
        sp = ta.add_parser(name, help="Set/update recurrence.")
        sp.add_argument("task_id")
        sp.add_argument("--frequency", required=True, choices=["daily", "weekly", "monthly"])
        sp.add_argument("--interval", required=True, type=int, help="1–52.")
        sp.add_argument("--end-type", dest="end_type", required=True, choices=["never", "count", "date"])
        sp.add_argument("--days-of-week", dest="days_of_week", nargs="+", help="1–7 (weekly).")
        sp.add_argument("--day-of-month", dest="day_of_month", type=int, help="1–31 (monthly).")
        sp.add_argument("--end-count", dest="end_count", type=int)
        sp.add_argument("--end-date", dest="end_date", help="YYYY-MM-DD.")
        sp.add_argument("--start-at", dest="start_at", help="YYYY-MM-DD.")
        sp.add_argument("--due-time", dest="due_time", help="HH:MM (15-min increments).")
        sp.add_argument("--due-weekday", dest="due_weekday", type=int, help="1–7 ISO.")
    trr = ta.add_parser("recur-remove", help="Strip recurring status.")
    trr.add_argument("task_id")
    tasks.set_defaults(handler=cmd_tasks)

    # weeks
    week = sub.add_parser("week", help="A week's tasks grouped by project.")
    week.add_argument("--date", help="Week start YYYY-MM-DD. Omit for current.")
    add_json(week)
    week.set_defaults(handler=cmd_week)
    weeks = sub.add_parser("weeks", help="List weeks with completion stats.")
    weeks.add_argument("--past", type=int)
    weeks.add_argument("--future", type=int)
    add_json(weeks)
    weeks.set_defaults(handler=cmd_weeks)

    # assets
    asset = sub.add_parser("asset", help="Polymorphic asset reads/writes.")
    aa = asset.add_subparsers(dest="asset_action", required=True)
    ag = aa.add_parser("get", help="Fetch an asset by id.")
    ag.add_argument("asset_id")
    asr = aa.add_parser("search", help="Filename search across project files.")
    asr.add_argument("--q", required=True)
    asr.add_argument("--sort")
    asr.add_argument("--limit", type=int)
    alp = aa.add_parser("list-project", help="List a project's assets.")
    alp.add_argument("project_id")
    alp.add_argument("--search")
    alp.add_argument("--sort")
    alp.add_argument("--page", type=int)
    alg = aa.add_parser("list-page", help="List a page's assets.")
    alg.add_argument("project_id")
    alg.add_argument("page_id")
    alg.add_argument("--search")
    alg.add_argument("--sort")
    alg.add_argument("--page", type=int)
    aut = aa.add_parser("upload-task", help="Upload a file to a task.")
    aut.add_argument("task_id")
    aut.add_argument("file")
    aup = aa.add_parser("upload-project", help="Upload a file to a project.")
    aup.add_argument("project_id")
    aup.add_argument("file")
    aug = aa.add_parser("upload-page", help="Upload a file to a page.")
    aug.add_argument("project_id")
    aug.add_argument("page_id")
    aug.add_argument("file")
    art = aa.add_parser("rename-task", help="Rename a task asset.")
    art.add_argument("task_id")
    art.add_argument("asset_id")
    art.add_argument("filename")
    arp = aa.add_parser("rename-project", help="Rename a project asset.")
    arp.add_argument("project_id")
    arp.add_argument("asset_id")
    arp.add_argument("filename")
    arg = aa.add_parser("rename-page", help="Rename a page asset.")
    arg.add_argument("project_id")
    arg.add_argument("page_id")
    arg.add_argument("asset_id")
    arg.add_argument("filename")
    adt = aa.add_parser("delete-task", help="PERMANENT delete of a task asset, DB + S3 (requires --confirm).")
    adt.add_argument("task_id")
    adt.add_argument("asset_id")
    adt.add_argument("--confirm", action="store_true")
    adp = aa.add_parser("delete-project", help="PERMANENT delete of a project asset, DB + S3 (requires --confirm).")
    adp.add_argument("project_id")
    adp.add_argument("asset_id")
    adp.add_argument("--confirm", action="store_true")
    adg = aa.add_parser("delete-page", help="PERMANENT delete of a page asset, DB + S3 (requires --confirm).")
    adg.add_argument("project_id")
    adg.add_argument("page_id")
    adg.add_argument("asset_id")
    adg.add_argument("--confirm", action="store_true")
    asset.set_defaults(handler=cmd_asset)

    # desk discovery (read) + owner desk management
    desks = sub.add_parser("desks", help="Desk discovery (read) + owner desk management.")
    ds = desks.add_subparsers(dest="desks_action", required=True)
    dsl = ds.add_parser("list", help="List the desks you may view.")
    dsl.add_argument("--include-retired", dest="include_retired", action="store_true")
    add_json(dsl)
    dsg = ds.add_parser("get", help="Single desk + its projects.")
    dsg.add_argument("desk_id")
    add_json(dsg)

    def add_desk_fields(sp):
        sp.add_argument("--owner-type", dest="owner_type", choices=["person", "agent", "unassigned"])
        sp.add_argument("--owner-actor-id", dest="owner_actor_id", type=int, help="Existing actor to own the desk.")
        sp.add_argument("--project-ids", dest="project_ids", help="Comma-separated project ids (display order).")

    dsc = ds.add_parser("create", help="Create a desk.")
    dsc.add_argument("--name", required=True)
    add_desk_fields(dsc)
    dsu = ds.add_parser("update", help="Partial update of a desk.")
    dsu.add_argument("desk_id")
    dsu.add_argument("--name")
    add_desk_fields(dsu)
    dsd = ds.add_parser("delete", help="Delete a desk (requires --confirm).")
    dsd.add_argument("desk_id")
    dsd.add_argument("--confirm", action="store_true")
    for name in ("retire", "unretire"):
        sp = ds.add_parser(name, help=f"{name.capitalize()} a desk.")
        sp.add_argument("desk_id")
    dsa = ds.add_parser("attach", help="Attach a project to a desk.")
    dsa.add_argument("desk_id")
    dsa.add_argument("project_id")
    dsx = ds.add_parser("detach", help="Detach a project from a desk.")
    dsx.add_argument("desk_id")
    dsx.add_argument("project_id")
    dsk = ds.add_parser("mint-key", help="Mint a desk key (token shown once).")
    dsk.add_argument("desk_id")
    dsk.add_argument("--name", required=True, help="Key label (≤255).")
    dsk.add_argument("--expires-at", dest="expires_at", help="ISO-8601 in the future.")
    desks.set_defaults(handler=cmd_desks)

    return parser


# Subcommands that hard-delete and must be gated behind --confirm. Every entry's
# second element is the value of the command's `<command>_action` subparser dest.
_CONFIRM_GATED = {
    ("projects", "delete"),
    ("page", "delete"),
    ("tasks", "delete"),
    ("tasks", "comment-delete"),
    ("desks", "delete"),
    ("asset", "delete-task"),
    ("asset", "delete-project"),
    ("asset", "delete-page"),
}


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    # Each command group names its subparser dest `<command>_action` (see build_parser),
    # so the action is resolvable generically — no per-command branch to keep in sync.
    action = getattr(args, f"{args.command}_action", None)
    try:
        if (args.command, action) in _CONFIRM_GATED:
            _confirm_or_abort(args)
        # One key = one workspace/desk actor; the client reads RUNDESK_API_KEY
        # from the process env or the local .env.
        client = RundeskClient(env_file=args.env_file)
        return args.handler(args, client)
    except RundeskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

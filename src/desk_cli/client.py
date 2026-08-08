#!/usr/bin/env python3
"""Importable bearer REST client for the Rundesk productivity + desk API (no CLI).

Purpose:
  A thin, dependency-light HTTP client over the Rundesk REST surface for accounts,
  projects, pages, tasks, weeks, assets, and the desk surface (agent + owner
  management), as defined by the Rundesk REST API documentation published by your
  deployment. NOT a full mirror of every endpoint: the calendar pass-through,
  asset-embed resolution, and admin/feedback routes are out of scope (see the
  "Out of scope" note in README.md). It is the single seam the `desk` CLI and any
  importing code use to read/write Rundesk.

Usage (import only):
  from client import RundeskClient, RundeskError
  rd = RundeskClient()                 # resolves base URL + key from env/.env
  account = rd.get_account()           # dict
  desk = rd.get_desk()                 # full desk row + nested projects[]

Inputs:
  Reads RUNDESK_BASE_URL and RUNDESK_API_KEY from process env, falling back to
  the local `.env` via the dotenv-reuse pattern (an already-set env var
  always wins, so a launcher-injected RUNDESK_API_KEY is never overwritten).
  One key = one Rundesk workspace/desk actor; a workspace is provisioned per
  desk, so there is no profile/multi-key selection here.

Outputs:
  Returns parsed JSON (dict/list) by default, or raw pipe-delimited text when a
  method is called with `as_text=True` (only where the API wires `?format=text`;
  project pages are JSON-only). Raises RundeskError on any failure, carrying a
  `kind` that maps to a stable process exit code.

Key surfaces:
  - account, projects (+ pages, search/grep), tasks (+ deadline/recurring/move),
    weeks, unified/parent-scoped assets — the standard account-scoped surface.
  - the DESK surface: an agent (desk-bound) key uses `/desk/...`; an owner key
    manages desks via `/desks/...`. The key decides which surface is permitted
    (the other returns 403).

ALL endpoint paths live in `Paths` below — the one place to update as the
web-app API firms up.
"""

from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


# The `.env` lives at the repo root; this module sits at
# src/desk_cli/, so parents[2] resolves the repo root. This anchors ONLY the
# default dotenv path (always injectable via env_file) — never cache/state.
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV = ROOT / ".env"
API_PREFIX = "/api/v1"
USER_AGENT = "desk-cli/1.0"


# ── Error model + exit-code mapping ────────────────────────────────────────
# 0 ok · 2 no key/usage/pending · 3 401 · 4 403 · 5 404/unresolvable · 6 422 ·
# 7 network. Any unmapped kind falls through to 1 (unknown).
KIND_EXIT = {
    "usage": 2,
    "no_key": 2,
    "pending": 2,
    "auth": 3,
    "forbidden": 4,
    "not_found": 5,
    "unprocessable": 6,
    "network": 7,
}
# HTTP status → error kind. Unlisted statuses (e.g. 500) map to a generic
# "http" kind whose exit code is 1.
STATUS_KIND = {
    401: "auth",
    403: "forbidden",
    404: "not_found",
    422: "unprocessable",
}


class RundeskError(RuntimeError):
    """A typed Rundesk failure. `kind` maps to a stable process exit code."""

    def __init__(self, kind: str, message: str = "") -> None:
        self.kind = kind
        super().__init__(message or kind)

    @property
    def exit_code(self) -> int:
        return KIND_EXIT.get(self.kind, 1)


# ── Centralized endpoint paths (the single source of truth) ────────────────
class Paths:
    """Every Rundesk REST path, relative to the `/api/v1` base. Update here as
    the web-app API firms up; nothing else hardcodes a path."""

    account = "/me"
    changelog = "/changelog"
    projects = "/projects"
    week = "/week"
    weeks = "/weeks"
    tasks = "/tasks"
    assets = "/assets"
    pages_search = "/pages/search"
    project_assets_search = "/projects/assets/search"

    # Desk (agent) surface — desk resolved from the key, no {desk} in the URL.
    desk = "/desk"
    desk_inbox = "/desk/inbox"
    desk_mentions = "/desk/mentions"

    # Human/user mention surface — a non-desk bearer acts for the signed-in
    # person's inbox rather than the token actor itself.
    user_mentions = "/mentions"
    user_mentions_count = "/mentions/unread-count"
    user_mentions_search = "/mentions/search"
    user_mentions_read_all = "/mentions/read-all"

    # Owner desk-management surface.
    desks = "/desks"

    @staticmethod
    def week_for(date: str) -> str:
        return f"/weeks/{date}"

    @staticmethod
    def project(project_id: Any) -> str:
        return f"/projects/{project_id}"

    @staticmethod
    def project_archive(project_id: Any) -> str:
        return f"/projects/{project_id}/archive"

    @staticmethod
    def project_unarchive(project_id: Any) -> str:
        return f"/projects/{project_id}/unarchive"

    @staticmethod
    def pages(project_id: Any) -> str:
        return f"/projects/{project_id}/pages"

    @staticmethod
    def pages_reorder(project_id: Any) -> str:
        return f"/projects/{project_id}/pages/reorder"

    @staticmethod
    def pages_grep(project_id: Any) -> str:
        return f"/projects/{project_id}/pages/grep"

    @staticmethod
    def page(project_id: Any, page_id: Any) -> str:
        return f"/projects/{project_id}/pages/{page_id}"

    @staticmethod
    def page_patch(project_id: Any, page_id: Any) -> str:
        return f"/projects/{project_id}/pages/{page_id}/patch"

    @staticmethod
    def user_mention_read(mention_id: Any) -> str:
        return f"/mentions/{mention_id}/read"

    @staticmethod
    def user_mention_entity(type: str, entity_id: Any) -> str:
        return f"/mentions/entity/{type}/{entity_id}"

    @staticmethod
    def task(task_id: Any) -> str:
        return f"/tasks/{task_id}"

    @staticmethod
    def task_complete(task_id: Any) -> str:
        return f"/tasks/{task_id}/complete"

    @staticmethod
    def task_uncomplete(task_id: Any) -> str:
        return f"/tasks/{task_id}/uncomplete"

    @staticmethod
    def task_move(task_id: Any) -> str:
        return f"/tasks/{task_id}/move"

    @staticmethod
    def task_move_project(task_id: Any) -> str:
        return f"/tasks/{task_id}/move-project"

    @staticmethod
    def task_restore(task_id: Any) -> str:
        return f"/tasks/{task_id}/restore"

    @staticmethod
    def task_recurring(task_id: Any) -> str:
        return f"/tasks/{task_id}/recurring"

    @staticmethod
    def task_deadline(task_id: Any) -> str:
        return f"/tasks/{task_id}/deadline"

    @staticmethod
    def task_comments(task_id: Any) -> str:
        return f"/tasks/{task_id}/comments"

    @staticmethod
    def task_comment(task_id: Any, comment_id: Any) -> str:
        return f"/tasks/{task_id}/comments/{comment_id}"

    # Assets — polymorphic across tasks, projects, and pages.
    @staticmethod
    def asset(asset_id: Any) -> str:
        return f"/assets/{asset_id}"

    @staticmethod
    def task_assets(task_id: Any) -> str:
        return f"/tasks/{task_id}/assets"

    @staticmethod
    def task_asset(task_id: Any, asset_id: Any) -> str:
        return f"/tasks/{task_id}/assets/{asset_id}"

    @staticmethod
    def project_assets(project_id: Any) -> str:
        return f"/projects/{project_id}/assets"

    @staticmethod
    def project_asset(project_id: Any, asset_id: Any) -> str:
        return f"/projects/{project_id}/assets/{asset_id}"

    @staticmethod
    def page_assets(project_id: Any, page_id: Any) -> str:
        return f"/projects/{project_id}/pages/{page_id}/assets"

    @staticmethod
    def page_asset(project_id: Any, page_id: Any, asset_id: Any) -> str:
        return f"/projects/{project_id}/pages/{page_id}/assets/{asset_id}"

    # Owner desk-management surface.
    @staticmethod
    def desk_by_id(desk_id: Any) -> str:
        return f"/desks/{desk_id}"

    @staticmethod
    def desk_retire(desk_id: Any) -> str:
        return f"/desks/{desk_id}/retire"

    @staticmethod
    def desk_unretire(desk_id: Any) -> str:
        return f"/desks/{desk_id}/unretire"

    @staticmethod
    def desk_project(desk_id: Any, project_id: Any) -> str:
        return f"/desks/{desk_id}/projects/{project_id}"

    @staticmethod
    def desk_keys(desk_id: Any) -> str:
        return f"/desks/{desk_id}/keys"


def load_dotenv(path: Path) -> None:
    """Populate os.environ from a dotenv file WITHOUT overwriting already-set
    keys, so a launcher-injected RUNDESK_API_KEY always wins over the file."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class RundeskClient:
    """Bearer REST client for one Rundesk actor (the key determines the account
    AND which surface — owner vs. desk — is permitted). Construct with no args
    to resolve config from env/.env, or pass `base_url`/`api_key` explicitly
    (offline tests do this)."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        env_file: str | os.PathLike[str] | None = None,
        timeout: int = 30,
    ) -> None:
        if base_url is None or api_key is None:
            load_dotenv(Path(env_file) if env_file else DEFAULT_ENV)
        self.base_url = (base_url if base_url is not None else os.environ.get("RUNDESK_BASE_URL", "")).rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("RUNDESK_API_KEY", "")
        self.timeout = timeout

    # ── URL + transport ────────────────────────────────────────────────────
    def build_url(self, path: str, params: dict[str, Any] | None = None, as_text: bool = False) -> str:
        """Compose a full request URL: base + /api/v1 + path + query. Drops
        None-valued params; adds `?format=text` when `as_text` is set."""
        query = {key: value for key, value in (params or {}).items() if value is not None}
        if as_text:
            query["format"] = "text"
        url = f"{self.base_url}{API_PREFIX}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)
        return url

    def _require_config(self) -> None:
        if not self.base_url:
            raise RundeskError("usage", "Missing RUNDESK_BASE_URL. Add it to local .env.")
        if not self.api_key:
            raise RundeskError("no_key", "Missing RUNDESK_API_KEY. Add it to local .env or have the launcher inject it.")

    def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        as_text: bool = False,
    ) -> Any:
        """Issue one JSON request and return parsed JSON (dict/list), raw text
        (when `as_text`), or None for empty/204 responses. Maps every failure to
        a typed RundeskError."""
        self._require_config()
        url = self.build_url(path, params, as_text)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "text/plain" if as_text else "application/json",
            "User-Agent": USER_AGENT,
        }
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        return self._send(req, method, path, as_text)

    def _send(self, req: urllib.request.Request, method: str, path: str, as_text: bool) -> Any:
        """Execute a prepared Request and normalize the response / errors. Shared
        by `request` (JSON) and `_post_multipart` (file upload)."""
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                if not raw:
                    return None
                if as_text:
                    return raw
                try:
                    return json.loads(raw)
                except ValueError as exc:
                    # 200 with a non-JSON body (proxy/maintenance page) — keep the
                    # documented exit-code contract instead of a raw traceback.
                    raise RundeskError(
                        "http", f"Rundesk API returned a non-JSON body for {method} {path}"
                    ) from exc
        except urllib.error.HTTPError as exc:
            kind = STATUS_KIND.get(exc.code, "http")
            detail = _safe_read(exc)
            raise RundeskError(kind, f"Rundesk API {exc.code} {method} {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RundeskError("network", f"Rundesk API request failed {method} {path}: {exc.reason}") from exc

    def _post_multipart(self, path: str, file_path: str | os.PathLike[str]) -> Any:
        """POST a single `file` field as multipart/form-data (asset uploads).
        Returns the parsed 201 asset payload."""
        self._require_config()
        source = Path(file_path)
        if not source.is_file():
            raise RundeskError("usage", f"Upload source not found: {source}")
        data = source.read_bytes()
        filename = source.name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        boundary = uuid.uuid4().hex
        prologue = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8")
        epilogue = f"\r\n--{boundary}--\r\n".encode("utf-8")
        body = prologue + data + epilogue
        url = self.build_url(path)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": USER_AGENT,
        }
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        return self._send(req, "POST", path, as_text=False)

    # ── Account ─────────────────────────────────────────────────────────────
    def get_account(self, as_text: bool = False) -> Any:
        """GET /me → dict {id, name, email, timezone, created_at}, or the
        `id|name|email|timezone` text row when `as_text`."""
        return self.request("GET", Paths.account, as_text=as_text)

    def get_changelog(
        self,
        limit: int | None = None,
        all: bool = False,
        major: int | None = None,
    ) -> Any:
        """GET /changelog → `{data:[{version,date,body}], meta}` release notes,
        newest first. `limit` 1–50 (default 3); `all=True` returns every entry;
        `major` narrows to one major release line."""
        params = {"limit": limit, "all": 1 if all else None, "major": major}
        return self.request("GET", Paths.changelog, params=params)

    # ── Desk surface (agent / desk-bound key) ────────────────────────────────
    def get_desk(self, as_text: bool = False) -> Any:
        """GET /desk → the bound desk's identity, owner, and nested `projects[]`
        (each a raw project object INCLUDING short_code and desk_id — the
        desk-scoped key map). Text mode renders `key|name|archived` + a scope
        summary."""
        return self.request("GET", Paths.desk, as_text=as_text)

    def get_desk_inbox(
        self,
        week: Any | None = None,
        unscheduled: bool = False,
        as_text: bool = False,
    ) -> Any:
        """GET /desk/inbox → the desk's to-do view (replaces the old /desk/board).

        Default: `{desk, mode, week, projects:[{name, tasks:[...]}], mentions}` —
        this week's tasks (each with its latest comments) plus unread @-mentions.
        The two filters are MUTUALLY EXCLUSIVE (422 if both) and swap in a plain
        task list with no mentions:
          - `week`: a `task_weeks` id (that week's tasks); unknown id → 422.
          - `unscheduled=True`: the desk's no-week (inbox) tasks.
        Text mode renders the agent-facing markdown to-do."""
        params: dict[str, Any] = {}
        if week is not None:
            params["week"] = week
        if unscheduled:
            params["unscheduled"] = 1
        return self.request("GET", Paths.desk_inbox, params=params or None, as_text=as_text)

    def get_desk_mentions(self, limit: int | None = None, as_text: bool = False) -> Any:
        """GET /desk/mentions → unread @-mentions on this desk's tasks, newest
        first (read-only, desk-bound key). `limit` 1–100 caps the result set.
        Text mode renders the agent-facing rows; the default is the parsed payload,
        as it is for every other read on this client."""
        params = _compact({"limit": limit})
        return self.request("GET", Paths.desk_mentions, params=params or None, as_text=as_text)

    # ── Human/user mentions (non-desk bearer surface) ───────────────────────
    def list_user_mentions(
        self,
        unread: bool = False,
        per_page: int | None = None,
        page: int | None = None,
    ) -> Any:
        """GET /mentions → the signed-in human identity's paginated inbox."""
        params = {
            "unread": 1 if unread else None,
            "per_page": per_page,
            "page": page,
        }
        return self.request("GET", Paths.user_mentions, params=params)

    def get_user_mentions_count(self) -> Any:
        """GET /mentions/unread-count → ``{count}`` for the human inbox."""
        return self.request("GET", Paths.user_mentions_count)

    def search_user_mention_targets(
        self,
        q: str | None = None,
        types: str | None = None,
        limit: int | None = None,
        project_id: Any | None = None,
        task_id: Any | None = None,
    ) -> Any:
        """GET /mentions/search → visible page, task, and actor targets."""
        params = {
            "q": q,
            "types": types,
            "limit": limit,
            "project_id": project_id,
            "task_id": task_id,
        }
        return self.request("GET", Paths.user_mentions_search, params=params)

    def list_entity_mentions(
        self,
        type: str,
        entity_id: Any,
        per_page: int | None = None,
        page: int | None = None,
    ) -> Any:
        """GET /mentions/entity/{type}/{id} → incoming mentions for an entity."""
        return self.request(
            "GET",
            Paths.user_mention_entity(type, entity_id),
            params={"per_page": per_page, "page": page},
        )

    def mark_user_mention_read(self, mention_id: Any) -> Any:
        """POST /mentions/{mention}/read → mark one human mention read."""
        return self.request("POST", Paths.user_mention_read(mention_id))

    def mark_all_user_mentions_read(self) -> Any:
        """POST /mentions/read-all → clear the human inbox's unread state."""
        return self.request("POST", Paths.user_mentions_read_all)

    # ── Projects ────────────────────────────────────────────────────────────
    def list_projects(
        self,
        search: str | None = None,
        type: str | None = None,
        is_archived: int | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort: str | None = None,
        sort_order: int | None = None,
        as_text: bool = False,
        desk_id: Any | None = None,
    ) -> Any:
        """GET /projects → the parsed JSON list payload (or `id|name|type|files`
        text rows when `as_text`). `search` is name-scoped; `type` is
        professional/personal. NOTE: `short_code` is HIDDEN on this response."""
        params = {
            "search": search,
            "type": type,
            "is_archived": is_archived,
            "per_page": per_page,
            "page": page,
            "sort": sort,
            "sort_order": sort_order,
            "desk_id": desk_id,
        }
        return self.request("GET", Paths.projects, params=params, as_text=as_text)

    def get_project(
        self,
        project_id: Any,
        as_text: bool = False,
        desk_id: Any | None = None,
    ) -> Any:
        """GET /projects/{id} → single project + asset list (dict), or text."""
        params = {"desk_id": desk_id} if desk_id is not None else None
        return self.request(
            "GET", Paths.project(project_id), params=params, as_text=as_text,
        )

    def create_project(
        self,
        name: str,
        short_code: str | None = None,
        color: str | None = None,
        type: str | None = None,
        is_hidden: bool | None = None,
        index_pages: bool | None = None,
        desk_id: Any | None = None,
    ) -> Any:
        """POST /projects → 201 project (auto-seeds a starter page; the response
        strips short_code). `desk_id` optionally targets an owner-visible desk.
        New projects always begin with page indexing enabled. The retained
        `is_hidden`/`index_pages` arguments protect the 0.2 call signature, but
        retired or impossible values fail instead of reporting false success."""
        _validate_legacy_project_options(is_hidden, index_pages, creating=True)
        payload = _project_payload(name, short_code, color, type)
        if desk_id is not None:
            payload["desk_id"] = desk_id
        return self.request("POST", Paths.projects, payload=payload)

    def update_project(
        self,
        project_id: Any,
        name: str | None = None,
        short_code: str | None = None,
        color: str | None = None,
        type: str | None = None,
        is_hidden: bool | None = None,
        index_pages: bool | None = None,
    ) -> Any:
        """PUT /projects/{id} → partial update. Page indexing can be toggled;
        the retired `is_hidden` argument is rejected rather than ignored."""
        _validate_legacy_project_options(is_hidden, index_pages, creating=False)
        payload = _project_payload(name, short_code, color, type)
        if index_pages is not None:
            payload["index_pages"] = index_pages
        return self.request("PUT", Paths.project(project_id), payload=payload)

    def delete_project(self, project_id: Any) -> Any:
        """DELETE /projects/{id} → PERMANENT delete of the project + all child
        files. Returns None (204)."""
        return self.request("DELETE", Paths.project(project_id))

    def archive_project(self, project_id: Any) -> Any:
        """POST /projects/{id}/archive → returns the updated project."""
        return self.request("POST", Paths.project_archive(project_id))

    def unarchive_project(self, project_id: Any) -> Any:
        """POST /projects/{id}/unarchive → returns the updated project."""
        return self.request("POST", Paths.project_unarchive(project_id))

    # NOTE: there is intentionally no `find_project_by_short_code` here. The public
    # `GET /projects` list HIDES `short_code`, so a client-side scan would always miss.
    # Resolve a project by key via `get_desk()`'s nested `projects[]` instead (a desk
    # key sees its own projects WITH `short_code`).

    # ── Project pages ───────────────────────────────────────────────────────
    def get_pages(
        self,
        project_id: Any,
        meta: dict[str, Any] | None = None,
        include_body: bool = False,
        frontmatter_only: bool = False,
        body_chars: int | None = None,
        search: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
    ) -> Any:
        """GET /projects/{p}/pages → parsed JSON list of pages (JSON-only). Each
        item carries id, title, sort_order, updated_at, assets_count,
        frontmatter, frontmatter_parsed.

        - `meta`: frontmatter containment filter (e.g. {"page_role": "rules"});
          serialized to the `?meta=` URL-encoded JSON object the API expects.
        - `include_body`: adds `body_preview` (capped at `body_chars`, default
          255, hard max 512 — NOT the full body; use `get_page`).
        - `frontmatter_only`: frontmatter is always present, so this just forces
          body off (the server flag lives on the single-page GET via `get_page`).
        """
        params: dict[str, Any] = {}
        params.update({"search": search, "per_page": per_page, "page": page})
        if meta:
            params["meta"] = json.dumps(meta, separators=(",", ":"), sort_keys=True)
        if include_body and not frontmatter_only:
            params["include_body"] = 1
            if body_chars is not None:
                params["body_chars"] = body_chars
        return self.request("GET", Paths.pages(project_id), params=params)

    def get_page(self, project_id: Any, page_id: Any, frontmatter_only: bool = False) -> Any:
        """GET /projects/{p}/pages/{page} → single page dict (JSON-only). Default
        returns the full body markdown plus the children subtree;
        `frontmatter_only=True` returns frontmatter + frontmatter_parsed instead
        of body (children subtree omitted)."""
        params = {"frontmatter_only": 1} if frontmatter_only else None
        return self.request("GET", Paths.page(project_id, page_id), params=params)

    def create_page(
        self,
        project_id: Any,
        body: str | None,
        parent_page_id: Any | None = None,
        sort_order: int | None = None,
    ) -> Any:
        """POST /projects/{p}/pages → 201 slim `{id, title, created_at}`. `body`
        ≤1,000,000 chars and may lead with a `---\\nyaml\\n---\\n` frontmatter
        block (bad YAML → 422). `parent_page_id` nests one level; `sort_order`
        positions the page."""
        payload: dict[str, Any] = {"body": body}
        if parent_page_id is not None:
            payload["parent_page_id"] = parent_page_id
        if sort_order is not None:
            payload["sort_order"] = sort_order
        return self.request("POST", Paths.pages(project_id), payload=payload)

    def update_page(
        self,
        project_id: Any,
        page_id: Any,
        body: str | None = None,
        frontmatter: str | None = None,
        description: str | None = None,
        parent_page_id: Any | None = None,
        sort_order: int | None = None,
        set_parent: bool = False,
    ) -> Any:
        """PUT /projects/{p}/pages/{page} → full update, three shapes: `body`
        alone (full replace incl. any kept frontmatter), `frontmatter` alone
        (replace YAML, prose preserved; "" / explicit clear), or BOTH (body is
        body-only, frontmatter wrapped automatically; frontmatter must NOT carry
        `---` fences). Returns slim `{id, title, updated_at}`."""
        payload: dict[str, Any] = {}
        if body is not None:
            payload["body"] = body
        if frontmatter is not None:
            payload["frontmatter"] = frontmatter
        if description is not None:
            payload["description"] = description
        if parent_page_id is not None or set_parent:
            payload["parent_page_id"] = parent_page_id
        if sort_order is not None:
            payload["sort_order"] = sort_order
        return self.request("PUT", Paths.page(project_id, page_id), payload=payload)

    def patch_page(
        self,
        project_id: Any,
        page_id: Any,
        mode: str,
        old_str: str | None = None,
        new_str: str | None = None,
        content: str | None = None,
        description: str | None = None,
    ) -> Any:
        """POST /projects/{p}/pages/{page}/patch — surgical body edit (frontmatter
        preserved). Returns the slim {id, title, updated_at} dict.

        - `mode="replace"`: requires `old_str` (must match prose exactly once,
          frontmatter excluded) and `new_str` (empty/None deletes the snippet).
        - `mode="append"` / `"prepend"`: requires `content`; `old_str` is an
          optional anchor (omit for body-level insertion). A `\\n\\n` separator
          is auto-inserted when the existing prose/anchor is non-empty.
        - `description`: optional ≤255-char label for the version-history row.
        """
        if mode not in {"replace", "append", "prepend"}:
            raise RundeskError("usage", f"patch_page mode must be replace/append/prepend, got {mode!r}")
        payload: dict[str, Any] = {"mode": mode}
        if mode == "replace":
            if not old_str:
                raise RundeskError("usage", "patch_page mode=replace requires a non-empty old_str")
            payload["old_str"] = old_str
            payload["new_str"] = new_str
        else:
            if not content:
                raise RundeskError("usage", f"patch_page mode={mode} requires non-empty content")
            payload["content"] = content
            if old_str is not None:
                payload["old_str"] = old_str
        if description is not None:
            payload["description"] = description
        return self.request("POST", Paths.page_patch(project_id, page_id), payload=payload)

    def delete_page(self, project_id: Any, page_id: Any) -> Any:
        """DELETE /projects/{p}/pages/{page} → 204. 422 when it is the last page
        ("A project must have at least one page.")."""
        return self.request("DELETE", Paths.page(project_id, page_id))

    def reorder_pages(
        self,
        project_id: Any,
        ids: list[Any] | None = None,
        parent_page_id: Any | None = None,
        scopes: list[dict[str, Any]] | None = None,
    ) -> Any:
        """PATCH /projects/{p}/pages/reorder using complete sibling scopes.

        `ids` preserves the released single-scope call and defaults to top-level;
        pass `parent_page_id` for one child scope. `scopes` exposes the complete
        API for multi-scope moves.
        """
        if scopes is not None and (ids is not None or parent_page_id is not None):
            raise RundeskError(
                "usage", "--scopes cannot be combined with sibling ids or --parent",
            )
        if scopes is None:
            if ids is None:
                raise RundeskError("usage", "page reorder requires ids or scopes")
            scopes = [{"parent_page_id": parent_page_id, "ids": ids}]
        return self.request(
            "PATCH", Paths.pages_reorder(project_id), payload={"scopes": scopes},
        )

    def search_pages(
        self,
        q: str,
        project_type: str,
        project_id: Any | None = None,
        limit: int | None = None,
        page_id: Any | None = None,
    ) -> Any:
        """GET /pages/search → `{results:[...]}` semantic+keyword content search.
        `q` 3–500 chars (under 8 → keyword only); `project_type` required
        (professional|personal, scopes the search); `project_id` narrows;
        `page_id` narrows within that project; `limit` 1–25 (default 5)."""
        params = {
            "q": q,
            "project_type": project_type,
            "project_id": project_id,
            "page_id": page_id,
            "limit": limit,
        }
        return self.request("GET", Paths.pages_search, params=params)

    def grep_pages(
        self,
        project_id: Any,
        pattern: str,
        page_id: Any | None = None,
        ignore_case: bool = False,
        context: int | None = None,
        max_count: int | None = None,
        max_pages: int | None = None,
        count_only: bool = False,
        as_text: bool = False,
    ) -> Any:
        """GET /projects/{project}/pages/grep → regex matches over page prose.

        ``page_id`` narrows to one page. The remaining options mirror grep's
        case, context, per-page match, page-count, and count-only controls.
        """
        params = {
            "pattern": pattern,
            "page_id": page_id,
            "ignore_case": 1 if ignore_case else None,
            "context": context,
            "max_count": max_count,
            "max_pages": max_pages,
            "count_only": 1 if count_only else None,
        }
        return self.request(
            "GET", Paths.pages_grep(project_id), params=params, as_text=as_text,
        )

    # ── Tasks ────────────────────────────────────────────────────────────────
    def list_tasks(
        self,
        status: str | None = None,
        project_id: Any | None = None,
        task_week_id: Any | None = None,
        inbox: int | None = None,
        is_recurring_template: int | None = None,
        sort: str | None = None,
        sort_order: int | None = None,
        per_page: int | None = None,
        page: int | None = None,
        as_text: bool = False,
        desk_id: Any | None = None,
        is_flagged: int | None = None,
    ) -> Any:
        """GET /tasks → parsed JSON list (or `id|title|status|project_id|week_id|
        due|files` text rows when `as_text`). `status` todo/done;
        `inbox=1` returns the desk's no-week tasks (mutually exclusive with
        `task_week_id` — the API rejects both); `is_recurring_template` 1/0."""
        params = {
            "status": status,
            "project_id": project_id,
            "task_week_id": task_week_id,
            "inbox": inbox,
            "desk_id": desk_id,
            "is_recurring_template": is_recurring_template,
            "is_flagged": is_flagged,
            "sort": sort,
            "sort_order": sort_order,
            "per_page": per_page,
            "page": page,
        }
        return self.request("GET", Paths.tasks, params=params, as_text=as_text)

    def get_task(self, task_id: Any, as_text: bool = False) -> Any:
        """GET /tasks/{id} → single task with project, week, and asset list."""
        return self.request("GET", Paths.task(task_id), as_text=as_text)

    def create_task(
        self,
        title: str,
        body: str | None = None,
        project_id: Any | None = None,
        task_week_id: Any | None = None,
        desk_id: Any | None = None,
        is_flagged: bool | None = None,
    ) -> Any:
        """POST /tasks → create. `title` ≤500; omit `task_week_id` for inbox.
        Returns the created task."""
        payload = _compact(
            {
                "title": title,
                "body": body,
                "project_id": project_id,
                "task_week_id": task_week_id,
                "desk_id": desk_id,
                "is_flagged": is_flagged,
            }
        )
        return self.request("POST", Paths.tasks, payload=payload)

    def update_task(
        self,
        task_id: Any,
        title: str | None = None,
        body: str | None = None,
        project_id: Any | None = None,
        is_flagged: bool | None = None,
    ) -> Any:
        """PUT /tasks/{id} → partial update. Accepts `title`, `body`,
        `project_id`, `is_flagged`. NOTE: `task_week_id` is PROHIBITED here (422)
        — change a task's week with `move_task_week`; `desk_id` is not accepted."""
        payload = _compact(
            {"title": title, "body": body, "project_id": project_id, "is_flagged": is_flagged}
        )
        return self.request("PUT", Paths.task(task_id), payload=payload)

    def complete_task(self, task_id: Any) -> Any:
        """POST /tasks/{id}/complete → status=done, completed_at=now."""
        return self.request("POST", Paths.task_complete(task_id))

    def uncomplete_task(self, task_id: Any) -> Any:
        """POST /tasks/{id}/uncomplete → status=todo, clears completed_at."""
        return self.request("POST", Paths.task_uncomplete(task_id))

    def delete_task(self, task_id: Any) -> Any:
        """DELETE /tasks/{id} → soft delete (restorable). Returns None (204)."""
        return self.request("DELETE", Paths.task(task_id))

    def restore_task(self, task_id: Any) -> Any:
        """POST /tasks/{id}/restore → restore a soft-deleted task."""
        return self.request("POST", Paths.task_restore(task_id))

    def move_task_week(self, task_id: Any, task_week_id: Any | None) -> Any:
        """POST /tasks/{id}/move → move to a week. `task_week_id` int, or None for
        inbox (the key is always sent)."""
        return self.request("POST", Paths.task_move(task_id), payload={"task_week_id": task_week_id})

    def move_task_project(self, task_id: Any, project_id: Any | None) -> Any:
        """POST /tasks/{id}/move-project → move to a project. `project_id` int, or
        None for uncategorized (the key is always sent)."""
        return self.request("POST", Paths.task_move_project(task_id), payload={"project_id": project_id})

    def set_task_deadline(self, task_id: Any, due_at: str, is_all_day_due: bool | None = None) -> Any:
        """POST /tasks/{id}/deadline → set/update deadline. `due_at` ISO-8601 UTC
        (e.g. 2026-05-01T15:00:00Z). `is_all_day_due=True` makes `due_at` a
        floating date (pass YYYY-MM-DDT00:00:00Z). On an inbox task this
        auto-moves it into the matching week (`moved_to_week` in the response)."""
        payload: dict[str, Any] = {"due_at": due_at}
        if is_all_day_due is not None:
            payload["is_all_day_due"] = is_all_day_due
        return self.request("POST", Paths.task_deadline(task_id), payload=payload)

    def remove_task_deadline(self, task_id: Any) -> Any:
        """DELETE /tasks/{id}/deadline → clear the deadline (week unchanged)."""
        return self.request("DELETE", Paths.task_deadline(task_id))

    def set_task_recurring(
        self,
        task_id: Any,
        frequency: str,
        interval: int,
        end_type: str,
        days_of_week: list[int] | None = None,
        day_of_month: int | None = None,
        end_count: int | None = None,
        end_date: str | None = None,
        start_at: str | None = None,
        due_time: str | None = None,
        due_weekday: int | None = None,
        due_all_day: bool | None = None,
    ) -> Any:
        """POST /tasks/{id}/recurring → make the task recurring. Inbox tasks
        become the template directly; week tasks spawn a new inbox template and
        become the first instance. `frequency` daily/weekly/monthly; `interval`
        1–52; `end_type` never/count/date; `days_of_week` (weekly, 1–7);
        `day_of_month` (monthly, 1–31); `end_count`/`end_date` per end_type;
        `start_at` delays generation; `due_time` HH:MM (mutually exclusive with
        `due_all_day`); `due_weekday` 1–7."""
        return self.request(
            "POST",
            Paths.task_recurring(task_id),
            payload=_recurring_payload(
                frequency, interval, end_type, days_of_week, day_of_month,
                end_count, end_date, start_at, due_time, due_weekday, due_all_day,
            ),
        )

    def update_task_recurring(
        self,
        task_id: Any,
        frequency: str,
        interval: int,
        end_type: str,
        days_of_week: list[int] | None = None,
        day_of_month: int | None = None,
        end_count: int | None = None,
        end_date: str | None = None,
        start_at: str | None = None,
        due_time: str | None = None,
        due_weekday: int | None = None,
        due_all_day: bool | None = None,
    ) -> Any:
        """PUT /tasks/{id}/recurring → update the recurrence pattern (same body as
        set_task_recurring)."""
        return self.request(
            "PUT",
            Paths.task_recurring(task_id),
            payload=_recurring_payload(
                frequency, interval, end_type, days_of_week, day_of_month,
                end_count, end_date, start_at, due_time, due_weekday, due_all_day,
            ),
        )

    def remove_task_recurring(self, task_id: Any) -> Any:
        """DELETE /tasks/{id}/recurring → strip recurring status, demoting the
        template back to a normal inbox task."""
        return self.request("DELETE", Paths.task_recurring(task_id))

    # ── Task comments (the timeline — read history, post an outcome) ──────────
    # JSON-only (no ?format=text view). NOTE: a task's *own* GET /tasks/{id} text
    # view already embeds its comment history, so the desk `task` read needs no
    # separate call; these are for posting/managing comments directly.
    def list_task_comments(self, task_id: Any) -> Any:
        """GET /tasks/{id}/comments → `{comments:[{id, body, created_at,
        updated_at, author:{id, kind, display_name, handle, ...}}]}`, oldest
        first. A desk-bound agent key is scoped to its own desk (404 otherwise)."""
        return self.request("GET", Paths.task_comments(task_id))

    def create_task_comment(self, task_id: Any, body: str) -> Any:
        """POST /tasks/{id}/comments → post a comment (the desk tick's "record
        and close" outcome summary). `body` required (≤ the task-comment max).
        Bare `@handle` mentions are resolved server-side. Returns 201
        `{comment:{...}}`."""
        return self.request("POST", Paths.task_comments(task_id), payload={"body": body})

    def update_task_comment(self, task_id: Any, comment_id: Any, body: str) -> Any:
        """PATCH /tasks/{id}/comments/{comment} → edit a comment. AUTHOR-ONLY:
        403 unless the acting actor wrote it; a comment not on this task is 404."""
        return self.request("PATCH", Paths.task_comment(task_id, comment_id), payload={"body": body})

    def delete_task_comment(self, task_id: Any, comment_id: Any) -> Any:
        """DELETE /tasks/{id}/comments/{comment} → remove a comment (204).
        AUTHOR-ONLY, no owner override; wrong-task comment id → 404 before 403."""
        return self.request("DELETE", Paths.task_comment(task_id, comment_id))

    # ── Weeks ────────────────────────────────────────────────────────────────
    def get_week(
        self,
        date: str | None = None,
        as_text: bool = False,
        desk_id: Any | None = None,
    ) -> Any:
        """GET /week (current) or /weeks/{YYYY-MM-DD} → tasks grouped by project,
        split todo/done. Text mode emits the `week|...` / `project|task_id|...`
        block."""
        path = Paths.week_for(date) if date else Paths.week
        return self.request("GET", path, params={"desk_id": desk_id}, as_text=as_text)

    def list_weeks(
        self,
        past: int | None = None,
        future: int | None = None,
        as_text: bool = False,
        desk_id: Any | None = None,
    ) -> Any:
        """GET /weeks → weeks with completion stats (`id|starts_at|ends_at|
        completed|total` in text mode). `past`/`future` window (bounded by
        rundesk.weeks_ahead, default 52)."""
        params = {"past": past, "future": future, "desk_id": desk_id}
        return self.request("GET", Paths.weeks, params=params, as_text=as_text)

    # ── Assets (polymorphic: tasks, projects, pages) ─────────────────────────
    def get_asset(self, asset_id: Any, as_text: bool = False) -> Any:
        """GET /assets/{id} → single asset by id (no parent context). Text files
        carry full `content`; binaries have `content=null` + a `note` pointer."""
        return self.request("GET", Paths.asset(asset_id), as_text=as_text)

    def list_assets(
        self,
        filename: str | None = None,
        task_id: Any | None = None,
        project_id: Any | None = None,
        page_id: Any | None = None,
        sort: str | None = None,
        page: int | None = None,
        per_page: int | None = None,
        as_text: bool = False,
    ) -> Any:
        """GET /assets → recent assets across task, project, and page parents.

        ``filename`` is a substring filter. At most one parent id should be
        supplied; the CLI enforces that before this method is called.
        """
        params = {
            "filename": filename,
            "task_id": task_id,
            "project_id": project_id,
            "page_id": page_id,
            "sort": sort,
            "page": page,
            "per_page": per_page,
        }
        return self.request("GET", Paths.assets, params=params, as_text=as_text)

    def update_asset(
        self,
        asset_id: Any,
        filename: str | None = None,
        content: str | None = None,
        encoding: str | None = None,
    ) -> Any:
        """PATCH /assets/{asset} → rename and/or replace an asset directly."""
        if filename is None and content is None:
            raise RundeskError("usage", "asset update requires --filename or content.")
        payload = _compact(
            {"filename": filename, "content": content, "encoding": encoding}
        )
        return self.request("PATCH", Paths.asset(asset_id), payload=payload)

    def list_project_assets(
        self,
        project_id: Any,
        search: str | None = None,
        sort: str | None = None,
        page: int | None = None,
        as_text: bool = False,
    ) -> Any:
        """GET /projects/{p}/assets → `{files:[...], has_more, next_page}`
        (24/page). `search` filename ilike; `sort` newest/oldest/name_asc/
        name_desc."""
        params = {"search": search, "sort": sort, "page": page}
        return self.request("GET", Paths.project_assets(project_id), params=params, as_text=as_text)

    def list_page_assets(
        self,
        project_id: Any,
        page_id: Any,
        search: str | None = None,
        sort: str | None = None,
        page: int | None = None,
        as_text: bool = False,
    ) -> Any:
        """GET /projects/{p}/pages/{page}/assets → `{files:[...], has_more,
        next_page}` (24/page); same query as list_project_assets."""
        params = {"search": search, "sort": sort, "page": page}
        return self.request("GET", Paths.page_assets(project_id, page_id), params=params, as_text=as_text)

    def search_project_assets(self, q: str, sort: str | None = None, limit: int | None = None) -> Any:
        """GET /projects/assets/search → filename search across all of the user's
        projects (PROJECT files only — task/page files excluded). `q` 1–200
        chars required; `limit` 1–100 (default 25)."""
        params = {"q": q, "sort": sort, "limit": limit}
        return self.request("GET", Paths.project_assets_search, params=params)

    def upload_task_asset(self, task_id: Any, file_path: str | os.PathLike[str]) -> Any:
        """POST /tasks/{t}/assets (multipart `file`) → 201 asset."""
        return self._post_multipart(Paths.task_assets(task_id), file_path)

    def upload_project_asset(self, project_id: Any, file_path: str | os.PathLike[str]) -> Any:
        """POST /projects/{p}/assets (multipart `file`) → 201 asset."""
        return self._post_multipart(Paths.project_assets(project_id), file_path)

    def upload_page_asset(self, project_id: Any, page_id: Any, file_path: str | os.PathLike[str]) -> Any:
        """POST /projects/{p}/pages/{page}/assets (multipart `file`) → 201 asset."""
        return self._post_multipart(Paths.page_assets(project_id, page_id), file_path)

    def rename_task_asset(self, task_id: Any, asset_id: Any, filename: str) -> Any:
        """PATCH /tasks/{t}/assets/{a} → rename (display name only). Returns the
        updated asset."""
        return self.request("PATCH", Paths.task_asset(task_id, asset_id), payload={"filename": filename})

    def rename_project_asset(self, project_id: Any, asset_id: Any, filename: str) -> Any:
        """PATCH /projects/{p}/assets/{a} → rename (display name only)."""
        return self.request("PATCH", Paths.project_asset(project_id, asset_id), payload={"filename": filename})

    def rename_page_asset(self, project_id: Any, page_id: Any, asset_id: Any, filename: str) -> Any:
        """PATCH /projects/{p}/pages/{page}/assets/{a} → rename (display name)."""
        return self.request(
            "PATCH", Paths.page_asset(project_id, page_id, asset_id), payload={"filename": filename}
        )

    def delete_task_asset(self, task_id: Any, asset_id: Any) -> Any:
        """DELETE /tasks/{t}/assets/{a} → `{deleted: true}` (DB + S3)."""
        return self.request("DELETE", Paths.task_asset(task_id, asset_id))

    def delete_project_asset(self, project_id: Any, asset_id: Any) -> Any:
        """DELETE /projects/{p}/assets/{a} → `{deleted: true}`."""
        return self.request("DELETE", Paths.project_asset(project_id, asset_id))

    def delete_page_asset(self, project_id: Any, page_id: Any, asset_id: Any) -> Any:
        """DELETE /projects/{p}/pages/{page}/assets/{a} → `{deleted: true}`."""
        return self.request("DELETE", Paths.page_asset(project_id, page_id, asset_id))

    # ── Desk discovery + owner desk-management surface (`/desks`) ─────────────
    def list_desks(self, include_retired: bool = False, as_text: bool = False) -> Any:
        """GET /desks → the desks the caller may view (a desk-bound key sees only
        its own desk; a Member key sees its assigned desk; owner/admin keys see
        every desk). Read-only discovery — desk MANAGEMENT below is owner-gated.
        `include_retired=True` adds retired desks."""
        params = {"include_retired": 1} if include_retired else None
        return self.request("GET", Paths.desks, params=params, as_text=as_text)

    def get_desk_by_id(self, desk_id: Any, as_text: bool = False) -> Any:
        """GET /desks/{desk} → single desk + its projects (any caller who may view
        that desk; self-scoped for a desk key)."""
        return self.request("GET", Paths.desk_by_id(desk_id), as_text=as_text)

    def create_desk(
        self,
        name: str,
        owner_type: str | None = None,
        owner_actor_id: int | None = None,
        project_ids: list[int] | None = None,
        *,
        assignee_type: str | None = None,
        assignee_actor_id: int | None = None,
        owner_id: int | None = None,
        brief: str | None = None,
        rules: str | None = None,
        memory: str | None = None,
    ) -> Any:
        """POST /desks → create a desk (owner key only). `assignee_type` and
        `assignee_actor_id` seat an existing person/agent; `owner_id` is the
        responsible human for an agent desk. The old `owner_type` and
        `owner_actor_id` keywords remain aliases for source compatibility."""
        assignee_type, assignee_actor_id = _resolve_desk_assignment(
            assignee_type, assignee_actor_id, owner_type, owner_actor_id,
        )
        payload = _desk_payload(
            name, assignee_type, assignee_actor_id, owner_id, project_ids,
            brief, rules, memory,
        )
        return self.request("POST", Paths.desks, payload=payload)

    def update_desk(
        self,
        desk_id: Any,
        name: str | None = None,
        owner_type: str | None = None,
        owner_actor_id: int | None = None,
        project_ids: list[int] | None = None,
        *,
        assignee_type: str | None = None,
        assignee_actor_id: int | None = None,
        owner_id: int | None = None,
        brief: str | None = None,
        rules: str | None = None,
        memory: str | None = None,
    ) -> Any:
        """PUT /desks/{desk} → partial assignment/project update. Legacy
        `owner_type`/`owner_actor_id` keywords map to the assignee fields."""
        assignee_type, assignee_actor_id = _resolve_desk_assignment(
            assignee_type, assignee_actor_id, owner_type, owner_actor_id,
        )
        payload = _desk_payload(
            name, assignee_type, assignee_actor_id, owner_id, project_ids,
            brief, rules, memory,
        )
        return self.request("PUT", Paths.desk_by_id(desk_id), payload=payload)

    def delete_desk(self, desk_id: Any) -> Any:
        """DELETE /desks/{desk} → delete the desk. Returns None (204)."""
        return self.request("DELETE", Paths.desk_by_id(desk_id))

    def retire_desk(self, desk_id: Any) -> Any:
        """POST /desks/{desk}/retire → retire the desk. Returns the updated desk."""
        return self.request("POST", Paths.desk_retire(desk_id))

    def unretire_desk(self, desk_id: Any) -> Any:
        """POST /desks/{desk}/unretire → restore a retired desk. Returns the
        updated desk."""
        return self.request("POST", Paths.desk_unretire(desk_id))

    def attach_project(self, desk_id: Any, project_id: Any) -> Any:
        """POST /desks/{desk}/projects/{project} → attach a project to the desk."""
        return self.request("POST", Paths.desk_project(desk_id, project_id))

    def detach_project(self, desk_id: Any, project_id: Any) -> Any:
        """DELETE /desks/{desk}/projects/{project} → detach a project (404 if not
        on this desk)."""
        return self.request("DELETE", Paths.desk_project(desk_id, project_id))

    def create_desk_key(self, desk_id: Any, name: str, expires_at: str | None = None) -> Any:
        """POST /desks/{desk}/keys → mint a desk key. `name` ≤255; `expires_at`
        ISO-8601 in the future (omit for non-expiring). Returns 201
        `{message, plain_text_token, actor, desk}` — the token is shown ONCE."""
        payload = _compact({"name": name, "expires_at": expires_at})
        return self.request("POST", Paths.desk_keys(desk_id), payload=payload)

    # ── Helpers ─────────────────────────────────────────────────────────────
    @staticmethod
    def items(payload: Any) -> list[Any]:
        """Normalize a list response to a plain list, tolerating both a bare JSON
        array and a `{"data": [...]}` envelope (the doc shows both shapes across
        endpoints)."""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                return data
        return []


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop None-valued keys so optional fields are omitted from the request
    body (a key set to None is treated as 'not provided')."""
    return {key: value for key, value in payload.items() if value is not None}


def _recurring_payload(
    frequency: str,
    interval: int,
    end_type: str,
    days_of_week: list[int] | None,
    day_of_month: int | None,
    end_count: int | None,
    end_date: str | None,
    start_at: str | None,
    due_time: str | None,
    due_weekday: int | None,
    due_all_day: bool | None = None,
) -> dict[str, Any]:
    """Shape the shared recurring-task payload (set + update). `due_all_day` is
    mutually exclusive with `due_time` (the API 422s if both are sent)."""
    return _compact(
        {
            "frequency": frequency,
            "interval": interval,
            "end_type": end_type,
            "days_of_week": days_of_week,
            "day_of_month": day_of_month,
            "end_count": end_count,
            "end_date": end_date,
            "start_at": start_at,
            "due_time": due_time,
            "due_weekday": due_weekday,
            "due_all_day": due_all_day,
        }
    )


def _project_payload(
    name: str | None,
    short_code: str | None,
    color: str | None,
    type: str | None,
) -> dict[str, Any]:
    """Shape fields shared by project create and update."""
    return _compact(
        {
            "name": name,
            "short_code": short_code,
            "color": color,
            "type": type,
        }
    )


def _validate_legacy_project_options(
    is_hidden: bool | None,
    index_pages: bool | None,
    creating: bool,
) -> None:
    """Reject released flags the current API cannot honor."""
    if is_hidden is not None:
        raise RundeskError(
            "usage",
            "project visibility was retired; --hidden is no longer supported",
        )
    if creating and index_pages is False:
        raise RundeskError(
            "usage",
            "new projects always enable page indexing; create it, then use "
            "`projects update <id> --no-index-pages`",
        )


def _resolve_desk_assignment(
    assignee_type: str | None,
    assignee_actor_id: int | None,
    owner_type: str | None,
    owner_actor_id: int | None,
) -> tuple[str | None, int | None]:
    """Map 0.2 owner-named aliases to the API's assignee fields."""
    if assignee_type is not None and owner_type is not None:
        raise RundeskError("usage", "choose --assignee-type or --owner-type, not both")
    if assignee_actor_id is not None and owner_actor_id is not None:
        raise RundeskError(
            "usage", "choose --assignee-actor-id or --owner-actor-id, not both",
        )
    resolved_type = assignee_type if assignee_type is not None else owner_type
    resolved_actor_id = (
        assignee_actor_id if assignee_actor_id is not None else owner_actor_id
    )
    return resolved_type, resolved_actor_id


def _desk_payload(
    name: str | None,
    assignee_type: str | None = None,
    assignee_actor_id: int | None = None,
    owner_id: int | None = None,
    project_ids: list[int] | None = None,
    brief: str | None = None,
    rules: str | None = None,
    memory: str | None = None,
) -> dict[str, Any]:
    """Shape the shared desk assignment and project payload."""
    return _compact(
        {
            "name": name,
            "assignee_type": assignee_type,
            "assignee_actor_id": assignee_actor_id,
            "owner_id": owner_id,
            "project_ids": project_ids,
            "brief": brief,
            "rules": rules,
            "memory": memory,
        }
    )


def _safe_read(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - best-effort error detail only
        return ""
    raw = raw.strip()
    return raw[:500]

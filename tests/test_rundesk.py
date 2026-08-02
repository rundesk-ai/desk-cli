#!/usr/bin/env python3
"""Offline tests for the Rundesk integration (no network, no real account).

Covers: URL building (incl. ?format=text and ?meta= JSON encoding), env-key
resolution via the dotenv-reuse loader, single-key CLI client construction,
RundeskError → exit-code mapping, and request payload shaping for patch_page / create_page /
get_desk_inbox / get_desk_mentions / list_task_comments / create_task / update_task /
set_task_recurring / create_desk (the real desk field set) — verified by
monkeypatching the transport so nothing leaves the process.

Run: python3 tests/test_rundesk.py
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "desk_cli"))

import client as client_mod  # noqa: E402
import rundesk as rundesk_mod  # noqa: E402
from client import RundeskClient, RundeskError, load_dotenv  # noqa: E402


def _http_error(code: int, body: bytes = b'{"message":"boom"}'):
    """Build a fake_urlopen that raises an HTTPError with `code`/`body`."""

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, code, "err", {}, io.BytesIO(body))

    return fake_urlopen


@contextlib.contextmanager
def patched_cli_client():
    """Patch rundesk.RundeskClient with a MagicMock so `main` makes no network
    call. Yields (class_mock, instance_mock); the class is only *constructed*
    once the confirm gate passes, so `class_mock.assert_not_called()` proves a
    gated command aborted before touching the client.

    Exports a bare RUNDESK_API_KEY so no real .env leaks into these wiring
    tests (one key = one workspace; there is no profile selection)."""
    with mock.patch.dict(os.environ, {"RUNDESK_API_KEY": "cli-test-key"}, clear=False):
        with mock.patch.object(rundesk_mod, "RundeskClient") as cls:
            # Handlers print their (mock) results; swallow that to keep output clean.
            with contextlib.redirect_stdout(io.StringIO()):
                yield cls, cls.return_value


def make_client() -> RundeskClient:
    """A client with explicit config so no env/.env is read."""
    return RundeskClient(base_url="https://rundesk.example.com/", api_key="test-key")


class RecordingTransport:
    """Captures the single request a method issues and returns a canned body.

    Installed by monkeypatching `RundeskClient.request` is too coarse (it hides
    payload shaping under test), so instead we monkeypatch `_send` to capture the
    prepared urllib Request and short-circuit the network.
    """

    def __init__(self, response_body: object = None):
        self.calls: list[dict] = []
        self.response_body = response_body if response_body is not None else {"ok": True}

    def __call__(self, req, method, path, as_text):
        payload = None
        if req.data:
            try:
                payload = json.loads(req.data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                payload = req.data
        self.calls.append(
            {
                "method": method,
                "path": path,
                "url": req.full_url,
                "headers": dict(req.header_items()),
                "payload": payload,
                "as_text": as_text,
            }
        )
        if as_text:
            return "text-response"
        return self.response_body

    @property
    def last(self) -> dict:
        return self.calls[-1]


class URLBuildingTests(unittest.TestCase):
    def setUp(self):
        self.client = make_client()

    def test_base_and_prefix(self):
        url = self.client.build_url("/me")
        self.assertEqual(url, "https://rundesk.example.com/api/v1/me")

    def test_trailing_slash_stripped(self):
        c = RundeskClient(base_url="https://x.test/", api_key="k")
        self.assertEqual(c.build_url("/desk"), "https://x.test/api/v1/desk")

    def test_format_text_added(self):
        url = self.client.build_url("/tasks", as_text=True)
        self.assertTrue(url.endswith("/api/v1/tasks?format=text"))

    def test_none_params_dropped(self):
        url = self.client.build_url("/tasks", params={"status": "todo", "project_id": None})
        self.assertIn("status=todo", url)
        self.assertNotIn("project_id", url)

    def test_meta_json_encoding(self):
        transport = RecordingTransport([])
        self.client._send = transport
        self.client.get_pages(7, meta={"page_role": "rules", "status": "done"})
        url = transport.last["url"]
        # meta is compact, sort_keys JSON, URL-encoded.
        self.assertIn("meta=", url)
        self.assertIn("%22page_role%22%3A%22rules%22", url)
        self.assertIn("/projects/7/pages", transport.last["path"])

    def test_include_body_and_chars(self):
        transport = RecordingTransport([])
        self.client._send = transport
        self.client.get_pages(3, include_body=True, body_chars=120)
        url = transport.last["url"]
        self.assertIn("include_body=1", url)
        self.assertIn("body_chars=120", url)

    def test_frontmatter_only_forces_body_off(self):
        transport = RecordingTransport([])
        self.client._send = transport
        self.client.get_pages(3, include_body=True, frontmatter_only=True)
        self.assertNotIn("include_body", transport.last["url"])


class EnvResolutionTests(unittest.TestCase):
    def test_dotenv_does_not_overwrite_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                'RUNDESK_BASE_URL="https://from-file.test"\nRUNDESK_API_KEY=file-key\n',
                encoding="utf-8",
            )
            prior = {k: os.environ.get(k) for k in ("RUNDESK_BASE_URL", "RUNDESK_API_KEY")}
            try:
                os.environ["RUNDESK_API_KEY"] = "already-set"
                os.environ.pop("RUNDESK_BASE_URL", None)
                load_dotenv(env_path)
                # already-set wins; missing one is filled from file.
                self.assertEqual(os.environ["RUNDESK_API_KEY"], "already-set")
                self.assertEqual(os.environ["RUNDESK_BASE_URL"], "https://from-file.test")
            finally:
                for k, v in prior.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

    def test_client_resolves_from_env_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("RUNDESK_BASE_URL=https://envfile.test\nRUNDESK_API_KEY=envfile-key\n", encoding="utf-8")
            prior = {k: os.environ.get(k) for k in ("RUNDESK_BASE_URL", "RUNDESK_API_KEY")}
            try:
                os.environ.pop("RUNDESK_BASE_URL", None)
                os.environ.pop("RUNDESK_API_KEY", None)
                c = RundeskClient(env_file=str(env_path))
                self.assertEqual(c.base_url, "https://envfile.test")
                self.assertEqual(c.api_key, "envfile-key")
            finally:
                for k, v in prior.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

    def test_missing_key_raises_no_key(self):
        c = RundeskClient(base_url="https://x.test", api_key="")
        with self.assertRaises(RundeskError) as ctx:
            c.request("GET", "/me")
        self.assertEqual(ctx.exception.kind, "no_key")
        self.assertEqual(ctx.exception.exit_code, 2)

    def test_missing_base_url_raises_usage(self):
        c = RundeskClient(base_url="", api_key="k")
        with self.assertRaises(RundeskError) as ctx:
            c.request("GET", "/me")
        self.assertEqual(ctx.exception.kind, "usage")
        self.assertEqual(ctx.exception.exit_code, 2)


class ExitCodeMappingTests(unittest.TestCase):
    def test_kind_to_exit(self):
        cases = {
            "usage": 2,
            "no_key": 2,
            "pending": 2,
            "auth": 3,
            "forbidden": 4,
            "not_found": 5,
            "unprocessable": 6,
            "network": 7,
            "http": 1,
            "totally-unknown": 1,
        }
        for kind, code in cases.items():
            self.assertEqual(RundeskError(kind).exit_code, code, kind)

    def test_http_status_to_kind(self):
        client = make_client()

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 422, "Unprocessable", {}, io.BytesIO(b'{"message":"bad"}'))

        orig = client_mod.urllib.request.urlopen
        client_mod.urllib.request.urlopen = fake_urlopen
        try:
            with self.assertRaises(RundeskError) as ctx:
                client.request("POST", "/tasks", payload={"title": "x"})
            self.assertEqual(ctx.exception.kind, "unprocessable")
            self.assertEqual(ctx.exception.exit_code, 6)
        finally:
            client_mod.urllib.request.urlopen = orig

    def test_network_error_mapped(self):
        client = make_client()

        def fake_urlopen(req, timeout=None):
            raise urllib.error.URLError("connection refused")

        orig = client_mod.urllib.request.urlopen
        client_mod.urllib.request.urlopen = fake_urlopen
        try:
            with self.assertRaises(RundeskError) as ctx:
                client.request("GET", "/me")
            self.assertEqual(ctx.exception.kind, "network")
            self.assertEqual(ctx.exception.exit_code, 7)
        finally:
            client_mod.urllib.request.urlopen = orig


class PayloadShapingTests(unittest.TestCase):
    def setUp(self):
        self.client = make_client()
        self.transport = RecordingTransport()
        self.client._send = self.transport

    def test_patch_page_replace(self):
        self.client.patch_page(1, 2, mode="replace", old_str="foo", new_str="bar", description="lbl")
        call = self.transport.last
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["path"], "/projects/1/pages/2/patch")
        self.assertEqual(
            call["payload"], {"mode": "replace", "old_str": "foo", "new_str": "bar", "description": "lbl"}
        )

    def test_patch_page_replace_requires_old_str(self):
        with self.assertRaises(RundeskError) as ctx:
            self.client.patch_page(1, 2, mode="replace", new_str="bar")
        self.assertEqual(ctx.exception.kind, "usage")

    def test_patch_page_append(self):
        self.client.patch_page(1, 2, mode="append", content="more text")
        self.assertEqual(self.transport.last["payload"], {"mode": "append", "content": "more text"})

    def test_patch_page_append_requires_content(self):
        with self.assertRaises(RundeskError):
            self.client.patch_page(1, 2, mode="append")

    def test_patch_page_bad_mode(self):
        with self.assertRaises(RundeskError):
            self.client.patch_page(1, 2, mode="upsert")

    def test_create_page_minimal(self):
        self.client.create_page(5, body="# Title\n\nhello")
        call = self.transport.last
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["path"], "/projects/5/pages")
        self.assertEqual(call["payload"], {"body": "# Title\n\nhello"})

    def test_create_page_with_parent_and_sort(self):
        self.client.create_page(5, body="x", parent_page_id=9, sort_order=2)
        self.assertEqual(self.transport.last["payload"], {"body": "x", "parent_page_id": 9, "sort_order": 2})

    def test_create_page_allows_null_body(self):
        self.client.create_page(5, body=None)
        self.assertEqual(self.transport.last["payload"], {"body": None})

    def test_get_desk_inbox_default(self):
        self.client.get_desk_inbox()
        call = self.transport.last
        self.assertEqual(call["method"], "GET")
        self.assertEqual(call["path"], "/desk/inbox")
        # No filter params on the default this-week view.
        self.assertNotIn("week=", call["url"])
        self.assertNotIn("unscheduled", call["url"])

    def test_get_desk_inbox_week(self):
        self.client.get_desk_inbox(week=42)
        self.assertEqual(self.transport.last["path"], "/desk/inbox")
        self.assertIn("week=42", self.transport.last["url"])

    def test_get_desk_inbox_unscheduled(self):
        self.client.get_desk_inbox(unscheduled=True)
        self.assertIn("unscheduled=1", self.transport.last["url"])

    def test_get_desk_mentions_default(self):
        self.client.get_desk_mentions()
        call = self.transport.last
        self.assertEqual(call["method"], "GET")
        self.assertEqual(call["path"], "/desk/mentions")
        self.assertNotIn("limit=", call["url"])
        # Every read on this client returns the parsed payload when called bare;
        # a lone method defaulting to text hands a library caller a string where
        # its siblings hand back a dict, and nothing says so at the call site.
        self.assertFalse(call["as_text"])

    def test_get_desk_mentions_limit(self):
        self.client.get_desk_mentions(limit=5)
        call = self.transport.last
        self.assertEqual(call["path"], "/desk/mentions")
        self.assertIn("limit=5", call["url"])

    def test_list_task_comments(self):
        self.client.list_task_comments(8)
        call = self.transport.last
        self.assertEqual(call["method"], "GET")
        self.assertEqual(call["path"], "/tasks/8/comments")

    def test_create_task_comment(self):
        self.client.create_task_comment(8, "done")
        call = self.transport.last
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["path"], "/tasks/8/comments")
        self.assertEqual(call["payload"], {"body": "done"})

    def test_update_task_omits_task_week_id(self):
        self.client.update_task(8, title="New", project_id=3)
        call = self.transport.last
        self.assertEqual(call["method"], "PUT")
        self.assertEqual(call["path"], "/tasks/8")
        self.assertEqual(call["payload"], {"title": "New", "project_id": 3})
        self.assertNotIn("task_week_id", call["payload"])

    def test_create_task_drops_none(self):
        self.client.create_task(title="Task A", project_id=3)
        self.assertEqual(self.transport.last["payload"], {"title": "Task A", "project_id": 3})

    def test_move_task_week_inbox_keeps_null(self):
        self.client.move_task_week(8, None)
        call = self.transport.last
        self.assertEqual(call["path"], "/tasks/8/move")
        self.assertEqual(call["payload"], {"task_week_id": None})

    def test_set_task_deadline_all_day(self):
        self.client.set_task_deadline(8, due_at="2026-05-01T00:00:00Z", is_all_day_due=True)
        self.assertEqual(
            self.transport.last["payload"], {"due_at": "2026-05-01T00:00:00Z", "is_all_day_due": True}
        )

    def test_set_task_recurring_compacts(self):
        self.client.set_task_recurring(8, frequency="weekly", interval=1, end_type="never", days_of_week=[1, 3])
        call = self.transport.last
        self.assertEqual(call["path"], "/tasks/8/recurring")
        self.assertEqual(
            call["payload"],
            {"frequency": "weekly", "interval": 1, "end_type": "never", "days_of_week": [1, 3]},
        )

    def test_update_task_recurring_uses_put(self):
        self.client.update_task_recurring(8, frequency="daily", interval=2, end_type="count", end_count=5)
        self.assertEqual(self.transport.last["method"], "PUT")

    def test_create_project_strips_none(self):
        self.client.create_project(name="Proj", short_code="PR")
        self.assertEqual(self.transport.last["payload"], {"name": "Proj", "short_code": "PR"})

    def test_create_desk_owner(self):
        self.client.create_desk(
            name="Support", owner_type="agent", owner_actor_id=11, project_ids=[3, 7]
        )
        call = self.transport.last
        self.assertEqual(call["path"], "/desks")
        self.assertEqual(
            call["payload"],
            {"name": "Support", "owner_type": "agent", "owner_actor_id": 11, "project_ids": [3, 7]},
        )

    def test_create_desk_key(self):
        self.client.create_desk_key(3, name="worker", expires_at="2027-01-01T00:00:00Z")
        call = self.transport.last
        self.assertEqual(call["path"], "/desks/3/keys")
        self.assertEqual(call["payload"], {"name": "worker", "expires_at": "2027-01-01T00:00:00Z"})

    def test_attach_project(self):
        self.client.attach_project(3, 7)
        self.assertEqual(self.transport.last["path"], "/desks/3/projects/7")
        self.assertEqual(self.transport.last["method"], "POST")

    def test_reorder_pages(self):
        self.client.reorder_pages(5, [3, 1, 2])
        call = self.transport.last
        self.assertEqual(call["method"], "PATCH")
        self.assertEqual(call["path"], "/projects/5/pages/reorder")
        self.assertEqual(call["payload"], {"ids": [3, 1, 2]})

    def test_authorization_header_present(self):
        self.client.get_account()
        self.assertEqual(self.transport.last["headers"].get("Authorization"), "Bearer test-key")


class TransportResponseTests(unittest.TestCase):
    def test_text_mode_returns_raw(self):
        client = make_client()

        def fake_urlopen(req, timeout=None):
            return _FakeResponse(b"id|name\n1|x")

        orig = client_mod.urllib.request.urlopen
        client_mod.urllib.request.urlopen = fake_urlopen
        try:
            out = client.get_account(as_text=True)
            self.assertEqual(out, "id|name\n1|x")
        finally:
            client_mod.urllib.request.urlopen = orig

    def test_empty_body_returns_none(self):
        client = make_client()

        def fake_urlopen(req, timeout=None):
            return _FakeResponse(b"")

        orig = client_mod.urllib.request.urlopen
        client_mod.urllib.request.urlopen = fake_urlopen
        try:
            self.assertIsNone(client.delete_task(1))
        finally:
            client_mod.urllib.request.urlopen = orig

    def test_items_normalizes(self):
        self.assertEqual(RundeskClient.items([1, 2]), [1, 2])
        self.assertEqual(RundeskClient.items({"data": [3]}), [3])
        self.assertEqual(RundeskClient.items({"nope": 1}), [])


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# ── client.py: HTTP status → kind mapping & non-JSON body ────────────────────
class HttpStatusMappingTests(unittest.TestCase):
    def _assert_status(self, code: int, kind: str, exit_code: int):
        client = make_client()
        with mock.patch.object(client_mod.urllib.request, "urlopen", _http_error(code)):
            with self.assertRaises(RundeskError) as ctx:
                client.request("GET", "/me")
        self.assertEqual(ctx.exception.kind, kind, code)
        self.assertEqual(ctx.exception.exit_code, exit_code, code)

    def test_401_auth(self):
        self._assert_status(401, "auth", 3)

    def test_403_forbidden(self):
        self._assert_status(403, "forbidden", 4)

    def test_404_not_found(self):
        self._assert_status(404, "not_found", 5)

    def test_422_unprocessable(self):
        self._assert_status(422, "unprocessable", 6)

    def test_unmapped_500_http(self):
        self._assert_status(500, "http", 1)

    def test_non_json_200_body_raises_http(self):
        client = make_client()

        def fake_urlopen(req, timeout=None):
            return _FakeResponse(b"<html>maintenance</html>")

        with mock.patch.object(client_mod.urllib.request, "urlopen", fake_urlopen):
            with self.assertRaises(RundeskError) as ctx:
                client.get_account()
        self.assertEqual(ctx.exception.kind, "http")
        self.assertEqual(ctx.exception.exit_code, 1)


# ── client.py: multipart upload framing ──────────────────────────────────────
class MultipartUploadTests(unittest.TestCase):
    def test_upload_missing_file_raises_usage(self):
        client = make_client()
        with self.assertRaises(RundeskError) as ctx:
            client.upload_task_asset(1, "/no/such/file.png")
        self.assertEqual(ctx.exception.kind, "usage")
        self.assertEqual(ctx.exception.exit_code, 2)

    def test_multipart_framing_and_auth_header(self):
        client = make_client()
        transport = RecordingTransport({"id": 1})
        client._send = transport
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "note.txt"
            src.write_bytes(b"hello bytes")
            client.upload_project_asset(9, src)

        call = transport.last
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["path"], "/projects/9/assets")
        # Authorization rides on the multipart request.
        self.assertEqual(call["headers"].get("Authorization"), "Bearer test-key")
        # urllib capitalizes header keys: "Content-Type" → "Content-type".
        content_type = call["headers"].get("Content-type", "")
        self.assertTrue(content_type.startswith("multipart/form-data; boundary="))
        boundary = content_type.split("boundary=", 1)[1]
        body = call["payload"]
        self.assertIsInstance(body, (bytes, bytearray))
        text = body.decode("utf-8")
        self.assertIn(f"--{boundary}", text)
        self.assertIn('Content-Disposition: form-data; name="file"; filename="note.txt"', text)
        self.assertIn("Content-Type: text/plain", text)
        self.assertIn("hello bytes", text)

    def test_upload_page_asset_path(self):
        client = make_client()
        transport = RecordingTransport({"id": 1})
        client._send = transport
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "x.bin"
            src.write_bytes(b"\x00\x01")
            client.upload_page_asset(4, 5, src)
        self.assertEqual(transport.last["path"], "/projects/4/pages/5/assets")


# ── client.py: write/delete method method+path+payload ───────────────────────
class WriteDeleteMethodTests(unittest.TestCase):
    def setUp(self):
        self.client = make_client()
        self.transport = RecordingTransport()
        self.client._send = self.transport

    def _assert(self, method, path, payload="__none__"):
        call = self.transport.last
        self.assertEqual(call["method"], method)
        self.assertEqual(call["path"], path)
        if payload != "__none__":
            self.assertEqual(call["payload"], payload)

    def test_update_project(self):
        self.client.update_project(7, name="New", color="#abc")
        self._assert("PUT", "/projects/7", {"name": "New", "color": "#abc"})

    def test_delete_project(self):
        self.client.delete_project(7)
        self._assert("DELETE", "/projects/7", None)

    def test_update_page_body_only(self):
        self.client.update_page(1, 2, body="hello")
        self._assert("PUT", "/projects/1/pages/2", {"body": "hello"})

    def test_update_page_frontmatter_only(self):
        self.client.update_page(1, 2, frontmatter="role: rules")
        self._assert("PUT", "/projects/1/pages/2", {"frontmatter": "role: rules"})

    def test_update_page_both(self):
        self.client.update_page(1, 2, body="b", frontmatter="role: rules", description="d")
        self._assert(
            "PUT", "/projects/1/pages/2", {"body": "b", "frontmatter": "role: rules", "description": "d"}
        )

    def test_delete_page(self):
        self.client.delete_page(1, 2)
        self._assert("DELETE", "/projects/1/pages/2", None)

    def test_move_task_project_null_keeps_key(self):
        self.client.move_task_project(8, None)
        self._assert("POST", "/tasks/8/move-project", {"project_id": None})

    def test_move_task_project_with_id(self):
        self.client.move_task_project(8, 4)
        self._assert("POST", "/tasks/8/move-project", {"project_id": 4})

    def test_remove_task_deadline(self):
        self.client.remove_task_deadline(8)
        self._assert("DELETE", "/tasks/8/deadline", None)

    def test_remove_task_recurring(self):
        self.client.remove_task_recurring(8)
        self._assert("DELETE", "/tasks/8/recurring", None)

    def test_update_desk(self):
        self.client.update_desk(3, name="X", owner_type="person", owner_actor_id=5)
        self._assert("PUT", "/desks/3", {"name": "X", "owner_type": "person", "owner_actor_id": 5})

    def test_delete_desk(self):
        self.client.delete_desk(3)
        self._assert("DELETE", "/desks/3", None)

    def test_detach_project(self):
        self.client.detach_project(3, 7)
        self._assert("DELETE", "/desks/3/projects/7", None)

    def test_rename_task_asset(self):
        self.client.rename_task_asset(1, 2, "new.txt")
        self._assert("PATCH", "/tasks/1/assets/2", {"filename": "new.txt"})

    def test_rename_project_asset(self):
        self.client.rename_project_asset(1, 2, "new.txt")
        self._assert("PATCH", "/projects/1/assets/2", {"filename": "new.txt"})

    def test_rename_page_asset(self):
        self.client.rename_page_asset(1, 2, 3, "new.txt")
        self._assert("PATCH", "/projects/1/pages/2/assets/3", {"filename": "new.txt"})

    def test_delete_task_asset(self):
        self.client.delete_task_asset(1, 2)
        self._assert("DELETE", "/tasks/1/assets/2", None)

    def test_delete_project_asset(self):
        self.client.delete_project_asset(1, 2)
        self._assert("DELETE", "/projects/1/assets/2", None)

    def test_delete_page_asset(self):
        self.client.delete_page_asset(1, 2, 3)
        self._assert("DELETE", "/projects/1/pages/2/assets/3", None)


# ── client.py: state-change POSTs & read param wiring ────────────────────────
class StateAndReadWiringTests(unittest.TestCase):
    def setUp(self):
        self.client = make_client()
        self.transport = RecordingTransport()
        self.client._send = self.transport

    def test_archive_project(self):
        self.client.archive_project(7)
        self.assertEqual(self.transport.last["method"], "POST")
        self.assertEqual(self.transport.last["path"], "/projects/7/archive")

    def test_unarchive_project(self):
        self.client.unarchive_project(7)
        self.assertEqual(self.transport.last["method"], "POST")
        self.assertEqual(self.transport.last["path"], "/projects/7/unarchive")

    def test_retire_desk(self):
        self.client.retire_desk(3)
        self.assertEqual(self.transport.last["method"], "POST")
        self.assertEqual(self.transport.last["path"], "/desks/3/retire")

    def test_unretire_desk(self):
        self.client.unretire_desk(3)
        self.assertEqual(self.transport.last["method"], "POST")
        self.assertEqual(self.transport.last["path"], "/desks/3/unretire")

    def test_list_desks_include_retired_true(self):
        self.client.list_desks(include_retired=True)
        self.assertIn("include_retired=1", self.transport.last["url"])
        self.assertEqual(self.transport.last["path"], "/desks")

    def test_list_desks_include_retired_false(self):
        self.client.list_desks(include_retired=False)
        self.assertNotIn("include_retired", self.transport.last["url"])

    def test_get_account_uses_me_path(self):
        self.client.get_account()
        self.assertEqual(self.transport.last["path"], "/me")
        self.assertTrue(self.transport.last["url"].endswith("/api/v1/me"))

    def test_get_week_current(self):
        self.client.get_week()
        self.assertEqual(self.transport.last["path"], "/week")

    def test_get_week_dated(self):
        self.client.get_week(date="2026-01-05")
        self.assertEqual(self.transport.last["path"], "/weeks/2026-01-05")

    def test_search_pages_param_wiring(self):
        self.client.search_pages(q="hello world", project_type="professional", project_id=4, limit=10)
        url = self.transport.last["url"]
        self.assertEqual(self.transport.last["path"], "/pages/search")
        self.assertIn("project_type=professional", url)
        self.assertIn("project_id=4", url)
        self.assertIn("limit=10", url)
        self.assertIn("q=hello+world", url)

    def test_get_page_frontmatter_only(self):
        self.client.get_page(1, 2, frontmatter_only=True)
        self.assertEqual(self.transport.last["path"], "/projects/1/pages/2")
        self.assertIn("frontmatter_only=1", self.transport.last["url"])

    def test_get_changelog_all(self):
        self.client.get_changelog(all=True)
        url = self.transport.last["url"]
        self.assertIn("all=1", url)
        self.assertNotIn("limit", url)

    def test_list_tasks_multi_param(self):
        self.client.list_tasks(status="todo", project_id=3, task_week_id=9, is_recurring_template=1)
        url = self.transport.last["url"]
        self.assertEqual(self.transport.last["path"], "/tasks")
        self.assertIn("status=todo", url)
        self.assertIn("project_id=3", url)
        self.assertIn("task_week_id=9", url)
        self.assertIn("is_recurring_template=1", url)

    def test_list_tasks_inbox(self):
        self.client.list_tasks(inbox=1)
        url = self.transport.last["url"]
        self.assertEqual(self.transport.last["path"], "/tasks")
        self.assertIn("inbox=1", url)

    def test_list_projects_multi_param(self):
        self.client.list_projects(search="foo", type="personal", is_archived=1)
        url = self.transport.last["url"]
        self.assertEqual(self.transport.last["path"], "/projects")
        self.assertIn("search=foo", url)
        self.assertIn("type=personal", url)
        self.assertIn("is_archived=1", url)

    def test_list_project_assets_multi_param(self):
        self.client.list_project_assets(5, search="img", sort="newest", page=2)
        url = self.transport.last["url"]
        self.assertEqual(self.transport.last["path"], "/projects/5/assets")
        self.assertIn("search=img", url)
        self.assertIn("sort=newest", url)
        self.assertIn("page=2", url)


# ── client.py: load_dotenv & _safe_read ──────────────────────────────────────
class LoadDotenvTests(unittest.TestCase):
    def test_missing_file_early_return(self):
        # Should not raise on a non-existent path.
        load_dotenv(Path("/no/such/.env.nope"))

    def test_skips_comments_blanks_and_no_equals(self):
        keys = ("RD_TEST_A", "RD_TEST_B", "RD_TEST_NOEQ")
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "# a comment\n"
                "\n"
                "   \n"
                "JUSTAKEYNOEQUALS\n"
                "RD_TEST_A=plain\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {}, clear=False):
                for k in keys:
                    os.environ.pop(k, None)
                load_dotenv(env_path)
                self.assertEqual(os.environ.get("RD_TEST_A"), "plain")
                self.assertNotIn("JUSTAKEYNOEQUALS", os.environ)

    def test_single_quote_value_stripped(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("RD_TEST_Q='quoted-value'\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("RD_TEST_Q", None)
                load_dotenv(env_path)
                self.assertEqual(os.environ.get("RD_TEST_Q"), "quoted-value")


class SafeReadTests(unittest.TestCase):
    def test_exception_suppressed(self):
        class Boom:
            def read(self):
                raise OSError("nope")

        self.assertEqual(client_mod._safe_read(Boom()), "")

    def test_truncates_to_500(self):
        exc = urllib.error.HTTPError(
            "http://x", 500, "err", {}, io.BytesIO(b"x" * 600)
        )
        out = client_mod._safe_read(exc)
        self.assertEqual(len(out), 500)


# ── rundesk.py CLI: --confirm gate ───────────────────────────────────────────
class ConfirmGateTests(unittest.TestCase):
    # (argv-without-confirm, client-method-name, args-tail-for-confirm)
    CASES = [
        (["projects", "delete", "5"], "delete_project"),
        (["page", "delete", "5", "6"], "delete_page"),
        (["tasks", "delete", "5"], "delete_task"),
        (["desks", "delete", "5"], "delete_desk"),
        (["asset", "delete-task", "5", "6"], "delete_task_asset"),
        (["asset", "delete-project", "5", "6"], "delete_project_asset"),
        (["asset", "delete-page", "5", "6", "7"], "delete_page_asset"),
    ]

    def test_without_confirm_aborts_before_client(self):
        for argv, method in self.CASES:
            with self.subTest(argv=argv):
                with patched_cli_client() as (cls, inst):
                    rc = rundesk_mod.main(argv)
                self.assertEqual(rc, 2, argv)
                cls.assert_not_called()  # client never constructed
                getattr(inst, method).assert_not_called()

    def test_with_confirm_proceeds(self):
        for argv, method in self.CASES:
            with self.subTest(argv=argv):
                with patched_cli_client() as (cls, inst):
                    rc = rundesk_mod.main(argv + ["--confirm"])
                self.assertEqual(rc, 0, argv)
                cls.assert_called_once()
                getattr(inst, method).assert_called_once()


# ── rundesk.py CLI: main error propagation & new error handling ──────────────
class CliErrorHandlingTests(unittest.TestCase):
    def test_main_returns_exit_code_on_rundesk_error(self):
        with patched_cli_client() as (_cls, inst):
            inst.get_account.side_effect = RundeskError("forbidden")
            rc = rundesk_mod.main(["account"])
        self.assertEqual(rc, 4)

    def test_read_body_missing_file_raises_usage(self):
        ns = argparse.Namespace(body_file="/no/such/body.md", body=None)
        with self.assertRaises(RundeskError) as ctx:
            rundesk_mod._read_body(ns)
        self.assertEqual(ctx.exception.kind, "usage")
        self.assertEqual(ctx.exception.exit_code, 2)

    def test_page_create_bad_body_file_exits_usage(self):
        with patched_cli_client() as (_cls, inst):
            rc = rundesk_mod.main(["page", "create", "5", "--body-file", "/no/such/body.md"])
        self.assertEqual(rc, 2)
        inst.create_page.assert_not_called()

    def test_page_list_invalid_meta_exits_usage(self):
        with patched_cli_client() as (_cls, inst):
            rc = rundesk_mod.main(["page", "list", "5", "--meta", "{bad json"])
        self.assertEqual(rc, 2)
        inst.get_pages.assert_not_called()


# ── rundesk.py CLI: argument → client-call wiring ────────────────────────────
class CliWiringTests(unittest.TestCase):
    def test_page_list_role_shorthand(self):
        with patched_cli_client() as (_cls, inst):
            rundesk_mod.main(["page", "list", "5", "--role", "rules"])
        _, kwargs = inst.get_pages.call_args
        self.assertEqual(kwargs.get("meta"), {"page_role": "rules"})

    def test_page_list_valid_meta_parsed(self):
        with patched_cli_client() as (_cls, inst):
            rundesk_mod.main(["page", "list", "5", "--meta", '{"status":"done"}'])
        _, kwargs = inst.get_pages.call_args
        self.assertEqual(kwargs.get("meta"), {"status": "done"})

    def test_tasks_list_inbox_passes_flag(self):
        with patched_cli_client() as (_cls, inst):
            rundesk_mod.main(["tasks", "list", "--inbox"])
        _, kwargs = inst.list_tasks.call_args
        self.assertEqual(kwargs.get("inbox"), 1)

    def test_tasks_list_no_inbox_omits_flag(self):
        with patched_cli_client() as (_cls, inst):
            rundesk_mod.main(["tasks", "list"])
        _, kwargs = inst.list_tasks.call_args
        self.assertIsNone(kwargs.get("inbox"))

    def test_tasks_move_week_inbox_null(self):
        with patched_cli_client() as (_cls, inst):
            rundesk_mod.main(["tasks", "move-week", "8", "--inbox"])
        args, _ = inst.move_task_week.call_args
        self.assertEqual(args, ("8", None))

    def test_tasks_move_project_none_null(self):
        with patched_cli_client() as (_cls, inst):
            rundesk_mod.main(["tasks", "move-project", "8", "--none"])
        args, _ = inst.move_task_project.call_args
        self.assertEqual(args, ("8", None))

    def test_desks_create_field_wiring(self):
        with patched_cli_client() as (_cls, inst):
            rundesk_mod.main(
                ["desks", "create", "--name", "Support", "--owner-type", "agent",
                 "--owner-actor-id", "11", "--project-ids", "3,7"]
            )
        _, kwargs = inst.create_desk.call_args
        self.assertEqual(kwargs.get("owner_type"), "agent")
        self.assertEqual(kwargs.get("owner_actor_id"), 11)
        self.assertEqual(kwargs.get("project_ids"), [3, 7])

    def test_desks_update_project_ids_parsed(self):
        with patched_cli_client() as (_cls, inst):
            rundesk_mod.main(["desks", "update", "3", "--project-ids", "1, 2 ,3"])
        _, kwargs = inst.update_desk.call_args
        self.assertEqual(kwargs.get("project_ids"), [1, 2, 3])

    def test_desks_update_no_project_ids_is_none(self):
        with patched_cli_client() as (_cls, inst):
            rundesk_mod.main(["desks", "update", "3", "--name", "X"])
        _, kwargs = inst.update_desk.call_args
        self.assertIsNone(kwargs.get("project_ids"))

    def test_desks_update_empty_project_ids_is_none(self):
        # An empty --project-ids must be omitted, not sent as [] (which would
        # detach every project from the desk).
        with patched_cli_client() as (_cls, inst):
            rundesk_mod.main(["desks", "update", "3", "--project-ids", ""])
        _, kwargs = inst.update_desk.call_args
        self.assertIsNone(kwargs.get("project_ids"))

    def test_desks_update_bad_project_ids_exits_usage(self):
        # A non-integer --project-ids gates the write: exit 2, update never called.
        with patched_cli_client() as (_cls, inst):
            rc = rundesk_mod.main(["desks", "update", "3", "--project-ids", "1,x,3"])
        self.assertEqual(rc, 2)
        inst.update_desk.assert_not_called()

    def test_desks_retire_routes(self):
        with patched_cli_client() as (_cls, inst):
            rundesk_mod.main(["desks", "retire", "9"])
        inst.retire_desk.assert_called_once_with("9")

    def test_desks_unretire_routes(self):
        with patched_cli_client() as (_cls, inst):
            rundesk_mod.main(["desks", "unretire", "9"])
        inst.unretire_desk.assert_called_once_with("9")

    def test_asset_get_routes(self):
        with patched_cli_client() as (_cls, inst):
            rundesk_mod.main(["asset", "get", "42"])
        inst.get_asset.assert_called_once_with("42")

    def test_asset_search_routes(self):
        with patched_cli_client() as (_cls, inst):
            rundesk_mod.main(["asset", "search", "--q", "logo", "--limit", "5"])
        _, kwargs = inst.search_project_assets.call_args
        self.assertEqual(kwargs.get("q"), "logo")
        self.assertEqual(kwargs.get("limit"), 5)

    def test_asset_delete_task_with_confirm_routes(self):
        with patched_cli_client() as (_cls, inst):
            rc = rundesk_mod.main(["asset", "delete-task", "1", "2", "--confirm"])
        self.assertEqual(rc, 0)
        inst.delete_task_asset.assert_called_once_with("1", "2")


# ── rundesk.py CLI: _emit / _wants_json helpers ──────────────────────────────
class EmitHelperTests(unittest.TestCase):
    def _capture(self, value, as_json=False):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rundesk_mod._emit(value, as_json)
        return buf.getvalue()

    def test_emit_str_rstrips_newlines(self):
        self.assertEqual(self._capture("line\n\n"), "line\n")

    def test_emit_json_branch_for_dict(self):
        out = self._capture({"b": 1, "a": 2})
        self.assertEqual(json.loads(out), {"b": 1, "a": 2})
        # sort_keys → "a" before "b".
        self.assertLess(out.index('"a"'), out.index('"b"'))

    def test_emit_json_forced_for_str(self):
        out = self._capture("plain", as_json=True)
        self.assertEqual(json.loads(out), "plain")

    def test_wants_json_true(self):
        self.assertTrue(rundesk_mod._wants_json(argparse.Namespace(json=True)))

    def test_wants_json_default_false(self):
        self.assertFalse(rundesk_mod._wants_json(argparse.Namespace()))


# ── rundesk.py CLI: single-key client construction ───────────────────────────
class CliClientConstructionTests(unittest.TestCase):
    """One key = one workspace/desk actor. main() builds the client straight from
    the env (launcher-injected RUNDESK_API_KEY or the local .env) — there is
    no profile selection to resolve."""

    NOENV = "/no/such/.env.nope"

    def test_main_builds_client_with_env_file_and_runs_handler(self):
        with mock.patch.object(rundesk_mod, "RundeskClient") as cls:
            with contextlib.redirect_stdout(io.StringIO()):
                rc = rundesk_mod.main(["--env-file", self.NOENV, "account"])
        self.assertEqual(rc, 0)
        _, kwargs = cls.call_args
        self.assertEqual(kwargs.get("env_file"), self.NOENV)
        self.assertNotIn("api_key", kwargs)  # no profile key is injected

    def test_handler_rundesk_error_maps_to_exit_code(self):
        client = mock.Mock()
        client.get_account.side_effect = RundeskError("not_found", "nope")
        with mock.patch.object(rundesk_mod, "RundeskClient", return_value=client):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = rundesk_mod.main(["account"])
        self.assertEqual(rc, 5)
        self.assertIn("error:", err.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)

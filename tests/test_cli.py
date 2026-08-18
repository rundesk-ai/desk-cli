#!/usr/bin/env python3
"""End-to-end coverage tests for the `desk` CLI wrapper (offline).

The centerpiece (`ApiEndpointCoverageTests`) auto-discovers EVERY leaf command in
the CLI's argument tree and dispatches each through `cli.main()` against a fake
HTTP transport, asserting the command (a) exits 0 and (b) issued a request that
carried the active profile's base URL and bearer key. It is self-maintaining: any
new endpoint added to the command tree is walked automatically, so
"every desk method has tests / all endpoints covered" stays true over time. A
companion gate proves every public RundeskClient method is reachable from the
command tree (no orphan endpoints).

The remaining classes cover the pieces test_rundesk.py doesn't: the local
`profile` / `update` commands, credential wiring, and `--confirm` delete-gating.

Run: python3 tests/test_cli.py
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

SRC = Path(__file__).resolve().parents[1] / "src" / "desk_cli"
sys.path.insert(0, str(SRC))

# Keep the passive "new version available" notice from making network calls while
# we walk every command; its own behavior is tested in test_profiles.py.
os.environ.setdefault("DESK_NO_UPDATE_CHECK", "1")

import cli  # noqa: E402
import client as client_mod  # noqa: E402
import profiles  # noqa: E402
import rundesk as api  # noqa: E402
from client import RundeskClient, RundeskError  # noqa: E402

BASE_URL = "https://example.test"
API_KEY = "SECRET-KEY-1234"

AGENT_GUIDE_HEADINGS = [
    "# AGENTS",
    "## Purpose",
    "## Before you work",
    "## Repository layout",
    "## Package and artifact contract",
    "## Safety and approval gates",
    "## Delegation",
    "## Architecture and conventions",
    "## Documentation duties",
    "## Build, test, and run",
    "## Pull requests and releases",
    "## Definition of done",
]

PR_TEMPLATE_HEADINGS = [
    "## Summary",
    "## Scope and compatibility",
    "## Critical risk",
    "## Validation",
    "## Repository gates",
    "## Release",
    "## Manual user path",
]

PR_TEMPLATE_ANCHORS = [
    "- [ ] `python3 tests/test_profiles.py && python3 tests/test_cli.py && python3 tests/test_rundesk.py` passes.",
    "- [ ] Required GitHub checks pass for the exact head commit.",
    "- [ ] The diff contains no credential, API key, account data, private-project language, owner-specific path, or unrelated artifact.",
    "- [ ] Runtime code remains Python 3.9+ and standard-library only, unless the owner approved a dependency.",
    "- [ ] API keys remain masked and stdout, stderr, prompts, JSON, and tests do not expose secrets.",
    "- [ ] Default text output, `--json`, command/flag behavior, and stored formats preserve their documented contracts, or the approved compatibility impact is stated above.",
    "- [ ] `README.md`, `manifest.json`, and `skills/` agree.",
]

ISSUE_TEMPLATE_HEADINGS = {
    "bug-report.md": [
        "## Problem", "## Reproduction", "## Expected behavior", "## Evidence",
        "## Environment", "## Scope and privacy",
    ],
    "change-proposal.md": [
        "## Problem", "## Desired outcome", "## Users and value",
        "## Scope and compatibility", "## Alternatives", "## Validation",
    ],
}

ISSUE_TEMPLATE_FRONTMATTER = {
    "bug-report.md": [
        "---", "name: Bug report", "about: Report reproducible incorrect behavior",
        'title: "[Bug] "', 'labels: ""', 'assignees: ""', "---",
    ],
    "change-proposal.md": [
        "---", "name: Change proposal",
        "about: Propose a skill, integration, command, or repository improvement",
        'title: "[Proposal] "', 'labels: ""', 'assignees: ""', "---",
    ],
}

ISSUE_TEMPLATE_DIGESTS = {
    "bug-report.md": "747da5c0682a73adc61c35407327fb174c648630e80278c275af4a4542da6caf",
    "change-proposal.md": "2fe6a1d651ce91af2c3d19e98eea150ca26f41ad9a1ed95a6466a692b73eb4d7",
}

# Command groups handled locally (never hit the API) — excluded from the walk.
LOCAL_COMMANDS = {"profile", "update", "uninstall", "help"}

# Positional dests that should be filled with a numeric id rather than "x".
ID_DESTS = {
    "project_id", "page_id", "task_id", "comment_id", "asset_id", "desk_id",
    "id", "ref", "week_id", "ids",
}

# The few leaves whose client method validates arg combos before requesting:
# a surgical page patch in `replace` mode needs old_str/new_str.
EXTRA_ARGS = {
    ("page", "patch"): ["--old-str", "x", "--new-str", "y"],
    ("tasks", "move-week"): ["--inbox"],
    ("tasks", "move-project"): ["--none"],
    ("asset", "update"): ["--filename", "x.txt"],
    ("page", "reorder"): ["1"],
}

POSITIONAL_VALUES = {
    (("user-mentions", "entity"), "type"): "task",
}


class _FakeResponse:
    def __init__(self, body: bytes = b"{}"):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _find_subparsers(parser: argparse.ArgumentParser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _leaves(parser, prefix=()):
    """Yield (command-path-tuple, leaf-parser) for every leaf in the tree."""
    sub = _find_subparsers(parser)
    if sub is None:
        yield prefix, parser
        return
    for name, subparser in sub.choices.items():
        yield from _leaves(subparser, prefix + (name,))


def _opt_value(action, tmpfile):
    if action.choices:
        return str(list(action.choices)[0])
    if action.type is int:
        return "1"
    if action.dest == "file":
        return tmpfile
    return "x"


def _pos_value(prefix, dest, tmpfile):
    selected = POSITIONAL_VALUES.get((prefix, dest))
    if selected is not None:
        return selected
    if dest == "file":
        return tmpfile
    return "1" if dest in ID_DESTS else "x"


def _synth_argv(prefix, parser, tmpfile):
    """Build a minimally-valid argv for a leaf: fill required options and every
    positional, add --confirm where present, plus any per-leaf extras."""
    argv = list(prefix)
    for action in parser._actions:
        if isinstance(action, (argparse._SubParsersAction, argparse._HelpAction)):
            continue
        if action.option_strings:
            if action.required:
                argv += [action.option_strings[0], _opt_value(action, tmpfile)]
            elif "--confirm" in action.option_strings:
                argv += ["--confirm"]
        else:  # positional
            if action.nargs in ("?", "*"):
                continue  # optional positional — omit
            count = action.nargs if isinstance(action.nargs, int) else 1
            argv += [_pos_value(prefix, action.dest, tmpfile) for _ in range(count)]
    argv += EXTRA_ARGS.get(prefix, [])
    return argv


class _TransportMixin(unittest.TestCase):
    """Isolated profile store (default profile) + a capturing fake transport."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self._tmp.name}, clear=False)
        self._env.start()
        for var in (
            "RUNDESK_API_KEY", "RUNDESK_BASE_URL", "DESK_PROFILE",
            "RUNDESK_API_KEY__ALAN", "RUNDESK_BASE_URL__ALAN",
        ):
            os.environ.pop(var, None)

        cfg = profiles.load_config()
        profiles.add_profile(cfg, "work", BASE_URL, API_KEY)
        cfg["default"] = "work"
        profiles.save_config(cfg)

        self.captured = []

        def fake_urlopen(req, timeout=None):
            self.captured.append(
                {
                    "method": req.get_method(),
                    "url": req.full_url,
                    "auth": req.get_header("Authorization"),
                }
            )
            if req.full_url.endswith("/api/v1/desks/1/keys"):
                return _FakeResponse(
                    b'{"plain_text_token":"SYNTHETIC-MINTED-CREDENTIAL"}'
                )
            return _FakeResponse(b"{}")

        self._orig = client_mod.urllib.request.urlopen
        client_mod.urllib.request.urlopen = fake_urlopen

        fd, self._tmpfile = tempfile.mkstemp()
        os.write(fd, b"data")
        os.close(fd)

    def tearDown(self):
        client_mod.urllib.request.urlopen = self._orig
        os.unlink(self._tmpfile)
        self._env.stop()
        self._tmp.cleanup()


class ApiEndpointCoverageTests(_TransportMixin):
    def test_every_api_leaf_reaches_endpoint_with_credentials(self):
        parser = cli.build_parser()
        api_leaves = [(p, lp) for p, lp in _leaves(parser) if p[0] not in LOCAL_COMMANDS]
        self.assertGreaterEqual(len(api_leaves), 50, "sanity: expected the full API surface")

        failures = []
        for prefix, leaf_parser in api_leaves:
            self.captured.clear()
            argv = _synth_argv(prefix, leaf_parser, self._tmpfile)
            try:
                rc = cli.main(argv)
            except SystemExit as exc:  # argparse should never bail on a synthesized argv
                failures.append((prefix, f"SystemExit({exc.code}) argv={argv}"))
                continue
            if rc != 0:
                failures.append((prefix, f"exit={rc} argv={argv}"))
            elif not self.captured:
                failures.append((prefix, f"no HTTP request issued argv={argv}"))
            else:
                first = self.captured[0]
                if not first["url"].startswith(BASE_URL):
                    failures.append((prefix, f"wrong base_url: {first['url']}"))
                if first["auth"] != f"Bearer {API_KEY}":
                    failures.append((prefix, f"missing/wrong auth: {first['auth']}"))

        if failures:
            lines = "\n".join(f"  {' '.join(p)}: {msg}" for p, msg in failures)
            self.fail(f"{len(failures)} command(s) did not reach the endpoint correctly:\n{lines}")

        # Report the covered surface (visible with -v).
        print(f"\ncovered {len(api_leaves)} API endpoints end-to-end")

    def test_every_client_method_reachable_from_command_tree(self):
        """No orphan endpoints: every public RundeskClient API method is invoked
        by some handler in the command tree. The tree spans two modules —
        rundesk.py owns the full API groups, cli.py owns the desk-bound
        surface (show/inbox/mentions)."""
        source = "\n".join(
            (SRC / name).read_text(encoding="utf-8") for name in ("rundesk.py", "cli.py")
        )
        skip = {"build_url", "request", "request_multipart", "items"}
        methods = [
            name
            for name, _ in inspect.getmembers(RundeskClient, predicate=inspect.isfunction)
            if not name.startswith("_") and name not in skip
        ]
        self.assertGreaterEqual(len(methods), 60)
        # Attribute reference (not necessarily an immediate call) — some methods
        # are dispatched indirectly, e.g. `fn = client.set_task_recurring; fn(...)`.
        orphans = [m for m in methods if f".{m}" not in source]
        self.assertEqual(orphans, [], f"client methods not reachable from any command: {orphans}")


class MarkdownRoundTripTests(_TransportMixin):
    def test_task_body_and_comment_round_trip_exactly(self) -> None:
        task_body = (
            "## Outcome\n\n"
            "Preserve [Desk Markdown](https://rundesk.ai) through `desk`.\n\n"
            "## Definition of done\n\n"
            "- [x] Headings and checklists survive.\n"
            "- Bullets, links, and inline code stay byte-for-byte intact.\n"
        )
        comment_body = (
            "Verified: [CLI proof](https://example.test/proof) kept `inline code` intact."
        )
        stored_task = {"id": 41, "title": "Markdown brief"}
        stored_comments = []

        def round_trip_api(req: Any, timeout: Any = None) -> _FakeResponse:
            method = req.get_method()
            path = req.full_url.split("/api/v1", 1)[1].split("?", 1)[0]
            payload = json.loads(req.data.decode("utf-8")) if req.data else None

            if (method, path) == ("POST", "/tasks"):
                stored_task.update(payload)
                response = stored_task
            elif (method, path) == ("GET", "/tasks/41"):
                response = stored_task
            elif (method, path) == ("POST", "/tasks/41/comments"):
                comment = {"id": 7, "body": payload["body"]}
                stored_comments.append(comment)
                response = {"comment": comment}
            elif (method, path) == ("GET", "/tasks/41/comments"):
                response = {"comments": stored_comments}
            else:
                self.fail(f"unexpected request: {method} {path}")
            return _FakeResponse(json.dumps(response).encode("utf-8"))

        with mock.patch.object(client_mod.urllib.request, "urlopen", round_trip_api):
            created = _capture_stdout(
                lambda: self.assertEqual(
                    cli.main(
                        ["tasks", "create", "--title", "Markdown brief", "--body", task_body]
                    ),
                    0,
                )
            )
            fetched = _capture_stdout(
                lambda: self.assertEqual(cli.main(["tasks", "get", "41", "--json"]), 0)
            )
            posted = _capture_stdout(
                lambda: self.assertEqual(
                    cli.main(["tasks", "comment", "41", comment_body]),
                    0,
                )
            )
            comments = _capture_stdout(
                lambda: self.assertEqual(cli.main(["tasks", "comments", "41"]), 0)
            )

        self.assertEqual(json.loads(created)["body"], task_body)
        self.assertEqual(json.loads(fetched)["body"], task_body)
        self.assertEqual(json.loads(posted)["comment"]["body"], comment_body)
        self.assertEqual(json.loads(comments)["comments"][0]["body"], comment_body)


class DeskSurfaceTests(_TransportMixin):
    def test_inbox_is_top_level_and_hits_desk_inbox(self):
        rc = cli.main(["inbox"])
        self.assertEqual(rc, 0)
        self.assertIn("/desk/inbox", self.captured[0]["url"])

    def test_inbox_unscheduled_filter(self):
        rc = cli.main(["inbox", "--unscheduled"])
        self.assertEqual(rc, 0)
        self.assertIn("unscheduled=1", self.captured[0]["url"])

    def test_inbox_week_filter(self):
        rc = cli.main(["inbox", "--week", "7"])
        self.assertEqual(rc, 0)
        self.assertIn("week=7", self.captured[0]["url"])

    def test_mentions_is_top_level_and_hits_desk_mentions(self):
        rc = cli.main(["mentions"])
        self.assertEqual(rc, 0)
        self.assertTrue(self.captured[0]["url"].split("?")[0].endswith("/desk/mentions"))

    def test_mentions_limit_is_sent(self):
        rc = cli.main(["mentions", "--limit", "5"])
        self.assertEqual(rc, 0)
        url = self.captured[0]["url"]
        self.assertTrue(url.split("?")[0].endswith("/desk/mentions"))
        self.assertIn("limit=5", url)

    def test_show_is_the_desk_identity(self):
        rc = cli.main(["show"])
        self.assertEqual(rc, 0)
        self.assertTrue(self.captured[0]["url"].split("?")[0].endswith("/desk"))

    def test_whoami_still_works_as_a_hidden_alias_of_show(self):
        rc = cli.main(["whoami"])
        self.assertEqual(rc, 0)
        self.assertTrue(self.captured[0]["url"].split("?")[0].endswith("/desk"))

    def test_whoami_is_not_advertised_in_help(self):
        out = _capture_stdout(lambda: self.assertEqual(cli.main(["help"]), 0))
        self.assertIn("show", out)  # the command that replaced it IS listed
        self.assertNotIn("whoami", out)

    def test_account_is_the_account_record(self):
        rc = cli.main(["account"])
        self.assertEqual(rc, 0)
        self.assertTrue(self.captured[0]["url"].split("?")[0].endswith("/me"))

    def test_no_memory_or_jobs_leaf_survives(self):
        choices = _find_subparsers(cli.build_parser()).choices
        self.assertNotIn("desk", choices)  # no more `desk desk`
        self.assertNotIn("jobs", choices)
        self.assertIn("show", choices)
        self.assertIn("account", choices)
        self.assertIn("inbox", choices)
        self.assertIn("mentions", choices)
        # Neither a memory nor a jobs leaf survives anywhere in the built tree.
        leaves = {" ".join(p) for p, _ in _leaves(cli.build_parser())}
        stale = {path for path in leaves if "memory" in path or "jobs" in path}
        self.assertFalse(stale, f"memory/jobs leaves remain: {sorted(stale)}")

    def test_desk_desk_is_rejected(self):
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["desk", "show"])


class DeleteGatingTests(_TransportMixin):
    def test_delete_without_confirm_aborts_and_makes_no_request(self):
        rc = cli.main(["tasks", "delete", "5"])
        self.assertEqual(rc, 2)
        self.assertEqual(self.captured, [])

    def test_delete_with_confirm_issues_request(self):
        rc = cli.main(["tasks", "delete", "5", "--confirm"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.captured), 1)
        self.assertEqual(self.captured[0]["method"], "DELETE")

    def test_profile_override_selects_other_credentials(self):
        cfg = profiles.load_config()
        profiles.add_profile(cfg, "home", "https://home.test", "HOME-KEY-9999")
        profiles.save_config(cfg)
        self.captured.clear()
        rc = cli.main(["--profile", "home", "whoami"])
        self.assertEqual(rc, 0)
        self.assertTrue(self.captured[0]["url"].startswith("https://home.test"))
        self.assertEqual(self.captured[0]["auth"], "Bearer HOME-KEY-9999")

    def test_env_profile_selects_suffixed_credentials(self):
        with mock.patch.dict(
            os.environ,
            {
                "RUNDESK_API_KEY__ALAN": "ALAN-KEY-9999",
                "RUNDESK_BASE_URL__ALAN": "https://alan.test",
            },
            clear=False,
        ):
            rc = cli.main(["--env-profile", "alan", "account"])
        self.assertEqual(rc, 0)
        self.assertTrue(self.captured[0]["url"].startswith("https://alan.test"))
        self.assertEqual(self.captured[0]["auth"], "Bearer ALAN-KEY-9999")

    def test_env_profile_never_falls_back_to_saved_or_unsuffixed_credentials(self):
        with mock.patch.dict(
            os.environ,
            {"RUNDESK_API_KEY": "UNSUFFIXED-KEY"},
            clear=False,
        ):
            rc = cli.main(["--env-profile", "alan", "account"])
        self.assertEqual(rc, 2)
        self.assertEqual(self.captured, [])

    def test_saved_and_env_profile_flags_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(
                ["--profile", "work", "--env-profile", "alan", "account"]
            )


class MintedKeySafetyTests(_TransportMixin):
    def test_minted_key_is_saved_but_never_printed(self):
        output = _capture_stdout(
            lambda: self.assertEqual(
                cli.main(
                    ["desks", "mint-key", "1", "--name", "worker",
                     "--save-profile", "worker"]
                ),
                0,
            )
        )
        saved = profiles.load_config()["profiles"]["worker"]
        self.assertEqual(saved["api_key"], "SYNTHETIC-MINTED-CREDENTIAL")
        self.assertEqual(saved["base_url"], BASE_URL)
        self.assertNotIn("SYNTHETIC-MINTED-CREDENTIAL", output)
        self.assertIn("…TIAL", output)
        self.assertEqual(profiles.config_path().stat().st_mode & 0o777, 0o600)

    def test_mint_refuses_to_overwrite_a_profile_before_request(self):
        rc = cli.main(
            ["desks", "mint-key", "1", "--name", "worker",
             "--save-profile", "work"]
        )
        self.assertEqual(rc, 2)
        self.assertEqual(self.captured, [])

    def test_unwritable_profile_store_aborts_before_mint(self):
        with mock.patch.object(
            profiles, "save_config", side_effect=OSError("read-only")
        ):
            rc = cli.main(
                ["desks", "mint-key", "1", "--name", "worker",
                 "--save-profile", "worker"]
            )
        self.assertEqual(rc, 2)
        self.assertEqual(self.captured, [])

    def test_post_mint_storage_failure_is_actionable_and_never_leaks(self):
        import contextlib
        import io

        real_save = profiles.save_config
        saves = 0

        def fail_second_save(cfg):
            nonlocal saves
            saves += 1
            if saves == 2:
                raise OSError("disk full")
            real_save(cfg)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(profiles, "save_config", side_effect=fail_second_save):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                rc = cli.main(
                    ["desks", "mint-key", "1", "--name", "worker",
                     "--save-profile", "worker"]
                )
        self.assertEqual(rc, 1)
        self.assertEqual(len(self.captured), 1)
        self.assertNotIn("worker", profiles.load_config()["profiles"])
        combined = stdout.getvalue() + stderr.getvalue()
        self.assertNotIn("SYNTHETIC-MINTED-CREDENTIAL", combined)
        self.assertIn("revoke that desk key", combined)

    def test_missing_minted_token_creates_no_profile_and_leaks_nothing(self):
        import contextlib
        import io

        def missing_token(req, timeout=None):
            self.captured.append(
                {
                    "method": req.get_method(),
                    "url": req.full_url,
                    "auth": req.get_header("Authorization"),
                }
            )
            return _FakeResponse(b"{}")

        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(client_mod.urllib.request, "urlopen", missing_token):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                rc = cli.main(
                    ["desks", "mint-key", "1", "--name", "worker",
                     "--save-profile", "worker"]
                )
        self.assertEqual(rc, 1)
        self.assertEqual(len(self.captured), 1)
        self.assertNotIn("worker", profiles.load_config()["profiles"])
        combined = stdout.getvalue() + stderr.getvalue()
        self.assertNotIn("plain_text_token", combined)
        self.assertIn("revoke that desk key", combined)

    def test_concurrent_profile_claim_is_preserved_under_unique_name(self):
        def claim_requested_name(req, timeout=None):
            self.captured.append(
                {
                    "method": req.get_method(),
                    "url": req.full_url,
                    "auth": req.get_header("Authorization"),
                }
            )
            cfg = profiles.load_config()
            profiles.add_profile(
                cfg, "worker", "https://concurrent.test", "CONCURRENT-CREDENTIAL",
            )
            profiles.save_config(cfg)
            return _FakeResponse(
                b'{"plain_text_token":"SYNTHETIC-MINTED-CREDENTIAL"}'
            )

        with mock.patch.object(
            client_mod.urllib.request, "urlopen", claim_requested_name
        ):
            output = _capture_stdout(
                lambda: self.assertEqual(
                    cli.main(
                        ["desks", "mint-key", "1", "--name", "worker",
                         "--save-profile", "worker"]
                    ),
                    0,
                )
            )
        saved = profiles.load_config()["profiles"]
        self.assertEqual(saved["worker"]["api_key"], "CONCURRENT-CREDENTIAL")
        self.assertEqual(
            saved["worker-minted"]["api_key"], "SYNTHETIC-MINTED-CREDENTIAL",
        )
        self.assertIn("worker-minted", output)
        self.assertNotIn("SYNTHETIC-MINTED-CREDENTIAL", output)

    def test_late_profile_claim_retries_without_overwrite(self):
        real_save = profiles.save_config
        claimed = False

        def claim_after_reload(cfg):
            nonlocal claimed
            candidate = cfg.get("profiles", {}).get("worker", {})
            if not claimed and candidate.get("api_key") == "SYNTHETIC-MINTED-CREDENTIAL":
                claimed = True
                concurrent = profiles.load_config()
                profiles.add_profile(
                    concurrent, "worker", "https://concurrent.test",
                    "CONCURRENT-CREDENTIAL",
                )
                real_save(concurrent)
            real_save(cfg)

        with mock.patch.object(profiles, "save_config", side_effect=claim_after_reload):
            output = _capture_stdout(
                lambda: self.assertEqual(
                    cli.main(
                        ["desks", "mint-key", "1", "--name", "worker",
                         "--save-profile", "worker"]
                    ),
                    0,
                )
            )
        saved = profiles.load_config()["profiles"]
        self.assertEqual(saved["worker"]["api_key"], "CONCURRENT-CREDENTIAL")
        self.assertEqual(
            saved["worker-minted"]["api_key"], "SYNTHETIC-MINTED-CREDENTIAL",
        )
        self.assertIn("worker-minted", output)

    def test_post_mint_reload_failure_requires_revocation(self):
        import contextlib
        import io

        initial = profiles.load_config()
        stderr = io.StringIO()
        with mock.patch.object(
            profiles,
            "load_config",
            side_effect=[initial, initial, RundeskError("usage", "corrupt config")],
        ):
            with contextlib.redirect_stderr(stderr):
                rc = cli.main(
                    ["desks", "mint-key", "1", "--name", "worker",
                     "--save-profile", "worker"]
                )
        self.assertEqual(rc, 1)
        self.assertEqual(len(self.captured), 1)
        self.assertIn("revoke that desk key", stderr.getvalue())


class LocalProfileCommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self._tmp.name}, clear=False)
        self._env.start()
        for var in ("RUNDESK_API_KEY", "RUNDESK_BASE_URL", "DESK_PROFILE"):
            os.environ.pop(var, None)

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def test_add_verifies_and_saves_first_profile_as_default(self):
        fake_client = mock.Mock()
        fake_client.get_account.return_value = {"name": "Ann", "email": "ann@example.com"}
        with mock.patch.object(cli, "RundeskClient", return_value=fake_client), \
             mock.patch("builtins.input", side_effect=[""]), \
             mock.patch("cli.getpass.getpass", return_value="KEY-0001"):
            rc = cli.main(["profile", "add", "work"])
        self.assertEqual(rc, 0)
        cfg = profiles.load_config()
        self.assertEqual(cfg["default"], "work")
        self.assertEqual(cfg["profiles"]["work"]["api_key"], "KEY-0001")
        fake_client.get_account.assert_called_once()

    def test_api_command_without_credentials_exits_2(self):
        # Empty store → resolve_credentials raises no_key; cli.main maps it to 2.
        rc = cli.main(["whoami"])
        self.assertEqual(rc, 2)

    def test_add_requires_valid_key_and_does_not_save_on_failure(self):
        # Strict: verification against /me must pass, else it's an error and the
        # profile is NOT saved (no "save anyway" bypass).
        fake_client = mock.Mock()
        fake_client.get_account.side_effect = RundeskError("auth", "401 Unauthenticated")
        with mock.patch.object(cli, "RundeskClient", return_value=fake_client), \
             mock.patch("builtins.input", side_effect=[""]), \
             mock.patch("cli.getpass.getpass", return_value="BAD-KEY"):
            rc = cli.main(["profile", "add", "work"])
        self.assertEqual(rc, 3)  # the auth failure's exit code
        self.assertEqual(profiles.load_config()["profiles"], {})  # nothing saved
        fake_client.get_account.assert_called_once()  # it did try to validate

    def _seed(self):
        cfg = profiles.load_config()
        profiles.add_profile(cfg, "work", BASE_URL, "KEY-work-1111")
        profiles.add_profile(cfg, "home", "https://home.test", "KEY-home-2222")
        cfg["default"] = "work"
        profiles.save_config(cfg)

    def test_list_masks_keys(self):
        self._seed()
        buf = _capture_stdout(lambda: cli.main(["profile", "list"]))
        self.assertIn("work", buf)
        self.assertIn("…1111", buf)
        self.assertNotIn("KEY-work-1111", buf)  # never printed in full

    def test_use_sets_default(self):
        self._seed()
        self.assertEqual(cli.main(["profile", "use", "home"]), 0)
        self.assertEqual(profiles.load_config()["default"], "home")

    def test_use_unknown_errors(self):
        self._seed()
        self.assertEqual(cli.main(["profile", "use", "nope"]), 2)

    def test_show_defaults_to_default_profile(self):
        self._seed()
        buf = _capture_stdout(lambda: cli.main(["profile", "show"]))
        self.assertIn("work", buf)
        self.assertNotIn("KEY-work-1111", buf)

    def test_remove_confirmed(self):
        self._seed()
        with mock.patch("builtins.input", return_value="y"):
            rc = cli.main(["profile", "remove", "home"])
        self.assertEqual(rc, 0)
        self.assertNotIn("home", profiles.load_config()["profiles"])

    def test_remove_declined_keeps_profile(self):
        self._seed()
        with mock.patch("builtins.input", return_value="n"):
            rc = cli.main(["profile", "remove", "home"])
        self.assertEqual(rc, 0)
        self.assertIn("home", profiles.load_config()["profiles"])


class ProfileLocalCommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self._tmp.name}, clear=False)
        self._env.start()
        for var in ("RUNDESK_API_KEY", "RUNDESK_BASE_URL", "DESK_PROFILE"):
            os.environ.pop(var, None)
        cfg = profiles.load_config()
        profiles.add_profile(cfg, "agent-a", "https://a.test", "KEY-A")
        profiles.add_profile(cfg, "agent-b", "https://b.test", "KEY-B")
        cfg["default"] = "agent-a"
        profiles.save_config(cfg)
        # Work inside a throwaway dir so .desk-profile never lands in the repo.
        self._work = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._work.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._work.cleanup()
        self._env.stop()
        self._tmp.cleanup()

    def test_local_binds_directory_and_resolution_follows(self):
        rc = cli.main(["profile", "local", "agent-b"])
        self.assertEqual(rc, 0)
        marker = Path(self._work.name) / ".desk-profile"
        self.assertEqual(marker.read_text().strip(), "profile=agent-b")
        # A command run here now resolves to agent-b, not the default agent-a.
        self.assertEqual(profiles.resolve_credentials(), ("https://b.test", "KEY-B"))

    def test_local_clear_removes_marker(self):
        (Path(self._work.name) / ".desk-profile").write_text("agent-b\n")
        rc = cli.main(["profile", "local", "--clear"])
        self.assertEqual(rc, 0)
        self.assertFalse((Path(self._work.name) / ".desk-profile").exists())


class UninstallTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self._tmp.name}, clear=False)
        self._env.start()
        self._bindir = Path(self._tmp.name) / "bin"
        self._bindir.mkdir()
        # A symlink named `desk` pointing at this checkout's real shim.
        self._link = self._bindir / "desk"
        self._link.symlink_to(cli.REPO_ROOT / "desk")
        self._bins = mock.patch.object(cli, "_BIN_DIRS", (str(self._bindir),))
        self._bins.start()

    def tearDown(self):
        self._bins.stop()
        self._env.stop()
        self._tmp.cleanup()

    def test_uninstall_removes_symlink(self):
        rc = cli.main(["uninstall"])
        self.assertEqual(rc, 0)
        self.assertFalse(self._link.exists())
        self.assertFalse(self._link.is_symlink())

    def test_uninstall_ignores_foreign_symlink(self):
        # A desk symlink pointing somewhere else must be left alone.
        self._link.unlink()
        self._link.symlink_to("/usr/bin/true")
        rc = cli.main(["uninstall"])
        self.assertEqual(rc, 0)
        self.assertTrue(self._link.is_symlink())  # untouched

    def test_uninstall_purge_removes_profiles(self):
        cfg = profiles.load_config()
        profiles.add_profile(cfg, "work", BASE_URL, API_KEY)
        profiles.save_config(cfg)
        self.assertTrue(profiles.config_path().exists())
        with mock.patch("builtins.input", return_value="y"):
            rc = cli.main(["uninstall", "--purge"])
        self.assertEqual(rc, 0)
        self.assertFalse(profiles.config_dir().exists())


class HelpCommandTests(unittest.TestCase):
    def test_help_lists_commands(self):
        out = _capture_stdout(lambda: self.assertEqual(cli.main(["help"]), 0))
        self.assertIn("usage: desk", out)
        self.assertIn("inbox", out)
        self.assertIn("profile", out)

    def test_help_topic_shows_command_help(self):
        out = _capture_stdout(lambda: self.assertEqual(cli.main(["help", "inbox"]), 0))
        self.assertIn("--unscheduled", out)  # inbox's own options

    def test_help_nested_topic_shows_leaf_help(self):
        out = _capture_stdout(
            lambda: self.assertEqual(cli.main(["help", "tasks", "move-week"]), 0)
        )
        self.assertIn("--week-id", out)
        self.assertIn("--inbox", out)

    def test_help_unknown_topic_errors(self):
        self.assertEqual(cli.main(["help", "nope"]), 2)

    def test_bare_desk_prints_help(self):
        out = _capture_stdout(lambda: self.assertEqual(cli.main([]), 0))
        self.assertIn("usage: desk", out)

    def test_move_week_requires_exactly_one_destination(self):
        parser = cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["tasks", "move-week", "5"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["tasks", "move-week", "5", "--week-id", "2", "--inbox"])

    def test_move_project_requires_exactly_one_destination(self):
        parser = cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["tasks", "move-project", "5"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["tasks", "move-project", "5", "--project-id", "2", "--none"])


class UpdateRoutingTests(unittest.TestCase):
    def test_update_check_routes_to_updater(self):
        with mock.patch.object(cli.updater, "run", return_value=0) as run:
            rc = cli.main(["update", "--check"])
        self.assertEqual(rc, 0)
        run.assert_called_once_with(cli.REPO_ROOT, cli.__version__, check_only=True)

    def test_update_routes_to_updater(self):
        with mock.patch.object(cli.updater, "run", return_value=0) as run:
            cli.main(["update"])
        run.assert_called_once_with(cli.REPO_ROOT, cli.__version__, check_only=False)


class CatalogManifestTests(unittest.TestCase):
    """This repository is also a Rundesk skill catalog: `manifest.json` at the root
    plus each complete Agent Skill package discovered under ``skills/``.

    Rundesk validates a catalog on install and then *silently* ignores a package a
    brain would not index — a name with an underscore, a frontmatter name that
    disagrees with its directory, an over-long description. The failure mode is a
    skill that installs and never fires, which nothing reports. So the same rules are
    checked here, where a break is visible, rather than on somebody else's machine.
    """

    #: The catalog contract rundesk enforces (its `skill.ALLOWED`, `NAMED_LIMIT`,
    #: `DESCRIBED_LIMIT`). Restated rather than imported: rundesk is a separate
    #: install that is not here, and this repository is published without it.
    ALLOWED_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
    NAME_LIMIT = 64
    DESCRIPTION_LIMIT = 1024
    SCHEMA = 1

    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.manifest = json.loads((cls.root / "manifest.json").read_text(encoding="utf-8"))
        cls.packages = sorted(
            one for one in (cls.root / "skills").iterdir()
            if (one / "SKILL.md").is_file()
        )

    def test_manifest_version_tracks_the_package_version(self):
        """One release, one number. A catalog whose version trails `__version__`
        makes `rundesk skills update` refuse the newer repository as older."""
        self.assertEqual(self.manifest["version"], cli.__version__)

    def test_manifest_declares_a_valid_catalog(self):
        self.assertEqual(self.manifest["schema"], self.SCHEMA)
        self.assertRegex(self.manifest["name"], self.ALLOWED_NAME)
        self.assertRegex(self.manifest["version"], r"^\d+\.\d+\.\d+$")
        described = self.manifest["description"]
        self.assertTrue(described.strip())
        self.assertLessEqual(len(described), self.DESCRIPTION_LIMIT)
        self.assertNotIn("skills", self.manifest, "Rundesk discovers skills from the directory")
        self.assertTrue(self.packages, "a catalog contains at least one skill")

    def test_every_discovered_skill_is_a_complete_package(self):
        for at in self.packages:
            name = at.name
            with self.subTest(skill=name):
                at = at.resolve()
                self.assertIn(self.root, at.parents, "a skill path cannot leave the repository")
                self.assertTrue(at.is_dir(), f"{at} is not a directory")

                page = at / "SKILL.md"
                self.assertTrue(page.is_file(), f"{at} has no SKILL.md")
                said = _frontmatter(page.read_text(encoding="utf-8"))
                self.assertIsNotNone(said, "SKILL.md must open with a --- frontmatter block")

                # A brain indexes by the frontmatter name; a disagreement here is a
                # skill that is present and unreachable.
                self.assertEqual(said.get("name"), name)
                self.assertRegex(name, self.ALLOWED_NAME)
                self.assertLessEqual(len(name), self.NAME_LIMIT)

                described = said.get("description") or ""
                self.assertTrue(described.strip(), "the description is the whole of what a brain sees")
                self.assertLessEqual(len(described), self.DESCRIPTION_LIMIT)

                needs_path = at / "rundesk.json"
                if needs_path.exists():
                    needs_doc = json.loads(needs_path.read_text(encoding="utf-8"))
                    self.assertEqual(set(needs_doc), {"needs"})
                    self.assertIsInstance(needs_doc["needs"], dict)
                    for env_name, reason in needs_doc["needs"].items():
                        self.assertRegex(env_name, r"^[A-Z][A-Z0-9_]*$")
                        self.assertNotIn("__", env_name)
                        self.assertTrue(isinstance(reason, str) and reason.strip())

    def test_managing_your_desk_declares_its_api_key(self):
        needs_path = self.root / "skills" / "managing-your-desk" / "rundesk.json"
        self.assertTrue(needs_path.is_file())
        needs_doc = json.loads(needs_path.read_text(encoding="utf-8"))
        self.assertIn("RUNDESK_API_KEY", needs_doc.get("needs", {}))

    def test_handling_assigned_work_declares_its_api_key(self):
        needs_path = self.root / "skills" / "handling-assigned-desk-work" / "rundesk.json"
        self.assertTrue(needs_path.is_file())
        needs_doc = json.loads(needs_path.read_text(encoding="utf-8"))
        self.assertIn("RUNDESK_API_KEY", needs_doc.get("needs", {}))

    def test_handling_assigned_work_keeps_owner_control_and_comments_compact(self):
        skill_path = self.root / "skills" / "handling-assigned-desk-work" / "SKILL.md"
        skill = skill_path.read_text(encoding="utf-8")
        skill_text = " ".join(skill.split())
        described = _frontmatter(skill)["description"]

        self.assertIn("named Rundesk Desk tasks", described)
        self.assertIn("without delegating queue management", described)
        self.assertIn("owner-mentioned handoff", described)
        self.assertIn("Do not use it to choose work from an inbox", described)
        for required in (
            "Inbox presence, assignment, priority, a mention, or discovering related work does not",
            "If the owner explicitly says to handle all assigned Desk tasks",
            "the instruction creates no standing queue authority",
            "Never create a task or change its title, body, project, priority, week, deadline",
            "The owner reviews and closes the work.",
            "Post no start, progress, plan, resume, investigation, or narrative-summary comments.",
            "exact `owner.handle` from `desk show --json`",
            "@<owner-handle> Ready for review: <authoritative link>",
            "@<owner-handle> Blocked: <specific decision, authority, or missing input>",
            "@<owner-handle> Verified: <one short proof when no review link exists>",
            "Do not use this skill when the same agent holds `managing-your-desk`.",
            "[the adoption template](references/adoption.md)",
        ):
            with self.subTest(required=required):
                self.assertIn(required, skill_text)
        self.assertLessEqual(len(skill.splitlines()), 100)
        self.assertLessEqual(len(skill.split()), 700)

        adoption = (skill_path.parent / "references" / "adoption.md").read_text(encoding="utf-8")
        self.assertIn("Keep local task management as the execution and continuity system.", adoption)
        self.assertIn("load `handling-assigned-desk-work`", adoption)
        self.assertIn("never treat", adoption)
        self.assertIn("Desk inbox visibility as permission to choose work", adoption)
        self.assertIn("preserve every unrelated rule", adoption)
        self.assertIn("cmp -s AGENTS.md CLAUDE.md", adoption)
        self.assertIn("the skill is their source of truth", adoption)

    def test_readme_distinguishes_the_two_desk_authority_models(self):
        readme = (self.root / "README.md").read_text(encoding="utf-8")
        self.assertIn("**`handling-assigned-desk-work`** is passive", readme)
        self.assertIn("**`managing-your-desk`** delegates active queue ownership", readme)
        self.assertIn("Do not grant both to one agent", readme)

    def test_managing_your_desk_routes_persistent_queue_work_within_budget(self):
        skill_path = self.root / "skills" / "managing-your-desk" / "SKILL.md"
        skill = skill_path.read_text(encoding="utf-8")
        described = _frontmatter(skill)["description"]
        self.assertIn("persistent operational queue", described)
        self.assertIn("bounded specialists without persistent queues", described)
        self.assertIn("including related project work", described)
        self.assertIn("GitHub remain implementation truth", described)
        self.assertLessEqual(len(skill.splitlines()), 120)
        self.assertLessEqual(len(skill.split()), 1_000)

    def test_managing_your_desk_covers_queue_contract_and_adoption(self):
        skill_dir = self.root / "skills" / "managing-your-desk"
        core = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        adoption = (skill_dir / "references" / "queue-adoption.md").read_text(
            encoding="utf-8"
        )
        core_text = " ".join(core.split())

        for required in (
            "Treat **This week** as the ordered commitment and work top-down.",
            "inspect both the unscheduled inbox and mentions",
            "owner-requested work and tasks derived from owned goals",
            "independently completable chunks",
            "observable, measurable done criteria and required proof",
            "executable next action or explicit blocker",
            "complete it after proof, re-scope it, or assign a real future week",
            "never leave it indefinitely stale",
            "GitHub or the project repository is the implementation source of truth",
            "Comment sparingly and briefly",
            "Mark done only after the outcome is delivered",
            "assign a real future week, deadline, or recurrence",
            "Contact or mention the Desk owner only for a blocker",
            "Ordinary queue operation never edits an agent home or rule file",
            "Bounded specialist agents do not adopt or own persistent queues",
        ):
            with self.subTest(required=required):
                self.assertIn(required, core_text)

        self.assertIn("## Desk queue ownership", adoption)
        self.assertIn("`managing-your-desk` skill", adoption)
        self.assertIn("cmp -s AGENTS.md CLAUDE.md", adoption)
        self.assertIn("write the same complete merged content to both files", adoption)
        self.assertIn("Preserve every unrelated standing rule", adoption)
        for field in (
            "## Outcome", "## Scope / limits", "## Definition of done",
            "## Proof", "## Next", "## Blocked",
        ):
            with self.subTest(field=field):
                self.assertIn(field, adoption)
        self.assertIn("- [ ]", adoption)
        self.assertIn("operational brief, not a duplicate implementation plan", adoption)
        self.assertIn("Do not add headings, checklists, routine start", adoption)


def _frontmatter(text: str) -> dict | None:
    """The `name` and `description` out of a SKILL.md, or None if there is no block.

    Two scalars read by hand: the standard library has no YAML parser, and this is
    exactly how rundesk reads the same file.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    said: dict = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return said
        what, _, rest = line.partition(":")
        if rest and what.strip() in ("name", "description") and not what.startswith((" ", "\t")):
            said[what.strip()] = rest.strip().strip("'\"")
    return None


def _capture_stdout(fn) -> str:
    import contextlib
    import io

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn()
    return out.getvalue()


class AgentGuideContractTests(unittest.TestCase):
    def test_guides_are_identical_and_keep_the_required_heading_order(self) -> None:
        root = Path(__file__).resolve().parents[1]
        agents = (root / "AGENTS.md").read_bytes()
        claude = (root / "CLAUDE.md").read_bytes()

        self.assertEqual(agents, claude, "AGENTS.md and CLAUDE.md must be byte-identical")
        headings = [
            line for line in agents.decode("utf-8").splitlines()
            if re.match(r"^#{1,2} ", line)
        ]
        self.assertEqual(AGENT_GUIDE_HEADINGS, headings)

    def test_repository_templates_keep_the_required_heading_order(self) -> None:
        root = Path(__file__).resolve().parents[1]
        pull_request = (root / ".github" / "pull_request_template.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            PR_TEMPLATE_HEADINGS,
            [line for line in pull_request.splitlines() if line.startswith("## ")],
        )
        for anchor in PR_TEMPLATE_ANCHORS:
            with self.subTest(pull_request_anchor=anchor):
                self.assertIn(anchor, pull_request)
        issue_root = root / ".github" / "ISSUE_TEMPLATE"
        self.assertEqual(
            set(ISSUE_TEMPLATE_HEADINGS) | {"config.yml"},
            {path.name for path in issue_root.iterdir() if path.is_file()},
        )
        self.assertEqual(
            b"blank_issues_enabled: false\n",
            (issue_root / "config.yml").read_bytes(),
        )
        for name, expected in ISSUE_TEMPLATE_HEADINGS.items():
            with self.subTest(template=name):
                issue_bytes = (issue_root / name).read_bytes()
                issue = issue_bytes.decode("utf-8")
                self.assertEqual(
                    ISSUE_TEMPLATE_DIGESTS[name],
                    hashlib.sha256(issue_bytes).hexdigest(),
                )
                self.assertEqual(ISSUE_TEMPLATE_FRONTMATTER[name], issue.splitlines()[:7])
                self.assertEqual(
                    expected,
                    [line for line in issue.splitlines() if line.startswith("## ")],
                )

    def test_readme_links_the_canonical_skill_catalog_guide(self) -> None:
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "https://github.com/rundesk-ai/rundesk-cli/blob/main/docs/catalogs.md",
            readme,
        )
        self.assertIn(
            "https://github.com/rundesk-ai/rundesk-cli#supported-first-party-catalogs",
            readme,
        )

    def test_readme_shell_examples_have_no_angle_bracket_metavariables(self) -> None:
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
            encoding="utf-8"
        )
        shell_blocks = re.findall(r"^```(?:sh|bash)\n(.*?)^```", readme, re.M | re.S)
        self.assertTrue(shell_blocks, "README.md contains no shell example to check")
        for block in shell_blocks:
            with self.subTest(block=block.splitlines()[0] if block.splitlines() else ""):
                self.assertIsNone(re.search(r"<[^>\n]+>", block))
                self.assertNotIn("$RUNDESK_COMMAND", block)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Offline tests for the local profile store and the self-updater logic.

No network, no real key: an isolated XDG_CONFIG_HOME temp dir backs the profile
store, and the updater's git/HTTP seams are monkeypatched. Covers config
load/save (incl. 0600/0700 perms), credential-resolution precedence, and the
version compare / update-decision logic.

Run: python3 tests/test_profiles.py
"""

from __future__ import annotations

import io
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "desk_cli"))

import profiles  # noqa: E402
import updater  # noqa: E402
from client import RundeskError  # noqa: E402


class ProfileStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ,
            {"XDG_CONFIG_HOME": self._tmp.name},
            clear=False,
        )
        self._env.start()
        # Ensure env escape-hatch vars don't leak in from the dev shell.
        for var in ("RUNDESK_API_KEY", "RUNDESK_BASE_URL", "DESK_PROFILE"):
            os.environ.pop(var, None)

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    # ── location + load/save ────────────────────────────────────────────────
    def test_config_path_honors_xdg(self):
        self.assertEqual(profiles.config_path(), Path(self._tmp.name) / "desk" / "config.json")

    def test_load_missing_returns_skeleton(self):
        cfg = profiles.load_config()
        self.assertEqual(cfg["profiles"], {})
        self.assertIsNone(cfg["default"])

    def test_save_reload_roundtrip_and_perms(self):
        cfg = profiles.load_config()
        profiles.add_profile(cfg, "work", "https://rundesk.ai/", "KEY-abcd1234")
        cfg["default"] = "work"
        profiles.save_config(cfg)

        path = profiles.config_path()
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

        reloaded = profiles.load_config()
        self.assertEqual(reloaded["default"], "work")
        self.assertEqual(reloaded["profiles"]["work"]["api_key"], "KEY-abcd1234")
        # base_url is normalized (trailing slash stripped) on add.
        self.assertEqual(reloaded["profiles"]["work"]["base_url"], "https://rundesk.ai")

    def test_malformed_config_raises_usage(self):
        path = profiles.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json", encoding="utf-8")
        with self.assertRaises(RundeskError) as ctx:
            profiles.load_config()
        self.assertEqual(ctx.exception.kind, "usage")

    # ── mutations ───────────────────────────────────────────────────────────
    def test_remove_repoints_default(self):
        cfg = profiles.load_config()
        profiles.add_profile(cfg, "a", "https://a", "ka")
        profiles.add_profile(cfg, "b", "https://b", "kb")
        cfg["default"] = "a"
        profiles.remove_profile(cfg, "a")
        self.assertNotIn("a", cfg["profiles"])
        self.assertEqual(cfg["default"], "b")  # repointed to the remaining profile

    def test_remove_last_clears_default(self):
        cfg = profiles.load_config()
        profiles.add_profile(cfg, "only", "https://x", "k")
        cfg["default"] = "only"
        profiles.remove_profile(cfg, "only")
        self.assertIsNone(cfg["default"])

    # ── mask_key ────────────────────────────────────────────────────────────
    def test_mask_key(self):
        self.assertEqual(profiles.mask_key(""), "(none)")
        self.assertEqual(profiles.mask_key("abcd1234"), "…1234")
        self.assertEqual(profiles.mask_key("xy"), "••")
        self.assertNotIn("SECRET", profiles.mask_key("SECRETabcd"))  # secret prefix hidden
        self.assertEqual(profiles.mask_key("SECRETabcd"), "…abcd")  # only last 4 shown

    # ── resolve_credentials precedence ──────────────────────────────────────
    def _seed(self):
        cfg = profiles.load_config()
        profiles.add_profile(cfg, "work", "https://work.example", "WORK-KEY")
        profiles.add_profile(cfg, "home", "https://home.example", "HOME-KEY")
        cfg["default"] = "work"
        profiles.save_config(cfg)

    def test_resolve_default(self):
        self._seed()
        self.assertEqual(profiles.resolve_credentials(), ("https://work.example", "WORK-KEY"))

    def test_resolve_explicit_beats_default(self):
        self._seed()
        self.assertEqual(profiles.resolve_credentials("home"), ("https://home.example", "HOME-KEY"))

    def test_resolve_explicit_unknown_raises(self):
        self._seed()
        with self.assertRaises(RundeskError) as ctx:
            profiles.resolve_credentials("nope")
        self.assertEqual(ctx.exception.kind, "usage")

    def test_resolve_desk_profile_env_beats_default(self):
        self._seed()
        with mock.patch.dict(os.environ, {"DESK_PROFILE": "home"}):
            self.assertEqual(profiles.resolve_credentials(), ("https://home.example", "HOME-KEY"))

    def test_resolve_env_key_beats_default(self):
        self._seed()
        with mock.patch.dict(os.environ, {"RUNDESK_API_KEY": "ENV-KEY", "RUNDESK_BASE_URL": "https://env.example"}):
            self.assertEqual(profiles.resolve_credentials(), ("https://env.example", "ENV-KEY"))

    def test_resolve_env_key_default_base_url(self):
        self._seed()
        with mock.patch.dict(os.environ, {"RUNDESK_API_KEY": "ENV-KEY"}, clear=False):
            os.environ.pop("RUNDESK_BASE_URL", None)
            self.assertEqual(profiles.resolve_credentials(), (profiles.DEFAULT_BASE_URL, "ENV-KEY"))

    def test_resolve_precedence_explicit_over_env(self):
        self._seed()
        with mock.patch.dict(os.environ, {"DESK_PROFILE": "home", "RUNDESK_API_KEY": "ENV-KEY"}):
            # explicit --profile wins over both env vars
            self.assertEqual(profiles.resolve_credentials("work"), ("https://work.example", "WORK-KEY"))

    def test_dir_profile_walks_up_to_ancestor(self):
        root = Path(self._tmp.name) / "proj"
        (root / "a" / "b").mkdir(parents=True)
        (root / ".desk-profile").write_text("# a comment\nhome\n", encoding="utf-8")
        self.assertEqual(profiles.dir_profile(root / "a" / "b"), "home")

    def test_dir_profile_accepts_var_forms(self):
        base = Path(self._tmp.name)
        for i, body in enumerate(["profile=home\n", "profile: home\n", "DESK_PROFILE = home\n", '# c\nprofile="home"\n']):
            d = base / f"var{i}"
            d.mkdir()
            (d / ".desk-profile").write_text(body, encoding="utf-8")
            self.assertEqual(profiles.dir_profile(d), "home", body)

    def test_dir_profile_absent_is_none(self):
        empty = Path(self._tmp.name) / "empty"
        empty.mkdir()
        self.assertIsNone(profiles.dir_profile(empty))

    def test_resolve_uses_dir_profile(self):
        self._seed()
        work = Path(self._tmp.name) / "work-tree"
        work.mkdir()
        (work / ".desk-profile").write_text("home\n", encoding="utf-8")
        cwd = os.getcwd()
        os.chdir(work)
        try:
            self.assertEqual(profiles.resolve_credentials(), ("https://home.example", "HOME-KEY"))
        finally:
            os.chdir(cwd)

    def test_dir_profile_beats_default_but_env_beats_dir(self):
        self._seed()
        work = Path(self._tmp.name) / "tree2"
        work.mkdir()
        (work / ".desk-profile").write_text("home\n", encoding="utf-8")
        cwd = os.getcwd()
        os.chdir(work)
        try:
            # DESK_PROFILE (session) outranks the directory file.
            with mock.patch.dict(os.environ, {"DESK_PROFILE": "work"}):
                self.assertEqual(profiles.resolve_credentials()[1], "WORK-KEY")
        finally:
            os.chdir(cwd)

    def test_resolve_dir_profile_unknown_raises(self):
        self._seed()
        work = Path(self._tmp.name) / "tree3"
        work.mkdir()
        (work / ".desk-profile").write_text("ghost\n", encoding="utf-8")
        cwd = os.getcwd()
        os.chdir(work)
        try:
            with self.assertRaises(RundeskError) as ctx:
                profiles.resolve_credentials()
            self.assertEqual(ctx.exception.kind, "usage")
        finally:
            os.chdir(cwd)

    def test_resolve_none_raises_no_key(self):
        with self.assertRaises(RundeskError) as ctx:
            profiles.resolve_credentials()
        self.assertEqual(ctx.exception.kind, "no_key")
        self.assertEqual(ctx.exception.exit_code, 2)


class UpdaterVersionTests(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(updater.parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(updater.parse_version("1.2"), (1, 2, 0))
        self.assertEqual(updater.parse_version("v2"), (2, 0, 0))
        self.assertIsNone(updater.parse_version("garbage"))
        self.assertIsNone(updater.parse_version(""))

    def test_is_newer(self):
        self.assertTrue(updater.is_newer("v1.0.1", "1.0.0"))
        self.assertTrue(updater.is_newer("2.0.0", "1.9.9"))
        self.assertFalse(updater.is_newer("1.0.0", "1.0.0"))
        self.assertFalse(updater.is_newer("0.9.0", "1.0.0"))
        self.assertFalse(updater.is_newer("garbage", "1.0.0"))

    def test_highest_picks_max_numeric(self):
        # numeric compare (0.10 > 0.9), junk ignored, empty → None
        self.assertEqual(updater._highest(["v0.9.0", "v0.10.0", "v1.0.0", "junk"]), "v1.0.0")
        self.assertEqual(updater._highest(["v0.9.0", "v0.10.0"]), "v0.10.0")
        self.assertIsNone(updater._highest([]))
        self.assertIsNone(updater._highest(["nope", ""]))

    def test_latest_version_online_prefers_release_then_tags(self):
        # A published Release's tag_name wins over the tags list.
        def by_url(url):
            if url == updater.RELEASES_LATEST_URL:
                return {"tag_name": "v0.2.0"}
            return [{"name": "v0.5.0"}]

        with mock.patch.object(updater, "_github_json", side_effect=by_url):
            self.assertEqual(updater.latest_version_online(), "v0.2.0")

    def test_latest_version_online_falls_back_to_tags(self):
        # No release (releases/latest yields no tag_name) → highest tag.
        def by_url(url):
            if url == updater.RELEASES_LATEST_URL:
                return {}  # 404-equivalent: no tag_name
            return [{"name": "v0.4.0"}, {"name": "v0.10.0"}, {"name": "junk"}]

        with mock.patch.object(updater, "_github_json", side_effect=by_url):
            self.assertEqual(updater.latest_version_online(), "v0.10.0")

    def test_latest_version_falls_back_to_git_when_api_empty(self):
        # Neither releases nor GitHub tags → git ls-remote fallback.
        with mock.patch.object(updater, "_github_json", return_value=None), \
             mock.patch.object(updater, "_git", return_value="abc\trefs/tags/v0.7.0\n"):
            self.assertEqual(updater.latest_version(Path("/nonexistent")), "v0.7.0")


class UpdaterRunTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # Isolate the update-check cache that run() writes so it doesn't leak
        # into the developer's real ~/.config/desk.
        self._cfg = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self._cfg.name}, clear=False)
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._cfg.cleanup()
        self._tmp.cleanup()

    def _make_git_checkout(self):
        (self.root / ".git").mkdir()

    def test_not_a_git_checkout_returns_1(self):
        # No .git present.
        self.assertEqual(updater.run(self.root, "0.1.0", check_only=False), 1)

    def test_up_to_date_returns_0(self):
        self._make_git_checkout()
        with mock.patch.object(updater, "latest_version", return_value="v0.1.0"):
            self.assertEqual(updater.run(self.root, "0.1.0", check_only=False), 0)

    def test_no_latest_returns_1(self):
        self._make_git_checkout()
        with mock.patch.object(updater, "latest_version", return_value=None):
            self.assertEqual(updater.run(self.root, "0.1.0", check_only=True), 1)

    def test_behind_check_only_makes_no_git_changes(self):
        self._make_git_checkout()
        with mock.patch.object(updater, "latest_version", return_value="v0.2.0"), \
             mock.patch.object(updater, "_git") as git:
            self.assertEqual(updater.run(self.root, "0.1.0", check_only=True), 0)
            git.assert_not_called()  # --check never touches git

    def test_behind_dirty_refuses(self):
        self._make_git_checkout()
        with mock.patch.object(updater, "latest_version", return_value="v0.2.0"), \
             mock.patch.object(updater, "_is_dirty", return_value=True), \
             mock.patch.object(updater, "_git") as git:
            self.assertEqual(updater.run(self.root, "0.1.0", check_only=False), 1)
            git.assert_not_called()  # refuses before fetch/checkout

    def test_behind_clean_fetches_and_checks_out(self):
        self._make_git_checkout()
        calls = []

        def fake_git(root, *args, capture=False):
            calls.append(args)
            return ""

        with mock.patch.object(updater, "latest_version", return_value="v0.2.0"), \
             mock.patch.object(updater, "_is_dirty", return_value=False), \
             mock.patch.object(updater, "_git", side_effect=fake_git):
            self.assertEqual(updater.run(self.root, "0.1.0", check_only=False), 0)

        verbs = [args[0] for args in calls]
        self.assertIn("fetch", verbs)
        self.assertIn("checkout", verbs)
        # checked out the resolved latest tag
        self.assertTrue(any(args[0] == "checkout" and "v0.2.0" in args for args in calls))


class UpdaterNotifyTests(unittest.TestCase):
    """The passive 'new version available' notice: cached, opt-out, failsafe."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self._tmp.name}, clear=False)
        self._env.start()
        os.environ.pop("DESK_NO_UPDATE_CHECK", None)  # enabled by default for these tests

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def test_notifies_when_newer(self):
        buf = io.StringIO()
        with mock.patch.object(updater, "latest_version_online", return_value="v0.2.0"):
            updater.maybe_notify("0.1.0", stream=buf)
        out = buf.getvalue()
        self.assertIn("v0.2.0", out)
        self.assertIn("desk update", out)

    def test_silent_when_current(self):
        buf = io.StringIO()
        with mock.patch.object(updater, "latest_version_online", return_value="v0.1.0"):
            updater.maybe_notify("0.1.0", stream=buf)
        self.assertEqual(buf.getvalue(), "")

    def test_opt_out_env_silences(self):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"DESK_NO_UPDATE_CHECK": "1"}), \
             mock.patch.object(updater, "latest_version_online", return_value="v9.9.9") as online:
            updater.maybe_notify("0.1.0", stream=buf)
        self.assertEqual(buf.getvalue(), "")
        online.assert_not_called()  # opt-out short-circuits before any network

    def test_failsafe_never_raises(self):
        buf = io.StringIO()
        with mock.patch.object(updater, "latest_version_online", side_effect=RuntimeError("boom")):
            updater.maybe_notify("0.1.0", stream=buf)  # must not raise
        self.assertEqual(buf.getvalue(), "")

    def test_uses_fresh_cache_without_network(self):
        # Seed a fresh cache; the notifier must read it and skip the network.
        updater._write_cache("v0.5.0")
        buf = io.StringIO()
        with mock.patch.object(updater, "latest_version_online", side_effect=AssertionError("network hit")) as online:
            updater.maybe_notify("0.1.0", stream=buf)
        self.assertIn("v0.5.0", buf.getvalue())
        online.assert_not_called()

    def test_stale_cache_triggers_refresh(self):
        updater._write_cache("v0.4.0")
        # Force the cache to look old.
        cache_path = updater._cache_path()
        import json as _json
        cache_path.write_text(_json.dumps({"latest": "v0.4.0", "checked_at": 0}), encoding="utf-8")
        buf = io.StringIO()
        with mock.patch.object(updater, "latest_version_online", return_value="v0.6.0") as online:
            updater.maybe_notify("0.1.0", stream=buf)
        online.assert_called_once()
        self.assertIn("v0.6.0", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)

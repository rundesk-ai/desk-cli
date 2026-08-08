#!/usr/bin/env python3
"""The ``desk`` command surface.

This wraps the full-API command tree in ``rundesk.build_parser`` (every Rundesk
endpoint: account, projects, pages, tasks, weeks, assets, desks) with the things
a personal, installable CLI needs on top of the raw API:

  * ``desk profile …`` — manage local API credentials (multiple named profiles),
    plus a global ``--profile NAME`` to target one for a single command,
  * ``desk --env-profile NAME …`` — use one complete Rundesk-injected suffixed
    environment profile without mixing it with saved/default credentials,
  * ``desk update`` / ``desk uninstall`` / ``desk help``, and the desk-bound
    surface itself: ``desk show`` (identity, owner, projects), ``desk inbox``,
    and ``desk mentions``.

For any API command it resolves credentials from the profile store (see
``profiles.resolve_credentials``) and constructs a ``RundeskClient`` from them,
then dispatches to the command's handler. It reuses ``rundesk.py``'s ``--confirm``
delete-gating and the ``RundeskError`` → exit-code contract unchanged.
"""

from __future__ import annotations

import argparse
import getpass
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))          # flat imports: client, rundesk, profiles, updater
sys.path.insert(0, str(HERE.parent))   # package import: desk_cli (for __version__)

import profiles  # noqa: E402
import rundesk as api  # noqa: E402
import updater  # noqa: E402
from client import RundeskClient, RundeskError  # noqa: E402
from desk_cli import __version__  # noqa: E402

# repo root = .../desk-cli (src/desk_cli → src → repo root); used by `desk update`.
REPO_ROOT = HERE.parent.parent

# Where install.sh may have symlinked the `desk` shim; scanned by `desk uninstall`.
_BIN_DIRS = ("/usr/local/bin", str(Path.home() / ".local" / "bin"))


# ── Parser assembly (full API + our groups) ────────────────────────────────
def _subparsers(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    raise RuntimeError("expected a subparsers action on the API parser")


def _hide_subcommand(sub: argparse._SubParsersAction, name: str) -> None:
    """Keep a subcommand working but drop it from the help listing. `help` alone
    is not enough: argparse prints a `help=SUPPRESS` choice as a literal
    "==SUPPRESS==" row, so its pseudo-action has to go."""
    sub._choices_actions = [a for a in sub._choices_actions if getattr(a, "dest", None) != name]


def _cmd_show(args: argparse.Namespace, client: RundeskClient) -> int:
    """`desk show` — this desk: identity, owner, and projects. (The account
    record behind the key is available via `desk account`.)"""
    api._emit(client.get_desk(as_text=not args.json), args.json)
    return 0


def _cmd_inbox(args: argparse.Namespace, client: RundeskClient) -> int:
    """`desk inbox` — this week's tasks + mentions, or a specific week / the
    unscheduled inbox. The core desk read, promoted to a top-level command."""
    api._emit(
        client.get_desk_inbox(week=args.week, unscheduled=args.unscheduled, as_text=not args.json),
        args.json,
    )
    return 0


def _cmd_mentions(args: argparse.Namespace, client: RundeskClient) -> int:
    """`desk mentions` — unread mentions on this desk's tasks, newest first."""
    api._emit(client.get_desk_mentions(limit=args.limit, as_text=not args.json), args.json)
    return 0


def _reshape_desk_surface(sub: argparse._SubParsersAction) -> None:
    """Add the desk-bound surface the installed CLI owns: `show` (this desk's
    identity, owner, and projects), `inbox`, and `mentions`. `whoami` stays
    registered as a hidden alias of `show` so installed agents and scripts that
    already call it keep working. The account record behind the key stays
    available via `desk account`."""
    show = sub.add_parser("show", help="This desk: identity, owner, and projects.")
    show.add_argument("--json", action="store_true", help="Print the raw desk JSON.")
    show.set_defaults(handler=_cmd_show)

    whoami = sub.add_parser("whoami", help=argparse.SUPPRESS)  # hidden alias of `show`
    whoami.add_argument("--json", action="store_true", help="Print the raw desk JSON.")
    whoami.set_defaults(handler=_cmd_show)
    _hide_subcommand(sub, "whoami")

    inbox = sub.add_parser(
        "inbox",
        help="This desk's inbox: this week's tasks + mentions; --week / --unscheduled to filter.",
    )
    scope = inbox.add_mutually_exclusive_group()
    scope.add_argument("--week", type=int, help="A task_weeks id — that week's tasks (plain list).")
    scope.add_argument("--unscheduled", action="store_true", help="The desk's no-week (unscheduled) inbox tasks.")
    inbox.add_argument("--json", action="store_true", help="Print the raw inbox JSON.")
    inbox.set_defaults(handler=_cmd_inbox)

    mentions = sub.add_parser("mentions", help="Unread mentions on this desk's tasks.")
    mentions.add_argument("--limit", type=int, help="1–100 — cap the number of mentions returned.")
    mentions.add_argument("--json", action="store_true", help="Print the raw mentions JSON.")
    mentions.set_defaults(handler=_cmd_mentions)


def build_parser() -> argparse.ArgumentParser:
    parser = api.build_parser()
    parser.prog = "desk"
    parser.description = "desk — a command-line client for the Rundesk API."
    parser.add_argument("--version", action="version", version=f"desk {__version__}")
    credential_profile = parser.add_mutually_exclusive_group()
    credential_profile.add_argument(
        "--profile",
        help="Use a specific saved profile for this command (overrides the default). "
        "Place it before the subcommand, e.g. `desk --profile work tasks list`.",
    )
    credential_profile.add_argument(
        "--env-profile",
        help="Use one complete Rundesk-injected environment profile, e.g. "
        "RUNDESK_API_KEY__ALAN (+ optional matching base URL).",
    )

    # The rundesk.py parser exposes --env-file for the single-.env model; profiles
    # supersede it here, so hide it from help (still accepted, just ignored).
    for action in parser._actions:
        if "--env-file" in getattr(action, "option_strings", []):
            action.help = argparse.SUPPRESS

    sub = _subparsers(parser)
    # Name the choice slot instead of listing every command inline: the usage
    # line stays readable AND the hidden `whoami` alias is not advertised there.
    sub.metavar = "<command>"
    _reshape_desk_surface(sub)

    profile = sub.add_parser("profile", help="Manage local Rundesk API profiles (stored on this machine).")
    p_sub = profile.add_subparsers(dest="profile_action", required=True)
    p_add = p_sub.add_parser("add", help="Add a profile interactively (name, base URL, API key).")
    p_add.add_argument("name", nargs="?", help="Profile name (prompted if omitted).")
    p_sub.add_parser("list", help="List saved profiles (API keys masked).")
    p_use = p_sub.add_parser("use", help="Set the default profile.")
    p_use.add_argument("name")
    p_show = p_sub.add_parser("show", help="Show a profile's details (API key masked).")
    p_show.add_argument("name", nargs="?", help="Profile name (defaults to the current default).")
    p_remove = p_sub.add_parser("remove", help="Delete a saved profile.")
    p_remove.add_argument("name")
    p_local = p_sub.add_parser(
        "local",
        help="Bind the current directory (and subdirectories) to a profile via a .desk-profile file.",
    )
    p_local.add_argument("name", nargs="?", help="Profile to use here (omit to show the current directory's profile).")
    p_local.add_argument("--clear", action="store_true", help="Remove the .desk-profile in this directory.")

    update = sub.add_parser("update", help="Update desk to the latest released version.")
    update.add_argument("--check", action="store_true", help="Only check for an update; change nothing.")

    uninstall = sub.add_parser("uninstall", help="Remove the desk command from this computer.")
    uninstall.add_argument(
        "--purge",
        action="store_true",
        help="Also delete all saved profiles/credentials in ~/.config/desk.",
    )

    help_cmd = sub.add_parser(
        "help",
        help="Show help for desk or a nested command (`desk help tasks move-week`).",
    )
    help_cmd.add_argument(
        "topic", nargs="*", help="A command path to show help for; omit for the full list."
    )

    # A bare `desk` (no command) prints help instead of erroring.
    sub.required = False

    return parser


# ── Local commands (no API key required) ───────────────────────────────────
def _account_identity(account: object) -> str:
    fields = account if isinstance(account, dict) else {}
    name = fields.get("name") or "?"
    email = fields.get("email")
    return f"{name} <{email}>" if email else str(name)


def _yes(prompt: str) -> bool:
    return input(prompt).strip().lower() in ("y", "yes")


def cmd_profile(args: argparse.Namespace) -> int:
    action = args.profile_action
    if action == "add":
        return _profile_add(args)
    if action == "list":
        return _profile_list()
    if action == "use":
        return _profile_use(args)
    if action == "show":
        return _profile_show(args)
    if action == "remove":
        return _profile_remove(args)
    if action == "local":
        return _profile_local(args)
    raise RundeskError("usage", f"unknown profile action {action!r}.")


def _profile_add(args: argparse.Namespace) -> int:
    cfg = profiles.load_config()
    name = (args.name or input("Profile name: ")).strip()
    if not name:
        raise RundeskError("usage", "a profile name is required.")
    if name in cfg["profiles"] and not _yes(f"Profile {name!r} already exists. Overwrite? [y/N]: "):
        print("Aborted.")
        return 0

    base_url = input(f"Base URL [{profiles.DEFAULT_BASE_URL}]: ").strip() or profiles.DEFAULT_BASE_URL
    api_key = getpass.getpass("API key (hidden): ").strip()
    if not api_key:
        raise RundeskError("usage", "an API key is required.")

    # A profile is only saved if the key authenticates against /me — a bad key or
    # base URL is an error, never a silently-stored broken profile.
    print(f"Verifying key against {base_url} …")
    try:
        account = RundeskClient(base_url=base_url, api_key=api_key).get_account()
    except RundeskError as exc:
        print(f"desk: could not verify the API key against {base_url}: {exc}", file=sys.stderr)
        print("Profile not saved — check the base URL and API key, then try again.", file=sys.stderr)
        return exc.exit_code
    print(f"  authenticated as {_account_identity(account)}")

    profiles.add_profile(cfg, name, base_url, api_key)
    if not cfg.get("default"):
        cfg["default"] = name
    elif cfg["default"] != name and _yes(f"Set {name!r} as the default profile? [y/N]: "):
        cfg["default"] = name
    profiles.save_config(cfg)

    marker = " (default)" if cfg.get("default") == name else ""
    print(f"Saved profile {name!r}{marker} → {profiles.config_path()}")
    return 0


def _profile_list() -> int:
    cfg = profiles.load_config()
    profs = cfg.get("profiles", {})
    if not profs:
        print("No profiles yet. Run `desk profile add` to create one.")
        return 0
    default = cfg.get("default")
    for name in sorted(profs):
        prof = profs[name]
        marker = "*" if name == default else " "
        print(f" {marker} {name:20} {prof.get('base_url', ''):28} key={profiles.mask_key(prof.get('api_key', ''))}")
    print("\n* = default profile")
    return 0


def _profile_show(args: argparse.Namespace) -> int:
    cfg = profiles.load_config()
    name = args.name or cfg.get("default")
    if not name:
        raise RundeskError("usage", "no profile given and no default is set.")
    prof = cfg["profiles"].get(name)
    if not prof:
        raise RundeskError("usage", f"no profile named {name!r}.")
    default_marker = "  (default)" if cfg.get("default") == name else ""
    print(f"name:     {name}{default_marker}")
    print(f"base_url: {prof.get('base_url', '')}")
    print(f"api_key:  {profiles.mask_key(prof.get('api_key', ''))}")
    print(f"config:   {profiles.config_path()}")
    return 0


def _profile_use(args: argparse.Namespace) -> int:
    cfg = profiles.load_config()
    if args.name not in cfg.get("profiles", {}):
        raise RundeskError("usage", f"no profile named {args.name!r}. Run `desk profile list` to see profiles.")
    profiles.set_default(cfg, args.name)
    profiles.save_config(cfg)
    print(f"default profile → {args.name}")
    return 0


def _profile_remove(args: argparse.Namespace) -> int:
    cfg = profiles.load_config()
    if args.name not in cfg.get("profiles", {}):
        raise RundeskError("usage", f"no profile named {args.name!r}.")
    if not _yes(f"Delete profile {args.name!r}? [y/N]: "):
        print("Aborted.")
        return 0
    profiles.remove_profile(cfg, args.name)
    profiles.save_config(cfg)
    tail = f"; default is now {cfg['default']!r}" if cfg.get("default") else "; no default profile set"
    print(f"Removed profile {args.name!r}{tail}")
    return 0


def _profile_local(args: argparse.Namespace) -> int:
    path = Path.cwd() / profiles.LOCAL_PROFILE_FILENAME
    if args.clear:
        if path.exists():
            path.unlink()
            print(f"removed {path}")
        else:
            print(f"no {profiles.LOCAL_PROFILE_FILENAME} in this directory")
        return 0
    if args.name:
        cfg = profiles.load_config()
        if args.name not in cfg.get("profiles", {}):
            print(
                f"warning: no saved profile named {args.name!r} yet — add it with `desk profile add {args.name}`.",
                file=sys.stderr,
            )
        path.write_text(f"profile={args.name}\n", encoding="utf-8")
        print(f"This directory now uses profile {args.name!r} ({path}).")
        return 0
    # No name → report what the current directory resolves to.
    local = profiles.dir_profile()
    if local:
        print(f"This directory uses profile {local!r} (from {profiles.LOCAL_PROFILE_FILENAME}).")
    else:
        print(f"No {profiles.LOCAL_PROFILE_FILENAME} found in this directory or any parent.")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    return updater.run(REPO_ROOT, __version__, check_only=args.check)


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Remove the `desk` command: unlink any symlink on PATH that points at this
    checkout's shim, optionally purge saved profiles, and tell the user how to
    delete the checkout itself for a complete removal."""
    shim = (REPO_ROOT / "desk").resolve()
    removed = []
    for directory in _BIN_DIRS:
        link = Path(directory) / "desk"
        try:
            if link.is_symlink() and Path(os.readlink(link)).resolve() == shim:
                link.unlink()
                removed.append(str(link))
        except OSError:
            continue
    if removed:
        for path in removed:
            print(f"removed {path}")
    else:
        print("No desk symlink pointing at this checkout was found on PATH.")

    if args.purge:
        config_dir = profiles.config_dir()
        if config_dir.exists() and _yes(f"Also delete all saved profiles at {config_dir}? [y/N]: "):
            shutil.rmtree(config_dir, ignore_errors=True)
            print(f"removed {config_dir}")

    print(f"\nThe desk files remain at {REPO_ROOT}. To remove them completely, run:")
    print(f"    rm -rf {REPO_ROOT}")
    return 0


def cmd_help(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """``desk help [group [verb]]`` — full, group, or leaf help."""
    topics = getattr(args, "topic", None) or []
    if not topics:
        parser.print_help()
        return 0

    target = parser
    walked = []
    for topic in topics:
        try:
            choices = _subparsers(target).choices
        except RuntimeError:
            choices = {}
        target = choices.get(topic)
        walked.append(topic)
        if target is None:
            path = " ".join(walked)
            print(
                f"desk: no such command path {path!r}. Run `desk help` for the command list.",
                file=sys.stderr,
            )
            return 2
    target.print_help()
    return 0


def _mint_key_to_profile(
    args: argparse.Namespace,
    client: RundeskClient,
    base_url: str,
) -> int:
    """Mint one desk key directly into the protected profile store.

    The API returns the credential once. Never route that response through the
    normal JSON emitter: keys may be stored, but must not appear on stdout.
    """
    profile_name = args.save_profile.strip()
    if not profile_name:
        raise RundeskError("usage", "--save-profile requires a non-empty name.")
    cfg = profiles.load_config()
    if profile_name in cfg.get("profiles", {}):
        raise RundeskError(
            "usage",
            f"profile {profile_name!r} already exists; remove it explicitly before replacing its key.",
        )

    try:
        # Prove the protected destination can be written before making the
        # irreversible API call. The second atomic save still owns the token.
        profiles.save_config(cfg)
    except OSError as exc:
        raise RundeskError(
            "usage", f"profile store is not writable; no key was minted: {exc}",
        ) from exc

    result = client.create_desk_key(
        args.desk_id, name=args.name, expires_at=args.expires_at,
    )
    token = result.get("plain_text_token") if isinstance(result, dict) else None
    if not isinstance(token, str) or not token:
        raise RundeskError(
            "unknown",
            "Rundesk minted a key but returned no credential to store; revoke that desk key immediately.",
        )

    try:
        # Another process may change profiles while the API request is in
        # flight. Save with compare-and-swap; a conflict reloads, preserves the
        # other writer, chooses another name if needed, and retries.
        saved_name = profile_name
        for _attempt in range(5):
            cfg = profiles.load_config()
            saved_name = profile_name
            if saved_name in cfg.get("profiles", {}):
                stem = f"{profile_name}-minted"
                saved_name = stem
                suffix = 2
                while saved_name in cfg.get("profiles", {}):
                    saved_name = f"{stem}-{suffix}"
                    suffix += 1
            profiles.add_profile(cfg, saved_name, base_url, token)
            try:
                profiles.save_config(cfg)
            except profiles.ConfigConflict:
                continue
            break
        else:
            raise profiles.ConfigConflict()
    except (RundeskError, OSError) as exc:
        raise RundeskError(
            "unknown",
            "a key was minted but could not be stored; revoke that desk key in Rundesk immediately: "
            f"{exc}",
        ) from exc
    print(
        f"Saved minted desk key as profile {saved_name!r} "
        f"(key={profiles.mask_key(token)})."
    )
    return 0


# ── Entry point ────────────────────────────────────────────────────────────
def _dispatch(args: argparse.Namespace) -> int:
    # Local commands never touch the API or the credential store's resolution.
    if args.command == "profile":
        try:
            return cmd_profile(args)
        except RundeskError as exc:
            print(f"desk: {exc}", file=sys.stderr)
            return exc.exit_code
    if args.command == "update":
        return cmd_update(args)
    if args.command == "uninstall":
        return cmd_uninstall(args)

    # Full-API commands: reuse rundesk.py's delete-gating + error contract, but
    # build the client from the resolved profile instead of a single .env.
    action = getattr(args, f"{args.command}_action", None)
    try:
        if (args.command, action) in api._CONFIRM_GATED:
            api._confirm_or_abort(args)
        base_url, api_key = profiles.resolve_credentials(
            getattr(args, "profile", None),
            env_profile=getattr(args, "env_profile", None),
        )
        client = RundeskClient(base_url=base_url, api_key=api_key)
        if args.command == "desks" and action == "mint-key":
            return _mint_key_to_profile(args, client, base_url)
        return args.handler(args, client)
    except RundeskError as exc:
        print(f"desk: {exc}", file=sys.stderr)
        return exc.exit_code


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # A bare `desk` or `desk help [topic]` just prints help — no API, no notice.
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "help":
        return cmd_help(parser, args)

    rc = _dispatch(args)
    # After the command runs, print a passive "new version available" hint. It is
    # cached + fully failsafe (see updater.maybe_notify) and never affects rc. The
    # update/uninstall commands report their own version state, so skip them.
    if args.command not in ("update", "uninstall"):
        updater.maybe_notify(__version__)
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

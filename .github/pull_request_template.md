## Summary

<!-- State what changes and why in one or two lines. -->

-

## Scope and compatibility

- Runtime files changed:
- Skill packages changed:
- User-visible behavior:
- Preserved behavior:
- Command, output, stored-format, install, or update compatibility:
- Dependencies added: none

## Critical risk

<!-- Required for auth, credentials, privacy, destructive commands, installer/updater behavior, or other critical risk. Write "None" when no critical risk applies. -->

- Risk:
- Guard:

## Validation

- [ ] `python3 tests/test_profiles.py && python3 tests/test_cli.py && python3 tests/test_rundesk.py` passes.
- [ ] All Python sources and tests parse on Python 3.9+.
- [ ] `bash -n install.sh` passes, or the installer was not touched.
- [ ] Every changed public CLI or skill workflow has focused offline regression proof recorded below.
- [ ] `git diff --check` passes.
- [ ] Required GitHub checks pass for the exact head commit.

```text
# Exact focused and manual verification commands with observed results
```

## Repository gates

- [ ] The diff contains no credential, API key, account data, private-project language, owner-specific path, or unrelated artifact.
- [ ] Runtime code remains Python 3.9+ and standard-library only, unless the owner approved a dependency.
- [ ] Automated tests remain offline and never call the real Rundesk API.
- [ ] API keys remain masked and stdout, stderr, prompts, JSON, and tests do not expose secrets.
- [ ] Default text output, `--json`, command/flag behavior, and stored formats preserve their documented contracts, or the approved compatibility impact is stated above.
- [ ] Changed command, profile, install, update, or skill behavior has matching help, README, and agent-facing documentation.
- [ ] `README.md`, `manifest.json`, and `skills/` agree.
- [ ] Runtime and catalog versions match the intended release scope and are stated below.

## Release

- Runtime version: `<before>` → `<after>`
- Catalog manifest version: `<before>` → `<after>`
- SemVer reason:
- Release or follow-up required after merge:

## Manual user path

<!-- Give the shortest representative installed command or agent workflow and expected result. State clearly when no live API call or installed-catalog smoke test was made. -->

```text

```

**Issue linkage**

<!-- Use one standalone `Closes #<number>.` line per issue this PR completes. Use `Refs` for partial work. Remove this comment, but keep the label. -->

**Agent**

<!-- Replace the placeholder with the filing agent's display name. Do not add provider, model, tool, session, or generated-by branding. -->

🤖 by <Agent>

# AGENTS

Rules for every agent working in this repository. These instructions define how to work here; where they conflict with general habits, this file wins.

## Purpose

This repository ships the zero-dependency `desk` command-line client and a Rundesk skill catalog.
It is installed on other people's machines, stores API credentials, and is called by scripts and
agents that parse its output. The command surface, default and JSON output, stored files, installer,
updater, catalog contents, and Python 3.9 floor are published contracts.

Read [`.ai/BRIEF.md`](.ai/BRIEF.md) for scope, [`.ai/CODEMAP.md`](.ai/CODEMAP.md) for the code map,
and [`.ai/MEMORY.md`](.ai/MEMORY.md) for current operating lessons. Help text is the source of truth
for command use; `README.md` summarizes the consumer surface.
Use the canonical [Rundesk skill-catalog repository guide](https://github.com/rundesk-ai/rundesk-cli/blob/main/docs/catalogs.md)
when adding or reorganizing a published catalog.

## Before you work

1. Read `.ai/BRIEF.md`, `.ai/CODEMAP.md`, and `.ai/MEMORY.md`, then read every file you will edit.
2. Load the smallest complete set of applicable runtime skills. Use `writing-skills` for bundled
   skills, `naming-grammar-conventions` before choosing or changing recurring or cross-layer terms,
   and `managing-github` for pull requests or releases.
3. Inspect `git status` and the relevant diff before editing. Preserve other people's changes and
   do not assume an unfamiliar file is disposable.
4. Search before adding logic, terminology, tests, or documentation. Reuse, extend, or refactor the
   existing answer instead of creating a second one.
5. Establish the requested outcome, boundaries, compatibility requirements, and observable proof.
   Investigate concerns with repository evidence before contradicting them.
6. Use [`.github/pull_request_template.md`](.github/pull_request_template.md) for pull-request work;
   preserve all eight headings and its checklists.

## Repository layout

```text
desk                         checkout entry point
src/desk_cli/
  cli.py                     profiles, update, help, and top-level Desk commands
  rundesk.py                 full API command tree and rendering
  client.py                  authentication, HTTP transport, and response parsing
  profiles.py                profile storage and credential resolution
  updater.py                 update checks and replacement
skills/<skill>/              bundled Rundesk skill packages
  SKILL.md                   routing and core workflow
  rundesk.json               declared credential needs, when required
  references/                conditional detail
manifest.json                catalog identity and version
tests/test_profiles.py       profiles, credential resolution, and updater
tests/test_cli.py            command walk, fake transport, local commands, and catalog contract
tests/test_rundesk.py        REST client request and response behavior
install.sh                   installer and release handoff
.ai/                        agent-facing scope, map, and lessons
README.md                    install, command, profile, update, and catalog documentation
```

Keep new code in the narrowest existing module. Do not create a parallel command path, credential
resolver, transport, renderer, catalog index, or documentation source of truth.

## Package and artifact contract

- Runtime code uses Python 3.9+ and the standard library only. Do not add, vendor, or require a
  package, use Python 3.10+ syntax, or import a module introduced after 3.9.
- Preserve command and flag names, exit behavior, stdout/stderr separation, default text shape and
  ordering, and raw `--json` payloads. JSON output contains the API payload and no presentation.
- Preserve `config.json`, `.desk-profile`, credential-resolution order, XDG paths, `~/.desk` install
  layout, archive layout, entry-point location, and updater compatibility with older installs.
- `manifest.json` and each `skills/<name>/SKILL.md` form one catalog. Skill directory and
  frontmatter names match; required `rundesk.json` metadata is complete; references and scripts stay
  inside their package. `README.md`, `manifest.json`, and discovered packages must agree.
- A skill must be self-contained at runtime. Do not make it depend on another repository checkout.
  Use `writing-skills` and the existing catalog tests for every bundled-skill change.
- The runtime version and catalog manifest version are separate release contracts. Change either
  only when its published artifact changes and the repository's release rules require it.

## Safety and approval gates

Get explicit owner approval before changing a command/output/stored-format compatibility contract,
the Python floor or dependencies, credential resolution, installer/updater behavior, install or
archive layout, persisted state, an out-of-scope file deletion, these rule files, or before
committing, pushing, tagging, or releasing unless the current request already grants that action.

- Never commit or expose a credential, full API key, account/customer data, private identifier,
  private-project language, or owner-specific path. Use synthetic public examples.
- Never print a full key in stdout, stderr, prompts, errors, logs, or JSON. Preserve key validation,
  masking, and config-file mode `0600`.
- Never write outside `${XDG_CONFIG_HOME:-~/.config}/desk/`, `~/.desk`, or an explicitly requested
  working-directory `.desk-profile`.
- Never call the real Rundesk API from a test. Use the fake transport and keep every automated test
  offline.
- Never use destructive Git commands to undo shared work, including `reset --hard`, `checkout`, or
  `restore`. Make narrow edits and preserve unrelated worktree and index state.
- Never leave debug output, `breakpoint()`, `pdb`, commented-out code, a disabled test, placeholder,
  or task-created temporary artifact.
- Never report success that the command or test did not earn. A check that discovered no work did
  not pass.

## Delegation

Delegate only bounded, self-contained work when it materially helps. Assign non-overlapping file
ownership, the applicable rules, prohibited changes, expected evidence, and a definition of done.
Delegation never expands the request or approval. The parent agent retains architecture and naming
decisions, integrates every result, inspects the resulting diff, and runs the final proof. Do not
duplicate delegated work or accept a summary as verification.

## Architecture and conventions

Import dependencies point from callers to callees: `cli.py` -> command layer (`rundesk.py`) ->
`client.py`, with `cli.py` also importing `client.py` directly to construct the client. Requests
flow from `cli.py` through `rundesk.py` to `client.py`, and parsed results return to the caller for
rendering. Lower layers never import or perform the work of their callers.

- `client.py` owns authentication, one HTTP request seam, and parsed responses or dedicated
  exceptions. It knows no commands, profiles, rendering, or process exits.
- `rundesk.py` commands parse arguments, call the client, and render results. They contain no direct
  `urllib` call; all HTTP passes through the client seam patched by `tests/test_cli.py`.
- `cli.py` owns top-level dispatch and builds the client from the single resolution implementation
  in `profiles.py`. Never copy or reorder credential resolution.
- stdout is payload; stderr is diagnostics. Success exits `0`; failure exits non-zero. Expected
  failures produce one actionable stderr line and no traceback.
- Default list output is compact and stable: one entity per line, only decision-relevant fields,
  and stable ordering. `--json` is unmodified API data.
- Destructive commands refuse without `--confirm`. Profiles are saved only after authentication.
- Resolve home with `Path.home()` or `expanduser()` and honor `XDG_CONFIG_HOME`; never hardcode a
  user, home, or absolute path.
- Use PEP 8, four-space indentation, and type hints on every function signature. Prefer short
  functions, early returns, explicit parameters, dedicated expected-failure exceptions, and no
  mutable global state. Consolidate parsing, rendering, or validation repeated across commands.
- Use established product terms. Operations name outcomes; values and entities use noun phrases.
  Preserve published spellings and document intentional boundary mappings rather than silently
  renaming them.

## Documentation duties

Keep documentation true in the same change as behavior.

- Update `.ai/CODEMAP.md` when files move or responsibilities change. Add only a durable,
  non-obvious lesson to `.ai/MEMORY.md`; do not put rationale or task history there.
- Update code help and the README command list together for a command or flag change. Every README
  command must exist, and every public command must appear in `desk help`.
- Update the relevant README section for install, update, profile, credential-resolution, or catalog
  behavior changes.
- Update a skill's core instructions, conditional references, metadata, README/catalog description,
  and tests together when its public workflow changes.
- Keep `AGENTS.md` and `CLAUDE.md` byte-identical. Edit one complete source and copy it to the other;
  never maintain divergent instructions.

## Build, test, and run

There is no build or dependency-install step. Use the system Python and keep update checks disabled
during tests.

```sh
DESK_NO_UPDATE_CHECK=1 python3 tests/test_profiles.py
DESK_NO_UPDATE_CHECK=1 python3 tests/test_cli.py
DESK_NO_UPDATE_CHECK=1 python3 tests/test_rundesk.py
python3 -c "import ast, glob; [ast.parse(open(f).read()) for f in glob.glob('src/desk_cli/*.py') + glob.glob('tests/*.py')]; print('parse OK')"
bash -n install.sh
git diff --check
```

The exact full gate is the three named suites above; do not replace it with discovery or a subset.
Read each suite's `Ran N tests` result and exit status. New or changed commands belong in the
`test_cli.py` fake-transport walk, client methods in `test_rundesk.py`, and profile/resolution/update
behavior in `test_profiles.py`. Use only synthetic data and temporary XDG paths.

For an affected CLI, installer, or updater path, run the shortest safe representative command and a
material refusal/failure path; inspect exit code, stdout, stderr, and filesystem effects. Record the
exact environment, commands, counts, and observations. Do not make a live API call merely for proof.

## Pull requests and releases

- Complete the pull-request template from evidence for the exact head commit. Explain every
  unchecked or inapplicable item; never pre-check a future result.
- Inspect the complete diff and commit-visible artifacts for secrets, credentials, PII, private
  identifiers, private-project language, owner-specific paths, and unrelated files before
  publication. Use a GitHub noreply identity for public commit authorship and verify actual metadata.
- Required CI must pass for the exact PR head. After merge, verify the exact merge commit's `main`
  workflow before any authorized tag or release.
- Releases require `src/desk_cli/__init__.py::__version__` and tag `vX.Y.Z` to agree. Preserve the
  archive and entry-point layout so an older `desk update` can install the new release.
- Process-only changes to `AGENTS.md`, `CLAUDE.md`, pull-request templates, or equivalent repository
  guidance do not change runtime or catalog versions. Published command or skill behavior follows
  its normal SemVer and release rules.
- Do not commit, push, merge, tag, publish, or release unless the current request explicitly grants
  that action.

## Definition of done

A task is complete only when all applicable items below are observed, not inferred:

1. The full requested scope is implemented, with no unreported stub, TODO, unrelated change, or
   temporary artifact.
2. All three suites pass with non-zero test counts; Python sources and tests parse; `bash -n
   install.sh` and `git diff --check` pass.
3. Changed public behavior has focused offline regression proof and the relevant safe user-path and
   refusal-path observation. An intentionally process-only guide change requires guide parity and
   heading-order proof, not a runtime version bump.
4. Command, output, JSON, stored-format, credential, XDG, install, update, Python-floor, and catalog
   contracts remain intact unless an approved change says otherwise.
5. Documentation is current, and `AGENTS.md` and `CLAUDE.md` are byte-identical with the required
   heading order.
6. The final diff is narrow, clean, privacy-reviewed, and contains no secret, private identifier,
   debug residue, disabled test, or owner-specific artifact.
7. Report changed paths, exact commands and observed results, manual checks, and every unrun or
   blocked check. Re-read this file and verify this definition before calling the work complete.

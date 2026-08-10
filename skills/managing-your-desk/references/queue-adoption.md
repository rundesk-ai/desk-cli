# Queue adoption and compact task briefs

Read this only when the Desk owner or current request explicitly authorizes adding the persistent
queue contract to an agent's standing rules, or when a compact brief/comment example is needed.
Ordinary task, inbox, and mention work never authorizes rule-file edits.

## Adopt the standing rule

Adopt this only for an agent that owns a persistent Desk queue, never for a bounded specialist. Do
not infer a home path or editing authority. Preserve every unrelated standing rule: merge the
existing guidance rather than replacing either file wholesale.

When both `AGENTS.md` and `CLAUDE.md` are used, reconcile their existing guidance, add the following
section once, write the same complete merged content to both files, and verify the full files are
byte-identical with `cmp -s AGENTS.md CLAUDE.md`. A copied section alone is insufficient when the
rest of the files differ.

```markdown
## Desk queue ownership

Use the `managing-your-desk` skill and Desk to self-manage your persistent operational queue; the
owner should not micromanage it.
Bounded specialist agents do not own persistent queues. Treat This week as the ordered commitment:
keep active work there, keep it prioritized, and work top-down. If it is empty, inspect the inbox
and mentions and pull handleable work into This week before starting. Capture authorized owner
requests and goal-derived work as tasks; split large goals into independently completable chunks.
Give each active task a compact outcome, scope/limits, definition of done, required proof, and next
action or blocker. GitHub/project state is implementation truth; Desk records operational
commitment. Comment briefly only for decisions, blockers, handoffs/PRs, resumable state, and exact
verification. Mark done only after delivery and verification. Schedule a real future week, deadline,
or recurrence for follow-up that truly cannot happen now; never leave a vague reminder. Contact or
mention the Desk owner only when blocked or when material scope or authority is missing.
```

Do not edit agent homes during skill installation, granting, or normal queue operation. If the
authorized merge cannot preserve existing guidance and make both files identical, stop and ask the
owner to resolve the conflict.

## Keep tasks and comments compact

Use this task-body shape; omit `Blocked` when there is none:

```markdown
Outcome: <observable result>
Scope/limits: <included work; important non-goals or authority limits>
Done: <independently checkable completion criteria>
Proof: <required command, artifact, review, or user-path observation>
Next: <one concrete action>
Blocked: <condition and the exact decision or authority needed>
```

Keep changing plans, code state, and detailed investigation in GitHub or the project. Use at most a
short Desk comment when durable coordination value exists, for example:

```text
Decision: keep the released JSON shape; implement the new field behind --verbose.
Blocked: production fixture access is missing; owner decision needed on synthetic proof.
PR: <link> — ready for review; checks named in the PR are green.
Resume: parser updated; next run tests/test_cli.py, then inspect default output.
Verified: python3 tests/test_cli.py — 88 tests passed, 0 skipped.
```

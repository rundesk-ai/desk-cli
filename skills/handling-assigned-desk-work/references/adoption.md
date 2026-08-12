# Adopt passive assigned-task routing

Use this only when the owner asks to configure an agent for passive Desk work. Grant
`handling-assigned-desk-work`, not `managing-your-desk`, and keep the agent's existing local task
management unchanged.

Inspect both `AGENTS.md` and `CLAUDE.md`, preserve every unrelated rule, and merge this short routing
cue into both files with identical bytes:

```markdown
## Assigned Desk work

Keep local task management as the execution and continuity system. When the owner names a Desk task
or explicitly asks you to handle assigned Desk tasks, load `handling-assigned-desk-work`; never treat
Desk inbox visibility as permission to choose work.
```

Do not copy the skill's identity, task-authority, comment, or lifecycle rules into the agent files;
the skill is their source of truth. Verify the grant and merged rules:

```sh
"$RUNDESK_COMMAND" skills list <agent>
"$RUNDESK_COMMAND" skills doctor <agent>
cmp -s AGENTS.md CLAUDE.md
```

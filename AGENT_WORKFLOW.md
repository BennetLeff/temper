# Agentic Workflow Guide

This project supports a multi-agent workflow where a **Master Agent** delegates tasks to specialized **Worker Agents**.

## How to Delegate

As the Master Agent, you can use the `dispatch.sh` tool to assign work.

### Syntax

`./tools/agents/dispatch.sh <role> "<instruction>" <output_file>`

### Available Roles & Models

We use a tiered model strategy to balance reasoning depth and speed.

| Role          | Model Tier            | Description                                      |
| ------------- | --------------------- | ------------------------------------------------ |
| **architect** | 🧠 **Thinking** (Pro) | High-level design, patterns, trade-off analysis. |
| **security**  | 🧠 **Thinking** (Pro) | Deep vulnerability analysis and audit.           |
| **coder**     | ⚡ **Fast** (Flash)   | Implementation, refactoring, efficiency.         |
| **tester**    | ⚡ **Fast** (Flash)   | Unit tests, edge case generation.                |

### Workflow Example

1. **Plan**: You receive a complex feature request.
2. **Design**: Delegate the design to the architect.
   ```bash
   ./tools/agents/dispatch.sh architect "Design the class structure for the new UserAuth module" docs/design/auth_design.md
   ```
3. **Review**: Read the output file (`read_file docs/design/auth_design.md`).
4. **Implement**: Delegate coding based on the design.
   ```bash
   ./tools/agents/dispatch.sh coder "Implement the UserAuth class based on docs/design/auth_design.md" src/auth.py
   ```
5. **Verify**: Delegate test generation.
   ```bash
   ./tools/agents/dispatch.sh tester "Create unit tests for src/auth.py" tests/test_auth.py
   ```

## Label-Driven Automation (Auto-Assign)

You can simply **label** an issue to trigger an agent workflow.

### Setup

Ensure you have the `auto_assign.py` script ready.

### Workflow

1.  **Tag an issue**: Add a label like `agent:coder`, `agent:security`, or `agent:architect` to any open issue.
    ```bash
    bd update temper-123 --label agent:security
    ```
2.  **Run the watcher**:

    ```bash
    python3 tools/agents/auto_assign.py
    ```

    _Tip: You can run this in a loop or a cron job._

3.  **Result**: The script will find the issue, remove the label (to prevent re-running), and dispatch the appropriate agent.

### Supported Labels

- `agent:architect`
- `agent:security`
- `agent:tester`
- `agent:coder`

## Best Practices

- **Atomic Tasks**: Give workers specific, contained tasks.
- **Context Passing**: Explicitly mention input files the worker needs to read in the instruction.
- **Output Verification**: Always read the output file produced by a worker before proceeding.

## Parallel Agent Configuration

When running multiple agents in parallel (e.g., in git worktrees), configure beads to avoid sync conflicts:

### Sandbox Mode (Required for Worktrees)

Worker agents in worktrees **MUST** use sandbox mode:

```bash
# In any worktree, use --sandbox flag for all bd commands
bd --sandbox list
bd --sandbox show temper-xxx
bd --sandbox update temper-xxx --status in_progress
bd --sandbox close temper-xxx --reason "Done"
```

### Read-Only Mode (For Read-Only Agents)

Agents that only need to read issues can use read-only mode:

```bash
bd --readonly list
bd --readonly show temper-xxx
```

### Why This Matters

Without sandbox mode, multiple agents cause:

- **Sync loop spam**: Daemon detects its own writes, triggers reimport every second
- **Warning noise**: "Uncommitted local changes detected" warnings flood logs
- **Database conflicts**: Multiple agents fighting over the same SQLite database
- **Git conflicts**: Auto-sync commits colliding between worktrees

### Configuration Reference

The main repo's `.beads/config.yaml` has debounce settings:

```yaml
flush-debounce: "10s" # Reduces sync frequency
```

For worker agents, always pass `--sandbox` to disable daemon entirely.

# Agentic Workflow Guide

## 🎭 Multi-Agent Parallelism

We employ a "Shared Knowledge, Isolated Execution" model. Agents operate in separate **Git Worktrees** but share a **Global OpenMemory** instance.

### Tiered Coordination Strategy

| Component             | Responsibility           | Isolation Level                           |
| --------------------- | ------------------------ | ----------------------------------------- |
| **Git Worktree**      | File system changes      | **Full Isolation** (Separate folders)     |
| **Beads (--sandbox)** | Task status tracking     | **Synced via Git** (Eventual consistency) |
| **OpenMemory**        | Global preferences/facts | **Shared** (Instant consistency)          |

### Parallel Worker Checklist

When a Worker Agent is spawned in a new worktree, it must perform the following "Onboarding" sequence:

1.  **Sync Local Task**: `bd --sandbox show <issue_id>` to get specific task constraints.
2.  **Query Global Wisdom**: Search **OpenMemory** for project-wide standards (e.g., "Standardized error handling patterns").
3.  **Execute**: Perform work using Conventional Commits.
4.  **Update Global Wisdom**: If a project-wide pattern is discovered or changed, save it to **OpenMemory** so agents in other worktrees benefit immediately.
5.  **Final Sync**: Run `bd sync` inside the worktree before the directory is deleted.

### ⚠️ Conflict Resolution

If two agents in different worktrees update the same `beads` issue, Git will handle the merge via the JSONL format. If a merge conflict occurs in `.beads/issues.jsonl`, run `bd sync` to trigger the intelligent merge driver.

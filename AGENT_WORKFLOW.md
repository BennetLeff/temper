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
2. **Context**: Query OpenMemory for relevant architectural facts.
3. **Design**: Delegate the design to the architect.
   ```bash
   ./tools/agents/dispatch.sh architect "Design the class structure for the new UserAuth module" docs/design/auth_design.md
   ```
4. **Review**: Read the output file.
5. **Implement**: Delegate coding based on the design.
   ```bash
   ./tools/agents/dispatch.sh coder "Implement the UserAuth class based on docs/design/auth_design.md" src/auth.py
   ```
6. **Reflection**: Post architectural decisions to OpenMemory.

## Label-Driven Automation (Auto-Assign)

You can simply **label** an issue to trigger an agent workflow.

### Workflow

1.  **Tag an issue**: Add a label like `agent:coder`, `agent:security`, or `agent:architect`.
    ```bash
    bd update temper-123 --label agent:security
    ```
2.  **Run the watcher**:
    ```bash
    python3 tools/agents/auto_assign.py
    ```
3.  **Result**: The script will find the issue, remove the label, and dispatch the appropriate agent.

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

## 🎭 Multi-Agent Parallelism

We employ a "Shared Knowledge, Isolated Execution" model. Agents operate in separate **Git Worktrees** but share a **Global OpenMemory** instance.

### Tiered Coordination Strategy

| Component             | Responsibility           | Isolation Level                           |
| --------------------- | ------------------------ | ----------------------------------------- |
| **Git Worktree**      | File system changes      | **Full Isolation** (Separate folders)     |
| **Beads (--sandbox)** | Task status tracking     | **Synced via Git** (Eventual consistency) |
| **OpenMemory**        | Global knowledge/wisdom  | **Shared** (Instant consistency)          |

### Parallel Worker Checklist

When a Worker Agent is spawned in a new worktree, it must perform the following "Onboarding" sequence:

1.  **Sync Local Task**: `bd --sandbox show <issue_id>` to get specific task constraints.
2.  **Query Global Wisdom**: Search **OpenMemory** for project-wide standards and related documentation.
3.  **Review Reflections**: Read reflections left by previous agents on the components being modified.
4.  **Execute**: Perform work using Conventional Commits.
5.  **Post Reflection**: Save architectural decisions and hurdles to **OpenMemory**.
6.  **Final Sync**: Run `bd sync` inside the worktree before ending the session.

### ⚠️ Conflict Resolution

If two agents in different worktrees update the same `beads` issue, Git will handle the merge via the JSONL format. If a merge conflict occurs in `.beads/issues.jsonl`, run `bd sync` to trigger the intelligent merge driver.

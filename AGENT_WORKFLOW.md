# Agentic Workflow Guide

This project supports a multi-agent workflow where a **Master Agent** delegates tasks to specialized **Worker Agents**.

## How to Delegate

As the Master Agent, you can use the `dispatch.sh` tool to assign work.

### Syntax
`./tools/agents/dispatch.sh <role> "<instruction>" <output_file>`

### Available Roles & Models

We use a tiered model strategy to balance reasoning depth and speed.

| Role | Model Tier | Description |
|------|------------|-------------|
| **architect** | 🧠 **Thinking** (Pro) | High-level design, patterns, trade-off analysis. |
| **security** | 🧠 **Thinking** (Pro) | Deep vulnerability analysis and audit. |
| **coder** | ⚡ **Fast** (Flash) | Implementation, refactoring, efficiency. |
| **tester** | ⚡ **Fast** (Flash) | Unit tests, edge case generation. |

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
    *Tip: You can run this in a loop or a cron job.*

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

# Agent Delegation Workflow

## Overview

Temper uses specialized AI agents to parallelize work across different task types:
- **Nemotron** (`agent:nemotron`) - NVIDIA-powered worker agent for efficient execution
- **fast-build** (`agent:fast-build`) - Build/test agent for quick iterations
- **worker-bee** (`agent:worker-bee`) - General worker for parallel tasks

## Configured Agents

### Nemotron (Primary for TDD validation tasks)
```yaml
agent: nemotron
model: openrouter/nvidia/nemotron-3-nano-30b-a3b:free
description: Worker agent powered by NVIDIA Nemotron 3 Nano
prompt: |
  You are a worker agent powered by NVIDIA Nemotron 3 Nano. Focus on:
  - Executing tasks efficiently and independently
  - Following instructions precisely
  - Testing and validating your work
  - Moving fast without overthinking
```

### fast-build
```yaml
agent: fast-build
model: github-copilot/claude-sonnet-4.5
description: Fast agent for building, testing, and quick iterations
```

### worker-bee
```yaml
agent: worker-bee
model: openrouter/qwen/qwen3-235b-a22b-2507
description: Efficient worker agent for parallel task execution
```

## Delegation Workflow

### 1. Label Tasks for Delegation

```bash
# Label task for Nemotron
bd update temper-1mmr.2.2 --add-label agent:nemotron

# Label task for fast-build
bd update temper-abc --add-label agent:fast-build
```

### 2. Auto-Assign Tasks

```bash
# Assign all labeled tasks to their respective agents
python3 tools/agents/auto_assign.py
```

Output:
```
🤖 Auto-assigning tasks to agents...

📋 Checking tasks with label: agent:nemotron
   Found 8 task(s)
✅ Assigned temper-1mmr.2.2 to nemotron
✅ Assigned temper-1mmr.3.1 to nemotron
...

📋 Checking tasks with label: agent:fast-build
   Found 3 task(s)
✅ Assigned temper-abc to fast-build
...

📊 Summary: 11 task(s) assigned
```

### 3. Agent Works on Tasks

The agent picks up assigned tasks via:
- **beads ready queue**: `bd ready` shows tasks assigned to agent
- **Agent prompt**: Agent receives task context with ID and description
- **Independent execution**: Agent works without constant supervision

### 4. Agent Reports Completion

```bash
# Agent updates task status and adds notes
bd update temper-1mmr.2.2 --status done \
  --notes="Implemented wirelength.py with all 5 tests passing. Commit: abc123"
```

## TDD Delegation Pattern

For validation epics, tasks follow TDD pattern:

| Pattern | Task Example | Description |
|---------|---------------|-------------|
| RED (.1) | `temper-1mmr.2.1` | Write failing tests before implementation |
| GREEN (.2) | `temper-1mmr.2.2` | Implement code to make tests pass |

### Nemotron Instructions for RED Tasks
1. Review test expectations in description
2. Create test file with test functions
3. Ensure syntax is valid (no imports of non-existent modules)
4. Do NOT implement the module (that's the GREEN task)
5. Report completion with file path

### Nemotron Instructions for GREEN Tasks
1. Review failing tests from RED task
2. Create implementation file
3. Implement functions to make all tests pass
4. Run pytest to verify (should be GREEN)
5. Report completion with commit hash

## Current Agent Assignments

### Nemotron (8 TDD tasks delegated)

| Task ID | Title | Type |
|----------|--------|------|
| temper-1mmr.2.1 | TDD: Write wirelength comparison tests (RED) | Test writing |
| temper-1mmr.2.2 | TDD: Implement wirelength comparison (GREEN) | Implementation |
| temper-1mmr.3.1 | TDD: Write DRC compliance tests | Test writing |
| temper-1mmr.3.2 | TDD: Implement DRC compliance scoring | Implementation |
| temper-8ggu.2.1 | TDD: Write stress test runner tests | Test writing |
| temper-8ggu.2.2 | TDD: Implement stress test runner | Implementation |
| temper-j84e.1.1 | TDD: Write database schema tests | Test writing |
| temper-j84e.1.2 | TDD: Implement database schema | Implementation |

### fast-build (0 tasks)
Currently no tasks labeled `agent:fast-build`

### worker-bee (0 tasks)
Currently no tasks labeled `agent:worker-bee`

## Tracking Progress

### TDD Blueprint
`packages/temper-validation/TDD_BLUEPRINT.md` tracks:
- Module progress (tests written → implemented → refactored)
- Agent status for each module
- Next steps

### Beads Query

```bash
# See all tasks assigned to Nemotron
bd list --assignee nemotron --status open --json

# See all tasks with agent labels
bd list --label-any "agent:nemotron,agent:fast-build,agent:worker-bee" --json

# See ready work for Nemotron
bd ready --json | grep nemotron
```

## Adding New Agents

### 1. Configure in opencode.json

```json
{
  "agent": {
    "new-agent": {
      "description": "Agent description",
      "model": "model/provider",
      "prompt": "Agent prompt instructions"
    }
  }
}
```

### 2. Update auto_assign.py

```python
agent_labels = {
    "nemotron": "nemotron",
    "fast-build": "fast-build",
    "worker-bee": "worker-bee",
    "new-agent": "new-agent",  # Add new agent
}
```

### 3. Create Label Convention

Use `agent:<name>` for consistency:
- `agent:nemotron`
- `agent:fast-build`
- `agent:worker-bee`
- `agent:new-agent`

## Troubleshooting

### Task not picked up by agent

1. Check label is correct: `bd show temper-xxx --json | grep labels`
2. Verify agent is configured in opencode.json
3. Run auto-assign: `python3 tools/agents/auto_assign.py`

### Agent produces incorrect work

1. Review agent prompt in opencode.json
2. Add more specific instructions to task description
3. Consider using a different agent (e.g., fast-build for code reviews)

## References

- AGENTS.md - Main agent documentation
- opencode.json - Agent configurations
- packages/temper-validation/TDD_BLUEPRINT.md - TDD progress tracking

# GPBM Workflow: Gather-Plan-Build-Measure

A unified development loop integrating task tracking, semantic memory, requirements, and metrics for AI-assisted development.

## Quick Start

```bash
# Source the helpers
source tools/bd-worktree-helpers.sh

# 1. GATHER: Collect context for your goal
bd-gather "Add thermal shutdown to firmware" architect firmware

# 2. PLAN: Create epic with tasks (after reviewing context)
bd-plan /tmp/gather_context_*.md "Add thermal shutdown"

# 3. BUILD: Work on tasks in isolated worktrees
bd-work temper-xxx.1    # Creates worktree, claims task
# ... implement ...
bd-done "Implemented thermal shutdown"  # Auto-measures, closes, reminds about PR

# 4. MEASURE: (automatic in bd-done, or manual)
bd-measure temper-xxx   # Run metrics manually
```

## Architecture

```
HUMAN                    AGENTS                      SYSTEMS
──────                   ──────                      ───────

┌─────────┐         ┌──────────────┐          ┌───────────────┐
│ Approve │◀────────│   GATHER     │─────────▶│  Eco Memory   │
│ Scope   │         │  (architect) │          │  (semantic)   │
└────┬────┘         └──────┬───────┘          └───────────────┘
     │                     │                          ▲
     ▼                     ▼                          │
┌─────────┐         ┌──────────────┐          ┌───────────────┐
│ Review  │◀────────│    PLAN      │─────────▶│    Beads      │
│ Plan    │         │  (architect) │          │ (epic+tasks)  │
└────┬────┘         └──────┬───────┘          └───────────────┘
     │                     │                          │
     ▼                     ▼                          ▼
┌─────────┐         ┌──────────────┐          ┌───────────────┐
│ Monitor │◀────────│    BUILD     │─────────▶│ Git Worktrees │
│Progress │         │(coder/tester)│          │  (isolated)   │
└────┬────┘         └──────┬───────┘          └───────────────┘
     │                     │                          │
     ▼                     ▼                          ▼
┌─────────┐         ┌──────────────┐          ┌───────────────┐
│ Verify  │◀────────│   MEASURE    │─────────▶│   /metrics/   │
│ Accept  │         │   (tester)   │          │  (dashboard)  │
└─────────┘         └──────────────┘          └───────────────┘
```

## The Four Phases

### 1. GATHER Phase

Collects context from all knowledge sources before planning:

- **Eco Semantic Memory** - Past learnings from agents
- **Requirements** - REQ-* IDs from docs/requirements/
- **Beads Issues** - Related open/blocked issues
- **Metrics** - Current baselines from measurements.jsonl
- **Simulations** - Related verification results

**Command:**
```bash
bd-gather "goal description" [role] [domain]

# Examples:
bd-gather "Implement boundary loss function" architect placer
bd-gather "Fix PID oscillation issue" coder firmware
bd-gather "Add unit tests for state machine" tester firmware
```

**Outputs:**
- Context markdown file at `/tmp/gather_context_*.md`
- Human approval task (blocks planning until approved)

### 2. PLAN Phase

Creates structured work breakdown with dependencies:

- Epic issue with full context
- Subtasks with acceptance criteria
- Measurement targets per task
- Human approval gate

**Command:**
```bash
bd-plan <context-file> "epic title" [role]

# Example:
bd-plan /tmp/gather_context_1234.md "Add thermal shutdown protection"
```

**Creates:**
```
temper-xxx       (epic)
├── temper-xxx.0 (human approval - blocks all others)
├── temper-xxx.1 (first task)
├── temper-xxx.2 (second task)
└── ...
```

### 3. BUILD Phase

Execute tasks in isolated worktrees:

**Commands:**
```bash
# Start work (creates worktree + claims task)
bd-work temper-xxx.1

# Pause work (push WIP for multi-machine sync)
bd-pause

# Complete task (runs measurements, closes, pushes)
bd-done "Implemented feature"
bd-done --force "Quick fix"     # Skip measurements
bd-done --no-measure "WIP"      # Skip but confirm
```

**Worktree structure:**
```
~/worktrees/temper/
├── temper-xxx.1/     # Task 1 worktree
├── temper-xxx.2/     # Task 2 worktree
└── ...
```

### 4. MEASURE Phase

Automatically triggered in `bd-done`, or run manually:

**Command:**
```bash
bd-measure [task-id] [--json]

# Examples:
bd-measure                    # Current task from branch
bd-measure temper-xxx.1       # Specific task
bd-measure --json             # JSON output
```

**Available Metrics:**

| Metric | Domain | Description |
|--------|--------|-------------|
| `fw_test_coverage` | firmware | Test coverage percentage |
| `fw_test_pass_rate` | firmware | Percentage of tests passing |
| `fw_compile_warnings` | firmware | Number of compiler warnings |
| `fw_binary_size_kb` | firmware | Firmware binary size |
| `placer_drc_violations` | placer | KiCad DRC violation count |
| `placer_wirelength_mm` | placer | Total estimated wirelength |
| `placer_overlap_count` | placer | Component overlap count |
| `placer_test_pass_rate` | placer | pytest pass rate |
| `sim_convergence_rate` | simulation | SPICE simulation success |

**Measurement Targets in Issues:**

Add a YAML block to issue descriptions:
```yaml
measurement_targets:
  fw_test_coverage: ">=80"
  fw_compile_warnings: "==0"
```

## Eco User IDs

Multi-agent memory routing based on role and domain:

### Role-Based IDs
| Label | User ID | Purpose |
|-------|---------|---------|
| `agent:architect` | `temper-architect` | Design decisions, patterns |
| `agent:coder` | `temper-coder` | Implementation learnings |
| `agent:tester` | `temper-tester` | Test strategies, edge cases |
| `agent:human` | `temper-human` | Human feedback, corrections |

### Domain-Based IDs
| Label | User ID | Purpose |
|-------|---------|---------|
| `domain:firmware` | `temper-firmware` | ESP32 firmware knowledge |
| `domain:placer` | `temper-placer` | PCB placement optimizer |
| `domain:pcb` | `temper-pcb` | KiCad schematic/layout |

### Shared ID
| User ID | Purpose |
|---------|---------|
| `temper-shared` | Project-wide facts, standards |

**Eco CLI:**
```bash
# Search memories
python3 tools/gpbm/eco_client.py search "PID tuning" --role coder --domain firmware

# Post a reflection
python3 tools/gpbm/eco_client.py post "Learned that..." --role coder --domain firmware

# Post to shared
python3 tools/gpbm/eco_client.py post "Project standard..." --role architect --shared
```

## Requirements System

Requirements are tracked in markdown files with REQ-* IDs:

| File | ID Pattern | Domain |
|------|------------|--------|
| `REQUIREMENTS.md` | `REQ-SYS-*`, `REQ-PWR-*`, etc. | System/Hardware |
| `docs/requirements/FIRMWARE_REQUIREMENTS.md` | `REQ-FW-*` | Firmware |
| `docs/requirements/PLACER_REQUIREMENTS.md` | `REQ-PLACER-*` | PCB Placer |

**Link issues to requirements:**
```bash
bd update temper-xxx --label "req:REQ-FW-001"
```

**Search requirements:**
```bash
python3 tools/gpbm/requirements_parser.py --domain FW    # Filter by domain
python3 tools/gpbm/requirements_parser.py --status       # Coverage report
python3 tools/gpbm/requirements_parser.py --unlinked     # Unlinked requirements
python3 tools/gpbm/requirements_parser.py --json         # Export as JSON
```

## Metrics System

### Directory Structure
```
metrics/
├── METRICS.md           # Metric definitions and targets
├── measurements.jsonl   # Measurement log (append-only)
└── dashboards/          # Generated HTML dashboards
```

### Adding New Metrics

1. Define in `metrics/METRICS.md`
2. Implement collector in `tools/gpbm/measure.py`
3. Add to AVAILABLE_METRICS dict

### Measurement Log Format
```json
{"metric": "fw_test_coverage", "value": 85.5, "task": "temper-xxx", "timestamp": "2025-12-19T10:00:00Z", "passed": true, "target": ">=80"}
```

## CLI Reference

### Worktree Commands
| Command | Description |
|---------|-------------|
| `bd-work <task-id>` | Start work (create/resume worktree) |
| `bd-pause` | Pause (commit WIP, push) |
| `bd-done [reason]` | Complete (measure, close, push) |
| `bd-worktrees` | List active worktrees |
| `bd-cleanup-worktrees` | Remove merged worktrees |
| `bd-worktree-help` | Show help |

### GPBM Commands
| Command | Description |
|---------|-------------|
| `bd-gather "goal" [role] [domain]` | Collect context |
| `bd-plan <file> "title" [role]` | Create epic/tasks |
| `bd-measure [task] [--json]` | Run measurements |

### Flags
| Flag | For | Description |
|------|-----|-------------|
| `--force` | bd-done | Skip measurements entirely |
| `--no-measure` | bd-done | Skip measurements but confirm |
| `--json` | bd-measure | Output as JSON |

## Example Workflows

### Feature Development
```bash
# 1. Gather context
bd-gather "Add pan detection algorithm" architect firmware

# 2. Review and plan
cat /tmp/gather_context_*.md
bd-plan /tmp/gather_context_*.md "Pan detection algorithm"

# 3. Wait for human approval
bd show temper-xxx.0  # Approval task
# Human closes: bd close temper-xxx.0 --reason "Approved"

# 4. Work on tasks
bd-work temper-xxx.1
# ... implement ...
bd-done "Implemented impedance measurement"

bd-work temper-xxx.2
# ... implement ...
bd-done "Added confidence threshold"

# 5. Create PR
gh pr create --fill
```

### Bug Fix
```bash
# Quick fix workflow (skip full GPBM)
bd-work temper-bug-123
# ... fix bug ...
bd-done --force "Fixed null pointer dereference"
gh pr create --fill
```

### Multi-Machine Development
```bash
# Machine A
bd-work temper-xxx.1
# ... partial work ...
bd-pause  # Push WIP

# Machine B
bd-work temper-xxx.1  # Pulls latest
# ... continue work ...
bd-done "Completed feature"
```

## Configuration

### Environment Variables
```bash
# Worktree root (default: ~/worktrees)
export BD_WORKTREE_ROOT=/path/to/worktrees
```

### Shell Setup
Add to `~/.bashrc` or `~/.zshrc`:
```bash
source /path/to/temper/tools/bd-worktree-helpers.sh
```

## Troubleshooting

### "Task not found in bd"
```bash
# Check if task exists
bd show temper-xxx

# List open tasks
bd ready
```

### "Not in a task branch"
```bash
# Check current branch
git branch

# You must be in a worktree with a task branch
cd ~/worktrees/temper/temper-xxx
```

### "measure.py not found"
```bash
# Ensure you're in the temper repo
git rev-parse --show-toplevel

# Check the file exists
ls tools/gpbm/measure.py
```

### Measurement Failures
```bash
# Run manually to see errors
python3 tools/gpbm/measure.py --task temper-xxx

# Skip measurements for this task
bd-done --force "Skipping measurements"
```

### Worktree Conflicts
```bash
# Manual cleanup
git worktree remove ~/worktrees/temper/temper-xxx --force
git worktree prune

# Recreate
bd-work temper-xxx
```

## Integration with External Tools

### Beads Issue Tracker
All GPBM commands use `bd --sandbox` in worktrees to prevent daemon conflicts.

### GitHub CLI
```bash
# After bd-done, create PR
gh pr create --fill

# Check CI status
gh pr checks
```

### KiCad DRC
```bash
# Placer metrics run DRC
python3 tools/gpbm/measure.py --metric placer_drc_violations
```

## Related Documentation

- `AGENTS.md` - Agent instructions and bd usage
- `metrics/METRICS.md` - Metric definitions
- `docs/requirements/README.md` - Requirements system
- `tools/gpbm/` - GPBM Python modules

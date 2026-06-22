# Detailed Agent Instructions for temper Project

**For quick reference, see [AGENTS.md](AGENTS.md)**

This document contains operational instructions for working on the temper project with the bd workflow.

## Quick Start

```bash
# Verify setup
bd-validate-setup

# Find work
bd ready --json

# Start work
bd-work temper-xxx

# Complete session (MANDATORY)
bd-done "Done" && git push
```

## The temper Workflow

### 1. Before You Start

```bash
# Verify your setup is correct
bd-validate-setup
# If this fails, run: ./bd-setup.sh --quiet

# Get context for your task
python3 tools/get_context.py temper-xxx
```

### 2. Start Working

```bash
# Find available tasks
bd ready --json

# Claim and start work (creates worktree automatically)
bd-work temper-xxx

# You're now in ~/worktrees/temper/temper-xxx/
# All bd commands use --sandbox automatically
```

### 3. During Work

```bash
# Make changes
git add -A && git commit -m "feat: implement X"

# Commit = heartbeat for your claim
# Push to keep claim active across machines
git push

# Need to pause?
bd-pause  # Commits WIP and pushes

# Discover new work?
bd create "Found bug in X" \
  --description="..." \
  -t bug -p 1 \
  --deps discovered-from:temper-xxx \
  --json
```

### 4. Complete Work

```bash
# Run measurements (if task has them)
bd-measure  # or bd-done runs this automatically

# Close task
bd-done "Implemented feature X"

# This automatically:
# 1. Commits final changes
# 2. Pushes to remote
# 3. Closes issue in bd
# 4. Posts reflection to Eco
# 5. Creates PR if BEADS_AUTO_PR=true
```

### 5. End of Session (MANDATORY)

```bash
# Verify everything is pushed
git status  # Must show "up to date"

# If you made changes but didn't run bd-done:
bd-pause
git push

# Check reflection was posted
python3 tools/gpbm/reflect.py --task temper-xxx --reason "Done"
```

## Worktree Isolation

Each task gets its own directory:

```
~/worktrees/temper/
├── temper-xxx/  # Worktree for task xxx
├── temper-yyy/  # Worktree for task yyy
└── ...
```

**Benefits:**
- No context clobbering between tasks
- Work on multiple tasks simultaneously
- Seamless machine handoff with `bd-pause` + `git push`

**Rules:**
- Always use `bd-work` to start (not `git checkout`)
- Always use `bd --sandbox` for bd commands in worktrees
- Use `bd-pause` before ending session

## Multi-Agent Coordination

Multiple agents can work in parallel using git branches as atomic locks:

```bash
# See what others are working on
bd-claims

# Claim a task (atomic via git push)
bd-work temper-123

# If someone else claimed it first:
# - Active claim (<30min): wait or pick different work
# - Stale claim (>30min): bd-takeover temper-123
```

**Claim Rules:**
- Branch existence = claim
- First push wins (atomic)
- 30min inactivity = stale
- Hooks prevent push conflicts

## Protected Branch Mode

Issue metadata commits to `beads-sync` branch instead of `main`:

```bash
# Check current mode
bd config get sync.branch  # Should show "beads-sync"

# If not configured:
bd config set sync.branch beads-sync
bd daemon --start --auto-commit

# Merge metadata to main
bd sync --merge
```

## Common Tasks

### Find Work
```bash
# Unblocked issues
bd ready --json

# By priority
bd list --status open --priority 1 --json

# By type
bd list --issue-type bug --json
```

### Create Issues
```bash
# Simple issue
bd create "Fix auth bug" -t bug -p 1 --json

# With context
bd create "Add thermal protection" \
  --description="Users need protection against overheating..." \
  -t feature -p 1 \
  --json

# Subtask of epic
bd create "Implement X" \
  --description="..." \
  -t task \
  --parent temper-epic \
  --json
```

### Update Issues
```bash
# Claim
bd update temper-xxx --status in_progress --json

# Change priority
bd update temper-xxx --priority 2 --json

# Add labels
bd update temper-xxx --label domain:placer --json
```

### Close Issues
```bash
bd close temper-xxx --reason "Implemented feature X" --json
```

## ECO Memory Integration

**Before starting work:**
```bash
python3 tools/get_context.py temper-xxx
# Fetches issue + related memories
```

**After completing work:**
```bash
python3 tools/gpbm/reflect.py --task temper-xxx --reason "Done"
# Posts summary to long-term memory
```

**What goes in ECO:**
- Architectural decisions and rationale
- Technical learnings
- Project-wide facts and preferences

**What goes in bd:**
- Task-specific state
- Blockers and dependencies
- Implementation details

## Import Boundary Enforcement

Before pushing, verify import boundaries:

```bash
uv run python scripts/import_linter_gate.py
```

**If violations are reported:**
1. Check `.importlinter` for the boundary contract violated
2. **Option A**: Move the import to a permitted module (use public `__init__.py` exports)
3. **Option B**: Add an allowlist entry to `import-linter-allowlist.yaml` with justification + ticket reference

**Soft-launch**: Until 2026-07-06, violations are WARNING-only. After that date, violations block PR merge.

See `docs/plans/2026-06-22-014-feat-import-linter-boundary-enforcement-plan.md` for details.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Database not found" | Run `bd init --quiet` |
| "Hooks not installed" | Run `./bd-setup.sh --quiet` |
| "Branch claimed by other" | Pick different work or wait |
| Worktree corrupted | `git worktree remove <path> && git worktree prune` |
| Setup issues | `bd-validate-setup` to diagnose |

## Configuration Reference

```bash
# Required
export BEADS_AGENT_ID="your-name"

# Optional
export BD_WORKTREE_ROOT="$HOME/worktrees"  # Worktree location
export BEADS_STALE_MINUTES=30               # Stale claim threshold
export BEADS_AUTO_TAKEOVER=false            # Auto-takeover stale claims
export BEADS_AUTO_PR=false                  # Auto-create PR on bd-done
```

## Quick Commands Reference

| Command | Purpose |
|---------|---------|
| `bd ready` | Find unblocked work |
| `bd-work <id>` | Start work (creates worktree) |
| `bd-pause` | Commit+push WIP |
| `bd-done [msg]` | Complete task |
| `bd-claims` | See active claims |
| `bd-status` | Show workflow status |
| `bd-validate-setup` | Verify setup |

## Project Structure

```
temper/
├── firmware/           # ESP32-S3 firmware (C)
├── pcb/                # KiCad schematics
├── temper-placer/      # PCB placement optimizer (Python/JAX)
├── simulation/         # SPICE simulations
├── tools/              # Workflow scripts
│   ├── bd-worktree-helpers.sh  # Worktree commands
│   ├── bd-multiagent.sh        # Multi-agent coordination
│   └── gpbm/             # ECO memory tools
├── AGENTS.md            # Quick reference
└── AGENT_INSTRUCTIONS.md # This file
```

## For More Information

- **Quick reference**: [AGENTS.md](AGENTS.md)
- **bd CLI help**: `bd <command> --help`
- **Worktree help**: `bd-worktree-help`
- **Multi-agent help**: `bd-multiagent-help`

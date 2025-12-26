# Instructions for AI Agents

**Quick Reference:**
- `bd ready` → Find unblocked work
- `bd-work <id>` → Start work (creates worktree, claims issue)
- `bd-done` → Complete task
- `bd-validate-setup` → Verify your setup

## Setup (One-Time)

```bash
# 1. Run the unified setup (does everything)
./bd-setup.sh --quiet

# 2. Verify setup
bd-validate-setup

# 3. Check for work
bd ready --json
```

## Daily Workflow

### Start Working
```bash
# Find available work
bd ready --json

# Start work on a task (creates isolated worktree)
bd-work temper-xxx
```

### During Work
```bash
# Regular commits update your claim (heartbeat)
git add -A && git commit -m "feat: ..."
git push

# Pause for multi-machine sync
bd-pause

# Create linked issue for discoveries
bd create "Found bug in X" \
  --description="Details..." \
  -t bug -p 1 \
  --deps discovered-from:temper-xxx \
  --json
```

### Complete Work
```bash
# Run measurements and close task
bd-done "Implemented feature X"

# Or skip measurements
bd-done --no-measure "Quick fix"
```

## Session End (MANDATORY)

**Never end a session without completing these steps:**

```bash
# 1. Post reflection to Eco
python3 tools/gpbm/reflect.py --task temper-xxx --reason "Done"

# 2. Sync and push
bd sync
git push

# 3. Verify
git status  # Must show "up to date"
```

## Essential bd Commands

| Command | Description |
|---------|-------------|
| `bd ready --json` | Find unblocked issues |
| `bd list --status open --json` | List all open issues |
| `bd show <id> --json` | Show issue details |
| `bd create "Title" -p 1 -t task --json` | Create issue |
| `bd update <id> --status in_progress --json` | Claim issue |
| `bd close <id> --reason "Done" --json` | Close issue |
| `bd sync` | Force sync to remote |
| `bd blocked` | Show blocked issues |

## Multi-Agent Coordination

**Claim = Remote Branch**: Pushing a branch `temper-xxx` claims that issue.

```bash
# See what others are working on
bd-claims

# Check specific issue status
bd-claim-status temper-xxx

# Take over stale claim (>30min inactive)
bd-takeover temper-xxx
```

## Worktree Commands

| Command | Description |
|---------|-------------|
| `bd-work <id>` | Create/resume worktree for task |
| `bd-pause` | Commit WIP and push (sync) |
| `bd-done [--force]` | Complete, close, post reflection |
| `bd-worktrees` | List active worktrees |
| `bd-cleanup-worktrees` | Remove closed+merged worktrees |

## Configuration

**Quick setup check:**
```bash
bd-status          # Show current status
bd-validate-setup  # Validate setup
```

**Environment variables:**
```bash
export BEADS_AGENT_ID="your-name"        # Your identifier
export BD_WORKTREE_ROOT="$HOME/worktrees"  # Worktree location
export BEADS_AUTO_PR=true                # Auto-create PR on bd-done
export BEADS_AUTO_TAKEOVER=true          # Auto-takeover stale claims
```

## ECO Memory (Long-Term Context)

**Before starting work:**
```bash
python3 tools/get_context.py temper-xxx
```

**After completing work (mandatory):**
```bash
python3 tools/gpbm/reflect.py --task temper-xxx --reason "Done"
```

## Protected Branch Mode

This project uses beads protected branch mode for issue metadata:

```bash
# Metadata commits go to: beads-sync branch
bd sync --merge  # Merge to main when ready
```

## Common Patterns

### Finding Work
```bash
# By priority
bd list --status open --priority 1 --json

# By label
bd list --label-any urgent,critical --json

# By type
bd list --issue-type bug --json
```

### Creating Issues
```bash
# With discovered-from dependency
bd create "Fix bug in X" \
  --description="Found while working on temper-yyy" \
  -t bug -p 1 \
  --deps discovered-from:temper-yyy \
  --json

# As child of epic
bd create "Subtask" \
  --description="..." \
  -t task \
  --parent temper-epic \
  --json
```

### Managing Dependencies
```bash
# X blocks Y
bd dep add Y X

# Check blocking
bd blocked
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Database not found" | Run `bd init --quiet` |
| "Hooks not installed" | Run `./bd-setup.sh --quiet` |
| "Branch claimed by other agent" | Pick different work or wait |
| "Push blocked" | Branch is claimed by another agent |
| Worktree corrupted | `git worktree remove <path> && git worktree prune` |

## Project Context

**This is the Temper induction cooker project:**
- **Firmware**: ESP32-S3 with 8-state machine
- **PCB**: KiCad design with temper-placer optimizer
- **Language**: C (firmware), Python/JAX (placer)

**Key areas:**
- `firmware/` - ESP32-S3 control code
- `temper-placer/` - JAX-based PCB placement optimizer
- `pcb/` - KiCad schematics

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────┐
│  START:   bd ready → bd-work <id>                           │
│  WORK:    git add/commit/push (updates claim)               │
│  DISCOVER: bd create --deps discovered-from:<parent>        │
│  END:     bd-done → bd sync → git push → reflect           │
└─────────────────────────────────────────────────────────────┘
```

**See also:**
- `AGENT_INSTRUCTIONS.md` - Detailed development guidelines
- `bd-worktree-help` - Worktree command help
- `bd-multiagent-help` - Multi-agent coordination help

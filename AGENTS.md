# Instructions for AI Agents Working on Beads

> **📖 For detailed development instructions**, see [AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md)
> 
> This file provides a quick overview and reference. For in-depth operational details (development, testing, releases, git workflow), consult the detailed instructions.

## Project Overview

This is **beads** (command: `bd`), an issue tracker designed for AI-supervised coding workflows. We dogfood our own tool!

> **🤖 Using GitHub Copilot?** See [.github/copilot-instructions.md](.github/copilot-instructions.md) for a concise, Copilot-optimized version of these instructions that GitHub Copilot will automatically load.

## 🧠 The Cognitive Stack: Beads + ECO

To maintain context across different tasks and parallel sessions, we use two complementary memory systems:

1.  **Beads (Project Memory):** Use `bd` for task tracking, blockers, and feature-specific state. This is stored in Git.
2.  **ECO (Global Knowledge):** Use ECO for long-term "facts" and project-wide documentation. This persists across all branches and worktrees. The ECO memory server runs remotely at **https://eco.bennetleff.workers.dev**.

### 🔄 ECO Integration Workflow

**1. Context Retrieval (Session Start)**
Before starting any task, you MUST query ECO to gather relevant context.
**Recommended:** Use the unified context tool:
```bash
python3 tools/get_context.py <ISSUE_ID>
```

Alternatively, use the raw API:
- Search for the issue ID: `POST https://eco.bennetleff.workers.dev/memories/search` with body `{"query": "<ISSUE_ID>", "userId": "temper-agent"}`
- Search for related documentation: `POST https://eco.bennetleff.workers.dev/memories/search` with body `{"query": "<TOPIC>", "userId": "temper-agent"}`

**2. Reflection (Session Wrap-up)**
After completing a task or ending a session, you MUST post a reflection:
- Summarize what you learned, architectural decisions made, and hurdles encountered.
- Use the memory endpoint: `POST https://eco.bennetleff.workers.dev/memories` with body `{"content": "REFLECTION: <summary>", "userId": "temper-agent", "tags": ["reflection", "architecture"]}`
- This ensures the "agent hive mind" remains updated across sessions.

## 🆕 What's New?

**New to bd or upgrading?** Run `bd info --whats-new` to see agent-relevant changes from recent versions:

```bash
bd info --whats-new          # Human-readable output
bd info --whats-new --json   # Machine-readable output
```

This shows the last 3 versions with workflow-impacting changes, avoiding the need to re-read all documentation. Examples:

- New commands and flags that improve agent workflows
- Breaking changes that require workflow updates
- Performance improvements and bug fixes
- Integration features (MCP, Agent Mail, git hooks)

**Why this matters:** bd releases weekly with major versions. This command helps you quickly understand what changed without parsing the full CHANGELOG.

### 🔄 After Upgrading bd

When bd is upgraded to a new version, follow this workflow:

```bash
# 1. Check what changed
bd info --whats-new

# 2. Update git hooks to match new bd version
bd hooks install

# 3. Regenerate BD_GUIDE.md if it exists (optional but recommended)
bd onboard --output .beads/BD_GUIDE.md

# 4. Check for any outdated hooks (optional)
bd info  # Shows warnings if hooks are outdated
```

**Why update hooks?** Git hooks (pre-commit, post-merge, pre-push) are versioned with bd. Outdated hooks may miss new auto-sync features or bug fixes. Running `bd hooks install` ensures hooks match your bd version.

**About BD_GUIDE.md:** This is an optional auto-generated file that separates bd-specific instructions from project-specific ones. If your project uses this file (in `.beads/BD_GUIDE.md`), regenerate it after upgrades to get the latest bd documentation. The file is version-stamped and should never be manually edited.

**Related:** See GitHub Discussion #239 for background on agent upgrade workflows.

## Human Setup vs Agent Usage

**IMPORTANT:** If you need to initialize bd, use the `--quiet` flag:

```bash
bd init --quiet  # Non-interactive, auto-installs git hooks, no prompts
```

**Why `--quiet`?** Regular `bd init` has interactive prompts (git hooks, merge driver) that confuse agents. The `--quiet` flag makes it fully non-interactive:

- Automatically installs git hooks
- Automatically configures git merge driver for intelligent JSONL merging
- No prompts for user input
- Safe for agent-driven repo setup

**If the human already initialized:** Just use bd normally with `bd create`, `bd ready`, `bd update`, `bd close`, etc.

**If you see "database not found":** Run `bd init --quiet` yourself, or ask the human to run `bd init`.

## Issue Tracking

We use bd (beads) for issue tracking instead of Markdown TODOs or external tools.

### CLI + Hooks (Recommended)

**RECOMMENDED**: Use the `bd` CLI with hooks for the best experience. This approach:

- **Minimizes context usage** - Only injects ~1-2k tokens via `bd prime` vs MCP tool schemas
- **Reduces compute cost** - Less tokens = less processing per request
- **Lower latency** - Direct CLI calls are faster than MCP protocol overhead
- **More sustainable** - Every token has compute/energy cost; lean prompts are greener
- **Universal** - Works with any AI assistant, not just MCP-compatible ones

**Setup (one-time):**

```bash
# Install bd CLI (see docs/INSTALLING.md)
brew install bd  # or other methods

# Initialize in your project
bd init --quiet

# Install hooks for automatic context injection
bd hooks install
```

**How it works:**

1. **SessionStart hook** runs `bd prime` automatically when Claude Code starts
2. `bd prime` injects a compact workflow reference (~1-2k tokens)
3. You use `bd` CLI commands directly (no MCP layer needed)
4. Git hooks auto-sync the database with JSONL

**Why context minimization matters:**

Even with 200k+ context windows, minimizing context is important:

- **Compute cost scales with tokens** - More context = more expensive inference
- **Latency increases with context** - Larger prompts take longer to process
- **Energy consumption** - Every token has environmental impact
- **Attention quality** - Models attend better to smaller, focused contexts

A 50k token MCP schema consumes the same compute whether you use those tools or not. The CLI approach keeps your context lean and focused.

### CLI Quick Reference

**Essential commands for AI agents:**

```bash
# Find work
bd ready --json                                    # Unblocked issues
bd stale --days 30 --json                          # Forgotten issues

# Create and manage issues
bd create "Issue title" --description="Detailed context about the issue" -t bug|feature|task -p 0-4 --json
bd create "Found bug" --description="What the bug is and how it was discovered" -p 1 --deps discovered-from:<parent-id> --json
bd update <id> --status in_progress --json
bd close <id> --reason "Done" --json

# Search and filter
bd list --status open --priority 1 --json
bd list --label-any urgent,critical --json
bd show <id> --json

# Sync (CRITICAL at end of session!)
bd sync  # Force immediate export/commit/push
```

**For comprehensive CLI documentation**, see [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md).

### MCP Server (Alternative)

For Claude Desktop, Sourcegraph Amp, or other MCP-only environments where CLI access is limited, use the MCP server:

```bash
pip install beads-mcp
```

Add to MCP config:

```json
{
  "beads": {
    "command": "beads-mcp",
    "args": []
  }
}
```

**When to use MCP:**

- ✅ Claude Desktop (no shell access)
- ✅ MCP-only environments
- ✅ Environments where CLI is unavailable

**When to prefer CLI + hooks:**

- ✅ Claude Code, Cursor, Windsurf, or any environment with shell access
- ✅ When context efficiency matters (most cases)
- ✅ Multi-editor workflows (CLI is universal)

See `integrations/beads-mcp/README.md` for MCP documentation. For multi-repo MCP patterns, see [docs/MULTI_REPO_AGENTS.md](docs/MULTI_REPO_AGENTS.md).

### Import Configuration

bd provides configuration for handling edge cases during import, especially when dealing with hierarchical issues and deleted parents:

```bash
# Configure orphan handling for imports
bd config set import.orphan_handling "allow"      # Default: import orphans without validation
bd config set import.orphan_handling "resurrect"  # Auto-resurrect deleted parents as tombstones
bd config set import.orphan_handling "skip"       # Skip orphaned children with warning
bd config set import.orphan_handling "strict"     # Fail if parent is missing
```

**Modes explained:**

- **`allow` (default)** - Import orphaned children without parent validation. Most permissive, ensures no data loss even if hierarchy is temporarily broken.
- **`resurrect`** - Search JSONL history for deleted parents and recreate them as tombstones (Status=Closed, Priority=4). Preserves hierarchy with minimal data.
- **`skip`** - Skip orphaned children with a warning. Partial import succeeds but some issues are excluded.
- **`strict`** - Fail import immediately if a child's parent is missing. Use when database integrity is critical.

**When to use each mode:**

- Use `allow` (default) for daily imports and auto-sync - ensures no data loss
- Use `resurrect` when importing from another database that had parent deletions
- Use `strict` only for controlled imports where you need to guarantee parent existence
- Use `skip` rarely - only when you want to selectively import a subset

**Override per command:**

```bash
bd import -i issues.jsonl --orphan-handling resurrect  # One-time override
bd sync  # Uses import.orphan_handling config setting
```

See [docs/CONFIG.md](docs/CONFIG.md) for complete configuration documentation.

### Managing Daemons

bd runs a background daemon per workspace for auto-sync and RPC operations:

```bash
bd daemons list --json          # List all running daemons
bd daemons health --json        # Check for version mismatches
bd daemons logs . -n 100        # View daemon logs
bd daemons killall --json       # Restart all daemons
```

**After upgrading bd**: Run `bd daemons killall` to restart all daemons with new version.

### Event-Driven Daemon Mode (Experimental)

**NEW in v0.16+**: Event-driven mode replaces 5-second polling with instant reactivity (<500ms latency, 60% less CPU).

**Enable globally:**

```bash
export BEADS_DAEMON_MODE=events
bd daemons killall  # Restart daemons to apply
```

**For configuration, troubleshooting, and complete daemon management**, see [docs/DAEMON.md](docs/DAEMON.md).

### Web Interface (Monitor)

bd includes a built-in web interface for human visualization:

```bash
bd monitor                  # Start on localhost:8080
bd monitor --port 3000      # Custom port
```

**AI agents**: Continue using CLI with `--json` flags. The monitor is for human supervision only.

### Workflow

1. **Check for ready work**: Run `bd ready` to see what's unblocked (or `bd stale` to find forgotten issues)
2. **Claim your task**: `bd update <id> --status in_progress`
3. **Work on it**: Implement, test, document
4. **Discover new work**: If you find bugs or TODOs, create issues:
   - Old way (two commands): `bd create "Found bug in auth" --description="Details about the bug" -t bug -p 1 --json` then `bd dep add <new-id> <current-id> --type discovered-from`
   - New way (one command): `bd create "Found bug in auth" --description="Login fails with 500 when password has special chars" -t bug -p 1 --deps discovered-from:<current-id> --json`
5. **Complete**: `bd close <id> --reason "Implemented"`
6. **Sync at end of session**: `bd sync` (see "Agent Session Workflow" below)

### Git Worktree Workflow for Task Isolation

**This project uses git worktrees to isolate work on bd tasks.** Each task gets its own worktree directory, enabling:

- **Concurrent work**: Multiple agents/sessions working on different tasks simultaneously
- **Clean isolation**: Each task starts with a fresh working directory
- **Multi-machine sync**: Seamless hand-off between machines via git push/pull
- **Easy cleanup**: Remove worktrees without affecting other work

#### Directory Structure

```
~/worktrees/
└── temper/
    ├── bd-abc/      # worktree for task bd-abc
    ├── bd-xyz/      # worktree for task bd-xyz
    └── ...
```

**Configuration**: Set `BD_WORKTREE_ROOT` to change the worktree location (default: `~/worktrees`):

```bash
export BD_WORKTREE_ROOT=/path/to/your/worktrees
```

#### Setup (One-Time)

Source the helper functions in your shell:

```bash
# Add to ~/.bashrc or ~/.zshrc for persistence
source ~/Documents/temper/tools/bd-worktree-helpers.sh
```

Or source manually each session:

```bash
source tools/bd-worktree-helpers.sh
```

#### Helper Functions

| Command                | Description                                             |
| ---------------------- | ------------------------------------------------------- |
| `bd-work <task-id>`    | Start work on a task (creates/resumes worktree)         |
| `bd-pause`             | Pause work (commit WIP and push for multi-machine sync) |
| `bd-done [reason]`     | Complete task (close in bd, remind about PR)            |
| `bd-cleanup-worktrees` | Remove worktrees for closed+merged tasks                |
| `bd-worktrees`         | List active worktrees with status                       |
| `bd-worktree-help`     | Show detailed help                                      |

#### Workflow

**Starting work on a task:**

```bash
# Find ready work
bd ready --json

# Start work (creates worktree, claims task, creates branch)
bd-work bd-123

# Now you're in ~/worktrees/temper/bd-123 working on isolated branch
```

**What `bd-work` does:**

1. Creates `~/worktrees/temper/<task-id>` directory
2. Creates/checks out branch `<task-id>`
3. If branch exists remotely, pulls latest changes
4. If new task, creates branch from `main` and pushes immediately
5. Runs `bd update <task-id> --status in_progress`

**During work:**

```bash
# Work normally - make changes, commit, test
git add -A
git commit -m "feat: implement feature X"

# Run tests, iterate, etc.
```

**Pausing work (switching machines or ending session):**

```bash
# Commit and push WIP
bd-pause

# This commits any changes with "WIP: progress on <task-id>"
# Pushes to remote for multi-machine sync
# Runs bd sync to sync issue state
```

**Resuming work (same or different machine):**

```bash
# On any machine with the repo
bd-work bd-123

# Automatically resumes from remote branch
# You're now working with latest changes
```

**Completing a task:**

```bash
# Final push and close task
bd-done "Implemented feature X"

# This:
# 1. Commits final changes
# 2. Pushes to remote
# 3. Closes task in bd
# 4. Reminds you to create PR

# Create PR
gh pr create --fill

# Worktree remains until PR merged (for review iterations)
```

**Periodic cleanup:**

```bash
# Remove worktrees for closed tasks with merged PRs
bd-cleanup-worktrees

# This only removes worktrees where:
# - Task is closed in bd
# - Branch is merged to main
# - PR is complete
```

#### Multi-Machine Workflow

**Machine A:**

```bash
bd-work bd-123
# ... make changes ...
bd-pause           # Push WIP
```

**Machine B:**

```bash
bd-work bd-123     # Automatically pulls latest WIP
# ... continue work ...
bd-done            # Complete and close
```

**Machine A (later):**

```bash
cd ~/worktrees/temper/bd-123
git pull           # Get final changes if needed
```

#### Rules for Agents

- **ALWAYS use worktrees** for bd tasks - never work directly in main repo on task branches
- **ALWAYS use `bd --sandbox`** in worktrees - disables daemon and auto-sync to prevent conflicts
- **ALWAYS run `bd-pause`** before ending a session or switching machines
- **NEVER delete worktrees** immediately after closing task - wait for PR merge
- **Use `bd-worktrees`** to see what's currently active
- **Run `bd-cleanup-worktrees`** periodically (e.g., weekly) to remove old worktrees

#### Sandbox Mode for Parallel Agents

When running multiple agents in worktrees, use **sandbox mode** to prevent sync conflicts:

```bash
# In worktrees, always use --sandbox flag
bd --sandbox list
bd --sandbox show temper-xxx
bd --sandbox update temper-xxx --status in_progress

# Read-only agents can use --readonly instead
bd --readonly list
bd --readonly show temper-xxx
```

**Why sandbox mode?**

- Disables daemon RPC communication
- Disables auto-sync (no file watcher loops)
- Prevents multiple agents from fighting over the same database
- Avoids "uncommitted local changes" warning spam

**When to use each mode:**

- `--sandbox` - For worker agents that may create/update issues
- `--readonly` - For agents that only read issues (even faster)
- No flag - Only in the main repo with a single agent

#### Troubleshooting

**Worktree already exists but corrupted:**

```bash
# Manual cleanup
git worktree remove ~/worktrees/temper/bd-123 --force
git worktree prune
bd-work bd-123  # Recreate
```

**Branch conflicts when resuming:**

```bash
cd ~/worktrees/temper/bd-123
git pull --rebase  # Rebase your changes on remote
# Resolve conflicts if any
git push
```

**List all worktrees (git native):**

```bash
git worktree list
```

#### Benefits for AI Agents

1. **No context switching**: Each task is in its own directory with its own state
2. **Parallel execution**: Work on multiple tasks without interference
3. **Clean state**: Start each task with clean working tree from main
4. **Easy hand-off**: Push WIP, resume anywhere
5. **Safe experimentation**: Worktree isolation means breaking one task doesn't affect others

### IMPORTANT: Always Include Issue Descriptions

**Issues without descriptions lack context for future work.** When creating issues, always include a meaningful description with:

- **Why** the issue exists (problem statement or need)
- **What** needs to be done (scope and approach)
- **How** you discovered it (if applicable during work)

**Good examples:**

```bash
# Bug discovered during work
bd create "Fix auth bug in login handler" \
  --description="Login fails with 500 error when password contains special characters like quotes. Found while testing GH#123 feature. Stack trace shows unescaped SQL in auth/login.go:45." \
  -t bug -p 1 --deps discovered-from:bd-abc --json

# Feature request
bd create "Add password reset flow" \
  --description="Users need ability to reset forgotten passwords via email. Should follow OAuth best practices and include rate limiting to prevent abuse." \
  -t feature -p 2 --json

# Technical debt
bd create "Refactor auth package for testability" \
  --description="Current auth code has tight DB coupling making unit tests difficult. Need to extract interfaces and add dependency injection. Blocks writing tests for bd-xyz." \
  -t task -p 3 --json
```

**Bad examples (missing context):**

```bash
bd create "Fix auth bug" -t bug -p 1 --json  # What bug? Where? Why?
bd create "Add feature" -t feature --json     # What feature? Why needed?
bd create "Refactor code" -t task --json      # What code? Why refactor?
```

### Optional: Agent Mail for Multi-Agent Coordination

**⚠️ NOT CURRENTLY CONFIGURED** - The mcp-agent-mail server is not set up for this project. Do not attempt to use mcp-agent-mail tools.

**For multi-agent workflows only** - if multiple AI agents work on the same repository simultaneously, consider using Agent Mail for real-time coordination:

**With Agent Mail enabled:**

```bash
# Configure environment (one-time per session)
export BEADS_AGENT_MAIL_URL=http://127.0.0.1:8765
export BEADS_AGENT_NAME=assistant-alpha
export BEADS_PROJECT_ID=my-project

# Workflow (identical commands)
bd ready                                    # Shows available work
bd update bd-42 --status in_progress       # Reserves issue instantly (<100ms)
# ... work on issue ...
bd close bd-42 "Done"                       # Releases reservation automatically
```

**Without Agent Mail (git-only mode):**

```bash
# No environment variables needed
bd ready                                    # Shows available work
bd update bd-42 --status in_progress       # Updates via git sync (2-5s latency)
# ... work on issue ...
bd close bd-42 "Done"                       # Updates via git sync
```

**Key differences:**

- **Latency**: <100ms (Agent Mail) vs 2-5s (git-only)
- **Collision prevention**: Instant reservation (Agent Mail) vs eventual consistency (git)
- **Setup**: Requires server + env vars (Agent Mail) vs zero config (git-only)

**When to use Agent Mail:**

- ✅ Multiple agents working concurrently
- ✅ Frequent status updates (high collision risk)
- ✅ Real-time coordination needed

**When to skip:**

- ✅ Single agent workflows
- ✅ Infrequent updates (low collision risk)
- ✅ Simplicity preferred over latency

See [docs/AGENT_MAIL_QUICKSTART.md](docs/AGENT_MAIL_QUICKSTART.md) for 5-minute setup, or [docs/AGENT_MAIL.md](docs/AGENT_MAIL.md) for complete documentation. Example code in [examples/python-agent/AGENT_MAIL_EXAMPLE.md](examples/python-agent/AGENT_MAIL_EXAMPLE.md).

### Deletion Tracking

When issues are deleted (via `bd delete` or `bd cleanup`), they are recorded in `.beads/deletions.jsonl`. This manifest:

- **Propagates deletions across clones**: When you pull, deleted issues from other clones are removed from your local database
- **Provides audit trail**: See what was deleted, when, and by whom with `bd deleted`
- **Auto-prunes**: Old records are automatically cleaned up during `bd sync` (configurable retention)

**Commands:**

```bash
bd delete bd-42                # Delete issue (records to manifest)
bd cleanup -f                  # Delete closed issues (records all to manifest)
bd deleted                     # Show recent deletions (last 7 days)
bd deleted --since=30d         # Show deletions in last 30 days
bd deleted bd-xxx              # Show deletion details for specific issue
bd deleted --json              # Machine-readable output
```

**How it works:**

1. `bd delete` or `bd cleanup` appends deletion records to `deletions.jsonl`
2. The file is committed and pushed via `bd sync`
3. On other clones, `bd sync` imports the deletions and removes those issues from local DB
4. Git history fallback handles edge cases (pruned records, shallow clones)

### Issue Types

- `bug` - Something broken that needs fixing
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature composed of multiple issues (supports hierarchical children)
- `chore` - Maintenance work (dependencies, tooling)

**Hierarchical children:** Epics can have child issues with dotted IDs (e.g., `bd-a3f8e9.1`, `bd-a3f8e9.2`). Children are auto-numbered sequentially. Up to 3 levels of nesting supported. The parent hash ensures unique namespace - no coordination needed between agents working on different epics.

### Priorities

- `0` - Critical (security, data loss, broken builds)
- `1` - High (major features, important bugs)
- `2` - Medium (default, nice-to-have features, minor bugs)
- `3` - Low (polish, optimization)
- `4` - Backlog (future ideas)

### Dependency Types

- `blocks` - Hard dependency (issue X blocks issue Y)
- `related` - Soft relationship (issues are connected)
- `parent-child` - Epic/subtask relationship
- `discovered-from` - Track issues discovered during work (automatically inherits parent's `source_repo`)

Only `blocks` dependencies affect the ready work queue. 

**Note:** When creating an issue with a `discovered-from` dependency, the new issue automatically inherits the parent's `source_repo` field. This ensures discovered work stays in the same repository as the parent task.

### Planning Work with Dependencies

When breaking down large features into tasks, use **beads dependencies** to sequence work - NOT phases or numbered steps.

**⚠️ COGNITIVE TRAP: Temporal Language Inverts Dependencies**

Words like "Phase 1", "Step 1", "first", "before" trigger temporal reasoning that **flips dependency direction**. Your brain thinks:

- "Phase 1 comes before Phase 2" → "Phase 1 blocks Phase 2" → `bd dep add phase1 phase2`

But that's **backwards**! The correct mental model:

- "Phase 2 **depends on** Phase 1" → `bd dep add phase2 phase1`

**Solution: Use requirement language, not temporal language**

Instead of phases, name tasks by what they ARE, and think about what they NEED:

```bash
# ❌ WRONG - temporal thinking leads to inverted deps
bd create "Phase 1: Create buffer layout" ...
bd create "Phase 2: Add message rendering" ...
bd dep add phase1 phase2  # WRONG! Says phase1 depends on phase2

# ✅ RIGHT - requirement thinking
bd create "Create buffer layout" ...
bd create "Add message rendering" ...
bd dep add msg-rendering buffer-layout  # msg-rendering NEEDS buffer-layout
```

**Verification**: After adding deps, run `bd blocked` - tasks should be blocked by their prerequisites, not their dependents.

**Example breakdown** (for a multi-part feature):

```bash
# Create tasks named by what they do, not what order they're in
bd create "Implement conversation region" -t task -p 1
bd create "Add header-line status display" -t task -p 1
bd create "Render tool calls inline" -t task -p 2
bd create "Add streaming content support" -t task -p 2

# Set up dependencies: X depends on Y means "X needs Y first"
bd dep add header-line conversation-region    # header needs region
bd dep add tool-calls conversation-region     # tools need region
bd dep add streaming tool-calls               # streaming needs tools

# Verify with bd blocked - should show sensible blocking
bd blocked
```

### Duplicate Detection & Merging

AI agents should proactively detect and merge duplicate issues to keep the database clean:

**Automated duplicate detection:**

```bash
# Find all content duplicates in the database
bd duplicates

# Automatically merge all duplicates
bd duplicates --auto-merge

# Preview what would be merged
bd duplicates --dry-run

# During import
bd import -i issues.jsonl --dedupe-after
```

**Detection strategies:**

1. **Before creating new issues**: Search for similar existing issues

   ```bash
   bd list --json | grep -i "authentication"
bd show bd-41 bd-42 --json  # Compare candidates
   ```

2. **Periodic duplicate scans**: Review issues by type or priority

   ```bash
   bd list --status open --priority 1 --json  # High-priority issues
   bd list --issue-type bug --json             # All bugs
   ```

3. **During work discovery**: Check for duplicates when filing discovered-from issues
   ```bash
   # Before: bd create "Fix auth bug" --description="Details..." --deps discovered-from:bd-100
   # First: bd list --json | grep -i "auth bug"
   # Then decide: create new or link to existing
   ```

**Merge workflow:**

```bash
# Step 1: Identify duplicates (bd-42 and bd-43 duplicate bd-41)
bd show bd-41 bd-42 bd-43 --json

# Step 2: Preview merge to verify
bd merge bd-42 bd-43 --into bd-41 --dry-run

# Step 3: Execute merge
bd merge bd-42 bd-43 --into bd-41 --json

# Step 4: Verify result
bd dep tree bd-41  # Check unified dependency tree
bd show bd-41 --json  # Verify merged content
```

**What gets merged:**

- ✅ All dependencies from source → target
- ✅ Text references updated across ALL issues (descriptions, notes, design, acceptance criteria)
- ✅ Source issues closed with "Merged into bd-X" reason
- ❌ Source issue content NOT copied (target keeps its original content)

**Important notes:**

- Merge preserves target issue completely; only dependencies/references migrate
- If source issues have valuable content, manually copy it to target BEFORE merging
- Cannot merge in daemon mode yet (bd-190); use `--no-daemon` flag
- Operation cannot be undone (but git history preserves the original)

**Best practices:**

- Merge early to prevent dependency fragmentation
- Choose the oldest or most complete issue as merge target
- Add labels like `duplicate` to source issues before merging (for tracking)
- File a discovered-from issue if you found duplicates during work:
  ```bash
  bd create "Found duplicates during bd-X" \
    --description="Issues bd-A, bd-B, and bd-C are duplicates and need merging" \
    -p 2 --deps discovered-from:bd-X --json
  ```

## Agentic Workflows & Delegation

This project uses a tiered multi-agent system to optimize for reasoning depth and execution speed.

### Tiered Model Strategy

| Role          | Model Tier            | Responsibility                                            |
| ------------- | --------------------- | --------------------------------------------------------- |
| **architect** | 🧠 **Thinking** (Pro) | High-level design, pattern selection, trade-off analysis. |
| **security**  | 🧠 **Thinking** (Pro) | Deep vulnerability analysis, security audits, paranoia.   |
| **coder**     | ⚡ **Fast** (Flash)   | Feature implementation, refactoring, code efficiency.     |
| **tester**    | ⚡ **Fast** (Flash)   | Unit test generation, edge case coverage, QA.             |

### How to Delegate Tasks

You can delegate work to specialized agents using **Labels** in the `bd` issue tracker.

1.  **Label an Issue**: Add a label like `agent:coder` or `agent:security` to an open issue.
    ```bash
    bd update temper-123 --label agent:security
    ```
2.  **Trigger Automation**: Run the auto-assign script to scan and dispatch.
    ```bash
    python3 tools/agents/auto_assign.py
    ```
3.  **Manual Assignment**: Use the assignment tool for direct control.
    ```bash
    python3 tools/agents/assign.py <issue_id> <role>
    ```

### Output & Implementation

Agents save their work to `agent_outputs/<issue_id>_<role>_resolution.md`. The Master Agent (you) should review this output and implement/verify the changes.

## Development Guidelines

> **📋 For complete development instructions**, see [AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md)

**Quick reference:**

- **Go version**: 1.21+
- **Testing**: Use `BEADS_DB=/tmp/test.db` to avoid polluting production database
- **Before committing**: Run tests (`go test -short ./...`) and linter (`golangci-lint run ./...`)
- **End of session**: Always run `bd sync` to flush/commit/push changes
- **Git hooks**: Run `bd hooks install` to ensure DB ↔ JSONL consistency

See [AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md) for detailed workflows, testing patterns, and operational procedures.

### Conventional Commits

**IMPORTANT**: Use [Conventional Commits](https://www.conventionalcommits.org/) format for ALL git commits in this project.

**Format:**

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

**Types:**

- `feat`: New feature or functionality
- `fix`: Bug fix
- `docs`: Documentation changes only
- `style`: Code style changes (formatting, semicolons, etc.)
- `refactor`: Code changes that neither fix bugs nor add features
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `build`: Build system or dependency changes
- `ci`: CI/CD configuration changes
- `chore`: Maintenance tasks, tooling, etc.

**Scope** (optional but recommended):

- Use the module or component name (e.g., `firmware`, `pcb`, `placer`, `hal`, `safety`)
- For temper-placer: `core`, `io`, `geometry`, `losses`, `optimizer`, `viz`, `cli`

**Examples:**

```bash
# Feature
git commit -m "feat(placer): add Gumbel-Softmax rotation sampling"

# Bug fix
git commit -m "fix(hal): correct ADC channel mapping for temperature sensor"

# Tests
git commit -m "test(core): add unit tests for PlacementState"

# Documentation
git commit -m "docs: update AGENTS.md with conventional commits guide"

# Refactoring
git commit -m "refactor(safety): extract interlock logic into separate module"

# Build/dependencies
git commit -m "build(placer): add JAX and optax dependencies"

# Breaking change (add ! after type or BREAKING CHANGE in footer)
git commit -m "feat(api)!: change placement output format"
```

**For `bd sync` auto-commits:**
The `bd sync` command generates automatic commits for issue tracking changes. These are acceptable as-is since they track issue state, not code changes.

**Why Conventional Commits?**

- Enables automatic changelog generation
- Makes git history scannable and searchable
- Helps with semantic versioning decisions
- Provides clear context for code review

---

## Temper Project Overview

This repository contains the **Temper induction cooker** - a high-power induction heating system with:

- Half-bridge topology with IGBTs (IKW40N120H3)
- ESP32-S3 MCU for control (state machine-driven firmware)
- Resonant tank for induction heating
- Comprehensive safety interlocks and thermal management
- JAX-based PCB placement optimizer (temper-placer)

### Repository Structure

```
temper/
├── firmware/           # ESP32-S3 firmware (C, ESP-IDF)
│   ├── components/     # HAL, control, safety modules
│   │   ├── hal/        # Hardware abstraction (ADC, PWM, GPIO, SPI)
│   │   ├── control/    # PID controller, PLL tracking
│   │   └── safety/     # Safety monitoring, fault handling
│   ├── main/           # Application entry point + state machine
│   │   ├── state_machine.c  # Core 8-state state machine
│   │   └── main.c      # Application entry
│   ├── test/           # Unity-based unit and integration tests
│   │   ├── test_state_machine.c  # 37 unit tests
│   │   └── test_integration.c    # 30 integration tests
│   └── README.md       # Detailed firmware documentation
├── pcb/                # KiCad schematics (hierarchical)
│   ├── temper.kicad_sch       # Root schematic
│   ├── half_bridge.kicad_sch  # Power stage
│   ├── mcu.kicad_sch          # Microcontroller
│   ├── power_management.kicad_sch
│   ├── sensing.kicad_sch
│   ├── safety_interlock.kicad_sch
│   └── user_interface.kicad_sch
├── simulation/         # SPICE simulations (ngspice)
│   ├── models/         # Component SPICE models
│   ├── testbenches/    # .cir simulation files
│   └── results/        # Simulation outputs (.md reports)
├── components/         # Component libraries
│   ├── */              # Per-component: .kicad_sym, .lib, _Documentation.md
│   │                   # IKW40N120H3, UCC21550, LMR51430, MAX31865, etc.
├── temper-placer/      # JAX-based PCB placement optimizer
│   ├── src/temper_placer/
│   │   ├── core/       # Netlist, Board, PlacementState
│   │   ├── losses/     # Differentiable loss functions (12+ types)
│   │   ├── optimizer/  # Training loop, curriculum learning
│   │   ├── heuristics/ # Smart initialization (10 heuristics)
│   │   ├── io/         # KiCad parser/writer, config loader
│   │   ├── geometry/   # Transforms, overlap detection
│   │   ├── validation/ # DRC integration, preflight checks
│   │   └── visualization/ # HTML reports, board rendering
│   ├── tests/          # pytest test suite
│   │   ├── heuristics/ # Heuristics pipeline tests
│   │   ├── integration/# Roundtrip tests
│   │   └── validation/ # DRC correlation tests
│   ├── configs/        # Constraint YAML files
│   └── README.md       # temper-placer documentation
├── datasheets/         # Reference datasheets (PDF)
└── *.md                # Design documents
```

### Key Design Documents

| Document                                     | Purpose                                |
| -------------------------------------------- | -------------------------------------- |
| `TEMPER_PLACER_DESIGN.md`                    | PCB placer architecture and algorithms |
| `RESONANT_TANK_DESIGN.md`                    | LC tank calculations and tuning        |
| `HALF_BRIDGE_VERIFICATION_REPORT.md`         | Power stage validation                 |
| `GATE_DRIVER_POWER_ARCHITECTURE_DECISION.md` | Bootstrap vs isolated supply           |
| `CT_SENSING_DESIGN.md`                       | Current transformer sensing circuit    |
| `THERMAL_DESIGN_GUIDE.md`                    | Thermal management strategy            |
| `SAFETY_INTERLOCK_DESIGN.md`                 | Protection circuit design              |
| `PCB_SPECIFICATION.md`                       | Board constraints and zones            |

### temper-placer: PCB Placement Optimizer

The placer is a JAX-based gradient descent optimizer for component placement with **validation-in-the-loop** integration with KiCad DRC and ngspice.

**Key Features:**

- **Gumbel-Softmax discrete rotation** - Differentiable 0°/90°/180°/270° rotation
- **Multi-objective optimization** - 12+ loss functions (wirelength, overlap, thermal, EMI, etc.)
- **Smart initialization** - 10 heuristics applied before gradient descent
- **Curriculum learning** - Progressive constraint introduction
- **KiCad integration** - Native file format support via kiutils
- **Validation-in-the-loop** - KiCad DRC and ngspice integration for electrical soundness

**Installation:**

```bash
cd temper-placer

# With uv (recommended)
uv venv
uv pip install -e "(.[dev])"

# With pip
pip install -e "(.[dev])"
```

**Running the optimizer:**

```bash
# Basic optimization
temper-placer optimize input.kicad_pcb -c constraints.yaml -o output.kicad_pcb

# With all features
temper-placer optimize input.kicad_pcb -c constraints.yaml -o output.kicad_pcb \
    --epochs 8000 \
    --seed 42 \
    --curriculum \        # Multi-phase learning (default)
    --heuristics \        # Smart initialization (default)
    --visualize \         # Live browser-based dashboard
    --placements-json placements.json

# Run DRC validation
temper-placer validate output.kicad_pcb
```

**Key CLI flags:**

- `--heuristics/--no-heuristics` - Smart initialization using 10 heuristics (default: enabled)
- `--curriculum/--no-curriculum` - Multi-phase curriculum learning (default: enabled)
- `--epochs N` - Number of optimization epochs (default: 8000)
- `--seed N` - Random seed for reproducibility
- `--visualize` - Enable live visualization (browser-based)

**Heuristics Pipeline:**

The placer uses 10 heuristics applied in priority order before gradient optimization:

1. **HARD constraints:**

   - `KeepoutAwarenessHeuristic` - Respect keep-out zones

2. **STRUCTURAL constraints:**

   - `ConnectorEdgeSnappingHeuristic` - Place connectors on board edges
   - `ThermalEdgePlacementHeuristic` - Place thermal components near edges
   - `CriticalLoopHeuristic` - Minimize switching loop areas

3. **ORGANIZATIONAL constraints:**

   - `FunctionalModuleClusteringHeuristic` - Group related components
   - `PowerFlowTopologyHeuristic` - Arrange input → distribution → load
   - `DecouplingCapHeuristic` - Position decoupling caps near ICs
   - `DomainSeparationHeuristic` - Separate analog/digital domains

4. **STYLE constraints:**
   - `StarGroundTopologyHeuristic` - Star ground arrangement
   - `SignalFlowPreservationHeuristic` - Left-to-right signal flow

**Testing the placer:**

```bash
cd temper-placer

# Run all tests
pytest

# Run specific test suites
pytest tests/heuristics/ -v          # Heuristics pipeline tests
pytest tests/integration/ -v         # KiCad roundtrip tests
pytest tests/validation/ -v          # DRC correlation tests

# With coverage
pytest --cov=temper_placer --cov-report=html

# Type checking
mypy src

# Linting
ruff check src tests
```

**Key modules:**

- `temper_placer.heuristics` - Smart initialization (`create_default_pipeline()`)
- `temper_placer.optimizer` - Training loop (`train`, `train_multiphase`)
- `temper_placer.losses` - 12+ differentiable loss functions
- `temper_placer.io` - KiCad parser/writer, config loader
- `temper_placer.geometry` - Transforms, SDF, overlap detection (JAX-accelerated)
- `temper_placer.validation` - DRC integration, preflight checks
- `temper_placer.visualization` - HTML reports, board rendering

**Documentation:**

- See `temper-placer/README.md` for quick start
- See `TEMPER_PLACER_DESIGN.md` for full design specification
- See `temper-placer/docs/USAGE.md` for detailed usage guide

### Simulation Workflow

SPICE simulations use ngspice with custom component models:

```bash
# Run a simulation
cd simulation/testbenches
ngspice -b sim_01_ac_rectifier_softstart.cir

# Results go to simulation/results/
```

**Simulation naming convention:**

- `sim_XX_description.cir` - Testbench files
- `sim_XX_description.md` - Result analysis

### Firmware Development

The firmware uses ESP-IDF with a state machine-driven architecture. See `firmware/README.md` for complete documentation.

**Architecture:**

- **8-state state machine** (`main/state_machine.c`) - INIT, IDLE, PAN_DET, PREHEAT, HEATING, NO_PAN, COOLDOWN, FAULT
- **Comprehensive testing** - 37 unit tests + 30 integration tests (Unity framework)
- **Modular HAL** - Hardware abstraction for ADC, PWM, GPIO, SPI
- **Safety-critical** - Multiple protection layers (OCP, OVP, thermal, watchdog)

**Building for ESP32-S3:**

```bash
cd firmware
idf.py set-target esp32s3
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

**Running Tests (Host-Based):**

```bash
cd firmware/test
mkdir -p build && cd build
cmake ..
make

# Run specific test suites
./test_state_machine_only    # 37 unit tests
./test_integration_only       # 30 integration tests

# Run all tests via CTest
ctest --output-on-failure
```

**Module structure:**

- `components/hal/` - Hardware abstraction (ADC, PWM, GPIO, SPI, Timer)
  - `hal/esp32/` - ESP32-S3 specific implementations
  - `hal/mock/` - Mock implementations for testing
- `components/control/` - Control loops (PID, PLL tracking)
- `components/safety/` - Safety monitoring, fault handling
- `main/state_machine.c` - Core state machine (8 states, fault recovery)
- `test/` - Unity-based tests with mock HAL

**Safety Features:**

1. **Hardware Watchdog** (TPS3823-33) - 1.6s timeout, external WDT
2. **Software Watchdog** - State-specific timeouts (1-10s)
3. **Over-Current Protection** - DC bus >35A triggers shutdown
4. **Over-Temperature Protection** - Heatsink >100°C triggers fault
5. **Fan Failure Detection** - Tachometer monitoring
6. **RTD Probe Monitoring** - Open/short circuit detection
7. **Thermal Runaway Detection** - Pan temp >target + 10°C
8. **Pan Detection** - Impedance-based with confidence threshold

**Key Configuration:**

- Target temp range: 50-250°C
- Pan detection timeout: 5s
- Pan removal grace period: 3s
- Max preheat time: 10 minutes
- Safe idle temp: 50°C

## Current Project Status

**Overall Progress** (as of latest `bd stats`):

- **Total Issues**: 442
- **Open**: 69
- **In Progress**: 2
- **Closed**: 371
- **Blocked**: 4
- **Ready**: 65
- **Avg Lead Time**: 7.0 hours

Check current work with:

```bash
bd stats                     # Overall project statistics
bd ready --json              # Unblocked issues ready for work
bd list --issue-type epic    # All epics
bd show temper-7t1           # Main placer epic
bd show temper-1my           # Optimizer validation epic
bd show temper-37v           # Induction cooker development epic
```

### Key Active Areas

1. **temper-placer** - PCB placement optimizer (PRIMARY FOCUS - P1)

   - ✅ Core optimizer operational with curriculum learning
   - ✅ 10 heuristics implemented and tested
   - ✅ DRC validation integration complete
   - ✅ Preflight checks implemented
   - 🔄 Comprehensive test suite expansion (temper-1by)
   - 🔄 Optimizer validation against ground truth (temper-1my)
   - 🔄 Missing loss functions (temper-jzq, temper-ft9, temper-c1e)
   - **Related Epics**: temper-7t1, temper-1by, temper-1my, temper-jzq, temper-ft9, temper-c1e

2. **Firmware** - ESP32-S3 control (COMPLETE - Core Implementation)

   - ✅ 8-state state machine implemented (`main/state_machine.c`)
   - ✅ 37 unit tests passing
   - ✅ 30 integration tests passing
   - ✅ HAL layer with ESP32 and mock implementations
   - ✅ Comprehensive safety features (8 protection layers)
   - ✅ PID control, PLL tracking components
   - **Related Epic**: temper-37v (ongoing development)

3. **PCB Design** - KiCad schematics

   - ✅ Hierarchical design (7 subsystem sheets)
   - ✅ Component library complete (IKW40N120H3, UCC21550, LMR51430, MAX31865, etc.)
   - 🔄 Awaiting temper-placer optimization for layout
   - **Key Docs**: PCB_SPECIFICATION.md, COMPONENT_COMPATIBILITY_VERIFICATION.md

4. **Simulation** - SPICE verification
   - ✅ 32+ simulation testbenches complete
   - ✅ Power stage validated (half-bridge, gate driver, thermal)
   - ✅ Auxiliary power verified (LMR51430, isolated supplies)
   - ✅ Safety interlocks verified
   - ✅ Interface timing verified (SPI, I2C, PWM, ADC)
   - **Key Docs**: HALF_BRIDGE_VERIFICATION_REPORT.md, THERMAL_DESIGN_GUIDE.md

### Top Priority Work (P1, Ready)

Based on `bd ready`, the following P1 issues have no blockers:

1. **temper-7t1** - temper-placer: JAX-based PCB placement optimizer (EPIC)
2. **temper-1by** - Comprehensive Test Suite for PCB Generation Pipeline (EPIC)
3. **temper-1my** - Optimizer Validation Epic: Ensure Real-World Placement Quality (EPIC)
   - **temper-1my.6.1** - Create hand-placed reference Temper layout
   - **temper-1my.6.4** - Iterate optimizer until it matches reference quality
4. **temper-7zi** - External PCB Ground Truth Validation (EPIC)

### Recent Completions

- ✅ State machine implementation with comprehensive testing (Lesson 31)
- ✅ Component compatibility verification report
- ✅ Heuristics framework implementation (temper-600)
- ✅ DRC integration and validation pipeline

---

## Temper Development Guidelines

### Working with temper-placer

**Before making changes:**

1. Read `TEMPER_PLACER_DESIGN.md` for architecture overview
2. Check `temper-placer/README.md` for CLI usage
3. Review related bd issues: `bd list --label placer --status open`

**Development workflow:**

```bash
cd temper-placer

# Setup environment
uv venv
uv pip install -e "(.[dev])"

# Make changes to src/

# Run tests
pytest                       # All tests
pytest tests/losses/ -v      # Specific module
pytest -k "test_overlap"     # Specific test pattern

# Type checking and linting
mypy src
ruff check src tests

# Test actual optimization
temper-placer optimize ../pcb/temper.kicad_pcb \
    -c configs/temper_constraints.yaml \
    -o /tmp/test_placement.kicad_pcb \
    --epochs 1000 --seed 42
```

**Testing requirements for temper-placer:**

- All new loss functions MUST have unit tests
- Heuristics MUST have integration tests
- Geometry functions MUST have property-based tests where applicable
- DRC integration changes MUST verify against real KiCad output

### Working with Firmware

**Before making changes:**

1. Read `firmware/README.md` for architecture overview
2. Understand the state machine (`main/state_machine.c`)
3. Check safety implications - this is safety-critical code

**Development workflow:**

```bash
cd firmware

# For ESP32-S3 target build
idf.py set-target esp32s3
idf.py menuconfig           # Configure if needed
idf.py build
idf.py flash monitor        # Flash and monitor

# For host-based tests (preferred for rapid iteration)
cd test
mkdir -p build && cd build
cmake ..
make

# Run tests
./test_state_machine_only   # Fast unit tests
./test_integration_only       # Full integration tests
ctest --output-on-failure   # All tests

# Make changes, rebuild, retest
cd ..
cmake . && make && ./test_state_machine_only
```

**Testing requirements for firmware:**

- State machine changes MUST include unit tests
- Safety-critical features MUST include fault injection tests
- HAL changes MUST update both real and mock implementations
- Integration tests MUST cover complete operational sequences
- Minimum coverage: 80% line coverage for state machine

### Working with Simulations

**Before adding simulations:**

1. Check `simulation/results/` for existing similar sims
2. Follow naming convention: `sim_XX_description.cir`
3. Create corresponding `.md` report in `results/`

**Running simulations:**

```bash
cd simulation/testbenches

# Run specific simulation
ngspice -b sim_01_ac_rectifier_verification.cir > ../results/sim_01.log

# Analyze results
cd ../results
cat sim_01_ac_rectifier_verification.md  # Read analysis
```

**Simulation requirements:**

- All new circuits MUST have SPICE verification
- Use realistic component models from `simulation/models/`
- Document results with analysis in `results/*.md`
- Include plots/waveforms for key signals

### Documentation Standards

**When to create/update docs:**

1. **Design decisions** → Create `*_DESIGN.md` or `*_DECISION.md`

   - Example: `GATE_DRIVER_POWER_ARCHITECTURE_DECISION.md`
   - Include: rationale, alternatives considered, trade-offs

2. **Verification results** → Create `*_VERIFICATION_REPORT.md`

   - Example: `HALF_BRIDGE_VERIFICATION_REPORT.md`
   - Include: test conditions, results, pass/fail criteria

3. **Component analysis** → Update `components/*/.*_Documentation.md`

   - Include: electrical specs, thermal analysis, layout considerations

4. **API changes** → Update module README.md
   - `firmware/README.md`, `temper-placer/README.md`, etc.

**Documentation format:**

- Use markdown with clear section headers
- Include code examples for APIs
- Add tables for specifications/comparisons
- Reference bd issues where relevant: `See temper-123 for details`
- Use conventional commit format when updating docs

### Testing Philosophy

**For temper-placer (Python/JAX):**

- Fast unit tests (<10ms each)
- Integration tests run full pipelines
- Property-based tests for geometry (hypothesis)
- Validation tests against KiCad DRC
- Benchmark tests for performance regressions

**For firmware (C/Unity):**

- Unit tests with mocks (fast, isolated)
- Integration tests with full system (realistic scenarios)
- Fault injection tests (safety critical)
- Stress tests (long duration, rapid state changes)
- Time-based tests use mock time advancement

**Test naming convention:**

```python
# Python (pytest)
def test_overlap_loss_detects_simple_overlap():
    """Overlap loss should return >0 for overlapping rectangles."""
    ...

# C (Unity)
void test_state_transition_idle_to_pan_det_on_start_button(void) {
    ...
}
```

### Common Workflows

**Adding a new loss function to temper-placer:**

1. Create issue: `bd create "Implement XyzLoss for ..." -t task -p 1 --parent temper-jzq`
2. Read `TEMPER_PLACER_DESIGN.md` section on loss functions
3. Implement in `src/temper_placer/losses/xyz.py`
4. Add unit tests in `tests/losses/test_xyz.py`
5. Register in `src/temper_placer/losses/__init__.py`
6. Add to default config in `configs/temper_constraints.yaml`
7. Run full test suite: `pytest`
8. Document in code docstrings
9. Close issue: `bd close <id> --reason "Implemented XyzLoss with unit tests"`

**Adding a component to the library:**

1. Create `components/PART_NUMBER/` directory
2. Add KiCad symbol (`.kicad_sym`)
3. Add SPICE model (`.lib` if available)
4. Create `PART_NUMBER_Documentation.md` with:
   - Electrical specifications
   - Thermal characteristics
   - Layout recommendations
   - Application notes
5. Update `BOM.md` if using in Temper design
6. Add verification simulation if power/critical component

**Modifying the state machine:**

1. **CRITICAL**: Understand safety implications first
2. Update state diagram in `firmware/README.md` if adding states
3. Modify `firmware/main/state_machine.c`
4. Update corresponding tests in `firmware/test/test_state_machine.c`
5. Add integration test in `firmware/test/test_integration.c`
6. Run full test suite: `cd firmware/test/build && make && ctest`
7. Document new behavior in `firmware/README.md`
8. Consider creating `STATE_MACHINE_CHANGE_LOG.md` for major changes

## Common Development Tasks

See [AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md) for detailed instructions on:

- Adding new commands
- Adding storage features
- Adding examples
- Building and testing
- Version management
- Release process

## Pro Tips for Agents

- Always use `--json` flags for programmatic use
- **Always run `bd sync` at end of session** to flush/commit/push immediately
- **Check `bd info --whats-new` at session start** if bd was recently upgraded
- **Run `bd hooks install`** if `bd info` warns about outdated git hooks
- Link discoveries with `discovered-from` to maintain context
- Check `bd ready` before asking "what next?"
- Auto-sync batches changes in 30-second window - use `bd sync` to force immediate flush
- Use `bd dep tree` to understand complex dependencies
- Priority 0-1 issues are usually more important than 2-4
- Use `--dry-run` to preview import changes before applying
- Hash IDs eliminate collisions - same ID with different content is a normal update
- Use `--id` flag with `bd create` to partition ID space for parallel workers (e.g., `worker1-100`, `worker2-500`)

### Bias Towards Small, Iterative Tasks

**IMPORTANT**: When planning work, strongly prefer creating many small, focused tasks over fewer large ones. This applies to both epics and individual issues.

**Why small tasks?**

- **Faster feedback loops**: Complete and verify work incrementally
- **Easier resumption**: Sessions end unexpectedly; small tasks let you pick up easily
- **Better tracking**: Clear progress visibility with `bd stats`
- **Reduced risk**: Small changes are easier to test and revert
- **Parallel work**: Multiple agents can work on different small tasks simultaneously

**Guidelines:**

- **Epics**: Break into 5-15 subtasks, each completable in one session
- **Tasks**: Should be completable in 30-60 minutes of focused work
- **If a task feels big**: Split it immediately with `bd create --parent <epic-id>`
- **Create issues frequently**: When you discover work, create an issue right away

**Example - BAD (monolithic):**

```bash
bd create "Implement placement optimizer" -t epic -p 1  # Too vague, too big
```

**Example - GOOD (granular):**

```bash
bd create "Implement placement optimizer" -t epic -p 1
bd create "Implement geometric primitives (point, rect)" --parent <epic-id> -p 1
bd create "Implement overlap detection" --parent <epic-id> -p 1
bd create "Implement boundary_loss function" --parent <epic-id> -p 1
bd create "Add unit tests for geometry module" --parent <epic-id> -p 2
# ... continue breaking down until each task is small and focused
```

**When in doubt**: Create more issues. It's easier to merge or close unnecessary issues than to remember untracked work.

### Checking GitHub Issues and PRs

Use `gh` CLI tools for checking issues/PRs (see [AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md) for details).

## Building, Testing, Versioning, and Releases

See [AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md) for complete details on:

- Building and testing (`go build`, `go test`)
- Version management (`./scripts/bump-version.sh`)
- Release process (`./scripts/release.sh`)

---

**Remember**: We're building this tool to help AI agents like you! If you find the workflow confusing or have ideas for improvement, create an issue with your feedback.

Happy coding! 🔗

<!-- bd onboard section -->

## Issue Tracking with bd (beads)

**IMPORTANT**: This project uses **bd (beads)** for ALL issue tracking. Do NOT use markdown TODOs, task lists, or other tracking methods.

### Why bd?

- Dependency-aware: Track blockers and relationships between issues
- Git-friendly: Auto-syncs to JSONL for version control
- Agent-optimized: JSON output, ready work detection, discovered-from links
- Prevents duplicate tracking systems and confusion

### Quick Start

**FIRST TIME?** Just run `bd init` - it auto-imports issues from git:

```bash
bd init --prefix bd
```

**OSS Contributor?** Use the contributor wizard for fork workflows:

```bash
bd init --contributor  # Interactive setup for separate planning repo
```

**Team Member?** Use the team wizard for branch workflows:

```bash
bd init --team  # Interactive setup for team collaboration
```

**Check for ready work:**

```bash
bd ready --json
```

**Create new issues:**

```bash
bd create "Issue title" -t bug|feature|task -p 0-4 --json
bd create "Issue title" -p 1 --deps discovered-from:bd-123 --json
bd create "Subtask" --parent <epic-id> --json  # Hierarchical subtask (gets ID like epic-id.1)
```

**Claim and update:**

```bash
bd update bd-42 --status in_progress --json
bd update bd-42 --priority 1 --json
```

**Complete work:**

```bash
bd close bd-42 --reason "Completed" --json
```

### Issue Types

- `bug` - Something broken
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature with subtasks
- `chore` - Maintenance (dependencies, tooling)

### Priorities

- `0` - Critical (security, data loss, broken builds)
- `1` - High (major features, important bugs)
- `2` - Medium (default, nice-to-have)
- `3` - Low (polish, optimization)
- `4` - Backlog (future ideas)

### Workflow for AI Agents

1. **Check ready work**: `bd ready` shows unblocked issues
2. **Claim your task**: `bd update <id> --status in_progress`
3. **Work on it**: Implement, test, document
4. **Discover new work?** Create linked issue:
   - `bd create "Found bug" -p 1 --deps discovered-from:<parent-id>`
5. **Complete**: `bd close <id> --reason "Done"`
6. **Commit together**: Always commit the `.beads/issues.jsonl` file together with the code changes so issue state stays in sync with code state

### Auto-Sync

bd automatically syncs with git:

- Exports to `.beads/issues.jsonl` after changes (5s debounce)
- Imports from JSONL when newer (e.g., after `git pull`)
- No manual export/import needed!

### GitHub Copilot Integration

If using GitHub Copilot, also create `.github/copilot-instructions.md` for automatic instruction loading. Run `bd onboard` to get the content, or see step 2 of the onboard instructions.

### MCP Server (Recommended)

If using Claude or MCP-compatible clients, install the beads MCP server:

```bash
pip install beads-mcp
```

Add to MCP config (e.g., `~/.config/claude/config.json`):

```json
{
  "beads": {
    "command": "beads-mcp",
    "args": []
  }
}
```

Then use `mcp__beads__*` functions instead of CLI commands.

### Managing AI-Generated Planning Documents

AI assistants often create planning and design documents during development:

- PLAN.md, IMPLEMENTATION.md, ARCHITECTURE.md
- DESIGN.md, CODEBASE_SUMMARY.md, INTEGRATION_PLAN.md
- TESTING_GUIDE.md, TECHNICAL_DESIGN.md, and similar files

**Best Practice: Use a dedicated directory for these ephemeral files**

**Recommended approach:**

- Create a `history/` directory in the project root
- Store ALL AI-generated planning/design docs in `history/`
- Keep the repository root clean and focused on permanent project files
- Only access `history/` when explicitly asked to review past planning

**Example .gitignore entry (optional):**

```
# AI planning documents (ephemeral)
history/
```

**Benefits:**

- ✅ Clean repository root
- ✅ Clear separation between ephemeral and permanent documentation
- ✅ Easy to exclude from version control if desired
- ✅ Preserves planning history for archeological research
- ✅ Reduces noise when browsing the project

### CLI Help

Run `bd <command> --help` to see all available flags for any command.
For example: `bd create --help` shows `--parent`, `--deps`, `--assignee`, etc.

### Important Rules

- ✅ Use bd for ALL task tracking
- ✅ Always use `--json` flag for programmatic use
- ✅ Link discovered work with `discovered-from` dependencies
- ✅ Check `bd ready` before asking "what should I work on?"
- ✅ Store AI planning docs in `history/` directory
- ✅ Run `bd <cmd> --help` to discover available flags
- ❌ Do NOT create markdown TODO lists
- ❌ Do NOT use external issue trackers
- ❌ Do NOT duplicate tracking systems
- ❌ Do NOT clutter repo root with planning documents

For more details, see README.md and QUICKSTART.md.

<!-- /bd onboard section -->

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**

- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

## 🧠 The Cognitive Stack: Beads + ECO

To maintain context across different tasks and parallel sessions, we use two complementary memory systems:

1. **Beads (Project Memory):** Use `bd` for task tracking, blockers, and feature-specific state. This is stored in Git.
2. **ECO (Global Knowledge):** Use ECO for long-term "facts" (e.g., "The user prefers Rust for performance-critical modules"). This persists across all branches and worktrees. The ECO memory server runs remotely at **https://eco.bennetleff.workers.dev**.

**Rule for Agents:** - If information is about a **task**, put it in a `bd` issue description.

- If information is a **general project fact or user preference**, store it in **ECO**.

## 🌲 Parallel Execution with Git Worktrees

To work on multiple tasks simultaneously without context-clobbering, we use Git Worktrees.

### Worktree Directory Structure

~/worktrees/
└── temper/
├── bd-123/ # Worktree for task bd-123
├── bd-456/ # Worktree for task bd-456
└── ...

### 🛠 Workflow for Parallel Agents

1. **Create Worktree:** Use the helper `bd-work <id>` to spin up a new directory and branch.
2. **Sandbox Mode (Mandatory):** In a worktree, always use `bd --sandbox`. This prevents the daemon from fighting over the shared database across different folders.
3. **Cross-Pollination:** Before starting work in a new worktree, query **ECO** for any relevant global context learned by other agents in parallel branches.
4. **Completion:** Use `bd-done` to push and close.

```
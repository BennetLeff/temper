# Detailed Agent Instructions for Beads Development

**For project overview and quick start, see [AGENTS.md](AGENTS.md)**

This document contains detailed operational instructions for AI agents working on beads development, testing, and releases.

## Development Guidelines

### Code Standards

- **Go version**: 1.21+
- **Linting**: `golangci-lint run ./...` (baseline warnings documented in [docs/LINTING.md](docs/LINTING.md))
- **Testing**: All new features need tests (`go test -short ./...` for local, full tests run in CI)
- **Documentation**: Update relevant .md files

### File Organization

```
beads/
├── cmd/bd/              # CLI commands
├── internal/
│   ├── types/           # Core data types
│   └── storage/         # Storage layer
│       └── sqlite/      # SQLite implementation
├── examples/            # Integration examples
└── *.md                 # Documentation
```

### Testing Workflow

**IMPORTANT:** Never pollute the production database with test issues!

**For manual testing**, use the `BEADS_DB` environment variable to point to a temporary database:

```bash
# Create test issues in isolated database
BEADS_DB=/tmp/test.db ./bd init --quiet --prefix test
BEADS_DB=/tmp/test.db ./bd create "Test issue" -p 1

# Or for quick testing
BEADS_DB=/tmp/test.db ./bd create "Test feature" -p 1
```

**For automated tests**, use `t.TempDir()` in Go tests:

```go
func TestMyFeature(t *testing.T) {
    tmpDir := t.TempDir()
    testDB := filepath.Join(tmpDir, ".beads", "beads.db")
    s := newTestStore(t, testDB)
    # ... test code
}
```

**Warning:** bd will warn you when creating issues with "Test" prefix in the production database. Always use `BEADS_DB` for manual testing.

### Before Committing

1. **Run tests**: `go test -short ./...` (full tests run in CI)
2. **Run linter**: `golangci-lint run ./...` (ignore baseline warnings)
3. **Update docs**: If you changed behavior, update README.md or other docs
4. **Commit**: Issues auto-sync to `.beads/issues.jsonl` and import after pull

### Git Workflow

**Auto-sync provides batching!** bd automatically:

- **Exports** to JSONL after CRUD operations (30-second debounce for batching)
- **Imports** from JSONL when it's newer than DB (e.g., after `git pull`)
- **Daemon commits/pushes** every 5 seconds (if `--auto-commit` / `--auto-push` enabled)

The 30-second debounce provides a **transaction window** for batch operations - multiple issue changes within 30 seconds get flushed together, avoiding commit spam.

### Git Integration

**Auto-sync**: bd automatically exports to JSONL (30s debounce), imports after `git pull`, and optionally commits/pushes.

**Protected branches**: Use `bd init --branch beads-metadata` to commit to separate branch. See [docs/PROTECTED_BRANCHES.md](docs/PROTECTED_BRANCHES.md).

**Git worktrees**: Use `bd --sandbox` for all commands in worktrees. This disables daemon and auto-sync to prevent conflicts when multiple agents work in parallel. See [docs/GIT_INTEGRATION.md](docs/GIT_INTEGRATION.md).

**Merge conflicts**: Rare with hash IDs. If conflicts occur, use `git checkout --theirs/.beads/beads.jsonl` and `bd import`. See [docs/GIT_INTEGRATION.md](docs/GIT_INTEGRATION.md).

## Agentic Workflow System

### Infrastructure
- **Dispatcher**: `tools/agents/dispatch_core.sh` routes tasks to Gemini Pro (Thinking) or Flash (Fast).
- **Assigner**: `tools/agents/assign.py` bridges `bd` issues with the dispatcher.
- **Automation**: `tools/agents/auto_assign.py` provides a label-driven autonomous loop.
- **Memory**: OpenMemory (MCP) provides long-term cross-session knowledge.

### Creating Instructions for Sub-Agents
When delegating, ensure your issue description (the instruction) follows these rules:
1.  **Context-Rich**: Explicitly list filenames the sub-agent needs to read.
2.  **Role-Specific**: Choose the role that matches the task complexity (e.g., use `architect` for new modules).
3.  **Actionable**: Define clear success criteria for the sub-agent.

### Workflow Example
```bash
# 1. Context Retrieval (MANDATORY)
# Query OpenMemory for relevant facts/decisions
POST /memories/search { "query": "auth_design_patterns", "userId": "temper-agent" }

# 2. User/Master finds a complex task
bd create "Design Secure Auth" -t task --label agent:architect

# 3. Run automation
python3 tools/agents/auto_assign.py

# 4. Architect (Pro) produces design in agent_outputs/
# 5. Master reviews design, then creates coding task
bd create "Implement Auth" -t task --label agent:coder

# 6. Run automation again
python3 tools/agents/auto_assign.py

# 7. Reflection (MANDATORY)
# Post what was learned to OpenMemory
POST /memories { "content": "REFLECTION: Learned that auth-v2 requires...", "userId": "temper-agent", "tags": ["reflection"] }
```

## Landing the Plane

**When the user says "let's land the plane"**, you MUST complete ALL steps below. The plane is NOT landed until `git push` succeeds and a **Reflection** is posted.

**MANDATORY WORKFLOW - COMPLETE ALL STEPS:**

1. **Post Reflection to OpenMemory** - Summarize architectural decisions and findings for the project's long-term memory.
2. **File beads issues for any remaining work** that needs follow-up.
3. **Ensure all quality gates pass** (only if code changes were made) - run tests, linters, builds (file P0 issues if broken).
4. **Update beads issues** - close finished work, update status.
5. **PUSH TO REMOTE - NON-NEGOTIABLE** - This step is MANDATORY. Execute ALL commands below:
   ```bash
   # Pull first to catch any remote changes
   git pull --rebase

   # Sync the database (exports to JSONL, commits)
   bd sync

   # MANDATORY: Push everything to remote
   git push

   # MANDATORY: Verify push succeeded
   git status  # MUST show "up to date with origin/main"
   ```

   **CRITICAL RULES:**
   - The plane has NOT landed until `git push` completes successfully.
   - NEVER stop before `git push` - that leaves work stranded locally.
   - NEVER say "ready to push when you are!" - YOU must push, not the user.

6. **Clean up git state** - Clear old stashes and prune dead remote branches.
7. **Verify clean state** - Ensure all changes are committed AND PUSHED, no untracked files remain.
8. **Choose a follow-up issue for next session.**

## Agent Session Workflow

**IMPORTANT for AI agents:** When you start a session, always query OpenMemory for relevant context. When you finish making issue changes, always run `bd sync`.

**Example agent session:**

```bash
# 1. Gather Context
POST /memories/search { "query": "similar tasks to bd-42", "userId": "temper-agent" }

# 2. Claim Task
bd update bd-42 --status in_progress

# 3. Work...

# 4. Post Reflection
POST /memories { "content": "REFLECTION: Found that component X has a hidden dependency on Y", "userId": "temper-agent", "tags": ["reflection"] }

# 5. Force immediate sync at end of session
bd sync
```

## Common Development Tasks

### Adding a New Command

1. Create file in `cmd/bd/`
2. Add to root command in `cmd/bd/main.go`
3. Implement with Cobra framework
4. Add `--json` flag for agent use
5. Add tests in `cmd/bd/*_test.go`
6. Document in README.md

### Adding Storage Features

1. Update schema in `internal/storage/sqlite/schema.go`
2. Add migration if needed
3. Update `internal/types/types.go` if new types
4. Implement in `internal/storage/sqlite/sqlite.go`
5. Add tests
6. Update export/import in `cmd/bd/export.go` and `cmd/bd/import.go`

### Adding Examples

1. Create directory in `examples/`
2. Add README.md explaining the example
3. Include working code
4. Link from `examples/README.md`
5. Mention in main README.md

## Building and Testing

```bash
# Build
go build -o bd ./cmd/bd

# Test (short - for local development)
go test -short ./...

# Test with coverage (full tests - for CI)
go test -coverprofile=coverage.out ./...
go tool cover -html=coverage.out

# Run locally
./bd init --prefix test
./bd create "Test issue" -p 1
./bd ready
```

## Version Management

**IMPORTANT**: When the user asks to "bump the version" or mentions a new version number (e.g., "bump to 0.9.3"), use the version bump script:

```bash
# Preview changes (shows diff, doesn't commit)
./scripts/bump-version.sh 0.9.3

# Auto-commit the version bump
./scripts/bump-version.sh 0.9.3 --commit
git push origin main
```

## Release Process (Maintainers)

**Automated (Recommended):**

```bash
# One command to do everything (version bump, tests, tag, Homebrew update, local install)
./scripts/release.sh 0.9.3
```

## Checking GitHub Issues and PRs

**IMPORTANT**: When asked to check GitHub issues or PRs, use command-line tools like `gh` instead of browser/playwright tools.

## Important Files

- **README.md** - Main documentation (keep this updated!)
- **EXTENDING.md** - Database extension guide
- **ADVANCED.md** - JSONL format analysis
- **CONTRIBUTING.md** - Contribution guidelines
- **SECURITY.md** - Security policy

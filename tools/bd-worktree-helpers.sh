#!/usr/bin/env bash
# Git Worktree Helper Functions for bd Task Isolation
# Source this file in your shell: source tools/bd-worktree-helpers.sh
#
# GPBM Integration:
#   - Uses --sandbox flag for all bd commands (prevents daemon conflicts)
#   - Validates task exists before creating worktree
#   - Extracts task ID from git branch (not directory name)
#   - Supports both Bash and Zsh completion

# Configuration
BD_WORKTREE_ROOT="${BD_WORKTREE_ROOT:-$HOME/worktrees}"

# Get project name from git remote
_bd_get_project_name() {
    local remote_url
    remote_url=$(git remote get-url origin 2>/dev/null || echo "")
    if [[ -z "$remote_url" ]]; then
        # Fallback to directory name
        basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
    else
        # Extract project name from URL (works for both SSH and HTTPS)
        basename "$remote_url" .git
    fi
}

# Get task ID from current git branch (reliable across subdirectories)
_bd_get_task_id() {
    local branch
    branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
    
    if [[ -z "$branch" || "$branch" == "HEAD" || "$branch" == "main" || "$branch" == "master" ]]; then
        return 1
    fi
    
    echo "$branch"
}

# Validate task exists in bd
_bd_validate_task() {
    local task_id="$1"
    
    # Use --sandbox to avoid daemon conflicts in worktrees
    if ! bd --sandbox show "$task_id" --json &>/dev/null; then
        return 1
    fi
    return 0
}

# Start work on a bd task (creates/resumes worktree)
bd-work() {
    local task_id="$1"
    
    if [[ -z "$task_id" ]]; then
        echo "Usage: bd-work <task-id>"
        echo "Example: bd-work bd-123"
        return 1
    fi
    
    # Ensure we're in a git repo
    if ! git rev-parse --git-dir &>/dev/null; then
        echo "Error: Not in a git repository"
        return 1
    fi
    
    # Validate task exists in bd before creating worktree
    echo "Validating task $task_id..."
    if ! _bd_validate_task "$task_id"; then
        echo "Error: Task '$task_id' not found in bd"
        echo ""
        echo "Did you mean one of these?"
        bd --sandbox list --status open --json 2>/dev/null | grep -o '"id":"[^"]*"' | cut -d'"' -f4 | grep -i "${task_id:0:3}" | head -5 || echo "  (no similar tasks found)"
        return 1
    fi
    
    local project
    project=$(_bd_get_project_name)
    local worktree_dir="$BD_WORKTREE_ROOT/$project/$task_id"
    
    # Create worktree parent if needed
    mkdir -p "$BD_WORKTREE_ROOT/$project"
    
    if [[ -d "$worktree_dir" ]]; then
        # Resume existing worktree
        echo "Resuming existing worktree for $task_id"
        cd "$worktree_dir" || return 1
        
        # Pull latest changes if remote exists
        if git rev-parse --verify "origin/$task_id" &>/dev/null; then
            echo "Pulling latest changes..."
            git pull --rebase || {
                echo "Warning: Pull failed - you may need to resolve conflicts"
            }
        fi
    elif git show-ref --verify --quiet "refs/remotes/origin/$task_id"; then
        # Branch exists remotely - create worktree from it
        echo "Creating worktree from remote branch origin/$task_id"
        git worktree add "$worktree_dir" "$task_id"
        cd "$worktree_dir" || return 1
        git branch --set-upstream-to="origin/$task_id" "$task_id"
    else
        # New task - create fresh worktree from main
        echo "Creating new worktree for $task_id from main"
        git fetch origin main:main 2>/dev/null || true
        git worktree add "$worktree_dir" -b "$task_id"
        cd "$worktree_dir" || return 1
        
        # Push branch immediately to enable multi-machine sync
        echo "Pushing branch to remote..."
        git push -u origin "$task_id" || {
            echo "Warning: Initial push failed - will retry on bd-pause"
        }
    fi
    
    # Claim the task in bd (use --sandbox in worktree)
    echo "Claiming task $task_id"
    bd --sandbox update "$task_id" --status in_progress
    
    echo ""
    echo "✓ Now working on $task_id in $worktree_dir"
    echo "  Run 'bd-pause' before switching machines or ending session"
    echo "  Run 'bd-done' when task is complete"
}

# Pause work (commit WIP and push)
bd-pause() {
    # Ensure we're in a git repo
    if ! git rev-parse --git-dir &>/dev/null; then
        echo "Error: Not in a git repository"
        return 1
    fi
    
    # Get task ID from git branch (not directory name)
    local task_id
    task_id=$(_bd_get_task_id)
    
    if [[ -z "$task_id" ]]; then
        echo "Error: Not in a task branch (current branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'none'))"
        echo "       bd-pause should be run from a worktree with a task branch"
        return 1
    fi
    
    # Check if there are changes
    if git diff --quiet && git diff --cached --quiet; then
        echo "No changes to commit"
    else
        # Commit and push WIP
        git add -A
        git commit -m "WIP: progress on $task_id" || {
            echo "Warning: Commit failed (possibly nothing to commit)"
        }
    fi
    
    # Always try to push (handles both new commits and existing state)
    echo "Pushing to remote..."
    git push || {
        echo ""
        echo "Push failed. Try:"
        echo "  git pull --rebase && git push"
        return 1
    }
    
    # Sync bd state (use --sandbox in worktree)
    echo "Syncing bd state..."
    bd --sandbox sync
    
    echo ""
    echo "✓ Work paused and synced for $task_id"
    echo "  Resume on any machine with: bd-work $task_id"
}

# Complete task (close in bd, remind about PR)
bd-done() {
    local reason="${1:-Completed}"
    local force_flag=""
    local no_measure_flag=""
    
    # Parse flags
    while [[ "$1" == --* ]]; do
        case "$1" in
            --force)
                force_flag="1"
                shift
                ;;
            --no-measure)
                no_measure_flag="1"
                shift
                ;;
            *)
                shift
                ;;
        esac
    done
    
    # Get reason from remaining args
    if [[ -n "$1" ]]; then
        reason="$1"
    fi
    
    # Ensure we're in a git repo
    if ! git rev-parse --git-dir &>/dev/null; then
        echo "Error: Not in a git repository"
        return 1
    fi
    
    # Get task ID from git branch (not directory name)
    local task_id
    task_id=$(_bd_get_task_id)
    
    if [[ -z "$task_id" ]]; then
        echo "Error: Not in a task branch (current branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'none'))"
        echo "       bd-done should be run from a worktree with a task branch"
        return 1
    fi
    
    # Check for measurement targets (unless --force or --no-measure)
    if [[ -z "$force_flag" && -z "$no_measure_flag" ]]; then
        local has_measurements
        has_measurements=$(bd --sandbox show "$task_id" --json 2>/dev/null | grep -c 'measurement_targets' || echo "0")
        
        if [[ "$has_measurements" -gt 0 ]]; then
            echo "Task has measurement targets - running measurements..."
            if command -v python3 &>/dev/null && [[ -f "tools/gpbm/measure.py" ]]; then
                if ! python3 tools/gpbm/measure.py --task "$task_id" --json; then
                    echo ""
                    echo "Warning: Some measurements failed!"
                    read -p "Continue closing anyway? [y/N] " confirm
                    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
                        echo "Aborted. Fix issues and try again, or use --force to skip."
                        return 1
                    fi
                fi
            else
                echo "Note: measure.py not found, skipping measurements"
            fi
        fi
    fi
    
    # Final commit if needed
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "Committing final changes..."
        git add -A
        git commit -m "feat: complete $task_id" || true
    fi
    
    # Push
    echo "Pushing to remote..."
    git push || {
        echo ""
        echo "Push failed. Try:"
        echo "  git pull --rebase && git push"
        return 1
    }
    
    # Close in bd (use --sandbox in worktree)
    echo "Closing task in bd..."
    bd --sandbox close "$task_id" --reason "$reason"
    bd --sandbox sync
    
    echo ""
    echo "✓ Task $task_id marked as complete"
    echo ""
    echo "Next steps:"
    echo "  1. Create PR: gh pr create --fill"
    echo "  2. After PR merged, cleanup: bd-cleanup-worktrees"
    echo ""
    echo "  Or return to main repo: cd \$(git rev-parse --show-toplevel)"
}

# Cleanup old worktrees (for closed tasks with merged PRs)
bd-cleanup-worktrees() {
    local project
    project=$(_bd_get_project_name)
    local worktree_root="$BD_WORKTREE_ROOT/$project"
    
    if [[ ! -d "$worktree_root" ]]; then
        echo "No worktrees found for project $project"
        return 0
    fi
    
    echo "Checking for worktrees to cleanup in $worktree_root..."
    echo ""
    
    local cleaned=0
    local main_repo
    main_repo=$(git rev-parse --show-toplevel 2>/dev/null)
    
    # Iterate through worktree directories
    for worktree_dir in "$worktree_root"/*; do
        [[ -d "$worktree_dir" ]] || continue
        
        local task_id
        task_id=$(basename "$worktree_dir")
        
        # Check if task is closed in bd (use --sandbox)
        local status
        status=$(bd --sandbox show "$task_id" --json 2>/dev/null | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        
        if [[ "$status" != "closed" ]]; then
            continue
        fi
        
        # Check if branch is merged
        cd "$main_repo" || continue
        git fetch origin --prune
        
        if git branch -r --merged origin/main | grep -q "origin/$task_id"; then
            echo "✓ Cleaning up $task_id (closed + merged)"
            git worktree remove "$worktree_dir" --force 2>/dev/null || {
                echo "  Warning: Failed to remove worktree, trying manual cleanup..."
                rm -rf "$worktree_dir"
                git worktree prune
            }
            git branch -d "$task_id" 2>/dev/null || true
            git push origin --delete "$task_id" 2>/dev/null || true
            ((cleaned++))
        else
            echo "⊗ Skipping $task_id (closed but not merged)"
        fi
    done
    
    echo ""
    if [[ $cleaned -gt 0 ]]; then
        echo "✓ Cleaned up $cleaned worktree(s)"
    else
        echo "No worktrees ready for cleanup"
    fi
}

# List active worktrees
bd-worktrees() {
    local project
    project=$(_bd_get_project_name)
    local worktree_root="$BD_WORKTREE_ROOT/$project"
    
    if [[ ! -d "$worktree_root" ]]; then
        echo "No worktrees found for project $project"
        return 0
    fi
    
    echo "Active worktrees for $project:"
    echo ""
    
    for worktree_dir in "$worktree_root"/*; do
        [[ -d "$worktree_dir" ]] || continue
        
        local task_id
        task_id=$(basename "$worktree_dir")
        
        # Get bd status (use --sandbox)
        local status
        status=$(bd --sandbox show "$task_id" --json 2>/dev/null | grep -o '"status":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
        
        # Get last commit info
        local last_commit
        last_commit=$(cd "$worktree_dir" && git log -1 --format="%cr" 2>/dev/null || echo "unknown")
        
        echo "  $task_id [$status] - last commit: $last_commit"
        echo "    → $worktree_dir"
    done
}

# Print usage
bd-worktree-help() {
    cat <<'EOF'
Git Worktree Helper Functions for bd Task Isolation

=== Worktree Commands ===

  bd-work <task-id>           Start work on a task (creates/resumes worktree)
  bd-pause                    Pause work (commit WIP and push for multi-machine sync)
  bd-done [--force] [reason]  Complete task (close in bd, remind about PR)
  bd-cleanup-worktrees        Remove worktrees for closed+merged tasks
  bd-worktrees                List active worktrees with status
  bd-worktree-help            Show this help message

=== GPBM Workflow Commands ===

  bd-gather "goal" [role] [domain]     GATHER: Collect context for a goal
  bd-plan <context-file> "goal"        PLAN: Create epic/tasks from context
  bd-measure [task-id] [--json]        MEASURE: Run metrics for a task

Flags for bd-done:

  --force                     Skip measurement check and confirmation
  --no-measure                Skip measurements but still confirm

Configuration:

  BD_WORKTREE_ROOT            Root directory for worktrees (default: ~/worktrees)
                              Set with: export BD_WORKTREE_ROOT=/path/to/worktrees

=== Worktree Workflow ===

  1. bd-work <id>     → Validates task, creates worktree, claims task
  2. ... code ...     → Work in isolated directory
  3. bd-pause         → Commit+push WIP (optional, for multi-machine)
  4. bd-done          → Run measurements, close task, push, create PR
  5. bd-cleanup...    → Remove worktree after PR merged

=== GPBM Workflow ===

  1. bd-gather "goal"          → Query Eco, requirements, bd for context
  2. bd-plan context.md "goal" → Create epic with tasks + approval gate
  3. (Human approves)          → Close approval task to unblock
  4. bd-work <task-id>         → Work on individual tasks
  5. bd-done                   → Auto-runs bd-measure, closes task

GPBM Examples:

  # Start a new development cycle
  bd-gather "Add thermal protection to firmware" architect firmware
  
  # Review context, then create plan
  bd-plan /tmp/gather_context.md "Add thermal protection"
  
  # Work on tasks
  bd-work temper-xxx.1
  
  # Manually run measurements
  bd-measure

Multi-machine sync:

  - bd-pause on machine A pushes WIP commits
  - bd-work <id> on machine B pulls latest changes
  - Both machines work on same task seamlessly

GPBM Integration Notes:

  - All bd commands use --sandbox flag (prevents daemon conflicts)
  - Task ID extracted from git branch (works from any subdirectory)
  - Task validation before worktree creation (prevents orphan worktrees)
  - Measurement integration in bd-done (if task has measurement_targets)

EOF
}

# Auto-complete setup for Bash
if [[ -n "$BASH_VERSION" ]]; then
    _bd_work_complete() {
        local cur="${COMP_WORDS[COMP_CWORD]}"
        local tasks
        tasks=$(bd --sandbox list --status open --json 2>/dev/null | grep -o '"id":"[^"]*"' | cut -d'"' -f4 || echo "")
        COMPREPLY=($(compgen -W "$tasks" -- "$cur"))
    }
    complete -F _bd_work_complete bd-work
fi

# Auto-complete setup for Zsh
if [[ -n "$ZSH_VERSION" ]]; then
    _bd_work_complete() {
        local tasks
        tasks=(${(f)"$(bd --sandbox list --status open --json 2>/dev/null | grep -o '"id":"[^"]*"' | cut -d'"' -f4)"})
        _describe 'task' tasks
    }
    compdef _bd_work_complete bd-work
    
    _bd_done_complete() {
        _arguments \
            '--force[Skip measurement check]' \
            '--no-measure[Skip measurements but confirm]' \
            '*:reason:'
    }
    compdef _bd_done_complete bd-done
    
    _bd_gather_complete() {
        _arguments \
            '1:goal:' \
            '2:role:(architect coder tester human)' \
            '3:domain:(firmware placer pcb)'
    }
    compdef _bd_gather_complete bd-gather
    
    _bd_measure_complete() {
        local tasks
        tasks=(${(f)"$(bd --sandbox list --status in_progress --json 2>/dev/null | grep -o '"id":"[^"]*"' | cut -d'"' -f4)"})
        _arguments \
            '--json[Output as JSON]' \
            '1:task:($tasks)'
    }
    compdef _bd_measure_complete bd-measure
    
    _bd_plan_complete() {
        _arguments \
            '1:context:_files -g "*.md"' \
            '2:goal:' \
            '3:role:(architect coder tester)'
    }
    compdef _bd_plan_complete bd-plan
fi 2>/dev/null  # Suppress compdef errors when sourced in bash

# =============================================================================
# GPBM Workflow Commands
# =============================================================================

# Run GATHER phase - collect context for a goal
bd-gather() {
    local goal="$1"
    local role="${2:-architect}"
    local domain="${3:-}"
    local output_file="/tmp/gather_context_$(date +%s).md"
    
    if [[ -z "$goal" ]]; then
        echo "Usage: bd-gather \"goal description\" [role] [domain]"
        echo ""
        echo "Arguments:"
        echo "  goal    - What you're trying to accomplish"
        echo "  role    - Agent role: architect, coder, tester (default: architect)"
        echo "  domain  - Project domain: firmware, placer, pcb (optional)"
        echo ""
        echo "Examples:"
        echo "  bd-gather \"Add thermal protection to firmware\""
        echo "  bd-gather \"Implement boundary loss\" architect placer"
        echo "  bd-gather \"Fix PID oscillation\" coder firmware"
        return 1
    fi
    
    # Check if gather.py exists
    local script_dir
    script_dir=$(git rev-parse --show-toplevel 2>/dev/null)/tools/gpbm/gather.py
    
    if [[ ! -f "$script_dir" ]]; then
        echo "Error: tools/gpbm/gather.py not found"
        echo "       Are you in the temper repository?"
        return 1
    fi
    
    echo "=== GATHER Phase ==="
    echo "Goal: $goal"
    echo "Role: $role"
    [[ -n "$domain" ]] && echo "Domain: $domain"
    echo ""
    
    # Build command
    local cmd="python3 \"$script_dir\" --goal \"$goal\" --role \"$role\" --output \"$output_file\""
    [[ -n "$domain" ]] && cmd="$cmd --domain \"$domain\""
    
    # Run gather
    if eval "$cmd"; then
        echo ""
        echo "=== Context gathered to: $output_file ==="
        echo ""
        
        # Show summary
        if [[ -f "$output_file" ]]; then
            echo "Preview (first 50 lines):"
            head -50 "$output_file"
            echo ""
            echo "..."
            echo ""
            echo "Full context: $output_file"
            echo ""
            echo "Next steps:"
            echo "  1. Review the context file"
            echo "  2. Run: bd-plan \"$output_file\" \"$goal\""
        fi
    else
        echo "Error: GATHER phase failed"
        return 1
    fi
}

# Run MEASURE phase - collect metrics for current task
bd-measure() {
    local task_id="${1:-}"
    local json_flag=""
    
    # Parse flags
    while [[ "$1" == --* ]]; do
        case "$1" in
            --json)
                json_flag="--json"
                shift
                ;;
            *)
                shift
                ;;
        esac
    done
    
    # Get task ID from arg or branch
    if [[ -z "$task_id" || "$task_id" == --* ]]; then
        task_id=$(_bd_get_task_id)
    fi
    
    if [[ -z "$task_id" ]]; then
        local current_branch
        current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
        
        echo "Error: Not in a task branch (current branch: $current_branch)"
        echo ""
        echo "Either:"
        echo "  1. Specify a task ID:    bd-measure temper-xxx"
        echo "  2. Switch to a worktree: bd-work temper-xxx"
        echo ""
        echo "To list available tasks: bd ready"
        return 1
    fi
    
    # Check if measure.py exists
    local script_dir
    script_dir=$(git rev-parse --show-toplevel 2>/dev/null)/tools/gpbm/measure.py
    
    if [[ ! -f "$script_dir" ]]; then
        echo "Error: tools/gpbm/measure.py not found"
        echo "       Are you in the temper repository?"
        return 1
    fi
    
    echo "=== MEASURE Phase ==="
    echo "Task: $task_id"
    echo ""
    
    # Run measurements
    python3 "$script_dir" --task "$task_id" $json_flag
    local result=$?
    
    if [[ $result -eq 0 ]]; then
        echo ""
        echo "=== Measurements Complete ==="
    else
        echo ""
        echo "=== Some Measurements Failed ==="
        return $result
    fi
}

# Run PLAN phase - create epic and tasks from context
bd-plan() {
    local context_file="$1"
    local goal="$2"
    local role="${3:-architect}"
    
    if [[ -z "$context_file" || -z "$goal" ]]; then
        echo "Usage: bd-plan <context-file> \"goal\" [role]"
        echo ""
        echo "Arguments:"
        echo "  context-file - Output from bd-gather (markdown file)"
        echo "  goal         - Epic goal/title"
        echo "  role         - Agent role (default: architect)"
        echo ""
        echo "Example:"
        echo "  bd-plan /tmp/gather_context.md \"Add thermal protection\""
        return 1
    fi
    
    if [[ ! -f "$context_file" ]]; then
        echo "Error: Context file not found: $context_file"
        return 1
    fi
    
    # Check if plan.py exists
    local script_dir
    script_dir=$(git rev-parse --show-toplevel 2>/dev/null)/tools/gpbm/plan.py
    
    if [[ ! -f "$script_dir" ]]; then
        echo "Error: tools/gpbm/plan.py not found"
        echo "       Are you in the temper repository?"
        return 1
    fi
    
    echo "=== PLAN Phase ==="
    echo "Context: $context_file"
    echo "Goal: $goal"
    echo "Role: $role"
    echo ""
    
    # Run planning
    python3 "$script_dir" --context "$context_file" --goal "$goal" --role "$role"
    local result=$?
    
    if [[ $result -eq 0 ]]; then
        echo ""
        echo "=== Planning Complete ==="
        echo ""
        echo "Next steps:"
        echo "  1. Review created epic with: bd show <epic-id>"
        echo "  2. Human approves scope (close approval task)"
        echo "  3. Start work with: bd-work <task-id>"
    else
        echo ""
        echo "=== Planning Failed ==="
        return $result
    fi
}

echo "bd worktree helpers loaded. Run 'bd-worktree-help' for usage."

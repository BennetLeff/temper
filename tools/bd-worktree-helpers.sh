#!/usr/bin/env bash
# Git Worktree Helper Functions for bd Task Isolation
# Source this file in your shell: source tools/bd-worktree-helpers.sh

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
    
    local project
    project=$(_bd_get_project_name)
    local worktree_dir="$BD_WORKTREE_ROOT/$project/$task_id"
    
    # Create worktree parent if needed
    mkdir -p "$BD_WORKTREE_ROOT/$project"
    
    if [[ -d "$worktree_dir" ]]; then
        # Resume existing worktree
        echo "Resuming existing worktree for $task_id"
        cd "$worktree_dir" || return 1
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
        git push -u origin "$task_id"
    fi
    
    # Claim the task in bd
    echo "Claiming task $task_id"
    bd update "$task_id" --status in_progress
    
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
    
    local task_id
    task_id=$(basename "$(pwd)")
    
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
        echo "Warning: Push failed - you may need to pull first"
        return 1
    }
    
    # Sync bd state
    echo "Syncing bd state..."
    bd sync
    
    echo ""
    echo "✓ Work paused and synced for $task_id"
    echo "  Resume on any machine with: bd-work $task_id"
}

# Complete task (close in bd, remind about PR)
bd-done() {
    local task_id
    task_id=$(basename "$(pwd)")
    local reason="${1:-Completed}"
    
    # Ensure we're in a git repo
    if ! git rev-parse --git-dir &>/dev/null; then
        echo "Error: Not in a git repository"
        return 1
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
        echo "Warning: Push failed - you may need to pull first"
        return 1
    }
    
    # Close in bd
    echo "Closing task in bd..."
    bd close "$task_id" --reason "$reason"
    bd sync
    
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
        
        # Check if task is closed in bd
        local status
        status=$(bd show "$task_id" --json 2>/dev/null | grep -o '"Status":"[^"]*"' | cut -d'"' -f4)
        
        if [[ "$status" != "Closed" ]]; then
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
        
        # Get bd status
        local status
        status=$(bd show "$task_id" --json 2>/dev/null | grep -o '"Status":"[^"]*"' | cut -d'"' -f4 || echo "Unknown")
        
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

Available commands:

  bd-work <task-id>           Start work on a task (creates/resumes worktree)
  bd-pause                    Pause work (commit WIP and push for multi-machine sync)
  bd-done [reason]            Complete task (close in bd, remind about PR)
  bd-cleanup-worktrees        Remove worktrees for closed+merged tasks
  bd-worktrees                List active worktrees with status
  bd-worktree-help            Show this help message

Configuration:

  BD_WORKTREE_ROOT            Root directory for worktrees (default: ~/worktrees)
                              Set with: export BD_WORKTREE_ROOT=/path/to/worktrees

Examples:

  # Start work on a task
  bd-work bd-123

  # Pause before switching machines
  bd-pause

  # Complete the task
  bd-done "Implemented feature X"

  # Periodic cleanup
  bd-cleanup-worktrees

Workflow:

  1. bd-work <id>     → Creates worktree, claims task
  2. ... code ...     → Work in isolated directory
  3. bd-pause         → Commit+push WIP (optional, for multi-machine)
  4. bd-done          → Close task, push, create PR
  5. bd-cleanup...    → Remove worktree after PR merged

Multi-machine sync:

  - bd-pause on machine A pushes WIP commits
  - bd-work <id> on machine B pulls latest changes
  - Both machines work on same task seamlessly

EOF
}

# Auto-complete setup (optional, for bash)
if [[ -n "$BASH_VERSION" ]]; then
    _bd_work_complete() {
        local cur="${COMP_WORDS[COMP_CWORD]}"
        local tasks
        tasks=$(bd list --status open --json 2>/dev/null | grep -o '"ID":"[^"]*"' | cut -d'"' -f4 || echo "")
        COMPREPLY=($(compgen -W "$tasks" -- "$cur"))
    }
    complete -F _bd_work_complete bd-work
fi

echo "bd worktree helpers loaded. Run 'bd-worktree-help' for usage."

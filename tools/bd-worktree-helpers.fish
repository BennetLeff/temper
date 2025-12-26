#!/usr/bin/env fish
# Git Worktree Helper Functions for bd Task Isolation (Fish Shell)
#
# Usage: source tools/bd-worktree-helpers.fish

# Configuration
set -gx BD_WORKTREE_ROOT (test -n "$BD_WORKTREE_ROOT"; and echo $BD_WORKTREE_ROOT; or echo "$HOME/worktrees")

# Source multi-agent utilities
set -l script_dir (dirname (status filename))
if test -f "$script_dir/bd-multiagent.fish"
    source "$script_dir/bd-multiagent.fish"
    set -g _BD_MULTIAGENT_ENABLED true
else
    set -g _BD_MULTIAGENT_ENABLED false
end

# Get project name from git remote
function _bd_get_project_name
    set -l remote_url (git remote get-url origin 2>/dev/null)
    if test -z "$remote_url"
        basename (git rev-parse --show-toplevel 2>/dev/null; or pwd)
    else
        basename $remote_url .git
    end
end

# Get task ID from current git branch
function _bd_get_task_id
    set -l branch (git rev-parse --abbrev-ref HEAD 2>/dev/null)
    
    if test -z "$branch"; or test "$branch" = "HEAD"; or test "$branch" = "main"; or test "$branch" = "master"
        return 1
    end
    
    echo $branch
end

# Validate task exists in bd
function _bd_validate_task
    set -l task_id $argv[1]
    bd --sandbox show $task_id --json &>/dev/null
end

# Check if hooks are installed
function _bd_hooks_installed
    set -l repo_root (git rev-parse --show-toplevel 2>/dev/null)
    if test -z "$repo_root"
        return 1
    end
    
    if test -f "$repo_root/.git/hooks/pre-push"
        grep -q "bd-multiagent\|_bd_prepush_check" "$repo_root/.git/hooks/pre-push" 2>/dev/null
        return $status
    end
    
    return 1
end

# Start work on a bd task
function bd-work
    set -l task_id $argv[1]
    
    if test -z "$task_id"
        echo "Usage: bd-work <task-id>"
        echo "Example: bd-work bd-123"
        return 1
    end
    
    # Ensure we're in a git repo
    if not git rev-parse --git-dir &>/dev/null
        echo "Error: Not in a git repository"
        return 1
    end
    
    # Check if hooks are installed
    if test "$_BD_MULTIAGENT_ENABLED" = "true"; and not _bd_hooks_installed
        echo ""
        echo "⚠ Multi-agent hooks not installed."
        echo "  Hooks prevent conflicts when multiple agents work simultaneously."
        echo ""
        read -P "  Install multi-agent hooks now? [Y/n] " confirm
        if test "$confirm" != "n"; and test "$confirm" != "N"
            set -l script_dir (dirname (status filename))
            set -l hook_installer "$script_dir/git-hooks/install-multiagent.sh"
            if test -f "$hook_installer"
                if bash "$hook_installer"
                    echo "  ✓ Hooks installed"
                else
                    echo "  ⚠ Hook installation failed (continuing anyway)"
                end
            end
        end
        echo ""
    end
    
    # Validate task exists
    echo "Validating task $task_id..."
    if not _bd_validate_task $task_id
        echo "Error: Task '$task_id' not found in bd"
        return 1
    end
    
    # Multi-agent claim check
    if test "$_BD_MULTIAGENT_ENABLED" = "true"; and _bd_is_issue_branch $task_id
        echo "Checking claim status..."
        git fetch origin $task_id 2>/dev/null; or true
        
        set -l output (_bd_check_claim_status $task_id)
        set -l status (echo $output | string match -r 'status=(\w+)' | tail -1)
        set -l owner (echo $output | string match -r 'owner=(\S+)' | tail -1)
        set -l stale (echo $output | string match -r 'stale=(\w+)' | tail -1)
        
        switch $status
            case claimed
                if test "$stale" = "true"
                    echo ""
                    echo "Issue $task_id was claimed by $owner (STALE)"
                    if test "$BEADS_AUTO_TAKEOVER" = "true"
                        echo "Auto-takeover enabled, proceeding..."
                    else
                        read -P "Take over this stale claim? [y/N] " confirm
                        if test "$confirm" != "y"; and test "$confirm" != "Y"
                            echo "Aborted."
                            return 1
                        end
                    end
                else
                    echo ""
                    echo "Issue $task_id is claimed by $owner (active)"
                    echo ""
                    echo "Options:"
                    echo "  1. Pick a different issue: bd ready"
                    echo "  2. Wait for $owner to finish"
                    echo "  3. Force takeover: bd-takeover $task_id --force"
                    return 1
                end
            case mine
                echo "You already own this issue."
            case unclaimed
                echo "Issue is unclaimed, proceeding..."
        end
    end
    
    set -l project (_bd_get_project_name)
    set -l worktree_dir "$BD_WORKTREE_ROOT/$project/$task_id"
    
    # Create worktree parent if needed
    mkdir -p "$BD_WORKTREE_ROOT/$project"
    
    if test -d "$worktree_dir"
        echo "Resuming existing worktree for $task_id"
        cd $worktree_dir
        
        if git rev-parse --verify "origin/$task_id" &>/dev/null
            echo "Pulling latest changes..."
            git pull --rebase; or echo "Warning: Pull failed"
        end
    else if git show-ref --verify --quiet "refs/remotes/origin/$task_id"
        echo "Creating worktree from remote branch origin/$task_id"
        git worktree add $worktree_dir $task_id
        cd $worktree_dir
        git branch --set-upstream-to="origin/$task_id" $task_id
    else
        echo "Creating new worktree for $task_id from main"
        git fetch origin main:main 2>/dev/null; or true
        git worktree add $worktree_dir -b $task_id
        cd $worktree_dir
        
        # Push branch immediately - THIS IS THE ATOMIC CLAIM
        # If another agent already pushed this branch, we'll fail here
        echo "Claiming branch (atomic push)..."
        if not git push -u origin $task_id 2>/dev/null
            echo ""
            echo "✗ Failed to claim $task_id - another agent may have claimed it first"
            echo ""
            echo "Cleaning up worktree..."
            cd -
            git worktree remove $worktree_dir --force 2>/dev/null
            git branch -D $task_id 2>/dev/null
            echo ""
            echo "Options:"
            echo "  1. Check who has it: bd-claim-status $task_id"
            echo "  2. Pick different work: bd ready"
            echo "  3. If stale, takeover: bd-takeover $task_id"
            return 1
        end
        echo "✓ Branch claimed successfully"
    end
    
    # Only update bd status AFTER successful git push (the atomic lock)
    echo "Updating task status in bd..."
    bd --sandbox update $task_id --status in_progress
    
    echo ""
    echo "✓ Now working on $task_id in $worktree_dir"
    echo "  Run 'bd-pause' before switching machines"
    echo "  Run 'bd-done' when complete"
end

# Pause work
function bd-pause
    if not git rev-parse --git-dir &>/dev/null
        echo "Error: Not in a git repository"
        return 1
    end
    
    set -l task_id (_bd_get_task_id)
    if test -z "$task_id"
        echo "Error: Not in a task branch"
        return 1
    end
    
    if not git diff --quiet; or not git diff --cached --quiet
        git add -A
        git commit -m "WIP: progress on $task_id"; or echo "Warning: Commit failed"
    else
        echo "No changes to commit"
    end
    
    echo "Pushing to remote..."
    if not git push
        echo "Push failed. Try: git pull --rebase && git push"
        return 1
    end
    
    echo "Syncing bd state..."
    bd --sandbox sync
    
    echo ""
    echo "✓ Work paused and synced for $task_id"
end

# Complete task
function bd-done
    set -l reason "Completed"
    set -l force_flag ""
    
    # Parse args
    for arg in $argv
        switch $arg
            case --force
                set force_flag "1"
            case '--*'
                # skip other flags
            case '*'
                set reason $arg
        end
    end
    
    if not git rev-parse --git-dir &>/dev/null
        echo "Error: Not in a git repository"
        return 1
    end
    
    set -l task_id (_bd_get_task_id)
    if test -z "$task_id"
        echo "Error: Not in a task branch"
        return 1
    end
    
    # Final commit if needed
    if not git diff --quiet; or not git diff --cached --quiet
        echo "Committing final changes..."
        git add -A
        git commit -m "feat: complete $task_id"; or true
    end
    
    echo "Pushing to remote..."
    if not git push
        echo "Push failed. Try: git pull --rebase && git push"
        return 1
    end
    
    echo "Closing task in bd..."
    bd --sandbox close $task_id --reason "$reason"
    bd --sandbox sync
    
    # Auto-create PR if enabled
    set -l pr_url ""
    if test "$BEADS_AUTO_PR" = "true"; and command -q gh
        echo "Creating pull request..."
        set pr_url (gh pr create --fill 2>&1)
        if test $status -eq 0
            echo "  ✓ PR created: $pr_url"
        else
            echo "  ⚠ PR creation failed: $pr_url"
            set pr_url ""
        end
    end
    
    echo ""
    echo "✓ Task $task_id marked as complete"
    echo ""
    echo "Next steps:"
    if test -n "$pr_url"
        echo "  1. PR created: $pr_url"
        echo "  2. After PR merged: bd-cleanup-worktrees"
    else if command -q gh
        echo "  1. Create PR: gh pr create --fill"
        echo "  2. After PR merged: bd-cleanup-worktrees"
        echo ""
        echo "  Tip: Set BEADS_AUTO_PR=true for automatic PR creation"
    else
        echo "  1. Create PR manually"
        echo "  2. After PR merged: bd-cleanup-worktrees"
    end
end

# List worktrees
function bd-worktrees
    set -l project (_bd_get_project_name)
    set -l worktree_root "$BD_WORKTREE_ROOT/$project"
    
    if not test -d "$worktree_root"
        echo "No worktrees found for project $project"
        return 0
    end
    
    echo "Active worktrees for $project:"
    echo ""
    
    for worktree_dir in $worktree_root/*
        if not test -d "$worktree_dir"
            continue
        end
        
        set -l task_id (basename $worktree_dir)
        set -l status (bd --sandbox show $task_id --json 2>/dev/null | string match -r '"status":"([^"]*)"' | tail -1; or echo "unknown")
        set -l last_commit (cd $worktree_dir; and git log -1 --format="%cr" 2>/dev/null; or echo "unknown")
        
        echo "  $task_id [$status] - last commit: $last_commit"
        echo "    → $worktree_dir"
    end
end

# Cleanup worktrees
function bd-cleanup-worktrees
    set -l project (_bd_get_project_name)
    set -l worktree_root "$BD_WORKTREE_ROOT/$project"
    
    if not test -d "$worktree_root"
        echo "No worktrees found"
        return 0
    end
    
    echo "Checking for worktrees to cleanup..."
    set -l cleaned 0
    set -l main_repo (git rev-parse --show-toplevel)
    
    for worktree_dir in $worktree_root/*
        if not test -d "$worktree_dir"
            continue
        end
        
        set -l task_id (basename $worktree_dir)
        set -l status (bd --sandbox show $task_id --json 2>/dev/null | string match -r '"status":"([^"]*)"' | tail -1)
        
        if test "$status" != "closed"
            continue
        end
        
        cd $main_repo
        git fetch origin --prune
        
        if git branch -r --merged origin/main | grep -q "origin/$task_id"
            echo "✓ Cleaning up $task_id (closed + merged)"
            git worktree remove $worktree_dir --force 2>/dev/null; or begin
                rm -rf $worktree_dir
                git worktree prune
            end
            git branch -d $task_id 2>/dev/null; or true
            git push origin --delete $task_id 2>/dev/null; or true
            set cleaned (math $cleaned + 1)
        else
            echo "⊗ Skipping $task_id (not merged)"
        end
    end
    
    echo ""
    if test $cleaned -gt 0
        echo "✓ Cleaned up $cleaned worktree(s)"
    else
        echo "No worktrees ready for cleanup"
    end
end

function bd-worktree-help
    echo "Git Worktree Helpers (Fish Shell)"
    echo "================================="
    echo ""
    echo "Worktree Commands:"
    echo "  bd-work <task-id>       Start work on a task"
    echo "  bd-pause                Pause work (commit + push WIP)"
    echo "  bd-done [reason]        Complete task"
    echo "  bd-worktrees            List active worktrees"
    echo "  bd-cleanup-worktrees    Remove merged worktrees"
    echo ""
    echo "Multi-Agent Commands:"
    echo "  bd-claims               List active claims"
    echo "  bd-claim-status <id>    Check claim status"
    echo "  bd-takeover <id>        Take over stale claim"
    echo ""
    echo "Configuration:"
    echo "  BD_WORKTREE_ROOT        Worktree location (current: $BD_WORKTREE_ROOT)"
    echo "  BEADS_AGENT_ID          Your agent ID (current: $BEADS_AGENT_ID)"
    echo "  BEADS_AUTO_PR           Auto-create PR (current: $BEADS_AUTO_PR)"
end

echo "bd worktree helpers loaded (Fish). Run 'bd-worktree-help' for usage."

# ==============================================================================
# Setup Validation and Status
# ==============================================================================

function bd-validate-setup
    echo "Validating temper bd setup..."
    echo ""
    set -l errors 0

    # Check shell helpers
    if functions -q bd-work
        echo "✓ Worktree helpers: loaded"
    else
        echo "✗ Worktree helpers: NOT LOADED"
        set errors (math $errors + 1)
    end

    # Check hooks
    if _bd_hooks_installed
        echo "✓ Git hooks: installed"
    else
        echo "✗ Git hooks: NOT INSTALLED"
        echo "  Run: bash tools/git-hooks/install-multiagent.sh"
        set errors (math $errors + 1)
    end

    # Check agent ID
    if test -n "$BEADS_AGENT_ID"
        echo "✓ Agent ID: $BEADS_AGENT_ID"
    else
        echo "✗ BEADS_AGENT_ID: NOT SET"
        echo "  Run: set -g BEADS_AGENT_ID your-name"
        set errors (math $errors + 1)
    end

    # Check worktree root
    echo "✓ Worktree root: $BD_WORKTREE_ROOT"

    echo ""
    if test $errors -eq 0
        echo "Setup validation: PASSED"
        return 0
    else
        echo "Setup validation: $errors ERROR(S)"
        return 1
    end
end

function bd-status
    echo ""
    echo "temper bd Workflow Status"
    echo "========================="
    echo ""

    # Shell helpers
    if functions -q bd-work
        echo "✓ Shell helpers: loaded"
    else
        echo "✗ Shell helpers: NOT LOADED"
    end

    # Hooks
    if _bd_hooks_installed
        echo "✓ Git hooks: installed"
    else
        echo "✗ Git hooks: NOT INSTALLED"
    end

    # Agent ID
    if test -n "$BEADS_AGENT_ID"
        echo "✓ Agent ID: $BEADS_AGENT_ID"
    else
        echo "✗ Agent ID: NOT SET"
    end

    # Worktree root
    echo "  Worktree root: $BD_WORKTREE_ROOT"

    # Active worktrees
    echo ""
    echo "  Active worktrees:"
    set -l project (_bd_get_project_name)
    set -l worktree_root "$BD_WORKTREE_ROOT/$project"
    if test -d "$worktree_root"
        for wt in $worktree_root/*
            if test -d "$wt"
                set -l task_id (basename $wt)
                echo "    - $task_id"
            end
        end
    else
        echo "    (none)"
    end

    echo ""
    echo "  Quick commands:"
    echo "    bd ready              # Find unblocked work"
    echo "    bd-work <id>          # Start work"
    echo "    bd-done               # Complete task"
    echo "    bd-claims             # See active claims"
    echo "    bd-validate-setup     # Verify setup"
end

# Generate shell config block
function bd-generate-config
    set -l shell (string split -m1 -f2 (string match -r 'SHELL=.*' (set))) 2>/dev/null
    or set -l shell "fish"

    set -l config_block "# temper bd workflow - generated by bd-setup.sh
# DO NOT EDIT MANUALLY - rerun bd-setup.sh to regenerate

set -g BEADS_AGENT_ID \"$USER\"
set -g BD_WORKTREE_ROOT \"\$HOME/worktrees\"
set -g BEADS_STALE_MINUTES 30
set -g BEADS_AUTO_TAKEOVER false
set -g BEADS_AUTO_PR false

source (git rev-parse --show-toplevel 2>/dev/null)/tools/bd-worktree-helpers.fish"

    echo $config_block
end

# Install config to shell rc
function bd-install-config
    set -l config_block (bd-generate-config)
    set -l config_file "$HOME/.config/fish/config.fish"

    if test -f "$config_file"
        if grep -q "temper bd workflow" "$config_file"
            echo "temper bd workflow already configured in $config_file"
            return 0
        end
    end

    echo "" >> "$config_file"
    echo $config_block >> "$config_file"
    echo "✓ Added bd config to $config_file"
    echo ""
    echo "Restart Fish or run: source $config_file"
end

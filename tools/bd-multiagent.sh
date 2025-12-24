#!/usr/bin/env bash
# Multi-Agent Coordination Utilities for Beads
#
# This file provides shared functions for multi-agent coordination.
# Used by git hooks and bd-worktree-helpers.sh
#
# Coordination Model: Branch-as-Lock with Commit-Based Identity
# - Remote branch existence = atomic claim
# - First commit on branch tags the agent
# - Commit timestamps determine staleness
#
# Environment Variables:
#   BEADS_AGENT_ID        - Agent identifier (default: $USER)
#   BEADS_STALE_MINUTES   - Minutes before a claim is considered stale (default: 30)
#   BEADS_ISSUE_PATTERN   - Regex pattern for issue branches (default: ^(temper-|bd-))
#   BEADS_AUTO_TAKEOVER   - Auto-takeover stale claims without prompting (default: false)
#
# Usage:
#   source tools/bd-multiagent.sh

# ==============================================================================
# Configuration
# ==============================================================================

BEADS_STALE_MINUTES="${BEADS_STALE_MINUTES:-30}"
BEADS_ISSUE_PATTERN="${BEADS_ISSUE_PATTERN:-^(temper-|bd-)}"
BEADS_AUTO_TAKEOVER="${BEADS_AUTO_TAKEOVER:-false}"
BEADS_AUTO_PR="${BEADS_AUTO_PR:-false}"

# ==============================================================================
# Agent ID Detection (CI/CD Aware)
# ==============================================================================

# Detect agent ID from environment with CI/CD fallbacks
# Priority: BEADS_AGENT_ID > CI env vars > USER > "agent"
_bd_detect_agent_id() {
    # 1. Explicit BEADS_AGENT_ID takes priority
    if [[ -n "${BEADS_AGENT_ID:-}" ]]; then
        echo "$BEADS_AGENT_ID"
        return 0
    fi
    
    # 2. GitHub Actions
    if [[ -n "${GITHUB_ACTOR:-}" ]]; then
        echo "gh-${GITHUB_ACTOR}"
        return 0
    fi
    
    # 3. GitLab CI
    if [[ -n "${GITLAB_USER_LOGIN:-}" ]]; then
        echo "gl-${GITLAB_USER_LOGIN}"
        return 0
    fi
    if [[ -n "${CI_JOB_NAME:-}" ]]; then
        echo "gl-job-${CI_JOB_NAME}"
        return 0
    fi
    
    # 4. CircleCI
    if [[ -n "${CIRCLE_USERNAME:-}" ]]; then
        echo "circle-${CIRCLE_USERNAME}"
        return 0
    fi
    
    # 5. Jenkins
    if [[ -n "${BUILD_USER:-}" ]]; then
        echo "jenkins-${BUILD_USER}"
        return 0
    fi
    if [[ -n "${JOB_NAME:-}" ]]; then
        echo "jenkins-${JOB_NAME}"
        return 0
    fi
    
    # 6. Azure DevOps
    if [[ -n "${BUILD_REQUESTEDFOR:-}" ]]; then
        echo "azure-${BUILD_REQUESTEDFOR}"
        return 0
    fi
    
    # 7. Buildkite
    if [[ -n "${BUILDKITE_BUILD_CREATOR:-}" ]]; then
        echo "bk-${BUILDKITE_BUILD_CREATOR}"
        return 0
    fi
    
    # 8. Travis CI
    if [[ -n "${TRAVIS_REPO_SLUG:-}" ]]; then
        echo "travis-${TRAVIS_REPO_SLUG##*/}"
        return 0
    fi
    
    # 9. Generic CI detection (fallback)
    if [[ "${CI:-}" == "true" || -n "${CI_NAME:-}" ]]; then
        local ci_name="${CI_NAME:-ci}"
        echo "${ci_name}-agent"
        return 0
    fi
    
    # 10. Local user (default)
    if [[ -n "${USER:-}" ]]; then
        echo "$USER"
        return 0
    fi
    
    # 11. Final fallback
    echo "agent"
}

# Initialize agent ID using detection
BEADS_AGENT_ID="${BEADS_AGENT_ID:-$(_bd_detect_agent_id)}"

# ==============================================================================
# Core Utilities
# ==============================================================================

# Check if a branch name matches the issue pattern
# Usage: _bd_is_issue_branch "temper-123" && echo "yes"
_bd_is_issue_branch() {
    local branch="$1"
    [[ "$branch" =~ $BEADS_ISSUE_PATTERN ]]
}

# Get the current agent ID
# Usage: agent=$(_bd_get_agent_id)
_bd_get_agent_id() {
    echo "$BEADS_AGENT_ID"
}

# Extract agent ID from a commit message
# Looks for pattern: [agent: xxx] or (agent: xxx)
# Usage: agent=$(_bd_extract_agent_from_commit "abc123")
_bd_extract_agent_from_commit() {
    local commit="$1"
    local msg
    local agent_match
    msg=$(git log -1 --format=%B "$commit" 2>/dev/null)
    
    # Try [agent: xxx] pattern first using grep
    agent_match=$(echo "$msg" | grep -oE '\[agent:[[:space:]]*[^]]+\]' | head -1 | sed 's/\[agent:[[:space:]]*//' | sed 's/\]$//')
    if [[ -n "$agent_match" ]]; then
        echo "$agent_match"
        return 0
    fi
    
    # Try (agent: xxx) pattern
    agent_match=$(echo "$msg" | grep -oE '\(agent:[[:space:]]*[^)]+\)' | head -1 | sed 's/(agent:[[:space:]]*//' | sed 's/)$//')
    if [[ -n "$agent_match" ]]; then
        echo "$agent_match"
        return 0
    fi
    
    # Fallback: use commit author
    git log -1 --format=%an "$commit" 2>/dev/null
}

# Get the owner of a remote branch
# Usage: owner=$(_bd_get_branch_owner "origin/temper-123")
_bd_get_branch_owner() {
    local remote_branch="$1"
    
    if ! git rev-parse --verify "$remote_branch" &>/dev/null; then
        return 1
    fi
    
    _bd_extract_agent_from_commit "$remote_branch"
}

# Get the timestamp of the last commit on a branch (Unix epoch)
# Usage: ts=$(_bd_get_last_commit_time "origin/temper-123")
_bd_get_last_commit_time() {
    local branch="$1"
    git log -1 --format=%ct "$branch" 2>/dev/null
}

# Check if a branch is stale (no commits in BEADS_STALE_MINUTES)
# Usage: _bd_is_branch_stale "origin/temper-123" && echo "stale"
_bd_is_branch_stale() {
    local branch="$1"
    local last_commit_time
    local now
    local stale_seconds
    
    last_commit_time=$(_bd_get_last_commit_time "$branch")
    if [[ -z "$last_commit_time" ]]; then
        return 1  # Can't determine, assume not stale
    fi
    
    now=$(date +%s)
    stale_seconds=$((BEADS_STALE_MINUTES * 60))
    
    (( now - last_commit_time > stale_seconds ))
}

# Get human-readable time since last commit
# Usage: ago=$(_bd_time_since_commit "origin/temper-123")
_bd_time_since_commit() {
    local branch="$1"
    local last_commit_time
    local now
    local diff
    
    last_commit_time=$(_bd_get_last_commit_time "$branch")
    if [[ -z "$last_commit_time" ]]; then
        echo "unknown"
        return
    fi
    
    now=$(date +%s)
    diff=$((now - last_commit_time))
    
    if (( diff < 60 )); then
        echo "${diff}s ago"
    elif (( diff < 3600 )); then
        echo "$((diff / 60))m ago"
    elif (( diff < 86400 )); then
        echo "$((diff / 3600))h ago"
    else
        echo "$((diff / 86400))d ago"
    fi
}

# ==============================================================================
# Claim Checking
# ==============================================================================

# Check the claim status of an issue branch
# Returns JSON-like output for easy parsing
# Usage: status=$(_bd_check_claim_status "temper-123")
#        echo "$status" | grep "claimed_by"
_bd_check_claim_status() {
    local issue_id="$1"
    local remote_branch="origin/$issue_id"
    local my_agent
    local owner
    local is_stale
    local time_ago
    
    my_agent=$(_bd_get_agent_id)
    
    # Fetch latest (suppress output)
    git fetch origin "$issue_id" 2>/dev/null || true
    
    # Check if remote branch exists
    if ! git rev-parse --verify "$remote_branch" &>/dev/null; then
        echo "status=unclaimed"
        return 0
    fi
    
    owner=$(_bd_get_branch_owner "$remote_branch")
    time_ago=$(_bd_time_since_commit "$remote_branch")
    
    if _bd_is_branch_stale "$remote_branch"; then
        is_stale="true"
    else
        is_stale="false"
    fi
    
    if [[ "$owner" == "$my_agent" ]]; then
        echo "status=mine"
    else
        echo "status=claimed"
    fi
    echo "owner=$owner"
    echo "stale=$is_stale"
    echo "last_activity=$time_ago"
}

# Check if we can work on an issue (not claimed by another active agent)
# Returns 0 if we can work, 1 if blocked
# Usage: if _bd_can_claim "temper-123"; then echo "go ahead"; fi
_bd_can_claim() {
    local issue_id="$1"
    local status_output
    local status
    local owner
    local is_stale
    
    status_output=$(_bd_check_claim_status "$issue_id")
    
    status=$(echo "$status_output" | grep "^status=" | cut -d= -f2)
    owner=$(echo "$status_output" | grep "^owner=" | cut -d= -f2)
    is_stale=$(echo "$status_output" | grep "^stale=" | cut -d= -f2)
    
    case "$status" in
        unclaimed|mine)
            return 0
            ;;
        claimed)
            if [[ "$is_stale" == "true" ]]; then
                # Stale claim - can be taken over
                return 0
            else
                # Active claim by another agent
                return 1
            fi
            ;;
    esac
    
    return 1
}

# ==============================================================================
# User-Facing Functions
# ==============================================================================

# Display claim status for an issue with nice formatting
# Usage: bd-claim-status "temper-123"
bd-claim-status() {
    local issue_id="$1"
    local claim_output
    local claim_status
    local claim_owner
    local claim_stale
    local claim_activity
    
    if [[ -z "$issue_id" ]]; then
        echo "Usage: bd-claim-status <issue-id>"
        return 1
    fi
    
    claim_output=$(_bd_check_claim_status "$issue_id")
    
    claim_status=$(echo "$claim_output" | grep "^status=" | cut -d= -f2)
    claim_owner=$(echo "$claim_output" | grep "^owner=" | cut -d= -f2)
    claim_stale=$(echo "$claim_output" | grep "^stale=" | cut -d= -f2)
    claim_activity=$(echo "$claim_output" | grep "^last_activity=" | cut -d= -f2)
    
    echo "Issue: $issue_id"
    
    case "$claim_status" in
        unclaimed)
            echo "Status: Unclaimed (available)"
            ;;
        mine)
            echo "Status: Claimed by you ($claim_owner)"
            echo "Last activity: $claim_activity"
            ;;
        claimed)
            if [[ "$claim_stale" == "true" ]]; then
                echo "Status: STALE - claimed by $claim_owner"
                echo "Last activity: $claim_activity (>${BEADS_STALE_MINUTES}m ago)"
                echo "This claim can be taken over."
            else
                echo "Status: Active - claimed by $claim_owner"
                echo "Last activity: $claim_activity"
            fi
            ;;
    esac
}

# List all claimed issues (remote issue branches)
# Usage: bd-claims
bd-claims() {
    local my_agent
    local branch
    local issue_id
    local owner
    local time_ago
    local is_stale
    local status_indicator
    
    my_agent=$(_bd_get_agent_id)
    
    echo "Fetching remote branches..."
    git fetch origin --prune 2>/dev/null
    
    echo ""
    echo "Active Claims (branches matching: $BEADS_ISSUE_PATTERN)"
    echo "─────────────────────────────────────────────────────────"
    printf "%-20s %-15s %-12s %s\n" "ISSUE" "OWNER" "ACTIVITY" "STATUS"
    echo "─────────────────────────────────────────────────────────"
    
    local found=0
    while IFS= read -r branch; do
        [[ -z "$branch" ]] && continue
        
        # Extract issue ID from refs/remotes/origin/xxx
        issue_id="${branch##*/}"
        
        # Skip if not an issue branch
        _bd_is_issue_branch "$issue_id" || continue
        
        found=1
        owner=$(_bd_get_branch_owner "origin/$issue_id")
        time_ago=$(_bd_time_since_commit "origin/$issue_id")
        
        if _bd_is_branch_stale "origin/$issue_id"; then
            status_indicator="STALE"
        elif [[ "$owner" == "$my_agent" ]]; then
            status_indicator="(you)"
        else
            status_indicator="active"
        fi
        
        printf "%-20s %-15s %-12s %s\n" "$issue_id" "$owner" "$time_ago" "$status_indicator"
        
    done < <(git for-each-ref --format='%(refname)' refs/remotes/origin/)
    
    if [[ $found -eq 0 ]]; then
        echo "(no active claims)"
    fi
    
    echo ""
    echo "Your agent ID: $my_agent"
    echo "Stale threshold: ${BEADS_STALE_MINUTES} minutes"
}

# Take over a stale claim
# Usage: bd-takeover "temper-123" [--force]
bd-takeover() {
    local issue_id="$1"
    local force_flag="$2"
    local claim_output
    local claim_status
    local claim_owner
    local claim_stale
    local my_agent
    
    if [[ -z "$issue_id" ]]; then
        echo "Usage: bd-takeover <issue-id> [--force]"
        return 1
    fi
    
    my_agent=$(_bd_get_agent_id)
    claim_output=$(_bd_check_claim_status "$issue_id")
    
    claim_status=$(echo "$claim_output" | grep "^status=" | cut -d= -f2)
    claim_owner=$(echo "$claim_output" | grep "^owner=" | cut -d= -f2)
    claim_stale=$(echo "$claim_output" | grep "^stale=" | cut -d= -f2)
    
    case "$claim_status" in
        unclaimed)
            echo "Issue $issue_id is not claimed. Use 'bd-work $issue_id' to start."
            return 0
            ;;
        mine)
            echo "You already own $issue_id."
            return 0
            ;;
        claimed)
            if [[ "$claim_stale" != "true" && "$force_flag" != "--force" ]]; then
                echo "Issue $issue_id is actively claimed by $claim_owner."
                echo "Last activity: $(echo "$claim_output" | grep "^last_activity=" | cut -d= -f2)"
                echo ""
                echo "Cannot take over an active claim."
                echo "Wait until it becomes stale (>${BEADS_STALE_MINUTES}m) or use --force."
                return 1
            fi
            ;;
    esac
    
    # Confirm takeover
    if [[ "$force_flag" != "--force" && "$BEADS_AUTO_TAKEOVER" != "true" ]]; then
        echo "Taking over $issue_id from $claim_owner"
        echo "Their work will be preserved (you'll continue from their last commit)."
        echo ""
        read -p "Proceed? [y/N] " confirm
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            echo "Aborted."
            return 1
        fi
    fi
    
    echo "Taking over $issue_id..."
    
    # Fetch their branch
    git fetch origin "$issue_id"
    
    # Create local branch tracking remote (preserves their work)
    if git show-ref --verify --quiet "refs/heads/$issue_id"; then
        # Local branch exists - update it
        git checkout "$issue_id"
        git reset --hard "origin/$issue_id"
    else
        # Create new local branch from remote
        git checkout -b "$issue_id" "origin/$issue_id"
    fi
    
    # Make a takeover commit to mark new ownership
    git commit --allow-empty -m "chore: takeover from $claim_owner

[agent: $my_agent]
[takeover-from: $claim_owner]"
    
    # Push to claim
    if git push origin "$issue_id"; then
        echo ""
        echo "Taken over $issue_id from $claim_owner"
        echo "Their work has been preserved."
        echo ""
        echo "Next: Continue working or use 'bd-work $issue_id' to create a worktree."
    else
        echo "Failed to push takeover commit."
        return 1
    fi
}

# Show help for multi-agent commands
bd-multiagent-help() {
    cat <<'EOF'
Multi-Agent Coordination Commands
=================================

These commands help coordinate work between multiple agents using git branches
as atomic locks.

Commands:
---------
  bd-setup-multiagent      One-time setup for multi-agent coordination
  bd-claims                List all active claims (remote issue branches)
  bd-claim-status <id>     Check the claim status of a specific issue
  bd-takeover <id>         Take over a stale claim from another agent

Environment Variables:
----------------------
  BEADS_AGENT_ID         Your agent identifier (auto-detected from CI or $USER)
  BEADS_STALE_MINUTES    Minutes before a claim is stale (default: 30)
  BEADS_ISSUE_PATTERN    Regex for issue branches (default: ^(temper-|bd-))
  BEADS_AUTO_TAKEOVER    Auto-takeover without prompting (default: false)
  BEADS_AUTO_PR          Auto-create PR on bd-done (default: false)

How It Works:
-------------
1. When you run 'bd-work <issue-id>', it creates a branch and pushes to remote
2. The remote branch = your claim (atomic via git push)
3. Other agents see your branch and are blocked from working on the same issue
4. If you don't push for >30min, your claim becomes "stale" and can be taken over
5. Hooks enforce these rules automatically

CI/CD Detection:
----------------
Agent ID is automatically detected from CI environment variables:
  - GitHub Actions: GITHUB_ACTOR → gh-<user>
  - GitLab CI: GITLAB_USER_LOGIN or CI_JOB_NAME
  - CircleCI: CIRCLE_USERNAME
  - Jenkins: BUILD_USER or JOB_NAME
  - Azure DevOps: BUILD_REQUESTEDFOR
  - Buildkite: BUILDKITE_BUILD_CREATOR
  - Travis CI: TRAVIS_REPO_SLUG
  - Fallback: USER or "agent"

Examples:
---------
  # Initial setup
  bd-setup-multiagent

  # Check what's claimed
  bd-claims

  # Check a specific issue
  bd-claim-status temper-123

  # Take over a stale claim
  bd-takeover temper-123

  # Set your agent ID (add to ~/.bashrc)
  export BEADS_AGENT_ID="alice"

EOF
}

# Setup multi-agent coordination (one-time)
bd-setup-multiagent() {
    local install_hooks=true
    local add_to_shell=true
    local skip_prompts=false
    
    # Parse flags
    while [[ "$1" == --* ]]; do
        case "$1" in
            --no-hooks)
                install_hooks=false
                shift
                ;;
            --no-shell)
                add_to_shell=false
                shift
                ;;
            --yes|-y)
                skip_prompts=true
                shift
                ;;
            --help|-h)
                echo "Usage: bd-setup-multiagent [options]"
                echo ""
                echo "Options:"
                echo "  --no-hooks     Skip git hook installation"
                echo "  --no-shell     Skip shell configuration"
                echo "  --yes, -y      Skip confirmation prompts"
                echo "  --help, -h     Show this help"
                return 0
                ;;
            *)
                echo "Unknown option: $1"
                return 1
                ;;
        esac
    done
    
    echo "═══════════════════════════════════════════════════════════════"
    echo "  Multi-Agent Coordination Setup"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    
    # Check if we're in a git repo
    if ! git rev-parse --git-dir &>/dev/null; then
        echo "Error: Not in a git repository"
        return 1
    fi
    
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local repo_root
    repo_root="$(git rev-parse --show-toplevel)"
    
    # 1. Detect/configure agent ID
    echo "1. Agent ID Configuration"
    echo "   ─────────────────────────"
    
    local detected_id
    detected_id=$(_bd_detect_agent_id)
    echo "   Detected agent ID: $detected_id"
    
    if [[ -n "${GITHUB_ACTOR:-}" ]]; then
        echo "   Source: GitHub Actions (GITHUB_ACTOR)"
    elif [[ -n "${GITLAB_USER_LOGIN:-}" ]]; then
        echo "   Source: GitLab CI (GITLAB_USER_LOGIN)"
    elif [[ -n "${CI:-}" ]]; then
        echo "   Source: CI environment"
    else
        echo "   Source: Local user (\$USER)"
    fi
    
    if [[ "$skip_prompts" != "true" ]]; then
        echo ""
        read -p "   Use this agent ID? [Y/n] " confirm
        if [[ "$confirm" == "n" || "$confirm" == "N" ]]; then
            read -p "   Enter custom agent ID: " custom_id
            if [[ -n "$custom_id" ]]; then
                detected_id="$custom_id"
            fi
        fi
    fi
    
    BEADS_AGENT_ID="$detected_id"
    echo "   ✓ Agent ID set to: $BEADS_AGENT_ID"
    echo ""
    
    # 2. Install git hooks
    if [[ "$install_hooks" == "true" ]]; then
        echo "2. Git Hook Installation"
        echo "   ─────────────────────────"
        
        local hook_installer="$script_dir/git-hooks/install-multiagent.sh"
        
        if [[ -f "$hook_installer" ]]; then
            if [[ "$skip_prompts" != "true" ]]; then
                read -p "   Install multi-agent git hooks? [Y/n] " confirm
                if [[ "$confirm" == "n" || "$confirm" == "N" ]]; then
                    echo "   Skipped hook installation"
                    install_hooks=false
                fi
            fi
            
            if [[ "$install_hooks" == "true" ]]; then
                if bash "$hook_installer"; then
                    echo "   ✓ Git hooks installed"
                else
                    echo "   ✗ Hook installation failed"
                fi
            fi
        else
            echo "   ✗ Hook installer not found: $hook_installer"
            install_hooks=false
        fi
        echo ""
    else
        echo "2. Git Hook Installation"
        echo "   Skipped (--no-hooks)"
        echo ""
    fi
    
    # 3. Shell configuration
    if [[ "$add_to_shell" == "true" ]]; then
        echo "3. Shell Configuration"
        echo "   ─────────────────────────"
        
        local shell_rc=""
        if [[ -n "$ZSH_VERSION" || "$SHELL" == *"zsh"* ]]; then
            shell_rc="$HOME/.zshrc"
        elif [[ -n "$BASH_VERSION" || "$SHELL" == *"bash"* ]]; then
            shell_rc="$HOME/.bashrc"
        fi
        
        if [[ -n "$shell_rc" && -f "$shell_rc" ]]; then
            local config_block="# Beads Multi-Agent Configuration
export BEADS_AGENT_ID=\"$BEADS_AGENT_ID\"
source \"$script_dir/bd-worktree-helpers.sh\""
            
            # Check if already configured
            if grep -q "BEADS_AGENT_ID" "$shell_rc" 2>/dev/null; then
                echo "   Found existing BEADS_AGENT_ID in $shell_rc"
                if [[ "$skip_prompts" != "true" ]]; then
                    read -p "   Update configuration? [y/N] " confirm
                    if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
                        # Remove old config
                        sed -i.bak '/# Beads Multi-Agent/,/bd-worktree-helpers.sh/d' "$shell_rc" 2>/dev/null || true
                        echo "$config_block" >> "$shell_rc"
                        echo "   ✓ Updated $shell_rc"
                    else
                        echo "   Skipped shell configuration update"
                    fi
                fi
            else
                if [[ "$skip_prompts" != "true" ]]; then
                    echo ""
                    echo "   Will add to $shell_rc:"
                    echo "   ┌─────────────────────────────────────────────"
                    echo "$config_block" | sed 's/^/   │ /'
                    echo "   └─────────────────────────────────────────────"
                    echo ""
                    read -p "   Add to shell configuration? [Y/n] " confirm
                    if [[ "$confirm" == "n" || "$confirm" == "N" ]]; then
                        echo "   Skipped shell configuration"
                        add_to_shell=false
                    fi
                fi
                
                if [[ "$add_to_shell" == "true" ]]; then
                    echo "" >> "$shell_rc"
                    echo "$config_block" >> "$shell_rc"
                    echo "   ✓ Added to $shell_rc"
                fi
            fi
        else
            echo "   Could not detect shell RC file"
            echo "   Manually add to your shell config:"
            echo "     export BEADS_AGENT_ID=\"$BEADS_AGENT_ID\""
            echo "     source \"$script_dir/bd-worktree-helpers.sh\""
        fi
        echo ""
    else
        echo "3. Shell Configuration"
        echo "   Skipped (--no-shell)"
        echo ""
    fi
    
    # 4. Validation
    echo "4. Validation"
    echo "   ─────────────────────────"
    
    # Check hooks
    local hooks_ok=true
    for hook in pre-push post-checkout prepare-commit-msg; do
        if [[ -f "$repo_root/.git/hooks/$hook" ]]; then
            if grep -q "bd-multiagent" "$repo_root/.git/hooks/$hook" 2>/dev/null; then
                echo "   ✓ $hook hook installed"
            else
                echo "   ⚠ $hook hook exists but missing multi-agent integration"
                hooks_ok=false
            fi
        else
            echo "   ⚠ $hook hook not installed"
            hooks_ok=false
        fi
    done
    
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "  Setup Complete!"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "  Your agent ID: $BEADS_AGENT_ID"
    echo ""
    echo "  Quick start:"
    echo "    bd-claims               # See active claims"
    echo "    bd-work temper-xxx      # Start work (auto-claims)"
    echo "    bd-done                 # Complete and release claim"
    echo ""
    if [[ "$hooks_ok" != "true" ]]; then
        echo "  ⚠ Some hooks are missing. Run: $hook_installer"
        echo ""
    fi
    echo "  For help: bd-multiagent-help"
    echo ""
}

# Check if hooks are installed
_bd_hooks_installed() {
    local repo_root
    repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || return 1
    
    # Check for at least the pre-push hook with multi-agent content
    if [[ -f "$repo_root/.git/hooks/pre-push" ]]; then
        grep -q "bd-multiagent\|_bd_prepush_check" "$repo_root/.git/hooks/pre-push" 2>/dev/null
        return $?
    fi
    
    return 1
}

# ==============================================================================
# Hook Utilities (called by git hooks)
# ==============================================================================

# Pre-push check: verify we own the branch we're pushing to
# Returns 0 if push should proceed, 1 if blocked
# Usage (in pre-push hook): _bd_prepush_check || exit 1
_bd_prepush_check() {
    local branch
    local my_agent
    local status_output
    local status
    local owner
    local is_stale
    local last_activity
    
    branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
    
    # Skip non-issue branches
    if ! _bd_is_issue_branch "$branch"; then
        return 0
    fi
    
    my_agent=$(_bd_get_agent_id)
    
    # Fetch latest state of remote branch (silently)
    git fetch origin "$branch" 2>/dev/null || true
    
    # Check if remote branch exists
    if ! git rev-parse --verify "origin/$branch" &>/dev/null; then
        # No remote branch - this push will create it (claiming)
        return 0
    fi
    
    # Check if we have common ancestry with remote
    if git merge-base --is-ancestor "origin/$branch" HEAD 2>/dev/null; then
        # We're ahead of remote - normal push
        return 0
    fi
    
    if git merge-base --is-ancestor HEAD "origin/$branch" 2>/dev/null; then
        # Remote is ahead of us - we need to pull first
        echo "Remote branch has new commits. Pull first:"
        echo "  git pull --rebase origin $branch"
        return 1
    fi
    
    # Diverged - check ownership
    status_output=$(_bd_check_claim_status "$branch")
    owner=$(echo "$status_output" | grep "^owner=" | cut -d= -f2)
    is_stale=$(echo "$status_output" | grep "^stale=" | cut -d= -f2)
    last_activity=$(echo "$status_output" | grep "^last_activity=" | cut -d= -f2)
    
    if [[ "$owner" == "$my_agent" ]]; then
        # We own it but diverged - force push warning
        echo "Warning: Your local and remote branches have diverged."
        echo "You may need to force push: git push --force-with-lease"
        return 0
    fi
    
    # Someone else owns this branch
    if [[ "$is_stale" == "true" ]]; then
        echo "Branch $branch was claimed by $owner (STALE: $last_activity)"
        echo "Use 'bd-takeover $branch' to take over, then push."
    else
        echo "Branch $branch is claimed by $owner (active: $last_activity)"
        echo ""
        echo "You cannot push to a branch owned by another agent."
        echo "Options:"
        echo "  1. Work on a different issue: bd ready"
        echo "  2. Wait for $owner to finish"
        echo "  3. Force takeover (if stuck): bd-takeover $branch --force"
    fi
    
    return 1
}

# Post-checkout notification: warn if checking out a claimed branch
# Usage (in post-checkout hook): _bd_postcheckout_notify
_bd_postcheckout_notify() {
    local branch
    local my_agent
    local status_output
    local status
    local owner
    local is_stale
    local last_activity
    
    branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
    
    # Skip non-issue branches
    if ! _bd_is_issue_branch "$branch"; then
        return 0
    fi
    
    my_agent=$(_bd_get_agent_id)
    status_output=$(_bd_check_claim_status "$branch")
    status=$(echo "$status_output" | grep "^status=" | cut -d= -f2)
    owner=$(echo "$status_output" | grep "^owner=" | cut -d= -f2)
    is_stale=$(echo "$status_output" | grep "^stale=" | cut -d= -f2)
    last_activity=$(echo "$status_output" | grep "^last_activity=" | cut -d= -f2)
    
    case "$status" in
        mine)
            # Our branch, all good
            ;;
        unclaimed)
            echo ""
            echo "Note: Branch $branch is not yet claimed."
            echo "Push to claim it: git push -u origin $branch"
            ;;
        claimed)
            echo ""
            if [[ "$is_stale" == "true" ]]; then
                echo "Warning: Branch $branch was claimed by $owner (STALE: $last_activity)"
                echo "You can take it over: bd-takeover $branch"
            else
                echo "Warning: Branch $branch is claimed by $owner (active: $last_activity)"
                echo "You can view but your pushes will be blocked."
            fi
            ;;
    esac
}

# Prepare-commit-msg: add agent tag to first commit on issue branch
# Usage (in prepare-commit-msg hook): _bd_prepare_commit_msg "$1"
_bd_prepare_commit_msg() {
    local msg_file="$1"
    local branch
    local my_agent
    local existing_tag
    
    branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
    
    # Skip non-issue branches
    if ! _bd_is_issue_branch "$branch"; then
        return 0
    fi
    
    # Check if this is the first commit on this branch
    # (no commits that aren't also on main/master)
    if git merge-base --is-ancestor HEAD main 2>/dev/null || \
       git merge-base --is-ancestor HEAD master 2>/dev/null; then
        # First commit on this issue branch - add agent tag
        my_agent=$(_bd_get_agent_id)
        
        # Check if message already has an agent tag
        if grep -q '\[agent:' "$msg_file" 2>/dev/null; then
            return 0
        fi
        
        # Append agent tag
        echo "" >> "$msg_file"
        echo "[agent: $my_agent]" >> "$msg_file"
    fi
}

echo "bd multi-agent utilities loaded. Run 'bd-multiagent-help' for usage."

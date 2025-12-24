#!/usr/bin/env fish
# Multi-Agent Coordination Utilities for Beads (Fish Shell)
#
# Usage: source tools/bd-multiagent.fish

# ==============================================================================
# Configuration
# ==============================================================================

set -gx BEADS_STALE_MINUTES (test -n "$BEADS_STALE_MINUTES"; and echo $BEADS_STALE_MINUTES; or echo 30)
set -gx BEADS_ISSUE_PATTERN (test -n "$BEADS_ISSUE_PATTERN"; and echo $BEADS_ISSUE_PATTERN; or echo '^(temper-|bd-)')
set -gx BEADS_AUTO_TAKEOVER (test -n "$BEADS_AUTO_TAKEOVER"; and echo $BEADS_AUTO_TAKEOVER; or echo false)
set -gx BEADS_AUTO_PR (test -n "$BEADS_AUTO_PR"; and echo $BEADS_AUTO_PR; or echo false)

# ==============================================================================
# Agent ID Detection (CI/CD Aware)
# ==============================================================================

function _bd_detect_agent_id
    # 1. Explicit BEADS_AGENT_ID takes priority
    if test -n "$BEADS_AGENT_ID"
        echo $BEADS_AGENT_ID
        return 0
    end
    
    # 2. GitHub Actions
    if test -n "$GITHUB_ACTOR"
        echo "gh-$GITHUB_ACTOR"
        return 0
    end
    
    # 3. GitLab CI
    if test -n "$GITLAB_USER_LOGIN"
        echo "gl-$GITLAB_USER_LOGIN"
        return 0
    end
    if test -n "$CI_JOB_NAME"
        echo "gl-job-$CI_JOB_NAME"
        return 0
    end
    
    # 4. CircleCI
    if test -n "$CIRCLE_USERNAME"
        echo "circle-$CIRCLE_USERNAME"
        return 0
    end
    
    # 5. Jenkins
    if test -n "$BUILD_USER"
        echo "jenkins-$BUILD_USER"
        return 0
    end
    if test -n "$JOB_NAME"
        echo "jenkins-$JOB_NAME"
        return 0
    end
    
    # 6. Azure DevOps
    if test -n "$BUILD_REQUESTEDFOR"
        echo "azure-$BUILD_REQUESTEDFOR"
        return 0
    end
    
    # 7. Buildkite
    if test -n "$BUILDKITE_BUILD_CREATOR"
        echo "bk-$BUILDKITE_BUILD_CREATOR"
        return 0
    end
    
    # 8. Travis CI
    if test -n "$TRAVIS_REPO_SLUG"
        echo "travis-"(basename $TRAVIS_REPO_SLUG)
        return 0
    end
    
    # 9. Generic CI detection
    if test "$CI" = "true"; or test -n "$CI_NAME"
        set -l ci_name (test -n "$CI_NAME"; and echo $CI_NAME; or echo "ci")
        echo "$ci_name-agent"
        return 0
    end
    
    # 10. Local user
    if test -n "$USER"
        echo $USER
        return 0
    end
    
    # Try whoami as fallback
    set -l whoami_result (whoami 2>/dev/null)
    if test -n "$whoami_result"
        echo $whoami_result
        return 0
    end
    
    # 11. Final fallback
    echo "agent"
end

# Initialize agent ID
if not set -q BEADS_AGENT_ID
    set -gx BEADS_AGENT_ID (_bd_detect_agent_id)
end

# ==============================================================================
# Core Utilities
# ==============================================================================

function _bd_is_issue_branch
    set -l branch $argv[1]
    string match -rq $BEADS_ISSUE_PATTERN $branch
end

function _bd_get_agent_id
    echo $BEADS_AGENT_ID
end

function _bd_get_last_commit_time
    set -l branch $argv[1]
    git log -1 --format=%ct $branch 2>/dev/null
end

function _bd_is_branch_stale
    set -l branch $argv[1]
    set -l last_commit_time (_bd_get_last_commit_time $branch)
    
    if test -z "$last_commit_time"
        return 1
    end
    
    set -l now (date +%s)
    set -l stale_seconds (math "$BEADS_STALE_MINUTES * 60")
    
    test (math "$now - $last_commit_time") -gt $stale_seconds
end

function _bd_time_since_commit
    set -l branch $argv[1]
    set -l last_commit_time (_bd_get_last_commit_time $branch)
    
    if test -z "$last_commit_time"
        echo "unknown"
        return
    end
    
    set -l now (date +%s)
    set -l diff (math "$now - $last_commit_time")
    
    if test $diff -lt 60
        echo "$diff"s ago
    else if test $diff -lt 3600
        echo (math "$diff / 60")m ago
    else if test $diff -lt 86400
        echo (math "$diff / 3600")h ago
    else
        echo (math "$diff / 86400")d ago
    end
end

function _bd_extract_agent_from_commit
    set -l commit $argv[1]
    set -l msg (git log -1 --format=%B $commit 2>/dev/null)
    
    # Try [agent: xxx] pattern using grep (more reliable than Fish regex)
    set -l agent_match (echo $msg | grep -oE '\[agent:[[:space:]]*[^]]+\]' | head -1 | sed 's/\[agent:[[:space:]]*//' | sed 's/\]$//')
    if test -n "$agent_match"
        echo $agent_match
        return 0
    end
    
    # Fallback: use commit author
    git log -1 --format=%an $commit 2>/dev/null
end

function _bd_get_branch_owner
    set -l remote_branch $argv[1]
    
    if not git rev-parse --verify $remote_branch &>/dev/null
        return 1
    end
    
    _bd_extract_agent_from_commit $remote_branch
end

# ==============================================================================
# Claim Checking
# ==============================================================================

function _bd_check_claim_status
    set -l issue_id $argv[1]
    set -l remote_branch "origin/$issue_id"
    set -l my_agent (_bd_get_agent_id)
    
    # Fetch latest
    git fetch origin $issue_id 2>/dev/null; or true
    
    # Check if remote branch exists
    if not git rev-parse --verify $remote_branch &>/dev/null
        echo "status=unclaimed"
        return 0
    end
    
    set -l owner (_bd_get_branch_owner $remote_branch)
    set -l time_ago (_bd_time_since_commit $remote_branch)
    set -l is_stale "false"
    
    if _bd_is_branch_stale $remote_branch
        set is_stale "true"
    end
    
    if test "$owner" = "$my_agent"
        echo "status=mine"
    else
        echo "status=claimed"
    end
    echo "owner=$owner"
    echo "stale=$is_stale"
    echo "last_activity=$time_ago"
end

# ==============================================================================
# User-Facing Functions
# ==============================================================================

function bd-claim-status
    set -l issue_id $argv[1]
    
    if test -z "$issue_id"
        echo "Usage: bd-claim-status <issue-id>"
        return 1
    end
    
    set -l output (_bd_check_claim_status $issue_id)
    
    set -l status (echo $output | string match -r 'status=(\w+)' | tail -1)
    set -l owner (echo $output | string match -r 'owner=(\S+)' | tail -1)
    set -l stale (echo $output | string match -r 'stale=(\w+)' | tail -1)
    set -l activity (echo $output | string match -r 'last_activity=(\S+)' | tail -1)
    
    echo "Issue: $issue_id"
    
    switch $status
        case unclaimed
            echo "Status: Unclaimed (available)"
        case mine
            echo "Status: Claimed by you ($owner)"
            echo "Last activity: $activity"
        case claimed
            if test "$stale" = "true"
                echo "Status: STALE - claimed by $owner"
                echo "Last activity: $activity (>$BEADS_STALE_MINUTES"m ago")"
                echo "This claim can be taken over."
            else
                echo "Status: Active - claimed by $owner"
                echo "Last activity: $activity"
            end
    end
end

function bd-claims
    set -l my_agent (_bd_get_agent_id)
    
    echo "Fetching remote branches..."
    git fetch origin --prune 2>/dev/null
    
    echo ""
    echo "Active Claims (branches matching: $BEADS_ISSUE_PATTERN)"
    echo "─────────────────────────────────────────────────────────"
    printf "%-20s %-15s %-12s %s\n" "ISSUE" "OWNER" "ACTIVITY" "STATUS"
    echo "─────────────────────────────────────────────────────────"
    
    set -l found 0
    for ref in (git for-each-ref --format='%(refname)' refs/remotes/origin/)
        set -l issue_id (basename $ref)
        
        # Skip if not an issue branch
        if not _bd_is_issue_branch $issue_id
            continue
        end
        
        set found 1
        set -l owner (_bd_get_branch_owner "origin/$issue_id")
        set -l time_ago (_bd_time_since_commit "origin/$issue_id")
        set -l status_indicator "active"
        
        if _bd_is_branch_stale "origin/$issue_id"
            set status_indicator "STALE"
        else if test "$owner" = "$my_agent"
            set status_indicator "(you)"
        end
        
        printf "%-20s %-15s %-12s %s\n" $issue_id $owner $time_ago $status_indicator
    end
    
    if test $found -eq 0
        echo "(no active claims)"
    end
    
    echo ""
    echo "Your agent ID: $my_agent"
    echo "Stale threshold: $BEADS_STALE_MINUTES minutes"
end

function bd-multiagent-help
    echo "Multi-Agent Coordination Commands (Fish Shell)"
    echo "==============================================="
    echo ""
    echo "Commands:"
    echo "  bd-claims              List all active claims"
    echo "  bd-claim-status <id>   Check claim status of an issue"
    echo "  bd-takeover <id>       Take over a stale claim"
    echo ""
    echo "Environment Variables:"
    echo "  BEADS_AGENT_ID         Your agent identifier (current: $BEADS_AGENT_ID)"
    echo "  BEADS_STALE_MINUTES    Stale threshold (current: $BEADS_STALE_MINUTES)"
    echo "  BEADS_AUTO_PR          Auto-create PR on bd-done (current: $BEADS_AUTO_PR)"
    echo ""
    echo "Setup:"
    echo "  Add to ~/.config/fish/config.fish:"
    echo "    source ~/path/to/temper/tools/bd-multiagent.fish"
    echo "    source ~/path/to/temper/tools/bd-worktree-helpers.fish"
end

function bd-takeover
    set -l issue_id $argv[1]
    set -l force_flag $argv[2]
    
    if test -z "$issue_id"
        echo "Usage: bd-takeover <issue-id> [--force]"
        return 1
    end
    
    set -l my_agent (_bd_get_agent_id)
    set -l output (_bd_check_claim_status $issue_id)
    
    set -l status (echo $output | string match -r 'status=(\w+)' | tail -1)
    set -l owner (echo $output | string match -r 'owner=(\S+)' | tail -1)
    set -l stale (echo $output | string match -r 'stale=(\w+)' | tail -1)
    
    switch $status
        case unclaimed
            echo "Issue $issue_id is not claimed. Use 'bd-work $issue_id' to start."
            return 0
        case mine
            echo "You already own $issue_id."
            return 0
        case claimed
            if test "$stale" != "true"; and test "$force_flag" != "--force"
                echo "Issue $issue_id is actively claimed by $owner."
                echo "Cannot take over an active claim."
                echo "Wait until it becomes stale (>$BEADS_STALE_MINUTES"m") or use --force."
                return 1
            end
    end
    
    # Confirm takeover
    if test "$force_flag" != "--force"; and test "$BEADS_AUTO_TAKEOVER" != "true"
        echo "Taking over $issue_id from $owner"
        read -P "Proceed? [y/N] " confirm
        if test "$confirm" != "y"; and test "$confirm" != "Y"
            echo "Aborted."
            return 1
        end
    end
    
    echo "Taking over $issue_id..."
    
    git fetch origin $issue_id
    
    if git show-ref --verify --quiet "refs/heads/$issue_id"
        git checkout $issue_id
        git reset --hard "origin/$issue_id"
    else
        git checkout -b $issue_id "origin/$issue_id"
    end
    
    git commit --allow-empty -m "chore: takeover from $owner

[agent: $my_agent]
[takeover-from: $owner]"
    
    if git push origin $issue_id
        echo ""
        echo "✓ Taken over $issue_id from $owner"
    else
        echo "Failed to push takeover commit."
        return 1
    end
end

echo "bd multi-agent utilities loaded (Fish). Run 'bd-multiagent-help' for usage."

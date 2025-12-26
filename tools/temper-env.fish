#!/usr/bin/env fish
# Lazy loader for temper bd workflow (Fish Shell)
#
# Usage: Add to ~/.config/fish/config.fish:
#   set -g TEMPER_REPO "$HOME/path/to/temper"
#   source "$TEMPER_REPO/tools/temper-env.fish"
#
# This provides:
#   - Lazy loading of bd helpers on first use
#   - Tab completion for bd commands

# Configuration
set -g TEMPER_LOADED false

# Get repo path
if set -q TEMPER_REPO
    # Already set
else if git rev-parse --show-toplevel &>/dev/null
    set -g TEMPER_REPO (git rev-parse --show-toplevel)
else
    return 0 2>/dev/null || true
end

set -g TEMPER_HELPERS "$TEMPER_REPO/tools/bd-worktree-helpers.fish"

# Lazy load function
function _temper_load_bd
    if test "$TEMPER_LOADED" = "true"
        return 0
    end

    if test -f "$TEMPER_HELPERS"
        source "$TEMPER_HELPERS"
        set -g TEMPER_LOADED true
    end
end

# Wrap all bd commands with lazy loading
function bd
    _temper_load_bd
    command bd $argv
end

function bd-work
    _temper_load_bd
    command bd-work $argv
end

function bd-done
    _temper_load_bd
    command bd-done $argv
end

function bd-pause
    _temper_load_bd
    command bd-pause $argv
end

function bd-claims
    _temper_load_bd
    command bd-claims $argv
end

function bd-status
    _temper_load_bd
    command bd-status $argv
end

function bd-validate-setup
    _temper_load_bd
    command bd-validate-setup $argv
end

function bd-worktrees
    _temper_load_bd
    command bd-worktrees $argv
end

function bd-cleanup-worktrees
    _temper_load_bd
    command bd-cleanup-worktrees $argv
end

function bd-measure
    _temper_load_bd
    command bd-measure $argv
end

function bd-gather
    _temper_load_bd
    command bd-gather $argv
end

function bd-plan
    _temper_load_bd
    command bd-plan $argv
end

function bd-claim-status
    _temper_load_bd
    command bd-claim-status $argv
end

function bd-takeover
    _temper_load_bd
    command bd-takeover $argv
end

function bd-multiagent-help
    _temper_load_bd
    command bd-multiagent-help $argv
end

function bd-worktree-help
    _temper_load_bd
    command bd-worktree-help $argv
end

# Tab completion for Fish
if status is-interactive
    complete -c bd-work -a (command bd --sandbox list --status open --json 2>/dev/null | string match -r '"id":"([^"]*)"' | tail -n +2)
end

echo "✓ temper bd workflow (lazy loading enabled)"

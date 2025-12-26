#!/usr/bin/env bash
# Lazy loader for temper bd workflow
# This script is sourced by your shell and only loads helpers when you use bd commands
#
# Usage: Add to ~/.bashrc or ~/.zshrc:
#   export TEMPER_REPO="$HOME/path/to/temper"
#   source "$TEMPER_REPO/tools/temper-env.sh"
#
# This provides:
#   - bd alias that auto-loads helpers on first use
#   - bd-work, bd-done, etc. functions available immediately
#   - Tab completion for bd commands

# Configuration
TEMPER_REPO="${TEMPER_REPO:-$(git rev-parse --show-toplevel 2>/dev/null)}"
TEMPER_LOADED="${TEMPER_LOADED:-false}"

# Don't load if not in or linked to a temper repo
if [[ -z "$TEMPER_REPO" ]] || [[ ! -d "$TEMPER_REPO" ]]; then
    return 0 2>/dev/null || true
fi

# Path to helpers
TEMPER_HELPERS="$TEMPER_REPO/tools/bd-worktree-helpers.sh"

# Lazy load function
_temper_load_bd() {
    if [[ "$TEMPER_LOADED" == "true" ]]; then
        return 0
    fi

    # Load the helpers
    source "$TEMPER_HELPERS" 2>/dev/null
    TEMPER_LOADED=true
}

# Create bd alias that auto-loads on use
alias bd='_temper_load_bd && bd'

# Auto-load on first bd-work command
bd-work() {
    _temper_load_bd
    bd-work "$@"
}

# Auto-load on first bd-done command
bd-done() {
    _temper_load_bd
    bd-done "$@"
}

# Auto-load on first bd-pause command
bd-pause() {
    _temper_load_bd
    bd-pause "$@"
}

# Auto-load on first bd-claims command
bd-claims() {
    _temper_load_bd
    bd-claims "$@"
}

# Auto-load on first bd-status command
bd-status() {
    _temper_load_bd
    bd-status "$@"
}

# Auto-load on first bd-validate-setup command
bd-validate-setup() {
    _temper_load_bd
    bd-validate-setup "$@"
}

# Auto-load on first bd-worktrees command
bd-worktrees() {
    _temper_load_bd
    bd-worktrees "$@"
}

# Auto-load on first bd-cleanup-worktrees command
bd-cleanup-worktrees() {
    _temper_load_bd
    bd-cleanup-worktrees "$@"
}

# Auto-load on first bd-measure command
bd-measure() {
    _temper_load_bd
    bd-measure "$@"
}

# Auto-load on first bd-gather command
bd-gather() {
    _temper_load_bd
    bd-gather "$@"
}

# Auto-load on first bd-plan command
bd-plan() {
    _temper_load_bd
    bd-plan "$@"
}

# Auto-load on first bd-claim-status command
bd-claim-status() {
    _temper_load_bd
    bd-claim-status "$@"
}

# Auto-load on first bd-takeover command
bd-takeover() {
    _temper_load_bd
    bd-takeover "$@"
}

# Auto-load on first bd-multiagent-help command
bd-multiagent-help() {
    _temper_load_bd
    bd-multiagent-help "$@"
}

# Auto-load on first bd-worktree-help command
bd-worktree-help() {
    _temper_load_bd
    bd-worktree-help "$@"
}

# Completion for bd commands
_temper_bd_complete() {
    local cur prev
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    # Complete task IDs for worktree commands
    if [[ "$prev" == "bd-work" ]]; then
        local tasks
        tasks=$(bd --sandbox list --status open --json 2>/dev/null | grep -o '"id":"[^"]*"' | cut -d'"' -f4 || echo "")
        COMPREPLY=($(compgen -W "$tasks" -- "$cur"))
        return 0
    fi

    # Default completion for other commands
    compgen -W "ready show list create update close sync claims status" -- "$cur"
}

# Register completion for bash
if [[ -n "$BASH_VERSION" ]]; then
    complete -F _temper_bd_complete bd bd-work bd-done bd-pause
fi

# Notify user that lazy loading is enabled
if [[ -n "$BASH_VERSION" ]] && [[ "${TEMPER_SILENT:-false}" != "true" ]]; then
    echo "✓ temper bd workflow (lazy loading enabled)"
fi

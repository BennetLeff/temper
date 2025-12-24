#!/bin/bash
# Install Multi-Agent Git Hooks
#
# This script installs the multi-agent coordination hooks alongside
# the existing beads hooks.
#
# Usage:
#   ./tools/git-hooks/install-multiagent.sh
#
# What it does:
#   1. Appends multi-agent check to pre-push hook
#   2. Creates/updates post-checkout hook
#   3. Creates prepare-commit-msg hook
#
# To uninstall:
#   ./tools/git-hooks/install-multiagent.sh --uninstall

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"

# Marker to identify our additions
MARKER_START="# >>> BEADS MULTI-AGENT START >>>"
MARKER_END="# <<< BEADS MULTI-AGENT END <<<"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if we're in a git repo
if [[ ! -d "$HOOKS_DIR" ]]; then
    error "Not in a git repository or .git/hooks not found"
    exit 1
fi

# Uninstall function
uninstall_hooks() {
    info "Uninstalling multi-agent hooks..."
    
    for hook in pre-push post-checkout prepare-commit-msg; do
        hook_file="$HOOKS_DIR/$hook"
        if [[ -f "$hook_file" ]]; then
            # Remove our section
            if grep -q "$MARKER_START" "$hook_file"; then
                # Use sed to remove our section
                sed -i.bak "/$MARKER_START/,/$MARKER_END/d" "$hook_file"
                rm -f "$hook_file.bak"
                info "Removed multi-agent code from $hook"
            fi
            
            # If file is now empty (just shebang), remove it
            if [[ $(wc -l < "$hook_file") -le 2 ]]; then
                rm "$hook_file"
                info "Removed empty $hook hook"
            fi
        fi
    done
    
    info "Uninstall complete"
    exit 0
}

# Check for uninstall flag
if [[ "$1" == "--uninstall" || "$1" == "-u" ]]; then
    uninstall_hooks
fi

info "Installing multi-agent hooks..."

# ==============================================================================
# Pre-push hook
# ==============================================================================
PREPUSH_FILE="$HOOKS_DIR/pre-push"

# Check if multi-agent code already exists
if [[ -f "$PREPUSH_FILE" ]] && grep -q "$MARKER_START" "$PREPUSH_FILE"; then
    warn "Multi-agent code already in pre-push, skipping"
else
    # Append our code
    cat >> "$PREPUSH_FILE" << 'HOOK_EOF'

# >>> BEADS MULTI-AGENT START >>>
# Multi-agent coordination check
# See tools/bd-multiagent.sh for details

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
MULTIAGENT_SCRIPT="$REPO_ROOT/tools/bd-multiagent.sh"

if [[ -f "$MULTIAGENT_SCRIPT" ]]; then
    # shellcheck source=/dev/null
    source "$MULTIAGENT_SCRIPT" 2>/dev/null
    
    if ! _bd_prepush_check; then
        echo ""
        echo "Push blocked by multi-agent coordination."
        echo "Run 'bd-multiagent-help' for more information."
        exit 1
    fi
fi
# <<< BEADS MULTI-AGENT END <<<
HOOK_EOF
    
    chmod +x "$PREPUSH_FILE"
    info "Updated pre-push hook"
fi

# ==============================================================================
# Post-checkout hook
# ==============================================================================
POSTCHECKOUT_FILE="$HOOKS_DIR/post-checkout"

# Create or update post-checkout
if [[ -f "$POSTCHECKOUT_FILE" ]] && grep -q "$MARKER_START" "$POSTCHECKOUT_FILE"; then
    warn "Multi-agent code already in post-checkout, skipping"
else
    # If file doesn't exist, create with shebang
    if [[ ! -f "$POSTCHECKOUT_FILE" ]]; then
        echo '#!/bin/bash' > "$POSTCHECKOUT_FILE"
        echo '' >> "$POSTCHECKOUT_FILE"
    fi
    
    # For post-checkout, we need to insert BEFORE the final "exit 0"
    # since existing bd hooks end with exit 0
    if grep -q "^exit 0$" "$POSTCHECKOUT_FILE"; then
        # Remove the final exit 0, add our code, then add exit 0 back
        # Use a temp file for safety
        TEMP_FILE=$(mktemp)
        # Remove all trailing "exit 0" lines and trailing newlines
        sed '/^exit 0$/d' "$POSTCHECKOUT_FILE" > "$TEMP_FILE"
        
        cat >> "$TEMP_FILE" << 'HOOK_EOF'

# >>> BEADS MULTI-AGENT START >>>
# Multi-agent checkout notification
# See tools/bd-multiagent.sh for details

# Only run for branch checkouts
if [[ "${3:-}" == "1" ]]; then
    REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
    MULTIAGENT_SCRIPT="$REPO_ROOT/tools/bd-multiagent.sh"
    
    if [[ -f "$MULTIAGENT_SCRIPT" ]]; then
        # shellcheck source=/dev/null
        source "$MULTIAGENT_SCRIPT" 2>/dev/null
        _bd_postcheckout_notify
    fi
fi
# <<< BEADS MULTI-AGENT END <<<

exit 0
HOOK_EOF
        
        mv "$TEMP_FILE" "$POSTCHECKOUT_FILE"
    else
        # No exit 0 at end, just append
        cat >> "$POSTCHECKOUT_FILE" << 'HOOK_EOF'

# >>> BEADS MULTI-AGENT START >>>
# Multi-agent checkout notification
# See tools/bd-multiagent.sh for details

# Only run for branch checkouts
if [[ "${3:-}" == "1" ]]; then
    REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
    MULTIAGENT_SCRIPT="$REPO_ROOT/tools/bd-multiagent.sh"
    
    if [[ -f "$MULTIAGENT_SCRIPT" ]]; then
        # shellcheck source=/dev/null
        source "$MULTIAGENT_SCRIPT" 2>/dev/null
        _bd_postcheckout_notify
    fi
fi
# <<< BEADS MULTI-AGENT END <<<
HOOK_EOF
    fi
    
    chmod +x "$POSTCHECKOUT_FILE"
    info "Updated post-checkout hook"
fi

# ==============================================================================
# Prepare-commit-msg hook
# ==============================================================================
PREPARECOMMIT_FILE="$HOOKS_DIR/prepare-commit-msg"

if [[ -f "$PREPARECOMMIT_FILE" ]] && grep -q "$MARKER_START" "$PREPARECOMMIT_FILE"; then
    warn "Multi-agent code already in prepare-commit-msg, skipping"
else
    # If file doesn't exist, create with shebang
    if [[ ! -f "$PREPARECOMMIT_FILE" ]]; then
        echo '#!/bin/bash' > "$PREPARECOMMIT_FILE"
        echo 'MSG_FILE="$1"' >> "$PREPARECOMMIT_FILE"
        echo 'COMMIT_SOURCE="$2"' >> "$PREPARECOMMIT_FILE"
    fi
    
    cat >> "$PREPARECOMMIT_FILE" << 'HOOK_EOF'

# >>> BEADS MULTI-AGENT START >>>
# Multi-agent commit tagging
# See tools/bd-multiagent.sh for details

# Skip for merge commits, squash, etc.
if [[ -z "$COMMIT_SOURCE" || "$COMMIT_SOURCE" == "message" ]]; then
    REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
    MULTIAGENT_SCRIPT="$REPO_ROOT/tools/bd-multiagent.sh"
    
    if [[ -f "$MULTIAGENT_SCRIPT" ]]; then
        # shellcheck source=/dev/null
        source "$MULTIAGENT_SCRIPT" 2>/dev/null
        _bd_prepare_commit_msg "$MSG_FILE"
    fi
fi
# <<< BEADS MULTI-AGENT END <<<
HOOK_EOF
    
    chmod +x "$PREPARECOMMIT_FILE"
    info "Updated prepare-commit-msg hook"
fi

# ==============================================================================
# Done
# ==============================================================================

echo ""
info "Multi-agent hooks installed successfully!"
echo ""
echo "Next steps:"
echo "  1. Set your agent ID:  export BEADS_AGENT_ID=\"your-name\""
echo "  2. Source the helpers: source tools/bd-multiagent.sh"
echo "  3. Add to ~/.bashrc for persistence"
echo ""
echo "Commands available after sourcing:"
echo "  bd-claims         - List all active claims"
echo "  bd-claim-status   - Check status of an issue"
echo "  bd-takeover       - Take over a stale claim"
echo ""
echo "To uninstall: $0 --uninstall"

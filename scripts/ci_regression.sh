#!/usr/bin/env bash
# CI Regression Pipeline
# Runs: regression suite -> DRC ratchet -> closure test
# Exits non-zero if any step fails.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== CI Regression Pipeline ==="
echo "Repo: $REPO_ROOT"

EXIT_CODE=0

# Step 1: Regression suite
echo ""
echo "--- Step 1/3: Regression Suite ---"
cd "$REPO_ROOT"
if python -m temper-placer regression 2>&1; then
    echo "Regression suite: PASS"
else
    echo "Regression suite: FAIL"
    EXIT_CODE=1
fi

# Step 2: DRC ratchet
echo ""
echo "--- Step 2/3: DRC Ratchet ---"
if python "$SCRIPT_DIR/ci_check_drc.py" 2>&1; then
    echo "DRC ratchet: PASS"
else
    ret=$?
    if [ $ret -eq 2 ]; then
        echo "DRC ratchet: FAIL (ceiling raised without approval)"
    else
        echo "DRC ratchet: FAIL (ceiling exceeded)"
    fi
    EXIT_CODE=1
fi

# Step 3: Closure test (optional, depends on kicad-cli and heavy deps)
echo ""
echo "--- Step 3/3: Closure Test ---"
if [ -f "$REPO_ROOT/pcb/temper_placed.kicad_pcb" ]; then
    if python "$SCRIPT_DIR/ci_closure_test.py" --pcb pcb/temper_placed.kicad_pcb 2>&1; then
        echo "Closure test: PASS"
    else
        echo "Closure test: FAIL"
        EXIT_CODE=1
    fi
else
    echo "Closure test: SKIPPED (temper_placed.kicad_pcb not found)"
fi

echo ""
echo "=== CI Regression Pipeline Complete ==="
if [ $EXIT_CODE -eq 0 ]; then
    echo "All checks passed."
else
    echo "Some checks failed."
fi

exit $EXIT_CODE

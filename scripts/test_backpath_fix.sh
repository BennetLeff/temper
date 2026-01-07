#!/bin/bash
# Quick test to verify backward path fix

set -e

echo "Testing diff pair router backward path fix..."

# Run a single iteration
python3.11 scripts/run_feedback_loop.py --max-iterations 1 --output-dir output/test_backpath_verify

# Check for gaps in the output
echo ""
echo "Checking for gaps in USB_D+ routing..."
python3.11 scripts/debug_diff_pair_path.py

echo ""
echo "Test complete! Check output above for gap analysis."

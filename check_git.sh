#!/bin/bash
cd /Users/bennet/Desktop/temper
echo "=== Current Branch ===" 
git branch --show-current
echo ""
echo "=== All Branches ==="
git branch -a | head -20
echo ""
echo "=== Git Status ==="
git status --short | head -20
echo ""
echo "=== Last 3 Commits ==="
git log --oneline -3

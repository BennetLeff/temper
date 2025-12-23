#!/usr/bin/env python3
"""
Auto-assign tasks to specialized agents based on labels.

Usage:
    python3 tools/agents/auto_assign.py

This script:
1. Scans for open tasks with 'agent:<name>' labels
2. Assigns the corresponding agent as responsible party
3. Updates task status if needed
"""

import subprocess
import json
import sys
from typing import Dict, List


def get_labeled_tasks(label: str) -> List[Dict]:
    """Get open tasks with a specific label."""
    try:
        result = subprocess.run(
            ["bd", "list", "--label", label, "--status", "open", "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error listing tasks: {e.stderr}", file=sys.stderr)
        return []


def assign_task(task_id: str, assignee: str) -> bool:
    """Assign a task to an agent."""
    try:
        result = subprocess.run(
            ["bd", "update", task_id, "-a", assignee, "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"✅ Assigned {task_id} to {assignee}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error assigning {task_id}: {e.stderr}", file=sys.stderr)
        return False


def main():
    """Main auto-assignment workflow."""
    # Define agent mappings
    agent_labels = {
        "nemotron": "nemotron",
        "fast-build": "fast-build",
        "worker-bee": "worker-bee",
    }
    
    total_assigned = 0
    
    print("🤖 Auto-assigning tasks to agents...")
    print()
    
    for label, assignee in agent_labels.items():
        print(f"📋 Checking tasks with label: agent:{label}")
        
        tasks = get_labeled_tasks(f"agent:{label}")
        
        if not tasks:
            print(f"   No tasks found")
            print()
            continue
        
        print(f"   Found {len(tasks)} task(s)")
        
        for task in tasks:
            task_id = task["id"]
            task_title = task["title"]
            
            # Skip already assigned
            if task.get("assignee"):
                print(f"   ⏭️  Skipping {task_id} (already assigned)")
                continue
            
            # Assign the task
            if assign_task(task_id, assignee):
                total_assigned += 1
            else:
                print(f"   ❌ Failed to assign {task_id}")
        
        print()
    
    print(f"📊 Summary: {total_assigned} task(s) assigned")
    return 0 if total_assigned > 0 else 1


if __name__ == "__main__":
    sys.exit(main())

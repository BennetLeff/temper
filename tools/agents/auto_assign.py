#!/usr/bin/env python3
import sys
import json
import subprocess
import time

def run_command(command):
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def get_issues_with_agent_labels():
    # Filter for open issues
    json_out = run_command("bd list --status open --json")
    if not json_out:
        return []
    try:
        issues = json.loads(json_out)
        # Find issues with labels starting with 'agent:'
        agent_tasks = []
        for issue in issues:
            labels = issue.get("labels", [])
            if not labels: continue
            
            for label in labels:
                if label.startswith("agent:"):
                    role = label.split(":")[1]
                    agent_tasks.append((issue["id"], role, label))
        return agent_tasks
    except json.JSONDecodeError:
        return []

def main():
    print("🤖 Auto-Assign Agent: Scanning for labeled tasks...")
    
    tasks = get_issues_with_agent_labels()
    
    if not tasks:
        print("No tasks found with 'agent:<role>' labels.")
        return

    print(f"Found {len(tasks)} task(s).")
    
    for issue_id, role, label in tasks:
        print(f"\n--- Processing {issue_id} ---")
        print(f"Role: {role}")
        
        # 1. Remove the trigger label to prevent loop
        print(f"Removing label '{label}'...")
        run_command(f"bd update {issue_id} --remove-label {label} --json")
        
        # 2. Dispatch
        # We assume assign.py is in the same directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        assign_script = os.path.join(script_dir, "assign.py")
        
        cmd = ["python3", assign_script, issue_id, role]
        
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            print(f"❌ Failed to dispatch {issue_id}")

if __name__ == "__main__":
    import os
    main()

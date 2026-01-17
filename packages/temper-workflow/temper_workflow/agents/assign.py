#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path


def run_command(command):
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running command: {command}")
        print(result.stderr)
        return None
    return result.stdout.strip()

def get_issue(issue_id):
    json_out = run_command(f"bd show {issue_id} --json")
    if not json_out:
        return None
    try:
        data = json.loads(json_out)
        return data[0] if isinstance(data, list) and len(data) > 0 else None
    except json.JSONDecodeError:
        print("Failed to parse issue JSON")
        return None

def update_status(issue_id, status):
    run_command(f"bd update {issue_id} --status {status} --json")

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 assign.py <issue_id> <role>")
        print("Roles: architect, security, tester, coder")
        sys.exit(1)

    issue_id = sys.argv[1]
    role = sys.argv[2]

    # 1. Fetch Issue
    print(f"Fetching issue {issue_id}...")
    issue = get_issue(issue_id)
    if not issue:
        print(f"Issue {issue_id} not found.")
        sys.exit(1)

    title = issue.get("title", "")
    description = issue.get("description", "")

    print(f"Assigning '{title}' to {role} agent.")

    # 2. Update Status
    print("Updating status to in_progress...")
    update_status(issue_id, "in_progress")

    # 3. Construct Prompt
    prompt = f"Issue ID: {issue_id}\nTitle: {title}\n\nDescription:\n{description}\n\nInstructions:\nPlease address the requirements of this issue. If code changes are required, specify the files and changes clearly."

    # 4. Dispatch
    output_dir = Path("agent_outputs")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{issue_id}_{role}_resolution.md"

    dispatch_script = Path("tools/agents/dispatch_core.sh")

    # Determine Tier
    if role in ["architect", "security", "product_manager"]:
        tier = "thinking"
    else:
        tier = "fast"

    print(f"Dispatching to {role} ({tier} model)...")

    # dispatch_core.sh syntax: ./dispatch_core.sh <role> <tier> "<instruction>" <output_file>
    try:
        cmd = [str(dispatch_script), role, tier, prompt, str(output_file)]
        subprocess.run(cmd, check=True)
        print(f"\n✅ Mission Accomplished.\nAgent output saved to: {output_file}")
        print("Review this file and implement changes as needed.")
    except subprocess.CalledProcessError as e:
        print(f"Agent dispatch failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

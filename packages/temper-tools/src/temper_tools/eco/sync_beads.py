#!/usr/bin/env python3
"""
Sync Beads issues to Eco semantic memory with multi-user routing.

Routes issues to appropriate Eco user IDs based on labels:
- agent:architect -> temper-architect
- agent:coder -> temper-coder
- agent:tester -> temper-tester
- domain:firmware -> temper-firmware
- domain:placer -> temper-placer
- domain:pcb -> temper-pcb
- (no label) -> temper-shared

Usage:
    python3 tools/sync_beads_to_eco.py           # Sync all changed issues
    python3 tools/sync_beads_to_eco.py --force   # Force re-sync all issues
    python3 tools/sync_beads_to_eco.py --dry-run # Preview without posting
"""

import hashlib
import json
import os
import sys
import time
from typing import Any

from temper_workflow.gpbm.eco_client import EcoClient, EcoConfig

ISSUES_FILE = ".beads/issues.jsonl"
STATE_FILE = ".beads/eco_sync_state.json"


def load_issues() -> dict[str, Any]:
    """Load all issues from the JSONL file."""
    if not os.path.exists(ISSUES_FILE):
        return {}

    issues = {}
    with open(ISSUES_FILE) as f:
        for line in f:
            if line.strip():
                try:
                    issue = json.loads(line)
                    issues[issue["id"]] = issue
                except json.JSONDecodeError:
                    continue
    return issues


def load_state() -> dict[str, str]:
    """Load sync state (issue_id -> content_hash mapping)."""
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict[str, str]) -> None:
    """Save sync state."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def compute_hash(issue: dict) -> str:
    """Compute hash of issue fields we care about for sync."""
    content = f"{issue.get('title')}|{issue.get('description')}|{issue.get('status')}|{issue.get('priority')}"
    return hashlib.sha256(content.encode()).hexdigest()


def extract_role_from_labels(labels: list[str]) -> str | None:
    """Extract agent role from issue labels.

    Args:
        labels: List of issue labels

    Returns:
        Role name (architect, coder, tester, human) or None
    """
    role_map = {
        "agent:architect": "architect",
        "agent:coder": "coder",
        "agent:tester": "tester",
        "agent:human": "human",
    }

    for label in labels:
        if label in role_map:
            return role_map[label]
    return None


def extract_domain_from_labels(labels: list[str]) -> str | None:
    """Extract project domain from issue labels.

    Args:
        labels: List of issue labels

    Returns:
        Domain name (firmware, placer, pcb) or None
    """
    domain_map = {
        "domain:firmware": "firmware",
        "domain:placer": "placer",
        "domain:pcb": "pcb",
    }

    for label in labels:
        if label in domain_map:
            return domain_map[label]
    return None


def determine_user_id(issue: dict, config: EcoConfig) -> tuple[str, str | None, str | None]:
    """Determine the appropriate Eco user ID for an issue.

    Returns:
        Tuple of (user_id, role, domain)
    """
    labels = issue.get("labels", [])

    role = extract_role_from_labels(labels)
    domain = extract_domain_from_labels(labels)

    # Priority: role > domain > shared
    if role and role in config.ROLES:
        return config.ROLES[role], role, domain
    elif domain and domain in config.DOMAINS:
        return config.DOMAINS[domain], role, domain
    else:
        return config.SHARED, role, domain


def hydrate_state_from_eco(client: EcoClient, state: dict[str, str]) -> dict[str, str]:
    """Hydrate local state from Eco server to avoid double-syncing.

    Queries all user IDs and extracts sync hashes from existing memories.
    """
    print("Hydrating state from Eco server...")
    config = client.config

    # All user IDs to check
    all_user_ids = [config.SHARED] + list(config.ROLES.values()) + list(config.DOMAINS.values())

    count = 0

    for user_id in all_user_ids:
        cursor = None
        pages = 0

        while pages < 10:  # Safety limit per user
            pages += 1
            endpoint = f"/memories?userId={user_id}&limit=100"
            if cursor:
                endpoint += f"&cursor={cursor}"

            try:
                result = client._make_request(endpoint)
                if not result:
                    break

                memories = result.get("memories", [])
                if not memories:
                    break

                for mem in memories:
                    tags = mem.get("tags", [])
                    metadata = mem.get("metadata", {})

                    # Check if this is a beads sync memory
                    if "beads" in tags and "issueId" in metadata and "syncHash" in metadata:
                        issue_id = metadata["issueId"]
                        sync_hash = metadata["syncHash"]

                        # Only store if not already present
                        if issue_id not in state:
                            state[issue_id] = sync_hash
                            count += 1

                # Check for next page
                next_cursor = result.get("cursor")
                if not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor

                if len(memories) < 100:
                    break

            except Exception as e:
                print(f"  Warning: Error hydrating from {user_id}: {e}")
                break

    print(f"  Hydrated {count} entries from Eco.")
    return state


def format_issue_memory(issue: dict, action: str) -> str:
    """Format issue as memory content for Eco."""
    issue_id = issue.get("id", "unknown")
    title = issue.get("title", "")
    status = issue.get("status", "")
    priority = issue.get("priority", "")
    description = issue.get("description", "")
    issue_type = issue.get("issue_type", "task")
    labels = issue.get("labels", [])

    if action == "CREATED":
        desc = f"New {issue_type} {issue_id}: {title}"
    else:
        desc = f"Update on {issue_id} ({status}): {title}"

    content = f"BEADS {action}: {desc}\n\n"
    content += f"Status: {status}\n"
    content += f"Priority: {priority}\n"
    content += f"Type: {issue_type}\n"

    if labels:
        content += f"Labels: {', '.join(labels)}\n"

    content += f"\n{description}"

    # Truncate if too long
    if len(content) > 5000:
        content = content[:5000] + "... (truncated)"

    return content


def sync(force: bool = False, dry_run: bool = False) -> tuple[int, int]:
    """Sync all changed issues to Eco.

    Args:
        force: Force re-sync all issues (ignore state)
        dry_run: Preview without posting

    Returns:
        Tuple of (updates, errors)
    """
    print("Syncing Beads issues to Eco...")

    client = EcoClient()
    issues = load_issues()

    if force:
        state = {}
    else:
        state = load_state()

        # Hydrate from server if state is empty
        if not state:
            state = hydrate_state_from_eco(client, state)
            if state:
                save_state(state)

    updates = 0
    errors = 0

    # Sort IDs for deterministic processing
    issue_ids = sorted(issues.keys())

    for issue_id in issue_ids:
        issue = issues[issue_id]
        current_hash = compute_hash(issue)
        last_hash = state.get(issue_id)

        if current_hash == last_hash:
            continue

        # Determine action type
        is_new = last_hash is None
        action = "CREATED" if is_new else "UPDATED"

        # Determine target user ID based on labels
        user_id, role, domain = determine_user_id(issue, client.config)

        # Format memory content
        memory_content = format_issue_memory(issue, action)

        # Build tags
        tags = ["beads", "sync", action.lower(), issue.get("issue_type", "task")]
        if role:
            tags.append(f"role:{role}")
        if domain:
            tags.append(f"domain:{domain}")

        # Build metadata
        metadata = {
            "issueId": issue_id,
            "syncHash": current_hash,
            "timestamp": time.time(),
        }
        if role:
            metadata["role"] = role
        if domain:
            metadata["domain"] = domain

        if dry_run:
            print(f"[DRY RUN] Would sync {issue_id} ({action}) → {user_id}")
            updates += 1
        else:
            print(f"Syncing {issue_id} ({action}) → {user_id}...")

            success = client.post(
                content=memory_content,
                user_id=user_id,
                tags=tags,
                primary_sector="episodic",
                metadata=metadata,
            )

            if success:
                state[issue_id] = current_hash
                updates += 1
                # Rate limiting
                time.sleep(0.2)
            else:
                errors += 1

    if updates > 0 and not dry_run:
        save_state(state)

    print(f"Sync complete. {updates} updates, {errors} errors.")
    return updates, errors


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Sync Beads issues to Eco semantic memory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Multi-user routing based on labels:
  agent:architect  → temper-architect
  agent:coder      → temper-coder
  agent:tester     → temper-tester
  domain:firmware  → temper-firmware
  domain:placer    → temper-placer
  domain:pcb       → temper-pcb
  (no label)       → temper-shared

Examples:
  python3 tools/sync_beads_to_eco.py           # Sync changed issues
  python3 tools/sync_beads_to_eco.py --force   # Force re-sync all
  python3 tools/sync_beads_to_eco.py --dry-run # Preview only
""",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-sync all issues (ignore cached state)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be synced without posting",
    )

    args = parser.parse_args()

    updates, errors = sync(force=args.force, dry_run=args.dry_run)

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

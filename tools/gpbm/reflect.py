#!/usr/bin/env python3
"""
Auto-reflection tool for GPBM workflow.

Automatically posts reflections to Eco when tasks are completed,
capturing learnings, design decisions, and context for future work.

Usage:
    # From bd-done in worktree
    python3 tools/gpbm/reflect.py --task temper-xxx --reason "Completed feature"

    # Manual invocation
    python3 tools/gpbm/reflect.py --task temper-xxx --reason "Fixed bug" --role coder --domain firmware
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

# Add parent to path for eco_client import
sys.path.insert(0, str(Path(__file__).parent))
from eco_client import EcoClient, EcoConfig


class TaskReflector:
    """Generate and post reflections for completed tasks."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or self._find_project_root()
        self.eco_client = EcoClient()

    def _find_project_root(self) -> Path:
        """Find project root by looking for .git directory."""
        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents):
            if (parent / ".git").exists():
                return parent
        return cwd

    def _run_command(self, cmd: List[str], timeout: int = 10) -> Tuple[bool, str, str]:
        """Run a shell command and return (success, stdout, stderr)."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=timeout,
            )
            return (
                result.returncode == 0,
                result.stdout.strip(),
                result.stderr.strip(),
            )
        except subprocess.TimeoutExpired:
            return False, "", f"Command timed out after {timeout}s"
        except Exception as e:
            return False, "", str(e)

    def get_task_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task information from bd."""
        success, stdout, stderr = self._run_command(
            ["bd", "--sandbox", "show", task_id, "--json"]
        )

        if success and stdout:
            try:
                data = json.loads(stdout)
                if isinstance(data, list) and data:
                    return data[0]
            except json.JSONDecodeError:
                pass

        return None

    def extract_role_domain(
        self, task_info: Dict[str, Any]
    ) -> Tuple[str, Optional[str]]:
        """Extract role and domain from task labels.

        Args:
            task_info: Task data from bd

        Returns:
            (role, domain) tuple. Role defaults to 'coder' if not found.
        """
        labels = task_info.get("labels", [])

        role = "coder"  # Default role
        domain = None

        for label in labels:
            if label.startswith("agent:"):
                # agent:architect -> architect
                role = label.split(":")[1]
            elif label.startswith("domain:"):
                # domain:firmware -> firmware
                domain = label.split(":")[1]
            elif label in ["firmware", "placer", "pcb"]:
                # Direct domain label
                domain = label

        return role, domain

    def get_git_diff_summary(self, task_id: str) -> Dict[str, Any]:
        """Get summary of changes for this task branch.

        Args:
            task_id: Task ID (also branch name)

        Returns:
            Dict with file_count, insertions, deletions, files_changed
        """
        # Check if we're on the task branch
        success, current_branch, _ = self._run_command(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"]
        )

        if not success or current_branch != task_id:
            # Not on task branch, return empty summary
            return {
                "file_count": 0,
                "insertions": 0,
                "deletions": 0,
                "files_changed": [],
            }

        # Get diff stats vs main
        success, diffstat, _ = self._run_command(
            ["git", "diff", "--stat", "main...HEAD"]
        )

        if not success:
            return {
                "file_count": 0,
                "insertions": 0,
                "deletions": 0,
                "files_changed": [],
            }

        # Parse diffstat
        # Format: "3 files changed, 329 insertions(+)"
        lines = diffstat.strip().split("\n")
        files_changed = []
        insertions = 0
        deletions = 0

        for line in lines:
            if " | " in line:
                # File line: "path/to/file.py | 123 ++++"
                filename = line.split("|")[0].strip()
                files_changed.append(filename)
            elif "file" in line and "changed" in line:
                # Summary line
                parts = line.split(",")
                for part in parts:
                    if "insertion" in part:
                        insertions = int(part.split()[0])
                    elif "deletion" in part:
                        deletions = int(part.split()[0])

        return {
            "file_count": len(files_changed),
            "insertions": insertions,
            "deletions": deletions,
            "files_changed": files_changed[:10],  # Limit to first 10 files
        }

    def categorize_changes(self, files: List[str]) -> Dict[str, int]:
        """Categorize changed files by type.

        Args:
            files: List of file paths

        Returns:
            Dict mapping category to file count
        """
        categories = {
            "tests": 0,
            "docs": 0,
            "code": 0,
            "config": 0,
            "other": 0,
        }

        for f in files:
            if "test" in f.lower():
                categories["tests"] += 1
            elif f.endswith(".md") or "doc" in f.lower():
                categories["docs"] += 1
            elif f.endswith((".py", ".c", ".h", ".cpp", ".go", ".rs")):
                categories["code"] += 1
            elif f.endswith((".yaml", ".yml", ".json", ".toml", ".ini")):
                categories["config"] += 1
            else:
                categories["other"] += 1

        return categories

    def generate_reflection(
        self, task_id: str, reason: str, task_info: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate reflection content for a completed task.

        Args:
            task_id: Task ID
            reason: Reason for task completion
            task_info: Optional task data (fetched if not provided)

        Returns:
            Formatted reflection text
        """
        if not task_info:
            task_info = self.get_task_info(task_id)

        if not task_info:
            return f"REFLECTION: Completed {task_id}: {reason}"

        title = task_info.get("title", "Unknown task")
        description = task_info.get("description", "")
        issue_type = task_info.get("issue_type", "task")

        # Get git diff summary
        diff_summary = self.get_git_diff_summary(task_id)

        # Categorize files
        categories = self.categorize_changes(diff_summary["files_changed"])

        # Build reflection
        lines = [
            f"REFLECTION: Completed {issue_type} {task_id}",
            "",
            f"**Title**: {title}",
            f"**Outcome**: {reason}",
            "",
        ]

        # Add high-level change summary
        if diff_summary["file_count"] > 0:
            lines.append("**Changes**:")
            lines.append(
                f"- Modified {diff_summary['file_count']} files "
                f"({diff_summary['insertions']:+d} insertions, {diff_summary['deletions']:+d} deletions)"
            )

            # Show category breakdown
            if categories["code"] > 0:
                lines.append(f"- {categories['code']} code files")
            if categories["tests"] > 0:
                lines.append(f"- {categories['tests']} test files")
            if categories["docs"] > 0:
                lines.append(f"- {categories['docs']} documentation files")
            if categories["config"] > 0:
                lines.append(f"- {categories['config']} configuration files")

            lines.append("")

        # Extract key learnings from description
        # Look for specific sections that indicate learnings
        if description:
            # Look for sections like "Solution:", "Approach:", "Key Findings:"
            learning_sections = []
            for section_header in [
                "## Solution",
                "## Approach",
                "## Key Findings",
                "## Root Cause",
                "## Implementation",
            ]:
                if section_header in description:
                    lines.append("**Key Learning**:")
                    # Extract first paragraph after section
                    section_start = description.index(section_header)
                    section_text = description[section_start : section_start + 500]
                    # Take first non-empty paragraph
                    paragraphs = section_text.split("\n\n")
                    if len(paragraphs) > 1:
                        lines.append(paragraphs[1].strip()[:200] + "...")
                    break

            lines.append("")

        # Add link back to task
        lines.append(f"**Reference**: Task {task_id}")

        return "\n".join(lines)

    def post_reflection(
        self,
        task_id: str,
        reason: str,
        role: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> bool:
        """Generate and post reflection to Eco.

        Args:
            task_id: Task ID
            reason: Completion reason
            role: Agent role (auto-detected if not provided)
            domain: Project domain (auto-detected if not provided)

        Returns:
            True if reflection was posted successfully
        """
        # Get task info
        task_info = self.get_task_info(task_id)
        if not task_info:
            print(f"Warning: Could not fetch task info for {task_id}", file=sys.stderr)
            return False

        # Auto-detect role and domain if not provided
        if not role or not domain:
            detected_role, detected_domain = self.extract_role_domain(task_info)
            role = role or detected_role
            domain = domain or detected_domain

        # Generate reflection
        reflection = self.generate_reflection(task_id, reason, task_info)

        # Post to Eco
        print(f"Posting reflection to Eco (role={role}, domain={domain})...")
        success = self.eco_client.post_reflection(
            content=reflection,
            role=role,
            domain=domain,
            tags=["reflection", "auto-generated"],
            task_id=task_id,
            also_shared=False,  # Role-specific only
        )

        if success:
            print(f"✓ Reflection posted to Eco under {role} user ID")
        else:
            print(f"✗ Failed to post reflection", file=sys.stderr)

        return success


def main():
    """CLI interface for reflection tool."""
    parser = argparse.ArgumentParser(
        description="Post task reflection to Eco",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-detect role and domain from task labels
  python reflect.py --task temper-xxx --reason "Completed feature"
  
  # Override role and domain
  python reflect.py --task temper-yyy --reason "Fixed bug" --role coder --domain firmware
""",
    )

    parser.add_argument("--task", required=True, help="bd task ID")
    parser.add_argument("--reason", required=True, help="Completion reason")
    parser.add_argument("--role", help="Agent role (architect, coder, tester)")
    parser.add_argument("--domain", help="Project domain (firmware, placer, pcb)")
    parser.add_argument("--root", help="Project root directory")
    parser.add_argument(
        "--dry-run", action="store_true", help="Generate but don't post"
    )

    args = parser.parse_args()

    root = Path(args.root) if args.root else None
    reflector = TaskReflector(project_root=root)

    # Get task info
    task_info = reflector.get_task_info(args.task)
    if not task_info:
        print(f"Error: Task {args.task} not found", file=sys.stderr)
        return 1

    # Auto-detect role/domain if not provided
    role = args.role
    domain = args.domain
    if not role or not domain:
        detected_role, detected_domain = reflector.extract_role_domain(task_info)
        role = role or detected_role
        domain = domain or detected_domain

    # Generate reflection
    reflection = reflector.generate_reflection(args.task, args.reason, task_info)

    print("Generated reflection:")
    print("=" * 60)
    print(reflection)
    print("=" * 60)

    if args.dry_run:
        print("\n[DRY RUN] Would post to Eco:")
        print(f"  Role: {role}")
        print(f"  Domain: {domain}")
        print(f"  Tags: reflection, auto-generated, task:{args.task}")
        return 0

    # Post to Eco
    success = reflector.post_reflection(args.task, args.reason, role, domain)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
PLAN phase implementation for GPBM workflow.

Creates bd epics and tasks from gathered context, with:
- Automatic task breakdown suggestions
- Human approval gate (creates blocking approval task)
- Requirement linking
- Dependency management

Usage:
    # As CLI
    python plan.py --context context.md --epic "Implement PID improvements"
    python plan.py --goal "Fix boundary loss" --domain placer --auto

    # As library
    from gpbm.plan import PlanPhase
    planner = PlanPhase()
    epic_id = planner.create_epic("Implement PID improvements", tasks=[...])
"""

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class PlannedTask:
    """A task to be created in bd."""

    title: str
    description: str = ""
    task_type: str = "task"  # task, bug, feature, epic
    priority: int = 2  # 0-4
    labels: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # Task titles to depend on
    requirements: list[str] = field(default_factory=list)  # REQ-* IDs to link
    measurement_targets: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "type": self.task_type,
            "priority": self.priority,
            "labels": self.labels,
            "dependencies": self.dependencies,
            "requirements": self.requirements,
            "measurement_targets": self.measurement_targets,
        }


@dataclass
class Plan:
    """A plan with epic and tasks."""

    epic_title: str
    epic_description: str
    tasks: list[PlannedTask]
    domain: str | None = None
    role: str | None = None
    requires_approval: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "epic": {
                "title": self.epic_title,
                "description": self.epic_description,
            },
            "tasks": [t.to_dict() for t in self.tasks],
            "domain": self.domain,
            "requires_approval": self.requires_approval,
        }

    def to_markdown(self) -> str:
        """Format plan as markdown for review."""
        lines = [
            f"# Plan: {self.epic_title}",
            "",
            f"**Domain:** {self.domain or 'general'}  ",
            f"**Requires Approval:** {'Yes' if self.requires_approval else 'No'}  ",
            "",
            "## Epic Description",
            "",
            self.epic_description,
            "",
            "## Planned Tasks",
            "",
        ]

        for i, task in enumerate(self.tasks, 1):
            priority_label = [
                "P0-Critical",
                "P1-High",
                "P2-Medium",
                "P3-Low",
                "P4-Backlog",
            ][task.priority]
            lines.extend(
                [
                    f"### {i}. {task.title}",
                    "",
                    f"**Type:** {task.task_type}  ",
                    f"**Priority:** {priority_label}  ",
                ]
            )

            if task.labels:
                lines.append(f"**Labels:** {', '.join(task.labels)}  ")

            if task.dependencies:
                lines.append(f"**Depends on:** {', '.join(task.dependencies)}  ")

            if task.requirements:
                lines.append(f"**Requirements:** {', '.join(task.requirements)}  ")

            lines.append("")

            if task.description:
                lines.append(task.description[:500])
                lines.append("")

            if task.measurement_targets:
                lines.append("**Measurement Targets:**")
                for mt in task.measurement_targets:
                    lines.append(f"  - {mt['metric']}: {mt['target']}")
                lines.append("")

        lines.extend(
            [
                "---",
                "",
                "## Approval",
                "",
                "To approve this plan and create the tasks, run:",
                "```bash",
                "python plan.py --execute plan.json",
                "```",
                "",
                "Or review and modify `plan.json` before executing.",
            ]
        )

        return "\n".join(lines)


class PlanPhase:
    """PLAN phase implementation."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or self._find_project_root()

    def _find_project_root(self) -> Path:
        """Find project root."""
        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents):
            if (parent / ".git").exists():
                return parent
        return cwd

    def _run_bd(self, args: list[str]) -> tuple[bool, str, str]:
        """Run bd command and return (success, stdout, stderr)."""
        try:
            result = subprocess.run(
                ["bd", "--sandbox"] + args,
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=30,
            )
            return (
                result.returncode == 0,
                result.stdout.strip(),
                result.stderr.strip(),
            )
        except Exception as e:
            return False, "", str(e)

    def create_epic(
        self,
        title: str,
        description: str,
        priority: int = 1,
        labels: list[str] | None = None,
    ) -> str | None:
        """Create an epic in bd.

        Returns:
            Epic ID if successful, None otherwise
        """
        args = [
            "create",
            title,
            "--description",
            description,
            "-t",
            "epic",
            "-p",
            str(priority),
            "--json",
        ]

        if labels:
            for label in labels:
                args.extend(["--label", label])

        success, stdout, stderr = self._run_bd(args)

        if success:
            try:
                data = json.loads(stdout)
                return data.get("id")
            except json.JSONDecodeError:
                # Try to extract ID from output
                match = re.search(r"(temper-[\w.]+)", stdout)
                if match:
                    return match.group(1)

        print(f"Error creating epic: {stderr}", file=sys.stderr)
        return None

    def create_task(self, task: PlannedTask, parent_id: str | None = None) -> str | None:
        """Create a task in bd.

        Returns:
            Task ID if successful, None otherwise
        """
        # Build description with measurement targets
        desc = task.description

        if task.measurement_targets:
            desc += "\n\nmeasurement_targets:\n"
            for mt in task.measurement_targets:
                desc += f"  - metric: {mt['metric']}\n"
                desc += f'    target: "{mt["target"]}"\n'

        args = [
            "create",
            task.title,
            "--description",
            desc,
            "-t",
            task.task_type,
            "-p",
            str(task.priority),
            "--json",
        ]

        if parent_id:
            args.extend(["--parent", parent_id])

        for label in task.labels:
            args.extend(["--label", label])

        for req in task.requirements:
            args.extend(["--label", f"req:{req}"])

        success, stdout, stderr = self._run_bd(args)

        if success:
            try:
                data = json.loads(stdout)
                return data.get("id")
            except json.JSONDecodeError:
                match = re.search(r"(temper-[\w.]+)", stdout)
                if match:
                    return match.group(1)

        print(f"Error creating task '{task.title}': {stderr}", file=sys.stderr)
        return None

    def add_dependency(self, from_id: str, to_id: str, dep_type: str = "blocks") -> bool:
        """Add dependency between tasks."""
        success, _, stderr = self._run_bd(["dep", "add", from_id, to_id, "--type", dep_type])

        if not success:
            print(f"Error adding dependency: {stderr}", file=sys.stderr)

        return success

    def create_approval_task(self, epic_id: str, plan_title: str) -> str | None:
        """Create a human approval task that blocks the epic's tasks."""
        task = PlannedTask(
            title=f"[APPROVAL] Review and approve: {plan_title}",
            description=f"""## Human Approval Required

This task blocks work on the epic **{epic_id}**.

### To Approve:
1. Review the plan in the epic description
2. Make any necessary adjustments
3. Close this task with reason "Approved" to unblock work

### To Reject:
1. Close this task with reason "Rejected"
2. Add comments explaining needed changes
3. Create a new plan iteration

---

_This is a GPBM approval gate task._
""",
            task_type="task",
            priority=0,  # Critical - needs human attention
            labels=["gpbm:approval", "needs:human"],
        )

        return self.create_task(task, parent_id=epic_id)

    def _infer_agent_role(self, task: PlannedTask) -> Optional[str]:
        """Infer appropriate agent role from task content.

        Uses keyword matching in priority order (security/architect take precedence).

        Args:
            task: Task to analyze

        Returns:
            Inferred role name or None if no clear match
        """
        text = f"{task.title} {task.description}".lower()

        # Priority order matters - security/architect before coder
        if any(kw in text for kw in ["security", "vulnerability", "audit", "validation"]):
            return "security"
        elif any(kw in text for kw in ["design", "architecture", "pattern", "tradeoff"]):
            return "architect"
        elif any(kw in text for kw in ["test", "verify", "edge case", "coverage", "qa"]):
            return "tester"
        elif any(kw in text for kw in ["implement", "refactor", "optimize", "code", "fix"]):
            return "coder"

        return None  # No clear role, can be manually assigned

    def execute_plan(self, plan: Plan, dry_run: bool = False) -> dict[str, Any]:
        """Execute a plan by creating epic and tasks in bd.

        Args:
            plan: The plan to execute
            dry_run: If True, just print what would be created

        Returns:
            Dict with created IDs and status
        """
        result = {
            "epic_id": None,
            "task_ids": [],
            "approval_id": None,
            "dependencies_added": [],
            "success": False,
        }

        if dry_run:
            print("=== DRY RUN - No changes will be made ===\n")
            print(f"Would create epic: {plan.epic_title}")
            print(f"Would create {len(plan.tasks)} tasks:")
            for i, t in enumerate(plan.tasks, 1):
                print(f"  {i}. {t.title} [{t.task_type}, P{t.priority}]")
            if plan.requires_approval:
                print("\nWould create approval gate task")
            print("\n=== END DRY RUN ===")
            return result

        # Build labels
        labels = []
        if plan.domain:
            labels.append(f"domain:{plan.domain}")
        if plan.role:
            labels.append(f"agent:{plan.role}")
        labels.append("gpbm:planned")

        # Create epic
        print(f"Creating epic: {plan.epic_title}")
        epic_id = self.create_epic(
            plan.epic_title, plan.epic_description, priority=1, labels=labels
        )

        if not epic_id:
            print("Failed to create epic", file=sys.stderr)
            return result

        result["epic_id"] = epic_id
        print(f"  Created: {epic_id}")

        # Create tasks
        task_id_map = {}  # title -> id

        for i, task in enumerate(plan.tasks, 1):
            print(f"Creating task {i}/{len(plan.tasks)}: {task.title}")

            # Add domain label if not present
            if plan.domain and f"domain:{plan.domain}" not in task.labels:
                task.labels.append(f"domain:{plan.domain}")

            task_id = self.create_task(task, parent_id=epic_id)

            if task_id:
                result["task_ids"].append(task_id)
                task_id_map[task.title] = task_id
                print(f"  Created: {task_id}")

                # Auto-assign agent role based on task content
                agent_role = self._infer_agent_role(task)
                if agent_role:
                    print(f"  Auto-assigning to {agent_role} agent")
                    success, _, _ = self._run_bd(
                        ["update", task_id, "--add-label", f"agent:{agent_role}"]
                    )
                    if not success:
                        print(
                            f"  Warning: Failed to add agent:{agent_role} label",
                            file=sys.stderr,
                        )
            else:
                print("  Failed to create task")

        # Add dependencies between tasks
        for task in plan.tasks:
            if task.title not in task_id_map:
                continue

            task_id = task_id_map[task.title]

            for dep_title in task.dependencies:
                if dep_title in task_id_map:
                    dep_id = task_id_map[dep_title]
                    print(f"Adding dependency: {task_id} depends on {dep_id}")
                    if self.add_dependency(task_id, dep_id):
                        result["dependencies_added"].append((task_id, dep_id))

        # Create approval task if required
        if plan.requires_approval:
            print("Creating approval gate task")
            approval_id = self.create_approval_task(epic_id, plan.epic_title)
            if approval_id:
                result["approval_id"] = approval_id
                print(f"  Created: {approval_id}")

                # Make all tasks depend on approval
                for task_id in result["task_ids"]:
                    self.add_dependency(task_id, approval_id)

        result["success"] = True
        return result

    def suggest_tasks_from_context(
        self,
        context_file: Path,
        goal: str,
        role: str | None = None,
        domain: str | None = None,
    ) -> list[PlannedTask]:
        """Use LLM to generate intelligent task breakdown from context.

        Attempts to use Gemini API for smart task decomposition. Falls back
        to heuristics if LLM is unavailable or fails.

        Args:
            context_file: Path to gathered context file
            goal: Task goal/objective
            role: Agent role (for context)
            domain: Project domain (for context)

        Returns:
            List of PlannedTask objects
        """
        # Try LLM-based planning first
        try:
            llm_tasks = self._suggest_tasks_llm(context_file, goal, role, domain)
            if llm_tasks:
                print("✓ Using LLM-generated task breakdown", file=sys.stderr)
                return llm_tasks
        except Exception as e:
            print(
                f"⚠ LLM planning failed ({e}), falling back to heuristics",
                file=sys.stderr,
            )

        # Fallback to heuristics
        return self._suggest_tasks_heuristic(context_file, goal)

    def _suggest_tasks_llm(
        self,
        context_file: Path,
        goal: str,
        role: str | None = None,
        domain: str | None = None,
    ) -> list[PlannedTask] | None:
        """Call LLM API to generate task breakdown.

        Returns None if LLM unavailable or response invalid.
        """
        import os

        # Check if GEMINI_API_KEY is available
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None

        # Read context (truncate to avoid token limits)
        context = ""
        if context_file.exists():
            context = context_file.read_text()[:3000]  # Max 3000 chars

        # Build prompt
        prompt = f"""You are a planning assistant for the GPBM (Gather-Plan-Build-Measure) workflow.

CONTEXT:
{context}

GOAL: {goal}
DOMAIN: {domain or "general"}
ROLE: {role or "general"}

Break this goal into 3-8 specific, actionable tasks. Consider:
- Complexity of the domain
- Related requirements and issues in the context
- Past learnings from Eco memories
- Natural dependencies between tasks
- Task types: bug, feature, task (use "task" for general work items)
- Priorities: 0 (critical) to 4 (backlog)

Output ONLY valid JSON array (no markdown, no explanations):
[
  {{
    "title": "Clear, specific task title without redundant goal text",
    "description": "Detailed description with acceptance criteria",
    "priority": 1,
    "type": "task",
    "dependencies": ["Title of prerequisite task"],
    "requirements": ["REQ-ID-001"]
  }}
]

IMPORTANT:
- Keep task titles concise (don't repeat the full goal in every title)
- Make dependencies logical (design before implement, implement before test)
- Set realistic priorities (don't make everything P0/P1)
- Include acceptance criteria in descriptions
"""

        # Call Gemini API
        try:
            import urllib.request
            import json as json_module

            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent"
            headers = {
                "Content-Type": "application/json",
            }

            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 2048,
                },
            }

            encoded = json_module.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{url}?key={api_key}", data=encoded, headers=headers, method="POST"
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                result = json_module.load(response)

                # Extract text from response
                if "candidates" in result and result["candidates"]:
                    text = result["candidates"][0]["content"]["parts"][0]["text"]

                    # Clean up markdown code blocks if present
                    text = text.strip()
                    if text.startswith("```json"):
                        text = text[7:]
                    if text.startswith("```"):
                        text = text[3:]
                    if text.endswith("```"):
                        text = text[:-3]
                    text = text.strip()

                    # Parse JSON
                    tasks_data = json_module.loads(text)

                    # Convert to PlannedTask objects
                    tasks = []
                    for t in tasks_data:
                        tasks.append(
                            PlannedTask(
                                title=t.get("title", "Untitled task"),
                                description=t.get("description", ""),
                                task_type=t.get("type", "task"),
                                priority=t.get("priority", 2),
                                dependencies=t.get("dependencies", []),
                                requirements=t.get("requirements", []),
                                labels=t.get("labels", []),
                            )
                        )

                    return tasks if tasks else None

        except Exception as e:
            print(f"LLM API call failed: {e}", file=sys.stderr)
            return None

        return None

    def _suggest_tasks_heuristic(self, context_file: Path, goal: str) -> list[PlannedTask]:
        """Suggest tasks based on gathered context (heuristic fallback).

        This is a simple heuristic-based suggestion.
        Used as fallback when LLM is unavailable.
        """
        tasks = []

        # Read context if file exists
        context = {}
        if context_file.exists():
            content = context_file.read_text()
            # Try to extract requirements mentioned
            req_matches = re.findall(r"REQ-[\w-]+", content)
            context["requirements"] = list(set(req_matches))

        # Default task breakdown for common patterns
        goal_lower = goal.lower()

        if "implement" in goal_lower or "add" in goal_lower:
            tasks.extend(
                [
                    PlannedTask(
                        title=f"Design: {goal}",
                        description="Create detailed design document",
                        task_type="task",
                        priority=1,
                        labels=["phase:design"],
                    ),
                    PlannedTask(
                        title=f"Implement: {goal}",
                        description="Core implementation",
                        task_type="task",
                        priority=1,
                        labels=["phase:implement"],
                        dependencies=[f"Design: {goal}"],
                    ),
                    PlannedTask(
                        title=f"Test: {goal}",
                        description="Write unit and integration tests",
                        task_type="task",
                        priority=2,
                        labels=["phase:test"],
                        dependencies=[f"Implement: {goal}"],
                    ),
                    PlannedTask(
                        title=f"Document: {goal}",
                        description="Update documentation",
                        task_type="task",
                        priority=3,
                        labels=["phase:docs"],
                        dependencies=[f"Implement: {goal}"],
                    ),
                ]
            )

        elif "fix" in goal_lower or "bug" in goal_lower:
            tasks.extend(
                [
                    PlannedTask(
                        title=f"Reproduce: {goal}",
                        description="Create minimal reproduction case",
                        task_type="task",
                        priority=1,
                    ),
                    PlannedTask(
                        title=f"Fix: {goal}",
                        description="Implement the fix",
                        task_type="task",
                        priority=1,
                        dependencies=[f"Reproduce: {goal}"],
                    ),
                    PlannedTask(
                        title=f"Test: {goal}",
                        description="Add regression tests",
                        task_type="task",
                        priority=1,
                        dependencies=[f"Fix: {goal}"],
                    ),
                ]
            )

        else:
            # Generic breakdown
            tasks.extend(
                [
                    PlannedTask(
                        title=f"Research: {goal}",
                        description="Investigate and document approach",
                        task_type="task",
                        priority=2,
                    ),
                    PlannedTask(
                        title=f"Execute: {goal}",
                        description="Main implementation work",
                        task_type="task",
                        priority=2,
                        dependencies=[f"Research: {goal}"],
                    ),
                    PlannedTask(
                        title=f"Verify: {goal}",
                        description="Verify completion and quality",
                        task_type="task",
                        priority=2,
                        dependencies=[f"Execute: {goal}"],
                    ),
                ]
            )

        # Link requirements from context
        if context.get("requirements"):
            for task in tasks:
                task.requirements = context["requirements"][:3]  # Link top 3

        return tasks


def main():
    """CLI interface for PLAN phase."""
    import argparse

    parser = argparse.ArgumentParser(
        description="PLAN phase - create epics and tasks from context",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create plan from goal (interactive)
  python plan.py --goal "Implement PID improvements" --domain firmware

  # Create plan from context file
  python plan.py --context context.md --epic "PID Improvements"

  # Execute a saved plan
  python plan.py --execute plan.json

  # Dry run (preview without creating)
  python plan.py --goal "Fix bug" --dry-run
""",
    )

    parser.add_argument("--goal", "-g", type=str, help="Goal to create plan for")
    parser.add_argument("--context", "-c", type=str, help="Context file from GATHER phase")
    parser.add_argument("--epic", "-e", type=str, help="Epic title (default: derived from goal)")
    parser.add_argument(
        "--domain",
        "-d",
        type=str,
        choices=["firmware", "placer", "pcb"],
        help="Project domain",
    )
    parser.add_argument(
        "--role",
        "-r",
        type=str,
        choices=["architect", "coder", "tester"],
        help="Agent role",
    )
    parser.add_argument("--execute", type=str, help="Execute plan from JSON file")
    parser.add_argument("--output", "-o", type=str, help="Output plan file (JSON)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    parser.add_argument("--no-approval", action="store_true", help="Skip approval gate task")
    parser.add_argument("--root", type=str, help="Project root directory")

    args = parser.parse_args()

    root = Path(args.root) if args.root else None
    planner = PlanPhase(project_root=root)

    # Execute existing plan
    if args.execute:
        plan_file = Path(args.execute)
        if not plan_file.exists():
            print(f"Plan file not found: {args.execute}", file=sys.stderr)
            sys.exit(1)

        plan_data = json.loads(plan_file.read_text())
        plan = Plan(
            epic_title=plan_data["epic"]["title"],
            epic_description=plan_data["epic"]["description"],
            tasks=[PlannedTask(**t) for t in plan_data["tasks"]],
            domain=plan_data.get("domain"),
            requires_approval=plan_data.get("requires_approval", True),
        )

        result = planner.execute_plan(plan, dry_run=args.dry_run)

        if result["success"]:
            print("\n✓ Plan executed successfully!")
            print(f"  Epic: {result['epic_id']}")
            print(f"  Tasks: {len(result['task_ids'])}")
            if result["approval_id"]:
                print(f"  Approval task: {result['approval_id']}")
        else:
            print("\n✗ Plan execution failed", file=sys.stderr)
            sys.exit(1)

        return

    # Create new plan
    if not args.goal:
        parser.error("--goal is required (or use --execute to run existing plan)")

    epic_title = args.epic or args.goal
    context_file = Path(args.context) if args.context else Path("/dev/null")

    # Generate suggested tasks (use LLM if available, fallback to heuristics)
    tasks = planner.suggest_tasks_from_context(context_file, args.goal, args.role, args.domain)

    # Create plan
    plan = Plan(
        epic_title=epic_title,
        epic_description=f"## Goal\n\n{args.goal}\n\n## Generated by GPBM PLAN phase",
        tasks=tasks,
        domain=args.domain,
        role=args.role,
        requires_approval=not args.no_approval,
    )

    # Output
    if args.output:
        Path(args.output).write_text(json.dumps(plan.to_dict(), indent=2))
        print(f"Plan saved to {args.output}")
        print(plan.to_markdown())
    elif args.dry_run:
        planner.execute_plan(plan, dry_run=True)
    else:
        # Default: print markdown and prompt
        print(plan.to_markdown())
        print("\n" + "=" * 50)
        print("To execute this plan, save it and run:")
        print("  python plan.py --execute plan.json")
        print("\nOr pipe directly:")
        print(
            f"  python plan.py --goal '{args.goal}' --output plan.json && python plan.py --execute plan.json"
        )


if __name__ == "__main__":
    main()

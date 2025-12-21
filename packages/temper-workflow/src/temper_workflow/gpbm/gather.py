#!/usr/bin/env python3
"""
GATHER phase implementation for GPBM workflow.

Collects context from multiple sources:
- Eco semantic memory (multi-user)
- Requirements (from parsed markdown)
- Existing bd issues (related work)
- Codebase structure

Outputs a context document for planning.

Usage:
    # As CLI
    python gather.py --goal "Implement PID improvements" --output context.md
    python gather.py --goal "Fix boundary loss" --domain placer --role architect

    # As library
    from gpbm.gather import GatherPhase
    gatherer = GatherPhase()
    context = gatherer.gather("Implement PID improvements", domain="firmware")
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Configurable thresholds via environment variables
ECO_MIN_SCORE = float(os.environ.get("ECO_MIN_SCORE", "0.6"))
ECO_LIMIT = int(os.environ.get("ECO_LIMIT", "5"))

# Import sibling modules
try:
    from .eco_client import EcoClient
    from .requirements_parser import RequirementsParser
except ImportError:
    # Direct execution
    from eco_client import EcoClient
    from requirements_parser import RequirementsParser


@dataclass
class GatherContext:
    """Collected context from GATHER phase."""

    goal: str
    timestamp: str
    domain: str | None = None
    role: str | None = None

    # Eco memories
    eco_legacy: list[dict] = field(default_factory=list)
    eco_shared: list[dict] = field(default_factory=list)
    eco_role: list[dict] = field(default_factory=list)
    eco_domain: list[dict] = field(default_factory=list)

    # Requirements
    related_requirements: list[dict] = field(default_factory=list)
    unverified_requirements: list[dict] = field(default_factory=list)

    # bd issues
    related_issues: list[dict] = field(default_factory=list)
    blocking_issues: list[dict] = field(default_factory=list)

    # Codebase
    relevant_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "goal": self.goal,
            "timestamp": self.timestamp,
            "domain": self.domain,
            "role": self.role,
            "eco_memories": {
                "legacy": self.eco_legacy,
                "shared": self.eco_shared,
                "role": self.eco_role,
                "domain": self.eco_domain,
            },
            "requirements": {
                "related": self.related_requirements,
                "unverified": self.unverified_requirements,
            },
            "issues": {
                "related": self.related_issues,
                "blocking": self.blocking_issues,
            },
            "files": self.relevant_files,
        }

    def to_markdown(self) -> str:
        """Format as markdown document."""
        lines = [
            f"# GATHER Context: {self.goal}",
            "",
            f"**Generated:** {self.timestamp}  ",
            f"**Domain:** {self.domain or 'general'}  ",
            f"**Role:** {self.role or 'general'}  ",
            "",
            "---",
            "",
        ]

        # Eco memories section
        lines.extend(
            [
                "## Relevant Knowledge (from Eco)",
                "",
            ]
        )

        all_memories = self.eco_legacy + self.eco_shared + self.eco_role + self.eco_domain
        if all_memories:
            for i, mem in enumerate(all_memories[:10], 1):
                memory = mem.get("memory", {})
                content = memory.get("content", "")[:300]
                source = mem.get("source_user_id", "unknown")
                score = mem.get("score", 0)
                lines.extend(
                    [
                        f"### Memory {i} (from {source}, score: {score:.2f})",
                        "",
                        f"> {content}",
                        "",
                    ]
                )
        else:
            lines.extend(
                [
                    "_No relevant memories found in Eco semantic memory._",
                    "",
                    "**Note:** Eco memories are populated as agents work on tasks.",
                    "To add knowledge to Eco:",
                    "```bash",
                    "# Post a learning/reflection",
                    'python3 tools/gpbm/eco_client.py post "Learned that..." --role coder --domain firmware',
                    "",
                    "# Post shared knowledge",
                    'python3 tools/gpbm/eco_client.py post "Project uses..." --role architect --shared',
                    "```",
                    "",
                ]
            )

        # Requirements section
        lines.extend(
            [
                "## Related Requirements",
                "",
            ]
        )

        if self.related_requirements:
            lines.append("| ID | Title | Status | Priority |")
            lines.append("|-----|-------|--------|----------|")
            for req in self.related_requirements[:15]:
                lines.append(
                    f"| {req['id']} | {req['title'][:40]} | {req['status']} | {req['priority']} |"
                )
            lines.append("")
        else:
            lines.append("_No directly related requirements found._\n")

        if self.unverified_requirements:
            lines.extend(
                [
                    "### Unverified Requirements in Domain",
                    "",
                ]
            )
            for req in self.unverified_requirements[:10]:
                lines.append(f"- **{req['id']}**: {req['title'][:50]} [{req['status']}]")
            lines.append("")

        # Issues section
        lines.extend(
            [
                "## Related Issues (from bd)",
                "",
            ]
        )

        if self.related_issues:
            for issue in self.related_issues[:10]:
                status = issue.get("status", "unknown")
                priority = issue.get("priority", "?")
                title = issue.get("title", "Untitled")[:60]
                issue_id = issue.get("id", "?")
                lines.append(f"- **{issue_id}** [{status}, P{priority}]: {title}")
            lines.append("")
        else:
            lines.append("_No related issues found._\n")

        if self.blocking_issues:
            lines.extend(
                [
                    "### Potentially Blocking Issues",
                    "",
                ]
            )
            for issue in self.blocking_issues[:5]:
                lines.append(f"- **{issue.get('id')}**: {issue.get('title', '')[:50]}")
            lines.append("")

        # Files section
        if self.relevant_files:
            lines.extend(
                [
                    "## Relevant Files",
                    "",
                ]
            )
            for f in self.relevant_files[:20]:
                lines.append(f"- `{f}`")
            lines.append("")

        # Next steps
        lines.extend(
            [
                "---",
                "",
                "## Suggested Next Steps",
                "",
                "1. Review the memories and requirements above",
                "2. Identify gaps in current implementation",
                "3. Create a planning document or bd epic with subtasks",
                "4. Get human approval before proceeding to BUILD phase",
                "",
                "---",
                "",
                "_This context was generated by the GPBM GATHER phase._",
            ]
        )

        return "\n".join(lines)


class GatherPhase:
    """GATHER phase implementation."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or self._find_project_root()
        self.eco_client = EcoClient()
        self.req_parser = RequirementsParser(self.project_root)
        self.req_parser.parse_all()

    def _find_project_root(self) -> Path:
        """Find project root."""
        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents):
            if (parent / ".git").exists():
                return parent
        return cwd

    def _search_eco(
        self, goal: str, role: str | None = None, domain: str | None = None
    ) -> dict[str, list[dict]]:
        """Search Eco for relevant memories (parallel version).

        Uses ECO_MIN_SCORE and ECO_LIMIT environment variables for configuration.
        Defaults: min_score=0.6, limit=5

        Searches are executed in parallel for 4× speedup.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        result = {
            "shared": [],
            "role": [],
            "domain": [],
            "legacy": [],
        }

        # Build list of searches to execute
        searches = [
            ("legacy", self.eco_client.config.LEGACY),
            ("shared", self.eco_client.config.SHARED),
        ]

        if role and role in self.eco_client.config.ROLES:
            searches.append(("role", self.eco_client.config.ROLES[role]))

        if domain and domain in self.eco_client.config.DOMAINS:
            searches.append(("domain", self.eco_client.config.DOMAINS[domain]))

        # Execute searches in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_key = {
                executor.submit(
                    self.eco_client.search,
                    goal,
                    user_id,
                    limit=ECO_LIMIT,
                    min_score=ECO_MIN_SCORE,
                ): key
                for key, user_id in searches
            }

            for future in as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    result[key] = future.result()
                except Exception as e:
                    print(
                        f"Warning: Eco search failed for {key}: {e}",
                        file=sys.stderr,
                    )
                    result[key] = []

        return result

    def _search_requirements(self, goal: str, domain: str | None = None) -> dict[str, list[dict]]:
        """Search requirements related to goal."""
        result = {
            "related": [],
            "unverified": [],
        }

        # Simple keyword matching for now
        keywords = goal.lower().split()

        for req in self.req_parser.requirements.values():
            # Check if keywords match
            req_text = f"{req.id} {req.title} {req.description}".lower()
            matches = sum(1 for kw in keywords if kw in req_text and len(kw) > 3)

            if matches >= 2 or (domain and req.domain.upper() == domain.upper()):
                result["related"].append(req.to_dict())

            # Collect unverified in domain
            if domain and req.domain.upper() == domain.upper():
                if req.status.name != "VERIFIED":
                    result["unverified"].append(req.to_dict())

        # Sort by relevance (number of keyword matches)
        def relevance(r):
            text = f"{r['id']} {r['title']}".lower()
            return sum(1 for kw in keywords if kw in text)

        result["related"].sort(key=relevance, reverse=True)

        return result

    def _search_issues(self, goal: str, domain: str | None = None) -> dict[str, list[dict]]:
        """Search bd issues related to goal."""
        result = {
            "related": [],
            "blocking": [],
        }

        try:
            # Get open issues
            proc = subprocess.run(
                ["bd", "--sandbox", "list", "--status", "open", "--json"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=10,
            )

            if proc.returncode != 0:
                return result

            issues = json.loads(proc.stdout)
            keywords = goal.lower().split()

            for issue in issues:
                title = issue.get("title", "").lower()
                desc = issue.get("description", "").lower()
                issue_text = f"{title} {desc}"

                # Check keyword matches
                matches = sum(1 for kw in keywords if kw in issue_text and len(kw) > 3)

                # Check domain label
                labels = issue.get("labels", [])
                domain_match = domain and any(
                    f"domain:{domain}" in label.lower() for label in labels
                )

                if matches >= 2 or domain_match:
                    result["related"].append(issue)

                # Check for blocking issues (status blocked or has blockers)
                if issue.get("status") == "blocked":
                    result["blocking"].append(issue)

            # Sort by priority
            result["related"].sort(key=lambda x: x.get("priority", 9))

        except Exception as e:
            print(f"Warning: Could not search bd issues: {e}", file=sys.stderr)

        return result

    def _find_relevant_files(self, goal: str, domain: str | None = None) -> list[str]:
        """Find potentially relevant files based on goal and domain."""
        files = []

        # Map domains to directories
        domain_dirs = {
            "firmware": ["firmware/"],
            "placer": ["temper-placer/"],
            "pcb": ["pcb/", "components/"],
        }

        # Search in domain directories
        search_dirs = domain_dirs.get(domain, []) if domain else []

        # Also search based on keywords
        keywords = [kw for kw in goal.lower().split() if len(kw) > 4]

        try:
            for search_dir in search_dirs or ["."]:
                dir_path = self.project_root / search_dir
                if not dir_path.exists():
                    continue

                # Find Python and C files
                for pattern in ["**/*.py", "**/*.c", "**/*.h", "**/*.md"]:
                    for f in dir_path.glob(pattern):
                        if f.is_file():
                            rel_path = str(f.relative_to(self.project_root))
                            # Skip test files and hidden dirs
                            if "test" in rel_path.lower() or "/." in rel_path:
                                continue
                            # Check if filename matches keywords
                            if any(kw in f.name.lower() for kw in keywords):
                                files.append(rel_path)
                            elif len(files) < 10:
                                files.append(rel_path)
        except Exception:
            pass

        return files[:20]

    def gather(
        self, goal: str, domain: str | None = None, role: str | None = None
    ) -> GatherContext:
        """Gather context for a goal.

        Args:
            goal: What you want to accomplish
            domain: Project domain (firmware, placer, pcb)
            role: Agent role (architect, coder, tester)

        Returns:
            GatherContext with collected information
        """
        timestamp = datetime.now().isoformat()

        # Search all sources
        eco_results = self._search_eco(goal, role, domain)
        req_results = self._search_requirements(goal, domain)
        issue_results = self._search_issues(goal, domain)
        files = self._find_relevant_files(goal, domain)

        return GatherContext(
            goal=goal,
            timestamp=timestamp,
            domain=domain,
            role=role,
            eco_legacy=eco_results["legacy"],
            eco_shared=eco_results["shared"],
            eco_role=eco_results["role"],
            eco_domain=eco_results["domain"],
            related_requirements=req_results["related"],
            unverified_requirements=req_results["unverified"],
            related_issues=issue_results["related"],
            blocking_issues=issue_results["blocking"],
            relevant_files=files,
        )


def main():
    """CLI interface for GATHER phase."""
    import argparse

    parser = argparse.ArgumentParser(
        description="GATHER phase - collect context for planning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Gather context for a goal
  python gather.py --goal "Implement PID improvements"

  # Gather with domain and role
  python gather.py --goal "Fix boundary loss" --domain placer --role architect

  # Output to file
  python gather.py --goal "Add new safety check" --domain firmware --output context.md

  # Output as JSON
  python gather.py --goal "Optimize heuristics" --json
""",
    )

    parser.add_argument(
        "--goal",
        "-g",
        type=str,
        required=True,
        help="Goal or objective to gather context for",
    )
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
    parser.add_argument("--output", "-o", type=str, help="Output file path (default: stdout)")
    parser.add_argument("--json", action="store_true", help="Output as JSON instead of markdown")
    parser.add_argument("--root", type=str, help="Project root directory")

    args = parser.parse_args()

    # Initialize gatherer
    root = Path(args.root) if args.root else None
    gatherer = GatherPhase(project_root=root)

    # Gather context
    print(f"Gathering context for: {args.goal}", file=sys.stderr)
    if args.domain:
        print(f"  Domain: {args.domain}", file=sys.stderr)
    if args.role:
        print(f"  Role: {args.role}", file=sys.stderr)
    print("", file=sys.stderr)

    context = gatherer.gather(args.goal, domain=args.domain, role=args.role)

    # Format output
    if args.json:
        output = json.dumps(context.to_dict(), indent=2)
    else:
        output = context.to_markdown()

    # Write output
    if args.output:
        Path(args.output).write_text(output)
        print(f"Context written to {args.output}", file=sys.stderr)
    else:
        print(output)

    # Summary
    print("", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    print("GATHER Summary:", file=sys.stderr)
    print(
        f"  Eco memories: {len(context.eco_legacy) + len(context.eco_shared) + len(context.eco_role) + len(context.eco_domain)}",
        file=sys.stderr,
    )
    print(f"  Related requirements: {len(context.related_requirements)}", file=sys.stderr)
    print(f"  Related issues: {len(context.related_issues)}", file=sys.stderr)
    print(f"  Relevant files: {len(context.relevant_files)}", file=sys.stderr)
    print("=" * 50, file=sys.stderr)


if __name__ == "__main__":
    main()

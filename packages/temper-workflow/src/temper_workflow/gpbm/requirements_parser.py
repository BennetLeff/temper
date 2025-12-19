#!/usr/bin/env python3
"""
Requirements parser for GPBM workflow.

Parses REQ-* requirements from markdown files and provides:
- Status tracking (verified, in_progress, not_started)
- Linking to bd issues
- Coverage statistics
- JSON export for tooling

Usage:
    # As library
    from gpbm.requirements_parser import RequirementsParser
    parser = RequirementsParser()
    reqs = parser.parse_all()

    # As CLI
    python requirements_parser.py --status
    python requirements_parser.py --unlinked
    python requirements_parser.py --json
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum


class RequirementStatus(Enum):
    """Requirement verification status."""

    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"
    DEFERRED = "DEFERRED"


class RequirementPriority(Enum):
    """Requirement priority level."""

    P0 = 0  # Critical
    P1 = 1  # High
    P2 = 2  # Medium
    P3 = 3  # Low


@dataclass
class Requirement:
    """Parsed requirement from markdown."""

    id: str
    title: str
    priority: RequirementPriority
    status: RequirementStatus
    description: str = ""
    validation: str = ""
    linked_issues: List[str] = field(default_factory=list)
    source_file: str = ""
    line_number: int = 0
    domain: str = ""
    subsystem: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority.name,
            "status": self.status.name,
            "description": self.description,
            "validation": self.validation,
            "linked_issues": self.linked_issues,
            "source_file": self.source_file,
            "line_number": self.line_number,
            "domain": self.domain,
            "subsystem": self.subsystem,
        }


class RequirementsParser:
    """Parse requirements from markdown files."""

    # Regex patterns for parsing
    REQ_HEADER_PATTERN = re.compile(r"^###\s+(REQ-[\w-]+):\s*(.+)$", re.MULTILINE)
    PRIORITY_PATTERN = re.compile(r"\*\*Priority:\*\*\s*(P[0-3])", re.IGNORECASE)
    STATUS_PATTERN = re.compile(r"\*\*Status:\*\*\s*(\w+)", re.IGNORECASE)
    VALIDATION_PATTERN = re.compile(
        r"\*\*Validation:\*\*\s*(.+?)(?:\n\*\*|\n---|\n###|\Z)", re.DOTALL
    )
    LINKED_ISSUES_PATTERN = re.compile(
        r"\*\*Linked Issues:\*\*\s*(.+?)(?:\n\*\*|\n---|\n###|\Z)", re.DOTALL
    )

    # Default paths relative to project root
    DEFAULT_PATHS = [
        "REQUIREMENTS.md",
        "docs/requirements/FIRMWARE_REQUIREMENTS.md",
        "docs/requirements/PLACER_REQUIREMENTS.md",
    ]

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize parser with project root directory."""
        self.project_root = project_root or self._find_project_root()
        self.requirements: Dict[str, Requirement] = {}

    def _find_project_root(self) -> Path:
        """Find project root by looking for .git or REQUIREMENTS.md."""
        cwd = Path.cwd()

        # Walk up to find project root
        for parent in [cwd] + list(cwd.parents):
            if (parent / ".git").exists() or (parent / "REQUIREMENTS.md").exists():
                return parent

        return cwd

    def _parse_req_id(self, req_id: str) -> tuple:
        """Parse requirement ID into components.

        REQ-FW-SM-01 -> (domain="FW", subsystem="SM", number="01")
        REQ-PLACER-OPT-01 -> (domain="PLACER", subsystem="OPT", number="01")
        """
        parts = req_id.replace("REQ-", "").split("-")

        if len(parts) >= 3:
            domain = parts[0]
            subsystem = parts[1]
            number = "-".join(parts[2:])
        elif len(parts) == 2:
            domain = parts[0]
            subsystem = ""
            number = parts[1]
        else:
            domain = parts[0] if parts else ""
            subsystem = ""
            number = ""

        return domain, subsystem, number

    def _parse_priority(self, text: str) -> RequirementPriority:
        """Parse priority from text."""
        match = self.PRIORITY_PATTERN.search(text)
        if match:
            p = match.group(1).upper()
            return RequirementPriority[p]
        return RequirementPriority.P2  # Default to medium

    def _parse_status(self, text: str) -> RequirementStatus:
        """Parse status from text."""
        match = self.STATUS_PATTERN.search(text)
        if match:
            status_str = match.group(1).upper().replace(" ", "_")
            try:
                return RequirementStatus[status_str]
            except KeyError:
                pass
        return RequirementStatus.NOT_STARTED

    def _parse_validation(self, text: str) -> str:
        """Parse validation method from text."""
        match = self.VALIDATION_PATTERN.search(text)
        if match:
            return match.group(1).strip()
        return ""

    def _parse_linked_issues(self, text: str) -> List[str]:
        """Parse linked bd issues from text."""
        match = self.LINKED_ISSUES_PATTERN.search(text)
        if match:
            issues_text = match.group(1).strip()
            if issues_text.lower() in [
                "(none)",
                "none",
                "-",
                "(baseline requirement)",
                "(create issue)",
                "tbd",
            ]:
                return []
            # Extract issue IDs (temper-xxx, bd-xxx patterns)
            issue_pattern = re.compile(r"(temper-[\w.]+|bd-[\w.]+)", re.IGNORECASE)
            return issue_pattern.findall(issues_text)
        return []

    def parse_file(self, filepath: Path) -> List[Requirement]:
        """Parse requirements from a single markdown file."""
        if not filepath.exists():
            return []

        content = filepath.read_text()
        requirements = []

        # Split into sections by requirement headers
        sections = re.split(r"(^###\s+REQ-[\w-]+:.+$)", content, flags=re.MULTILINE)

        current_req_id = None
        current_title = None

        for i, section in enumerate(sections):
            # Check if this is a header
            header_match = self.REQ_HEADER_PATTERN.match(section.strip())
            if header_match:
                current_req_id = header_match.group(1)
                current_title = header_match.group(2).strip()
                continue

            # If we have a current requirement, parse its content
            if current_req_id and section.strip():
                domain, subsystem, _ = self._parse_req_id(current_req_id)

                req = Requirement(
                    id=current_req_id,
                    title=current_title or "",
                    priority=self._parse_priority(section),
                    status=self._parse_status(section),
                    description=section.strip()[:500],  # First 500 chars
                    validation=self._parse_validation(section),
                    linked_issues=self._parse_linked_issues(section),
                    source_file=str(filepath.relative_to(self.project_root)),
                    line_number=content[: content.find(current_req_id)].count("\n") + 1,
                    domain=domain,
                    subsystem=subsystem,
                )
                requirements.append(req)
                current_req_id = None
                current_title = None

        return requirements

    def parse_all(self, paths: Optional[List[str]] = None) -> Dict[str, Requirement]:
        """Parse all requirements from default or specified paths."""
        paths = paths or self.DEFAULT_PATHS
        self.requirements = {}

        for path_str in paths:
            filepath = self.project_root / path_str
            reqs = self.parse_file(filepath)
            for req in reqs:
                self.requirements[req.id] = req

        return self.requirements

    def get_statistics(self) -> Dict[str, Any]:
        """Get coverage statistics."""
        if not self.requirements:
            self.parse_all()

        total = len(self.requirements)
        if total == 0:
            return {"total": 0, "by_status": {}, "by_priority": {}, "by_domain": {}}

        by_status = {}
        by_priority = {}
        by_domain = {}
        linked = 0

        for req in self.requirements.values():
            # Count by status
            status_name = req.status.name
            by_status[status_name] = by_status.get(status_name, 0) + 1

            # Count by priority
            priority_name = req.priority.name
            by_priority[priority_name] = by_priority.get(priority_name, 0) + 1

            # Count by domain
            by_domain[req.domain] = by_domain.get(req.domain, 0) + 1

            # Count linked
            if req.linked_issues:
                linked += 1

        return {
            "total": total,
            "verified": by_status.get("VERIFIED", 0),
            "in_progress": by_status.get("IN_PROGRESS", 0),
            "not_started": by_status.get("NOT_STARTED", 0),
            "blocked": by_status.get("BLOCKED", 0),
            "deferred": by_status.get("DEFERRED", 0),
            "linked_to_issues": linked,
            "verified_pct": round(100 * by_status.get("VERIFIED", 0) / total, 1),
            "linked_pct": round(100 * linked / total, 1),
            "by_status": by_status,
            "by_priority": by_priority,
            "by_domain": by_domain,
        }

    def get_unlinked(self) -> List[Requirement]:
        """Get requirements not linked to any bd issues."""
        if not self.requirements:
            self.parse_all()

        return [req for req in self.requirements.values() if not req.linked_issues]

    def get_by_status(self, status: RequirementStatus) -> List[Requirement]:
        """Get requirements by status."""
        if not self.requirements:
            self.parse_all()

        return [req for req in self.requirements.values() if req.status == status]

    def get_by_priority(self, priority: RequirementPriority) -> List[Requirement]:
        """Get requirements by priority."""
        if not self.requirements:
            self.parse_all()

        return [req for req in self.requirements.values() if req.priority == priority]

    def get_by_domain(self, domain: str) -> List[Requirement]:
        """Get requirements by domain."""
        if not self.requirements:
            self.parse_all()

        return [
            req
            for req in self.requirements.values()
            if req.domain.upper() == domain.upper()
        ]

    def find_by_issue(self, issue_id: str) -> List[Requirement]:
        """Find requirements linked to a specific bd issue."""
        if not self.requirements:
            self.parse_all()

        return [
            req for req in self.requirements.values() if issue_id in req.linked_issues
        ]

    def to_json(self) -> str:
        """Export all requirements as JSON."""
        if not self.requirements:
            self.parse_all()

        return json.dumps(
            {req_id: req.to_dict() for req_id, req in self.requirements.items()},
            indent=2,
        )


def format_status_report(parser: RequirementsParser) -> str:
    """Format a human-readable status report."""
    stats = parser.get_statistics()

    lines = [
        "=" * 60,
        "REQUIREMENTS STATUS REPORT",
        "=" * 60,
        "",
        f"Total Requirements: {stats['total']}",
        "",
        "By Status:",
        f"  ✓ Verified:     {stats['verified']:3d} ({stats['verified_pct']:.1f}%)",
        f"  → In Progress:  {stats['in_progress']:3d}",
        f"  ○ Not Started:  {stats['not_started']:3d}",
        f"  ✗ Blocked:      {stats['blocked']:3d}",
        f"  ◇ Deferred:     {stats['deferred']:3d}",
        "",
        "By Priority:",
    ]

    for p in ["P0", "P1", "P2", "P3"]:
        count = stats["by_priority"].get(p, 0)
        lines.append(f"  {p}: {count:3d}")

    lines.extend(
        [
            "",
            "By Domain:",
        ]
    )

    for domain, count in sorted(stats["by_domain"].items()):
        lines.append(f"  {domain}: {count:3d}")

    lines.extend(
        [
            "",
            f"Linked to Issues: {stats['linked_to_issues']} ({stats['linked_pct']:.1f}%)",
            "",
            "=" * 60,
        ]
    )

    return "\n".join(lines)


def format_unlinked_report(parser: RequirementsParser) -> str:
    """Format report of unlinked requirements."""
    unlinked = parser.get_unlinked()

    if not unlinked:
        return "All requirements are linked to bd issues."

    lines = [
        f"Found {len(unlinked)} unlinked requirements:",
        "",
    ]

    # Group by priority
    by_priority = {}
    for req in unlinked:
        p = req.priority.name
        if p not in by_priority:
            by_priority[p] = []
        by_priority[p].append(req)

    for priority in ["P0", "P1", "P2", "P3"]:
        reqs = by_priority.get(priority, [])
        if reqs:
            lines.append(f"{priority} ({len(reqs)}):")
            for req in reqs:
                lines.append(f"  {req.id}: {req.title[:50]}")
            lines.append("")

    return "\n".join(lines)


def main():
    """CLI interface for requirements parser."""
    import argparse

    argparser = argparse.ArgumentParser(
        description="Parse and analyze REQ-* requirements from markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show status report
  python requirements_parser.py --status
  
  # Show unlinked requirements
  python requirements_parser.py --unlinked
  
  # Export as JSON
  python requirements_parser.py --json > requirements.json
  
  # Find requirements for a domain
  python requirements_parser.py --domain FW
  
  # Find requirements linked to an issue
  python requirements_parser.py --issue temper-5xc.1.1
""",
    )

    argparser.add_argument("--status", action="store_true", help="Show status report")
    argparser.add_argument(
        "--unlinked", action="store_true", help="Show requirements not linked to issues"
    )
    argparser.add_argument(
        "--json", action="store_true", help="Export all requirements as JSON"
    )
    argparser.add_argument(
        "--domain", type=str, help="Filter by domain (FW, PLACER, SYS, etc.)"
    )
    argparser.add_argument(
        "--priority",
        type=str,
        choices=["P0", "P1", "P2", "P3"],
        help="Filter by priority",
    )
    argparser.add_argument(
        "--issue", type=str, help="Find requirements linked to a bd issue"
    )
    argparser.add_argument(
        "--paths", nargs="*", help="Custom paths to requirements files"
    )
    argparser.add_argument("--root", type=str, help="Project root directory")

    args = argparser.parse_args()

    # Initialize parser
    root = Path(args.root) if args.root else None
    parser = RequirementsParser(project_root=root)
    parser.parse_all(args.paths)

    # Handle commands
    if args.json:
        print(parser.to_json())
    elif args.status:
        print(format_status_report(parser))
    elif args.unlinked:
        print(format_unlinked_report(parser))
    elif args.domain:
        reqs = parser.get_by_domain(args.domain)
        print(f"Requirements for domain {args.domain.upper()}:\n")
        for req in reqs:
            status_icon = {"VERIFIED": "✓", "IN_PROGRESS": "→", "NOT_STARTED": "○"}.get(
                req.status.name, "?"
            )
            print(f"  {status_icon} {req.id}: {req.title}")
    elif args.priority:
        priority = RequirementPriority[args.priority]
        reqs = parser.get_by_priority(priority)
        print(f"Requirements with priority {args.priority}:\n")
        for req in reqs:
            status_icon = {"VERIFIED": "✓", "IN_PROGRESS": "→", "NOT_STARTED": "○"}.get(
                req.status.name, "?"
            )
            print(f"  {status_icon} {req.id}: {req.title}")
    elif args.issue:
        reqs = parser.find_by_issue(args.issue)
        if reqs:
            print(f"Requirements linked to {args.issue}:\n")
            for req in reqs:
                print(f"  {req.id}: {req.title}")
        else:
            print(f"No requirements linked to {args.issue}")
    else:
        # Default: show status
        print(format_status_report(parser))


if __name__ == "__main__":
    main()

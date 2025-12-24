#!/usr/bin/env python3
"""
HYPOTHESIZE phase implementation for GPBM workflow.

Creates and validates hypothesis structures for experiment and validation issues.
Ensures scientific rigor by requiring:
- Null hypothesis (H0) and alternative hypothesis (H1)
- Expected effect size
- Pre-registered predictions
- Decision criteria

This phase sits between GATHER and PLAN for experimental work.

Usage:
    # As CLI
    python hypothesize.py --goal "Test if spread_loss weight affects routing"
    python hypothesize.py --validate temper-xxx  # Validate existing issue

    # As library
    from gpbm.hypothesize import HypothesizePhase
    hyp = HypothesizePhase()
    hypothesis = hyp.create("Test spread_loss effect", domain="placer")
"""

import argparse
import json
import os

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from ..utils import CommandRunner, BDCommand
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "packages" / "temper-workflow" / "src"))
    from temper_workflow.utils import CommandRunner, BDCommand



@dataclass
class Prediction:
    """A pre-registered prediction."""

    statement: str
    metric: str
    expected_direction: str  # "increase", "decrease", "no_change"
    expected_magnitude: Optional[str] = None  # e.g., ">=5%", "<10ms"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "statement": self.statement,
            "metric": self.metric,
            "expected_direction": self.expected_direction,
            "expected_magnitude": self.expected_magnitude,
        }


@dataclass
class DecisionCriteria:
    """Criteria for accepting/rejecting hypotheses."""

    accept_h1_if: str  # e.g., "p < 0.05 AND effect_size > 5%"
    accept_h0_if: str  # e.g., "p >= 0.05 OR effect_size < 5%"
    inconclusive_if: Optional[str] = None  # e.g., "sample_size < 10"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "accept_h1_if": self.accept_h1_if,
            "accept_h0_if": self.accept_h0_if,
            "inconclusive_if": self.inconclusive_if,
        }


@dataclass
class ControlCondition:
    """A variable held constant during experiment."""

    variable: str
    value: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "variable": self.variable,
            "value": self.value,
            "rationale": self.rationale,
        }


@dataclass
class Hypothesis:
    """A complete hypothesis structure for scientific rigor."""

    goal: str
    timestamp: str

    # Core hypotheses
    null_hypothesis: str  # H0: What we expect if no effect
    alternative_hypothesis: str  # H1: What we expect if there is an effect

    # Effect size and power
    expected_effect_size: str  # e.g., ">=5% improvement in routing completion"
    minimum_detectable_effect: Optional[str] = None  # Smallest meaningful change
    sample_size: int = 10  # Number of runs per condition
    random_seeds: list[int] = field(default_factory=lambda: [42, 123, 456, 789, 101112])

    # Pre-registration
    predictions: list[Prediction] = field(default_factory=list)
    decision_criteria: Optional[DecisionCriteria] = None

    # Control conditions
    control_conditions: list[ControlCondition] = field(default_factory=list)

    # Independent variables (what we manipulate)
    independent_variables: list[dict[str, Any]] = field(default_factory=list)

    # Dependent variables (what we measure)
    dependent_variables: list[dict[str, Any]] = field(default_factory=list)

    # Metadata
    domain: Optional[str] = None
    role: Optional[str] = None
    related_issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "goal": self.goal,
            "timestamp": self.timestamp,
            "hypotheses": {
                "null": self.null_hypothesis,
                "alternative": self.alternative_hypothesis,
            },
            "effect_size": {
                "expected": self.expected_effect_size,
                "minimum_detectable": self.minimum_detectable_effect,
            },
            "statistical_design": {
                "sample_size": self.sample_size,
                "random_seeds": self.random_seeds,
            },
            "pre_registration": {
                "predictions": [p.to_dict() for p in self.predictions],
                "decision_criteria": self.decision_criteria.to_dict()
                if self.decision_criteria
                else None,
            },
            "control_conditions": [c.to_dict() for c in self.control_conditions],
            "independent_variables": self.independent_variables,
            "dependent_variables": self.dependent_variables,
            "metadata": {
                "domain": self.domain,
                "role": self.role,
                "related_issues": self.related_issues,
            },
        }

    def to_markdown(self) -> str:
        """Format as markdown for issue description."""
        lines = [
            f"# Hypothesis: {self.goal}",
            "",
            f"**Pre-registered:** {self.timestamp}",
            f"**Domain:** {self.domain or 'General'}",
            "",
            "## Hypotheses",
            "",
            "### Null Hypothesis (H0)",
            f"> {self.null_hypothesis}",
            "",
            "### Alternative Hypothesis (H1)",
            f"> {self.alternative_hypothesis}",
            "",
            "### Expected Effect Size",
            f"{self.expected_effect_size}",
            "",
        ]

        if self.minimum_detectable_effect:
            lines.extend(
                [
                    "### Minimum Detectable Effect",
                    f"{self.minimum_detectable_effect}",
                    "",
                ]
            )

        lines.extend(
            [
                "## Pre-Registration",
                "",
                "### Predictions",
            ]
        )

        for i, pred in enumerate(self.predictions, 1):
            lines.append(f"{i}. **{pred.metric}**: {pred.statement}")
            if pred.expected_magnitude:
                lines.append(
                    f"   - Expected: {pred.expected_direction} by {pred.expected_magnitude}"
                )
            else:
                lines.append(f"   - Expected: {pred.expected_direction}")

        lines.append("")

        if self.decision_criteria:
            lines.extend(
                [
                    "### Decision Criteria",
                    f"- **Accept H1 if:** {self.decision_criteria.accept_h1_if}",
                    f"- **Accept H0 if:** {self.decision_criteria.accept_h0_if}",
                ]
            )
            if self.decision_criteria.inconclusive_if:
                lines.append(f"- **Inconclusive if:** {self.decision_criteria.inconclusive_if}")
            lines.append("")

        lines.extend(
            [
                "## Statistical Design",
                "",
                f"- **Sample size:** {self.sample_size} runs per condition",
                f"- **Random seeds:** `{self.random_seeds}`",
                "",
            ]
        )

        if self.control_conditions:
            lines.extend(
                [
                    "## Control Conditions",
                    "",
                    "| Variable | Value | Rationale |",
                    "|----------|-------|-----------|",
                ]
            )
            for cc in self.control_conditions:
                lines.append(f"| {cc.variable} | {cc.value} | {cc.rationale} |")
            lines.append("")

        if self.independent_variables:
            lines.extend(
                [
                    "## Independent Variables",
                    "",
                    "| Variable | Levels | Description |",
                    "|----------|--------|-------------|",
                ]
            )
            for iv in self.independent_variables:
                levels = ", ".join(str(l) for l in iv.get("levels", []))
                lines.append(
                    f"| {iv.get('name', 'unknown')} | {levels} | {iv.get('description', '')} |"
                )
            lines.append("")

        if self.dependent_variables:
            lines.extend(
                [
                    "## Dependent Variables (Metrics)",
                    "",
                    "| Metric | Definition | Target |",
                    "|--------|------------|--------|",
                ]
            )
            for dv in self.dependent_variables:
                lines.append(
                    f"| {dv.get('metric', 'unknown')} | {dv.get('definition', '')} | {dv.get('target', '')} |"
                )
            lines.append("")

        if self.related_issues:
            lines.extend(
                [
                    "## Related Issues",
                    "",
                ]
            )
            for issue in self.related_issues:
                lines.append(f"- {issue}")
            lines.append("")

        return "\n".join(lines)

    def to_yaml_block(self) -> str:
        """Generate YAML block for issue description."""
        lines = [
            "```yaml",
            "hypothesis:",
            f'  h0: "{self.null_hypothesis}"',
            f'  h1: "{self.alternative_hypothesis}"',
            f'  effect_size: "{self.expected_effect_size}"',
            f"  sample_size: {self.sample_size}",
            f"  seeds: {self.random_seeds}",
        ]

        if self.decision_criteria:
            lines.extend(
                [
                    "  decision:",
                    f'    accept_h1: "{self.decision_criteria.accept_h1_if}"',
                    f'    accept_h0: "{self.decision_criteria.accept_h0_if}"',
                ]
            )

        lines.append("```")
        return "\n".join(lines)


@dataclass
class ValidationResult:
    """Result of validating an issue's hypothesis structure."""

    issue_id: str
    is_valid: bool
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    score: float = 0.0  # 0-1 completeness score

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "issue_id": self.issue_id,
            "is_valid": self.is_valid,
            "missing_fields": self.missing_fields,
            "warnings": self.warnings,
            "score": self.score,
        }


class HypothesizePhase:
    """HYPOTHESIZE phase of GPBM workflow."""

    REQUIRED_FIELDS = [
        "null_hypothesis",
        "alternative_hypothesis",
        "expected_effect_size",
        "sample_size",
    ]

    RECOMMENDED_FIELDS = [
        "predictions",
        "decision_criteria",
        "control_conditions",
        "random_seeds",
    ]

    def __init__(self, repo_root: Optional[Path] = None):
        """Initialize hypothesize phase."""
        self.repo_root = repo_root or CommandRunner._find_project_root()


    def create(
        self,
        goal: str,
        h0: str,
        h1: str,
        effect_size: str,
        domain: Optional[str] = None,
        role: Optional[str] = None,
        sample_size: int = 10,
        seeds: Optional[list[int]] = None,
    ) -> Hypothesis:
        """Create a new hypothesis structure."""
        timestamp = datetime.now().isoformat()

        hypothesis = Hypothesis(
            goal=goal,
            timestamp=timestamp,
            null_hypothesis=h0,
            alternative_hypothesis=h1,
            expected_effect_size=effect_size,
            sample_size=sample_size,
            random_seeds=seeds or [42, 123, 456, 789, 101112],
            domain=domain,
            role=role,
        )

        return hypothesis

    def create_interactive(self, goal: str, domain: Optional[str] = None) -> Hypothesis:
        """Create hypothesis interactively with prompts."""
        print(f"\n=== Creating Hypothesis for: {goal} ===\n")

        # Get H0
        print("Null Hypothesis (H0):")
        print("  What do we expect if there is NO effect?")
        print("  Example: 'Reducing spread_loss weight has no effect on routing completion'")
        h0 = input("H0: ").strip()

        # Get H1
        print("\nAlternative Hypothesis (H1):")
        print("  What do we expect if there IS an effect?")
        print("  Example: 'Reducing spread_loss weight improves routing completion by >=5%'")
        h1 = input("H1: ").strip()

        # Get effect size
        print("\nExpected Effect Size:")
        print("  What is the minimum meaningful change?")
        print("  Example: '>=5% improvement in routing completion'")
        effect_size = input("Effect size: ").strip()

        # Get sample size
        print("\nSample Size:")
        print("  How many runs per condition? (default: 10)")
        sample_input = input("Sample size [10]: ").strip()
        sample_size = int(sample_input) if sample_input else 10

        return self.create(
            goal=goal,
            h0=h0,
            h1=h1,
            effect_size=effect_size,
            domain=domain,
            sample_size=sample_size,
        )

    def validate_issue(self, issue_id: str) -> ValidationResult:
        """Validate that an issue has proper hypothesis structure."""
        # Get issue from bd
        try:
            result = BDCommand.show(issue_id, "--json"],
                capture_output=True,
                text=True,
                check=True,
                cwd=str(self.repo_root),
            )
            issues = json.loads(result.stdout)
            if not issues:
                return ValidationResult(
                    issue_id=issue_id,
                    is_valid=False,
                    missing_fields=["issue not found"],
                    score=0.0,
                )
            issue = issues[0]
        except ( json.JSONDecodeError) as e:
            return ValidationResult(
                issue_id=issue_id,
                is_valid=False,
                missing_fields=[f"error: {e}"],
                score=0.0,
            )

        description = issue.get("description", "")
        missing = []
        warnings = []
        found = 0
        total = len(self.REQUIRED_FIELDS) + len(self.RECOMMENDED_FIELDS)

        # Check required fields
        required_patterns = {
            "null_hypothesis": [r"(?i)null\s+hypothesis", r"(?i)\bH0\b", r"(?i)H₀"],
            "alternative_hypothesis": [
                r"(?i)alternative\s+hypothesis",
                r"(?i)\bH1\b",
                r"(?i)H₁",
            ],
            "expected_effect_size": [r"(?i)effect\s+size", r"(?i)expected.*\d+%"],
            "sample_size": [r"(?i)sample\s+size", r"(?i)\d+\s+runs"],
        }

        import re

        for field, patterns in required_patterns.items():
            if any(re.search(p, description) for p in patterns):
                found += 1
            else:
                missing.append(field)

        # Check recommended fields
        recommended_patterns = {
            "predictions": [r"(?i)prediction", r"(?i)pre-register"],
            "decision_criteria": [r"(?i)accept\s+H[01]", r"(?i)decision\s+criteria"],
            "control_conditions": [r"(?i)control\s+condition", r"(?i)held\s+constant"],
            "random_seeds": [r"(?i)seed", r"\b42\b.*\b123\b"],
        }

        for field, patterns in recommended_patterns.items():
            if any(re.search(p, description) for p in patterns):
                found += 1
            else:
                warnings.append(f"Missing recommended: {field}")

        score = found / total if total > 0 else 0.0
        is_valid = len(missing) == 0

        return ValidationResult(
            issue_id=issue_id,
            is_valid=is_valid,
            missing_fields=missing,
            warnings=warnings,
            score=score,
        )

    def validate_issues_by_label(self, label: str) -> list[ValidationResult]:
        """Validate all issues with a given label."""
        try:
            result = BDCommand.list_issues(status="open", label=f"{label}", cwd=str(self.repo_root))

            result = BDCommand.list_issues(status="open", label=f"{label}", cwd=str(self.repo_root))

            result = BDCommand.list_issues(status="open", label=f"{label}", cwd=str(self.repo_root))

            result = BDCommand.list_issues(status="open", label=f"{label}", cwd=str(self.repo_root))

            result = BDCommand.list_issues(status="open", label=f"{label}", cwd=str(self.repo_root))

            result = BDCommand.list_issues(status="open", label=f"{label}", cwd=str(self.repo_root))

            result = BDCommand.list_issues(status="open", label=f"{label}", cwd=str(self.repo_root))

            issues = json.loads(result.stdout)

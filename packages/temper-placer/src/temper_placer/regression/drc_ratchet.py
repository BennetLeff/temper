"""DRC ratchet CI gate.

Loads drc_ceiling.json, runs DRC on target boards, and enforces
a monotonically-non-increasing ceiling on DRC violation counts.

Supports two backends:
  - ``rust`` (default): uses ``temper_drc_rs.run_drc()`` with the
    parsed-PCB-via-KiCad-parser path.
  - ``kicad-cli``: uses the KiCad CLI DRC via
    ``temper_placer.validation.drc_runner.run_drc()``.

When the Rust backend is selected but ``temper_drc_rs`` is not
installed, the check fails with a clear error message.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DrcCeilingEntry:
    """A single board entry in the DRC ceiling file."""

    board_id: str
    path: str
    error_ceiling: int
    warning_ceiling: int
    violations_by_type: dict[str, int] = field(default_factory=dict)


@dataclass
class DrcCategoryFailure:
    """One violation-type category that exceeded its ceiling.

    ``is_new`` distinguishes a category absent from ``violations_by_type``
    entirely (an implicit ceiling of 0, by design -- see drc_ceiling.json's
    ``_march`` notes) from one that is present in the file but regressed
    past its recorded ceiling. Both are real ceiling violations, but a
    brand-new violation class means the board grew a defect *type* the
    ratchet has never seen before, which is a materially different signal
    from "more of a kind we already track" and must not be folded into the
    same bucket silently.
    """

    rule: str
    count: int
    allowed: int
    is_new: bool

    @property
    def delta(self) -> int:
        return self.count - self.allowed


@dataclass
class DrcRatchetResult:
    """Result of a DRC ratchet check.

    A failing result may fail along more than one dimension at once
    (aggregate errors, aggregate warnings, and/or one or more per-type
    categories) -- ``message`` composes all of them into one human-readable
    report. ``category_failures`` and the two ``aggregate_*_delta`` fields
    carry the same information in structured form for callers that want it
    (e.g. a future CI step-summary table) without re-parsing ``message``.
    Existing consumers (``scripts/ci_check_drc.py``, the test suite) only
    read ``.passed``/``.message``/``.exit_code`` and are unaffected by the
    additional fields.
    """

    passed: bool
    board_id: str
    message: str
    exit_code: int = 0
    violation_deltas: dict[str, int] = field(default_factory=dict)
    category_failures: list[DrcCategoryFailure] = field(default_factory=list)
    aggregate_error_delta: int = 0
    aggregate_warning_delta: int = 0


class DrcRatchet:
    """Enforces DRC ceiling via committed JSON file.

    Args:
        ceiling_path: Path to ``drc_ceiling.json``.
        backend: ``"rust"`` (default) to use the Rust DRC engine via
            ``temper_drc_rs.run_drc()``, or ``"kicad-cli"`` to use
            KiCad's CLI DRC.
    """

    def __init__(self, ceiling_path: Path, backend: str = "rust"):
        self.ceiling_path = Path(ceiling_path)
        self.backend = backend
        self.entries: dict[str, DrcCeilingEntry] = {}

    def load(self) -> None:
        if not self.ceiling_path.exists():
            return

        with open(self.ceiling_path) as f:
            data = json.load(f)

        for entry in data.get("boards", []):
            board_id = entry["board_id"]
            self.entries[board_id] = DrcCeilingEntry(
                board_id=board_id,
                path=entry["path"],
                error_ceiling=entry.get("error_ceiling", 0),
                warning_ceiling=entry.get("warning_ceiling", 0),
                violations_by_type=entry.get("violations_by_type", {}),
            )

    def check(self, repo_root: Path) -> list[DrcRatchetResult]:
        results: list[DrcRatchetResult] = []

        for board_id, entry in self.entries.items():
            pcb_path = repo_root / entry.path
            result = self._check_board(board_id, pcb_path, entry)
            results.append(result)

        return results

    def _run_rust_drc(self, pcb_path: Path) -> tuple[int, int]:
        """Run the Rust DRC engine on a PCB file.

        Returns:
            (error_count, warning_count)

        Raises:
            ImportError: If ``temper_drc_rs`` is not installed.
            Exception: On parse/DRC failure.
        """
        import temper_drc_rs

        from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

        parsed = parse_kicad_pcb_v6(pcb_path)

        # ── Build board_dict ────────────────────────────────────────────
        components = []
        for c in parsed.components:
            x, y = c.initial_position or (0.0, 0.0)
            rotation = float(c.initial_rotation * 90) if c.initial_rotation is not None else 0.0
            side = "bottom" if c.initial_side is not None and c.initial_side == 1 else "top"
            fp_lower = c.footprint.lower() if c.footprint else ""
            if any(p in fp_lower for p in ("tht", "through", "pin", "dip")):
                package_type = "tht"
            elif "to-247" in fp_lower or "to247" in fp_lower:
                package_type = "to247"
            elif "to-220" in fp_lower or "to220" in fp_lower:
                package_type = "to220"
            elif "bga" in fp_lower:
                package_type = "bga"
            elif "qfn" in fp_lower:
                package_type = "qfn"
            elif "qfp" in fp_lower or "tqfp" in fp_lower:
                package_type = "qfp"
            elif "dpak" in fp_lower or "d2pak" in fp_lower:
                package_type = "dpak"
            else:
                package_type = "smd"

            components.append(
                {
                    "ref": c.ref,
                    "x": x,
                    "y": y,
                    "rot": rotation,
                    "side": side,
                    "width": float(c.width),
                    "height": float(c.height),
                    "net_class": c.net_class,
                    "package_type": package_type,
                    "power_dissipation_w": None,
                    "is_magnetic": False,
                    "is_electrolytic": False,
                    "vent_direction": None,
                    "footprint_polygon": None,
                    "is_mechanical": c.ref.startswith("MH"),
                }
            )

        nets: dict[str, list[str]] = {}
        net_classes: dict[str, str] = {}
        for net in parsed.nets:
            comp_refs = list({ref for ref, _ in net.pins})
            nets[net.name] = comp_refs
            net_classes[net.name] = net.net_class

        net_class_rules: dict[str, dict] = {}
        for class_name, rules in parsed.design_rules.net_classes.items():
            net_class_rules[class_name] = {
                "trace_width_mm": rules.trace_width_mm,
                "clearance_mm": rules.clearance_mm,
                "creepage_mm": None,
                "voltage_v": None,
                "max_current_rating": None,
                "safety_category": None,
                "required_layer": None,
                "routing_strategy": None,
            }

        board_dict = {
            "board": {
                "width_mm": float(parsed.board.width),
                "height_mm": float(parsed.board.height),
                "margin_mm": 3.0,
            },
            "components": components,
            "nets": nets,
            "net_classes": net_classes,
            "net_class_rules": net_class_rules,
        }

        # ── Build constraints_dict ──────────────────────────────────────
        constraints_dict: dict[str, Any] = {
            "clearances": [],
            "zones": [],
            "critical_loops": [],
            "noise_domains": [],
            "isolation_barriers": [],
            "thermal_properties": [],
            "matched_length_groups": [],
            "snubber_requirements": [],
            "bleed_resistor": None,
            "skin_effect_derating": None,
            "hv_clearance_mm": 10.0,
            "board_width": float(parsed.board.width),
            "board_height": float(parsed.board.height),
        }

        violations = temper_drc_rs.run_drc(board_dict, constraints_dict)

        errors = sum(
            1 for v in violations if v.get("severity", "").upper() in ("ERROR", "CRITICAL")
        )
        warnings = sum(1 for v in violations if v.get("severity", "").upper() == "WARNING")

        return errors, warnings

    def _check_board(
        self, board_id: str, pcb_path: Path, entry: DrcCeilingEntry
    ) -> DrcRatchetResult:
        if not pcb_path.exists():
            return DrcRatchetResult(
                passed=False,
                board_id=board_id,
                message=f"PCB file not found: {pcb_path}",
                exit_code=1,
            )

        # Per-error-type counts, when the backend can supply them. None means
        # "this backend cannot break errors down", which is distinct from "no
        # violations" and must never be treated as an all-clear.
        current_by_type: dict[str, int] | None = None

        try:
            if self.backend == "rust":
                current_errors, current_warnings = self._run_rust_drc(pcb_path)
            elif self.backend == "kicad-cli":
                from temper_placer.validation._drc_api import run_drc

                drc_result = run_drc(pcb_path)
                current_errors = drc_result.error_count
                current_warnings = drc_result.warning_count
                current_by_type = {}
                for err in drc_result.errors:
                    rule = err.rule or "unknown"
                    current_by_type[rule] = current_by_type.get(rule, 0) + 1
            else:
                return DrcRatchetResult(
                    passed=False,
                    board_id=board_id,
                    message=f"Unknown DRC backend: {self.backend}",
                    exit_code=1,
                )
        except Exception as e:
            return DrcRatchetResult(
                passed=False,
                board_id=board_id,
                message=f"DRC ({self.backend}) failed: {e}",
                exit_code=1,
            )

        # Evaluate every ceiling dimension -- aggregate errors, aggregate
        # warnings, and per-type -- before deciding pass/fail. A failing run
        # must show the complete picture in one shot: returning on the first
        # exceeded dimension (the previous behavior) hid the per-type
        # breakdown -- exactly the categories most worth seeing -- whenever
        # the aggregate itself was also exceeded. See
        # docs/evidence/2026-07-27-drc-truth-gate-discrepancy.md.
        aggregate_failures: list[str] = []

        error_delta = current_errors - entry.error_ceiling
        if error_delta > 0:
            aggregate_failures.append(
                f"errors {current_errors} exceeds ceiling {entry.error_ceiling} (+{error_delta})"
            )

        warning_delta = current_warnings - entry.warning_ceiling
        if warning_delta > 0:
            aggregate_failures.append(
                f"warnings {current_warnings} exceeds ceiling {entry.warning_ceiling} (+{warning_delta})"
            )

        # Per-type ceilings. `violations_by_type` is an exhaustive record of the
        # error categories this board is allowed to have, and how many of each.
        # Anything absent from it has an implicit ceiling of zero, so a brand
        # new violation category cannot arrive for free under the aggregate.
        # This is what lets categories be driven to zero independently --
        # notably `clearance`, where the aggregate ceiling is far too coarse to
        # notice a HighVoltage net at 0.336mm against a 2.0mm requirement.
        category_failures: list[DrcCategoryFailure] = []
        if entry.violations_by_type and current_by_type is not None:
            for rule, count in sorted(current_by_type.items()):
                allowed = entry.violations_by_type.get(rule, 0)
                if count > allowed:
                    category_failures.append(
                        DrcCategoryFailure(
                            rule=rule,
                            count=count,
                            allowed=allowed,
                            is_new=rule not in entry.violations_by_type,
                        )
                    )

        if aggregate_failures or category_failures:
            lines = [f"{board_id}: DRC FAIL"]
            for failure in aggregate_failures:
                lines.append(f"  aggregate {failure}")
            if category_failures:
                new_failures = [c for c in category_failures if c.is_new]
                regressed_failures = [c for c in category_failures if not c.is_new]
                n = len(category_failures)
                lines.append(
                    f"  per-type: {n} categor{'y' if n == 1 else 'ies'} over "
                    f"ceiling ({len(new_failures)} new, {len(regressed_failures)} "
                    "regressed):"
                )
                for c in new_failures + regressed_failures:
                    tag = "NEW" if c.is_new else "   "
                    lines.append(f"    [{tag}] {c.rule} {c.count} > {c.allowed} (+{c.delta})")
            return DrcRatchetResult(
                passed=False,
                board_id=board_id,
                message="\n".join(lines),
                exit_code=1,
                violation_deltas={c.rule: c.delta for c in category_failures},
                category_failures=category_failures,
                aggregate_error_delta=max(error_delta, 0),
                aggregate_warning_delta=max(warning_delta, 0),
            )

        slack = entry.error_ceiling - current_errors
        slack_note = (
            f" [{slack} error(s) of unratcheted slack -- lower error_ceiling to "
            f"{current_errors} to lock this in]"
            if slack > 0
            else ""
        )
        return DrcRatchetResult(
            passed=True,
            board_id=board_id,
            message=(
                f"{board_id}: DRC {current_errors}/{entry.error_ceiling} errors, "
                f"{current_warnings}/{entry.warning_ceiling} warnings within ceiling"
                f"{slack_note}"
            ),
        )

    def detect_ceiling_raise(
        self, old_ceiling: dict, new_ceiling: dict, commit_message: str = ""
    ) -> DrcRatchetResult | None:
        """Detect if ceiling was raised without approval."""
        old_boards = {b["board_id"]: b for b in old_ceiling.get("boards", [])}
        new_boards = {b["board_id"]: b for b in new_ceiling.get("boards", [])}

        for board_id, new_entry in new_boards.items():
            old_entry = old_boards.get(board_id)
            if old_entry is None:
                continue

            old_errors = old_entry.get("error_ceiling", 0)
            new_errors = new_entry.get("error_ceiling", 0)
            old_warnings = old_entry.get("warning_ceiling", 0)
            new_warnings = new_entry.get("warning_ceiling", 0)

            if new_errors > old_errors or new_warnings > old_warnings:
                has_approval = "Ceiling-Approval:" in commit_message
                if not has_approval:
                    return DrcRatchetResult(
                        passed=False,
                        board_id=board_id,
                        message=f"Ceiling increase {old_errors} -> {new_errors} requires explicit approval.",
                        exit_code=2,
                    )

        return None

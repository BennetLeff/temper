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
    """A single board entry in the DRC ceiling file.

    ``tool_versions`` and ``category_source`` are read from the file's
    ``provenance`` block and top level respectively -- pure metadata, never
    ceiling values -- and exist so the ratchet can (1) tell the reader which
    engine produced ``violations_by_type``/``warnings_by_type`` (currently
    always kicad-cli; see ``_check_board``'s kicad-cli branch, the only one
    that ever populates a per-type breakdown) and (2) detect when the
    running ``kicad-cli`` differs from the one the ceiling was measured
    with, rather than silently comparing against a different engine.
    """

    board_id: str
    path: str
    error_ceiling: int
    warning_ceiling: int
    violations_by_type: dict[str, int] = field(default_factory=dict)
    warnings_by_type: dict[str, int] = field(default_factory=dict)
    tool_versions: dict[str, str] = field(default_factory=dict)
    category_source: str | None = None


@dataclass
class DrcCategoryFailure:
    """One violation-type category that exceeded its ceiling.

    ``is_new`` distinguishes a category absent from ``violations_by_type``
    (or, for warnings, ``warnings_by_type``) entirely (an implicit ceiling
    of 0, by design -- see drc_ceiling.json's ``_march`` notes) from one
    that is present in the file but regressed past its recorded ceiling.
    Both are real ceiling violations, but a brand-new violation class means
    the board grew a defect *type* the ratchet has never seen before, which
    is a materially different signal from "more of a kind we already
    track" and must not be folded into the same bucket silently.

    ``kind`` distinguishes an error-category failure from a warning-category
    failure -- they come from separate exhaustive records
    (``violations_by_type`` vs. ``warnings_by_type``) and must not be
    conflated when reporting which dimension regressed.

    ``source`` names the DRC engine that produced this category's count
    (currently always ``"kicad-cli"`` at runtime -- the ``rust`` backend
    never supplies a per-type breakdown, see ``_check_board``). This exists
    because ``creepage``, for example, is a real category the Rust engine
    (``temper_drc_rs``) reports under its own ``check_name``, but it is not
    a KiCad DRC violation type at all -- bare kicad-cli never emits it. A
    category list mixing engines without saying which is which lets a
    reader mistake one engine's finding for the other's.
    """

    rule: str
    count: int
    allowed: int
    is_new: bool
    kind: str = "error"
    source: str = "unknown"

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
    kicad_cli_version_running: str | None = None
    kicad_cli_version_expected: str | None = None
    kicad_cli_version_mismatch: bool = False


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
            provenance = entry.get("provenance") or {}
            self.entries[board_id] = DrcCeilingEntry(
                board_id=board_id,
                path=entry["path"],
                error_ceiling=entry.get("error_ceiling", 0),
                warning_ceiling=entry.get("warning_ceiling", 0),
                violations_by_type=entry.get("violations_by_type", {}),
                warnings_by_type=entry.get("warnings_by_type", {}),
                tool_versions=provenance.get("tool_versions") or {},
                category_source=entry.get("category_source"),
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

        # Per-error-type and per-warning-type counts, when the backend can
        # supply them. None means "this backend cannot break this dimension
        # down", which is distinct from "no violations" (``{}``) and must
        # never be treated as an all-clear.
        current_by_type: dict[str, int] | None = None
        current_warnings_by_type: dict[str, int] | None = None

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

                # ``getattr`` (not a direct attribute access) because a
                # result object that cannot supply a warnings breakdown --
                # deliberately -- looks exactly like one that lacks the
                # attribute entirely; both must resolve to None, never to a
                # crash and never to an all-clear ``{}``.
                raw_warnings = getattr(drc_result, "warnings", None)
                if raw_warnings is not None:
                    current_warnings_by_type = {}
                    for warn in raw_warnings:
                        rule = warn.rule or "unknown"
                        current_warnings_by_type[rule] = (
                            current_warnings_by_type.get(rule, 0) + 1
                        )
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

        # kicad-cli version pin: the ceiling's provenance records the
        # kicad-cli version it was measured with, but nothing previously
        # enforced that CI (or a local run) uses that same version -- a
        # patch bump changes the DRC engine, which means a red gate could
        # be silently comparing against a different measuring instrument
        # rather than an actual regression. Reported prominently rather
        # than hard-failed: a version bump alone was already shown not to
        # explain the report count on this board (see
        # docs/evidence/2026-07-27-drc-truth-gate-discrepancy.md section 2),
        # so failing the whole gate on any patch mismatch would be its own
        # false positive -- but it must never again pass through unnoted.
        running_kicad_cli_version: str | None = None
        expected_kicad_cli_version: str | None = None
        version_mismatch = False
        if self.backend == "kicad-cli":
            from temper_placer.validation._drc_api import get_kicad_cli_version

            running_kicad_cli_version = get_kicad_cli_version()
            expected_kicad_cli_version = entry.tool_versions.get("kicad-cli")
            version_mismatch = bool(
                running_kicad_cli_version
                and expected_kicad_cli_version
                and running_kicad_cli_version != expected_kicad_cli_version
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
                            kind="error",
                            source=self.backend,
                        )
                    )

        # Per-type warning ceilings -- same semantics as errors above,
        # mirrored exactly: ``warnings_by_type`` is an exhaustive record, a
        # rule absent from it has an implicit ceiling of zero, and this only
        # runs when the backend actually supplied a breakdown (``is not
        # None``) so a backend that can't break warnings down never reads
        # as "0 categories, therefore all clear".
        if entry.warnings_by_type and current_warnings_by_type is not None:
            for rule, count in sorted(current_warnings_by_type.items()):
                allowed = entry.warnings_by_type.get(rule, 0)
                if count > allowed:
                    category_failures.append(
                        DrcCategoryFailure(
                            rule=rule,
                            count=count,
                            allowed=allowed,
                            is_new=rule not in entry.warnings_by_type,
                            kind="warning",
                            source=self.backend,
                        )
                    )

        version_note = (
            f"  NOTE: kicad-cli version mismatch -- running {running_kicad_cli_version}, "
            f"ceiling measured with {expected_kicad_cli_version} (numbers may not be "
            "directly comparable; see drc_ceiling.json provenance.tool_versions)"
            if version_mismatch
            else None
        )

        if aggregate_failures or category_failures:
            lines = [f"{board_id}: DRC FAIL"]
            if version_note:
                lines.append(version_note)
            for failure in aggregate_failures:
                lines.append(f"  aggregate {failure}")

            def _render_category_block(label: str, failures: list[DrcCategoryFailure]) -> None:
                if not failures:
                    return
                new_failures = [c for c in failures if c.is_new]
                regressed_failures = [c for c in failures if not c.is_new]
                n = len(failures)
                # All failures in one block share a single run's backend, so
                # the source is reported once per block rather than once per
                # line -- see DrcCategoryFailure.source's docstring for why
                # this must never be left implicit (creepage vs. track_width
                # style engine ambiguity).
                source = failures[0].source
                lines.append(
                    f"  per-type {label} (source: {source}): {n} categor"
                    f"{'y' if n == 1 else 'ies'} over ceiling ({len(new_failures)} new, "
                    f"{len(regressed_failures)} regressed):"
                )
                for c in new_failures + regressed_failures:
                    tag = "NEW" if c.is_new else "   "
                    lines.append(f"    [{tag}] {c.rule} {c.count} > {c.allowed} (+{c.delta})")

            _render_category_block(
                "errors", [c for c in category_failures if c.kind == "error"]
            )
            _render_category_block(
                "warnings", [c for c in category_failures if c.kind == "warning"]
            )
            return DrcRatchetResult(
                passed=False,
                board_id=board_id,
                message="\n".join(lines),
                exit_code=1,
                violation_deltas={c.rule: c.delta for c in category_failures},
                category_failures=category_failures,
                aggregate_error_delta=max(error_delta, 0),
                aggregate_warning_delta=max(warning_delta, 0),
                kicad_cli_version_running=running_kicad_cli_version,
                kicad_cli_version_expected=expected_kicad_cli_version,
                kicad_cli_version_mismatch=version_mismatch,
            )

        slack = entry.error_ceiling - current_errors
        slack_note = (
            f" [{slack} error(s) of unratcheted slack -- lower error_ceiling to "
            f"{current_errors} to lock this in]"
            if slack > 0
            else ""
        )
        pass_message = (
            f"{board_id}: DRC {current_errors}/{entry.error_ceiling} errors, "
            f"{current_warnings}/{entry.warning_ceiling} warnings within ceiling"
            f"{slack_note}"
        )
        if version_note:
            pass_message = f"{pass_message}\n{version_note.strip()}"
        return DrcRatchetResult(
            passed=True,
            board_id=board_id,
            message=pass_message,
            kicad_cli_version_running=running_kicad_cli_version,
            kicad_cli_version_expected=expected_kicad_cli_version,
            kicad_cli_version_mismatch=version_mismatch,
        )

    def detect_ceiling_raise(
        self, old_ceiling: dict, new_ceiling: dict, commit_message: str = ""
    ) -> DrcRatchetResult | None:
        """Detect if ceiling was raised without approval.

        A raise is any of: the aggregate ``error_ceiling`` increasing, the
        aggregate ``warning_ceiling`` increasing, or any single rule inside
        ``violations_by_type`` (errors) or ``warnings_by_type`` (warnings)
        increasing -- including a rule that didn't exist in the old record
        at all, which is a raise from its implicit ceiling of 0 (the same
        implicit-zero semantics ``_check_board`` enforces at runtime).
        Editing the ceiling *file* to grant a rule more room is exactly as
        much a raise as editing the aggregate number, and must require the
        same ``Ceiling-Approval:`` trailer -- otherwise the per-type
        ceiling could be silently inflated in the JSON itself, sidestepping
        the runtime check entirely. This applies symmetrically to
        ``violations_by_type`` and ``warnings_by_type``: an earlier version
        of this method checked only the warnings side, which meant a
        per-type *error* ceiling (e.g. ``clearance``) could be raised in
        the committed JSON with no trailer and this detector would not
        notice, even though ``_check_board`` enforces that exact ceiling at
        runtime.
        """
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

            reasons: list[str] = []
            if new_errors > old_errors:
                reasons.append(f"error_ceiling {old_errors} -> {new_errors}")
            if new_warnings > old_warnings:
                reasons.append(f"warning_ceiling {old_warnings} -> {new_warnings}")

            old_violations_by_type = old_entry.get("violations_by_type") or {}
            new_violations_by_type = new_entry.get("violations_by_type") or {}
            for rule in sorted(new_violations_by_type):
                new_count = new_violations_by_type[rule]
                old_count = old_violations_by_type.get(rule, 0)
                if new_count > old_count:
                    reasons.append(f"violations_by_type[{rule}] {old_count} -> {new_count}")

            old_warnings_by_type = old_entry.get("warnings_by_type") or {}
            new_warnings_by_type = new_entry.get("warnings_by_type") or {}
            for rule in sorted(new_warnings_by_type):
                new_count = new_warnings_by_type[rule]
                old_count = old_warnings_by_type.get(rule, 0)
                if new_count > old_count:
                    reasons.append(f"warnings_by_type[{rule}] {old_count} -> {new_count}")

            if reasons:
                has_approval = "Ceiling-Approval:" in commit_message
                if not has_approval:
                    return DrcRatchetResult(
                        passed=False,
                        board_id=board_id,
                        message=(
                            f"Ceiling increase ({'; '.join(reasons)}) requires explicit approval."
                        ),
                        exit_code=2,
                    )

        return None

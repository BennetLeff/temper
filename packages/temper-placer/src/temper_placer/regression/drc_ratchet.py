"""DRC ratchet CI gate.

Loads drc_ceiling.json, runs DRC on target boards, and enforces
a monotonically-non-increasing ceiling on DRC violation counts.

Wave 4 Phase 4 (regression slice): the ceiling-COMPARISON compute — aggregate
deltas, per-type category failure detection (implicit-zero ceiling), the
pass/fail message composition, and ``detect_ceiling_raise`` — moved to the
Rust kernels ``temper_drc_rs.ratchet_check`` /
``temper_drc_rs.detect_ceiling_raise`` (packages/temper-drc-rs/src/
drc_ratchet.rs). The DRC backends (rust-engine board-dict building,
kicad-cli subprocess), the ceiling-file loading, and the result dataclasses
stay Python — I/O and marshalling. The ratchet CONSTANTS (drc_ceiling.json,
the #575 gate) are untouched: this migration only ports the comparison
logic, so the ratchet reads exactly what it read before. Design boundaries
are argued in ``packages/temper-drc-rs/VERIFICATION.md``.

Supports two backends:
  - ``rust`` (default): uses ``temper_drc_rs.run_drc()`` with the
    parsed-PCB-via-KiCad-parser path.
  - ``kicad-cli``: uses the KiCad CLI DRC via
    ``temper_placer.validation._drc_api.run_drc()``.

When the Rust backend is selected but ``temper_drc_rs`` is not
installed, the check fails with a clear error message.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_RS = None


def _tdrc():
    global _RS
    if _RS is None:
        import temper_drc_rs  # type: ignore[import-untyped]

        _RS = temper_drc_rs
    return _RS


class CeilingMarshalError(ValueError):
    """A ceiling/count value the #575 gate cannot compare safely.

    The ratchet data model is int-only (``DrcCeilingEntry.error_ceiling``/
    ``warning_ceiling`` are typed ``int``; ``drc_ceiling.json`` records
    integer DRC counts measured by ``run_drc``). The pre-fix marshal coerced
    every value with ``int()``, which silently truncated a float-valued
    ceiling (``100.5`` -> ``100``): a raise ``100 -> 100.5`` became invisible
    to ``temper_drc_rs.detect_ceiling_raise``, so the shim returned None and
    the #575 approval gate failed OPEN. Any value that is not a genuine int
    is a data-model violation and fails LOUDLY here instead -- a fail-closed
    deviation from the oracle's raw compare, documented in
    ``packages/temper-drc-rs/VERIFICATION.md``.
    """


def _marshal_ceiling_int(value: object, field: str, board_id: str) -> int:
    """Coerce one ceiling/count value to int, failing loudly on anything that
    is not a genuine int (bool excluded).

    Raises:
        CeilingMarshalError: if ``value`` is not an ``int`` (a float --
            integral or fractional -- a string, None, ...). Naming the field
            and value so the bad record is identifiable without digging into
            a stack trace.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise CeilingMarshalError(
            f"non-integer {field}={value!r} on board {board_id!r}: the #575 "
            "ceiling gate requires integer-valued ceilings/counts (an int() "
            "coercion could hide a raise by truncating it)"
        )
    return value


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
        #
        # Wave 4 Phase 4: this comparison + message composition now runs in
        # ``temper_drc_rs.ratchet_check`` (the backend above still supplies
        # the measured counts; the kernel applies the ceiling comparisons and
        # builds the exact messages bit-identically to the pre-migration
        # oracle). ``None`` breakdowns stay None (the "backend cannot break
        # this dimension down" sentinel, distinct from an all-clear ``{}``).
        # The kernel call sits INSIDE a try/except so a missing
        # ``temper_drc_rs`` produces the clean "DRC (...) failed" FAIL (the
        # pre-migration graceful degradation) instead of an unhandled
        # ImportError traceback. Every ceiling/count crossing the i64
        # boundary is int-validated: a float-valued value (e.g. a ``100.5``
        # ceiling in the JSON) fails loudly with ``CeilingMarshalError``
        # rather than being silently truncated by the old ``int()`` coercion
        # (the P1-1 fail-open class).
        try:
            ratchet_dict = _tdrc().ratchet_check(
                board_id=board_id,
                current_errors=_marshal_ceiling_int(
                    current_errors, "current_errors", board_id
                ),
                current_warnings=_marshal_ceiling_int(
                    current_warnings, "current_warnings", board_id
                ),
                error_ceiling=_marshal_ceiling_int(
                    entry.error_ceiling, "error_ceiling", board_id
                ),
                warning_ceiling=_marshal_ceiling_int(
                    entry.warning_ceiling, "warning_ceiling", board_id
                ),
                current_by_type=(
                    list(current_by_type.items())
                    if current_by_type is not None
                    else None
                ),
                allowed_by_type=list(entry.violations_by_type.items()),
                current_warnings_by_type=(
                    list(current_warnings_by_type.items())
                    if current_warnings_by_type is not None
                    else None
                ),
                allowed_warnings_by_type=list(entry.warnings_by_type.items()),
                backend=self.backend,
                version_mismatch=version_mismatch,
                running_version=running_kicad_cli_version,
                expected_version=expected_kicad_cli_version,
            )
        except Exception as e:
            return DrcRatchetResult(
                passed=False,
                board_id=board_id,
                message=f"DRC ({self.backend}) failed: {e}",
                exit_code=1,
            )
        return DrcRatchetResult(
            passed=ratchet_dict["passed"],
            board_id=board_id,
            message=ratchet_dict["message"],
            exit_code=ratchet_dict["exit_code"],
            violation_deltas=ratchet_dict["violation_deltas"],
            category_failures=[
                DrcCategoryFailure(
                    rule=c["rule"],
                    count=c["count"],
                    allowed=c["allowed"],
                    is_new=c["is_new"],
                    kind=c["kind"],
                    source=c["source"],
                )
                for c in ratchet_dict["category_failures"]
            ],
            aggregate_error_delta=ratchet_dict["aggregate_error_delta"],
            aggregate_warning_delta=ratchet_dict["aggregate_warning_delta"],
            kicad_cli_version_running=ratchet_dict["kicad_cli_version_running"],
            kicad_cli_version_expected=ratchet_dict["kicad_cli_version_expected"],
            kicad_cli_version_mismatch=ratchet_dict["kicad_cli_version_mismatch"],
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

        Wave 4 Phase 4: the raise-detection compute now runs in
        ``temper_drc_rs.detect_ceiling_raise`` (the constants it compares
        are unchanged -- the #575 gate's behavior is preserved).
        """

        def _marshal(ceiling: dict) -> list[tuple]:
            # Pass 2 (P1-1): every value is int-VALIDATED at this marshal
            # boundary, not merely int()-coerced. The old coercion silently
            # truncated a float-valued ceiling (``100.5`` -> ``100``), making
            # a raise ``100 -> 100.5`` invisible to the kernel and failing
            # the #575 approval gate OPEN. ``CeilingMarshalError`` fires
            # before the kernel instead.
            boards: list[tuple] = []
            for board in ceiling.get("boards", []):
                board_id = board["board_id"]
                boards.append(
                    (
                        board_id,
                        _marshal_ceiling_int(
                            board.get("error_ceiling", 0), "error_ceiling", board_id
                        ),
                        _marshal_ceiling_int(
                            board.get("warning_ceiling", 0), "warning_ceiling", board_id
                        ),
                        [
                            (
                                rule,
                                _marshal_ceiling_int(
                                    count,
                                    f"violations_by_type[{rule}]",
                                    board_id,
                                ),
                            )
                            for rule, count in (
                                board.get("violations_by_type") or {}
                            ).items()
                        ],
                        [
                            (
                                rule,
                                _marshal_ceiling_int(
                                    count,
                                    f"warnings_by_type[{rule}]",
                                    board_id,
                                ),
                            )
                            for rule, count in (
                                board.get("warnings_by_type") or {}
                            ).items()
                        ],
                    )
                )
            return boards

        result = _tdrc().detect_ceiling_raise(
            _marshal(old_ceiling),
            _marshal(new_ceiling),
            commit_message,
        )
        if result is None:
            return None
        return DrcRatchetResult(
            passed=result["passed"],
            board_id=result["board_id"],
            message=result["message"],
            exit_code=result["exit_code"],
        )

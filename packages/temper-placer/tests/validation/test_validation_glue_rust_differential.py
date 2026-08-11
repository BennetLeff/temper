"""Differential test: the validation-glue kernels in Rust vs the pinned
pre-migration Python implementations (port-inventory entry-5 cluster).

Migrates the portable compute of ``temper_placer/validation/`` into
``temper_drc_rs.validation_glue``:

- ``_drc_api.py`` — DRC-report line parsing and per-violation aggregation
  (``_extract_ref_from_item_description``,
  ``_extract_net_from_item_description``, the ``_parse_drc_json`` item loop).
  The kicad-cli subprocess, the ``--all-track-errors`` flag, the
  ``run_drc`` signature, and the ``DrcResult``/``DrcError``/``DrcWarning``
  dataclass shapes stay Python — the kernel returns parsed records and the
  shim marshals them into the unchanged dataclasses.
- ``validation_gates.py`` — the four gate decision kernels (threshold
  comparisons, failed-metric selection, message composition). Wall-clock
  ``elapsed_ms`` and the ``GateResult``/``GateStatus`` dataclasses stay
  Python.
- ``scheduler.py`` — the schedule decision logic (``is_final_phase``,
  ``get_drc_interval``/``get_spice_interval``,
  ``should_run_drc``/``should_run_spice``). YAML load/save, the config
  dataclasses, and the scheduler's mutable run-state sets stay Python.

The oracle blocks below are VERBATIM copies of the pre-migration bodies
(commit ``5b2a03cfe``), with only the class/function prefixes renamed to
``_oracle_*`` so they do not bind to the migrated delegation shims (the
pre-migration ``_parse_drc_json`` called the module-level
``_extract_ref_from_item_description``, which now delegates to the Rust
kernel; the pre-migration ``ProductionReadyGate.check`` constructed
``PlacementCompleteGate()``, which is now a shim). Do not edit them — they
are the reference.

G1 TDD: the module-level ``= _tdrc.<symbol>`` bindings below fail to collect
until ``validation_glue.rs`` exists (RED); this file is green only after the
kernels + delegation shims land (GREEN).
"""

from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import temper_drc_rs as _tdrc
from hypothesis import given, settings
from hypothesis import strategies as st

# Rust symbols under test — must exist or this file fails to collect (RED).
DRC_EXTRACT_REF = _tdrc.drc_extract_ref
DRC_EXTRACT_NET = _tdrc.drc_extract_net
DRC_PARSE_VIOLATIONS = _tdrc.drc_parse_violations
SCHEDULER_IS_FINAL_PHASE = _tdrc.scheduler_is_final_phase
SCHEDULER_GET_INTERVAL = _tdrc.scheduler_get_interval
SCHEDULER_SHOULD_RUN = _tdrc.scheduler_should_run
GATE_PLACEMENT_COMPLETE = _tdrc.gate_placement_complete
GATE_ROUTING_COMPLETE = _tdrc.gate_routing_complete
GATE_PRODUCTION_READY = _tdrc.gate_production_ready
GATE_VALIDATED = _tdrc.gate_validated

from temper_placer.validation._drc_api import (  # noqa: E402
    DrcError,
    DrcResult,
    DrcWarning,
)
from temper_placer.validation._drc_api import _parse_drc_json as ShimParseDrcJson  # noqa: E402
from temper_placer.validation.scheduler import (  # noqa: E402
    ValidationScheduleConfig,
    ValidationScheduler,
)
from temper_placer.validation.validation_gates import (  # noqa: E402
    GateResult,
    GateStatus,
    PlacementCompleteGate,
    ProductionReadyGate,
    RoutingCompleteGate,
    ValidatedGate,
)

# ---------------------------------------------------------------------------
# Verbatim pre-migration oracles (copied from the modules AS COMMITTED
# before the entry-5 migration, commit 5b2a03cfe; do not edit — they are
# the reference).
# ---------------------------------------------------------------------------


# --- _drc_api.py: regex constants + extractors + _parse_drc_json -----------


_FOOTPRINT_DESC_RE = re.compile(r"^Footprint (\S+)$")
_OF_REF_DESC_RE = re.compile(r"\bof (\S+?)(?:\s+on\s+\S.*)?$")
_NET_IN_BRACKETS_RE = re.compile(r"\[([^\]]+)\]")


def _oracle_extract_ref_from_item_description(description: str) -> str | None:
    """Extract a component reference designator from a DRC item's
    free-text description, or None if the item isn't owned by a single
    component (e.g. a via or a board-edge polygon)."""
    match = _FOOTPRINT_DESC_RE.match(description)
    if match:
        return match.group(1)
    match = _OF_REF_DESC_RE.search(description)
    if match:
        return match.group(1)
    return None


def _oracle_extract_net_from_item_description(description: str) -> str | None:
    """Extract a net name from a DRC item's free-text description, or
    None if it doesn't carry one. KiCad embeds net names in square
    brackets for net-owned items -- "Via [GND] on F.Cu - B.Cu",
    "Pad 2 [hb.gate_hs.driver-p2] of C22 on F.Cu" -- but not for
    board-level features like "Polygon on Edge.Cuts"."""
    match = _NET_IN_BRACKETS_RE.search(description)
    if match:
        return match.group(1)
    return None


def _oracle_parse_drc_json(json_path: Path) -> DrcResult:
    """
    Parse kicad-cli DRC JSON output.

    Args:
        json_path: Path to JSON report file.

    Returns:
        DrcResult with parsed errors and warnings.
    """
    with open(json_path) as f:
        data = json.load(f)

    errors: list[DrcError] = []
    warnings: list[DrcWarning] = []

    for violation in data.get("violations", []):
        rule = violation.get("type", "unknown")
        severity = violation.get("severity", "error")
        message = violation.get("description", "")

        items = violation.get("items", [])

        location = (0.0, 0.0)
        components: list[str] = []
        nets: list[str] = []
        raw_items: list[str] = []
        location_set = False
        for item in items:
            description = item.get("description", "")
            raw_items.append(description)
            ref = _oracle_extract_ref_from_item_description(description)
            if ref and ref not in components:
                components.append(ref)
            net = _oracle_extract_net_from_item_description(description)
            if net and net not in nets:
                nets.append(net)
            if ref and not location_set:
                pos = item.get("pos", {})
                location = (pos.get("x", 0.0), pos.get("y", 0.0))
                location_set = True
        if not location_set and items:
            pos = items[0].get("pos", {})
            location = (pos.get("x", 0.0), pos.get("y", 0.0))

        if severity == "warning":
            warnings.append(
                DrcWarning(
                    rule=rule,
                    severity=severity,
                    location=location,
                    message=message,
                    components=components,
                    nets=nets,
                )
            )
        else:
            errors.append(
                DrcError(
                    rule=rule,
                    severity=severity,
                    location=location,
                    message=message,
                    components=components,
                    nets=nets,
                    items=raw_items,
                )
            )

    return DrcResult(
        error_count=len(errors),
        warning_count=len(warnings),
        errors=errors,
        warnings=warnings,
    )


# --- scheduler.py: ValidationScheduler decision methods ---------------------


class _OracleValidationScheduler:
    """
    Manages validation scheduling during training.

    Determines when to run DRC, SPICE, and other validations based on:
    - Current epoch
    - Total epochs (for final phase detection)
    - Configured intervals
    """

    def __init__(
        self,
        config: ValidationScheduleConfig,
        total_epochs: int = 5000,
    ):
        self.config = config
        self.total_epochs = total_epochs

        # Track what has been run
        self._drc_epochs: set[int] = set()
        self._spice_epochs: set[int] = set()

    def is_final_phase(self, epoch: int) -> bool:
        """Check if we're in the final phase of training."""
        final_start = self.total_epochs - self.config.final_phase_epochs
        return epoch >= final_start

    def get_drc_interval(self, epoch: int) -> int:
        """Get DRC interval for current epoch."""
        if self.is_final_phase(epoch):
            return self.config.drc.final_phase_interval
        return self.config.drc.interval

    def get_spice_interval(self, epoch: int) -> int:
        """Get SPICE interval for current epoch."""
        if self.is_final_phase(epoch):
            return self.config.spice.final_phase_interval
        return self.config.spice.interval

    def should_run_drc(self, epoch: int) -> bool:
        """Check if DRC should run at this epoch."""
        if not self.config.enabled or not self.config.drc.enabled:
            return False

        if epoch in self._drc_epochs:
            return False

        interval = self.get_drc_interval(epoch)
        should_run = epoch % interval == 0 or epoch == self.total_epochs - 1

        return should_run

    def should_run_spice(self, epoch: int) -> bool:
        """Check if SPICE should run at this epoch."""
        if not self.config.enabled or not self.config.spice.enabled:
            return False

        if epoch in self._spice_epochs:
            return False

        interval = self.get_spice_interval(epoch)
        should_run = epoch % interval == 0 or epoch == self.total_epochs - 1

        return should_run

    def mark_drc_run(self, epoch: int) -> None:
        """Mark that DRC was run at this epoch."""
        self._drc_epochs.add(epoch)

    def mark_spice_run(self, epoch: int) -> None:
        """Mark that SPICE was run at this epoch."""
        self._spice_epochs.add(epoch)


# --- validation_gates.py: the four gate decision classes --------------------


class _OraclePlacementCompleteGate:
    """Gate: Placement optimization has converged with all geometric constraints met."""

    @property
    def name(self) -> str:
        return "placement_complete"

    @property
    def required_metrics(self) -> list[str]:
        return [
            "overlap_loss",
            "boundary_loss",
            "hv_clearance_violations",
            "zone_violations",
        ]

    def check(self, metrics: Any) -> GateResult:
        import time

        start = time.time()

        failed: dict[str, float] = {}
        checks = [
            ("overlap_loss", metrics.overlap_loss, 0.01),
            ("boundary_loss", metrics.boundary_loss, 0.01),
            ("hv_clearance_violations", metrics.hv_clearance_violations, 0),
            ("zone_violations", metrics.zone_violations, 0),
        ]

        for name, value, threshold in checks:
            if value > threshold:
                failed[name] = value

        elapsed = (time.time() - start) * 1000

        if failed:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message=f"Failed {len(failed)} constraint(s)",
                required_metrics=self.required_metrics,
                failed_metrics=failed,
                elapsed_ms=elapsed,
            )

        if metrics.convergence_epoch == 0:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message="Did not converge",
                required_metrics=self.required_metrics,
                elapsed_ms=elapsed,
            )

        return GateResult(
            gate_name=self.name,
            status=GateStatus.PASS,
            message="All constraints met",
            required_metrics=self.required_metrics,
            elapsed_ms=elapsed,
        )


class _OracleRoutingCompleteGate:
    """Gate: Autorouter has completed with acceptable results."""

    @property
    def name(self) -> str:
        return "routing_complete"

    @property
    def required_metrics(self) -> list[str]:
        return [
            "routing_completion_percent",
            "drc_errors",
        ]

    def check(self, metrics: Any) -> GateResult:
        import time

        start = time.time()
        elapsed = (time.time() - start) * 1000

        if metrics.routing_completion_percent < 0:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.SKIP,
                message="Routing not measured",
                required_metrics=self.required_metrics,
                elapsed_ms=elapsed,
            )

        failed: dict[str, float] = {}

        if metrics.routing_completion_percent < 90.0:
            failed["routing_completion_percent"] = metrics.routing_completion_percent

        if metrics.drc_errors > 0:
            failed["drc_errors"] = metrics.drc_errors

        if failed:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message=f"Failed {len(failed)} requirement(s)",
                required_metrics=self.required_metrics,
                failed_metrics=failed,
                elapsed_ms=elapsed,
            )

        return GateResult(
            gate_name=self.name,
            status=GateStatus.PASS,
            message="Routing complete with 0 DRC errors",
            required_metrics=self.required_metrics,
            elapsed_ms=elapsed,
        )


class _OracleProductionReadyGate:
    """Gate: Design can be sent to fabrication."""

    @property
    def name(self) -> str:
        return "production_ready"

    @property
    def required_metrics(self) -> list[str]:
        return [
            "overlap_loss",
            "boundary_loss",
            "hv_clearance_violations",
            "zone_violations",
            "routing_completion_percent",
            "drc_errors",
            "creepage_estimate",
            "spice_gate_overshoot",
            "spice_power_ripple",
        ]

    def check(self, metrics: Any) -> GateResult:
        import time

        start = time.time()

        placement_gate = _OraclePlacementCompleteGate()
        placement_result = placement_gate.check(metrics)

        if not placement_result.passed:
            elapsed = (time.time() - start) * 1000
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message=f"Placement not ready: {placement_result.message}",
                required_metrics=self.required_metrics,
                failed_metrics=placement_result.failed_metrics,
                elapsed_ms=elapsed,
            )

        failed: dict[str, float] = {}

        if metrics.routing_completion_percent >= 0 and metrics.routing_completion_percent < 90.0:
            failed["routing_completion_percent"] = metrics.routing_completion_percent

        if metrics.drc_errors > 0:
            failed["drc_errors"] = metrics.drc_errors

        elapsed = (time.time() - start) * 1000

        if failed:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message=f"Failed {len(failed)} requirement(s)",
                required_metrics=self.required_metrics,
                failed_metrics=failed,
                elapsed_ms=elapsed,
            )

        return GateResult(
            gate_name=self.name,
            status=GateStatus.PASS,
            message="Production ready",
            required_metrics=self.required_metrics,
            elapsed_ms=elapsed,
        )


class _OracleValidatedGate:
    """Gate: Design has been statistically validated."""

    @property
    def name(self) -> str:
        return "validated"

    @property
    def required_metrics(self) -> list[str]:
        return [
            "failure_rate",
            "loss_cv",
        ]

    def check(self, metrics: Any) -> GateResult:
        import time

        start = time.time()
        elapsed = (time.time() - start) * 1000

        failure_rate = getattr(metrics, "failure_rate", None)
        loss_cv = getattr(metrics, "loss_cv", None)

        if failure_rate is None or loss_cv is None:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.SKIP,
                message="Statistical validation not performed",
                required_metrics=self.required_metrics,
                elapsed_ms=elapsed,
            )

        failed: dict[str, float] = {}

        if failure_rate > 5.0:
            failed["failure_rate"] = failure_rate

        if loss_cv > 0.15:
            failed["loss_cv"] = loss_cv

        if failed:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message=f"Failed {len(failed)} statistical requirement(s)",
                required_metrics=self.required_metrics,
                failed_metrics=failed,
                elapsed_ms=elapsed,
            )

        return GateResult(
            gate_name=self.name,
            status=GateStatus.PASS,
            message="Statistically validated",
            required_metrics=self.required_metrics,
            elapsed_ms=elapsed,
        )


# ---------------------------------------------------------------------------
# Input strategies
# ---------------------------------------------------------------------------

_REAL_DESCRIPTIONS = [
    "Footprint D3",
    "Reference field of C1",
    "Segment of C16 on F.Silkscreen",
    "PTH pad 1 [+15V] of R1",
    "Pad 13 [power_in.ntc-no] of K1 on F.Cu",
    "Via [bias] on F.Cu - B.Cu",
    "Polygon on Edge.Cuts",
    "Pad 2 [hb.gate_hs.driver-p2] of C22 on F.Cu",
    "Footprint U1",
    "Zone [power.GND] on F.Cu",
    "Track [net_sw] on B.Cu",
    "Arc [V_BUS_SENSE] on B.Cu",
]

_ADVERSARIAL_DESCRIPTIONS = [
    "",
    "of",
    " of",
    "of A",
    "of A on B",
    "of R1 on F.Cu on B.Cu",
    "Footprint X1 trailing",
    "no ref here",
    "[a][b]",
    "[]",
    "Via [GND]x[extra]",
    "on F.Cu",
    "of C1 on F.Cu",
    "Footprint D3\n",
    "of C16\n",
    "Reference field of C1\n",
    "Segment of C16 on F.Silkscreen\n",
    "of R1\non F.Cu",
    " [x] ",
    "of U_GD",
    "of U_GD on F.Cu",
    "Footprint U_GD",
]


@st.composite
def description(draw):
    return draw(st.sampled_from(_REAL_DESCRIPTIONS + _ADVERSARIAL_DESCRIPTIONS))


@st.composite
def item(draw):
    pos_present = draw(st.booleans())
    pos = {}
    if pos_present:
        pos = {
            "x": draw(
                st.one_of(
                    st.floats(min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False),
                    st.integers(min_value=-10000, max_value=10000),
                )
            ),
            "y": draw(
                st.one_of(
                    st.floats(min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False),
                    st.integers(min_value=-10000, max_value=10000),
                )
            ),
        }
    return {
        "description": draw(description()),
        "pos": pos,
    }


@st.composite
def violation(draw):
    n_items = draw(st.integers(min_value=0, max_value=4))
    return {
        "type": draw(st.one_of(st.none(), st.sampled_from(["clearance", "shorting_items", "courtyards_overlap", "copper_edge_clearance", "track_width"]))),
        "severity": draw(st.one_of(st.none(), st.sampled_from(["error", "warning", "ERROR", "WARNING"]))),
        "description": draw(st.sampled_from(["Clearance violation", "Courtyards overlap", "Board edge clearance violation", "", "x"])),
        "items": [draw(item()) for _ in range(n_items)],
    }


@st.composite
def schedule_config(draw):
    enabled = draw(st.booleans())
    drc_enabled = draw(st.booleans())
    spice_enabled = draw(st.booleans())
    final_phase_epochs = draw(st.integers(min_value=0, max_value=3000))
    total_epochs = draw(st.integers(min_value=1, max_value=8000))
    drc_interval = draw(st.integers(min_value=1, max_value=2000))
    drc_final_phase_interval = draw(st.integers(min_value=1, max_value=2000))
    spice_interval = draw(st.integers(min_value=1, max_value=2000))
    spice_final_phase_interval = draw(st.integers(min_value=1, max_value=2000))
    return {
        "enabled": enabled,
        "drc_enabled": drc_enabled,
        "spice_enabled": spice_enabled,
        "final_phase_epochs": final_phase_epochs,
        "total_epochs": total_epochs,
        "drc_interval": drc_interval,
        "drc_final_phase_interval": drc_final_phase_interval,
        "spice_interval": spice_interval,
        "spice_final_phase_interval": spice_final_phase_interval,
    }


def _build_schedule_pair(cfg: dict):
    config = ValidationScheduleConfig(
        enabled=cfg["enabled"],
        final_phase_epochs=cfg["final_phase_epochs"],
    )
    config.drc.enabled = cfg["drc_enabled"]
    config.drc.interval = cfg["drc_interval"]
    config.drc.final_phase_interval = cfg["drc_final_phase_interval"]
    config.spice.enabled = cfg["spice_enabled"]
    config.spice.interval = cfg["spice_interval"]
    config.spice.final_phase_interval = cfg["spice_final_phase_interval"]

    oracle = _OracleValidationScheduler(config, total_epochs=cfg["total_epochs"])
    shim = ValidationScheduler(config, total_epochs=cfg["total_epochs"])
    return oracle, shim


@st.composite
def gate_metrics(draw):
    """A duck-typed metrics namespace covering every gate's fields."""
    return SimpleNamespace(
        overlap_loss=draw(st.floats(min_value=-10.0, max_value=100.0, allow_nan=False, allow_infinity=False)),
        boundary_loss=draw(st.floats(min_value=-10.0, max_value=100.0, allow_nan=False, allow_infinity=False)),
        hv_clearance_violations=draw(st.integers(min_value=0, max_value=20)),
        zone_violations=draw(st.integers(min_value=0, max_value=20)),
        convergence_epoch=draw(st.integers(min_value=0, max_value=1000)),
        routing_completion_percent=draw(st.floats(min_value=-5.0, max_value=100.0, allow_nan=False, allow_infinity=False)),
        drc_errors=draw(st.integers(min_value=0, max_value=50)),
        failure_rate=draw(st.one_of(st.none(), st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False))),
        loss_cv=draw(st.one_of(st.none(), st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False))),
    )


# ---------------------------------------------------------------------------
# Ref / net extraction differentials
# ---------------------------------------------------------------------------


def test_ref_extraction_identical_on_curated_descriptions():
    for d in _REAL_DESCRIPTIONS + _ADVERSARIAL_DESCRIPTIONS:
        assert DRC_EXTRACT_REF(d) == _oracle_extract_ref_from_item_description(d), d


def test_net_extraction_identical_on_curated_descriptions():
    for d in _REAL_DESCRIPTIONS + _ADVERSARIAL_DESCRIPTIONS:
        assert DRC_EXTRACT_NET(d) == _oracle_extract_net_from_item_description(d), d


def test_ref_extraction_trailing_newline_semantics():
    """CPython's ``$`` also matches immediately before a single trailing
    ``\n``; the kernel must reproduce that (see VERIFICATION.md)."""
    assert DRC_EXTRACT_REF("Footprint D3\n") == "D3"
    assert DRC_EXTRACT_REF("Segment of C16 on F.Silkscreen\n") == "C16"
    assert DRC_EXTRACT_REF("of C16\n") == "C16"
    assert DRC_EXTRACT_REF("Reference field of C1\n") == "C1"


def test_net_extraction_trailing_newline():
    assert DRC_EXTRACT_NET("Via [GND]\n") == "GND"


def test_ref_extraction_non_string_raises_type_error():
    """``re.match`` on a non-str raises TypeError; the kernel's ``&str``
    extraction raises the same exception type."""
    with pytest.raises(TypeError):
        _oracle_extract_ref_from_item_description(123)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        DRC_EXTRACT_REF(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _parse_drc_json differential
# ---------------------------------------------------------------------------


def _write_violations_json(tmp_path: Path, violations: list[dict]) -> Path:
    path = tmp_path / "drc.json"
    path.write_text(json.dumps({"violations": violations}))
    return path


def _canon_error(e):
    return (
        e.rule,
        e.severity,
        tuple(e.location),
        e.message,
        tuple(e.components),
        tuple(e.nets),
        tuple(e.items),
    )


def _canon_result(r: DrcResult):
    return (
        r.error_count,
        r.warning_count,
        tuple(_canon_error(e) for e in r.errors),
        tuple(_canon_error(w) for w in r.warnings),
    )


def test_parse_drc_json_identical_on_curated_violations(tmp_path):
    violations = [
        {
            "description": "Courtyards overlap",
            "items": [
                {"description": "Footprint D3", "pos": {"x": 134.8, "y": 74.25}, "uuid": "u1"},
                {"description": "Footprint C4", "pos": {"x": 139.92, "y": 64.5}, "uuid": "u2"},
            ],
            "severity": "error",
            "type": "courtyards_overlap",
        },
        {
            "description": "Clearance violation",
            "items": [
                {"description": "Via [cs_n] on F.Cu - B.Cu", "pos": {"x": 10.0, "y": 20.0}, "uuid": "u1"},
                {"description": "Via [sclk] on F.Cu - B.Cu", "pos": {"x": 12.0, "y": 20.0}, "uuid": "u2"},
            ],
            "severity": "error",
            "type": "clearance",
        },
        {
            "description": "Board edge clearance violation",
            "items": [
                {"description": "Polygon on Edge.Cuts", "pos": {"x": 0.0, "y": 0.0}, "uuid": "u1"},
                {"description": "Pad 1 [V_BUS_SENSE] of C35 on F.Cu", "pos": {"x": 100.385, "y": 60.23}, "uuid": "u2"},
            ],
            "severity": "error",
            "type": "copper_edge_clearance",
        },
        {
            "description": "A warning",
            "items": [
                {"description": "Segment of C16 on F.Silkscreen", "pos": {"x": 1.0, "y": 2.0}},
            ],
            "severity": "warning",
            "type": "silkscreen",
        },
        {
            "description": "No items",
            "items": [],
            "severity": "error",
            "type": "unknown",
        },
        {
            "description": "Missing severity defaults to error",
            "items": [],
        },
    ]
    path = _write_violations_json(tmp_path, violations)
    oracle = _oracle_parse_drc_json(path)
    shim = ShimParseDrcJson(path)
    assert _canon_result(oracle) == _canon_result(shim)
    assert shim.error_count == oracle.error_count
    assert shim.warning_count == oracle.warning_count


@given(violation())
@settings(max_examples=60, deadline=None)
def test_parse_drc_json_identical_on_randomized_violations(tmp_path, v):
    path = _write_violations_json(tmp_path, [v])
    oracle = _oracle_parse_drc_json(path)
    shim = ShimParseDrcJson(path)
    assert _canon_result(oracle) == _canon_result(shim)


@given(st.lists(violation(), min_size=0, max_size=6))
@settings(max_examples=40, deadline=None)
def test_parse_drc_json_identical_on_violation_lists(tmp_path, vs):
    path = _write_violations_json(tmp_path, list(vs))
    oracle = _oracle_parse_drc_json(path)
    shim = ShimParseDrcJson(path)
    assert _canon_result(oracle) == _canon_result(shim)


def test_parse_drc_json_empty_violations(tmp_path):
    path = _write_violations_json(tmp_path, [])
    oracle = _oracle_parse_drc_json(path)
    shim = ShimParseDrcJson(path)
    assert _canon_result(oracle) == _canon_result(shim)
    assert shim.error_count == 0
    assert shim.warning_count == 0


def test_parse_drc_json_missing_violations_key(tmp_path):
    path = tmp_path / "drc.json"
    path.write_text(json.dumps({}))
    oracle = _oracle_parse_drc_json(path)
    shim = ShimParseDrcJson(path)
    assert _canon_result(oracle) == _canon_result(shim)


# ---------------------------------------------------------------------------
# Scheduler differential
# ---------------------------------------------------------------------------


@given(schedule_config())
@settings(max_examples=60, deadline=None)
def test_scheduler_decisions_identical(cfg):
    oracle, shim = _build_schedule_pair(cfg)
    total = cfg["total_epochs"]
    fixed = {0, 1, total // 2, total - 1, total - 2, -1, -(total // 2)}
    sampled = {random.randrange(-total, total + 1) for _ in range(20)}
    epochs = sorted(fixed | sampled)
    for epoch in epochs:
        assert oracle.is_final_phase(epoch) == shim.is_final_phase(epoch), (cfg, epoch)
        assert oracle.get_drc_interval(epoch) == shim.get_drc_interval(epoch), (cfg, epoch)
        assert oracle.get_spice_interval(epoch) == shim.get_spice_interval(epoch), (cfg, epoch)
        assert oracle.should_run_drc(epoch) == shim.should_run_drc(epoch), (cfg, epoch)
        assert oracle.should_run_spice(epoch) == shim.should_run_spice(epoch), (cfg, epoch)
        # already-marked epochs flip the run decisions
        oracle.mark_drc_run(epoch)
        oracle.mark_spice_run(epoch)
        shim.mark_drc_run(epoch)
        shim.mark_spice_run(epoch)
        assert oracle.should_run_drc(epoch) == shim.should_run_drc(epoch), (cfg, epoch)
        assert oracle.should_run_spice(epoch) == shim.should_run_spice(epoch), (cfg, epoch)


def test_scheduler_zero_interval_raises_both_arms():
    """``epoch % 0`` is ZeroDivisionError on both arms."""
    cfg = {
        "enabled": True,
        "drc_enabled": True,
        "spice_enabled": True,
        "final_phase_epochs": 0,
        "total_epochs": 10,
        "drc_interval": 0,
        "drc_final_phase_interval": 0,
        "spice_interval": 0,
        "spice_final_phase_interval": 0,
    }
    oracle, shim = _build_schedule_pair(cfg)
    with pytest.raises(ZeroDivisionError):
        oracle.should_run_drc(5)
    with pytest.raises(ZeroDivisionError):
        shim.should_run_drc(5)
    with pytest.raises(ZeroDivisionError):
        oracle.should_run_spice(5)
    with pytest.raises(ZeroDivisionError):
        shim.should_run_spice(5)


# ---------------------------------------------------------------------------
# Gate differential
# ---------------------------------------------------------------------------


def _canon_gate_result(r) -> tuple:
    return (
        r.gate_name,
        r.status,
        r.message,
        tuple(r.required_metrics),
        tuple(sorted((k, v) for k, v in r.failed_metrics.items())),
        r.elapsed_ms,
    )


GATE_PAIRS = [
    ("placement", _OraclePlacementCompleteGate(), PlacementCompleteGate()),
    ("routing", _OracleRoutingCompleteGate(), RoutingCompleteGate()),
    ("production", _OracleProductionReadyGate(), ProductionReadyGate()),
    ("validated", _OracleValidatedGate(), ValidatedGate()),
]


@pytest.mark.parametrize("gate_kind", ["placement", "routing", "production", "validated"])
def test_gate_identical_on_curated_metrics(gate_kind, monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.567)
    oracle_gate = dict(GATE_PAIRS)[gate_kind][1]
    shim_gate = dict(GATE_PAIRS)[gate_kind][2]
    cases = [
        SimpleNamespace(
            overlap_loss=0.0, boundary_loss=0.0, hv_clearance_violations=0,
            zone_violations=0, convergence_epoch=100,
            routing_completion_percent=100.0, drc_errors=0,
            failure_rate=1.0, loss_cv=0.05,
        ),
        SimpleNamespace(
            overlap_loss=0.05, boundary_loss=0.0, hv_clearance_violations=0,
            zone_violations=0, convergence_epoch=100,
            routing_completion_percent=100.0, drc_errors=0,
            failure_rate=1.0, loss_cv=0.05,
        ),
        SimpleNamespace(
            overlap_loss=0.0, boundary_loss=0.0, hv_clearance_violations=2,
            zone_violations=0, convergence_epoch=100,
            routing_completion_percent=100.0, drc_errors=0,
            failure_rate=1.0, loss_cv=0.05,
        ),
        SimpleNamespace(
            overlap_loss=0.0, boundary_loss=0.0, hv_clearance_violations=0,
            zone_violations=0, convergence_epoch=0,
            routing_completion_percent=100.0, drc_errors=0,
            failure_rate=1.0, loss_cv=0.05,
        ),
        SimpleNamespace(
            overlap_loss=0.0, boundary_loss=0.0, hv_clearance_violations=0,
            zone_violations=0, convergence_epoch=100,
            routing_completion_percent=-1.0, drc_errors=0,
            failure_rate=1.0, loss_cv=0.05,
        ),
        SimpleNamespace(
            overlap_loss=0.0, boundary_loss=0.0, hv_clearance_violations=0,
            zone_violations=0, convergence_epoch=100,
            routing_completion_percent=50.0, drc_errors=3,
            failure_rate=1.0, loss_cv=0.05,
        ),
        SimpleNamespace(
            overlap_loss=0.0, boundary_loss=0.0, hv_clearance_violations=0,
            zone_violations=0, convergence_epoch=100,
            routing_completion_percent=100.0, drc_errors=0,
            failure_rate=10.0, loss_cv=0.2,
        ),
        SimpleNamespace(
            overlap_loss=0.0, boundary_loss=0.0, hv_clearance_violations=0,
            zone_violations=0, convergence_epoch=100,
            routing_completion_percent=100.0, drc_errors=0,
            failure_rate=None, loss_cv=0.05,
        ),
        SimpleNamespace(
            overlap_loss=0.0, boundary_loss=0.0, hv_clearance_violations=0,
            zone_violations=0, convergence_epoch=100,
            routing_completion_percent=100.0, drc_errors=0,
            failure_rate=1.0, loss_cv=None,
        ),
    ]
    for m in cases:
        o = oracle_gate.check(m)
        s = shim_gate.check(m)
        assert _canon_gate_result(o) == _canon_gate_result(s), (gate_kind, m)


@given(gate_metrics())
@settings(max_examples=40, deadline=None)
def test_gate_identical_on_randomized_metrics(monkeypatch, m):
    monkeypatch.setattr(time, "time", lambda: 1234.567)
    for _name, oracle_gate, shim_gate in GATE_PAIRS:
        o = oracle_gate.check(m)
        s = shim_gate.check(m)
        assert _canon_gate_result(o) == _canon_gate_result(s), (_name, m)


def test_gate_status_values_match_gate_status_enum():
    """The kernel status strings are exactly the GateStatus values, so the
    shim's mapping to the enum is lossless."""
    assert GateStatus.PASS.value == "pass"
    assert GateStatus.FAIL.value == "fail"
    assert GateStatus.SKIP.value == "skip"


# ---------------------------------------------------------------------------
# run_drc provenance boundary — the observable DrcResult shape is unchanged
# ---------------------------------------------------------------------------


def test_run_drc_public_signature_and_result_shape_unchanged(monkeypatch, tmp_path):
    """The kicad-cli subprocess path (``run_drc``) stays Python; its public
    API and the DrcResult it returns are pinned here: the empty-report shape
    that test_drc_api_thread_pinning also exercises."""
    pcb = tmp_path / "board.kicad_pcb"
    pcb.write_text("(kicad_pcb)")
    pcb.with_suffix(".kicad_pro").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("temper_placer.validation._drc_api.is_kicad_cli_available", lambda: True)
    monkeypatch.setattr("temper_placer.validation._drc_api.get_kicad_cli_version", lambda: "10.0.4")

    import subprocess as sp

    def fake_run(cmd, **kwargs):
        output = Path(cmd[cmd.index("--output") + 1])
        output.write_text('{"violations": []}')
        return sp.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("temper_placer.validation._drc_api.subprocess.run", fake_run)

    from temper_placer.validation._drc_api import run_drc

    result = run_drc(pcb)
    assert isinstance(result, DrcResult)
    assert result.error_count == 0
    assert result.warning_count == 0
    assert result.errors == []
    assert result.warnings == []

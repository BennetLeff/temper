"""
Tests for the SELV/HV isolation-barrier YAML->IsolationBarrierCheck wiring
(polyline-barrier follow-up to the 2026-08-08 SELV/HV pour-crossing-barrier
DRC spike, ``docs/evidence/2026-08-08-selv-hv-pour-barrier-drc-spike.md``).

Covers two integration gaps that made ``IsolationBarrierCheck``
(``packages/temper-drc-rs/src/rules/routing/isolation_barrier.rs``)
unreachable in practice even once a barrier is configured:

1. ``temper_placer.validation.drc_runner._placement_to_board_dict`` built a
   ``board_dict["zones"]``/``["traces"]`` shape that did not match the K1
   schema ``temper_drc_rs.board_py_bridge`` parses (``{net, layer, polygon}``
   / ``{net, layer, width, segments}``), so ``CheckRunner.run()`` raised
   ``ValueError: missing required key: net`` whenever ``placement.zones`` or
   ``placement.trace_placement`` was populated -- a legitimate, common state
   (e.g. any placement loaded via ``drc_cli.py``'s ``check`` command against
   ``temper_constraints.yaml``, which always defines placement zones).

2. ``temper_placer.validation.drc_oracle.DRCOracle._build_constraints_dict``
   merged ``context.constraints_config``'s pydantic ``BaseModel`` fields
   (e.g. ``isolation_barriers: list[IsolationBarrier]``) directly into the
   dict passed to ``temper_drc_rs.run_drc()``, which only understands
   plain dict/list/str/int/float/bool/None -- so a YAML-configured barrier
   would raise ``cannot convert Python value to JSON`` inside the Rust
   boundary instead of reaching the check.

These tests exercise the real fix functions end-to-end through
``temper_drc_rs.run_drc()`` (not mocks), so a regression that reintroduces
either shape mismatch fails loudly here rather than silently making the
check a no-op again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

temper_drc_rs = pytest.importorskip("temper_drc_rs")

from temper_placer._constraint_types import IsolationBarrier
from temper_placer.validation.drc_oracle import DRCOracle, _constraint_value_to_plain
from temper_placer.validation.drc_runner import _placement_to_board_dict


# ---------------------------------------------------------------------------
# Fakes -- duck-typed stand-ins for the real Placement/context objects.
# ---------------------------------------------------------------------------


@dataclass
class _FakeSegment:
    net_name: str
    layer: str
    width: float
    start: tuple[float, float]
    end: tuple[float, float]


@dataclass
class _FakeTracePlacement:
    segments: list[_FakeSegment] = field(default_factory=list)


@dataclass
class _FakePlacement:
    components: dict[str, Any] = field(default_factory=dict)
    zones: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
    board_width: float = 152.0
    board_height: float = 234.0
    nets: dict[str, list[str]] = field(default_factory=dict)
    net_classes: dict[str, str] = field(default_factory=dict)
    via_placement: Any = None
    trace_placement: Any = None


def _crossing_zone_board_dict() -> dict[str, Any]:
    """A board dict (K1 schema) with a single copper zone that genuinely
    crosses x=60.0 for y in [100, 274] -- the bent segment of the polyline
    barrier fixtures below, but NOT a straight vertical line at x=94.703."""
    return {
        "board": {"width_mm": 152.0, "height_mm": 234.0, "margin_mm": 0.0},
        "components": [],
        "nets": {},
        "net_classes": {},
        "zones": [
            {
                "net": "gnd",
                "layer": "F.Cu",
                "polygon": [
                    [50.0, 140.0],
                    [70.0, 140.0],
                    [70.0, 160.0],
                    [50.0, 160.0],
                    [50.0, 140.0],
                ],
            }
        ],
    }


def _bent_barrier(**overrides: Any) -> IsolationBarrier:
    kwargs: dict[str, Any] = dict(
        name="MAINS_SELV_ISOLATION_BARRIER",
        x_mm=94.703,
        y_span=(0.0, 274.0),
        points=[[94.703, 0.0], [94.703, 100.0], [60.0, 100.0], [60.0, 274.0]],
        layers="all",
        clearance_mm=8.0,
    )
    kwargs.update(overrides)
    return IsolationBarrier(**kwargs)


# ---------------------------------------------------------------------------
# Gap 1: drc_runner._placement_to_board_dict's zones/traces shape
# ---------------------------------------------------------------------------


class TestPlacementToBoardDictShape:
    def test_populated_placement_zones_no_longer_crashes_run_drc(self) -> None:
        """Regression guard: `placement.zones` (placement-boundary regions,
        e.g. `temper_constraints.yaml`'s power_zone/driver_zone) must not be
        serialized under the K1 `board_dict["zones"]` key, which
        `board_py_bridge.rs::extract_copper_zone` parses as `{net, layer,
        polygon}` CopperZone records. Before the fix, any populated
        `placement.zones` made `run_drc()` raise
        `ValueError: missing required key: net` -- unconditionally, for
        every check, not just isolation-barrier ones.

        Phase-A U5: the marshaler is the typed `DrcBoardSnapshot`, which
        reads the `Placement` pyclass (the `_FakePlacement` dataclass this
        test used previously is no longer accepted by the typed path); the
        zones-collision guard is asserted on the snapshot's `to_dict()`."""
        from temper_placer.validation.drc_types import Placement

        placement = Placement(
            zones={"power_zone": (0.0, 110.0, 100.0, 150.0)},
        )
        snapshot = _placement_to_board_dict(placement)

        assert "zones" not in snapshot.to_dict(), (
            "placement-boundary zones must not collide with the "
            "CopperZone-shaped board_dict['zones'] key"
        )
        # Must not raise.
        violations = temper_drc_rs.run_drc(snapshot, {"isolation_barriers": []})
        assert violations == []

    def test_trace_placement_shape_matches_k1_schema_and_is_detected(self) -> None:
        """`board_py_bridge.rs::extract_trace_segment` requires key "net"
        (not "net_name") and a "segments" list of [x1,y1,x2,y2] coordinate
        groups (not top-level "start"/"end"). This proves the corrected
        shape is not just non-crashing but semantically CORRECT: a trace
        that genuinely crosses a configured barrier is caught end-to-end.

        Phase-A U5: the marshaler is the typed `DrcBoardSnapshot`, so the
        placement is built from the real `Placement` pyclasses and the shape
        is asserted on `to_dict()`."""
        from temper_placer.validation.drc_types import Placement, TracePlacement, TraceSegment

        placement = Placement(
            trace_placement=TracePlacement(
                segments=[
                    TraceSegment(
                        net_name="gnd", layer="F.Cu", width=0.25,
                        start=(80.0, 100.0), end=(110.0, 100.0),
                    )
                ]
            ),
        )
        snapshot = _placement_to_board_dict(placement)

        assert snapshot.to_dict()["traces"] == [
            {
                "net": "gnd",
                "layer": "F.Cu",
                "width": 0.25,
                "segments": [[80.0, 100.0, 110.0, 100.0]],
            }
        ]

        constraints_dict = {
            "isolation_barriers": [
                {
                    "name": "B", "x_mm": 94.703, "y_span": [0.0, 274.0],
                    "layers": "all", "clearance_mm": 8.0,
                }
            ],
        }
        violations = temper_drc_rs.run_drc(snapshot, constraints_dict)
        assert len(violations) == 1
        assert violations[0]["code"] == "ROUTING_ISO_001"


# ---------------------------------------------------------------------------
# Gap 2: drc_oracle._build_constraints_dict's pydantic-object serialization
# ---------------------------------------------------------------------------


class TestConstraintValueToPlain:
    def test_pydantic_model_becomes_plain_dict(self) -> None:
        barrier = _bent_barrier()
        # Phase-A U5: _constraint_value_to_plain returns the typed
        # ConstraintValue wrapper; to_python() renders the plain value.
        plain = _constraint_value_to_plain(barrier).to_python()
        assert isinstance(plain, dict)
        # Every value must itself be JSON-primitive-shaped (no tuples --
        # PyO3's bridge only recognizes list, not tuple).
        assert plain["points"] == [[94.703, 0.0], [94.703, 100.0], [60.0, 100.0], [60.0, 274.0]]
        assert isinstance(plain["points"], list)
        assert all(isinstance(p, list) for p in plain["points"])
        assert isinstance(plain["y_span"], list)

    def test_list_of_pydantic_models_becomes_list_of_plain_dicts(self) -> None:
        plain = _constraint_value_to_plain([_bent_barrier(), _bent_barrier(name="B2")]).to_python()
        assert plain == [p for p in plain if isinstance(p, dict)]
        assert [p["name"] for p in plain] == ["MAINS_SELV_ISOLATION_BARRIER", "B2"]

    def test_non_model_values_pass_through_unchanged(self) -> None:
        assert _constraint_value_to_plain(None).to_python() is None
        assert _constraint_value_to_plain(3.14).to_python() == 3.14
        assert _constraint_value_to_plain("x").to_python() == "x"


class TestBuildConstraintsDictEndToEnd:
    """The full chain: pydantic IsolationBarrier (as `preprocess_config`
    would produce from YAML) -> `_build_constraints_dict` ->
    `temper_drc_rs.run_drc()` -> a real violation. This is the "not dead"
    proof for the YAML->IsolationBarrierCheck wiring at the Python
    integration layer, complementing the Rust-level anti-vacuity test
    (`isolation_barrier.rs::tests::configured_barrier_with_real_zones_evaluates_a_nonzero_number_of_them`)."""

    def _oracle(self) -> DRCOracle:
        return DRCOracle(
            runner=None, constraints=None,
            net_class_map={}, footprint_map={}, layer_map={},
        )

    def _context(self, barrier: IsolationBarrier) -> Any:
        return SimpleNamespace(
            clearance_rules=[],
            board=SimpleNamespace(width=152.0, height=234.0),
            constraints_config=SimpleNamespace(isolation_barriers=[barrier]),
        )

    def test_configured_polyline_barrier_reaches_the_check_and_rejects_a_crossing_zone(
        self,
    ) -> None:
        constraints_dict = self._oracle()._build_constraints_dict(
            self._context(_bent_barrier())
        ).to_dict()

        ib = constraints_dict["isolation_barriers"][0]
        assert isinstance(ib, dict), "must be a plain dict, not a pydantic object"

        violations = temper_drc_rs.run_drc(constraints_dict=constraints_dict, board_dict=_crossing_zone_board_dict())
        assert len(violations) == 1
        assert violations[0]["code"] == "ROUTING_ISO_002"

    def test_straight_line_variant_of_the_same_barrier_misses_it(self) -> None:
        """Same pour, same barrier name/clearance, but `points` omitted
        (the pre-existing straight-line-only representation) -- must NOT
        catch the crossing. Pairs with the polyline test above to prove
        this integration path carries the *geometry*, not just presence of
        a barrier."""
        straight_only = _bent_barrier(points=[])
        constraints_dict = self._oracle()._build_constraints_dict(
            self._context(straight_only)
        ).to_dict()

        violations = temper_drc_rs.run_drc(constraints_dict=constraints_dict, board_dict=_crossing_zone_board_dict())
        assert violations == []

    def test_configured_barrier_over_compliant_zone_is_accepted(self) -> None:
        board_dict = {
            "board": {"width_mm": 152.0, "height_mm": 234.0, "margin_mm": 0.0},
            "components": [],
            "nets": {},
            "net_classes": {},
            "zones": [
                {
                    "net": "gnd",
                    "layer": "F.Cu",
                    # Far from every segment of the bent barrier.
                    "polygon": [[10.0, 50.0], [30.0, 50.0], [30.0, 90.0], [10.0, 90.0], [10.0, 50.0]],
                }
            ],
        }
        constraints_dict = self._oracle()._build_constraints_dict(
            self._context(_bent_barrier())
        ).to_dict()

        violations = temper_drc_rs.run_drc(constraints_dict=constraints_dict, board_dict=board_dict)
        assert violations == []

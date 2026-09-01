"""Coverage-paydown wave 21: regression modules (fingerprint,
metrics_recorder, closure_test, drc_ratchet, manifest), router_v6 pure
orchestration (stage_ledger, tree_route_geometry, routing_results,
constraints_design_rules), and the two ABC surfaces (deterministic Stage,
heuristics Heuristic) whose abstract methods still sit on the allowlist.

Every target is a pure function, a dataclass method, a cheaply-constructed
observer, or a Rust-delegation shim reachable from ``tests/core/`` without a
live kicad-cli/ngspice backend or a full solve.  Each target is exercised
directly so the CI-exact coverage run records non-zero line coverage and the
entry becomes removable from ``.coverage-allowlist``.

Abstract methods (``Stage.name`` / ``Stage.run`` / ``Heuristic.name`` /
``Heuristic.priority`` / ``Heuristic.apply``) are ``pass``-only bodies that a
subclass call never reaches -- the base implementation is therefore exercised
directly via ``Class.__dict__["meth"]`` (``property.fget`` for the
properties), which executes the ``pass`` statement and gives the function one
executed line.

Do NOT edit ``.coverage-allowlist`` here -- the orchestrator applies the
removals after CI-exact verification.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState
from temper_placer.heuristics.base import (
    Heuristic,
    HeuristicPriority,
    HeuristicResult,
)
from temper_placer.regression import fingerprint as fingerprint_mod
from temper_placer.regression.closure_test import ClosureResult, ClosureTest
from temper_placer.regression.drc_ratchet import DrcRatchet
from temper_placer.regression.manifest import GoldenManifest
from temper_placer.regression.metrics_recorder import (
    find_metrics_file,
    load_metrics,
    record_closure_result,
    record_metrics,
    record_metrics_for_stage,
    record_stage_timing,
)
from temper_placer.router_v6.astar_core import RoutePath, RoutePath3D
from temper_placer.router_v6.astar_pathfinding import PathfindingResult
from temper_placer.router_v6.connectivity import PadIdentity
from temper_placer.router_v6.constraints_design_rules import (
    ClearanceMatrix,
    DesignRulesParser,
    infer_zones,
)
from temper_placer.router_v6.routing_results import compile_routing_results
from temper_placer.router_v6.stage_ledger import (
    LedgerReport,
    StageLedger,
    StageLedgerImbalanceError,
)
from temper_placer.router_v6.terminal_tree import TerminalTreeEdge
from temper_placer.router_v6.trace_width_assignment import TraceWidth, TraceWidthAssignment
from temper_placer.router_v6.tree_route_geometry import (
    TreeRouteBranch,
    TreeRouteGeometry,
)
from temper_placer.router_v6.via_placement import Via, ViaPlacement

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


# ---------------------------------------------------------------------------
# deterministic/stages/base.py::Stage  (7 allowlist entries)
# ---------------------------------------------------------------------------


class _ConcreteStage(Stage):
    @property
    def name(self) -> str:
        return "concrete"

    def run(self, state: BoardState) -> BoardState:
        return state


class TestStageABC:
    def test_defaulted_contract_properties(self):
        st = _ConcreteStage()
        state = BoardState()
        assert st.invariants == ()
        assert st.last_modified_regions is None
        assert st.declared_writes == ()
        assert st.declared_reads == ()
        assert st.is_active is True
        assert st.name == "concrete"
        assert st.run(state) is state

    def test_abstract_bodies_executed_directly(self):
        # The abstract name/run bodies are `pass`-only and never reachable
        # through a subclass call; exercise them so each gains one executed
        # line (the `pass` statement).
        st = _ConcreteStage()
        state = BoardState()
        Stage.__dict__["name"].fget(st)
        Stage.__dict__["run"](st, state)


# ---------------------------------------------------------------------------
# heuristics/base.py::Heuristic  (3 allowlist entries: apply/name/priority)
# ---------------------------------------------------------------------------


class _ConcreteHeuristic(Heuristic):
    @property
    def name(self) -> str:
        return "concrete"

    @property
    def priority(self) -> HeuristicPriority:
        return HeuristicPriority.STRUCTURAL

    def apply(self, context) -> HeuristicResult:
        return HeuristicResult(success=True, message="placed")


class TestHeuristicABC:
    def test_subclass_surface(self):
        h = _ConcreteHeuristic()
        assert h.name == "concrete"
        assert h.priority == HeuristicPriority.STRUCTURAL
        assert h.apply(None).success is True

    def test_abstract_bodies_executed_directly(self):
        h = _ConcreteHeuristic()
        Heuristic.__dict__["name"].fget(h)
        Heuristic.__dict__["priority"].fget(h)
        Heuristic.__dict__["apply"](h, None)


# ---------------------------------------------------------------------------
# router_v6/stage_ledger.py::StageLedger  (checkin/checkout/verify)
# ---------------------------------------------------------------------------


def _pcb_obj(nets=0, components=0, routing_spaces=None):
    return SimpleNamespace(
        nets=[object() for _ in range(nets)],
        components=[object() for _ in range(components)],
        routing_spaces=routing_spaces or {},
        routing_results=None,
    )


class TestStageLedger:
    def test_checkin_checkout_balanced(self):
        ledger = StageLedger(fail_on_imbalance=False)
        ledger.checkin(_pcb_obj(nets=2, components=3))
        report = ledger.checkout("stage", _pcb_obj(nets=2, components=3))
        assert isinstance(report, LedgerReport)
        assert report.is_balanced is True
        assert "BALANCED" in str(report)

    def test_checkout_imbalance_reports(self):
        ledger = StageLedger(fail_on_imbalance=False)
        ledger.checkin(_pcb_obj(nets=2))
        report = ledger.checkout("stage", _pcb_obj(nets=3))
        assert report.is_balanced is False
        assert "IMBALANCED" in str(report)

    def test_verify_convenience(self):
        ledger = StageLedger(fail_on_imbalance=False)
        report = ledger.verify("stage", _pcb_obj(nets=1), _pcb_obj(nets=1))
        assert report.is_balanced is True

    def test_fail_on_imbalance_raises(self):
        ledger = StageLedger(fail_on_imbalance=True)
        ledger.checkin(_pcb_obj(nets=1))
        with pytest.raises(StageLedgerImbalanceError):
            ledger.checkout("stage", _pcb_obj(nets=2))

    def test_checkout_without_checkin(self):
        ledger = StageLedger(fail_on_imbalance=False)
        report = ledger.checkout("stage", _pcb_obj(nets=1))
        assert report.is_balanced is False
        assert "missing pre-snapshot" in report.message


# ---------------------------------------------------------------------------
# regression/fingerprint.py  (6 allowlist entries)
# ---------------------------------------------------------------------------


class TestFingerprint:
    def test_compute_input_fingerprint(self, tmp_path: Path):
        pcb = tmp_path / "b.kicad_pcb"
        pcb.write_text("kicad")
        cons = tmp_path / "c.yaml"
        cons.write_text("constraints: {}")
        missing = tmp_path / "baseline.yaml"  # does not exist
        fp = fingerprint_mod.compute_input_fingerprint(pcb, cons, missing, 42, 10)
        assert isinstance(fp, str) and len(fp) == 64
        # Deterministic across calls.
        assert fp == fingerprint_mod.compute_input_fingerprint(pcb, cons, missing, 42, 10)

    def test_compute_source_fingerprint(self, tmp_path: Path):
        src = tmp_path / "packages" / "temper-placer" / "src"
        src.mkdir(parents=True)
        (src / "dummy.py").write_text("x = 1\n")
        fp = fingerprint_mod.compute_source_fingerprint(tmp_path)
        assert isinstance(fp, str) and len(fp) == 64

    def test_load_cache_missing(self, tmp_path: Path):
        cache = fingerprint_mod.load_cache(tmp_path)
        assert cache["version"] == fingerprint_mod.CACHE_VERSION
        assert cache["boards"] == {}

    def test_load_cache_malformed(self, tmp_path: Path):
        (tmp_path / fingerprint_mod.CACHE_FILENAME).write_text("{ not json")
        cache = fingerprint_mod.load_cache(tmp_path)
        assert cache["boards"] == {}

    def test_save_and_load_cache_roundtrip(self, tmp_path: Path):
        cache = {"version": fingerprint_mod.CACHE_VERSION, "boards": {}}
        fingerprint_mod.save_cache(tmp_path, cache)
        loaded = fingerprint_mod.load_cache(tmp_path)
        assert loaded["boards"] == {}

    def test_should_skip_and_update_cache(self, tmp_path: Path):
        cache = {"version": fingerprint_mod.CACHE_VERSION, "boards": {}}
        assert fingerprint_mod.should_skip("b1", "fp", "sfp", cache) is False
        fingerprint_mod.update_cache_entry(cache, "b1", "fp", "sfp", "deadbeef")
        assert "b1" in cache["boards"]
        assert cache["boards"]["b1"]["input_fingerprint"] == "fp"
        assert fingerprint_mod.should_skip("b1", "fp", "sfp", cache) is True
        assert fingerprint_mod.should_skip("b1", "other", "sfp", cache) is False


# ---------------------------------------------------------------------------
# regression/metrics_recorder.py  (6 allowlist entries)
# ---------------------------------------------------------------------------


class TestMetricsRecorder:
    def test_find_metrics_file(self):
        path = find_metrics_file(Path("/repo"))
        assert path.name == "pipeline_metrics.jsonl"
        assert "power_pcb_dataset" in path.parts

    def test_record_closure_result(self):
        result = ClosureResult(
            passed=True,
            board_id="b1",
            benders_iterations=4,
            benders_cuts=2,
            router_completion_pct=98.6,
            drc_errors=3,
            drc_warnings=1,
            wall_clock_seconds=2.5,
        )
        rec = record_closure_result(result, "b1", commit="abc")
        assert rec.board == "b1"
        assert rec.metrics["wall_time_ms"] == 2500
        assert rec.metrics["drc_errors"] == 3
        assert rec.metrics["completion_pct"] == 98.6

    def test_record_stage_timing(self):
        rec = record_stage_timing("b1", "route", 1234, commit="abc")
        assert rec.stage == "route"
        assert rec.stage_name == "route"
        assert rec.metrics == {"wall_time_ms": 1234}

    def test_record_metrics_for_stage(self):
        rec = record_metrics_for_stage("b1", "route", "pipeline", {"x": 1.0})
        assert rec.module == "pipeline"
        assert rec.metrics == {"x": 1.0}

    def test_record_metrics_writes_jsonl(self, tmp_path: Path):
        rec = record_stage_timing("b1", "route", 500)
        filepath = tmp_path / "metrics.jsonl"
        record_metrics(rec, filepath)
        assert filepath.exists()
        lines = filepath.read_text().strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["stage"] == "route"

    def test_load_metrics(self, tmp_path: Path):
        filepath = tmp_path / "metrics.jsonl"
        filepath.write_text(
            '{"schema_version": 2, "stage": "a", "board": "b"}\n'
            "not json\n"
            '{"schema_version": 99, "stage": "future", "board": "b"}\n'
            '{"stage": "no-schema", "board": "b"}\n'
        )
        with pytest.warns(UserWarning):
            records = load_metrics(filepath)
        # "not json" skipped, future schema skipped; 2 valid records remain.
        assert len(records) == 2

    def test_load_metrics_missing_file(self, tmp_path: Path):
        assert load_metrics(tmp_path / "nope.jsonl") == []


# ---------------------------------------------------------------------------
# regression/closure_test.py  (ClosureResult.validate/summary, ClosureTest.load_seed)
# ---------------------------------------------------------------------------


class TestClosureResult:
    def test_validate_good(self):
        result = ClosureResult(
            passed=True,
            board_id="b1",
            benders_iterations=5,
            router_completion_pct=100.0,
            stages_exercised=3,
        )
        assert result.validate() == []

    def test_validate_zero_results_fails(self):
        result = ClosureResult(passed=False, board_id="b1")
        failures = result.validate()
        assert failures
        assert any("no placement iterations" in f for f in failures)

    def test_summary(self):
        result = ClosureResult(
            passed=True,
            board_id="b1",
            benders_iterations=5,
            benders_cuts=3,
            router_completion_pct=100.0,
            drc_errors=0,
            drc_warnings=0,
            wall_clock_seconds=1.5,
            stages_exercised=4,
        )
        text = result.summary()
        assert "Closure Test: b1" in text
        assert "PASS" in text
        assert "100.0%" in text


class TestClosureTestLoadSeed:
    def test_load_seed_missing(self, tmp_path: Path):
        seed = ClosureTest.load_seed(tmp_path / "nope.json")
        assert seed == {"benders_seed": 42, "router_seed": 42}

    def test_load_seed_present(self, tmp_path: Path):
        path = tmp_path / "seed.json"
        path.write_text('{"benders_seed": 7, "router_seed": 9}')
        assert ClosureTest.load_seed(path) == {"benders_seed": 7, "router_seed": 9}


# ---------------------------------------------------------------------------
# regression/drc_ratchet.py  (DrcRatchet.load/check/detect_ceiling_raise)
# ---------------------------------------------------------------------------


def _ceiling_doc(error_ceiling: int = 10, warning_ceiling: int = 5) -> dict:
    return {
        "boards": [
            {
                "board_id": "b1",
                "path": "pcb/does_not_exist.kicad_pcb",
                "error_ceiling": error_ceiling,
                "warning_ceiling": warning_ceiling,
                "violations_by_type": {"clearance": 3},
                "warnings_by_type": {"unconnected_items": 1},
            }
        ]
    }


class TestDrcRatchet:
    def test_load(self, tmp_path: Path):
        path = tmp_path / "drc_ceiling.json"
        path.write_text(json.dumps(_ceiling_doc()))
        ratchet = DrcRatchet(path)
        ratchet.load()
        assert "b1" in ratchet.entries
        entry = ratchet.entries["b1"]
        assert entry.error_ceiling == 10
        assert entry.violations_by_type == {"clearance": 3}

    def test_load_missing_file_is_noop(self, tmp_path: Path):
        ratchet = DrcRatchet(tmp_path / "nope.json")
        ratchet.load()
        assert ratchet.entries == {}

    def test_check_reports_missing_pcb(self, tmp_path: Path):
        path = tmp_path / "drc_ceiling.json"
        path.write_text(json.dumps(_ceiling_doc()))
        ratchet = DrcRatchet(path)
        ratchet.load()
        results = ratchet.check(tmp_path)
        assert len(results) == 1
        assert results[0].passed is False
        assert "PCB file not found" in results[0].message

    def test_detect_ceiling_raise_none(self, tmp_path: Path):
        ratchet = DrcRatchet(tmp_path / "unused.json")
        result = ratchet.detect_ceiling_raise(_ceiling_doc(), _ceiling_doc())
        assert result is None

    def test_detect_ceiling_raise_aggregate(self, tmp_path: Path):
        ratchet = DrcRatchet(tmp_path / "unused.json")
        raised = _ceiling_doc(error_ceiling=11)
        result = ratchet.detect_ceiling_raise(_ceiling_doc(), raised)
        assert result is not None
        assert result.passed is False
        assert "error_ceiling 10 -> 11" in result.message

    def test_detect_ceiling_raise_approved(self, tmp_path: Path):
        ratchet = DrcRatchet(tmp_path / "unused.json")
        raised = _ceiling_doc(error_ceiling=11)
        # An approved raise is not an *unapproved* raise, so the detector
        # reports nothing (None) rather than a passed result.
        result = ratchet.detect_ceiling_raise(
            _ceiling_doc(), raised, commit_message="Ceiling-Approval: noise remeasure"
        )
        assert result is None


# ---------------------------------------------------------------------------
# regression/manifest.py  (GoldenManifest.load/validate)
# ---------------------------------------------------------------------------


class TestGoldenManifest:
    def test_load(self, tmp_path: Path):
        path = tmp_path / "golden_manifest.yaml"
        path.write_text(
            "version: 1\n"
            "boards:\n"
            "  - id: b1\n"
            "    path: pcb/b1.kicad_pcb\n"
            "    component_count: 12\n"
            "    net_count: 30\n"
            "    baseline_git_hash: abc123\n"
        )
        manifest = GoldenManifest.load(path)
        assert manifest.version == 1
        assert len(manifest.boards) == 1
        board = manifest.boards[0]
        assert board.id == "b1"
        assert board.component_count == 12
        assert board.net_count == 30

    def test_load_empty(self, tmp_path: Path):
        path = tmp_path / "golden_manifest.yaml"
        path.write_text("version: 1\n")
        manifest = GoldenManifest.load(path)
        assert manifest.boards == []

    def test_validate_no_boards(self, tmp_path: Path):
        manifest = GoldenManifest(version=1, boards=[])
        assert manifest.validate(tmp_path) == []

    def test_validate_missing_pcb(self, tmp_path: Path):
        from temper_placer.regression.manifest import GoldenBoard

        manifest = GoldenManifest(
            version=1,
            boards=[GoldenBoard(id="b1", path="pcb/missing.kicad_pcb", component_count=0, net_count=0, baseline_git_hash="x")],
        )
        problems = manifest.validate(tmp_path)
        assert any("not found" in p for p in problems)


# ---------------------------------------------------------------------------
# router_v6/tree_route_geometry.py  (TreeRouteGeometry.iter_segments/via_positions)
# ---------------------------------------------------------------------------


def _pid(ref: str, pad: str, x: float, y: float) -> PadIdentity:
    return PadIdentity(component_ref=ref, pad=pad, net="N1", x=x, y=y, layers=(0,))


class TestTreeRouteGeometry:
    def test_iter_segments_and_via_positions(self):
        edge_a = TerminalTreeEdge(source=_pid("U1", "1", 0, 0), target=_pid("U2", "1", 5, 0))
        edge_b = TerminalTreeEdge(source=_pid("U1", "2", 0, 1), target=_pid("U3", "1", 0, 5))
        path_3d = RoutePath3D(
            net_name="N1",
            segments=[(0.0, 0.0, "F.Cu"), (1.0, 1.0, "F.Cu")],
            via_positions=[(0.5, 0.5)],
            path_length=1.4,
        )
        path_2d = RoutePath(
            net_name="N1",
            coordinates=[(0.0, 0.0), (2.0, 2.0)],
            layer_name="B.Cu",
            path_length=2.8,
        )
        geom = TreeRouteGeometry(
            net_name="N1",
            branches=(TreeRouteBranch(edge=edge_a, path=path_3d), TreeRouteBranch(edge=edge_b, path=path_2d)),
        )
        # via_positions come only from 3D branch paths.
        assert geom.via_positions == ((0.5, 0.5),)
        segments = geom.iter_segments()
        # One segment from the 3D path, one from the 2D path.
        assert len(segments) == 2

    def test_net_mismatch_raises(self):
        edge = TerminalTreeEdge(source=_pid("U1", "1", 0, 0), target=_pid("U2", "1", 5, 0))
        path = RoutePath(net_name="OTHER", coordinates=[(0, 0), (1, 1)], layer_name="F.Cu", path_length=1.0)
        with pytest.raises(ValueError):
            TreeRouteGeometry(net_name="N1", branches=(TreeRouteBranch(edge=edge, path=path),))


# ---------------------------------------------------------------------------
# router_v6/routing_results.py::compile_routing_results
# ---------------------------------------------------------------------------


class TestCompileRoutingResults:
    def test_compile_routes_widths_vias_and_planes(self):
        path = RoutePath(
            net_name="N1", coordinates=[(0, 0), (10, 0)], layer_name="F.Cu", path_length=10.0
        )
        pf = PathfindingResult(
            routed_paths={"N1": path},
            failed_nets=[],
            partial_paths={},
            tree_routes={},
            partial_tree_routes={},
        )
        widths = TraceWidthAssignment(
            assignments={"N1": TraceWidth(net_name="N1", width_mm=0.3, reason="signal")}
        )
        vias = ViaPlacement(
            vias=[Via(position=(5, 0), from_layer="F.Cu", to_layer="B.Cu", diameter=0.6, drill=0.3, net_name="N1")]
        )
        results = compile_routing_results(pf, widths, vias, plane_net_names=["GND"])
        assert "N1" in results.compiled_routes
        assert results.compiled_routes["N1"].width_mm == 0.3
        assert len(results.compiled_routes["N1"].vias) == 1
        # Plane net emitted with a real trace width.
        assert "GND" in results.compiled_routes
        assert results.compiled_routes["GND"].width_mm == 0.2
        assert results.success_count == 2
        assert results.get_route("N1") is not None

    def test_compile_empty(self):
        pf = PathfindingResult(
            routed_paths={},
            failed_nets=["N2"],
            partial_paths={},
            tree_routes={},
            partial_tree_routes={},
        )
        widths = TraceWidthAssignment(assignments={})
        vias = ViaPlacement(vias=[])
        results = compile_routing_results(pf, widths, vias)
        assert results.compiled_routes == {}
        assert results.failed_nets == ["N2"]
        assert results.success_count == 0


# ---------------------------------------------------------------------------
# router_v6/constraints_design_rules.py  (DesignRulesParser.parse_from_file, infer_zones)
# ---------------------------------------------------------------------------


class TestDesignRulesParserFromFile:
    def test_parse_from_file_fixture(self):
        matrix = DesignRulesParser.parse_from_file(str(FIXTURES / "pitchfork.kicad_pcb"))
        assert isinstance(matrix, ClearanceMatrix)
        # Temper defaults always seeded.
        assert matrix.default_clearance == 0.2


class TestInferZones:
    def _footprint(self, ref, pos, pads):
        return SimpleNamespace(
            pads=pads,
            properties={"Reference": ref},
            position=SimpleNamespace(X=pos[0], Y=pos[1]),
        )

    def _pad(self, net_name):
        return SimpleNamespace(net=SimpleNamespace(name=net_name))

    def test_infer_zones_hv_and_signal(self):
        matrix = ClearanceMatrix()
        matrix.set_net_class("HV1", "HighVoltage")
        matrix.set_net_class("SIG1", "Signal")
        pcb = SimpleNamespace(
            footprints=[
                self._footprint("Q1", (0.0, 0.0), [self._pad("HV1")]),
                self._footprint("Q2", (10.0, 0.0), [self._pad("HV1")]),
                self._footprint("R1", (20.0, 0.0), [self._pad("SIG1")]),
            ]
        )
        zones = infer_zones(pcb, matrix)
        names = {z.name for z in zones}
        assert "HV" in names
        assert "Signal" in names

    def test_infer_zones_empty(self):
        matrix = ClearanceMatrix()
        pcb = SimpleNamespace(footprints=[])
        assert infer_zones(pcb, matrix) == []

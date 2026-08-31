"""Coverage-paydown wave 19: validation/spice, mfem_compare, drc_runner
data-surface, helps_battery, prereg schema, battery_run artifacts, and
deterministic/router_v6 pure loaders (guard_strip, channels,
drc_parser, stage_validators, test_boards).

Targets allowlist entries that are pure functions, dataclass methods, or
cheaply-constructed observers reachable from ``tests/core/`` without a live
ngspice/kicad-cli backend or a full FDM solve.  Every target is exercised
directly so the CI-exact coverage run records non-zero line coverage and the
entry becomes removable.

Do NOT edit ``.coverage-allowlist`` here -- the orchestrator applies the
removals after CI-exact verification.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import yaml
from shapely.geometry import Polygon

from temper_placer.deterministic.channels import ChannelMap, ChannelSidecarError
from temper_placer.deterministic.feedback.drc_parser import parse_kicad_drc
from temper_placer.deterministic.geometry.guard_strip import compute_guard_strip
from temper_placer.physics.thermal_fdm import ThermalFDMConfig
from temper_placer.router_v6 import stage_validators as sv
from temper_placer.router_v6.test_boards import (
    get_available_boards,
    get_board_by_name,
    print_test_suite_status,
)
from temper_placer.router_v6.test_boards import TestBoard as BoardCatalogEntry
from temper_placer.validation.drc_result import ClearanceCheck, CourtyardCheck, PowerDomainCheck
from temper_placer.validation.drc_runner import CheckRunner
from temper_placer.validation.helps_battery import BatteryVerdict, run_helps_battery
from temper_placer.validation.mfem_compare import compare_fields, project_mfem_to_fdm
from temper_placer.validation.mfem_runner import MFEMResult
from temper_placer.validation.prereg.schema import PreregistrationManifest
from temper_placer.validation.results.battery_run import BatteryRunArtifact
from temper_placer.validation.scorecard import GateMargin, MarginScorecard
from temper_placer.validation.spice import (
    NgspiceValidator,
    PlacementSpiceResult,
    SpiceMeasurement,
    SpiceResult,
    compute_total_spice_penalty,
    create_validation_netlist,
    estimate_loop_inductance,
    run_all_placement_validations,
    run_bootstrap_simulation,
    run_gate_drive_simulation,
    run_power_integrity_simulation,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _thermal_record() -> dict:
    """Minimal well-formed thermal field preregistration record."""
    return {
        "field_name": "thermal",
        "independent_instrument": "temper_placer.physics.thermal.ThermalOracle",
        "cheap_baseline": {
            "name": "uniform_heat_spread",
            "description": "No thermal optimization.",
            "metric": "thermal_score",
            "target_value": 0.0,
            "because": "Worst-case thermal profile.",
        },
        "parametric_ranges": [
            {
                "parameter": "max_heatspread_mm",
                "min": 5.0,
                "max": 40.0,
                "because": "Tight enclosure to open chassis.",
            }
        ],
        "structural_bounding_cases": [
            {
                "case_name": "single_igbt",
                "description": "Single IGBT, passive cooling.",
                "because": "Minimum viable configuration.",
            }
        ],
        "pass_bar": {
            "margin_gain": {"name": "X", "value": 0.10, "because": "X rationale"},
            "beat_cheap_baseline_by": {"name": "Y", "value": 0.05, "because": "Y rationale"},
            "across_perturbations": {"name": "N", "value": 2.0, "because": "N rationale"},
        },
        "kill_criterion": {
            "description": "Ships iff pass bar met.",
            "because": "Thermal is safety-critical.",
        },
        "cost_budget": {
            "max_total_battery_seconds": 3600.0,
            "max_rounds_budget": 20,
            "field_convergence_round_limit": 5,
            "thermal_grid_cells_max": 10000,
            "target_solve_time_ms_per_field": 5000.0,
        },
    }


def _write_prereg(tmp_path: Path) -> Path:
    path = tmp_path / "prereg.yaml"
    path.write_text(
        yaml.dump(
            {
                "version": 1,
                "created_at": "2026-07-09T00:00:00Z",
                "fields": [_thermal_record()],
            }
        )
    )
    return path


def _make_validator() -> NgspiceValidator:
    """Validator with an unavailable ngspice path (deterministic unavailable path)."""
    return NgspiceValidator(ngspice_path="/nonexistent/ngspice")


# ---------------------------------------------------------------------------
# validation/spice
# ---------------------------------------------------------------------------


class TestSpiceMeasurement:
    def test_to_dict(self):
        m = SpiceMeasurement(name="v_peak", value=12.5, unit="V", targ=1.0, trig=0.5)
        d = m.to_dict()
        assert d["name"] == "v_peak"
        assert d["value"] == 12.5
        assert d["unit"] == "V"
        assert d["targ"] == 1.0
        assert d["trig"] == 0.5


class TestSpiceResult:
    def test_get_value_hit_and_default(self):
        r = SpiceResult(success=True, measurements={"v": SpiceMeasurement("v", 1.5, "V")})
        assert r.get_value("v") == pytest.approx(1.5)
        assert r.get_value("missing", 9.9) == pytest.approx(9.9)

    def test_summary_success(self):
        r = SpiceResult(
            success=True,
            measurements={"v": SpiceMeasurement("v", 1.5, "V")},
            elapsed_ms=3.0,
        )
        s = r.summary()
        assert "SUCCESS" in s
        assert "v = 1.500000e+00" in s
        assert "Elapsed" in s

    def test_summary_failed_with_errors(self):
        r = SpiceResult(success=False, errors=["boom"], elapsed_ms=1.0)
        s = r.summary()
        assert "FAILED" in s
        assert "boom" in s


class TestPlacementSpiceResult:
    def test_passed_true(self):
        psr = PlacementSpiceResult(
            spice_result=SpiceResult(success=True),
            template_name="t",
            threshold_results={"a": {"passed": True, "value": 1.0}},
        )
        assert psr.passed is True

    def test_passed_false_on_spice_failure(self):
        psr = PlacementSpiceResult(spice_result=SpiceResult(success=False), template_name="t")
        assert psr.passed is False

    def test_passed_false_on_empty_thresholds(self):
        # anti-vacuous-truth: zero thresholds checked -> not passed
        psr = PlacementSpiceResult(spice_result=SpiceResult(success=True), template_name="t")
        assert psr.passed is False

    def test_summary(self):
        psr = PlacementSpiceResult(
            spice_result=SpiceResult(success=True),
            template_name="gate_drive",
            penalty=0.5,
            threshold_results={"a": {"passed": True, "value": 1.0}},
        )
        s = psr.summary()
        assert "gate_drive" in s
        assert "Penalty" in s
        assert "Threshold checks" in s


class TestEstimateLoopInductance:
    def test_too_few_components(self):
        assert estimate_loop_inductance({"Q1": (0, 0), "Q2": (1, 1)}, ["Q1", "Q2"]) == 0.0

    def test_missing_component(self):
        assert (
            estimate_loop_inductance({"Q1": (0, 0)}, ["Q1", "Q2", "Q3"]) == 0.0
        )

    def test_triangle_loop(self):
        ind = estimate_loop_inductance(
            {"Q1": (0.0, 0.0), "Q2": (10.0, 0.0), "Q3": (10.0, 10.0)},
            ["Q1", "Q2", "Q3"],
        )
        assert ind > 0.0


class TestCreateValidationNetlist:
    def test_substitution(self):
        out = create_validation_netlist(
            "L {{LOOP}} R {{RES}}",
            {"LOOP": "50n", "RES": "4.7"},
        )
        assert out == "L 50n R 4.7"

    def test_no_params(self):
        assert create_validation_netlist("plain", {}) == "plain"


class TestComputeTotalSpicePenalty:
    def test_weighted(self):
        results = {
            "gate_drive": PlacementSpiceResult(spice_result=SpiceResult(True), template_name="gd", penalty=2.0),
            "power_integrity": PlacementSpiceResult(spice_result=SpiceResult(True), template_name="pi", penalty=1.0),
        }
        assert compute_total_spice_penalty(results) == pytest.approx(3.0)
        assert compute_total_spice_penalty(results, {"gate_drive": 2.0}) == pytest.approx(5.0)


class TestNgspiceValidator:
    def test_name(self):
        assert _make_validator().name == "NgspiceValidator"

    def test_is_available_false(self):
        assert _make_validator().is_available() is False

    def test_check_ngspice_unavailable(self):
        assert _make_validator().check_ngspice() is False

    def test_validate_unavailable_skips(self):
        result = _make_validator().validate(None, None, None)
        assert result.valid is True
        assert any(i.code == "SPICE_NOT_AVAILABLE" for i in result.issues)

    def test_run_simulation_unavailable(self):
        result = _make_validator().run_simulation(Path("/tmp/nope.cir"))
        assert result.success is False
        assert result.errors == ["ngspice not available"]

    def test_run_template_unsubstituted(self):
        result = _make_validator().run_template("L {{LOOP}}", {})
        assert result.success is False
        assert "Unsubstituted" in result.errors[0]

    def test_run_template_unavailable(self):
        result = _make_validator().run_template("V1 1 0 DC 5", {})
        assert result.success is False

    def test_run_netlist_string_unavailable(self):
        result = _make_validator().run_netlist_string("V1 1 0 DC 5")
        assert result.success is False


class TestPlacementSpiceSimulations:
    def test_run_gate_drive_simulation(self):
        v = _make_validator()
        result = run_gate_drive_simulation(
            v, {"U_GD": (0.0, 0.0), "Q1": (10.0, 0.0), "R_GATE": (10.0, 10.0)}
        )
        assert result.template_name == "gate_drive"
        assert result.spice_result.success is False
        assert result.penalty == pytest.approx(50.0)

    def test_run_bootstrap_simulation(self):
        v = _make_validator()
        result = run_bootstrap_simulation(
            v, {"U_GD": (0.0, 0.0), "D_BOOT": (10.0, 0.0), "C_BOOT": (10.0, 10.0)}
        )
        assert result.template_name == "bootstrap_charging"
        assert result.penalty == pytest.approx(50.0)

    def test_run_power_integrity_simulation(self):
        v = _make_validator()
        result = run_power_integrity_simulation(
            v, {"C_DC": (0.0, 0.0), "Q1": (10.0, 0.0), "Q2": (10.0, 10.0)}
        )
        assert result.template_name == "power_integrity"
        assert result.penalty == pytest.approx(50.0)

    def test_run_all_placement_validations(self):
        v = _make_validator()
        results = run_all_placement_validations(
            v, {"C_DC": (0.0, 0.0), "Q1": (10.0, 0.0), "Q2": (10.0, 10.0)}
        )
        assert set(results.keys()) == {"gate_drive", "bootstrap_charging", "power_integrity"}
        assert all(r.spice_result.success is False for r in results.values())


# ---------------------------------------------------------------------------
# validation/mfem_compare
# ---------------------------------------------------------------------------


class TestCompareFields:
    def test_agree_within_tolerance(self):
        fdm = np.zeros((4, 4))
        mfem = np.full((4, 4), 2.0)
        result = compare_fields(fdm, mfem, tolerance_C=5.0)
        assert result.max_delta_C == pytest.approx(2.0)
        assert result.exceeds_tolerance is False
        assert result.attribution == "fields agree within tolerance"

    def test_exceeds_tolerance_with_devices(self):
        fdm = np.zeros((4, 4))
        mfem = np.full((4, 4), 8.0)
        result = compare_fields(
            fdm, mfem, tolerance_C=5.0, devices={"Q1": (0, 0), "Q2": (10, 10)}
        )
        assert result.exceeds_tolerance is True
        assert result.device_deltas["Q1"] == pytest.approx(8.0)
        # out-of-bounds device coords clamp to grid bounds
        assert result.device_deltas["Q2"] == pytest.approx(8.0)
        assert "disagreement" in result.attribution

    def test_mismatched_shape_raises(self):
        with pytest.raises(ValueError):
            compare_fields(np.zeros((4, 4)), np.zeros((3, 3)))


class TestProjectMfemToFdm:
    def _config(self):
        return ThermalFDMConfig(
            cell_size_mm=1.0, origin_mm=(0.0, 0.0), height_cells=4, width_cells=4
        )

    def test_flat_reshape_fallback(self):
        result = MFEMResult(node_coords=None, temperature=np.arange(16, dtype=float))
        projected = project_mfem_to_fdm(result, self._config())
        assert projected.shape == (4, 4)

    def test_nearest_neighbor_lookup(self):
        result = MFEMResult(
            node_coords=np.array([[0.5, 0.5, 0.0], [1.5, 0.5, 0.0]]),
            temperature=np.array([1.0, 2.0]),
        )
        projected = project_mfem_to_fdm(result, self._config())
        assert projected.shape == (4, 4)
        assert projected[0, 0] == pytest.approx(1.0)

    def test_unprojectable_size_raises(self):
        result = MFEMResult(node_coords=None, temperature=np.array([1.0, 2.0, 3.0]))
        with pytest.raises(ValueError):
            project_mfem_to_fdm(result, self._config())


# ---------------------------------------------------------------------------
# validation/drc_runner — CheckRunner data surface
# ---------------------------------------------------------------------------


class TestCheckRunnerDataSurface:
    def test_empty_runner(self):
        r = CheckRunner()
        assert r.categories == set()
        assert r.check_names == []
        assert "0 checks" in r.summary()

    def test_add_check_and_categories(self):
        r = CheckRunner()
        r.add_check(ClearanceCheck())
        r.add_checks([PowerDomainCheck(), CourtyardCheck()])
        assert r.categories == {"drc", "erc"}
        assert r.check_names == ["drc_clearance", "erc_power_domain", "drc_courtyard"]
        assert len(r.checks) == 3

    def test_get_checks_by_category(self):
        r = CheckRunner()
        r.add_checks([ClearanceCheck(), CourtyardCheck(), PowerDomainCheck()])
        drc = r.get_checks_by_category("drc")
        assert {c.name for c in drc} == {"drc_clearance", "drc_courtyard"}
        assert r.get_checks_by_category("emc") == []

    def test_clear(self):
        r = CheckRunner()
        r.add_check(ClearanceCheck())
        assert r.check_names == ["drc_clearance"]
        r.clear()
        assert r.check_names == []


# ---------------------------------------------------------------------------
# validation/prereg schema + helps_battery + battery_run
# ---------------------------------------------------------------------------


class TestPreregistrationManifestLoad:
    def test_load(self, tmp_path):
        path = _write_prereg(tmp_path)
        manifest = PreregistrationManifest.load(path)
        assert manifest.version == 1
        assert [f.field_name for f in manifest.fields] == ["thermal"]

    def test_temporal_gate_accepts_earlier_created(self, tmp_path):
        path = _write_prereg(tmp_path)
        manifest = PreregistrationManifest.load(
            path, battery_run_timestamp=datetime(2026, 7, 10, tzinfo=UTC)
        )
        assert manifest.version == 1

    def test_temporal_gate_rejects_post_dating(self, tmp_path):
        path = _write_prereg(tmp_path)
        with pytest.raises(ValueError):
            PreregistrationManifest.load(
                path, battery_run_timestamp=datetime(2026, 7, 8, tzinfo=UTC)
            )


class TestBatteryRunArtifact:
    def _artifact(self) -> BatteryRunArtifact:
        return BatteryRunArtifact(
            field_name="thermal",
            verdict=BatteryVerdict.KEEP,
            verdict_details="d",
            prereg_version=1,
            prereg_created_at="2026-07-09T00:00:00Z",
            run_timestamp_utc="2026-07-10T00:00:00Z",
            run_hash="abc",
            gate_clean=True,
            human_reference_calibrated=False,
            human_reference={},
            cost_seconds=1.0,
            budget_exceeded=False,
            budget_detail="",
            divergence_detected=True,
            divergence_detail="dd",
            n_perturbations=5,
        )

    def test_to_dict(self):
        d = self._artifact().to_dict()
        assert d["verdict"] == "keep"
        assert d["field_name"] == "thermal"

    def test_save_and_load_roundtrip(self, tmp_path):
        artifact = self._artifact()
        path = tmp_path / "artifact.json"
        artifact.save(path)
        loaded = BatteryRunArtifact.load(path)
        assert loaded.verdict == BatteryVerdict.KEEP
        assert loaded.field_name == "thermal"
        assert loaded.run_hash == "abc"


class TestRunHelpsBattery:
    def test_full_run(self, tmp_path):
        manifest = PreregistrationManifest.load(_write_prereg(tmp_path))

        def build_arm(arm_id, _pert, _board, _netlist, _seed):
            x = 1.0 if arm_id == "physics_field" else 0.0
            return type("P", (), {"positions": np.array([[x, 0.0]], dtype=np.float32)})()

        def score(_placement, _board, _netlist):
            return MarginScorecard(
                board_id="b",
                scorer_id="thermal-gauss-seidel",
                margins=[GateMargin(gate_name="thermal", value=0.5, unit="C")],
            )

        result = run_helps_battery(
            manifest=manifest,
            field_name="thermal",
            board=None,
            netlist=None,
            build_arm_placement=build_arm,
            score_placement_fn=score,
            scorer_id="thermal-gauss-seidel",
        )
        assert result.n_perturbations == 2
        assert len(result.per_run) == 6  # 3 arms x 2 perturbations
        assert result.divergence_detected is True
        assert isinstance(result.verdict, BatteryVerdict)


# ---------------------------------------------------------------------------
# deterministic/geometry/guard_strip
# ---------------------------------------------------------------------------


class TestComputeGuardStrip:
    def _outline(self) -> Polygon:
        return Polygon([(0, 0), (100, 0), (100, 50), (0, 50)])

    def test_zero_width(self):
        hv, lv, corridor = compute_guard_strip(self._outline(), 0)
        assert hv.is_empty
        assert corridor.is_empty
        assert lv.area == pytest.approx(5000.0)

    def test_normal_width(self):
        hv, lv, corridor = compute_guard_strip(self._outline(), 5.0)
        assert lv.area == pytest.approx((100 - 10) * (50 - 10))
        assert corridor.area > 0

    def test_width_larger_than_half_side(self):
        hv, lv, corridor = compute_guard_strip(self._outline(), 1000.0)
        assert lv.is_empty
        assert hv.area == pytest.approx(5000.0)
        assert corridor.area == pytest.approx(5000.0)

    def test_non_polygon_raises(self):
        with pytest.raises(ValueError):
            compute_guard_strip([(0, 0), (1, 0)], 1.0)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# deterministic/channels
# ---------------------------------------------------------------------------


class TestChannelMapLoadFromSidecar:
    def _payload(self):
        return {
            "temper_schema_hash": "temper.channels.v1",
            "cell_size_um": 1000.0,
            "grid": [[0.1, 0.2], [0.3, 0.4]],
            "bottlenecks": [{"x": 0, "y": 0, "layer": "F.Cu", "severity": "HIGH", "score": 0.8}],
        }

    def test_load(self, tmp_path):
        p = tmp_path / "channels.json"
        p.write_text(json.dumps(self._payload()))
        cm = ChannelMap.load_from_sidecar(p)
        assert cm.width == 2
        assert cm.height == 2
        assert cm.cell_size_um == 1000.0
        assert len(cm.bottlenecks) == 1
        assert cm.has_grid() is True

    def test_missing_file(self, tmp_path):
        with pytest.raises(ChannelSidecarError):
            ChannelMap.load_from_sidecar(tmp_path / "nope.json")

    def test_malformed_json(self, tmp_path):
        p = tmp_path / "channels.json"
        p.write_text("{ not json")
        with pytest.raises(ChannelSidecarError):
            ChannelMap.load_from_sidecar(p)

    def test_unknown_schema_hash(self, tmp_path):
        payload = self._payload()
        payload["temper_schema_hash"] = "temper.channels.v999"
        p = tmp_path / "channels.json"
        p.write_text(json.dumps(payload))
        with pytest.raises(ChannelSidecarError):
            ChannelMap.load_from_sidecar(p)


# ---------------------------------------------------------------------------
# deterministic/feedback/drc_parser
# ---------------------------------------------------------------------------


class TestParseKicadDrc:
    def test_parse_violations_and_unconnected(self, tmp_path):
        p = tmp_path / "drc.json"
        p.write_text(
            json.dumps(
                {
                    "violations": [
                        {
                            "type": "clearance",
                            "severity": "error",
                            "description": "clearance",
                            "items": [{"reference": "Q1"}, {"reference": "Q2"}],
                            "pos": {"x": 0, "y": 0},
                        }
                    ],
                    "unconnected_items": [
                        {
                            "type": "unconnected_items",
                            "severity": "warning",
                            "description": "unrouted",
                            "items": [],
                            "pos": None,
                        }
                    ],
                }
            )
        )
        report = parse_kicad_drc(str(p))
        assert len(report) == 2

    def test_empty_report(self, tmp_path):
        p = tmp_path / "drc.json"
        p.write_text(json.dumps({"violations": [], "unconnected_items": []}))
        report = parse_kicad_drc(str(p))
        assert len(report) == 0


# ---------------------------------------------------------------------------
# router_v6/stage_validators
# ---------------------------------------------------------------------------


class TestStageValidators:
    def _restore_registry(self):
        # Preserve any import-time-registered validators for other tests.
        return dict(sv.VALIDATOR_REGISTRY)

    def test_run_validators_single_and_list(self):
        stage = "v19_unique_stage"

        @sv.register_validator(stage)
        def single(state):  # noqa: ANN001,ANN202
            return sv.StageDRCFailure(field="x", value=1, reason="r")

        @sv.register_validator(stage)
        def multi(state):  # noqa: ANN001,ANN202
            return [sv.StageDRCFailure(field="a", value=1, reason="r1"),
                    sv.StageDRCFailure(field="b", value=2, reason="r2")]

        failures = sv.run_validators(stage, None)
        assert len(failures) == 3
        assert stage in sv.get_registered_stages()
        # re-registering the same function is idempotent
        sv.register_validator(stage)(single)
        assert sv.run_validators(stage, None) == failures

    def test_clear_validators(self):
        saved = self._restore_registry()
        try:
            sv.clear_validators()
            assert sv.VALIDATOR_REGISTRY == {}
            assert sv.get_registered_stages() == []
        finally:
            sv.VALIDATOR_REGISTRY.update(saved)


# ---------------------------------------------------------------------------
# router_v6/test_boards
# ---------------------------------------------------------------------------


class TestTestBoards:
    def test_exists(self, tmp_path):
        f = tmp_path / "board.kicad_pcb"
        f.write_text("(kicad_pcb")
        board = BoardCatalogEntry(
            name="t", path=f, domain="digital", layers=2, expected_net_count=1,
            description="d", source="s", license="l",
        )
        assert board.exists() is True
        assert BoardCatalogEntry(
            name="t2", path=tmp_path / "missing.kicad_pcb", domain="digital",
            layers=2, expected_net_count=1, description="d", source="s", license="l",
        ).exists() is False

    def test_get_available_boards(self):
        boards = get_available_boards()
        assert all(isinstance(b, BoardCatalogEntry) for b in boards)

    def test_get_board_by_name_case_insensitive(self):
        assert get_board_by_name("piantor_right") is not None
        assert get_board_by_name("PIANTOR_RIGHT") is not None
        assert get_board_by_name("no_such_board") is None

    def test_print_test_suite_status(self, capsys):
        print_test_suite_status()
        out = capsys.readouterr().out
        assert "Router V6 Test Suite Status" in out
        assert "Digital Boards" in out

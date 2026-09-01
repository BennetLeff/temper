"""
Integration tests for the Rust quality oracle crate (temper_quality_oracle).

Covers:
- R14: E2E tests drive full oracle through PyO3
- Parity with existing Python quality pipeline
- NormalizedScore error handling
- panic-to-exception safety (R15)
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

try:
    import temper_quality_oracle  # type: ignore[import-untyped]

    HAS_RUST_ORACLE = True
except ImportError:
    HAS_RUST_ORACLE = False


def require_oracle():
    if not HAS_RUST_ORACLE:
        pytest.skip("temper_quality_oracle not installed")


def evaluate_quality(netlist, placement, spec, metrics):
    """Exercise the two-step API used by production callers."""
    prepared = temper_quality_oracle.prepare_quality_py(netlist, spec)
    return temper_quality_oracle.evaluate_prepared_py(prepared, placement, metrics)


class TestOracleModule:
    @staticmethod
    def _corridor_evidence():
        root = Path(__file__).resolve().parents[4]
        evidence = root / "docs/evidence/net41-route-layer-corridor-20260831"
        predecessor = root / "docs/evidence/r14-hv-domain-refloorplan-20260831"
        return root, evidence, predecessor

    def _validated_screen(self, *, mutate_evidence=None):
        root, evidence, predecessor = self._corridor_evidence()
        scripts_dir = root / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import generate_kicad_dru

        declaration = (evidence / "declaration.json").read_bytes()
        manifest = (predecessor / "pre-route-manifest.json").read_bytes()
        candidate_set = json.loads(
            temper_quality_oracle.declare_corridor_candidates_from_evidence_json_py(
                declaration, manifest
            )
        )
        kwargs = {
            "declaration_bytes": declaration,
            "basis_bytes": (evidence / "design-basis.json").read_bytes(),
            "board_bytes": (root / "pcb/temper.kicad_pcb").read_bytes(),
            "predecessor_receipt_bytes": (predecessor / "terminal-receipt.json").read_bytes(),
            "predecessor_manifest_bytes": manifest,
            "domain_manifest_bytes": (root / "elec/domain_manifest.yaml").read_bytes(),
            "netlist_bytes": (root / "elec/build/default.net").read_bytes(),
            # The DRU is generated and gitignored, so a clean CI checkout has
            # no pcb/temper.kicad_dru to read. Exercise the same SSOT output
            # without making the integration test depend on local residue.
            "kicad_dru_bytes": generate_kicad_dru.generate_dru().encode(),
            "screening_request_json": json.dumps(
                {
                    "schema_version": "temper-regional-validated-screen-request/v4",
                    "candidates": [
                        {
                            "candidate_id": row["candidate_id"],
                            "minimum_clearance_mm": 6.0,
                            "minimum_creepage_mm": 12.6,
                            "route_length_mm": float(row["ordinal"]),
                        }
                        for row in candidate_set["candidates"]
                    ],
                    "route_budget": 12,
                }
            ),
        }
        if mutate_evidence is not None:
            mutate_evidence(kwargs)
        return json.loads(
            temper_quality_oracle.validate_and_screen_corridor_evidence_json_py(**kwargs)
        )

    def test_module_imports(self):
        require_oracle()
        assert callable(temper_quality_oracle.prepare_quality_py)

    def test_regional_declaration_is_sorted_and_budgeted(self):
        require_oracle()
        rows = temper_quality_oracle.declare_regional_candidates_py(
            ["C002", "C001"], [5.5, 4.0, 5.0, 4.5], 8
        )
        assert rows[0] == (1, "R14HV-001", "C001", 4.0)
        assert rows[-1] == (8, "R14HV-008", "C002", 5.5)
        with pytest.raises(ValueError, match="budget"):
            temper_quality_oracle.declare_regional_candidates_py(["C001"], [4.0, 4.5], 1)

    def test_pre_route_verdict_is_rust_owned_and_ordered(self):
        require_oracle()
        accepted, reasons = temper_quality_oracle.evaluate_pre_route_candidate_py(
            12.0, 11.0, 1, 1, 1, 1, 1, 1, 1, 1
        )
        assert not accepted
        assert reasons == [
            "k1_j1",
            "route_to_selv",
            "affected_safety",
            "safety_regression",
            "body_overlap",
            "courtyard_overlap",
            "containment",
        ]

    def test_isolation_qualification_has_one_rust_evaluator_registration(self):
        require_oracle()
        expected = [
            "evaluate_ct07_t2_qualification_json",
            "evaluate_iso7741_gate_drive_qualification_json",
            "evaluate_isolation_qualification_json",
        ]
        for name in expected:
            assert sum(exported == name for exported in dir(temper_quality_oracle)) == 1
            assert callable(getattr(temper_quality_oracle, name))

    def test_ct07_has_one_uniquely_named_rust_evaluator_registration(self):
        require_oracle()
        name = "evaluate_ct07_t2_qualification_json"
        assert sum(exported == name for exported in dir(temper_quality_oracle)) == 1
        assert callable(getattr(temper_quality_oracle, name))

    def test_ct07_boundary_matches_canonical_rust_output(self):
        require_oracle()
        package = _ct07_package()
        result = temper_quality_oracle.evaluate_ct07_t2_qualification_json(
            json.dumps(package)
        )
        assert json.loads(result) == {
            "schema_version": 1,
            "construction_id": "ct07-construction-1",
            "construction_digest": "d" * 64,
            "internal_stage": "stopped-indeterminate",
            "stage": "stopped-indeterminate",
            "reasons": [
                "r1.ocp02-dnf",
                "r10.electrical-thermal-rating",
                "r11.construction-identity",
                "r12.creepage",
                "r13.environmental-stress",
                "r14.production-controls",
                "r15.identity-sourcing",
                "r18.protected-artifacts",
                "r2.independent-coverage",
                "r3.trip-window-latency",
                "r4.trip-ordering",
                "r5.hardware-latch-lifecycle",
                "r6.single-fault-containment",
                "r7.transfer-function",
                "r8.waveform-detection",
                "r9.saturation-margin",
            ],
            "requirements": package["requirements"],
            "owner_floor": package["owner_floor"],
            "invalid_or_excluded_records": [],
            "limitations": [],
        }

    @pytest.mark.parametrize(
        "mutation, message",
        [
            (lambda _package: "not-json", "invalid CT07 qualification JSON"),
            (
                lambda package: {**package, "schema_version": 99},
                "unsupported CT07 schema version",
            ),
            (
                lambda package: {**package, "evidence_digest": "e" * 64},
                "evidence digest mismatch",
            ),
            (
                lambda package: {
                    **package,
                    "axes": package["axes"][:-1],
                },
                "invalid or missing internal axis",
            ),
        ],
        ids=["invalid-json", "unsupported-schema", "digest-mismatch", "missing-axis"],
    )
    def test_ct07_boundary_maps_invalid_payloads_to_stable_value_errors(
        self, mutation, message
    ):
        require_oracle()
        payload = mutation(_ct07_package())
        with pytest.raises(ValueError, match=message):
            temper_quality_oracle.evaluate_ct07_t2_qualification_json(
                payload if isinstance(payload, str) else json.dumps(payload)
            )

    def test_isolation_qualification_crosses_boundary_and_is_canonical(self):
        require_oracle()
        result = json.loads(
            temper_quality_oracle.evaluate_isolation_qualification_json(
                json.dumps(_qualification_manifest())
            )
        )
        assert result["schema_version"] == 1
        assert result["provenance"] == {"commit": "a" * 40, "dirty": True}
        assert [row["candidate"]["candidate_id"] for row in result["candidates"]] == [
            "gate-hybrid",
            "gate-replacement",
            "sensing-replacement",
            "sensing-slot",
        ]
        assert all(row["verdict"] == "qualified" for row in result["candidates"])

    def test_isolation_veto_is_evaluated_by_rust_not_python(self):
        require_oracle()
        manifest = _qualification_manifest()
        gate_candidate = next(
            candidate
            for candidate in manifest["candidates"]
            if candidate["candidate_id"] == "gate-replacement"
        )
        gate_candidate["axes"] = [
            axis
            if axis["code"] != "gate.timing_shutdown_uvlo"
            else {**axis, "status": "fail", "reason_code": "gate.shutdown.failed"}
            for axis in gate_candidate["axes"]
        ]
        result = json.loads(
            temper_quality_oracle.evaluate_isolation_qualification_json(json.dumps(manifest))
        )
        gate = next(row for row in result["candidates"] if row["candidate"]["candidate_id"] == "gate-replacement")
        assert gate["verdict"] == "rejected"
        assert gate["reasons"] == [
            {"code": "gate.shutdown.failed", "explanation": "gate.timing_shutdown_uvlo evidence"}
        ]

    def test_isolation_qualification_invalid_inputs_fail_closed(self):
        require_oracle()
        with pytest.raises(ValueError, match="invalid qualification manifest JSON"):
            temper_quality_oracle.evaluate_isolation_qualification_json("not-json")

        unsupported = _qualification_manifest()
        unsupported["schema_version"] = 99
        with pytest.raises(ValueError, match="unsupported qualification schema version"):
            temper_quality_oracle.evaluate_isolation_qualification_json(json.dumps(unsupported))

        missing = _qualification_manifest()
        missing["candidates"][0]["axes"] = [
            axis
            for axis in missing["candidates"][0]["axes"]
            if axis["code"] != "sensing.transfer_function"
        ]
        with pytest.raises(ValueError, match="missing required evidence axis"):
            temper_quality_oracle.evaluate_isolation_qualification_json(json.dumps(missing))

    @staticmethod
    def _corridor_evidence():
        root = Path(__file__).resolve().parents[4]
        evidence = root / "docs/evidence/net41-route-layer-corridor-20260831"
        predecessor = root / "docs/evidence/r14-hv-domain-refloorplan-20260831"
        return root, evidence, predecessor

    def _validated_screen(self, *, mutate_evidence=None):
        root, evidence, predecessor = self._corridor_evidence()
        declaration = (evidence / "declaration.json").read_bytes()
        manifest = (predecessor / "pre-route-manifest.json").read_bytes()
        candidate_set = json.loads(
            temper_quality_oracle.declare_corridor_candidates_from_evidence_json_py(
                declaration, manifest
            )
        )
        kwargs = {
            "declaration_bytes": declaration,
            "basis_bytes": (evidence / "design-basis.json").read_bytes(),
            "board_bytes": (root / "pcb/temper.kicad_pcb").read_bytes(),
            "predecessor_receipt_bytes": (predecessor / "terminal-receipt.json").read_bytes(),
            "predecessor_manifest_bytes": manifest,
            "domain_manifest_bytes": (root / "elec/domain_manifest.yaml").read_bytes(),
            "netlist_bytes": (root / "elec/build/default.net").read_bytes(),
            "kicad_dru_bytes": (root / "pcb/temper.kicad_dru").read_bytes(),
            "screening_request_json": json.dumps({
                "schema_version": "temper-regional-validated-screen-request/v4",
                "candidates": [
                    {
                        "candidate_id": row["candidate_id"],
                        "minimum_clearance_mm": 6.0,
                        "minimum_creepage_mm": 12.6,
                        "route_length_mm": float(row["ordinal"]),
                    }
                    for row in candidate_set["candidates"]
                ],
                "route_budget": 12,
            }),
        }
        if mutate_evidence is not None:
            mutate_evidence(kwargs)
        return json.loads(
            temper_quality_oracle.validate_and_screen_corridor_evidence_json_py(**kwargs)
        )

    def test_corridor_screening_validates_raw_evidence_atomically(self):
        require_oracle()
        verdict = self._validated_screen()
        assert verdict["schema_version"] == "temper-regional-validated-screen-verdict/v4"
        assert verdict["evaluated_count"] == 2880
        assert len(verdict["results"]) == 2880
        assert len(verdict["clearance_creepage_prefilter_subset"]) == 2880

    def test_free_form_corridor_authority_seams_are_absent(self):
        require_oracle()
        assert not hasattr(temper_quality_oracle, "declare_corridor_candidates_json_py")
        assert not hasattr(temper_quality_oracle, "screen_declared_corridor_candidates_json_py")


def _qualification_manifest():
    """Small, complete fixture for the Rust-owned qualification contract."""

    protected_paths = [
        "pcb/temper.kicad_pcb",
        "power_pcb_dataset/drc_ceiling.json",
        "elec/domain_manifest.yaml",
        "docs/ENVIRONMENTAL_SPEC.md",
        "packages/temper-placer/src/temper_placer/core/isolation_constants.py",
    ]

    def ref(kind):
        return {
            "kind": kind,
            "url": f"docs/evidence/{kind}.md",
            "revision": "rev-1",
            "retrieved_at": "2026-09-01",
            "sha256": "a" * 64,
        }

    def axis(code, status="pass"):
        item = {
            "code": code,
            "status": status,
            "reason_code": f"{code}.{'passed' if status == 'pass' else status}",
            "explanation": f"{code} evidence",
        }
        if code == "geometry.straight_corridor":
            item.update(
                {
                    "authority": "temper-quality-oracle::exact-copper",
                    "measured_mm": 12.6,
                    "required_mm": 12.6,
                    "source": {
                        "path": "docs/evidence/datasheet.md",
                        "sha256": "a" * 64,
                    },
                }
            )
        return item

    common = [
        "identity.lifecycle",
        "identity.sourcing",
        "package.footprint_provenance",
        "geometry.straight_corridor",
        "certification.insulation",
        "protected_inputs.base_identity",
    ]
    sensing = common + [
        "sensing.transfer_function",
        "sensing.saturation_thermal_hf",
        "sensing.coverage_disposition",
        "mechanical.conductor_and_mounting",
    ]
    gate = common + [
        "gate.channel_and_supply_contract",
        "gate.timing_shutdown_uvlo",
        "gate.integration_consequences",
    ]

    def candidate(candidate_id, family, domain, codes):
        axes = [axis(code) for code in codes]
        if family != "replacement":
            alternate = axis("geometry.alternate_authority")
            alternate["authority"] = "certification-lab:fixture"
            axes.append(alternate)
        return {
            "candidate_id": candidate_id,
            "family": family,
            "domain": domain,
            "manufacturer": "Acme",
            "part_number": candidate_id,
            "lifecycle_status": "active",
            "sourcing_status": "approved",
            "package": "PKG",
            "footprint_provenance": "library:PKG",
            "evidence_as_of": "2026-09-01",
            "datasheet": ref("datasheet"),
            "certification_references": [ref("certification")],
            "axes": axes,
        }

    return {
        "schema_version": 1,
        "campaign_id": "python-integration",
        "provenance": {"commit": "a" * 40, "dirty": True},
        "corridor_requirement_mm": 12.6,
        "candidates": [
            candidate("sensing-replacement", "replacement", "sensing", sensing),
            candidate("gate-replacement", "replacement", "gate-drive", gate),
            candidate("sensing-slot", "retain-with-slot", "sensing", sensing),
            candidate("gate-hybrid", "hybrid", "gate-drive", gate),
        ],
        "protected_inputs": [
            {"path": path, "sha256": "b" * 64} for path in protected_paths
        ],
    }


def _ct07_package():
    """Small complete CT07 package for the direct PyO3 contract tests."""

    raw = b"ct07-boundary"
    raw_digest = hashlib.sha256(raw).hexdigest()
    return {
        "schema_version": 1,
        "construction_id": "ct07-construction-1",
        "construction_digest": "d" * 64,
        "evidence_digest": raw_digest,
        "raw_evidence": [
            {"id": "raw-1", "sha256": raw_digest, "bytes": list(raw)}
        ],
        "axes": [
            {"code": code, "status": "pending", "reason": "awaiting evidence"}
            for code in [
                "r1.ocp02-dnf",
                "r2.independent-coverage",
                "r3.trip-window-latency",
                "r4.trip-ordering",
                "r5.hardware-latch-lifecycle",
                "r6.single-fault-containment",
                "r7.transfer-function",
                "r8.waveform-detection",
                "r9.saturation-margin",
                "r10.electrical-thermal-rating",
                "r11.construction-identity",
                "r12.creepage",
                "r13.environmental-stress",
                "r14.production-controls",
                "r15.identity-sourcing",
                "r18.protected-artifacts",
            ]
        ],
        "dispositions": [
            {
                "axis": "r1.ocp02-dnf",
                "owner_role": "board-product-safety",
                "verifier_role": "verification",
                "signed_artifact_digest": "e" * 64,
                "manual_verification_digest": "f" * 64,
                "status": "pending",
            }
        ],
        "requirements": [
            {
                "requirement": f"R{number}",
                "status": "pending",
                "implementation_owner": "ct07 qualification owner",
                "next_authority": "CT07 evidence owner",
            }
            for number in range(1, 21)
        ],
        "owner_floor": {
            "classification": "engineering-screen",
            "minimum_complete_assemblies": 5,
            "minimum_independent_lots": 2,
            "repetitions_per_electrical_corner": 3,
            "zero_failures_required": True,
            "larger_a7_sample_requirement": "pending A7 ruling",
        },
        "invalid_or_excluded_records": [],
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda manifest: manifest["provenance"].update({"commit": "UNKNOWN"}),
        lambda manifest: manifest["provenance"].update({"commit": "DERIVED"}),
        lambda manifest: manifest["provenance"].update({"commit": "A" * 40}),
        lambda manifest: manifest["provenance"].update({"commit": "a" * 39}),
        lambda manifest: manifest.update({"protected_inputs": []}),
        lambda manifest: manifest["protected_inputs"].__setitem__(
            0, {"path": "", "sha256": "b" * 64}
        ),
        lambda manifest: manifest["protected_inputs"].__setitem__(
            0, {"path": "/pcb/temper.kicad_pcb", "sha256": "b" * 64}
        ),
        lambda manifest: manifest["protected_inputs"].__setitem__(
            0, {"path": "../pcb/temper.kicad_pcb", "sha256": "b" * 64}
        ),
        lambda manifest: manifest["protected_inputs"].pop(),
        lambda manifest: manifest["protected_inputs"].append(
            {"path": "docs/extra.md", "sha256": "c" * 64}
        ),
        lambda manifest: manifest["protected_inputs"].append(
            manifest["protected_inputs"][0].copy()
        ),
    ],
    ids=[
        "unknown-commit",
        "derived-commit",
        "uppercase-commit",
        "short-commit",
        "empty-protected-set",
        "empty-protected-path",
        "absolute-protected-path",
        "traversal-protected-path",
        "missing-protected-path",
        "extra-protected-path",
        "duplicate-protected-path",
    ],
)
def test_isolation_qualification_provenance_envelope_is_rust_owned(mutation):
    require_oracle()
    manifest = _qualification_manifest()
    mutation(manifest)
    with pytest.raises(ValueError, match="provenance commit|protected input"):
        temper_quality_oracle.evaluate_isolation_qualification_json(json.dumps(manifest))


class TestQualityOraclePipeline:
    def test_empty_board_passes(self):
        require_oracle()
        netlist = {"nets": [], "components": []}
        placement = {
            "positions": [],
            "component_refs": [],
            "board_width_mm": 100.0,
            "board_height_mm": 100.0,
        }
        spec = {"name": "test"}
        metrics = {
            "thermal_score": 0.5,
            "zone_compliance_score": 0.5,
            "hv_lv_clearance_score": 0.5,
            "loop_area_score": 0.5,
            "congestion_score": 0.5,
            "compactness_score": 0.5,
            "connectivity_clustering_score": 0.5,
            "total_wirelength_mm": 100.0,
        }
        result = evaluate_quality(netlist, placement, spec, metrics)
        assert result["verdict"] == "Pass"
        assert "metrics" in result
        assert abs(result["metrics"]["overall_score"] - 0.5) < 1e-6

    def test_hv_lv_violation_detected(self):
        require_oracle()
        netlist = {
            "nets": [{"name": "SIG1", "pins": ["Q1", "U1"]}],
            "components": [
                {
                    "ref": "Q1",
                    "footprint": "TO-247",
                    "width": 15.0,
                    "height": 20.0,
                    "voltage": 230.0,
                },
                {"ref": "U1", "footprint": "SOIC-8", "width": 5.0, "height": 4.0, "voltage": 3.3},
            ],
        }
        placement = {
            "positions": [5.0, 5.0, 6.0, 5.0],
            "component_refs": ["Q1", "U1"],
            "board_width_mm": 100.0,
            "board_height_mm": 100.0,
        }
        spec = {"name": "test"}
        metrics = {
            "thermal_score": 0.5,
            "zone_compliance_score": 0.5,
            "hv_lv_clearance_score": 0.5,
            "loop_area_score": 0.5,
            "congestion_score": 0.5,
            "compactness_score": 0.5,
            "connectivity_clustering_score": 0.5,
            "total_wirelength_mm": 100.0,
        }
        result = evaluate_quality(netlist, placement, spec, metrics)
        assert result["verdict"] == "Fail"
        assert "violations" in result
        violations = result["violations"]
        assert len(violations) > 0
        assert any(v["type"] == "creepage_insufficient" for v in violations)

    def test_invalid_score_rejected(self):
        require_oracle()
        netlist = {"nets": [], "components": []}
        placement = {
            "positions": [],
            "component_refs": [],
            "board_width_mm": 100.0,
            "board_height_mm": 100.0,
        }
        spec = {"name": "test"}
        metrics = {
            "thermal_score": 1.5,
            "zone_compliance_score": 0.5,
            "hv_lv_clearance_score": 0.5,
            "loop_area_score": 0.5,
            "congestion_score": 0.5,
            "compactness_score": 0.5,
            "connectivity_clustering_score": 0.5,
            "total_wirelength_mm": 100.0,
        }
        result = evaluate_quality(netlist, placement, spec, metrics)
        assert result["verdict"] == "Fail"
        assert "violations" in result

    def test_deterministic(self):
        require_oracle()
        netlist = {"nets": [], "components": []}
        placement = {
            "positions": [],
            "component_refs": [],
            "board_width_mm": 100.0,
            "board_height_mm": 100.0,
        }
        spec = {"name": "test"}
        metrics = {
            "thermal_score": 0.5,
            "zone_compliance_score": 0.5,
            "hv_lv_clearance_score": 0.5,
            "loop_area_score": 0.5,
            "congestion_score": 0.5,
            "compactness_score": 0.5,
            "connectivity_clustering_score": 0.5,
            "total_wirelength_mm": 100.0,
        }
        r1 = evaluate_quality(netlist, placement, spec, metrics)
        r2 = evaluate_quality(netlist, placement, spec, metrics)
        assert r1["verdict"] == r2["verdict"]


class TestPrepareEvaluateSplit:
    """The setup/evaluate precompute split (R-x: prepare once, score many)."""

    def _hv_lv_inputs(self):
        netlist = {
            "nets": [{"name": "GATE_DRV_H", "pins": ["Q1", "U1"]}],
            "components": [
                {
                    "ref": "Q1",
                    "footprint": "TO-247",
                    "width": 15.0,
                    "height": 20.0,
                    "voltage": 230.0,
                },
                {"ref": "U1", "footprint": "SOIC-8", "width": 5.0, "height": 4.0, "voltage": 3.3},
            ],
        }
        spec = {"name": "test"}
        metrics = {
            "thermal_score": 0.5,
            "zone_compliance_score": 0.5,
            "hv_lv_clearance_score": 0.5,
            "loop_area_score": 0.5,
            "congestion_score": 0.5,
            "compactness_score": 0.5,
            "connectivity_clustering_score": 0.5,
            "total_wirelength_mm": 100.0,
        }
        return netlist, spec, metrics

    def test_prepared_round_trips(self):
        require_oracle()
        netlist, spec, _ = self._hv_lv_inputs()
        prepared = temper_quality_oracle.prepare_quality_py(netlist, spec)
        assert set(prepared.keys()) == {"spec", "config", "classifications"}
        config = prepared["config"]
        assert set(config.keys()) == {
            "thermal_components",
            "hv_components",
            "lv_components",
            "zone_assignments",
            "loop_components",
            "min_hv_lv_clearance_mm",
        }
        assert "Q1" in config["hv_components"]
        assert "U1" in config["lv_components"]
        assert prepared["classifications"] == [
            {"net_name": "GATE_DRV_H", "class": "gate_drive"}
        ]

    def test_evaluate_prepared_matches_evaluate_quality(self):
        require_oracle()
        netlist, spec, metrics = self._hv_lv_inputs()
        placement = {
            "positions": [5.0, 5.0, 6.0, 5.0],
            "component_refs": ["Q1", "U1"],
            "board_width_mm": 100.0,
            "board_height_mm": 100.0,
        }
        single = evaluate_quality(netlist, placement, spec, metrics)
        prepared = temper_quality_oracle.prepare_quality_py(netlist, spec)
        split = temper_quality_oracle.evaluate_prepared_py(prepared, placement, metrics)
        assert split == single
        assert split["verdict"] == "Fail"
        assert any(v["type"] == "creepage_insufficient" for v in split["violations"])

    def test_prepare_once_score_many_placements(self):
        require_oracle()
        netlist, spec, metrics = self._hv_lv_inputs()
        prepared = temper_quality_oracle.prepare_quality_py(netlist, spec)

        close = {
            "positions": [5.0, 5.0, 6.0, 5.0],
            "component_refs": ["Q1", "U1"],
            "board_width_mm": 100.0,
            "board_height_mm": 100.0,
        }
        far = {
            "positions": [5.0, 5.0, 80.0, 80.0],
            "component_refs": ["Q1", "U1"],
            "board_width_mm": 100.0,
            "board_height_mm": 100.0,
        }
        r_close = temper_quality_oracle.evaluate_prepared_py(prepared, close, metrics)
        r_far = temper_quality_oracle.evaluate_prepared_py(prepared, far, metrics)
        assert r_close["verdict"] == "Fail"
        assert r_far["verdict"] == "Pass"
        # The same prepared dict is reusable across placement states.
        r_close_again = temper_quality_oracle.evaluate_prepared_py(prepared, close, metrics)
        assert r_close_again == r_close

    def test_evaluate_prepared_rejects_bad_metrics(self):
        require_oracle()
        netlist, spec, metrics = self._hv_lv_inputs()
        prepared = temper_quality_oracle.prepare_quality_py(netlist, spec)
        placement = {
            "positions": [5.0, 5.0, 80.0, 80.0],
            "component_refs": ["Q1", "U1"],
            "board_width_mm": 100.0,
            "board_height_mm": 100.0,
        }
        bad_metrics = dict(metrics)
        bad_metrics["thermal_score"] = 1.5
        result = temper_quality_oracle.evaluate_prepared_py(prepared, placement, bad_metrics)
        assert result["verdict"] == "Fail"
        assert any(v["type"] == "invalid_metric" for v in result["violations"])

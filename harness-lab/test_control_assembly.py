"""P3 U3 tests: control-assembly routing and verification (plan scenarios 1-7).

These exercise the verification apparatus against the committed
apparatus-only artifacts plus controlled synthetic failures, so the checks
are proven to *detect* the conditions the plan names — an open return, a
cross-domain short, an antenna-keepout intrusion, a narrowed power path, a
new finding hidden by an unchanged aggregate, a surviving placeholder, and a
one-view change.

They do not re-run KiCad; the native reports are committed under
``pcb/blocks/control-assembly/verification/apparatus-only/``. Run with::

    .venv/bin/python -m pytest harness-lab/test_control_assembly.py -q
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

import compose_blocks  # noqa: E402
import run_control_assembly as u3  # noqa: E402

VERIFY = REPO / "pcb" / "blocks" / "control-assembly" / "verification" / "apparatus-only"
SUMMARY = VERIFY / "summary.json"
CONNECTIVITY = VERIFY / "routed-connectivity.json"
CROSS_VIEW = VERIFY / "cross-view-report.json"


class Scenario1PhysicalConnectivity(unittest.TestCase):
    """Both blocks and the inter-block supply/return share correct source nets."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        cls.connectivity = json.loads(CONNECTIVITY.read_text(encoding="utf-8"))

    def test_required_nets_are_single_native_clusters(self) -> None:
        result = u3.check_required_connectivity(self.connectivity)
        self.assertEqual(result["status"], "pass", result)

    def test_inter_block_endpoints_share_a_cluster(self) -> None:
        result = u3.check_inter_block(self.connectivity)
        self.assertEqual(result["status"], "pass", result)
        # U2 VCC3V3 and GND must sit on the buck supply/return clusters.
        plus3 = self.connectivity["nets"]["buck-vcc-1"]["clusters"]
        gnd = self.connectivity["nets"]["gnd"]["clusters"]
        self.assertTrue(any("U2.2" in c for c in plus3))
        self.assertTrue(any("U2.1" in c for c in gnd))

    def test_both_blocks_present_in_assembly(self) -> None:
        source_map = json.loads(
            (REPO / "pcb/blocks/control-assembly/assembly-candidate/source-map.json")
            .read_text(encoding="utf-8")
        )
        blocks = {entry["block"] for entry in source_map["entries"].values()}
        self.assertEqual(blocks, {"buck", "mcu"})


class Scenario2FailureDetection(unittest.TestCase):
    """Named failure conditions are detected, not accepted."""

    def test_open_inter_block_return_fails(self) -> None:
        connectivity = {
            "nets": {
                "gnd": {"clusters": [["U2.1"], ["U1.1"]], "cluster_count": 2, "pad_count": 2},
                "buck-vcc-1": {"clusters": [["U2.2", "L1.2"]], "cluster_count": 1, "pad_count": 2},
                "buck-vcc": {"clusters": [["U1.3"]], "cluster_count": 1, "pad_count": 1},
                "sw": {"clusters": [["U1.2"]], "cluster_count": 1, "pad_count": 1},
                "fb": {"clusters": [["U1.4"]], "cluster_count": 1, "pad_count": 1},
                "boot": {"clusters": [["U1.6"]], "cluster_count": 1, "pad_count": 1},
            }
        }
        self.assertEqual(u3.check_required_connectivity(connectivity)["status"], "fail")
        self.assertEqual(u3.check_inter_block(connectivity)["status"], "fail")

    def test_cross_domain_short_detected_in_finding_set(self) -> None:
        report = {
            "violations": [
                {
                    "type": "shorting_items",
                    "severity": "error",
                    "items": [
                        {"description": "Pad 1 [gnd] of C7 on F.Cu"},
                        {"description": "Track [buck-vcc] on F.Cu"},
                    ],
                }
            ],
            "unconnected_items": [],
            "schematic_parity": [],
        }
        findings = u3.drc_finding_set(report)
        self.assertEqual(len(findings), 1)
        self.assertIn("shorting_items", next(iter(findings)))

    def test_antenna_keepout_intrusion_fails(self) -> None:
        keepout = {"x1": 18.0, "y1": 20.0, "x2": 52.0, "y2": 32.0}
        clean = {"tracks": []}
        self.assertEqual(u3.check_keepout(clean, keepout)["status"], "pass")
        intruding = {
            "tracks": [
                {
                    "uuid": "t",
                    "kind": "segment",
                    "net": "+3V3",
                    "start_mm": [30.0, 25.0],
                    "end_mm": [30.0, 40.0],
                }
            ]
        }
        result = u3.check_keepout(intruding, keepout)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(len(result["intrusions"]), 1)

    def test_narrowed_power_path_fails(self) -> None:
        wide = {"tracks": [{"uuid": "w", "kind": "segment", "net": "gnd", "width_mm": 0.8}]}
        narrow = {"tracks": [{"uuid": "n", "kind": "segment", "net": "gnd", "width_mm": 0.2}]}
        self.assertEqual(u3.check_power_width(wide, ["gnd"])["status"], "pass")
        self.assertEqual(u3.check_power_width(narrow, ["gnd"])["status"], "fail")


class Scenario3RefillCannotFakeConnectivity(unittest.TestCase):
    """Connectivity is native measurement, never an estimate from a render."""

    def test_committed_refill_completed(self) -> None:
        summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        self.assertEqual(summary["refill"]["returncode"], 0)

    def test_multi_cluster_net_fails_even_if_it_looks_connected(self) -> None:
        # A filled zone that splits into islands can look continuous and be
        # electrically open; the native cluster count is the verdict.
        connectivity = json.loads(CONNECTIVITY.read_text(encoding="utf-8"))
        native_gnd = connectivity["nets"]["gnd"]
        self.assertEqual(native_gnd["cluster_count"], 1)
        broken = {
            "nets": {
                "gnd": {"clusters": native_gnd["clusters"] + [["U2.1"]],
                        "cluster_count": 2, "pad_count": native_gnd["pad_count"] + 1,
                        "pads": native_gnd["pads"] + ["U2.1"]},
                "buck-vcc-1": connectivity["nets"]["buck-vcc-1"],
                "buck-vcc": connectivity["nets"]["buck-vcc"],
                "sw": connectivity["nets"]["sw"],
                "fb": connectivity["nets"]["fb"],
                "boot": connectivity["nets"]["boot"],
            }
        }
        self.assertEqual(u3.check_required_connectivity(broken)["status"], "fail")


class Scenario4SetDeltaNotCount(unittest.TestCase):
    """A new violation is caught even when the aggregate count is unchanged."""

    def test_new_violation_with_equal_counts(self) -> None:
        baseline = {"a", "b"}
        candidate = {"a", "c"}
        delta = u3.finding_set_delta(baseline, candidate)
        self.assertEqual(len(baseline), len(candidate))
        self.assertEqual(delta["introduced"], ["c"])
        self.assertEqual(delta["resolved"], ["b"])
        self.assertEqual(delta["introduced_count"], 1)

    def test_no_introduced_findings_in_committed_pass(self) -> None:
        summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        self.assertEqual(summary["drc"]["delta"]["introduced_count"], 0)
        self.assertEqual(summary["erc"]["delta"]["introduced_count"], 0)


class Scenario5ProductionUnchanged(unittest.TestCase):
    """Unchanged outside-region geometry and the production digest is exact."""

    def test_production_digest_matches_frozen_context(self) -> None:
        result = u3.production_digest_exact()
        self.assertEqual(result["status"], "pass", result)

    def test_production_digest_matches_target_context(self) -> None:
        context = json.loads(
            (REPO / "pcb/blocks/control-assembly/target-context.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertNotEqual(u3.production_digest_exact()["actual_sha256"], "")
        self.assertEqual(
            u3.production_digest_exact()["expected_sha256"],
            context["provenance"]["pcb/temper.kicad_pcb"],
        )


class Scenario6NoLeftoverOrOrphan(unittest.TestCase):
    """Replacement leaves no old instance and no orphan copper behind."""

    def test_no_placeholder_leftover(self) -> None:
        extract = u3.native_extract(
            VERIFY / "control-assembly-routed.kicad_pcb"
        )
        ledger = json.loads(
            (REPO / "pcb/blocks/control-assembly/assembly-candidate/replacement-ledger.json")
            .read_text(encoding="utf-8")
        )
        result = u3.check_no_mcu_buck_placeholder(extract, ledger)
        self.assertEqual(result["status"], "pass", result)

    def test_placeholder_leftover_is_detected(self) -> None:
        extract = {
            "footprints": [{"reference": "U27"}, {"reference": "U1"}],
            "tracks": [],
        }
        ledger = {"removals": [{"ref": "U27"}]}
        self.assertEqual(
            u3.check_no_mcu_buck_placeholder(extract, ledger)["status"], "fail"
        )


class Scenario7CrossViewComparison(unittest.TestCase):
    """A change in only one candidate view fails the comparison."""

    def _extract(self, **overrides) -> dict:
        base = {
            "pads": {"U2.2": {"net": "buck-vcc-1", "x_mm": 26.0, "y_mm": 58.89}},
            "tracks": [{"uuid": "t", "net": "buck-vcc-1"}],
            "vias": [{"uuid": "v", "span": "F.Cu-B.Cu"}],
            "zones": [],
            "endpoints": {"BUCK_3V3_TO_MCU": {"net": "buck-vcc-1"}},
        }
        base.update(overrides)
        return base

    def test_identical_views_agree(self) -> None:
        self.assertEqual(
            compose_blocks.compare_views(self._extract(), self._extract()), []
        )

    def test_one_view_track_change_fails(self) -> None:
        other = self._extract()
        other["tracks"] = [{"uuid": "t", "net": "gnd"}]
        mismatches = compose_blocks.compare_views(self._extract(), other)
        self.assertTrue(any(m["category"] == "tracks" for m in mismatches))

    def test_one_view_via_change_fails(self) -> None:
        other = self._extract()
        other["vias"] = [{"uuid": "v", "span": "In1.Cu-B.Cu"}]
        mismatches = compose_blocks.compare_views(self._extract(), other)
        self.assertTrue(any(m["category"] == "vias" for m in mismatches))

    def test_one_view_zone_change_fails(self) -> None:
        view = self._extract(zones=[{"uuid": "z", "net": "gnd", "layer": "F.Cu"}])
        other = self._extract(zones=[{"uuid": "z", "net": "gnd", "layer": "B.Cu"}])
        mismatches = compose_blocks.compare_views(view, other)
        self.assertTrue(any(m["category"] == "zones" for m in mismatches))

    def test_one_view_pad_change_fails(self) -> None:
        other = self._extract()
        other["pads"] = {"U2.2": {"net": "buck-vcc-1", "x_mm": 26.5, "y_mm": 58.89}}
        mismatches = compose_blocks.compare_views(self._extract(), other)
        self.assertTrue(any(m["category"] == "pads" for m in mismatches))

    def test_one_view_endpoint_change_fails(self) -> None:
        other = self._extract()
        other["endpoints"] = {"BUCK_3V3_TO_MCU": {"net": "gnd"}}
        mismatches = compose_blocks.compare_views(self._extract(), other)
        self.assertTrue(any(m["category"] == "endpoints" for m in mismatches))

    def test_committed_overlay_cross_view_passes(self) -> None:
        report = json.loads(CROSS_VIEW.read_text(encoding="utf-8"))
        self.assertIsNotNone(report["overlay_view"], report)
        self.assertEqual(report["status"], "pass", report)
        self.assertEqual(report["mismatch_count"], 0, report)
        self.assertEqual(
            set(report["categories"]), set(compose_blocks.COMPARE_CATEGORIES)
        )
        self.assertIn("rebind_required_after", report)


class Scenario5OverlayScratchBoard(unittest.TestCase):
    """The scratch overlay is the copied production board plus the section."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        cls.report = json.loads(CROSS_VIEW.read_text(encoding="utf-8"))
        cls.overlay = cls.summary["overlay"]

    def test_production_board_digest_stays_exact(self) -> None:
        self.assertEqual(self.overlay["production_digest_after_overlay"]["status"], "pass")
        self.assertEqual(self.summary["checks"]["production_digest"]["status"], "pass")

    def test_untouched_outside_region_geometry_is_exact(self) -> None:
        invariance = self.overlay["outside_region_invariance"]
        self.assertEqual(invariance["status"], "pass", invariance)
        self.assertEqual(invariance["problem_count"], 0, invariance)
        # Track geometry outside the replaced placeholders is unchanged; any
        # net re-propagation is recorded rather than silently absorbed.
        self.assertIn("net_reassigned", invariance)

    def test_overlay_is_bound_in_the_manifest(self) -> None:
        binding = json.loads(
            (VERIFY / "candidate-binding.json").read_text(encoding="utf-8")
        )
        overlay_path = REPO / binding["overlay_board"]["path"]
        self.assertTrue(overlay_path.is_file())
        self.assertEqual(
            u3._sha256(overlay_path), binding["overlay_board"]["sha256"]
        )
        report_path = REPO / binding["cross_view_report"]["path"]
        self.assertEqual(
            u3._sha256(report_path), binding["cross_view_report"]["sha256"]
        )

    def test_overlay_finding_delta_is_set_based(self) -> None:
        delta = self.overlay["finding_delta"]
        self.assertEqual(delta["introduced_count"], len(delta["introduced"]))
        self.assertEqual(delta["resolved_count"], len(delta["resolved"]))
        self.assertEqual(delta["persistent_count"], len(delta["persistent"]))
        # Both views must be sampled the same way; kicad-cli is nondeterministic.
        stability = self.overlay["stability"]
        self.assertEqual(stability["baseline"]["samples"], stability["routed"]["samples"])
        self.assertGreaterEqual(stability["baseline"]["union"], stability["baseline"]["intersection"])

    def test_overlay_reveals_section_integration_debt(self) -> None:
        """The overlay is an honest instrument: the current section is NOT
        overlay-clean (its board-wide gnd pour shorts against production
        copper). The report keeps that debt visible rather than suppressing it."""
        delta = self.overlay["finding_delta"]
        self.assertGreater(delta["introduced_count"], 0, self.overlay)
        self.assertTrue(
            any("shorting_items" in item for item in delta["introduced"]),
            "expected shorting_items from the section's board-wide gnd pour",
        )


class PowerWidthClassification(unittest.TestCase):
    """The power-width floor is unchanged; the net classification is explicit."""

    def test_committed_power_width_passes_for_power_nets(self) -> None:
        summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        result = summary["checks"]["power_width"]
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result["narrow"], [], result)
        self.assertEqual(
            set(result["power_nets"]), set(u3.run_block.ASSEMBLY_POWER_NETS)
        )

    def test_inherited_signal_copper_is_attributed_not_hidden(self) -> None:
        summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        inherited = summary["checks"]["power_width"]["inherited_below_power_floor"]
        self.assertTrue(inherited, "inherited prototype debt must stay visible")
        self.assertTrue(all(item["net"] in ("fb", "boot") for item in inherited))
        self.assertTrue(all(item["width_mm"] == 0.3 for item in inherited))

    def test_narrow_power_segment_still_fails(self) -> None:
        narrow = {
            "tracks": [{"uuid": "n", "kind": "segment", "net": "buck-vcc-1",
                        "width_mm": 0.3}]
        }
        result = u3.check_power_width(narrow, ["buck-vcc-1"], ("fb",))
        self.assertEqual(result["status"], "fail", result)

    def test_signal_below_power_floor_is_recorded_not_failed(self) -> None:
        signal = {
            "tracks": [{"uuid": "s", "kind": "segment", "net": "fb",
                        "width_mm": 0.3}]
        }
        result = u3.check_power_width(signal, ["buck-vcc-1"], ("fb",))
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(len(result["inherited_below_power_floor"]), 1)


class BlockSessionAdmission(unittest.TestCase):
    """All PCB mutations used the shared bounded native operation."""

    def test_summary_records_the_block_session(self) -> None:
        summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        session = summary["session"]
        self.assertEqual(session["runner"], "run_block.BlockSession")
        self.assertEqual(session["contract_kind"], "assembly")
        self.assertGreaterEqual(session["actions"], 1)
        self.assertEqual(
            summary["routing"]["bounded_operation"].split(" dispatched")[0],
            "replace_copper",
        )
        self.assertIn("BlockSession", summary["routing"]["bounded_operation"])


class ApparatusOnlyLabelling(unittest.TestCase):
    """The pass must not be mistaken for an autonomous or qualified result."""

    def test_summary_is_labelled_apparatus_only(self) -> None:
        summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "apparatus-only-assisted")
        self.assertFalse(summary["live_model"])
        self.assertIn("429", summary["live_model_blocker"])


if __name__ == "__main__":
    unittest.main()

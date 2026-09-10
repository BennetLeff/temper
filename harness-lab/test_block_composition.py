"""P3 U2 preparation tests: source-derived block composition without the MCU.

Covers plan U2 test scenarios that do not need P1 U4's accepted MCU:
combined source mapping (functional buck nine + prototype exclusion),
refdes/net-code change preservation, asymmetric native transforms, via
span, and unsupported-layer/orphan-stub/outside-region rejection.

Needs only the repo checkout plus the built ``temper_geometry`` and
``temper-design-bundle`` extensions; no board writes, no P1/P2 staging.
Run with::

    .venv/bin/python -m pytest harness-lab/test_block_composition.py -q
"""

from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

import compose_blocks  # noqa: E402
from compose_blocks import CompositionError  # noqa: E402

TARGET_CONTEXT = REPO / "pcb" / "blocks" / "control-assembly" / "target-context.json"
MCU_CONTRACT = REPO / "pcb" / "blocks" / "control-assembly" / "mcu-input-contract.json"


def buck_bridge() -> list:
    """Synthetic P1-style bridge entries for the functional buck nine."""
    return [
        {"reference": ref, "instance_path": f"buck.{ref.lower()}", "footprint": "fp:Part"}
        for ref in compose_blocks.BUCK_FUNCTIONAL_REFS
    ]


def mcu_bridge() -> list:
    """Synthetic P1-style bridge entries for the functional MCU ten."""
    return [
        {"reference": ref, "instance_path": f"mcu.{ref.lower()}", "footprint": "fp:Part"}
        for ref in compose_blocks.MCU_FUNCTIONAL_REFS
    ]


class CombinedSourceMapping(unittest.TestCase):
    def test_functional_buck_nine_map_by_source_path(self) -> None:
        mapping = compose_blocks.build_source_map(buck_bridge())
        self.assertEqual(len(mapping), 9)
        for comp in buck_bridge():
            self.assertEqual(mapping[comp["instance_path"]]["reference"], comp["reference"])
            self.assertEqual(mapping[comp["instance_path"]]["block"], "buck")

    def test_prototype_only_objects_are_excluded(self) -> None:
        for ref in ("J1", "J2", "TP1", "TP4", "H1", "H4"):
            with self.assertRaises(CompositionError) as ctx:
                compose_blocks.build_source_map(
                    buck_bridge()
                    + [{"reference": ref, "instance_path": f"buck.{ref.lower()}", "footprint": "fp:X"}]
                )
            self.assertIn("prototype-only", str(ctx.exception))

    def test_mcu_side_staged_behind_require_flag(self) -> None:
        # Pre-U4: buck-only map succeeds without the MCU.
        mapping = compose_blocks.build_source_map(buck_bridge(), require_mcu=False)
        self.assertTrue(all(v["block"] == "buck" for v in mapping.values()))
        # Post-U4 shape: combined map with require_mcu=True admits both blocks.
        combined = compose_blocks.build_source_map(
            buck_bridge() + mcu_bridge(), require_mcu=True
        )
        self.assertEqual(len(combined), 19)
        # An MCU-claiming map that drops instances fails, even pre-U4.
        with self.assertRaises(CompositionError):
            compose_blocks.build_source_map(
                buck_bridge() + mcu_bridge()[:4], require_mcu=True
            )

    def test_duplicate_and_missing_instances_fail(self) -> None:
        entries = buck_bridge()
        with self.assertRaises(CompositionError) as ctx:
            compose_blocks.build_source_map(entries + [entries[0]])
        self.assertIn("duplicate instance path", str(ctx.exception))
        with self.assertRaises(CompositionError) as ctx:
            compose_blocks.build_source_map(entries[1:])
        self.assertIn("missing", str(ctx.exception))

    def test_foreign_namespace_rejected(self) -> None:
        entries = buck_bridge()
        entries[0] = dict(entries[0], instance_path="elsewhere.u3")
        with self.assertRaises(CompositionError) as ctx:
            compose_blocks.build_source_map(entries)
        self.assertIn("neither block namespace", str(ctx.exception))


class RefdesNetcodePreservation(unittest.TestCase):
    def _pin_entries(self, refs: tuple, nets: dict) -> tuple:
        entries = [
            {
                "instance_path": f"buck.{ref.lower()}",
                "reference": ref,
                "pin": pin,
                "pad": pin,
                "alias_note": "",
                "positional": False,
            }
            for ref, pins in refs
            for pin in pins
        ]
        pads = {ref: list(pins) for ref, pins in refs}
        pins = {ref: list(pins) for ref, pins in refs}
        return entries, pads, pins

    def test_refdes_and_netcode_changes_preserve_connections(self) -> None:
        # Canonical connection is (instance_path, pin) -> net. A refdes
        # renumber (C9 -> C109) keeps the same instance-path key: the map
        # is keyed by source path, and the caller updates the expected
        # refdes census explicitly (a renumber that silently passes the
        # old census would be a stale-identity defect).
        rest = [
            {"reference": r, "instance_path": f"buck.{r.lower()}", "footprint": "fp:P"}
            for r in compose_blocks.BUCK_FUNCTIONAL_REFS
            if r != "C9"
        ]
        mapping_before = compose_blocks.build_source_map(
            [{"reference": "C9", "instance_path": "buck.c_in", "footprint": "fp:C"}, *rest]
        )
        after_refs = tuple(
            "C109" if r == "C9" else r for r in compose_blocks.BUCK_FUNCTIONAL_REFS
        )
        mapping_after = compose_blocks.build_source_map(
            [{"reference": "C109", "instance_path": "buck.c_in", "footprint": "fp:C"}, *rest],
            expected_buck_refs=after_refs,
        )
        self.assertIn("buck.c_in", mapping_before)
        self.assertIn("buck.c_in", mapping_after)
        self.assertEqual(mapping_before["buck.c_in"]["footprint"], "fp:C")
        self.assertEqual(mapping_after["buck.c_in"]["reference"], "C109")
        # The old census no longer admits the renumbered board: stale
        # identities fail instead of passing silently.
        with self.assertRaises(CompositionError):
            compose_blocks.build_source_map(
                [{"reference": "C109", "instance_path": "buck.c_in", "footprint": "fp:C"},
                 *rest]
            )

    def test_rust_gate_rejects_duplicate_missing_and_positional(self) -> None:
        base = {
            "instance_path": "buck.u3",
            "reference": "U3",
            "pin": "1",
            "pad": "1",
            "alias_note": "",
            "positional": False,
        }
        pads = {"U3": ["1"]}
        pins = {"U3": ["1"]}
        with self.assertRaises(ValueError) as ctx:
            compose_blocks.validate_pin_map_native([base, dict(base)], pads, pins, [])
        self.assertIn("duplicate_map", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            compose_blocks.validate_pin_map_native([], pads, pins, [])
        self.assertIn("missing_map", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            compose_blocks.validate_pin_map_native(
                [dict(base, positional=True)], pads, pins, []
            )
        self.assertIn("positional_fallback", str(ctx.exception))

    def test_rust_gate_rejects_empty_net_admission(self) -> None:
        nets = [
            {"name": "vcc", "nodes": [["U3", "3"]]},
            {"name": "buck-reference", "nodes": []},
        ]
        with self.assertRaises(ValueError) as ctx:
            compose_blocks.validate_net_admission(nets, ["vcc", "buck-reference"])
        self.assertIn("empty_net_admitted", str(ctx.exception))


class NativeTransformContract(unittest.TestCase):
    def test_asymmetric_probe_matches_kicad(self) -> None:
        # pcbnew ground truth (AGENTS.md): dx != dy at 45deg discriminates
        # R(-theta) from the standard-math R(+theta); a 90deg probe alone
        # cannot. 45deg is exact in neither float system: compare to 1nm.
        x, y = compose_blocks.rotate_local_to_world(10.0, 4.0, math.radians(45.0))
        self.assertAlmostEqual(x, 9.899495, places=5)
        self.assertAlmostEqual(y, -4.242641, places=5)

    def test_axis_probe_matches_kicad(self) -> None:
        x, y = compose_blocks.rotate_local_to_world(15.0, 0.0, math.radians(90.0))
        self.assertAlmostEqual(x, 0.0, places=9)
        self.assertAlmostEqual(y, -15.0, places=9)

    def test_placement_is_rotate_then_translate(self) -> None:
        x, y = compose_blocks.place_local_to_world(
            10.0, 4.0, 100.0, 100.0, math.radians(45.0)
        )
        self.assertAlmostEqual(x, 109.899495, places=5)
        self.assertAlmostEqual(y, 95.757359, places=5)

    def test_no_local_trig_policy(self) -> None:
        text = (ROOT / "compose_blocks.py").read_text(encoding="utf-8")
        for token in ("math.cos", "math.sin", "np.cos", "np.sin"):
            self.assertNotIn(token, text)


class ViaAndLayerContract(unittest.TestCase):
    def test_proto_outer_pair_maps_to_target(self) -> None:
        order = ["F.Cu", "In3.Cu", "In1.Cu", "In2.Cu", "In4.Cu", "B.Cu"]
        self.assertEqual(compose_blocks.map_proto_layer("F.Cu", order), "F.Cu")
        self.assertEqual(compose_blocks.map_proto_layer("B.Cu", order), "B.Cu")

    def test_unsupported_layer_rejected_not_dropped(self) -> None:
        order = ["F.Cu", "In3.Cu", "In1.Cu", "In2.Cu", "In4.Cu", "B.Cu"]
        for layer in ("In1.Cu", "GND", "Edge.Cuts"):
            with self.assertRaises(CompositionError):
                compose_blocks.map_proto_layer(layer, order)

    def test_through_via_span_and_dims(self) -> None:
        via = compose_blocks.recreate_through_via([10.0, 20.0], 0.8, 0.4)
        self.assertEqual(via["span"], "F.Cu-B.Cu")
        with self.assertRaises(CompositionError):
            compose_blocks.recreate_through_via([10.0, 20.0], 0.5, 0.4)
        with self.assertRaises(CompositionError):
            compose_blocks.recreate_through_via([10.0, 20.0], 0.8, 0.3)


class LedgerAndRegionGuard(unittest.TestCase):
    def test_ledger_verifies_existence_and_retains_identities(self) -> None:
        baseline = {
            "U3": {"tstamp": "t-u3", "footprint": "SOT-23-6"},
            "L2": {"tstamp": "t-l2", "footprint": "SRP1265A"},
            "U27": {"tstamp": "t-u27", "footprint": "WROOM-1"},
        }
        records = compose_blocks.apply_replacement_ledger(
            baseline,
            [
                {"ref": "U3", "reason": "buck IC placeholder replaced"},
                {"ref": "U27", "reason": "MCU placeholder replaced"},
            ],
        )
        self.assertEqual([r["ref"] for r in records], ["U3", "U27"])
        self.assertEqual(records[0]["before"]["tstamp"], "t-u3")
        self.assertIsNone(records[0]["after"])

    def test_ledger_rejects_unknown_and_duplicate(self) -> None:
        with self.assertRaises(CompositionError):
            compose_blocks.apply_replacement_ledger({}, [{"ref": "U3"}])
        with self.assertRaises(CompositionError):
            compose_blocks.apply_replacement_ledger(
                {"U3": {"tstamp": "t"}}, [{"ref": "U3"}, {"ref": "U3"}]
            )

    def test_owned_region_guard(self) -> None:
        envelopes = [
            {"ref": "U3", "x1": 112.93, "y1": 144.08, "x2": 122.93, "y2": 154.08}
        ]
        hit = compose_blocks.check_owned_region(117.93, 149.08, envelopes, ref="U3")
        self.assertEqual(hit["ref"], "U3")
        with self.assertRaises(CompositionError) as ctx:
            compose_blocks.check_owned_region(10.0, 10.0, envelopes, ref="U3")
        self.assertIn("outside every owned envelope", str(ctx.exception))

    def test_orphan_fixture_stubs_rejected(self) -> None:
        tracks = [
            {"uuid": "t-keep", "pads": ["U3.3", "C9.1"]},
            {"uuid": "t-stub", "pads": ["J1.1", "J1.2"]},
        ]
        owners = {
            "U3.3": "U3",
            "C9.1": "C9",
            "J1.1": "J1",
            "J1.2": "J1",
        }
        kept, removed = compose_blocks.strip_orphan_stubs(tracks, {"J1"}, owners)
        self.assertEqual([t["uuid"] for t in kept], ["t-keep"])
        self.assertEqual([t["uuid"] for t in removed], ["t-stub"])
        with self.assertRaises(CompositionError):
            compose_blocks.strip_orphan_stubs(
                [{"uuid": "t-x", "pads": ["J1.1", "U3.3"]}], {"J1"}, owners
            )
        with self.assertRaises(CompositionError):
            compose_blocks.strip_orphan_stubs([{"uuid": "t-o", "pads": []}], {"J1"}, owners)


class CrossViewScaffolding(unittest.TestCase):
    def _extract(self, **overrides) -> dict:
        base = {
            "pads": {"U3.3": {"net": "+15V", "x_mm": 1.0, "y_mm": 2.0}},
            "tracks": [{"uuid": "a", "net": "+15V"}],
            "vias": [{"uuid": "v", "span": "F.Cu-B.Cu"}],
            "zones": [],
            "endpoints": {"BUCK_3V3_TO_MCU": {"net": "+3V3"}},
        }
        base.update(overrides)
        return base

    def test_identical_views_agree(self) -> None:
        self.assertEqual(
            compose_blocks.compare_views(self._extract(), self._extract()), []
        )

    def test_single_view_change_fails(self) -> None:
        other = self._extract()
        other["pads"] = {"U3.3": {"net": "+15V", "x_mm": 1.5, "y_mm": 2.0}}
        mismatches = compose_blocks.compare_views(self._extract(), other)
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0]["category"], "pads")


class U2AssemblyPackage(unittest.TestCase):
    """Plan U2 scenarios 1-4 against the committed combined assembly package."""

    PACKAGE = REPO / "pcb" / "blocks" / "control-assembly" / "assembly-candidate"

    @classmethod
    def setUpClass(cls) -> None:
        cls.source_map = json.loads(
            (cls.PACKAGE / "source-map.json").read_text(encoding="utf-8")
        )
        cls.entries = cls.source_map["entries"]

    def test_scenario1_functional_census_and_no_fixtures(self) -> None:
        expected = set(compose_blocks.BUCK_FUNCTIONAL_PATHS) | set(
            compose_blocks.MCU_FUNCTIONAL_PATHS
        )
        self.assertEqual(set(self.entries), expected)
        self.assertEqual(len(self.entries), 19)
        refs = {entry["reference"] for entry in self.entries.values()}
        self.assertFalse(refs & set(compose_blocks.PROTOTYPE_ONLY_REFS))
        # Both blocks are present and namespaced by source path.
        self.assertEqual(
            {self.entries[p]["block"] for p in compose_blocks.BUCK_FUNCTIONAL_PATHS},
            {"buck"},
        )
        self.assertEqual(
            {self.entries[p]["block"] for p in compose_blocks.MCU_FUNCTIONAL_PATHS},
            {"mcu"},
        )

    def test_scenario2_refdes_renumber_preserves_path_identity(self) -> None:
        # The combined build renumbers refdes: prototype U3/C9 -> combined
        # U1/C1, standalone MCU U1 -> combined U2. Identity is the path.
        self.assertEqual(self.entries["buck.buck"]["reference"], "U1")
        self.assertEqual(self.entries["mcu.mcu"]["reference"], "U2")
        self.assertEqual(self.entries["mcu.mcu"]["packaged_ref"], "U1")
        self.assertEqual(self.entries["buck.c_in"]["reference"], "C1")
        # A path census that omits an instance fails, even with plausible refs.
        bridge = [
            {"reference": ref, "instance_path": path, "footprint": "fp:P"}
            for path, ref in [
                ("buck.buck", "U1"),
                ("buck.l_out", "L1"),
            ]
        ]
        with self.assertRaises(CompositionError):
            compose_blocks.build_source_map(
                bridge,
                require_mcu=True,
                expected_buck_paths=compose_blocks.BUCK_FUNCTIONAL_PATHS,
                expected_mcu_paths=compose_blocks.MCU_FUNCTIONAL_PATHS,
            )

    def test_scenario3_vias_span_target_and_transform_is_native(self) -> None:
        vias = json.loads((self.PACKAGE / "via-recreation.json").read_text(encoding="utf-8"))
        self.assertEqual(vias["target_span"], "F.Cu-B.Cu")
        self.assertGreater(len(vias["vias"]), 0)
        for via in vias["vias"]:
            self.assertEqual(via["span"], "F.Cu-B.Cu")
        # Asymmetric 45-degree probe against the pcbnew ground truth.
        x, y = compose_blocks.rotate_local_to_world(10.0, 4.0, math.radians(45.0))
        self.assertAlmostEqual(x, 9.899495, places=5)
        self.assertAlmostEqual(y, -4.242641, places=5)

    def test_scenario4_rejections_and_owned_region(self) -> None:
        layer_map = json.loads((self.PACKAGE / "layer-map.json").read_text(encoding="utf-8"))
        self.assertEqual(layer_map["mapping"], {"F.Cu": "F.Cu", "B.Cu": "B.Cu"})
        for record in layer_map["records"]:
            self.assertIn(record["source"], ("F.Cu", "B.Cu"))
        exclusion = json.loads(
            (self.PACKAGE / "prototype-exclusion.json").read_text(encoding="utf-8")
        )
        self.assertIn("J1", exclusion["excluded_refs"])
        self.assertGreater(len(exclusion["removed_copper"]), 0)
        guard = json.loads(
            (self.PACKAGE / "owned-region-guard.json").read_text(encoding="utf-8")
        )
        for record in guard["records"]:
            self.assertIn(record["envelope"], ("buck_block", "mcu_block"))
        # An out-of-region change is rejected before publication.
        with self.assertRaises(CompositionError):
            compose_blocks.check_owned_region(
                5.0, 5.0, [{"ref": "buck_block", "x1": 100.0, "y1": 132.0, "x2": 146.0, "y2": 162.0}]
            )


class StagingReadiness(unittest.TestCase):
    def test_buck_nine_ready_pending_mcu(self) -> None:
        readiness = compose_blocks.buck_staging_readiness(TARGET_CONTEXT)
        self.assertEqual(len(readiness["functional_refs"]), 9)
        self.assertIn("U3", readiness["functional_refs"])
        self.assertEqual(readiness["via"]["span"], "F.Cu-B.Cu")
        self.assertIn("mcu_pending", readiness)
        self.assertEqual(
            readiness["physical_copper_order"],
            ["F.Cu", "In3.Cu", "In1.Cu", "In2.Cu", "In4.Cu", "B.Cu"],
        )

    def test_mcu_input_contract_shape(self) -> None:
        contract = json.loads(MCU_CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["schema"], "control-assembly.mcu-input-contract.v1")
        self.assertEqual(contract["status"], "pending-p1-u4")
        self.assertEqual(len(contract["source_identity"]["functional_refs"]), 10)
        self.assertEqual(contract["source_identity"]["instance_path_prefix"], "mcu.")
        self.assertIn("source-manifest.json", contract["package"]["required_files"])


if __name__ == "__main__":
    unittest.main()

"""P1 U1 contract tests: the compiled MCU block matches its inventory.

Builds ``harness-lab/blocks/mcu/mcu.ato:McuCandidate`` in a fresh workspace
with pinned Atopile 0.2.69 and checks the result against
``harness-lab/blocks/mcu/identity-inventory.json``.

A missing pad, wrong ESP32 variant, contradictory part tolerance, or swapped
exported pin must fail here with the responsible source identified. These
tests are the U1 oracle; the strict Rust-side validation ships in U2 and
must agree with them, not replace them silently.

P1 U2 (below): the strict source-to-board bridge
(``harness-lab/block_source.py`` + Rust gates in ``temper-design-bundle``)
generates the MCU candidate schematic/board and the combined wrapper is
proven. Generation tests need kiutils and the fresh extension; oracle tests
need kicad-cli. Run the full file with::

    uv run --no-sync --with kiutils python -m pytest harness-lab/test_block_source.py -q
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BLOCKS = ROOT / "blocks" / "mcu"
REPO = ROOT.parent
PINNED_ATOPILE = "0.2.69"

EXPECTED_MCU_SECTION_SHA256 = "7c7da71f9afd172b347e6cee5769a91ca3388138ee9029de4b08fac079476619"


def run_build(workspace: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "uv",
            "tool",
            "run",
            "--offline",
            "--from",
            f"atopile=={PINNED_ATOPILE}",
            "ato",
            "--non-interactive",
            "build",
            "mcu.ato:McuCandidate",
        ],
        cwd=workspace,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )


def fresh_workspace(parent: Path) -> Path:
    workspace = parent / "mcu-ws"
    (workspace / "elec").mkdir(parents=True)
    shutil.copytree(
        REPO / "elec" / "src",
        workspace / "elec" / "src",
        ignore=shutil.ignore_patterns("*.log", "__pycache__"),
    )
    shutil.copyfile(BLOCKS / "mcu.ato", workspace / "mcu.ato")
    shutil.copyfile(BLOCKS / "ato.yaml", workspace / "ato.yaml")
    return workspace


def parse_csv_bom(csv_text: str) -> dict[str, str]:
    """Designator -> MPN, expanding grouped designator cells ("R1,R2")."""
    bom: dict[str, str] = {}
    for row in csv.DictReader(csv_text.splitlines()):
        for ref in row["Designator"].split(","):
            bom[ref.strip().strip('"')] = row["Comment"].strip()
    return bom


def parse_netlist(net_text: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Return (ref -> instance path, net name -> sorted U1 pads)."""
    comp_paths = dict(
        re.findall(
            r'\(comp \(ref "(.*?)"\).*?\(sheetpath \(names "(.*?)"\)',
            net_text,
            re.S,
        )
    )
    u1_pins: dict[str, list[str]] = {}
    for name, body in re.findall(
        r'\(net \(code "\d+"\) \(name "(.*?)"\)(.*?)(?=\(net \(code|\Z)',
        net_text,
        re.S,
    ):
        pins = sorted(
            re.findall(r'\(node \(ref "U1"\) \(pin "(\d+)"\)', body),
            key=int,
        )
        u1_pins[name] = pins
    return comp_paths, u1_pins


def check_against_inventory(net_text: str, csv_text: str, inventory: dict) -> None:
    """Raise AssertionError naming the responsible source on any mismatch."""
    bom = parse_csv_bom(csv_text)
    expected_mpns = {inst["designator"]: inst["mpn"] for inst in inventory["physical_instances"]}
    if set(bom) != set(expected_mpns):
        raise AssertionError(
            f"physical instance set mismatch: netlist={sorted(bom)} "
            f"inventory={sorted(expected_mpns)} "
            "(responsible source: elec/src/modules.ato MCU instances)"
        )
    for ref, mpn in expected_mpns.items():
        if bom[ref] != mpn:
            raise AssertionError(
                f"wrong part at {ref}: built {bom[ref]!r} != "
                f"inventory {mpn!r} "
                "(responsible source: elec/src/modules.ato or "
                "elec/src/components.ato MPN fields)"
            )
    _, u1_pins = parse_netlist(net_text)
    for entry in inventory["boundary_nets"]:
        actual = u1_pins.get(entry["net"])
        if actual != [entry["u1_pad"]]:
            raise AssertionError(
                f"swapped/missing pin on net {entry['net']!r}: built "
                f"{actual} != inventory U1 pad [{entry['u1_pad']}] "
                "(responsible source: elec/src/modules.ato MCU wiring or "
                "elec/src/components.ato ESP32_S3_WROOM_1 pin numbers)"
            )


class McuBlockSourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="mcu-u1-"))
        cls.workspace = fresh_workspace(cls.tmp)
        cls.build = run_build(cls.workspace)
        cls.inventory = json.loads((BLOCKS / "identity-inventory.json").read_text())
        cls.net_text = (cls.workspace / "build" / "default.net").read_text()
        cls.csv_text = (cls.workspace / "build" / "default.csv").read_text()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_build_succeeds_with_all_assertions_passing(self) -> None:
        self.assertEqual(self.build.returncode, 0, self.build.stderr[-2000:])
        # Belt and braces: a failed assertion exits nonzero, but build
        # artifacts are still written, so consumers must gate on the
        # report text as well as the return code (measured 2026-09-10).
        self.assertNotIn("FAILED", self.build.stdout)
        self.assertIn("3.3V within 3.13 to 3.46 V", self.build.stdout)
        self.assertTrue((self.workspace / "build" / "default.net").is_file())
        self.assertTrue((self.workspace / "build" / "default.csv").is_file())

    def test_mcu_source_section_is_the_inventoried_one(self) -> None:
        src = (REPO / "elec" / "src" / "modules.ato").read_text()
        section = re.search(r"(?ms)^module MCU:.*?(?=^module |\Z)", src)
        self.assertIsNotNone(section)
        digest = hashlib.sha256(section.group(0).encode()).hexdigest()  # type: ignore[union-attr]
        self.assertEqual(
            digest,
            EXPECTED_MCU_SECTION_SHA256,
            "MCU source section changed without re-inventory: update "
            "harness-lab/blocks/mcu/identity-inventory.json and this pin "
            "after review",
        )
        self.assertEqual(
            digest,
            self.inventory["provenance"]["mcu_section_sha256"],
        )

    def test_exact_physical_instances_and_interfaces(self) -> None:
        check_against_inventory(self.net_text, self.csv_text, self.inventory)
        comp_paths, _ = parse_netlist(self.net_text)
        instances = {inst["instance"] for inst in self.inventory["physical_instances"]}
        built_instances = {path.split("::")[-1] for path in comp_paths.values()}
        self.assertEqual(built_instances, instances)
        for path in comp_paths.values():
            self.assertIn("McuCandidate::mcu.", path)

    def test_wrong_variant_is_rejected_with_source_identified(self) -> None:
        mutated = self.csv_text.replace("ESP32-S3-WROOM-1-N8R8", "ESP32-S3-WROOM-1-N4R2", 1)
        with self.assertRaises(AssertionError) as ctx:
            check_against_inventory(self.net_text, mutated, self.inventory)
        self.assertIn("components.ato", str(ctx.exception))

    def test_swapped_exported_pin_is_rejected(self) -> None:
        mutated = self.net_text.replace(
            '(node (ref "U1") (pin "17")', '(node (ref "U1") (pin "99")', 1
        )
        with self.assertRaises(AssertionError) as ctx:
            check_against_inventory(mutated, self.csv_text, self.inventory)
        self.assertIn("modules.ato", str(ctx.exception))

    def test_missing_pad_is_rejected(self) -> None:
        mutated = re.sub(
            r'\(node \(ref "U1"\) \(pin "24"\)[^\)]*\)',
            "",
            self.net_text,
            count=1,
        )
        with self.assertRaises(AssertionError):
            check_against_inventory(mutated, self.csv_text, self.inventory)

    def test_contradictory_tolerance_fails_the_compiler_bands(self) -> None:
        # Restoring the pre-fix 9-11ms band under the honest +/-10%
        # tolerance must FAIL: proves the widened bands are load-bearing
        # and the old source was contradictory, not merely strict.
        tmp = Path(tempfile.mkdtemp(prefix="mcu-u1-neg-"))
        try:
            workspace = fresh_workspace(tmp)
            wrapper_src = workspace / "elec" / "src" / "modules.ato"
            src = wrapper_src.read_text()
            src = src.replace(
                "assert t_boot_rc within 8.5ms to 11.5ms",
                "assert t_boot_rc within 9ms to 11ms",
            )
            wrapper_src.write_text(src)
            result = run_build(workspace)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAILED", result.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# P1 U2: strict source-to-board bridge + combined wrapper.
# ---------------------------------------------------------------------------

try:
    import kiutils  # noqa: F401

    HAVE_KIUTILS = True
except ImportError:
    HAVE_KIUTILS = False

HAVE_KICAD_CLI = shutil.which("kicad-cli") is not None

sys.path.insert(0, str(ROOT))
import block_source  # noqa: E402

COMBO_BLOCK = ROOT / "blocks" / "control-assembly"
TARGET_CONTEXT = REPO / "pcb" / "blocks" / "control-assembly" / "target-context.json"

requires_kiutils = unittest.skipUnless(HAVE_KIUTILS, "candidate generation needs kiutils")
requires_kicad_cli = unittest.skipUnless(HAVE_KICAD_CLI, "oracle verification needs kicad-cli")


def fresh_combo_workspace(parent: Path) -> Path:
    return block_source.fresh_block_workspace(REPO, COMBO_BLOCK, parent, "combo-ws")


def run_combo_build(workspace: Path) -> subprocess.CompletedProcess[str]:
    return block_source.run_atopile_build(
        workspace, "control-assembly.ato", "ControlAssemblyCandidate"
    )


def combo_shared_nets(net_text: str) -> dict[str, set[str]]:
    """Net name -> set of top-level block paths (buck.* / mcu.*)."""
    comp_paths = dict(
        re.findall(
            r'\(comp \(ref "(.*?)"\).*?\(sheetpath \(names "(.*?)"\)',
            net_text,
            re.S,
        )
    )
    shared: dict[str, set[str]] = {}
    for name, body in re.findall(
        r'\(net \(code "\d+"\) \(name "(.*?)"\)(.*?)(?=\(net \(code|\Z)',
        net_text,
        re.S,
    ):
        blocks = set()
        for ref in re.findall(r'\(node \(ref "(.*?)"\)', body):
            path = comp_paths.get(ref, "")
            tail = path.split("ControlAssemblyCandidate::")[-1]
            blocks.add(tail.split(".")[0])
        if "buck" in blocks and "mcu" in blocks:
            shared[name] = blocks
    return shared


class ControlAssemblyContract(unittest.TestCase):
    """The combined wrapper compiles and joins buck+MCU supply/return."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="mcu-u2-combo-"))
        cls.workspace = fresh_combo_workspace(cls.tmp)
        cls.build = run_combo_build(cls.workspace)
        cls.net_text = (cls.workspace / "build" / "default.net").read_text()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_combined_build_succeeds_with_all_assertions_passing(self) -> None:
        self.assertEqual(self.build.returncode, 0, self.build.stderr[-2000:])
        self.assertNotIn("FAILED", self.build.stdout)

    def test_supply_and_return_are_shared_across_both_blocks(self) -> None:
        shared = combo_shared_nets(self.net_text)
        supply = [name for name in shared if "vcc" in name]
        self.assertTrue(
            supply,
            f"no shared buck->MCU supply net; shared nets: {sorted(shared)}",
        )
        self.assertIn("gnd", shared)

    def test_wrapper_leaves_production_sources_untouched(self) -> None:
        # The wrapper is three files; the modules stay owned by elec/src.
        self.assertEqual(
            sorted(p.name for p in COMBO_BLOCK.iterdir()),
            ["README.md", "ato.yaml", "control-assembly.ato"],
        )


class McuCandidateGenerationContract(unittest.TestCase):
    """Scenario 1: a clean source build yields a natively loadable PCB and a
    matching schematic with no functional copper."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="mcu-u2-gen-"))
        cls.out = cls.tmp / "candidate"
        cls.manifest = block_source.assemble_mcu_candidate(REPO, TARGET_CONTEXT, cls.out)
        cls.pcb_text = (cls.out / "mcu_candidate.kicad_pcb").read_text()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @requires_kiutils
    def test_ten_components_and_canonical_identities(self) -> None:
        self.assertEqual(len(self.manifest["converted"]["components"]), 10)
        inventory = json.loads((BLOCKS / "identity-inventory.json").read_text())
        expected_mpns = {
            inst["designator"]: inst["mpn"] for inst in inventory["physical_instances"]
        }
        for comp in self.manifest["converted"]["components"]:
            self.assertEqual(comp["mpn"], expected_mpns[comp["reference"]])
            self.assertEqual(comp["origins"]["mpn"], "resolved-attr+csv")

    @requires_kiutils
    def test_no_functional_copper(self) -> None:
        for marker in ("(segment ", "(via ", "(zone ", "(track "):
            self.assertNotIn(marker, self.pcb_text)

    @requires_kiutils
    def test_pcb_oracle_passes_on_raw_pad_numbers(self) -> None:
        sys.path.insert(0, str(REPO / "scripts"))
        import gen_pcb_skeleton as skeleton

        net_path = self.out / "build-evidence" / "default.net"
        self.assertTrue(net_path.is_file())
        self.assertTrue((self.out / "mcu_candidate.kicad_pcb").is_file())
        self.assertTrue(
            skeleton.candidate_oracle_verify(
                self.out / "mcu_candidate.kicad_pcb",
                skeleton.parse_netlist(net_path),
                {
                    (e["reference"], e["pin"]): e["pad"]
                    for e in self.manifest["strict_map"]["entries"]
                },
                tuple(self.manifest["board"]["outline_mm"]),
            )
        )

    @requires_kiutils
    def test_p3_outline_layers_and_neutral_staging(self) -> None:
        live = json.loads(TARGET_CONTEXT.read_text())
        self.assertEqual(
            self.manifest["board"]["outline_mm"],
            [live["target"]["outline_mm"][k] for k in ("x1", "y1", "x2", "y2")],
        )
        self.assertEqual(
            self.manifest["board"]["layers"],
            live["target"]["physical_copper_order"],
        )
        region = live["reserved_regions_mm"]["mcu_block"]
        staging = self.manifest["staging"]["positions"]
        self.assertTrue(self.manifest["staging"]["staging_only"])
        for ref, (x, y, rot) in staging.items():
            self.assertTrue(
                region["x1"] <= x <= region["x2"] and region["y1"] <= y <= region["y2"],
                f"staging position {ref}={(x, y)} outside the P3 MCU region",
            )
            self.assertEqual(rot, 0.0)
        self.assertFalse(self.manifest["production_pcb_geometry_used"])

    @requires_kiutils
    def test_empty_reference_nets_never_become_copper(self) -> None:
        excluded = self.manifest["converted"]["empty_reference_nets_excluded"]
        self.assertTrue(excluded)
        board_nets = set(re.findall(r'\(net \d+ "(.*?)"', self.pcb_text))
        for name in excluded:
            self.assertNotIn(name, board_nets)

    @requires_kicad_cli
    @requires_kiutils
    def test_schematic_oracle_passes(self) -> None:
        sys.path.insert(0, str(REPO / "scripts"))
        import gen_schematics as schematics

        self.assertTrue((self.out / "mcu_candidate.kicad_sch").is_file())
        self.assertTrue((self.out / "mcu.kicad_sch").is_file())
        layout = schematics.mcu_candidate_layout()
        self.assertEqual(layout.root_sheet, "mcu_candidate.kicad_sch")
        self.assertTrue(
            schematics.oracle_verify(
                self.out / "build-evidence" / "default.net",
                self.out,
                layout=layout,
            )
        )


def _bundle() -> object:
    import temper_design_bundle_python as bundle

    return bundle


def _sexpr_blocks(text: str, head: str) -> list[str]:
    """Raw top-level `(head ...)` blocks via paren balancing (strings aware
    of quotes and backslash escapes)."""
    blocks: list[str] = []
    token = f"({head} "
    pos = 0
    while True:
        start = text.find(token, pos)
        if start < 0:
            return blocks
        depth = 0
        in_string = False
        escaped = False
        end = start
        for i in range(start, len(text)):
            char = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        blocks.append(text[start:end])
        pos = end


def pcb_pad_net_partition(pcb_text: str) -> dict[tuple[str, str], str]:
    """Independent (ref, pad) -> net rebuild from raw PCB text: net table
    plus per-footprint pad net numbers. No kiutils, no generator code."""
    nets = dict(re.findall(r'\(net (\d+) "(.*?)"', pcb_text))
    partition: dict[tuple[str, str], str] = {}
    for body in _sexpr_blocks(pcb_text, "footprint"):
        ref_match = re.search(r'\(property "Reference" "(.*?)"', body)
        if not ref_match:
            continue
        ref = ref_match.group(1)
        for pad in _sexpr_blocks(body, "pad"):
            number = re.match(r'\(pad "([^"]+)"', pad)
            net = re.search(r'\(net (\d+)(?: "[^"]*")?\)', pad)
            if number and net and net.group(1) != "0" and nets.get(net.group(1)):
                partition[(ref, number.group(1))] = nets[net.group(1)]
    return partition


def compiled_pin_partition(net_text: str) -> dict[tuple[str, str], str]:
    """Independent (ref, pin) -> net rebuild from the compiled netlist,
    including single-node nets."""
    partition: dict[tuple[str, str], str] = {}
    for name, body in re.findall(
        r'\(net \(code "\d+"\) \(name "(.*?)"\)(.*?)(?=\(net \(code|\Z)',
        net_text,
        re.S,
    ):
        for ref, pin in re.findall(r'\(node \(ref "(.*?)"\) \(pin "(.*?)"\)', body):
            partition[(ref, pin)] = name
    return partition


class StrictPinPartitionContract(unittest.TestCase):
    """Scenario 2: every pad net matches the independent compiled pin
    partition, including repeated same-number pads and unconnected pins."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="mcu-u2-part-"))
        cls.out = cls.tmp / "candidate"
        cls.manifest = block_source.assemble_mcu_candidate(REPO, TARGET_CONTEXT, cls.out)
        cls.pcb_text = (cls.out / "mcu_candidate.kicad_pcb").read_text()
        cls.net_text = (cls.out / "build-evidence" / "default.net").read_text()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @requires_kiutils
    def test_board_pads_match_compiled_pins_exactly(self) -> None:
        board = pcb_pad_net_partition(self.pcb_text)
        compiled = compiled_pin_partition(self.net_text)
        pin_map = {
            (e["reference"], e["pin"]): e["pad"] for e in self.manifest["strict_map"]["entries"]
        }
        # Every compiled pin lands on its mapped pad with the same net, and
        # every board pad traces back to exactly one compiled pin.
        self.assertTrue(compiled)
        for (ref, pin), net in compiled.items():
            self.assertIn((ref, pin), pin_map)
            self.assertEqual(board.get((ref, pin_map[(ref, pin)])), net)
        mapped_back = {(ref, pad): pin for (ref, pin), pad in pin_map.items()}
        for (ref, pad), net in board.items():
            self.assertIn((ref, pad), mapped_back)
            pin = mapped_back[(ref, pad)]
            self.assertEqual(compiled.get((ref, pin)), net)

    @requires_kiutils
    def test_single_node_nets_keep_their_pad_net(self) -> None:
        compiled = compiled_pin_partition(self.net_text)
        singles = [key for key, net in compiled.items() if net == "gpio18"]
        self.assertEqual(singles, [("U1", "11")])
        board = pcb_pad_net_partition(self.pcb_text)
        self.assertEqual(board.get(("U1", "11")), "gpio18")

    def test_repeated_ground_pads_and_unconnected_via_rust(self) -> None:
        bundle = _bundle()
        entries = json.dumps(
            [
                {
                    "instance_path": "m.U1",
                    "reference": "U1",
                    "pin": "1",
                    "pad": "1",
                    "alias_note": "",
                    "positional": False,
                }
            ]
        )
        pads = json.dumps({"U1": ["1", "1", "9"]})
        pins = json.dumps({"U1": ["1"]})
        # Repeated pad number on the same pin plus an explicitly listed
        # unconnected pad passes.
        bundle.candidate_validate_pin_map(entries, pads, pins, json.dumps([["U1", "9"]]))
        # The same repeated pad claimed for another pin fails as split.
        split = json.dumps(
            json.loads(entries)
            + [
                {
                    "instance_path": "m.U1",
                    "reference": "U1",
                    "pin": "2",
                    "pad": "1",
                    "alias_note": "reviewed",
                    "positional": False,
                }
            ]
        )
        with self.assertRaises(ValueError) as ctx:
            bundle.candidate_validate_pin_map(
                split,
                pads,
                json.dumps({"U1": ["1", "2"]}),
                json.dumps([["U1", "9"]]),
            )
        self.assertIn("split_pad", str(ctx.exception))


class StrictRejectionContract(unittest.TestCase):
    """Scenario 3: duplicate/missing maps, positional-only mappings, altered
    footprint bytes, stale exports, and extra components all fail."""

    def test_duplicate_missing_and_positional_maps_fail(self) -> None:
        bundle = _bundle()
        base = {
            "instance_path": "m.U1",
            "reference": "U1",
            "pin": "1",
            "pad": "1",
            "alias_note": "",
            "positional": False,
        }
        pads = json.dumps({"U1": ["1"]})
        pins = json.dumps({"U1": ["1"]})
        with self.assertRaises(ValueError) as ctx:
            bundle.candidate_validate_pin_map(
                json.dumps([base, dict(base)]), pads, pins, json.dumps([])
            )
        self.assertIn("duplicate_map", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            bundle.candidate_validate_pin_map(json.dumps([]), pads, pins, json.dumps([]))
        self.assertIn("missing_map", str(ctx.exception))
        positional = dict(base, positional=True)
        with self.assertRaises(ValueError) as ctx:
            bundle.candidate_validate_pin_map(json.dumps([positional]), pads, pins, json.dumps([]))
        self.assertIn("positional_fallback", str(ctx.exception))

    def test_stale_export_and_failed_build_fail(self) -> None:
        bundle = _bundle()
        recorded = json.dumps({"mcu.ato": "aaa", "elec/src/x.ato": "bbb"})
        bundle.validation.candidate_check_freshness(recorded, recorded, 0, "3 passed")
        with self.assertRaises(ValueError) as ctx:
            bundle.validation.candidate_check_freshness(recorded, recorded, 1, "3 passed")
        self.assertIn("failed_build", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            bundle.validation.candidate_check_freshness(recorded, recorded, 0, "1 FAILED, 2 passed")
        self.assertIn("failed_assertion", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            bundle.validation.candidate_check_freshness(
                recorded, json.dumps({"mcu.ato": "CHANGED"}), 0, "3 passed"
            )
        self.assertIn("stale_export", str(ctx.exception))

    def test_conflicting_and_extra_bridge_inputs_fail(self) -> None:
        bundle = _bundle()
        export = {
            "schema": "temper.circuit-export.v1",
            "atopile_version": "0.2.69",
            "entry": "/w/mcu.ato:McuCandidate",
            "components": [
                {
                    "address": "/w/mcu.ato:McuCandidate::mcu.mcu",
                    "attributes": {
                        "mpn": "PART-A",
                        "footprint": "Test:Foo",
                        "value": "10kohm",
                    },
                }
            ],
        }
        netlist = {
            "components": [
                {
                    "reference": "U1",
                    "instance_path": "mcu.mcu",
                    "footprint": "Test:Foo",
                    "tstamp": "t",
                }
            ],
            "nets": [{"name": "vcc", "nodes": [["U1", "2"]]}],
        }
        with self.assertRaises(ValueError) as ctx:
            bundle.candidate_convert_bridge(
                json.dumps(export),
                json.dumps(netlist),
                json.dumps({"U1": "PART-B"}),
                "McuCandidate",
            )
        self.assertIn("bom_conflict", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            bundle.candidate_convert_bridge(
                json.dumps(export),
                json.dumps(netlist),
                json.dumps({"U1": "PART-A", "U9": "PART-A"}),
                "McuCandidate",
            )
        self.assertIn("bom_extra", str(ctx.exception))
        wrong_tool = dict(export, atopile_version="0.2.70")
        with self.assertRaises(ValueError) as ctx:
            bundle.candidate_convert_bridge(
                json.dumps(wrong_tool),
                json.dumps(netlist),
                json.dumps({"U1": "PART-A"}),
                "McuCandidate",
            )
        self.assertIn("tool_mismatch", str(ctx.exception))

    def test_empty_net_admission_fails(self) -> None:
        bundle = _bundle()
        nets = json.dumps(
            [
                {"name": "vcc", "nodes": [["U1", "2"]]},
                {"name": "mcu-reference", "nodes": []},
            ]
        )
        with self.assertRaises(ValueError) as ctx:
            bundle.validation.candidate_check_net_admission(
                nets, json.dumps(["vcc", "mcu-reference"])
            )
        self.assertIn("empty_net_admitted", str(ctx.exception))

    @requires_kiutils
    def test_altered_footprint_bytes_break_the_map(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="mcu-u2-tamper-"))
        try:
            out = tmp / "candidate"
            manifest = block_source.assemble_mcu_candidate(REPO, TARGET_CONTEXT, out)
            census = manifest["inputs"]["footprint_census"]
            victim = out / "candidate-libs" / "lib.pretty" / "ESP32-S3-WROOM-1.kicad_mod"
            before = census["lib:ESP32-S3-WROOM-1"]["sha256"]
            text = victim.read_text()
            victim.write_text(text.replace('(pad "1" smd', '(pad "1X" smd', 1))
            self.assertNotEqual(block_source.sha256_file(victim), before)
            tampered = block_source.footprint_pad_census(
                out / "fp-lib-table",
                {
                    c["footprint"]
                    for c in block_source.bridge_netlist(
                        out / "build-evidence" / "default.net",
                        "McuCandidate",
                    )["components"]
                },
            )
            self.assertNotIn("1", tampered["lib:ESP32-S3-WROOM-1"]["pads"])
            bridge = block_source.bridge_netlist(
                out / "build-evidence" / "default.net", "McuCandidate"
            )
            nick = {c["reference"]: c["footprint"] for c in bridge["components"]}
            by_ref = {comp["reference"]: comp for comp in manifest["converted"]["components"]}
            bundle = _bundle()
            with self.assertRaises(ValueError):
                bundle.candidate_validate_pin_map(
                    json.dumps(manifest["strict_map"]["entries"]),
                    json.dumps({ref: tampered[nick[ref]]["pads"] for ref in by_ref}),
                    json.dumps(
                        {
                            ref: sorted(
                                {
                                    pin
                                    for net in bridge["nets"]
                                    for r, pin in net["nodes"]
                                    if r == ref
                                }
                            )
                            for ref in by_ref
                        }
                    ),
                    json.dumps(manifest["strict_map"]["unconnected_pads"]),
                )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class CandidateDeterminismContract(unittest.TestCase):
    """Scenario 4: repeated generation keeps stable canonical identities and
    geometry; workspace-path-derived hashes are identified separately."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="mcu-u2-det-"))
        cls.first = cls.tmp / "first"
        cls.second = cls.tmp / "second"
        cls.manifest_a = block_source.assemble_mcu_candidate(REPO, TARGET_CONTEXT, cls.first)
        cls.manifest_b = block_source.assemble_mcu_candidate(REPO, TARGET_CONTEXT, cls.second)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @requires_kiutils
    def test_board_schematic_and_libs_are_byte_stable(self) -> None:
        for name in (
            "mcu_candidate.kicad_pcb",
            "mcu_candidate.kicad_sch",
            "mcu.kicad_sch",
            "fp-lib-table",
            "schematic_layout.json",
            "rules.json",
            "mcu_candidate.kicad_pro",
        ):
            self.assertEqual(
                (self.first / name).read_bytes(),
                (self.second / name).read_bytes(),
                f"{name} differs between repeated generations",
            )
        for lib in ("lib.pretty", "Capacitor_SMD.pretty", "Resistor_SMD.pretty"):
            for mod in sorted((self.first / "candidate-libs" / lib).iterdir()):
                self.assertEqual(
                    mod.read_bytes(),
                    (self.second / "candidate-libs" / lib / mod.name).read_bytes(),
                )

    @requires_kiutils
    def test_canonical_identities_and_geometry_are_stable(self) -> None:
        for key in (
            "converted",
            "strict_map",
            "staging",
            "schematic",
            "board",
            "target_context",
        ):
            self.assertEqual(self.manifest_a[key], self.manifest_b[key])

    @requires_kiutils
    def test_only_workspace_derived_hashes_move(self) -> None:
        moving = {
            f"inputs.{key}"
            for key in self.manifest_a["inputs"]
            if self.manifest_a["inputs"][key] != self.manifest_b["inputs"].get(key)
        }
        # The compiled netlist/export and raw build logs embed the ephemeral
        # workspace path, so their bytes (and hashes) move; everything else
        # -- including the gate summary, source hashes, library bytes, and
        # census -- is stable. stderr moves only if the compiler ever warns;
        # on a clean build it is empty and stable.
        self.assertTrue(
            moving - {"inputs.stderr_sha256"}
            == {
                "inputs.netlist_sha256",
                "inputs.export_sha256",
                "inputs.stdout_sha256",
            }
        )
        for manifest in (self.manifest_a, self.manifest_b):
            self.assertEqual(
                manifest["inputs"]["build_gate"],
                {"returncode": 0, "failed_present": False},
            )


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    unittest.main()

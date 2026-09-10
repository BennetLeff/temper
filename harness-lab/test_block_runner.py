"""P1 U3 runner tests: bounded block execution, memory delivery, preflight.

Session/host behavior runs against a synthetic MCU-like candidate package on
real KiCad (runner-machinery control on buck geometry: the profile path,
budgets, atomicity, and preflight are what's under test; MCU construction
semantics are pinned at the judge level in test_block_boundary and go live
in U4). Memory loads through the real P2 Rust judge; workspace delivery
uses the real sandbox worker.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

import buck_host
import harness
import run_block
import workspace

ROOT = Path(__file__).parent
FIXTURE_BOARD = ROOT / "fixtures" / "buck" / "buck-dev-a" / "candidate.kicad_pcb"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fake_netlist(path: Path) -> None:
    path.write_text(
        """(export (version D) (design (source "mcu.ato") (date "2026-09-10"))
  (components
    (comp (ref U3) (value "LMR51430") (footprint "lib:LMR51430")
      (tstamps "t1") (sheetpath (names "/aa/Top:McuCandidate::buck.buck") (tstamps "/aa")))
    (comp (ref C9) (value "10u") (footprint "lib:C_0805")
      (tstamps "t2") (sheetpath (names "/aa/Top:McuCandidate::buck.c_in") (tstamps "/aa"))))
  (nets
    (net (code 1) (name "vcc") (node (ref U3) (pin 3)) (node (ref C9) (pin 1)))
    (net (code 2) (name "gnd") (node (ref U3) (pin 1)) (node (ref C9) (pin 2)))))
""",
        encoding="utf-8",
    )


def fake_candidate(parent: Path) -> Path:
    """Minimal MCU-like candidate package (manifest + netlist + libs + board).

    Geometry comes from the buck fixture purely as a runner-machinery
    control; the manifest/netlist shape is what build_task_contract reads.
    """
    candidate = parent / "candidate"
    target_context = (
        ROOT.parent / "pcb" / "blocks" / "control-assembly" / "target-context.json"
    )
    (candidate / "build-evidence").mkdir(parents=True)
    fake_netlist(candidate / "build-evidence" / "default.net")
    (candidate / "build-evidence" / "default.csv").write_text(
        'Designator,Comment\n"U3","LMR51430XDDCR"\n"C9","CL32B106KBJZW6E"\n',
        encoding="utf-8",
    )
    manifest = {
        "entry": "mcu.ato:McuCandidate",
        "atopile_pinned": "0.2.69",
        "target_context": {
            "path": "pcb/blocks/control-assembly/target-context.json",
            "sha256": sha256(target_context),
        },
        "strict_map": {
            "entries": [
                {
                    "instance_path": "buck.buck",
                    "reference": "U3",
                    "pin": "3",
                    "pad": "3",
                    "alias_note": "",
                    "positional": False,
                },
                {
                    "instance_path": "buck.buck",
                    "reference": "U3",
                    "pin": "1",
                    "pad": "1",
                    "alias_note": "",
                    "positional": False,
                },
                {
                    "instance_path": "buck.c_in",
                    "reference": "C9",
                    "pin": "1",
                    "pad": "1",
                    "alias_note": "",
                    "positional": False,
                },
                {
                    "instance_path": "buck.c_in",
                    "reference": "C9",
                    "pin": "2",
                    "pad": "2",
                    "alias_note": "",
                    "positional": False,
                },
            ],
            "unconnected_pads": [],
        },
        "staging": {
            "positions": {"U3": [30.0, 30.0, 0.0], "C9": [20.0, 25.0, 0.0]},
            "staging_only": True,
        },
        "converted": {
            "components": [
                {"reference": "U3", "instance_path": "buck.buck"},
                {"reference": "C9", "instance_path": "buck.c_in"},
            ],
            "net_count": 2,
            "empty_reference_nets": [],
        },
    }
    (candidate / "source-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (candidate / "fp-lib-table").write_text(
        "(fp_lib_table\n  (version 7)\n"
        '  (lib (name "lib")(type "KiCad")'
        '(uri "${KIPRJMOD}/candidate-libs/lib.pretty")(options "")(descr "")))\n',
        encoding="utf-8",
    )
    (candidate / "candidate-libs" / "lib.pretty").mkdir(parents=True)
    shutil.copyfile(FIXTURE_BOARD, candidate / "mcu_candidate.kicad_pcb")
    return candidate


class FakeSession:
    """Untrusted-worker harness double (mirrors test_workspace.FakeSession)."""

    def __init__(self) -> None:
        self.deadline = time.monotonic() + 1200
        self.revision = "0" * 64
        self.actions = 0
        self.sequence = 0
        self.terminal_error = None
        self.calls: list[tuple[str, dict]] = []

    def _rust_policy(self, operation: str, arguments: dict) -> dict:
        if operation == "execute" and set(arguments) != {"code"}:
            raise ValueError("bad execute arguments")
        return {"status": "pass", "operation": operation}

    def call(self, operation: str, arguments: dict) -> dict:
        self.sequence += 1
        self.calls.append((operation, arguments))
        if operation in ("place", "replace_copper"):
            if self.actions >= 200:
                return {"status": "invalid", "error": "budget"}
            self.actions += 1
            self.revision = f"{self.actions:064x}"
            return {
                "status": "pass",
                "mutation_committed": True,
                "native_verdict": "pass",
                "revision": self.revision,
            }
        return {"status": "pass", "mutation_committed": False, "native_verdict": None}


class BlockRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assertTrue(Path(harness.JUDGE).is_file(), "harness judge is not built")
        cls.assertTrue(FIXTURE_BOARD.is_file(), "buck fixture board missing")

    def make_trial(self, parent: Path) -> tuple[Path, Path]:
        candidate = fake_candidate(parent)
        trial = run_block.prepare(parent / "trial", candidate)
        return trial, candidate

    def test_task_contract_pins_p3_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            candidate = fake_candidate(Path(tmp))
            contract = run_block.build_task_contract(candidate)
            target = json.loads(
                (
                    ROOT.parent
                    / "pcb"
                    / "blocks"
                    / "control-assembly"
                    / "target-context.json"
                ).read_text()
            )
            self.assertEqual(
                contract["physical_copper_order"],
                target["target"]["physical_copper_order"],
            )
            self.assertEqual(contract["profile"], "block")
            self.assertEqual(contract["movable_refs"], ["C9", "U3"])
            self.assertEqual(
                contract["obligations"],
                {"vcc": ["C9.1", "U3.3"], "gnd": ["C9.2", "U3.1"]},
            )
            self.assertEqual(contract["keepouts"][0]["id"], "antenna_keepout")
            self.assertEqual(contract["protected_ports"], {})
            self.assertEqual(contract["boundary"], {})

    def test_task_contract_rejects_target_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            candidate = fake_candidate(Path(tmp))
            manifest_path = candidate / "source-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["target_context"]["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                run_block.build_task_contract(candidate)

    def test_prepare_seals_contract_natively(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trial, _ = self.make_trial(Path(tmp))
            contract = json.loads((trial / "task-contract.json").read_text())
            self.assertEqual(len(contract["protected_sha256"]), 64)
            source = json.loads((trial / "source.json").read_text())
            self.assertEqual(
                source["task_contract_sha256"], sha256(trial / "task-contract.json")
            )
            self.assertEqual(source["context_sha256"], harness.context_hash(trial))
            self.assertTrue((trial / "initial.kicad_pcb").is_file())

    def test_inspect_passes_natively(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trial, _ = self.make_trial(Path(tmp))
            session = run_block.BlockSession(trial)
            try:
                result = session.call("inspect", {})
                self.assertEqual(result["status"], "pass", result)
                self.assertTrue(result["measurement"]["footprints"], result)
                self.assertFalse(result["mutation_committed"])
            finally:
                session.close()

    def test_rejected_edit_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trial, _ = self.make_trial(Path(tmp))
            session = run_block.BlockSession(trial)
            try:
                before = (trial / "candidate.kicad_pcb").read_bytes()
                result = session.call(
                    "place",
                    {"reference": "NOPE", "x_mm": 30, "y_mm": 30, "angle_deg": 0},
                )
                self.assertEqual(result["status"], "invalid", result)
                self.assertFalse(result["mutation_committed"])
                self.assertEqual(session.actions, 0)
                self.assertEqual((trial / "candidate.kicad_pcb").read_bytes(), before)
            finally:
                session.close()

    def test_stale_revision_rejected_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trial, _ = self.make_trial(Path(tmp))
            session = run_block.BlockSession(trial)
            try:
                before_actions = session.actions
                with (trial / "candidate.kicad_pcb").open("ab") as stream:
                    stream.write(b"\n")
                result = session.call("inspect", {})
                self.assertEqual(result["status"], "invalid", result)
                self.assertEqual(session.actions, before_actions)
            finally:
                session.close()

    def test_place_commits_with_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trial, _ = self.make_trial(Path(tmp))
            session = run_block.BlockSession(trial)
            try:
                before = session.revision
                result = session.call(
                    "place",
                    {"reference": "C9", "x_mm": 25, "y_mm": 30, "angle_deg": 90},
                )
                self.assertTrue(result["mutation_committed"], result)
                self.assertNotEqual(session.revision, before)
                self.assertEqual(session.actions, 1)
                self.assertTrue((trial / "state-000001.kicad_pcb").is_file())
            finally:
                session.close()

    def test_preflight_inspect_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trial, _ = self.make_trial(Path(tmp))
            session = run_block.BlockPreflight(trial)
            try:
                self.assertEqual(session.call("inspect", {})["status"], "pass")
                before = (trial / "candidate.kicad_pcb").read_bytes()
                result = session.call(
                    "place",
                    {"reference": "C9", "x_mm": 25, "y_mm": 30, "angle_deg": 0},
                )
                self.assertEqual(result["status"], "invalid", result)
                self.assertEqual(session.actions, 0)
                self.assertEqual((trial / "candidate.kicad_pcb").read_bytes(), before)
            finally:
                session.close()

    def test_expired_deadline_is_indeterminate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trial, _ = self.make_trial(Path(tmp))
            session = run_block.BlockSession(trial, deadline=time.monotonic() - 1)
            try:
                result = session.call("inspect", {})
                self.assertEqual(result["status"], "indeterminate", result)
                self.assertIsNotNone(session.terminal_error)
            finally:
                session.close()

    def test_generation_is_operator_controlled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with self.assertRaises(run_block.GenerationNotPermitted):
                run_block.generate_candidate(
                    ROOT.parent,
                    ROOT.parent
                    / "pcb"
                    / "blocks"
                    / "control-assembly"
                    / "target-context.json",
                    tmp_path / "out",
                    confirm=True,
                )
            self.assertFalse((tmp_path / "out").exists())
            with self.assertRaises(run_block.GenerationNotPermitted):
                run_block.generate_candidate(
                    ROOT.parent,
                    ROOT.parent
                    / "pcb"
                    / "blocks"
                    / "control-assembly"
                    / "target-context.json",
                    tmp_path / "out2",
                    confirm=False,
                )
            request = run_block.request_generation(
                tmp_path / "req", "need a fresh candidate", attempt_id="mcu-u3-probe"
            )
            self.assertTrue(request.is_file())
            with self.assertRaises(ValueError):
                run_block.request_generation(tmp_path / "req", "second request")
            with self.assertRaises(ValueError):
                run_block.request_generation(tmp_path / "req2", "x" * 9000)

    def test_memory_reaches_worker_and_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            delivery = run_block.load_memory(tmp_path / "store", source_identities={})
            self.assertTrue(
                delivery["selection"]["selected_ids"], delivery["selection"]
            )
            self.assertEqual(
                delivery["record"]["revision_sha256"],
                delivery["receipt"]["materialized"]["revision_sha256"],
            )
            session = FakeSession()
            with workspace.Workspace(session=session) as worker:
                receipt = run_block.deliver_to_workspace(
                    worker, delivery, tmp_path / "trial-receipt"
                )
                self.assertTrue(receipt["delivery"]["acknowledged"])
                self.assertEqual(
                    worker.current_revision, delivery["record"]["revision_sha256"]
                )
                result = worker.execute(
                    "assert skills.notes, 'memory notes missing'\n"
                    "print('notes-bytes:', len(skills.notes))"
                )
                self.assertEqual(result["status"], "pass", result)
                self.assertIn("notes-bytes:", result["stdout"])

    def test_helper_nested_ops_share_budget_and_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            delivery = run_block.load_memory(tmp_path / "store", source_identities={})
            session = FakeSession()
            helper = (
                "def route_pair():\n"
                "    first = pcb.call('inspect', {})\n"
                "    second = pcb.call('place', {'reference': 'C9', 'x_mm': 10,"
                " 'y_mm': 10, 'angle_deg': 0})\n"
                "    assert first['status'] == 'pass'\n"
                "    assert second['mutation_committed']\n"
                "    return second\n"
            )
            store_record = dict(delivery["record"])
            store_record["skills_utf8"] = helper
            with workspace.Workspace(session=session) as worker:
                self.assertTrue(
                    worker.apply_revision(
                        "rev-probe",
                        helper,
                        delivery["record"]["notes_utf8"],
                    )
                )
                result = worker.execute("outcome = skills.route_pair()\nprint('ok')")
                self.assertEqual(result["status"], "pass", result)
                self.assertEqual(session.actions, 1)
                self.assertEqual(
                    worker.revision_events[-1]["source_revision"], "rev-probe"
                )

    def test_model_brief_binds_facts_findings_budget_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            trial, candidate = self.make_trial(tmp_path)
            delivery = run_block.load_memory(tmp_path / "store", source_identities={})
            session = run_block.BlockSession(trial)
            try:
                last = session.call("inspect", {})
                brief = run_block.build_model_brief(session, candidate, delivery, last)
                self.assertIn("U3", json.dumps(brief["source_facts"]["components"]))
                self.assertIn("memory", brief)
                self.assertEqual(
                    brief["memory"]["revision_sha256"],
                    delivery["record"]["revision_sha256"],
                )
                self.assertEqual(
                    brief["budget"]["remaining_actions"],
                    buck_host.MAX_ACTIONS - session.actions,
                )
                self.assertIn("stage_findings", brief)
            finally:
                session.close()


ASSEMBLY_PACKAGE = (
    ROOT.parent / "pcb" / "blocks" / "control-assembly" / "assembly-candidate"
)


class AssemblyBlockSessionTests(unittest.TestCase):
    """The combined 19-instance assembly is admitted by the same BlockSession.

    The MCU-profile contract/session path above is unchanged; this proves the
    shared bounded operations accept the combined census, nets and obligations
    without a profile fork.
    """

    @classmethod
    def setUpClass(cls):
        cls.assertTrue(Path(harness.JUDGE).is_file(), "harness judge is not built")
        cls.assertTrue(
            (ASSEMBLY_PACKAGE / "control-assembly.kicad_pcb").is_file(),
            "committed assembly candidate package missing",
        )

    def test_assembly_task_contract_admits_19_instances(self) -> None:
        contract = run_block.build_assembly_task_contract(ASSEMBLY_PACKAGE)
        self.assertEqual(contract["kind"], "assembly")
        self.assertEqual(contract["profile"], "block")
        self.assertEqual(len(contract["movable_refs"]), 19)
        self.assertEqual(sorted(contract["pad_census"]), contract["movable_refs"])
        self.assertEqual(
            sorted(contract["obligations"]), sorted(run_block.ASSEMBLY_REQUIRED_NETS)
        )
        self.assertTrue(
            set(run_block.ASSEMBLY_POWER_NETS) <= set(contract["power_nets"])
        )
        self.assertTrue(contract["signal_nets"], "signal nets must be partitioned")
        self.assertFalse(
            set(contract["power_nets"]) & set(contract["signal_nets"]),
            "power and signal nets must be disjoint",
        )
        # Every measured pad is keyed by one of the 19 movable references.
        movable = set(contract["movable_refs"])
        self.assertTrue(
            all(pad.split(".")[0] in movable for pad in contract["net_mapping"])
        )
        self.assertEqual(contract["keepouts"][0]["id"], "antenna_keepout")
        self.assertEqual(contract["zone_nets"], ["gnd"])

    def test_assembly_contract_has_no_unconnected_gap(self) -> None:
        contract = run_block.build_assembly_task_contract(ASSEMBLY_PACKAGE)
        self.assertEqual(
            sum(contract["pad_census"].values()), len(contract["net_mapping"])
        )

    def test_assembly_prepare_and_session_inspect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trial = run_block.prepare_assembly(Path(tmp) / "trial", ASSEMBLY_PACKAGE)
            session = run_block.BlockSession(trial)
            try:
                self.assertEqual(session.kind, "assembly")
                result = session.call("inspect", {})
                self.assertEqual(result["status"], "pass", result)
                self.assertFalse(result["mutation_committed"])
                self.assertEqual(len(result["measurement"]["footprints"]), 19)
            finally:
                session.close()

    def test_assembly_session_commits_bounded_copper_replace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trial = run_block.prepare_assembly(Path(tmp) / "trial", ASSEMBLY_PACKAGE)
            session = run_block.BlockSession(trial)
            try:
                before = session.revision
                result = session.call(
                    "replace_copper",
                    {"net": "buck-vcc-1", "segments": [], "vias": [], "zones": []},
                )
                self.assertTrue(result.get("mutation_committed"), result)
                self.assertEqual(session.actions, 1)
                self.assertNotEqual(session.revision, before)
                self.assertEqual(result["native_verdict"], "fail")  # retained debt
            finally:
                session.close()

    def test_assembly_session_rejects_unadmitted_net(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trial = run_block.prepare_assembly(Path(tmp) / "trial", ASSEMBLY_PACKAGE)
            session = run_block.BlockSession(trial)
            try:
                before = (trial / "candidate.kicad_pcb").read_bytes()
                result = session.call(
                    "replace_copper",
                    {"net": "not_a_net", "segments": [], "vias": [], "zones": []},
                )
                self.assertEqual(result["status"], "invalid", result)
                self.assertFalse(result["mutation_committed"])
                self.assertEqual(session.actions, 0)
                self.assertEqual((trial / "candidate.kicad_pcb").read_bytes(), before)
            finally:
                session.close()


if __name__ == "__main__":
    unittest.main()

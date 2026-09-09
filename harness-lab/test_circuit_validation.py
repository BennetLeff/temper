"""Bounded software controls for the Rust-owned U7 circuit validator."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import harness  # noqa: E402

ROOT = Path(__file__).parent
FIX = ROOT / "engineering/controls/circuit"
DIGEST = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate() -> dict:
    contract = json.loads((ROOT / "engineering/circuit-contract.json").read_text())
    return {
        "footprints": [
            {
                "reference": spec["pcb_reference"],
                "pads": [
                    {"number": pin, "net": net} for pin, net in spec["pins"].items()
                ],
            }
            for spec in contract["components"].values()
        ]
    }


def payload(*, qualification: bool = False) -> dict:
    net = FIX / "default.net"
    bom = FIX / "default.csv"
    export = json.loads((FIX / "temper-u7-export.json").read_text())
    source = {"harness-lab/engineering/buck.ato": export["source_sha256"]["buck.ato"]}
    result = {
        "profile": "engineering-circuit",
        "source": source,
        "source_unchanged": True,
        "resolved_export": export,
        "candidate": candidate(),
        "circuit_source_sha256": DIGEST,
        "atopile": {
            "build": {
                "status": "pass",
                "artifacts": {"default.net": str(net), "default.csv": str(bom)},
                "artifact_hashes": {
                    "default.net": digest(net),
                    "default.csv": digest(bom),
                },
            }
        },
    }
    if qualification:
        result["component_qualification"] = {
            "verified_artifact": True,
            "reviewed_by": "software-test",
            "source": "synthetic control",
            "source_sha256": DIGEST,
            "capacitors": {
                name: {"effective_min_uf": 1, "required_min_uf": 0.5}
                for name in ["c_in", "c_boot", "c_out1", "c_out2", "c_out_hf"]
            },
            "inductor_saturation_a": 2,
            "required_peak_a": 1,
        }
    return result


class CircuitValidatorControls(unittest.TestCase):
    def run_judge(self, value: dict) -> dict:
        proc = subprocess.run(
            [str(harness.JUDGE)],
            input=json.dumps(value),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertTrue(proc.stdout, proc.stderr)
        return json.loads(proc.stdout)

    def test_baseline_integrity_passes_but_qualification_blocks(self) -> None:
        result = self.run_judge(payload())
        self.assertEqual(result["integrity"]["status"], "pass")
        self.assertEqual(result["status"], "blocked")
        self.assertIn(
            "component_qualification_missing", {f["id"] for f in result["findings"]}
        )

    def test_resolved_software_fixture_passes_stage(self) -> None:
        result = self.run_judge(payload(qualification=True))
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["hardware_validated"])

    def test_mutations_fail_independently(self) -> None:
        value = payload(qualification=True)
        mutated = copy.deepcopy(value)
        mutated["resolved_export"]["components"][-2]["attributes"]["value"] = "10kohm"
        self.assertEqual(self.run_judge(mutated)["integrity"]["status"], "fail")
        mutated = copy.deepcopy(value)
        mutated["candidate"]["footprints"][0]["pads"].append(
            {"number": "99", "net": "gnd"}
        )
        self.assertEqual(self.run_judge(mutated)["integrity"]["status"], "fail")
        mutated = copy.deepcopy(value)
        mutated["source"]["harness-lab/engineering/buck.ato"] = "f" * 64
        self.assertEqual(self.run_judge(mutated)["integrity"]["status"], "fail")
        mutated = copy.deepcopy(value)
        mutated["circuit_source_sha256"] = "f" * 64
        self.assertEqual(self.run_judge(mutated)["status"], "blocked")
        with tempfile.TemporaryDirectory() as directory:
            net = Path(directory) / "default.net"
            net.write_text(
                (FIX / "default.net").read_text().replace('"gnd"', '"sw"', 1)
            )
            mutated = copy.deepcopy(value)
            mutated["atopile"]["build"]["artifacts"]["default.net"] = str(net)
            mutated["atopile"]["build"]["artifact_hashes"]["default.net"] = digest(net)
            mutated["resolved_export"]["build_sha256"]["build/default.net"] = digest(
                net
            )
            self.assertEqual(self.run_judge(mutated)["integrity"]["status"], "fail")
            csv = Path(directory) / "default.csv"
            csv.write_text(
                (FIX / "default.csv")
                .read_text()
                .replace("GRM32ER71E226KE15L", "WRONG-MPN", 1)
            )
            mutated = copy.deepcopy(value)
            mutated["atopile"]["build"]["artifacts"]["default.csv"] = str(csv)
            mutated["atopile"]["build"]["artifact_hashes"]["default.csv"] = digest(csv)
            mutated["resolved_export"]["build_sha256"]["build/default.csv"] = digest(
                csv
            )
            self.assertEqual(self.run_judge(mutated)["integrity"]["status"], "fail")
        mutated = copy.deepcopy(value)
        mutated["atopile"]["build"]["artifact_hashes"]["default.net"] = "f" * 64
        self.assertEqual(self.run_judge(mutated)["integrity"]["status"], "fail")

    def test_missing_tool_is_blocked_without_fake_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch("circuit_native._build", return_value={"status": "blocked"}):
                from circuit_native import collect

                evidence = collect(
                    ROOT,
                    Path(directory) / "output",
                    board=Path(directory) / "candidate.kicad_pcb",
                )
        self.assertEqual(evidence["status"], "blocked")
        self.assertEqual(evidence["atopile"]["build"]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()

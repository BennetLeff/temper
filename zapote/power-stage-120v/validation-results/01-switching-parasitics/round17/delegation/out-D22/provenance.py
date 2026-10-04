#!/usr/bin/env python3
"""Bind the report to exact source inputs and retained output bytes."""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "AGENTS.md").exists() and (p / "firmware").is_dir())
PS = ROOT / "zapote/power-stage-120v"
BASE = "fda5ab9ece24ef1ee6f2317604c5ca73367d5201"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    target = HERE / "provenance.json"
    if args.verify:
        saved = json.loads(target.read_text())
        for group, root in (("inputs", ROOT), ("outputs", HERE)):
            for relative, expected in saved[group].items():
                actual = digest(root / relative)
                if actual != expected:
                    raise ValueError(f"changed {group}: {relative}")
        print("PASS: all recorded input/output SHA-256 digests match")
        return
    inputs = [
        HERE.parent / "out-D19" / name
        for name in ("periodic-sweep.cir", "sweep.py", "prepare.py", "spectrum.py")
    ]
    inputs += [
        PS / "validation-plan/sim-kit/common/options.inc",
        PS / "validation-results/07-conducted-emi/round3/scripts/emi_topology.cir",
        PS / "validation-results/07-conducted-emi/round3/scripts/fit_choke.py",
        PS / "validation-results/07-conducted-emi/round3/outputs/tdk_choke_fit.json",
        HERE.parents[1] / "scripts/mesh25d_hybrid.py",
        HERE.parents[1] / "scripts/leg_region_diff.py",
    ]
    inputs += [HERE.parent / "D22-emi-filter.md", HERE.parent / "README.md"]
    inputs += [
        HERE.parents[1] / "d2/run_d2.py",
        HERE.parents[1] / "d2/legA-h0-best.matrix.txt",
        PS / "validation-plan/sim-kit/common/run_ngspice.py",
    ]
    for tag in (
        "v170-r2-e1.06-f35000-s0.5-c24",
        "v170-r2-e1.06-f60000-s2-c48",
        "v170-r2-e1.06-f60000-s0.5-c48",
    ):
        inputs += [
            HERE.parent / "out-D19/periodic-runs" / (tag + suffix)
            for suffix in (".json", "-fft.npz", ".raw.gz")
        ]

    changed = subprocess.check_output(
        ["git", "diff", "--name-only", BASE], cwd=ROOT, text=True
    ).splitlines()
    allowed = str(HERE.relative_to(ROOT)) + "/"
    if any(not name.startswith(allowed) for name in changed):
        raise ValueError("tracked change outside D-22 output")
    for path in inputs:
        original = subprocess.check_output(
            ["git", "show", f"{BASE}:{path.relative_to(ROOT)}"], cwd=ROOT
        )
        if hashlib.sha256(original).hexdigest() != digest(path):
            raise ValueError(f"input differs from required base: {path}")
    attempts = json.loads((HERE / "attempts.json").read_text())
    recorded_cases = {row["case"] for row in attempts if row["outcome"] != "pending"}
    replayed = set(json.loads((HERE / "replay-results.json").read_text())["completed_raw_captures_replayed"])
    expected_replay = {
        "periodic-runs/" + row["case"] for row in attempts
        if row["outcome"] in ("complete", "not_settled")
    }
    if replayed != expected_replay:
        raise ValueError("attempt ledger and raw replay describe different snapshots; refresh analysis")
    outputs = {
        str(p.relative_to(HERE)): digest(p)
        for p in sorted(HERE.rglob("*"))
        if p.is_file()
        and p.name not in ("provenance.json", "provenance.log")
        and not (
            p.parent == HERE
            and p.name in ("envelope-0.125.log", "anchor-0.0625.log", "targeted-refinement.log", "additional-refinement.log", "fine-refinement.log", "recovery-refinement.log", "weak-refinement.log", "retry-refinement.log", "last-refinement.log", "closing-refinement.log", "terminal-refinement.log", "final-light-refinement.log")
            and not (HERE / (p.stem + "-results.json")).exists()
        )
        and not (
            p.relative_to(HERE).parts[0] == "periodic-runs"
            and p.relative_to(HERE).parts[1] not in recorded_cases
        )
        and not any(
            part.startswith(".") or part == "__pycache__" for part in p.relative_to(HERE).parts
        )
    }
    if any(name.endswith(".lib") for name in outputs):
        raise ValueError("vendor library in output tree")
    report = {
        "base_revision": BASE,
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True
        ).strip(),
        "authored_by": "GPT-6 / OpenAI",
        "recorded_UTC": datetime.now(UTC).isoformat(),
        "runtime": {
            "python": sys.version,
            "numpy": np.__version__,
            "platform": platform.platform(),
            "ngspice": subprocess.check_output(["/opt/homebrew/bin/ngspice", "-v"], text=True),
        },
        "licensed_model_SHA256_only": digest(
            PS / "validation-plan/sim-kit/models/vendor/IFX_CFD7_650V.lib"
        ),
        "inputs": {str(p.relative_to(ROOT)): digest(p) for p in inputs},
        "outputs": outputs,
        "scope": "Inputs match the committed base; authored and generated output is confined to out-D22. No compliance or universal numerical-error bound is implied.",
    }
    target.write_text(json.dumps(report, indent=2) + "\n")
    print(len(inputs), "inputs;", len(outputs), "outputs recorded")


if __name__ == "__main__":
    main()

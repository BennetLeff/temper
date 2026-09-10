"""P1 U4 independent final native check (run-local apparatus).

Runs the full final check on a saved board three times with complete reports:
  * native measurement (protected-state identity),
  * ``kicad-cli pcb drc`` with ``--all-track-errors --schematic-parity
    --severity-all`` (the block host omits ``--schematic-parity``; the plan's
    verification contract requires it, so it is added here),
  * ``kicad-cli sch erc`` with ``--severity-all``,
  * the block Rust judge over (measurement, sealed contract, DRC).

Every run writes its own complete JSON reports; the summary records stability
across the three runs.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

RUN = Path(__file__).resolve().parent
HARNESS = RUN.parent.parent
sys.path.insert(0, str(RUN))
sys.path.insert(0, str(HARNESS))

import harness  # noqa: E402
import runlib  # noqa: E402

KICAD_CLI = "kicad-cli"


def _kicad_env(config: Path) -> dict[str, str]:
    config.mkdir(parents=True, exist_ok=True)
    (config / "kicad_common.json").write_text('{"environment":{"vars":{}}}\n')
    (config / "kicad_advanced").write_text("MaximumThreads=1\n")
    return {**os.environ, "KICAD_CONFIG_HOME": str(config)}


def _run(argv: list[str], env: dict[str, str], timeout: float = 120.0) -> dict:
    completed = subprocess.run(
        argv, capture_output=True, text=True, timeout=timeout, check=False, env=env
    )
    return {
        "argv": argv,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def assemble(trial: Path, candidate: Path, destination: Path) -> None:
    """Board named candidate.kicad_pcb plus the schematic/project/library
    context schematic-parity and ERC need."""
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(trial / "candidate.kicad_pcb", destination / "candidate.kicad_pcb")
    shutil.copyfile(trial / "candidate.kicad_dru", destination / "candidate.kicad_dru")
    shutil.copyfile(trial / "source.json", destination / "source.json")
    shutil.copyfile(candidate / "mcu_candidate.kicad_sch", destination / "candidate.kicad_sch")
    shutil.copyfile(candidate / "mcu.kicad_sch", destination / "mcu.kicad_sch")
    shutil.copyfile(candidate / "mcu_candidate.kicad_pro", destination / "candidate.kicad_pro")
    shutil.copyfile(candidate / "fp-lib-table", destination / "fp-lib-table")
    shutil.copytree(candidate / "candidate-libs", destination / "candidate-libs")


def one_run(work: Path, contract: dict, index: int) -> dict:
    out = work / f"run-{index}"
    out.mkdir(parents=True, exist_ok=False)
    board = work / "check" / "candidate.kicad_pcb"
    env = _kicad_env(out / "kicad-config")

    # Native measurement (protected state) via the block adapter.
    measure_proc = _run(
        [
            harness.KICAD_PYTHON,
            str(RUN.parent.parent / "block_native.py"),
            "measure",
            str(board),
        ],
        env,
        timeout=60.0,
    )
    (out / "measure-command.json").write_text(json.dumps(measure_proc, indent=2) + "\n")
    if measure_proc["returncode"] != 0:
        raise RuntimeError("native measure failed")
    measurement = json.loads(measure_proc["stdout"])
    (out / "measurement.json").write_text(json.dumps(measurement, indent=2) + "\n")

    # DRC with schematic parity and all severities.
    drc_proc = _run(
        [
            KICAD_CLI,
            "pcb",
            "drc",
            "--format",
            "json",
            "--all-track-errors",
            "--schematic-parity",
            "--severity-all",
            "--output",
            str(out / "drc.json"),
            str(board),
        ],
        env,
    )
    (out / "drc-command.json").write_text(json.dumps(drc_proc, indent=2) + "\n")
    drc = json.loads((out / "drc.json").read_text()) if (out / "drc.json").is_file() else None

    # ERC with all severities.
    erc_proc = _run(
        [
            KICAD_CLI,
            "sch",
            "erc",
            "--format",
            "json",
            "--severity-all",
            "--output",
            str(out / "erc.json"),
            str(work / "check" / "candidate.kicad_sch"),
        ],
        env,
    )
    (out / "erc-command.json").write_text(json.dumps(erc_proc, indent=2) + "\n")
    erc = json.loads((out / "erc.json").read_text()) if (out / "erc.json").is_file() else None
    if erc is not None:
        erc["violations"] = [
            v for sheet in erc.get("sheets", []) for v in sheet.get("violations", [])
        ]

    # Rust judge (block profile) over measurement + sealed contract + DRC.
    judged = None
    if drc is not None:
        completed = subprocess.run(
            [str(harness.JUDGE)],
            input=json.dumps({"measurement": measurement, "contract": contract, "drc": drc}),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        (out / "judge-command.json").write_text(
            json.dumps(
                {
                    "returncode": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                },
                indent=2,
            )
            + "\n"
        )
        judged = json.loads(completed.stdout)

    summary = {
        "run": index,
        "measurement_protected_sha256": measurement["protected_sha256"],
        "measurement_board_sha256": measurement["board_sha256"],
        "drc_returncode": drc_proc["returncode"],
        "drc_violations": len(drc["violations"]) if drc else None,
        "drc_unconnected": len(drc["unconnected_items"]) if drc else None,
        "drc_parity": len(drc.get("schematic_parity", [])) if drc else None,
        "erc_returncode": erc_proc["returncode"],
        "erc_violations": len(erc["violations"]) if erc else None,
        "judge_status": judged.get("status") if judged else None,
        "judge_findings": len(judged.get("findings", [])) if judged else None,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trial", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    if args.out.exists():
        shutil.rmtree(args.out)
    contract = json.loads((args.trial / "task-contract.json").read_text())
    check_dir = args.out / "check"
    assemble(args.trial, args.candidate, check_dir)
    summaries = []
    for index in range(1, args.runs + 1):
        summaries.append(one_run(args.out, contract, index))
    stable = all(
        (s["judge_status"], s["drc_violations"], s["drc_parity"], s["erc_violations"])
        == (
            summaries[0]["judge_status"],
            summaries[0]["drc_violations"],
            summaries[0]["drc_parity"],
            summaries[0]["erc_violations"],
        )
        for s in summaries
    )
    report = {
        "schema": "temper.mcu-native-check.v1",
        "runs": summaries,
        "stable_across_runs": stable,
    }
    runlib.write_json(args.out / "summary.json", report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()

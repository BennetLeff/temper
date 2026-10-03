#!/usr/bin/env python3
"""Independently reparse retained logs and fail closed on incomplete evidence."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from investigate import OPTIONS, R17
from summarize import compare, original_baseline

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[6]
MEAS = re.compile(r"^\s*([a-z_][a-z0-9_]*)\s*=\s*([-+0-9.eE]+)", re.I)
ABORT = re.compile(r"Timestep too small|simulation\(s\) aborted|singular matrix|fatal error", re.I)
REQUIRED = {
    "vds_ls_die_pk",
    "vds_hs_die_pk",
    "vgs_ls_die_max",
    "vgs_ls_die_min",
    "vgs_hs_die_max",
    "vgs_hs_die_min",
    "vgs_ls_off_max",
    "vgs_hs_off_max",
    "vds_ls_at_on",
    "vds_hs_at_on",
    "vgs_ls_at_partner",
    "vgs_hs_at_partner",
    "end_time",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_complete(row: dict, log: str) -> bool:
    """Check raw termination, parse every measurement, and require the endpoint."""
    measured = {}
    for line in log.splitlines():
        match = MEAS.match(line)
        if match:
            measured[match[1].lower()] = float(match[2])
    if measured != row["meas"]:
        raise AssertionError(f"Parsed measurements disagree with saved record: {row['name']}")
    endpoint = 2e-6 + float(row["params"]["DT"].removesuffix("n")) * 1e-9 + 0.8e-6
    failed_meas = any(
        "failed" in line.lower() and "meas" in line.lower() for line in log.splitlines()
    )
    return (
        row["returncode"] == 0
        and not row["aborted"]
        and not ABORT.search(log)
        and not failed_meas
        and not row["failed"]
        and REQUIRED <= measured.keys()
        and abs(measured.get("end_time", 0) - endpoint) < 1e-11
    )


def check_campaign(
    label: str, steps: tuple[str, ...] | None = None, *, require_complete: bool = True
) -> dict:
    manifest = json.loads((HERE / f"manifest-{label}.json").read_text())
    rows = json.loads((HERE / f"{label}.json").read_text())
    expected = {
        (c["name"], o, s)
        for c in manifest["cases"]
        for o in manifest["options"]
        for s in (steps or (c["params"]["TRMAX"],))
    }
    actual = {(r["name"], r["option"], r["params"]["TRMAX"]) for r in rows}
    assert len(actual) == len(rows) == manifest["jobs"] and actual == expected, (
        f"Incomplete or duplicated campaign: {label}"
    )
    for row in rows:
        work = HERE / "raw" / f"{row['name']}_{row['option']}_step{row['params']['TRMAX']}"
        retained = json.loads((work / "result.json").read_text())
        assert row == retained, f"Summary/raw mismatch: {work}"
        complete = bool(is_complete(row, (work / "run.log").read_text()))
        assert complete == row["complete"], f"False campaign completion: {work}"
        assert complete or not require_complete, f"Unqualified final case: {work}"
    return {
        "rows": len(rows),
        "all_complete": all(r["complete"] for r in rows),
        "identity_inventory_matches": True,
    }


def main() -> None:
    original = json.loads((HERE / "original-recorder-provenance.json").read_text())
    inputs = (
        json.loads((HERE / "source-inputs.json").read_text())["sha256"] | original["dependencies"]
    )
    for name, expected in inputs.items():
        assert sha(REPO / name) == expected, f"Changed measurement input: {name}"
    for path in HERE.glob("manifest-*.json"):
        expected = json.loads(path.read_text())["script_sha256"]
        assert sha(HERE / "recorder-snapshots" / f"{expected}.py.txt") == expected, (
            f"Recorder snapshot missing/changed: {path}"
        )
    binary = json.loads((HERE / "simulator-executable.json").read_text())
    assert sha(Path(binary["path_invoked_by_common_runner"])) == binary["sha256"]
    checked = 0
    failures = 0
    example = None
    for path in (HERE / "raw").glob("*/result.json"):
        row = json.loads(path.read_text())
        source = R17 / row["deck"]
        assert sha(source) == row["identity"]["source_deck"]
        assert row["identity"]["params"] == row["params"]
        assert row["identity"]["options"] == OPTIONS[row["option"]]
        expected_deck = source.read_text().replace(
            ".end\n", OPTIONS[row["option"]] + "\n.meas tran end_time MAX time\n.end\n"
        )
        generated = (path.parent / "case.cir").read_text()
        normalized = re.sub(
            r"(?m)^\.include .*/common/options\.inc$", ".include ../common/options.inc", generated
        )
        assert normalized == expected_deck, (
            f"Generated deck differs from frozen input/options: {path}"
        )
        expected_params = "".join(f".param {key}={value}\n" for key, value in row["params"].items())
        assert (path.parent / "params.inc").read_text() == expected_params
        assert (
            path.parent / ".spiceinit"
        ).read_text() == "set ngbehavior=psa\nset filetype=ascii\n"
        log = (path.parent / "run.log").read_text()
        complete = bool(is_complete(row, log))
        assert complete == row["complete"], f"False completion classification: {path}"
        checked += 1
        failures += not complete
        if complete and example is None:
            example = (row, log)
    assert example is not None
    # Real-record perturbations: an abort, nonzero native return code, a missing
    # metric or a truncated endpoint must never be accepted as a complete run.
    row, log = example
    assert not is_complete(row, log + "\nTimestep too small\n")
    assert not is_complete(dict(row, returncode=1), log)
    missing = dict(row, meas={k: v for k, v in row["meas"].items() if k != "end_time"})
    assert not is_complete(
        missing,
        "\n".join(line for line in log.splitlines() if not line.lstrip().startswith("end_time")),
    )
    short = dict(row, meas=dict(row["meas"], end_time=1e-6))
    short_log = re.sub(r"(^\s*end_time\s*=\s*)[-+0-9.eE]+", r"\g<1>1e-6", log, flags=re.M)
    assert not is_complete(short, short_log)
    result = {
        "original_inputs_verified": len(inputs),
        "raw_records_reparsed": checked,
        "retained_incomplete_records": failures,
        "abort_nonzero_missing_and_truncated_mutations_rejected": True,
        "qualification": check_campaign("qualify-itl100k"),
        "convergence": check_campaign("convergence-itl100k", ("0.2n", "0.1n", "0.05n")),
        "boundary_probe": check_campaign("boundary-probe-itl100k", ("0.025n",)),
    }
    old = original_baseline()
    if (HERE / "original-reproduction.json").exists():
        result["fresh_baseline"] = check_campaign("original-reproduction", require_complete=False)
    for row in old.values():
        work = HERE / "raw" / f"{row['name']}_old_step{row['params']['TRMAX']}"
        assert row == json.loads((work / "result.json").read_text()), (
            f"Baseline summary/raw mismatch: {work}"
        )
        assert bool(is_complete(row, (work / "run.log").read_text())) == row["complete"]
    proposed = json.loads((HERE / "qualify-itl100k.json").read_text())
    comparable = [r for r in proposed if old[r["name"]]["complete"]]
    assert len(comparable) == 221
    assert all(r["meas"] == old[r["name"]]["meas"] for r in comparable)
    result["same_step_all_printed_measurements_identical"] = len(comparable)
    result["original_aborts_recovered"] = len(proposed) - len(comparable)
    convergence = json.loads((HERE / "convergence-itl100k.json").read_text())
    indexed = {(r["name"], r["params"]["TRMAX"]): r for r in convergence}
    fine = [
        compare(r, indexed[(r["name"], "0.05n")])
        for r in convergence
        if r["params"]["TRMAX"] == "0.1n"
    ]
    assert len(fine) == 200
    result["fine_interval_pairs"] = len(fine)
    result["fine_interval_outside_tolerance"] = sum(not r["within_tolerance"] for r in fine)
    result["fine_interval_classification_changes"] = sum(bool(r["verdict_changes"]) for r in fine)
    decision = [r for r in fine if r["group"] == "decision"]
    assert len(decision) == 192
    assert all(r["within_tolerance"] and not r["verdict_changes"] for r in decision)
    result["decision_fine_interval_tolerance_and_verdict_passes"] = len(decision)
    (HERE / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

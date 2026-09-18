#!/usr/bin/env python3
"""Emit the AR-COORD checker receipt and manifest from the retained bytes.

Run after every other artifact exists. manifest.json hashes every file produced
by this attempt except itself and the delivered dispatch.json.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ATTEMPT = Path(__file__).resolve().parent.parent
CHECKER = ATTEMPT / "raw" / "checker"

BINARIES = {
    "zapote-claims": "/Users/bennet/Desktop/temper/target-shared/debug/zapote-claims",
    "zapote-fault-loop": "/Users/bennet/Desktop/temper/target-shared/debug/zapote-fault-loop",
}


def sha_bytes(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def exit_code(name: str) -> int:
    text = (CHECKER / name).read_text().strip()
    return int(text.split("=")[-1])


RECEIPT = {
    "schema": "pfc-campaign-AR-COORD-checker-receipt/v1",
    "task_id": "AR-COORD",
    "attempt_id": "attempt-001",
    "campaign_id": "2026-09-17-pfc-campaign",
    "scope_disclaimer": "A clean run means NO VIOLATIONS DETECTED BY THE IMPLEMENTED CHECKS. It does not establish derivation soundness in general, does not establish that any claim is true, and is not physical evidence.",
    "binaries": {k: {"path": v, "sha256": sha_bytes(Path(v))} for k, v in BINARIES.items()},
    "checker_status": "RUN",
    "counted_as_validated_run": False,
    "counted_reason": "dispatch declared checker_revision_and_sha256 'not_applicable: G0 checker unimplemented, so per ADMISSION.md this attempt will not be counted as a validated run'",
    "runs": [
        {
            "check": "evidence ledger",
            "command": f"{BINARIES['zapote-claims']} claims.json",
            "exit_code": exit_code("exit_claims.txt"),
            "stdout_file": "raw/checker/out_claims.txt",
            "stdout": (CHECKER / "out_claims.txt").read_text().strip(),
            "role": "required pass",
        },
        {
            "check": "evidence ledger (negative control: bound reversal / min->max restatement)",
            "command": f"{BINARIES['zapote-claims']} raw/checker/negative_control_bound_reversal.json",
            "exit_code": exit_code("exit_claims_negative_control.txt"),
            "stdout_file": "raw/checker/out_claims_negative_control.txt",
            "stdout": (CHECKER / "out_claims_negative_control.txt").read_text().strip(),
            "role": "negative control; retained as the checker's teeth, not a model of this attempt",
        },
        {
            "check": "fault loop (representative envelope discharge: U10/U9 and bank caps)",
            "command": "python3 zapote/tools/check_fault_loop.py --netlist raw/evidence/netlist_fault_loop.json --loop-nets PFC_BUS_PLUS_390V,PFC_BUS_MINUS,a1 --assignments raw/assignments_envelope_representative.json",
            "exit_code": exit_code("exit_fault_loop_representative.txt"),
            "stdout_file": "raw/checker/out_fault_loop_representative.txt",
            "stdout": (CHECKER / "out_fault_loop_representative.txt").read_text().strip(),
            "role": "required pass (connectivity only)",
        },
        {
            "check": "fault loop (negative control: current assigned to the out-of-loop shunt U12)",
            "command": "python3 zapote/tools/check_fault_loop.py --netlist raw/evidence/netlist_fault_loop.json --loop-nets PFC_BUS_PLUS_390V,PFC_BUS_MINUS,a1 --assignments raw/assignments_negative_control_u12.json",
            "exit_code": exit_code("exit_fault_loop_negative_control.txt"),
            "stdout_file": "raw/checker/out_fault_loop_negative_control.txt",
            "stdout": (CHECKER / "out_fault_loop_negative_control.txt").read_text().strip(),
            "role": "negative control; retained as the checker's teeth",
        },
    ],
    "claims_json_sha256": sha_bytes(ATTEMPT / "claims.json"),
}

(CHECKER / "checker_receipt.json").write_text(json.dumps(RECEIPT, indent=2) + "\n")

# --- manifest ---------------------------------------------------------------
files = []
for p in sorted(ATTEMPT.rglob("*")):
    if not p.is_file():
        continue
    rel = p.relative_to(ATTEMPT).as_posix()
    if rel in {"manifest.json", "dispatch.json"}:
        continue
    files.append({"path": rel, "sha256": sha_bytes(p), "bytes": p.stat().st_size})

manifest = {
    "schema": "pfc-campaign-manifest/v1",
    "task_id": "AR-COORD",
    "attempt_id": "attempt-001",
    "campaign_id": "2026-09-17-pfc-campaign",
    "algorithm": "sha256",
    "note": "SHA-256 of every file produced by this attempt except manifest.json itself and dispatch.json (the delivered input).",
    "files": files,
}
(ATTEMPT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(f"wrote checker_receipt.json and manifest.json ({len(files)} files)")

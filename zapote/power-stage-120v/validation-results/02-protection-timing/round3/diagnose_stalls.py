#!/usr/bin/env python3
"""Diagnose original CT transmission-line stalls, changing one item per run."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parents[2] / "validation-plan/sim-kit"
DECK = (KIT / "02-chain/ct_frontend.cir").read_text()
CASES = ((33000, 37, 1e7, -0.004, 45e-9),
         (33000, 10, 1e6, 0.0, 55e-9),
         (39000, 37, 1e6, -0.004, 45e-9))


def run_case(case: tuple[int, int, float, float, float], stage: str) -> dict:
    freq, i0, slope, vos, tpd = case
    deck = DECK.replace("../common/", str(KIT / "common") + "/")
    if stage == "smooth_cap":
        # Smooth minimum, ~0.002 A from the hard cap 10 A below its knee.
        deck = deck.replace("min(I0+SLOPE*time,150)",
                            "(I0+SLOPE*time+150-sqrt((I0+SLOPE*time-150)^2+1))/2")
    elif stage == "half_step":
        deck = deck.replace(".tran 5n {TSTOP} 0 5n", ".tran 2.5n {TSTOP} 0 2.5n")
    elif stage == "wider_tanh":
        deck = deck.replace("/1m)", "/5m)")
    elif stage != "baseline":
        raise ValueError(stage)
    params = (f".param FREQ={freq} I0={i0} SLOPE={slope:.12g} "
              f"VOS={vos:.12g} TPD={tpd:.12g}\n")
    label = f"{stage}-f{freq}-i{i0}-s{slope:g}"
    with tempfile.TemporaryDirectory(prefix="ps-ct-diagnose-") as tmp:
        wd = Path(tmp)
        (wd / "ct.cir").write_text(deck)
        (wd / "params.inc").write_text(params)
        (wd / ".spiceinit").write_text("set ngbehavior=psa\nset filetype=ascii\n")
        started = time.monotonic()
        try:
            result = subprocess.run(["/opt/homebrew/bin/ngspice", "-b", "ct.cir"],
                                    cwd=wd, capture_output=True, text=True,
                                    timeout=15, check=False)
            log = result.stdout + "\n" + result.stderr
            status = "complete" if result.returncode == 0 and not re.search(
                "timestep too small|aborted|singular matrix|fatal error", log, re.I) else "failed"
            exit_code = result.returncode
        except subprocess.TimeoutExpired as exc:
            log = ((exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes)
                   else (exc.stdout or ""))
            log += ((exc.stderr or b"").decode(errors="replace") if isinstance(exc.stderr, bytes)
                    else (exc.stderr or ""))
            status, exit_code = "timeout", None
    log_path = HERE / "outputs" / "stall_logs" / f"{label}.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(log)
    refs = re.findall(r"Reference value\s*:\s*([\deE+.-]+)", log)
    return {"case": case, "stage": stage, "status": status, "exit_code": exit_code,
            "elapsed_s": round(time.monotonic() - started, 3),
            "last_reference_time_s": float(refs[-1]) if refs else None,
            "reference_lines": len(refs), "log": str(log_path.relative_to(HERE)),
            "log_sha256": hashlib.sha256(log.encode()).hexdigest(),
            "deck_sha256": hashlib.sha256(deck.encode()).hexdigest()}


def main() -> None:
    rows = []
    for case in CASES:
        for stage in ("baseline", "smooth_cap", "half_step", "wider_tanh"):
            row = run_case(case, stage)
            rows.append(row)
            print(row["case"][:3], stage, row["status"], row["last_reference_time_s"], flush=True)
            (HERE / "outputs/stall_diagnosis.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()

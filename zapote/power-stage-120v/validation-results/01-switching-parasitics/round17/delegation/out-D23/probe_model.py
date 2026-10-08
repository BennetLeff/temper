"""Bounded compatibility probe. Exit 2 means INDETERMINATE, never a pass.

Default: low-input-start fixture; --first: original high-input-start fixture.
No vendor model modifications; downloads are hash-checked before invocation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED = {
    "ucc21550-q1.lib": "4355b47c5ee17cd416075f86f3b80e76b013125f9539fe9ac04b077136ea2b22",
    "IFX_CFD7_650V.lib": "02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b",
}


def run_probe(name: str, text: str, seconds: int = 60) -> dict:
    for model, expected in EXPECTED.items():
        actual = hashlib.sha256((HERE / "vendor" / model).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Model hash mismatch: {model}")
    work = HERE / "runs" / name
    work.mkdir(parents=True, exist_ok=True)
    (work / "probe.cir").write_text(text)
    (work / "params.inc").write_text(".param RDT=50k\n")
    (work / ".spiceinit").write_text("set ngbehavior=psa\n")
    result: dict[str, object]
    try:
        proc = subprocess.run(["/opt/homebrew/bin/ngspice", "-b", "probe.cir"], cwd=work,
                              capture_output=True, text=True, timeout=seconds)
        output = proc.stdout + proc.stderr
        required = ("t_end", "deadtime")
        meas = {k: float(v) for k, v in re.findall(
            r"^\s*([a-z_]+)\s*=\s*([-+0-9.eE]+)", output, re.M)}
        completed = (proc.returncode == 0 and all(k in meas for k in required)
                     and meas["t_end"] >= (24e-6 if name == "fixture-first-replay" else 4e-6)
                     and not re.search(r"aborted|timestep too small|fatal error", output, re.I))
        result = {"status": "completed" if completed else "INDETERMINATE",
                  "returncode": proc.returncode, "meas": meas}
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or b"").decode() + (exc.stderr or b"").decode()
        result = {"status": "INDETERMINATE", "reason": "timeout", "timeout_seconds": seconds}
    (work / "run.log").write_text(output)
    result["deck_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    result["vendor_hashes"] = EXPECTED
    (work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(name, result, flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", action="store_true")
    args = parser.parse_args()
    # Both inputs start low, matching TI's shipped testbench's initial input state.
    # This is our capacitive fixture, not a claim of reproducing TI's entire testbench.
    text = """* TI UCC21550B-Q1 unchanged model compatibility fixture
.include ../../vendor/ucc21550-q1.lib
Vcc vcc 0 3.3
Vdda vdda 0 12
Vddb vddb 0 12
Va ina 0 PWL(0 0 1u 0 1.001u 3.3 2u 3.3 2.001u 0)
Vb inb 0 PWL(0 0 2.2u 0 2.201u 3.3)
Rdt dt 0 50k
Xdrv ina inb vcc 0 0 dt vdda outa 0 vddb outb 0 UCC21550-Q1
Ca outa 0 1.8n
Cb outb 0 1.8n
.options method=gear reltol=1e-3 abstol=1e-9 vntol=1e-6 itl1=500 itl4=200
.tran 0.1n 4u 0 0.1n
.meas tran t_end FIND time AT=4u
.meas tran deadtime TRIG v(outa) VAL=10.8 FALL=1 TARG v(outb) VAL=1.2 RISE=1
.end
"""
    name = "fixture-low-start"
    if args.first:
        name = "fixture-first-replay"
        text = (HERE / "driver_fixture.cir").read_text()
    result = run_probe(name, text)
    raise SystemExit(0 if result["status"] == "completed" else 2)

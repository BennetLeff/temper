#!/usr/bin/env python3
"""Run one ngspice deck with parameters and return its .meas results as JSON.

    python3 common/run_ngspice.py <deck.cir> [NAME=VALUE ...] [--keep DIR] [--raw]

- Copies the deck into a fresh run directory, writes params.inc with one
  `.param NAME=VALUE` per argument, and writes .spiceinit with
  `set ngbehavior=psa` (PSpice compatibility; the Infineon library needs it).
- Decks include "params.inc", "../common/options.inc" style paths are
  rewritten to absolute paths, and models/vendor/IFX_CFD7_650V.lib is
  available as "IFX_CFD7_650V.lib".
- Prints {"params": ..., "meas": {name: value}, "failed": [...], "log_tail": ...,
  "returncode": ..., "raw_returncode": ...}. Full logs are in <run dir>/run.log
  (and raw_run.log). Before using any result, also check that every .meas you
  need is present and that the waveform covers the whole .tran window.
  A .meas that ngspice could not evaluate is listed in "failed". An aborted run
  (for example "Timestep too small") sets "aborted": true; treat that as a
  failed run, never as a result.
- --raw also saves every waveform to <run dir>/waves.raw (ASCII rawfile) by
  running the deck a second time (ngspice disables .meas when -r is set).
  Load it with read_raw() from this module: {vector name: list of floats},
  e.g. waves["v(sw)"], waves["time"].
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
VENDOR = KIT / "models" / "vendor" / "IFX_CFD7_650V.lib"
MEAS = re.compile(r"^\s*([a-z_][a-z0-9_]*)\s*=\s*([-+0-9.eE]+)", re.I)


def run(deck: Path, params: dict[str, str], keep: Path | None = None, raw: bool = False) -> dict:
    work = Path(keep) if keep else Path(tempfile.mkdtemp(prefix="simkit-"))
    work.mkdir(parents=True, exist_ok=True)
    text = deck.read_text()
    text = text.replace("../common/", str(KIT / "common") + "/")
    (work / deck.name).write_text(text)
    (work / "params.inc").write_text("".join(f".param {k}={v}\n" for k, v in params.items()))
    (work / ".spiceinit").write_text("set ngbehavior=psa\nset filetype=ascii\n")
    if VENDOR.is_file():
        shutil.copy(VENDOR, work / VENDOR.name)
    # ngspice refuses .meas in batch mode when -r is set, so waveforms are a
    # second run of the same deck.
    proc = subprocess.run(["ngspice", "-b", deck.name], cwd=work, capture_output=True, text=True, timeout=1800)
    out = proc.stdout + proc.stderr
    raw_rc = None
    if raw:
        rproc = subprocess.run(["ngspice", "-b", "-r", "waves.raw", deck.name], cwd=work,
                               capture_output=True, text=True, timeout=1800)
        raw_rc = rproc.returncode
        (work / "raw_run.log").write_text(rproc.stdout + rproc.stderr)
    meas, failed = {}, []
    for line in out.splitlines():
        m = MEAS.match(line)
        if m and not line.strip().startswith(("Reference", "Note")):
            try:
                meas[m.group(1).lower()] = float(m.group(2))
            except ValueError:
                pass
        if "failed" in line.lower() and "meas" in line.lower():
            failed.append(line.strip())
    (work / "run.log").write_text(out)
    aborted = bool(re.search(r"Timestep too small|simulation\(s\) aborted|singular matrix|fatal error", out, re.I))
    # A nonzero exit or a failed waveform run also counts as aborted.
    aborted = aborted or proc.returncode != 0 or (raw and (raw_rc != 0 or not (work / "waves.raw").is_file()))
    return {"deck": str(deck), "params": params, "run_dir": str(work), "aborted": aborted,
            "returncode": proc.returncode, "raw_returncode": raw_rc,
            "meas": meas, "failed": failed, "log_tail": out.splitlines()[-6:]}


def read_raw(path: str | Path) -> dict[str, list[float]]:
    """Parse an ngspice ASCII rawfile (first plot) into {vector name: values}.

    Transient values are floats; AC values are complex (use abs() for magnitude).
    """
    lines = Path(path).read_text().splitlines()
    names, i = [], 0
    nvars = npoints = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("No. Variables:"):
            nvars = int(line.split(":")[1])
        elif line.startswith("No. Points:"):
            npoints = int(line.split(":")[1])
        elif line.startswith("Variables:"):
            for j in range(nvars):
                names.append(lines[i + 1 + j].split()[1].lower())
            i += nvars
        elif line.startswith("Values:"):
            i += 1
            break
        i += 1
    data = {n: [] for n in names}
    tokens = " ".join(lines[i:]).split()
    k = 0
    for _ in range(npoints):
        k += 1                       # point index
        for n in names:
            tok = tokens[k]
            if "," in tok:                       # AC analysis: complex "re,im"
                re_, im_ = tok.split(",")
                data[n].append(complex(float(re_), float(im_)))
            else:
                data[n].append(float(tok))
            k += 1
    return data


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    deck = Path(args.pop(0)).resolve()
    keep = None
    raw = "--raw" in args
    args = [a for a in args if a != "--raw"]
    if "--keep" in args:
        i = args.index("--keep")
        keep = Path(args[i + 1])
        del args[i:i + 2]
    params = dict(a.split("=", 1) for a in args)
    print(json.dumps(run(deck, params, keep, raw), indent=1))


if __name__ == "__main__":
    main()

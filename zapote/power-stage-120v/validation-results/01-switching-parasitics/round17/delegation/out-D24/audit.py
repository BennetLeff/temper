#!/usr/bin/env python3
"""Recompute D24 transition metrics and compare unmodified-model references."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
R17 = HERE.parents[1]


def crossing(
    t: np.ndarray, current: np.ndarray, level: float, start: int, up: bool
) -> tuple[float, int]:
    for k in range(start, len(t) - 1):
        if (current[k] < level <= current[k + 1]) if up else (current[k] > level >= current[k + 1]):
            return float(
                t[k] + (level - current[k]) * (t[k + 1] - t[k]) / (current[k + 1] - current[k])
            ), k + 1
    raise ValueError("required crossing absent")


def main() -> None:
    rows = [json.loads(p.read_text()) for p in sorted((HERE / "results").glob("*/result.json"))]
    if not rows:
        raise ValueError("no results")
    cold = [
        json.loads(s)
        for s in (R17 / "d2/results/grid-best-longdt/results.jsonl").read_text().splitlines()
    ]
    hot = json.loads((R17 / "delegation/out-D13/results-main.json").read_text())
    comparisons, checks = [], []
    for r in rows:
        ident = r["identity"]
        if r["status"] == "INDETERMINATE":
            continue
        if r["aborted"] or r["returncode"] != 0 or r["raw_returncode"] != 0 or r["failed_measures"]:
            raise ValueError(f"invalid completed case {r['tag']}")
        with gzip.open(HERE / "results" / r["tag"] / "waves.csv.gz", "rt") as fh:
            names = fh.readline().strip().split(",")
            values = np.loadtxt(fh, delimiter=",")
        w = dict(zip(names, values.T, strict=True))
        t = w["time"]
        if not np.isfinite(values).all() or not np.all(np.diff(t) > 0):
            raise ValueError(f"nonfinite/unordered waveform {r['tag']}")
        p = ident["params"]
        if ident["kind"] == "s4":
            end = 2e-6 + 443e-9 + 0.75e-6
            vmask = (t >= 2e-6) & (t <= end)
            gmask = (t >= 2e-6 + 443e-9) & (t <= end)
            off = "l" if p["DIR"] == "0" else "h"
            vds = max(
                float((w[f"v(xq{s}.dd)"] - w[f"v(xq{s}.s)"])[vmask].max()) for s in ("l", "h")
            )
            gate = float((w[f"v(xq{off}.g)"] - w[f"v(xq{off}.s)"])[gmask].max())
            if abs(vds - r["vds_pk_V"]) > 0.0001 or abs(gate - r["vgs_off_max_V"]) > 0.000001:
                raise ValueError(f"waveform/measurement mismatch {r['tag']}")
            if abs(t[-1] - 3.243e-6) > 1e-12:
                raise ValueError("incomplete S4 waveform")
            if r["status"] != ("PASS" if vds <= 520 and gate < 1.9 else "FAIL"):
                raise ValueError("incorrect verdict")
            if ident["tt_ns"] == 50 and ident["step_ns"] == 0.2:
                refs = []
                if p["TJ"] == "27":
                    refs += [
                        (x, "grid-best-longdt", x["vds_pk"], x["vgs_off_max"])
                        for x in cold
                        if x["case"] == "S4"
                        and x["dt_ns"] == 443
                        and x["vbus"] == int(p["VBUS"])
                        and x["dir"] == int(p["DIR"])
                        and x["esl_nH"] == float(p["LESL"][:-1])
                    ]
                refs += [
                    (x, "D13", x["vds_V"], x["off_V"])
                    for x in hot
                    if x["status"] == "complete"
                    and x["case"] == "S4"
                    and x["dt_ns"] == 443
                    and x["variant"] == "baseline"
                    and x["temp_C"] == int(p["TJ"])
                    and x["vbus"] == int(p["VBUS"])
                    and x["dir"] == int(p["DIR"])
                    and x["esl_nH"] == float(p["LESL"][:-1])
                ]
                for _, source, vd, vg in refs:
                    delta_vds = r["vds_pk_V"] - vd
                    delta_gate = r["vgs_off_max_V"] - vg
                    comparisons.append(
                        {
                            "tag": r["tag"],
                            "source": source,
                            "delta_vds_V": delta_vds,
                            "delta_gate_V": delta_gate,
                        }
                    )
                    if abs(delta_vds) > 0.001 or abs(delta_gate) > 0.00001:
                        raise ValueError(f"baseline mismatch {r['tag']} {source}")
        else:
            c = w["i(vprobe)"]
            zero, k = crossing(t, c, 0, 0, True)
            peak = k + int(np.argmax(c[k:]))
            end, e = crossing(t, c, 0.1 * c[peak], peak, False)
            tt = np.r_[zero, t[k:e], end]
            ii = np.r_[0, c[k:e], 0.1 * c[peak]]
            q = float(np.trapezoid(ii, tt) * 1e6)
            if abs(q - r["Qrr_uC"]) > 1e-7 or abs((end - zero) * 1e9 - r["trr_ns"]) > 1e-4:
                raise ValueError("recovery integration mismatch")
        checks.append(r["tag"])
    # Tabulate measured output, keeping diagnostic controls separate from bounded claims.
    fields = [
        "tag",
        "tt_ns",
        "TJ",
        "VBUS",
        "DIR",
        "LESL",
        "step_ns",
        "status",
        "Qrr_uC",
        "trr_ns",
        "Irrm_A",
        "softness_tb10_over_ta",
        "slew_A_per_us",
        "vds_pk_V",
        "vgs_off_max_V",
    ]
    with (HERE / "sweep-table.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            ident = r["identity"]
            writer.writerow(
                {
                    k: (r.get(k) if k in r else ident.get(k, ident["params"].get(k, "")))
                    for k in fields
                }
            )
    summary = []
    for tt in sorted({r["identity"]["tt_ns"] for r in rows}):
        selected = [
            r
            for r in rows
            if r["identity"]["kind"] == "s4"
            and r["identity"]["tt_ns"] == tt
            and r["identity"]["step_ns"] == 0.2
        ]
        complete = [r for r in selected if r["status"] != "INDETERMINATE"]
        if not selected:
            continue
        summary.append(
            {
                "tt_ns": tt,
                "attempted": len(selected),
                "complete": len(complete),
                "pass": sum(r["status"] == "PASS" for r in complete),
                "vds_min_V": min(r["vds_pk_V"] for r in complete),
                "vds_max_V": max(r["vds_pk_V"] for r in complete),
                "off_min_V": min(r["vgs_off_max_V"] for r in complete),
                "off_max_V": max(r["vgs_off_max_V"] for r in complete),
            }
        )
    refinement = []
    for r in rows:
        i = r["identity"]
        if i["kind"] != "s4" or i["step_ns"] == 0.2:
            continue
        coarse = [
            s
            for s in rows
            if s["identity"]["kind"] == "s4"
            and s["identity"]["tt_ns"] == i["tt_ns"]
            and s["identity"]["step_ns"] == 0.2
            and all(
                s["identity"]["params"][k] == i["params"][k] for k in ("TJ", "VBUS", "DIR", "LESL")
            )
        ]
        if len(coarse) != 1:
            raise ValueError("missing unique coarse reference")
        c = coarse[0]
        refinement.append(
            {
                "tag": r["tag"],
                "delta_vds_V": r["vds_pk_V"] - c["vds_pk_V"],
                "delta_off_V": r["vgs_off_max_V"] - c["vgs_off_max_V"],
                "same_verdict": r["status"] == c["status"],
            }
        )
    audit = {
        "checked_complete": len(checks),
        "indeterminate": sum(r["status"] == "INDETERMINATE" for r in rows)
        + int((HERE / "out-of-range-interruption.json").exists()),
        "baseline_comparisons": comparisons,
        "s4_summary": summary,
        "refinement": refinement,
        "result_sha256": {
            str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((HERE / "results").glob("*/result.json"))
        },
    }
    (HERE / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps({k: v for k, v in audit.items() if k != "result_sha256"}, indent=2))


if __name__ == "__main__":
    main()

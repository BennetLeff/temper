#!/usr/bin/env python3
"""Build comparison/convergence tables from retained simulator results."""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def metrics(row: dict) -> dict[str, float]:
    m = row["meas"]
    off, inc = ("ls", "hs") if row["params"]["DIR"] == "0" else ("hs", "ls")
    out = {
        "off_V": m[f"vgs_{off}_off_max"],
        "partner_V": m[f"vgs_{off}_at_partner"],
        "vds_V": max(m["vds_ls_die_pk"], m["vds_hs_die_pk"]),
        "incoming_V": m[f"vds_{inc}_at_on"],
        "gate_abs_V": max(
            abs(m[k])
            for k in ("vgs_ls_die_max", "vgs_ls_die_min", "vgs_hs_die_max", "vgs_hs_die_min")
        ),
    }
    if "e_l_pre" in m:
        out["energy_uJ"] = (
            sum(m[f"e_{side}_{part}"] for side in ("l", "h") for part in ("pre", "post")) * 1e6
        )
    return out


def verdicts(row: dict) -> dict[str, bool]:
    m = metrics(row)
    limit = 585 if "_S2_" in row["name"] else 520
    return {
        "gate25": m["off_V"] < 3,
        "gatehot": m["off_V"] < 1.9,
        "vds": m["vds_V"] <= limit,
        "gateabs": m["gate_abs_V"] <= 30,
        "zvs": m["incoming_V"] <= 0.05 * float(row["params"]["VBUS"]),
    }


def compare(a: dict, b: dict) -> dict:
    row = {
        "case": a["name"],
        "group": a["group"],
        "first_option": a["option"],
        "second_option": b["option"],
        "first_step": a["params"]["TRMAX"],
        "second_step": b["params"]["TRMAX"],
        "first_complete": a["complete"],
        "second_complete": b["complete"],
    }
    if not a["complete"] or not b["complete"]:
        return row
    x, y = metrics(a), metrics(b)
    for key in x:
        row[f"first_{key}"] = x[key]
        row[f"second_{key}"] = y[key]
        row[f"delta_{key}"] = y[key] - x[key]
    row["vds_relative_delta"] = abs(y["vds_V"] - x["vds_V"]) / max(abs(x["vds_V"]), 1)
    row["within_tolerance"] = (
        abs(y["off_V"] - x["off_V"]) <= 0.01 and row["vds_relative_delta"] <= 0.005
    )
    row["verdict_changes"] = ",".join(k for k, v in verdicts(a).items() if v != verdicts(b)[k])
    row["min_gate_screen_margin_V"] = min(abs(x["off_V"] - s) for s in (1.9, 3))
    return row


def write_csv(name: str, rows: list[dict]) -> None:
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with (HERE / name).open("w") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def stats(rows: list[dict]) -> dict:
    comparable = [r for r in rows if "within_tolerance" in r]
    return {
        "pairs": len(rows),
        "comparable": len(comparable),
        "outside_tolerance": [r for r in comparable if not r["within_tolerance"]],
        "verdict_changes": [r for r in comparable if r["verdict_changes"]],
        "worst_off_delta": max(comparable, key=lambda r: abs(r["delta_off_V"]), default=None),
        "worst_vds_relative_delta": max(
            comparable, key=lambda r: r["vds_relative_delta"], default=None
        ),
        "closest_gate_threshold": min(
            comparable, key=lambda r: r["min_gate_screen_margin_V"], default=None
        ),
    }


def original_baseline() -> dict[str, dict]:
    """Use a complete fresh reproduction when present; reject baseline drift."""
    source = json.loads((HERE / "qualify.json").read_text())
    source += json.loads((HERE / "near-threshold-qualification.json").read_text())
    rows = [r for r in source if r["option"] == "old"]
    frozen = {r["name"]: r for r in rows}
    assert len(frozen) == len(rows) == 246, "Invalid frozen baseline inventory"
    path = HERE / "original-reproduction.json"
    if not path.exists():
        return frozen
    rows = json.loads(path.read_text())
    fresh = {r["name"]: r for r in rows}
    assert len(fresh) == len(rows) == len(frozen) and fresh.keys() == frozen.keys(), (
        "Incomplete or duplicated fresh baseline"
    )
    for name, row in fresh.items():
        for key in ("option", "group", "deck", "params", "identity", "complete", "meas"):
            assert row[key] == frozen[name][key], f"Fresh baseline drift: {name}: {key}"
    return fresh


def main() -> None:
    original = original_baseline()
    summary = {}
    if (HERE / "qualify.json").exists():
        source = json.loads((HERE / "qualify.json").read_text())
        indexed = {(r["name"], r["option"]): r for r in source}
        rows = [compare(r, indexed[(r["name"], "itl4")]) for r in source if r["option"] == "old"]
        write_csv("comparison.csv", rows)
        summary["qualification"] = stats(rows)
        summary["qualification"]["failures"] = [r for r in source if not r["complete"]]
        summary["qualification"]["counts"] = {
            o: {
                g: {
                    "runs": sum(r["option"] == o and r["group"] == g for r in source),
                    "complete": sum(
                        r["option"] == o and r["group"] == g and r["complete"] for r in source
                    ),
                }
                for g in ("grid-abort", "refine", "decision")
            }
            for o in ("old", "itl4")
        }
    if (HERE / "convergence-itl100k.json").exists():
        source = json.loads((HERE / "convergence-itl100k.json").read_text())
        indexed = {(r["name"], r["params"]["TRMAX"]): r for r in source}
        rows = [
            compare(r, indexed[(r["name"], step)])
            for r in source
            if r["params"]["TRMAX"] == "0.2n"
            for step in ("0.1n", "0.05n")
        ]
        rows += [
            compare(r, indexed[(r["name"], "0.05n")])
            for r in source
            if r["params"]["TRMAX"] == "0.1n"
        ]
        write_csv("convergence.csv", rows)
        write_csv(
            "near-threshold-convergence.csv",
            [
                dict(case=r["name"], step=r["params"]["TRMAX"], **metrics(r), **verdicts(r))
                for r in source
                if r["group"] == "near-threshold" and r["complete"]
            ],
        )
        summary["convergence"] = stats(rows)
        summary["convergence"]["failures"] = [r for r in source if not r["complete"]]
        summary["convergence"]["intervals"] = [
            dict(
                steps=steps,
                **stats([r for r in rows if (r["first_step"], r["second_step"]) == steps]),
            )
            for steps in (("0.2n", "0.1n"), ("0.1n", "0.05n"), ("0.2n", "0.05n"))
        ]
    if (HERE / "remaining-failure-probe.json").exists():
        probes = json.loads((HERE / "remaining-failure-probe.json").read_text())
        cap = {r["params"]["TRMAX"]: r for r in probes if r["option"] == "itl10k"}
        references = json.loads((HERE / "remaining-failure-reference.json").read_text())
        references += [
            r
            for r in json.loads((HERE / "qualify.json").read_text())
            if r["name"] == cap["0.2n"]["name"]
        ]
        pairs = [compare(r, cap[r["params"]["TRMAX"]]) for r in references if r["option"] == "old"]
        write_csv("exception-comparison.csv", pairs)
        summary["exception_qualification"] = stats(pairs)
        pairs = [
            compare(cap[a], cap[b])
            for a, b in (("0.2n", "0.1n"), ("0.1n", "0.05n"), ("0.2n", "0.05n"))
        ]
        write_csv("exception-convergence.csv", pairs)
        summary["exception_convergence"] = stats(pairs)
        summary["exception_probes"] = {
            "runs": len(probes),
            "failed": [r for r in probes if not r["complete"]],
        }
    if (HERE / "near-threshold-qualification.json").exists():
        source = json.loads((HERE / "near-threshold-qualification.json").read_text())
        indexed = {(r["name"], r["option"]): r for r in source}
        pairs = [compare(r, indexed[(r["name"], "itl10k")]) for r in source if r["option"] == "old"]
        write_csv("near-threshold-comparison.csv", pairs)
        summary["near_threshold_qualification"] = stats(pairs)
    if (HERE / "qualify-itl100k.json").exists():
        proposed = json.loads((HERE / "qualify-itl100k.json").read_text())
        pairs = [compare(original[r["name"]], r) for r in proposed]
        write_csv("final-comparison.csv", pairs)
        summary["final_qualification"] = stats(pairs)
        summary["final_qualification"]["option"] = "itl4=100000"
        summary["final_qualification"]["failures"] = [r for r in proposed if not r["complete"]]
        summary["final_qualification"]["counts"] = {
            g: {
                "cases": sum(r["group"] == g for r in proposed),
                "original_complete": sum(
                    original[r["name"]]["complete"] for r in proposed if r["group"] == g
                ),
                "proposed_complete": sum(r["complete"] for r in proposed if r["group"] == g),
            }
            for g in ("grid-abort", "refine", "decision", "near-threshold")
        }
        recovered = [
            dict(case=r["name"], **metrics(r), **verdicts(r))
            for r in proposed
            if not original[r["name"]]["complete"] and r["complete"]
        ]
        write_csv("recovered-aborts.csv", recovered)
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: {kk: vv for kk, vv in v.items() if kk in ("pairs", "comparable", "counts")}
                for k, v in summary.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

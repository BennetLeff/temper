"""T2: maximum-setpoint sensitivity with the unchanged C firmware in the loop.

Run from any directory: python3 setpoint_cap.py [--check] [--caps 250,200] [--jobs 5].
The 250 C control must match the committed leak and rim study headlines before
any lower cap is evaluated. All leak latches remain passive for classification;
late hazardous runs retain exposure through the latch and over the passive run.

Hazardous = leak_checks.hazardous(): the untripped T_c crosses 300 degC at any
time, transient overshoot included (owner, 2026-10-16). The final-tail mean
(T_c_steady) is reported for information only.

Evidence: setpoint-cap.json (summary) and setpoint-cap-rows.json.gz (every
run's row, gzip with mtime 0). --check compares both by content, except the
toolchain strings in TOOLCHAIN_KEYS. --caps runs a subset (250 always runs
first, for the control) and compares only those caps.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import tempfile
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import scipy

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
FW = HERE.parent / "firmware"
REPO = HERE.parents[2]
sys.path.insert(0, str(FW))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cold_soak as CS  # noqa: E402
import evidence_compare as EC  # noqa: E402  (reference_platform on the evidence written)
import input_manifest as IM  # noqa: E402  (content-hash manifest of the study inputs)
import leak_checks as LC  # noqa: E402
import rim_limit as RL  # noqa: E402
import xcheck_cosim as X  # noqa: E402
from ref import es  # noqa: E402

# Information only: the commit whose sources produced the box (reference) evidence.
# The input gate is the content-hash manifest in input_manifest.py (T2_INPUTS), not git.
BASE = "68ef097296db106550b2f357c2fae8336784e5db"
CAPS = (200, 210, 220, 230, 240, 250)
OUT = HERE / "setpoint-cap.json"
ROWS_OUT = HERE / "setpoint-cap-rows.json.gz"
# Where and with what the evidence was generated; every derived value must
# still match on any machine.
TOOLCHAIN_KEYS = ("python", "numpy", "scipy", "matplotlib", "machine", "compiler", "library_sha256")


def read_json(name):
    return json.loads((FW / name).read_text())


def first_latch(r):
    return min(((r["first"][k]["t_s"], k) for k in LC.LATCHES if k in r["first"]), default=None)


def thermal_metrics(r, until=None):
    trace = r["trace"]
    if until is not None:
        # The trace uses float32, whereas first-event times are rounded doubles.
        trace = trace[np.rint(trace[:, 0].astype(float) / es.DT_CTRL) <= round(until / es.DT_CTRL)]
    tc = trace[:, 6]
    return {
        "peak_T_c_C": round(float(tc.max()), 1) if until is not None else r["T_c_max"],
        "seconds_above_300": round(int(np.count_nonzero(tc > LC.T_BAR)) * es.DT_CTRL, 1),
        "ends_above_300": bool(tc[-1] > LC.T_BAR),
        "observed_until_s": round(float(trace[-1, 0]) + es.DT_CTRL, 1),
    }


def worker(case):
    r = LC.run_case(dict(case, trace_dt=es.DT_CTRL))
    fl = first_latch(r)
    t300 = r["first"].get("T_c_over_300", {}).get("t_s")
    late = LC.hazardous(r) and fl is not None and t300 is not None and fl[0] >= t300
    late_metrics = None
    if late:
        late_metrics = {
            "passive_until_latch": thermal_metrics(r, fl[0]),
            "passive_full_horizon": thermal_metrics(r),
        }
    # Reproduce rim_limit.py's offline control on precisely its 0.5 s samples.
    offline = RL.rule_latches(r["trace"][:: round(RL.TRACE_DT / es.DT_CTRL)], [RL.CHOSEN])[0]
    row = {k: v for k, v in r.items() if k != "trace"}
    row["offline_rim_latch_s"] = offline
    row["late_thermal"] = late_metrics
    return row


def capped_cases(cap):
    LC.SP_FRY = float(cap)
    sets = {
        "nominal": LC.leak_cases(),
        "worst": RL.stress_leak(),
        "benign": LC.benign_cases(LC.N_SEEDS),
        "stress_benign": RL.stress_benign(),
    }
    for name, cases in sets.items():
        for i, c in enumerate(cases):
            c["case_id"] = f"{name}/{i}"
            if "sp_profile" in c:
                c["sp_profile"] = [(t, min(sp, cap)) for t, sp in c["sp_profile"]]
            else:
                sp1, sp2 = es.PANS[c["pan"]]["sp"]
                sp2 = c.get("sp2") if c.get("sp2") is not None else sp2
                # The first targets are already at or below the lowest cap.
                # Preserve run_case's original down-step timing and seed paths.
                assert sp1 <= cap
                c["sp2"] = min(sp2, cap)
            if "sp_profile" in c:
                assert max(sp for _, sp in c["sp_profile"]) <= cap
            else:
                assert c["sp2"] <= cap
    return sets


def fraction(n, d):
    return {"caught": n, "hazardous": d, "percent": round(100.0 * n / d, 4) if d else None}


def summarize(rows):
    haz = [r for r in rows if LC.hazardous(r)]
    by_mechanism = {k: {"before": 0, "after": 0, "never": 0} for k in (*LC.LATCHES, "none")}
    for r in haz:
        row = LC.leak_row(r)
        key = "none" if row["first_latch"] is None else row["first_latch"]["rule"]
        status = "never" if key == "none" else ("before" if row["latched_before_300"] else "after")
        by_mechanism[key][status] += 1
    counts = {s: sum(v[s] for v in by_mechanism.values()) for s in ("before", "after", "never")}
    late = [r for r in haz if r["late_thermal"] is not None]
    metrics = {}
    for mode in ("passive_until_latch", "passive_full_horizon"):
        vals = [r["late_thermal"][mode] for r in late]
        metrics[mode] = {
            "peak_T_c_C_range": [
                min(v["peak_T_c_C"] for v in vals),
                max(v["peak_T_c_C"] for v in vals),
            ]
            if vals
            else None,
            "seconds_above_300_range": [
                min(v["seconds_above_300"] for v in vals),
                max(v["seconds_above_300"] for v in vals),
            ]
            if vals
            else None,
            "ends_above_300_runs": sum(v["ends_above_300"] for v in vals),
        }
    return {
        "runs": len(rows),
        "hazardous": len(haz),
        **counts,
        "before_percent": fraction(counts["before"], len(haz))["percent"],
        "every_hazard_before_300": counts["before"] == len(haz),
        "lowest_hazardous_R_ohm": round(min(r["r_leak"] for r in haz), 1) if haz else None,
        "highest_hazardous_R_ohm": round(max(r["r_leak"] for r in haz), 1) if haz else None,
        "by_first_mechanism": by_mechanism,
        "late_thermal": metrics,
        "hazardous_by_R_ohm": dict(
            sorted(Counter(str(round(r["r_leak"], 1)) for r in haz).items())
        ),
        "max_abs_tail_drift_K": max((abs(r["T_c_drift_last_100s"]) for r in haz), default=None),
        # The pre-2026-10-16 rule, for information: final-tail mean above the bar.
        "steady_rule_hazardous_info": sum(r["T_c_steady"] > LC.T_BAR for r in rows),
        "hazardous_settling_at_or_below_bar": sum(r["T_c_steady"] <= LC.T_BAR for r in haz),
        "pre_leak_latches": sum(
            first_latch(r) is not None and first_latch(r)[0] < LC.LEAK_AT for r in rows
        ),
        "never_rows": [r["case_id"] for r in haz if first_latch(r) is None],
    }


def benign_summary(rows):
    bad = [r for r in rows if first_latch(r) is not None]
    return {
        "runs": len(rows),
        "false_latches": len(bad),
        "d1_lost": sum("d1_lost" in r["first"] for r in rows),
        "false_latch_rows": [
            {
                "case_id": r["case_id"],
                "kind": r["kind"],
                "pan": r["pan"],
                "first": r["first"],
                "seed": r["seed"],
            }
            for r in bad
        ],
    }


def offline_scores(sets):
    rows = [r for group in sets.values() for r in group]
    for i, r in enumerate(rows):
        r["_i"] = i
    lat = {r["_i"]: r["offline_rim_latch_s"] for r in rows}
    base_lat = {r["_i"]: None for r in rows}
    benign = {n: sets[n] for n in ("benign", "stress_benign")}
    return {
        "chosen": {
            "nominal": RL.score(sets["nominal"], benign, lat),
            "worst": RL.score(sets["worst"], {}, lat),
        },
        "existing": {n: RL.score(sets[n], {}, base_lat) for n in ("nominal", "worst")},
    }


def control(sets):
    lc, rl = read_json("leak-checks.json"), read_json("rim-limit.json")
    got = LC.leak_summary([LC.leak_row(r) for r in sets["nominal"]])
    want = lc["summary"]["leak"]["all_onsets"]
    fields = (
        "runs",
        "hazardous_runs",
        "hazardous_latched_before_300",
        "hazardous_latched_after_300",
        "hazardous_never_latched",
        "hazardous_leak_check_first",
        "hazardous_rim_fault_first",
        "hazardous_rim_limit_first",
        "highest_r_hazardous_ohm",
    )
    checks = {
        "C_nominal_headlines": {
            "expected": {k: want[k] for k in fields},
            "actual": {k: got[k] for k in fields},
        }
    }
    for onset in LC.ONSETS:
        actual = LC.leak_summary([LC.leak_row(r) for r in sets["nominal"] if r["onset"] == onset])
        expected = lc["summary"]["leak"]["by_onset"][onset]
        checks[f"C_nominal_{onset}"] = {
            "expected": {k: expected[k] for k in fields},
            "actual": {k: actual[k] for k in fields},
        }
    off = offline_scores(sets)
    chosen = next(c for c in rl["curve"] if all(c[k] == v for k, v in RL.CHOSEN.items()))
    for label, actual, expected in (
        ("offline_nominal_chosen", off["chosen"]["nominal"], chosen["sweep"]),
        ("offline_worst_chosen", off["chosen"]["worst"], chosen["stress_leak"]),
        (
            "offline_nominal_existing",
            off["existing"]["nominal"],
            rl["baseline_existing_latches"]["sweep"],
        ),
        (
            "offline_worst_existing",
            off["existing"]["worst"],
            rl["baseline_existing_latches"]["stress_leak"],
        ),
    ):
        fields = [k for k, v in expected.items() if isinstance(v, int)]
        checks[label] = {
            "expected": {k: expected[k] for k in fields},
            "actual": {k: actual[k] for k in fields},
        }
    for name, source_name in (
        ("nominal", "sweep"),
        ("worst", "stress_leak"),
        ("benign", "benign"),
        ("stress_benign", "stress_benign"),
    ):
        checks[f"runs_{name}"] = {"actual": len(sets[name]), "expected": rl["runs"][source_name]}
    for name in ("benign", "stress_benign"):
        checks[f"false_{name}"] = {
            "actual": benign_summary(sets[name])["false_latches"],
            "expected": 0,
        }
    checks["benign_d1_lost"] = {
        "actual": benign_summary(sets["benign"])["d1_lost"],
        "expected": lc["summary"]["benign"]["d1_lost"],
    }
    source_cold = read_json("cold-soak.json")["hazardous"]["coverage"]
    actual_cold = cold_tables(sets["nominal"], cold_evidence(), "nominal")["coverage"]
    expected, actual = {}, {}
    for variant in CS.VARIANTS:
        for family, ambients in actual_cold[variant].items():
            for ambient, cell in ambients.items():
                key = f"{variant}/{family}/{ambient}"
                source = source_cold[variant]["nominal"][family][ambient]
                expected[key] = [
                    source[k]
                    for k in (
                        "hazardous",
                        "caught_before_heating",
                        "cold_soak",
                        "window_84.27_only",
                    )
                ]
                actual[key] = [cell[k] for k in ("hazardous", "caught", "cold_soak", "window")]
    checks["cold_nominal_coverage"] = {"actual": actual, "expected": expected}
    for c in checks.values():
        c["match"] = c["actual"] == c["expected"]
    return {"checks": checks, "pass": all(c["match"] for c in checks.values())}


def cold_evidence():
    cs = read_json("cold-soak.json")
    return cs["hazardous"]["per_leak_value"]


def cold_tables(rows, per_value, corner):
    haz = [r for r in rows if LC.hazardous(r)]
    coverage = {}
    for variant in CS.VARIANTS:
        for family in ("independent", *(str(e) for e in CS.EA_EV)):
            for ambient in CS.AMBIENTS:
                results = [
                    per_value[f"{variant}/{corner}/{family}/{ambient}/{round(r['r_leak'], 1)}"]
                    for r in haz
                ]
                n = sum(x["caught_by"] is not None for x in results)
                by_r = {round(r["r_leak"], 1): x for r, x in zip(haz, results, strict=True)}
                caught_r = sorted(r for r, x in by_r.items() if x["caught_by"] is not None)
                coverage.setdefault(variant, {}).setdefault(family, {})[str(ambient)] = {
                    **fraction(n, len(haz)),
                    "distinct_leak_values": fraction(len(caught_r), len(by_r)),
                    "caught_R_ohm": caught_r,
                    "cold_soak": sum(x["caught_by"] == "cold_soak" for x in results),
                    "window": sum(x["caught_by"] == "window_84.27" for x in results),
                }
    return {"cold_corner": corner, "coverage": coverage}


def compact_row(r):
    row = {
        k: v
        for k, v in r.items()
        if k not in ("_i", "suspect_times_s", "offline_rim_latch_s", "case_id")
    }
    if r["kind"] == "leak":
        row.update(LC.leak_row(r))
    return {"case_id": r["case_id"], **row}


def cap_result(sets, per_value):
    result = {name: summarize(sets[name]) for name in ("nominal", "worst")}
    result["worst_by_glass"] = {
        name: summarize([r for r in sets["worst"] if r["glass"] == name])
        for name in sorted({r["glass"] for r in sets["worst"]})
    }
    result["benign"] = {name: benign_summary(sets[name]) for name in ("benign", "stress_benign")}
    result["cold"] = {
        "nominal": cold_tables(sets["nominal"], per_value, "nominal"),
        "worst": cold_tables(sets["worst"], per_value, "miss"),
    }
    rows = {name: [compact_row(r) for r in sets[name]] for name in ("nominal", "worst")}
    return result, rows


def apparatus(lib_path):
    return {
        "base_commit_info": BASE,
        "input_sha256": IM.sha256_manifest(REPO, IM.T2_INPUTS),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "library_sha256": hashlib.sha256(Path(lib_path).read_bytes()).hexdigest(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "matplotlib": importlib.metadata.version("matplotlib"),
        "machine": platform.machine(),
        "compiler": subprocess.check_output(
            [os.environ.get("CC", "cc"), "--version"], text=True
        ).splitlines()[0],
    }


def run(jobs, lib_path, caps=CAPS):
    per_value = cold_evidence()
    result = {
        "apparatus": apparatus(lib_path),
        "firmware_cap_inventory": cap_inventory(),
        "model": {
            "caps_C": list(CAPS),
            "exposure_scope": "All latches passive, as in leak_checks.run_case; no shutdown trajectory is simulated",
            "bar_C": LC.T_BAR,
            "delta_K": list(LC.DELTAS),
            "bead_tolerance_K_at_250C": RL.PCB_BEAD_250_K,
            "bead_R25_and_beta_multipliers": X.CORNERS,
            "benign_hot_stack": X.STACKS["hot_stack"],
            "cold_stack": X.STACKS["cold_stack"],
            "nominal_tau_g_s": X.TAU_G,
            "worst_tau_g_s": max(RL.TAU_GS),
            "worst_rail_mV": X.STACKS["cold_stack"][1],
            "w_lo_hot": RL.W_LO_HOT,
            "w_hi": RL.W_HI,
            "eye_lo_C": RL.T_EYE_LO,
            "leak_onset_s": LC.LEAK_AT,
            "onset_ramps_s": LC.ONSETS,
            "horizon_s": LC.T_END_LEAK,
            "dt_control_s": es.DT_CTRL,
            "dt_plant_s": es.DT_SIM,
            "cold_thresholds_K": read_json("cold-soak.json")["thresholds_used"],
            "cold_ambients_C": list(CS.AMBIENTS),
            "cold_Arrhenius_Ea_eV": list(CS.EA_EV),
            "cold_benign": read_json("cold-soak.json")["benign_gated"],
            "cold_reported_outside_assumptions": read_json("cold-soak.json")[
                "benign_reported_outside_assumptions"
            ],
            "cold_reported_latched": read_json("cold-soak.json")["benign_reported_latched"],
            "rim_constants": RL.firmware_constants(),
        },
        "caps": {},
        "combined_table": [],
    }
    all_rows = {}
    cache = {}
    progress = Path(tempfile.gettempdir()) / f"temper-t2-progress-{os.getpid()}.json"
    for cap in sorted(caps, reverse=True):
        cases = capped_cases(cap)
        print(
            f"cap {cap}: {sum(len(v) for v in cases.values())} passive cases",
            flush=True,
        )

        # Exact input duplicates (notably the unchanged water pot and benign
        # targets below a cap) have the same trajectory. Cache only in memory
        # within this invocation; --check starts with an empty cache too.
        def key(c):
            return json.dumps({k: v for k, v in c.items() if k != "case_id"}, sort_keys=True)

        pending = {key(c): c for group in cases.values() for c in group if key(c) not in cache}
        with Pool(jobs, initializer=X._init, initargs=(lib_path,)) as pool:
            for i, (k, r) in enumerate(
                zip(pending, pool.imap(worker, pending.values(), chunksize=1), strict=True), 1
            ):
                cache[k] = r
                if i % 100 == 0:
                    print(f"cap {cap}: evaluated {i}/{len(pending)} unique cases", flush=True)
        sets = {
            name: [dict(cache[key(c)], case_id=c["case_id"]) for c in group]
            for name, group in cases.items()
        }
        if cap == 250:
            result["control_250"] = control(sets)
            if not result["control_250"]["pass"]:
                details = {
                    k: v for k, v in result["control_250"]["checks"].items() if not v["match"]
                }
                raise RuntimeError(
                    "250 C control mismatch; lower caps not evaluated: " + json.dumps(details)
                )
            print("250 C controls match committed C and offline headlines", flush=True)
        result["caps"][str(cap)], all_rows[str(cap)] = cap_result(sets, per_value)
        c = result["caps"][str(cap)]
        c["evaluated_unique_cases"] = len(pending)
        c["reused_identical_cases"] = sum(len(v) for v in cases.values()) - len(pending)
        table = {"cap_C": cap}
        for name in ("nominal", "worst"):
            table[name] = {
                k: c[name][k] for k in ("hazardous", "before", "after", "never", "before_percent")
            }
            table[name]["cold_check_alone_independent_25C"] = {
                v: c["cold"][name]["coverage"][v]["independent"]["25.0"] for v in CS.VARIANTS
            }
        result["combined_table"].append(table)
        # Keep completed measurements if the long sweep is interrupted. This
        # checkpoint is never an input to generation or the --check gate.
        progress.write_text(
            json.dumps(result, indent=1, allow_nan=False) + "\n"
        )
        print(
            f"cap {cap}: nominal {c['nominal']['before']}/{c['nominal']['hazardous']}; worst {c['worst']['before']}/{c['worst']['hazardous']}",
            flush=True,
        )
    result["combined_table"].sort(key=lambda r: r["cap_C"])
    result["gate"] = {
        "all_caps_complete": set(result["caps"]) == {str(c) for c in caps}
        and len(result["combined_table"]) == len(caps),
        "control_250_matches": result["control_250"]["pass"],
        # Re-verified after the sweep: every input hash recorded at start still matches.
        "source_inputs_unchanged": IM.unchanged(result["apparatus"]["input_sha256"], REPO),
        "rim_constants_match": result["model"]["rim_constants"]["match"],
        "no_benign_false_latches": all(
            b["false_latches"] == 0 for c in result["caps"].values() for b in c["benign"].values()
        ),
        "benign_no_d1_lost": all(
            c["benign"]["benign"]["d1_lost"] == 0 for c in result["caps"].values()
        ),
        "cold_benign_no_latches": all(
            b["latches"] == 0
            for variant in result["model"]["cold_benign"].values()
            for b in variant.values()
        ),
        "no_pre_leak_latches": all(
            c[n]["pre_leak_latches"] == 0
            for c in result["caps"].values()
            for n in ("nominal", "worst")
        ),
    }
    result["all_pass"] = all(result["gate"].values())
    progress.unlink(missing_ok=True)
    return result, all_rows


def plot(result, path):
    os.environ.setdefault("MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "temper-t2-matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 5.5), layout="constrained")
    colors = {"nominal": "#206a9c", "worst": "#b64c37"}
    for name in ("nominal", "worst"):
        rows = result["combined_table"]
        x = [r["cap_C"] for r in rows]
        y = [r[name]["before_percent"] for r in rows]
        ax.plot(x, y, "o-", color=colors[name], label=f"Mid-cook leak: {name}")
        for r, a, b in zip(rows, x, y, strict=True):
            ax.annotate(
                f"{r[name]['before']}/{r[name]['hazardous']}",
                (a, b),
                xytext=(0, 9 if name == "nominal" else -16),
                textcoords="offset points",
                ha="center",
                fontsize=9,
                color=colors[name],
            )
    ax.set(
        xlabel="Maximum requested setpoint (C)",
        ylabel="Hazardous runs latched before first 300 C crossing (%)",
        ylim=(-5, 110),
        xticks=list(CAPS),
        title="Lower setpoint caps: firmware coverage of modelled Pt100 leaks",
    )
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8, loc="best")
    fig.text(
        0.5,
        -0.025,
        "Labels are caught / hazardous; each cap has its own hazardous set. Leaks begin during heating, after the cold-soak check.",
        ha="center",
        fontsize=8,
    )
    fig.savefig(
        path, dpi=160, bbox_inches="tight", metadata={"Software": "Temper T2 setpoint_cap.py"}
    )
    plt.close(fig)


def cap_inventory():
    import re

    patterns = {
        "firmware/config.yaml": r"c_symbol: MAX_TEMP|field: max_temp|value: 250.0|env_var: TEMP_MAX_C",
        "firmware/config.h": r"max_temp =|#define MAX_TEMP|TEMP_MAX_C",
        "firmware/main/ui.c": r"current_temp_setpoint >",
        "firmware/main/state_machine.c": r"temp_celsius >= MIN_TEMP",
        "firmware/main/state_handlers.c": r"target_temperature > MAX_TEMP|target_temperature = MAX_TEMP",
        "firmware/components/control/pan_rate_pid.c": r"p->kp_per_s =|p->ki_per_s2 =|p->kd =",
        "firmware/components/control/contact_check.c": r"p->probe_off_s =|p->probe_on_s =|p->probe_p_frac =|p->probe_lag_s =",
    }
    return {
        p: [
            {"line": i, "text": line.strip()}
            for i, line in enumerate((REPO / p).read_text().splitlines(), 1)
            if re.search(pattern, line)
        ]
        for p, pattern in patterns.items()
    }


def notes(result):
    m = result["model"]
    lines = [
        "# T2 — maximum user setpoint and Pt100 leak coverage",
        "",
        "This is a sensitivity study for a human product decision. No firmware constants, existing studies, or existing evidence are changed.",
        "",
        "**Hazard definition (owner, 2026-10-16).** A run is hazardous when its untripped pan-centre temperature crosses 300 °C at any time, transient overshoot included (`leak_checks.hazardous()`, the unrounded first crossing). Until 2026-10-16 the studies used the final-tail mean (`T_c_steady`) instead; that count is kept for information as `caps.<cap>.<ensemble>.steady_rule_hazardous_info`, and `hazardous_settling_at_or_below_bar` counts the hazardous runs that overshoot and settle at or below the bar.",
        "",
        "## Combined coverage",
        "",
        "The plot and mid-cook columns cover any first firmware latch in `leak_checks.LATCHES`, including the leak chain, rim limit and rim over-range. The leak begins during heating, so cold soak contributes no catches to those runs. The last column reports the cold check alone for temperature-independent leakage already present at an eligible cold start, with a measured rail at the stated ambient. These are distinct onset scenarios, with no assumed probability of a cold-present leak. They cannot be combined into a physically validated cold-start trajectory by adding or joining counts: leakage from cold can change D1 and the subsequent trajectory. That would require a separate coupled cold-start simulation.",
        "",
        "Source: `combined_table[]`; each count and percentage is regenerated into `setpoint-cap.json`. Nominal/worst denominators are separate ensembles. `caps.<cap>.{nominal,worst}.highest_hazardous_R_ohm` gives the highest hazardous resistance (weakest hazardous conductance); lowest resistance is also recorded, since the older study calls that the largest leak.",
        "",
        "| Cap C | Nominal before / hazardous (%) | Worst before / hazardous (%) | Never, nominal / worst | Highest hazardous R, nominal / worst (ohm) | False, benign / stress | Cold check alone at 25 C, measured rail, nominal / worst (%) |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["combined_table"]:
        cap = str(row["cap_C"])
        c = result["caps"][cap]
        n, w = c["nominal"], c["worst"]
        cold = [
            row[k]["cold_check_alone_independent_25C"]["rail_measured"]["percent"]
            for k in ("nominal", "worst")
        ]
        lines.append(
            f"| {cap} | {n['before']}/{n['hazardous']} ({n['before_percent']:.2f}) | {w['before']}/{w['hazardous']} ({w['before_percent']:.2f}) | {n['never']} / {w['never']} | {n['highest_hazardous_R_ohm']} / {w['highest_hazardous_R_ohm']} | {c['benign']['benign']['false_latches']} / {c['benign']['stress_benign']['false_latches']} | {cold[0]:.2f} / {cold[1]:.2f} |"
        )
    lines += [
        "",
        "![Coverage vs cap](setpoint-cap.png)",
        "",
        "## First mechanism and timing",
        "",
        "Source: `caps.<cap>.<ensemble>.by_first_mechanism`; pairs are before / after the first crossing. `none.never` is the never-latched count within the run horizon. A same-tick latch and crossing counts as after, matching the original strict-before rule. The JSON retains all other mechanisms separately, including the sensor guard and supervisor.",
        "",
        "| Cap C | Ensemble | Leak before / after | Rim limit before / after | Rim over-range before / after | Other before / after | Never |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in result["combined_table"]:
        cap = str(row["cap_C"])
        for name in ("nominal", "worst"):
            c = result["caps"][cap][name]
            by = c["by_first_mechanism"]
            pairs = {k: f"{v['before']} / {v['after']}" for k, v in by.items()}
            other = [
                sum(by[k][s] for k in LC.LATCHES if k not in ("leak", "rim_limit", "rim_fault"))
                for s in ("before", "after")
            ]
            lines.append(
                f"| {cap} | {name} | {pairs['leak']} | {pairs['rim_limit']} | {pairs['rim_fault']} | {other[0]} / {other[1]} | {c['never']} |"
            )
    lines += [
        "",
        "## Late-latch exposure",
        "",
        "Sources: `caps.<cap>.<ensemble>.late_thermal` (ranges), and `setpoint-cap-rows.json.gz` `<cap>.<ensemble>[].late_thermal` (every late hazardous run). Passive-until-latch reports the original trajectory up to its first latch. Passive-full-horizon reports continued heating with every latch passive, exactly as `leak_checks.run_case` operates. Both peak temperature and time above the bar are reported for each window; full-horizon metrics are not a post-shutdown prediction. Coverage counts detection timing and does not establish that an early-latched pan remains below the bar after power removal. The existing API has no actuation argument. Minimal extension needed, not made under this task's rules: add an optional `actuate_latches=False` argument to `leak_checks.run_case`; when enabled, remember the first latch and force plant input power to zero from the next control period onward, keeping the default passive path unchanged. That would permit shutdown peak/exposure measurement with the existing truth plant; its first latch should be checked against the passive run. No functions or truth-model classes are replaced by this script.",
        "",
        f"Exposure counts sampled periods at {m['dt_control_s']} s resolution; peak temperatures are rounded to a tenth of a degree. A final sample still above the bar means the duration is censored by the {m['horizon_s']} s horizon.",
        "",
        "| Cap C | Ensemble | Late runs | Passive through latch: peak C range | Through latch: seconds above range | Passive full run: peak C range | Passive full run: seconds above range | Still above at horizon |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["combined_table"]:
        cap = str(row["cap_C"])
        for name in ("nominal", "worst"):
            c = result["caps"][cap][name]
            p, a = (c["late_thermal"][k] for k in ("passive_until_latch", "passive_full_horizon"))
            lines.append(
                f"| {cap} | {name} | {c['after']} | {p['peak_T_c_C_range']} | {p['seconds_above_300_range']} | {a['peak_T_c_C_range']} | {a['seconds_above_300_range']} | {a['ends_above_300_runs']} |"
            )
    lines += [
        "",
        "## Cold soak: before heating, only if the leak is present when cold",
        "",
        "The existing check runs at eligible PREHEAT entry, before any heating; it is not an unconditional power-up latch. The original idle/history, heatsink, flatness and rim-saturation conditions still apply. A leak forming later during a cook cannot be caught by this layer for that cook. `window` denotes the existing RTD low-resistance fault rather than D-SOAK.",
        "",
        "Source: `caps.<cap>.cold.<ensemble>.coverage.<rail>.<family>.<ambient>`. The script reweights committed `cold-soak.json` `hazardous.per_leak_value` by the newly hazardous runs at each cap, rather than carrying over the original denominator. Fractions in the table count hazardous runs; each JSON cell also records `distinct_leak_values` and `caught_R_ohm` for the fraction of distinct hazardous resistance values. Nominal uses the nominal cold corner; worst uses the cold check's miss corner as well as the dynamic cold-stack ensemble. Rail unknown is `rail_fallback`. The same committed benign cold-start sets are retained at their original cook temperature, a conservative envelope for lower caps: `model.cold_benign`.",
        "",
        "The next table gives temperature-independent leakage fractions at the displayed ambient and the minimum/maximum percentages across the source ambient grid. All Arrhenius families, ambients and counts are also in the JSON; no distribution over ambients or leak families is assumed.",
        "",
        "| Cap C | Ensemble | Rail | At 25 C: caught / hazardous (%) | Range across ambients (%) | Arrhenius range across all Ea and ambients (%) |",
        "|---:|---|---|---:|---:|---:|",
    ]
    for row in result["combined_table"]:
        cap = str(row["cap_C"])
        for name in ("nominal", "worst"):
            for variant in CS.VARIANTS:
                cov = result["caps"][cap]["cold"][name]["coverage"][variant]
                a = cov["independent"]["25.0"]
                vals = [v["percent"] for v in cov["independent"].values()]
                arr = [
                    v["percent"]
                    for family, ambs in cov.items()
                    if family != "independent"
                    for v in ambs.values()
                ]
                lines.append(
                    f"| {cap} | {name} | {variant} | {a['caught']}/{a['hazardous']} ({a['percent']:.2f}) | {min(vals):.2f}–{max(vals):.2f} | {min(arr):.2f}–{max(arr):.2f} |"
                )
    lines += [
        "",
        "Cold and dynamic catches are not added as independent percentages. The dynamic sweep does not simulate temperature-varying resistance for the Arrhenius families. Those families illustrate how leakage that disappears when cold can evade D-SOAK. The source study also reports benign latches outside its gated assumptions, including frozen-pan plateaus, a room below the budgeted band, and an unusually slow heatsink relaxation. Those source results are retained in `model.cold_reported_outside_assumptions` and `model.cold_reported_latched`; they are reference results at the original cook condition, not new cap-specific trajectories. A cap does not establish that those cases are safe or eliminate their bench prerequisites.",
        "",
        "## Model scope and control",
        "",
        f"The nominal ensemble retains glass offsets {m['delta_K']} K, both bead corners (the cited bead budget is ±{m['bead_tolerance_K_at_250C']} K at the reference temperature), and a {m['nominal_tau_g_s']} s glass lag. The stress ensemble is exactly `rim_limit.stress_leak`: both its leak-envelope and flat/cool-eye geometries, cold bead/rail stack at {m['worst_rail_mV']} mV, glass lag {m['worst_tau_g_s']} s, eye {m['eye_lo_C']} C, and weights {m['w_lo_hot']} / {m['w_hi']}. It is an adverse sampled model ensemble, not a proof over every possible pan or tolerance combination. `caps.<cap>.worst_by_glass` separates its geometries.",
        "",
        "The cap changes the requested frying-pan final target and clips all requested profiles. Initial targets, pan physics, seeds, leak values, onset ramps, C thresholds, gains, D1 response and supervisor behavior are preserved. Stress-benign hold/down/hot-pan profiles come from the existing factory with its top target capped. The stress factory's fixed initially hot glass is retained, including the original high-temperature envelope even for a lower cap. Original benign hot-glass cases are retained too. These explicit conservative thermal initial conditions are not reduced to manufacture a false-latch pass.",
        "",
        "Hazardous means the untripped pan-centre temperature crosses the bar at any time within the horizon (`leak_checks.hazardous()`). D1 LOST still removes power and may alter which runs are hazardous. `max_abs_tail_drift_K` is reported per ensemble for the steady figures given as information. Both ends of the hazardous resistance range are sampled sweep values, not continuous critical-resistance bounds. Percentages describe this grid of runs, not probabilities or field failure rates.",
        "",
        "`control_250.checks` compares the committed C-loop headline counts and the rim study's offline chosen/existing headline counts exactly. The offline rim evaluation has its original decimated sampling and differs from the authoritative C result; it is retained only to reproduce that control, while cap results use the C latches. A control mismatch raises an error before any lower cap runs. `gate` also checks unchanged source inputs, unchanged rim constants, benign latches, and pre-leak latches. A modeled coverage shortfall is reported, not turned into a passing safety claim.",
        "",
        "## Firmware integration and re-verification",
        "",
        "Exact source lines/excerpts are in `firmware_cap_inventory`. A real product cap belongs in the config manifest's `MAX_TEMP`/`max_temp` entry and generated header, with both independent UI clamps reconciled. The target setter rejects targets beyond `MAX_TEMP`; heating handlers also clamp to it. Runtime config/environment metadata is present in the generated header; a change must preserve agreement between the runtime config, compile-time limit, UI, persistence and all entry points. No limit is changed here.",
        "",
        "Re-verify D1 excitation/acceptance, contact-loss and retry behavior, food/batch and hot-pan behavior, estimator/contact-shift and online gain identification, PID gain scheduling and the latent-plateau guard across the reduced target range. The rim rule is setpoint-relative: its glass envelope, hot-tolerance interpolation, decaying reference and not-falling window still require coverage/false-latch checks, with bench glass transients and sensor tolerances. Do not simply lower the absolute runaway, RTD-window or independent hardware comparator limits along with the UI cap. Revisit overshoot/recovery bars, thermal and cooking performance, stored targets, UI feedback, SIL/runtime tests, cold-soak restart histories, production calibration and hot insulation/ingress qualification. This sweep does not replace physical fault injection or qualification.",
        "",
        "## Reproduce",
        "",
        "Evidence reference platform: the remote box (linux x86_64; `reference_platform` in the JSON and rows). "
        "Regenerate there; anywhere else `--check` compares counts, classifications and gates exactly and floats "
        "within `../evidence_compare.py`'s tolerance (DECISIONS.md D-EVPLAT). From the repository root:",
        "",
        "```bash",
        "# on the box (the reference): ssh bennet@100.121.239.87, cd ~/WS-sensor/temper, put ~/router-scratch/env/bin first on PATH, then:",
        "python3 output/temper-sensor-r3/leak-barrier/setpoint_cap.py                    # regenerate the JSON, rows, PNG and these notes (box only)",
        "python3 output/temper-sensor-r3/leak-barrier/setpoint_cap.py --check            # full check, every cap",
        "python3 output/temper-sensor-r3/leak-barrier/setpoint_cap.py --check --caps 250,200   # the run.sh step 5d subset",
        "cd output/temper-sensor-r3/firmware && ./run.sh",
        "```",
        "",
        "The script rebuilds the unchanged C cosimulation library on each invocation. `--check` reruns the sweep and compares the regenerated `setpoint-cap.json` and `setpoint-cap-rows.json.gz` with the committed files by content; it does not rewrite them. Only the toolchain strings in `TOOLCHAIN_KEYS` (interpreter and package versions, machine, compiler, library hash) are exempt; on the reference platform every count, temperature and source-input hash must match, and elsewhere floats follow `evidence_compare.py` (summary floats tight, per-run rows within 0.5 s / 0.5 K, listed outliers) while every count, flag and source hash stays exact. `--caps` restricts both the run and the comparison to the listed caps (250 always runs first, for the control). The input manifest (`apparatus.input_sha256`, leak-barrier/input_manifest.py `T2_INPUTS`) is re-verified after the sweep. `--jobs` affects throughput only. `T2 PASS` means evidence/control/benign gates pass, not that the every-hazard-before-bar requirement is met.",
        "",
        "## Review observations",
        "",
        "A cap changes both the hazardous population and the detector signal. Hazardous counts generally fall, but the identities are not strictly nested: D1 power interruptions can make a case qualify at one cap and not at another. The physical case identities and seeds are fixed; compare `setpoint-cap-rows.json.gz` `<cap>.<ensemble>[].{case_id,T_c_max,t_T_c_over_300_s,d1_lost}`. The before-bar percentage alone does not describe the tradeoff: `caps.<cap>.<ensemble>.never` records hazardous runs that never latch within the horizon. The mechanism table retains all after/never counts.",
        "",
        "`caps.<cap>.benign.<set>.d1_lost` records nonlatched contact-loss interruptions separately from false latched faults. Some stress-benign cases have these interruptions. Zero false-latch counts do not mean that every benign trajectory is uninterrupted.",
        "",
        "Provenance: the study was written by a Codex cloud agent on Linux (commit 0ab4a857f, steady hazard rule) and ported to the peak hazard rule and regenerated on the Mac. The cloud and Mac runs of the unchanged script are compared in the port's commit message.",
        "",
    ]
    return "\n".join(lines)


def comparable(summary, rows, caps):
    """The evidence minus the toolchain strings, restricted to the caps that ran."""
    summary = json.loads(json.dumps(summary, allow_nan=False))
    for k in TOOLCHAIN_KEYS:
        summary["apparatus"].pop(k, None)
    keep = {str(c) for c in caps}
    summary["caps"] = {k: v for k, v in summary["caps"].items() if k in keep}
    summary["combined_table"] = [r for r in summary["combined_table"] if str(r["cap_C"]) in keep]
    if keep != {str(c) for c in CAPS}:
        # The gates aggregate over the caps that ran; a subset run checks its own.
        summary.pop("gate", None)
        summary.pop("all_pass", None)
    return summary, {k: v for k, v in rows.items() if k in keep}


def write_rows(rows, path):
    # mtime 0 and no file name in the header: the same rows give the same bytes
    # with the same zlib; --check compares content, not bytes.
    with open(path, "wb") as fh, gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0) as gz:
        # The platform travels with the rows so evidence_compare can pick its rule.
        gz.write((json.dumps(EC.stamp(rows), allow_nan=False) + "\n").encode())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="rebuild and regenerate; fail on any committed evidence difference (toolchain strings excepted)",
    )
    ap.add_argument(
        "--caps",
        default=",".join(str(c) for c in CAPS),
        help="comma-separated subset of caps to run (250 is always included); --check compares only these",
    )
    ap.add_argument("--jobs", type=int, default=min(5, os.cpu_count() or 1))
    args = ap.parse_args()
    try:
        if args.jobs < 1:
            raise ValueError("--jobs must be positive")
        caps = sorted({int(c) for c in args.caps.split(",")} | {250})
        if not set(caps) <= set(CAPS):
            raise ValueError(f"--caps must be drawn from {CAPS}")
        if not args.check and caps != sorted(CAPS):
            raise ValueError("a subset of caps is for --check only; regenerate with every cap")
        with tempfile.TemporaryDirectory(prefix="temper-t2-") as tmp:
            lib_path = subprocess.check_output([str(FW / "build_lib.sh"), tmp], text=True).strip()
            result, rows = run(args.jobs, lib_path, caps)
        if args.check:
            committed = (
                json.loads(OUT.read_text()),
                json.loads(gzip.decompress(ROWS_OUT.read_bytes())),
            )
            fresh = comparable(EC.stamp(result), rows, caps)
            old = comparable(*committed, caps)
            # The rows carry no platform of their own: they follow the summary's.
            cross = EC.cross_platform(old[0], fresh[0])
            problems = []
            for label, a, b, name in (("summary", old[0], fresh[0], OUT.name), ("rows", old[1], fresh[1], ROWS_OUT.name)):
                res = EC.compare(a, b, name=name, cross=cross)
                for o in res.outliers if res.ok else []:
                    print(f"T2 {label}: allowed cross-platform outlier {o}", flush=True)
                problems += [f"{label}: {d}" for d in res.diffs[:10]]
            if problems:
                cand = Path(tempfile.gettempdir()) / f"temper-t2-regenerated-{os.getpid()}"
                cand.mkdir(exist_ok=True)
                (cand / OUT.name).write_text(json.dumps(result, indent=1, allow_nan=False) + "\n")
                write_rows(rows, cand / ROWS_OUT.name)
                raise RuntimeError(f"regenerated evidence differs; candidate saved to {cand}:\n  "
                                   + "\n  ".join(problems))
        else:
            OUT.write_text(json.dumps(EC.stamp(result), indent=1, allow_nan=False) + "\n")
            write_rows(rows, ROWS_OUT)
            plot(result, HERE / "setpoint-cap.png")
            (HERE / "NOTES-t2.md").write_text(notes(result))
        if not result["all_pass"]:
            raise RuntimeError(
                "failed gates: " + ", ".join(k for k, v in result["gate"].items() if not v)
            )
    except Exception as exc:
        print(f"T2 FAIL: {exc}", flush=True)
        return 1
    print("T2 PASS" + ("" if caps == sorted(CAPS) else f" (caps {','.join(map(str, caps))})"), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

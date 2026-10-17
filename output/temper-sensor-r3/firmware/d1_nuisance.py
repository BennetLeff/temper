"""F1: reproduce and gate D1 nuisance power cuts on rim_limit's stress benign set.

Run: python3 d1_nuisance.py [--check] [--jobs N] [--lib path] [--out path]
The library is rebuilt from source on every invocation. The 132 cases
at each cap use leak_checks.run_case unchanged; only cases containing LOST are
rerun with a transparent library proxy. Every LOST and subsequent retry is
reported with exact float32 C inputs and the complete probe window. Full-run
traces stay in memory and are not emitted. Production D1 is unchanged; the
shape-guard diagnostics describe a rejected counterfactual candidate only.

--check compares every value and source hash exactly, ignoring only explicitly
listed toolchain strings. It never writes evidence. --lib uses a caller-built
library, accepted only if its bytes match the fresh build from these sources.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import shlex
import subprocess
import sys
import tempfile
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
import cosim  # noqa: E402
import leak_checks as LC  # noqa: E402
import rim_limit as RL  # noqa: E402
from ref import es  # noqa: E402

BASE_REVISION = "ebf8a777b50ecb81040fc0c56fa8bde706720638"
CAPS = (250, 230)
EXPECTED_RUNS = 132
# Recorded baseline ceiling; reductions pass, increases do not.
LOST_MAX = {250: 2, 230: 1}
OUT = HERE / "d1-nuisance.json"
EVENT = {0: "none", 1: "suspect", 2: "probe_passed", 3: "lost", 4: "restored"}
STATE = {0: "normal", 1: "probe", 2: "lost", 3: "retry"}
TOOLCHAIN_KEYS = ("python", "numpy", "scipy", "matplotlib", "machine", "compiler")
PARAM_NAMES = (
    "dt_s", "p_max_w", "trig_window", "trig_rate_k_per_s", "trig_hold_s",
    "trig_pmin_frac", "probe_off_s", "probe_on_s", "probe_p_frac", "probe_lag_s",
    "retry_off_s", "retry_on_s", "retry_p_frac", "retry_lag_s", "probe_frac",
    "retry_s", "holdoff_s", "decay_tau_s", "decay_tau_tol", "decay_steps",
    "decay_asym_k", "decay_rms_k", "probe_min_sigma", "retry_decay_only",
    "decay_min_change_k",
)


def capped_cases(cap):
    """Exactly setpoint_cap.capped_cases(cap)['stress_benign'], without its other sets."""
    previous = LC.SP_FRY
    try:
        # Set this BEFORE the factory: its down-step is top - 100 K.
        LC.SP_FRY = float(cap)
        cases = RL.stress_benign()
    finally:
        LC.SP_FRY = previous
    for i, case in enumerate(cases):
        case["case_id"] = f"stress_benign/{i}"
        case["sp_profile"] = [(t, min(sp, cap)) for t, sp in case["sp_profile"]]
    if len(cases) != EXPECTED_RUNS:
        raise RuntimeError(f"stress_benign factory changed: {len(cases)} != {EXPECTED_RUNS}")
    return cases


def read_params(lib, handle):
    getter = lib.sim_cc_params
    getter.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_double)]
    getter.restype = ctypes.c_int
    params = {}
    for name in PARAM_NAMES:
        value = ctypes.c_double()
        if getter(handle, name.encode(), ctypes.byref(value)) != 0:
            raise RuntimeError(f"D1 parameter unavailable: {name}")
        if name == "retry_decay_only":
            params[name] = bool(value.value)
        elif name in ("trig_window", "decay_steps"):
            params[name] = int(value.value)
        else:
            params[name] = value.value
    return params


def f32(value):
    return float(np.float32(value))


def slope(values, dt):
    x = np.arange(len(values), dtype=float)
    x -= x.mean()
    y = np.asarray(values, dtype=float)
    return float(x @ (y - y.mean()) / (x @ x) / dt) if len(x) > 1 else 0.0


def summary(values, dt):
    values = np.asarray(values, dtype=float)
    return {"first": float(values[0]), "last": float(values[-1]), "min": float(values.min()),
                "max": float(values.max()), "mean": float(values.mean()), "slope_per_s": slope(values, dt)}


def shape_guard(window, params, retry):
    """Counterfactual rise/curvature evidence for a rejected rule, never active in C."""
    y = np.asarray([r["y_C"] for r in window], dtype=float)
    rim = np.asarray([r["rim_effective_C"] for r in window], dtype=float)
    x = np.linspace(-1.0, 1.0, len(y))
    z = x * x - np.mean(x * x)
    design = np.column_stack([np.ones(len(y)), x, z])
    coef = np.linalg.lstsq(design, y, rcond=None)[0]
    residual = y - design @ coef
    variance = float(residual @ residual) / (len(y) - 3)
    covariance = variance * np.linalg.inv(design.T @ design)
    rise, curve = float(coef[1]), float(coef[2])
    rise_sd, curve_sd = math.sqrt(covariance[1, 1]), math.sqrt(covariance[2, 2])
    half_span = (len(y) - 1) * params["dt_s"] / 2.0
    sigma = params["probe_min_sigma"]
    finite = bool(np.isfinite(y).all() and np.isfinite(rim).all())
    rim_nonincreasing = bool(np.all(np.diff(rim) <= 0.0))
    predicate = (not retry and sigma > 0 and finite and rim_nonincreasing and rise > 0 and curve > 0 and
                 rise >= sigma * rise_sd and curve >= sigma * curve_sd)
    return {"first_probe": not retry, "enabled_by_sigma": sigma > 0, "all_samples_finite": finite,
                "rim_nonincreasing": rim_nonincreasing, "maximum_rim_step_K": float(np.max(np.diff(rim))),
                "rise_coefficient_K": rise, "curve_coefficient_K": curve,
                "rise_standard_error_K": rise_sd, "curve_standard_error_K": curve_sd,
                "rise_sigma": rise / rise_sd if rise_sd > 0 else None,
                "curve_sigma": curve / curve_sd if curve_sd > 0 else None,
                "slope_at_midpoint_K_per_s": rise / half_span,
                "curvature_K_per_s2": 2.0 * curve / half_span ** 2,
                "slope_at_start_K_per_s": (rise - 2.0 * curve) / half_span,
                "slope_at_end_K_per_s": (rise + 2.0 * curve) / half_span,
                "required_sigma": sigma, "predicate": bool(predicate)}


def decision(window, params, retry=False):
    """Reconstruct D1 inputs and a rejected counterfactual; C outputs remain authoritative."""
    dt = params["dt_s"]
    y = np.asarray([r["y_C"] for r in window], dtype=float)
    power = np.asarray([r["p_applied_W"] for r in window], dtype=float)
    n = len(y)
    span = (n - 1) * dt
    lag = params["retry_lag_s" if retry else "probe_lag_s"]
    energy, previous_energy, lagged_energy = 0.0, 0.0, 0.0
    rows = []
    for i, watts in enumerate(power):
        if i:
            lagged_energy += dt / lag * (previous_energy - lagged_energy)
        energy += watts * dt / 1000.0
        previous_energy = energy
        t = i * dt / span
        rows.append([1.0, t, t * t, lagged_energy])
    design = np.asarray(rows)
    # SVD avoids the production normal equations' roundoff; keep both results.
    coef, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
    residual = y - design @ coef
    sse = float(residual @ residual)
    d = float(coef[3])
    sd = math.sqrt(sse / (n - 4) * float(np.linalg.inv(design.T @ design)[3, 3])) if rank == 4 else None
    a = window[-1]["output"]["a"]
    rim = window[-1]["rim_effective_C"]
    d_exp = a * 1000.0
    candidates = []
    for k in range(params["decay_steps"]):
        frac = (1.0 if params["decay_steps"] == 1 else 1.0 - params["decay_tau_tol"] +
                2.0 * params["decay_tau_tol"] * k / (params["decay_steps"] - 1))
        tau = frac * params["decay_tau_s"]
        z = np.exp(-np.arange(n) * dt / tau)
        c0, c1 = np.linalg.lstsq(np.column_stack([np.ones(n), z]), y, rcond=None)[0]
        if abs(c0 - rim) > params["decay_asym_k"]:
            continue
        rms = float(np.sqrt(np.mean((y - (c0 + c1 * z)) ** 2)))
        candidates.append({"tau_s": float(tau), "asymptote_C": float(c0), "initial_amplitude_K": float(c1),
                               "rms_K": rms, "change_K": float(abs(c1) * (1.0 - math.exp(-span / tau))),
                               "direction": "falling" if c1 > 0 else "rising"})
    best = min(candidates, key=lambda candidate: candidate["rms_K"]) if candidates else None
    gain_ok = d >= params["probe_frac"] * d_exp
    sigma_ok = sd is None or params["probe_min_sigma"] <= 0 or d >= params["probe_min_sigma"] * sd
    decays = (best is not None and best["rms_K"] <= params["decay_rms_k"] and
              (retry or best["change_K"] >= params["decay_min_change_k"]))
    contact = gain_ok and sigma_ok or not decays
    path = "retry_decay_only" if retry and params["retry_decay_only"] else "response_or_not_decay"
    if path == "retry_decay_only":
        contact = best is None or best["rms_K"] > params["decay_rms_k"]
    shape = shape_guard(window, params, retry)
    output = window[-1]["output"]
    return {
        "n": n, "dt_s": dt, "lag_s": lag, "a_K_per_J": a, "rim_effective_C": rim, "decision_path": path,
        "C": {"d_K_per_kJ": output["d"], "expected_d_K_per_kJ": output["d_exp"],
               "decay_rms_K": output["decay_rms"], "decay_change_K": output["decay_change"],
               "state": STATE[int(output["cc_state"])], "event": EVENT[int(output["cc_event"])],
               "output": output},
        "independent": {"d_K_per_kJ": d, "expected_d_K_per_kJ": d_exp, "d_standard_error_K_per_kJ": sd,
                         "d_sigma": None if sd is None or sd == 0 else d / sd,
                         "gain_threshold_K_per_kJ": params["probe_frac"] * d_exp,
                         "significance_threshold_K_per_kJ": None if sd is None else params["probe_min_sigma"] * sd,
                         "responds_gain": bool(gain_ok), "responds_significance": bool(sigma_ok),
                         "free_decay": best, "decays": bool(decays), "says_contact_before_shape_guard": bool(contact),
                         "shape_guard": shape, "shape_guard_predicate": shape["predicate"],
                         "shape_guard_would_change_decision": not bool(contact) and shape["predicate"],
                         "rms_fit_residual_K": math.sqrt(sse / n)},
        "summaries": {"y": summary(y, dt), "power": summary(power, dt),
                       "rim": summary([r["rim_effective_C"] for r in window], dt),
                       "t_hat": summary([r["output"]["t_hat"] for r in window], dt)},
        "windows": {"t_s": [r["t_s"] for r in window], "y_C": y.tolist(), "power_applied_W": power.tolist(),
                     "power_next_W": [r["p_next_W"] for r in window],
                     "t_hat_C": [r["output"]["t_hat"] for r in window],
                     "rim_effective_C": [r["rim_effective_C"] for r in window],
                     "true_pan_C": [r["true_pan_C"] for r in window],
                     "true_glass_C": [r["true_glass_C"] for r in window]},
    }


class TraceLib:
    """Forward every call unchanged; capture inputs and read-only diagnostics."""

    def __init__(self, lib):
        self.lib = lib
        self.records = []
        self.params = None
        self.rim = None
        self.forced = False

    def __getattr__(self, name):
        return getattr(self.lib, name)

    def sim_start(self, handle, t0):
        result = self.lib.sim_start(handle, t0)
        if result == 0:
            self.params = read_params(self.lib, handle)
        return result

    def sim_request_probe(self, handle):
        self.forced = True
        return self.lib.sim_request_probe(handle)

    def rim_step(self, *args):
        result = self.lib.rim_step(*args)
        self.rim = list(args[-1])
        return result

    def sim_step(self, handle, y, rim, sp, p_applied, src, fresh, spi_ok, fault_status, out):
        result = self.lib.sim_step(handle, y, rim, sp, p_applied, src, fresh, spi_ok, fault_status, out)
        cs = (ctypes.c_double * len(cosim.CS_OUT))()
        self.lib.sim_cs_stats(handle, cs)
        k = len(self.records)
        self.records.append({
            "k": k, "t_s": round(k * es.DT_CTRL, 1), "y_C": f32(y), "rim_effective_C": f32(rim),
            "sp_C": f32(sp), "p_applied_W": f32(p_applied), "output": dict(zip(cosim.OUT, map(float, out), strict=True)),
            "contact_shift": dict(zip(cosim.CS_OUT, map(float, cs), strict=True)),
            "xcheck": bool(self.lib.sim_xcheck(handle)), "forced": self.forced,
            "rim_state": int(self.rim[0]), "rim_raw_C": self.rim[1], "rim_diag": int(self.rim[2]),
        })
        self.forced = False
        return result

    def sup_step(self, *args):
        result = self.lib.sup_step(*args)
        out = list(args[-1])
        record = self.records[-1]
        record["supervisor"] = {"cut_power": bool(out[0]), "latch": int(out[1]), "rise_K": out[2]}
        record["p_next_W"] = 0.0 if out[0] else record["output"]["p_cmd"]
        return result


def intervals(records, predicate):
    """Command intervals [start, end); the final interval may be censored."""
    result = []
    start = None
    for i, record in enumerate(records):
        on = predicate(record)
        if on and start is None:
            start = i
        if start is not None and (not on or i == len(records) - 1):
            end = i if not on else i + 1
            result.append({"start_s": records[start]["t_s"], "end_s": round(end * es.DT_CTRL, 1),
                               "duration_s": round((end - start) * es.DT_CTRL, 1), "right_censored": bool(on)})
            start = None
    return result


def trigger_window(records, index, params):
    recent = records[max(0, index - params["trig_window"] + 1):index + 1]
    rate = slope([r["output"]["t_hat"] for r in recent], params["dt_s"])
    power = float(np.mean([r["p_applied_W"] for r in recent]))
    return {
        "n": len(recent), "t_hat_slope_K_per_s": rate, "p_mean_W": power,
        "slope_below_threshold": rate < params["trig_rate_k_per_s"],
        "power_above_threshold": power >= params["trig_pmin_frac"] * params["p_max_w"],
        "t_s": [r["t_s"] for r in recent], "t_hat_C": [r["output"]["t_hat"] for r in recent],
        "p_applied_W": [r["p_applied_W"] for r in recent],
    }


def analyse(records, params):
    events, probes, pending = [], [], []
    active = None
    previous = 0
    for i, record in enumerate(records):
        output = record["output"]
        state, event = int(output["cc_state"]), int(output["cc_event"])
        requests = []
        if record["forced"]:
            requests.append("forced")
        if record["xcheck"]:
            requests.append("cross_check")
        if int(record["contact_shift"]["event"]) == 5:
            requests.append("contact_shift_escalation")
        if previous == 0:
            pending.extend({"t_s": record["t_s"], "source": source} for source in requests)
        else:
            # Requests during an active probe/retry are consumed by C that tick.
            pending = []
        if event or state != previous or requests or int(record["contact_shift"]["event"]):
            events.append({
                "t_s": record["t_s"], "event": EVENT[event], "state": STATE[state], "previous_state": STATE[previous],
                "contact_shift_event": cosim.CS_EVT.get(int(record["contact_shift"]["event"]), "none"),
                "xcheck": record["xcheck"], "forced": record["forced"],
                "trigger_window": trigger_window(records, i, params),
                "point": {k: record[k] for k in ("y_C", "rim_effective_C", "sp_C", "p_applied_W", "p_next_W",
                                              "true_pan_C", "true_glass_C", "rim_state", "rim_raw_C")},
                "output": output, "contact_shift": record["contact_shift"], "supervisor": record["supervisor"],
            })
        if event == 1:
            active = {"start_index": i, "start_s": record["t_s"], "retry": False,
                          "trigger_sources": pending[:] or [{"t_s": record["t_s"], "source": "slope_under_power"}],
                          "trigger_window": trigger_window(records, i, params)}
            pending = []
        elif state == 3 and previous == 2:
            active = {"start_index": i, "start_s": record["t_s"], "retry": True,
                          "trigger_sources": [{"t_s": record["t_s"], "source": "retry_timer"}]}
        if active is not None and previous in (1, 3) and state in (0, 2):
            probe = dict(active)
            begin = probe.pop("start_index")
            probe["end_s"] = record["t_s"]
            probe["decision"] = decision(records[begin:i + 1], params, retry=probe["retry"])
            probes.append(probe)
            active = None
        if state != 0:
            pending = []
        previous = state
    if active is not None:
        active = dict(active)
        active.pop("start_index")
        active["right_censored"] = True
        probes.append(active)

    lost = []
    for i, record in enumerate(records):
        if int(record["output"]["cc_event"]) != cosim.CC_EVT_LOST:
            continue
        end = next((j for j in range(i + 1, len(records))
                    if int(records[j]["output"]["cc_event"]) == cosim.CC_EVT_RESTORED), len(records))
        t_end = records[end]["t_s"] if end < len(records) else len(records) * es.DT_CTRL
        initial_zero = i
        while initial_zero > 0 and records[initial_zero - 1]["p_next_W"] == 0:
            initial_zero -= 1
        episode = records[i:end]
        # Actual continuous off time can extend beyond RESTORED when PID still wants zero.
        resumed = next((r["t_s"] for r in records[i:] if r["p_next_W"] > 0), None)
        off_end = resumed if resumed is not None else len(records) * es.DT_CTRL
        probe_index = next(j for j, probe in enumerate(probes) if probe.get("end_s") == record["t_s"])
        lost.append({
            "t_lost_s": record["t_s"], "t_restored_s": None if end == len(records) else t_end,
            "duration_s": round(t_end - record["t_s"], 1), "right_censored": end == len(records),
            "decision_probe_index": probe_index,
            "retry_probe_indices": [j for j, probe in enumerate(probes)
                                 if probe["retry"] and record["t_s"] < probe["start_s"] < t_end],
            "continuous_off_began_s": records[initial_zero]["t_s"], "first_resumed_power_s": resumed,
            "continuous_off_duration_s": round(off_end - records[initial_zero]["t_s"], 1),
            "continuous_off_right_censored": resumed is None,
            "zero_power_after_lost_s": round(es.DT_CTRL * sum(r["p_next_W"] == 0 for r in episode), 1),
            "zero_power_where_PID_wanted_heat_s": round(es.DT_CTRL * sum(
                r["p_next_W"] == 0 and r["output"]["p_pid"] > 0 for r in episode), 1),
        })
    zero = intervals(records, lambda record: record["p_next_W"] == 0)
    return {"events": events, "probes": probes, "lost_episodes": lost, "zero_power_intervals": zero,
                "seconds_power_zero": round(sum(interval["duration_s"] for interval in zero), 1)}


def trace_case(case):
    """Run unchanged LC physics and control; the temporary proxy is restored."""
    original_lib = LC.lib
    proxy = TraceLib(original_lib())
    try:
        LC.lib = lambda: proxy
        result = LC.run_case(dict(case, trace_dt=es.DT_CTRL))
        truth = result.pop("trace")
        result.pop("trace_dt")
        if len(truth) != len(proxy.records):
            raise RuntimeError("Truth and controller trace lengths differ")
        for record, row in zip(proxy.records, truth, strict=True):
            record["true_pan_C"] = float(row[6])
            record["true_glass_C"] = float(row[7])
        return {"case": case, "result": result, "params": proxy.params,
                    "diagnostics": analyse(proxy.records, proxy.params)}
    finally:
        LC.lib = original_lib


def init_worker(lib_path):
    cosim.LIB = None
    cosim.LIB_PATH = str(lib_path)


def run_case(case):
    result = LC.run_case(case)
    detail = None
    if "d1_lost" in result["first"]:
        detail = trace_case(case)
        if detail["result"] != result:
            raise RuntimeError(f"Tracing altered the run: {case['case_id']}")
        if not detail["diagnostics"]["lost_episodes"]:
            raise RuntimeError(f"LOST was not traced: {case['case_id']}")
    return result, detail


def source_hashes():
    inputs = {
        HERE / name for name in ("d1_nuisance.py", "cosim.py", "cosim_shim.c", "ref.py", "leak_checks.py",
                                "rim_limit.py", "xcheck_cosim.py", "rim_ntc.py", "rail_adc.py", "build_lib.sh")
    }
    inputs.update((REPO / "firmware/components/control").glob("*.[ch]"))
    inputs.update((REPO / "firmware/components/sensors").glob("*.c"))
    inputs.update((REPO / "firmware/components/sensors/include").glob("*.h"))
    inputs.update((REPO / "firmware/components/sensors").glob("*.h"))
    inputs.update({
        HERE.parent / "screen.py", HERE.parent / "contact_model.py", HERE.parent / "robustness/shift_kf.py",
        HERE.parent / "cad/thermal-axisym.json", HERE.parent.parent / "temper-sensor-r2/estimator_study.py",
        REPO / "firmware/config.h",
    })
    return {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(inputs)}


def changed_from_base(hashes):
    """Compare actual bytes with the task base, independently of HEAD or dirty state."""
    base_names = set(subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", BASE_REVISION], cwd=REPO, text=True).splitlines())
    changed = []
    for name, digest in sorted(hashes.items()):
        if name not in base_names:
            changed.append(name)
            continue
        original = subprocess.check_output(["git", "show", f"{BASE_REVISION}:{name}"], cwd=REPO)
        if hashlib.sha256(original).hexdigest() != digest:
            changed.append(name)
    return changed


def build_library(directory, supplied=None):
    """A supplied library cannot silently disagree with the recorded source hashes."""
    subprocess.run([str(HERE / "build_lib.sh"), str(directory)], check=True)
    fresh = Path(directory) / "libpantemp.so"
    if supplied is not None:
        supplied = supplied.resolve()
        if hashlib.sha256(supplied.read_bytes()).digest() != hashlib.sha256(fresh.read_bytes()).digest():
            raise RuntimeError(f"--lib does not match the fresh build from current sources: {supplied}")
        return supplied
    return fresh


def toolchain():
    return {"python": platform.python_version(), "numpy": np.__version__,
                "scipy": importlib.metadata.version("scipy"), "matplotlib": importlib.metadata.version("matplotlib"),
                "machine": platform.machine(), "compiler": subprocess.check_output(
                    [*shlex.split(os.environ.get("CC", "cc")), "--version"], text=True).splitlines()[0]}


def comparable(result):
    """Ignore only these six strings in this one metadata object."""
    copy = json.loads(json.dumps(result, allow_nan=False))
    for key in TOOLCHAIN_KEYS:
        if not isinstance(copy["toolchain"][key], str):
            raise ValueError(f"toolchain.{key} must be a string")
        copy["toolchain"][key] = "<toolchain>"
    return json.dumps(copy, sort_keys=True, separators=(",", ":"), allow_nan=False)


def controller_params(lib_path):
    previous_lib, previous_path = cosim.LIB, cosim.LIB_PATH
    try:
        init_worker(lib_path)
        lib = LC.lib()
        handle = lib.sim_new()
        try:
            for key, value in cosim.FW_K.items():
                if lib.sim_set(handle, key.encode(), value) != 0:
                    raise RuntimeError(f"Unknown firmware parameter: {key}")
            if lib.sim_set(handle, b"decay_tau", cosim.FW_K["c_cap"] / cosim.FW_K["g_leak"]) != 0:
                raise RuntimeError("Cannot set LC decay time constant")
            if lib.sim_start(handle, es.T_AMB) != 0:
                raise RuntimeError("Cannot start D1")
            return read_params(lib, handle)
        finally:
            lib.sim_free(handle)
    finally:
        cosim.LIB, cosim.LIB_PATH = previous_lib, previous_path


def run(jobs, lib_path):
    hashes = source_hashes()
    result = {"schema": 1, "toolchain": toolchain(), "base_revision": BASE_REVISION, "source_sha256": hashes,
                  "source_changed_from_base": changed_from_base(hashes),
                  "d1_params": controller_params(lib_path), "caps": {}, "notes": [
        "Every case is the unchanged rim_limit.stress_benign factory, capped with setpoint_cap semantics.",
        "The LC latches remain passive as in leak_checks.run_case; its supervisor still overrides power.",
        "LOST counts are events, not merely affected cases; failed retries remain LOST without a new LOST event.",
        "Probe windows contain every C float32 input (normally 181 samples); C outputs are authoritative.",
        "Independent regressions use SVD; shape-guard predicates describe a rejected counterfactual rule, never active C behavior.",
        "Production D1 is unchanged; C outputs remain authoritative for every probe and retry.",
        "Trace timestamps label the sampled period: applied power precedes the sample; p_next follows it.",
        "Off durations count actual zero commands, including retry off phases; PID-wanted heat is also reported.",
        "A final un-restored LOST or zero interval is right-censored at the case horizon.",
    ]}
    with Pool(jobs, initializer=init_worker, initargs=(str(lib_path),)) as pool:
        for cap in CAPS:
            pairs = list(pool.imap(run_case, capped_cases(cap)))
            rows = [row for row, _ in pairs]
            details = [detail for _, detail in pairs if detail is not None]
            count = sum(len(detail["diagnostics"]["lost_episodes"]) for detail in details)
            passed = count <= LOST_MAX[cap]
            result["caps"][str(cap)] = {"runs": len(rows), "d1_lost_cases": len(details), "d1_lost_events": count,
                                           "lost_max": LOST_MAX[cap], "gate": passed, "rows": rows, "lost_cases": details}
            print(f"D1 cap={cap}: {len(rows)} stress_benign; LOST cases={len(details)} events={count} "
                  f"max={LOST_MAX[cap]} {'PASS' if passed else 'FAIL'}", flush=True)
            for detail in details:
                case = detail["case"]
                for episode in detail["diagnostics"]["lost_episodes"]:
                    probe = detail["diagnostics"]["probes"][episode["decision_probe_index"]]
                    d = probe["decision"]
                    sigma = d["independent"]["d_sigma"]
                    print(f"  LOST cap={cap} {case['case_id']} {case['kind']} {case['pan']} seed={case['seed']} "
                          f"corner={case['corner']} glass_w={case['glass_w']:.6f} tau_g={case['tau_g']} "
                          f"t={episode['t_lost_s']:.1f}s d={d['C']['d_K_per_kJ']:.6f} "
                          f"d_exp={d['C']['expected_d_K_per_kJ']:.6f} sigma={sigma} "
                          f"rms={d['C']['decay_rms_K']:.6f} change={d['C']['decay_change_K']:.6f} "
                          f"off={episode['zero_power_after_lost_s']:.1f}s "
                          f"censored={episode['right_censored']}", flush=True)
    result["gate"] = all(value["gate"] for value in result["caps"].values())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--lib", type=Path)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    with tempfile.TemporaryDirectory(prefix="d1-nuisance-") as tmp:
        lib_path = build_library(tmp, args.lib)
        result = run(args.jobs, lib_path)
    matches = True
    if args.check:
        expected = json.loads(args.out.read_text())
        matches = comparable(result) == comparable(expected)
        print(f"D1 nuisance evidence: {'MATCH' if matches else 'MISMATCH'} "
              "(exact values and source hashes; toolchain strings excluded)")
    else:
        args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
        print(f"Wrote {args.out}")
    passed = result["gate"] and matches
    print(f"D1 NUISANCE {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

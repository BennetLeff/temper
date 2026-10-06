#!/usr/bin/env python3
"""Offline native-20 B0–B4 measurement screens; see bench-verdict.md.

No hardware control. CSV units: seconds, volts, amperes. Exit 0 PASS,
1 FAIL, 2 INVALID. A screen is never permission to energize the assembly.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ADDENDUM = "validation-plan/BENCH-NATIVE20-ADDENDUM.md"
D8 = "validation-results/01-switching-parasitics/round17/delegation/out-D8/README.md"


@dataclass(frozen=True)
class Trace:
    t: tuple[float, ...]
    y: tuple[float, ...]

    def at(self, t: float) -> float:
        if not self.t[0] <= t <= self.t[-1]:
            raise ValueError("capture does not cover requested interval")
        i = min(bisect_right(self.t, t) - 1, len(self.t) - 2)
        return self.y[i] + (self.y[i + 1] - self.y[i]) * (t - self.t[i]) / (self.t[i + 1] - self.t[i])

    def window(self, start: float, end: float) -> Trace:
        if end <= start:
            raise ValueError("empty/reversed window")
        points = [(start, self.at(start))]
        points += [(t, y) for t, y in zip(self.t, self.y) if start < t < end]
        points.append((end, self.at(end)))
        return Trace(tuple(t for t, _ in points), tuple(y for _, y in points))

    def crossings(self, level: float, rising: bool) -> list[float]:
        answer = []
        for i in range(1, len(self.t)):
            a, b = self.y[i - 1:i + 1]
            if (a < level <= b) if rising else (a > level >= b):
                answer.append(self.t[i - 1] + (self.t[i] - self.t[i - 1]) * (level - a) / (b - a))
        return answer

    def edge(self, level: float, rising: bool, start: float, hold: float) -> float:
        """First threshold crossing that remains across it for hold seconds.

        Use interpolation for the crossing; persistence rejects narrow noise.
        Analog peaks are never persistence-filtered.
        """
        for t in self.crossings(level, rising):
            if t < start or t + hold > self.t[-1]:
                continue
            values = self.window(t, t + hold).y
            if (min(values) >= level - 1e-12) if rising else (max(values) <= level + 1e-12):
                return t
        raise ValueError(f"missing sustained {'rising' if rising else 'falling'} edge at {level}")


def load_csv(path: Path) -> dict[str, Trace]:
    with path.open(newline="") as stream:
        reader = csv.reader(stream)
        names = next(reader)
        if not names or names[0] != "time_s" or len(set(names)) != len(names):
            raise ValueError("CSV needs unique columns beginning with time_s")
        rows = []
        for row in reader:
            if len(row) != len(names):
                raise ValueError("ragged CSV row")
            rows.append(tuple(float(v) for v in row))
    if len(rows) < 3 or any(not math.isfinite(v) for row in rows for v in row):
        raise ValueError("capture needs at least three finite samples")
    t = tuple(row[0] for row in rows)
    if any(b <= a for a, b in zip(t, t[1:])):
        raise ValueError("time_s must be strictly increasing")
    return {name: Trace(t, tuple(row[i] for row in rows)) for i, name in enumerate(names) if i}


def recovery(trace: Trace, start: float, end: float, hold: float) -> dict[str, float]:
    wave = trace.window(start, end)
    zero = wave.edge(0, True, start, hold)
    positive = wave.window(zero, end)
    peak = max(positive.y)
    tp = positive.t[positive.y.index(peak)]
    if peak <= 0 or tp <= zero:
        raise ValueError("no resolved recovery peak")
    t10 = positive.edge(0.1 * peak, False, tp, hold)
    charge = positive.window(zero, t10)
    q = sum((b - a) * (max(0, u) + max(0, v)) / 2 for a, b, u, v in
            zip(charge.t, charge.t[1:], charge.y, charge.y[1:]))
    slopes = {}
    for width in (20, 40):
        fit = trace.window(zero - width * 1e-9, zero + width * 1e-9)
        tm, ym = sum(fit.t) / len(fit.t), sum(fit.y) / len(fit.y)
        slopes[f"di_dt_{width}ns_A_per_us"] = sum((t - tm) * (y - ym) for t, y in zip(fit.t, fit.y)) / sum((t - tm)**2 for t in fit.t) * 1e-6
    return {"Qrr_C": q, "Irrm_A": peak, "trr_s": t10 - zero, "ta_s": tp - zero,
            "tb10_s": t10 - tp, "softness": (t10 - tp) / (tp - zero),
            "zero_s": zero, "peak_s": tp, "end10_s": t10, **slopes}


def verdict(raw: dict[str, Trace], meta: dict[str, Any]) -> dict[str, Any]:
    criteria: list[dict[str, Any]] = []
    result: dict[str, Any] = {"schema": 1, "status": "INVALID", "criteria": criteria}
    try:
        if not isinstance(meta, dict):
            raise ValueError("metadata must be an object")
        test = meta["test"]
        result["test"] = test
        if test not in {"B0", "B1", "B2", "B3", "B4"} or meta["leg"] not in {"A", "B"}:
            raise ValueError("unknown test or leg")
        if not math.isfinite(meta["bus_v"]) or meta["bus_v"] < 0:
            raise ValueError("invalid bus_v")
        if meta["capture_ok"] is not True:
            raise ValueError("capture quality/null/overrange checks not confirmed")
        if len(meta["board_manifest_sha256"]) != 64 or any(c not in "0123456789abcdef" for c in meta["board_manifest_sha256"]):
            raise ValueError("board manifest SHA256 required")
        deskew = meta["deskew_s"]
        uncertainty = meta["uncertainty"]
        for name in ("gate_v", "vds_v", "current_a", "offset_v", "timing_s"):
            if not math.isfinite(uncertainty[name]) or uncertainty[name] < 0:
                raise ValueError("nonnegative finite uncertainty required")
        waves = {}
        for name, trace in raw.items():
            delay = deskew[name]
            if not math.isfinite(delay):
                raise ValueError("nonfinite deskew")
            waves[name] = Trace(tuple(t - delay for t in trace.t), trace.y)
        start, end = meta["window_s"]
        if not (math.isfinite(start) and math.isfinite(end) and end > start):
            raise ValueError("invalid window_s")
        hold = meta.get("edge_hold_s", 2e-9)
        if not math.isfinite(hold) or hold <= 0:
            raise ValueError("edge_hold_s must be positive")
        if test != "B0":
            if not math.isfinite(meta["logic_threshold_v"]) or meta["logic_threshold_v"] <= 0:
                raise ValueError("logic_threshold_v must be positive and finite")
        if test in {"B1", "B3"}:
            if not math.isfinite(meta["driver_high_v"]) or meta["driver_high_v"] <= 0:
                raise ValueError("driver_high_v must be positive and finite")
        # Check full requested window after deskew, including every exported channel.
        for wave in waves.values():
            wave.window(start, end)

        def check(name: str, value: float, limit: float | list[float], unit: str,
                  u: float = 0, strict: bool = False, source: str = ADDENDUM) -> None:
            good = limit[0] <= value - u and value + u <= limit[1] if isinstance(limit, list) else (value + u < limit if strict else value + u <= limit)
            if not math.isfinite(value):
                raise ValueError(f"nonfinite {name}")
            criteria.append({"name": name, "status": "PASS" if good else "FAIL", "value": value,
                             "uncertainty": u, "limit": limit, "unit": unit,
                             "operator": "inside" if isinstance(limit, list) else ("<" if strict else "<="), "source": source})

        def edge(name: str, level: float, rising: bool, after: float = start) -> float:
            return waves[name].window(start, end).edge(level, rising, after, hold)

        def delay(name: str, a: float, b: float, limit_ns: float) -> None:
            if b < a:
                raise ValueError(f"{name}: causality reversed after deskew")
            check(name, (b - a) * 1e9, limit_ns, "ns", uncertainty["timing_s"] * 1e9)

        def peak(name: str, a: float = start, b: float = end, absolute: bool = False) -> float:
            values = waves[name].window(a, b).y
            return max(map(abs, values)) if absolute else max(values)

        if test == "B0":
            if meta["bus_v"] != 0:
                raise ValueError("B0 requires zero bus voltage")
            for name in ("r35_kelvin_v", "u5_kelvin_v"):
                check(name, peak(name, absolute=True) * 1000, 2.13, "mV", uncertainty["offset_v"] * 1000)
        elif test == "B1":
            if meta["bus_v"] != 0:
                raise ValueError("B1 requires zero bus voltage")
            p = edge("permit_v", meta["logic_threshold_v"], False)
            g = edge("permit_gate_v", 0.65, False)
            d = edge("dis_v", 2.3, True)
            delay("permit_to_gate", p, g, 181.6)
            delay("gate_to_dis", g, d, 119.1)
            for name in ("out_a_v", "out_b_v"):
                off = edge(name, meta["driver_high_v"] * 0.1, False)
                delay("permit_to_" + name, p, off, 380)
        elif test in {"B2", "B3"}:
            command = edge("incoming_cmd_v", meta["logic_threshold_v"], True)
            stop = command + 0.75e-6
            check("partner_vgs_peak", peak("outgoing_vgs_v", command, stop), 3.0, "V", uncertainty["gate_v"], strict=True, source=D8 if test == "B3" else ADDENDUM)
            if test == "B3":
                out_on = edge("incoming_out_v", meta["driver_high_v"] * 0.1, True)
                check("partner_vgs_output_window", peak("outgoing_vgs_v", out_on, out_on + 0.75e-6), 3.0, "V", uncertainty["gate_v"], strict=True, source=D8)
                for role in ("incoming", "outgoing"):
                    check(role + "_vds_peak", peak(role + "_vds_v"), 520, "V", uncertainty["vds_v"], source=D8)
                    check(role + "_gate_rating", peak(role + "_vgs_v", absolute=True), 20, "V", uncertainty["gate_v"], strict=True, source=D8)
                measurements: dict[str, Any] = {}
                for level in (3.0, 1.9):
                    a = edge("outgoing_vgs_v", level, False)
                    b = edge("incoming_vgs_v", level, True)
                    measurements[f"gate_gap_{level}V_s"] = b - a
                    for role in ("incoming", "outgoing"):
                        measurements[f"{role}_crossings_{level}V_s"] = {direction: waves[role + "_vgs_v"].window(start, end).crossings(level, rising) for direction, rising in (("rise", True), ("fall", False))}
                measurements["output_gap_s"] = out_on - edge("outgoing_out_v", meta["driver_high_v"] * 0.9, False)
                measurements["input_gap_s"] = command - edge("outgoing_cmd_v", meta["logic_threshold_v"], False)
                measurements["recovery"] = recovery(waves["diode_id_a"], command, end, hold)
                result["measurements"] = measurements
                result["recovery_comparison"] = "Measurements only: native S4 is not the 400 V / 58.2 A / 25 C / 100 A/us datasheet coupon."
        else:
            fault = edge("bus_fault_v", meta["logic_threshold_v"], True)
            check("trip_current", waves["load_current_a"].at(fault), [47.54, 97.98], "A", uncertainty["current_a"])
            comp = edge("comparator_v", meta["logic_threshold_v"], False)
            gate = edge("conducting_vgs_v", 3.0, False)
            delay("comparator_to_gate_below_3V", comp, gate, 573)
            if meta["vds_reference"] != "die":
                raise ValueError("B4 die-VDS screen needs die reference or documented de-embedding to die")
            check("die_vds_peak", peak("die_vds_v"), 520, "V", uncertainty["vds_v"])
        result["status"] = "FAIL" if any(c["status"] == "FAIL" for c in criteria) else "PASS"
        result["metadata"] = meta
    except (KeyError, ValueError, TypeError, ZeroDivisionError) as exc:
        result["error"] = str(exc)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("metadata", type=Path)
    args = parser.parse_args()
    try:
        result = verdict(load_csv(args.csv), json.loads(args.metadata.read_text()))
        result["csv_sha256"] = hashlib.sha256(args.csv.read_bytes()).hexdigest()
        result["metadata_sha256"] = hashlib.sha256(args.metadata.read_bytes()).hexdigest()
    except (OSError, ValueError, StopIteration) as exc:
        result = {"status": "INVALID", "error": str(exc)}
    print(json.dumps(result, indent=2, allow_nan=False))
    return {"PASS": 0, "FAIL": 1, "INVALID": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Auditable, unit-explicit primitives for one-off C2 loss analysis.

These are model calculations, not board acceptance rules. Input curves are
digitized *typical* Infineon figures; no function extrapolates them.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MonotoneCurve:
    x: tuple[float, ...]
    y: tuple[float, ...]
    log_x: bool = False

    def __post_init__(self) -> None:
        if len(self.x) < 2 or len(self.x) != len(self.y):
            raise ValueError("curve needs at least two paired points")
        if any(not math.isfinite(v) for v in (*self.x, *self.y)):
            raise ValueError("nonfinite curve point")
        if any(b <= a for a, b in zip(self.x, self.x[1:], strict=False)):
            raise ValueError("curve x must strictly increase")
        if self.log_x and self.x[0] <= 0:
            raise ValueError("logarithmic x must be positive")

    def at(self, value: float) -> float:
        if not math.isfinite(value) or value < self.x[0] or value > self.x[-1]:
            raise ValueError(f"{value} outside curve [{self.x[0]}, {self.x[-1]}]")
        if value == self.x[-1]:
            return self.y[-1]
        lo, hi = 0, len(self.x) - 1
        while hi - lo > 1:
            mid = (hi + lo) // 2
            if self.x[mid] <= value:
                lo = mid
            else:
                hi = mid
        a, b = self.x[lo], self.x[hi]
        if self.log_x:
            a, b, value = math.log(a), math.log(b), math.log(value)
        fraction = (value - a) / (b - a)
        return self.y[lo] + fraction * (self.y[hi] - self.y[lo])


@dataclass(frozen=True)
class InfineonTypicalCurves:
    vf_25c: MonotoneCurve
    vf_125c: MonotoneCurve
    eoss_j: MonotoneCurve

    @classmethod
    def from_csv(cls, vf_csv: Path, eoss_csv: Path) -> InfineonTypicalCurves:
        with vf_csv.open(newline="") as stream:
            vf = list(csv.DictReader(stream))
        with eoss_csv.open(newline="") as stream:
            eoss = list(csv.DictReader(stream))
        if not vf or not eoss:
            raise ValueError("empty manufacturer graph extraction")
        current = tuple(float(row["current_a"]) for row in vf)
        # Eoss(0)=0 is the physical stored-energy origin, separately noted
        # in the graph provenance. The first digitized graph knot is 1 V.
        volts = (0.0, *(float(row["vds_v"]) for row in eoss))
        curves = cls(
            vf_25c=MonotoneCurve(current, tuple(float(row["vf_25c_v"]) for row in vf), True),
            vf_125c=MonotoneCurve(current, tuple(float(row["vf_125c_v"]) for row in vf), True),
            eoss_j=MonotoneCurve(volts, (0.0, *(float(row["eoss_typ_uj"]) * 1e-6 for row in eoss))),
        )
        if abs(curves.vf_25c.at(58.2) - 1.0) > .03:
            raise ValueError("diode curve does not match 58.2 A table point")
        if abs(curves.eoss_j.at(400) / 31.68e-6 - 1) > .01:
            raise ValueError("Eoss curve does not match Co(er) table point")
        return curves


@dataclass(frozen=True)
class DiodeInterval:
    charge_c: float
    dwell_s: float
    energy_25c_j: float
    energy_125c_j: float
    unmodeled_charge_c: float
    right_censored: bool


def integrate_diode_interval(
    time_s: Sequence[float],
    forward_current_a: Sequence[float],
    curves: InfineonTypicalCurves,
    *,
    right_censored: bool = False,
) -> DiodeInterval:
    """Integrate a *physical body-diode probe*, including channel takeover.

    Current below the 0.1 A graph domain contributes known charge but unknown
    heat; it is never silently assigned zero. No external-drain current belongs
    here because that probe contains displacement current.
    """
    if len(time_s) < 2 or len(time_s) != len(forward_current_a):
        raise ValueError("time and forward-current vectors must pair")
    q = dwell = cold = hot = unmodeled_q = 0.0
    graph_min = curves.vf_25c.x[0]
    graph_max = curves.vf_25c.x[-1]
    for t0, t1, i0, i1 in zip(time_s, time_s[1:], forward_current_a, forward_current_a[1:], strict=False):
        if not all(map(math.isfinite, (t0, t1, i0, i1))) or t1 <= t0:
            raise ValueError("invalid diode waveform sample")
        # Split a linearly interpolated sample at every physical/model
        # boundary. Clamping the signed *mean* erases triangular forward
        # charge when a waveform crosses zero inside the sample.
        fractions = [0.0, 1.0]
        if i0 != i1:
            fractions.extend((limit - i0) / (i1 - i0)
                             for limit in (0.0, graph_min, graph_max)
                             if 0 < (limit - i0) / (i1 - i0) < 1)
        fractions.sort()
        for f0, f1 in zip(fractions, fractions[1:], strict=False):
            midpoint = (f0 + f1) / 2
            mid_i = max(0.0, i0 + (i1 - i0) * midpoint)
            dt = (t1 - t0) * (f1 - f0)
            segment_q = mid_i * dt
            q += segment_q
            if graph_min <= mid_i <= graph_max:
                dwell += dt
                cold += curves.vf_25c.at(mid_i) * segment_q
                hot += curves.vf_125c.at(mid_i) * segment_q
            else:
                unmodeled_q += segment_q
    return DiodeInterval(q, dwell, cold, hot, unmodeled_q, right_censored)


@dataclass(frozen=True)
class HardTurnOnScreen:
    eoss_typ_j: float
    snubber_die_vds_proxy_j: float
    reverse_recovery_typ_j: float | None
    reverse_recovery_max_test_j: float | None


def hard_turn_on_screen(
    residual_die_v: float,
    bus_v: float,
    curves: InfineonTypicalCurves,
    *,
    outgoing_diode_forward_observed: bool | None,
    qrr_typ_c: float = 2.30e-6,
    qrr_max_test_c: float = 4.60e-6,
    csnub_f: float = 1e-9,
) -> HardTurnOnScreen:
    """Screen residual energy; Qrr applies only with outgoing diode history.

    Vbus*Qrr transfers the Infineon 400 V/58.2 A/100 A/us test charge to
    this bus as an explicit assumption. It is not a guaranteed energy bound.
    The 1 nF snubber is across the package's external terminals, but this
    screen has only die VDS at channel onset. Thus its .5 C Vdie^2 is a
    voltage-based sensitivity, not measured snubber dissipation. Allocation
    between channel, gate, and series resistance is also unresolved.
    """
    if not math.isfinite(residual_die_v) or not math.isfinite(bus_v) or bus_v < 0:
        raise ValueError("invalid turn-on voltage")
    voltage = max(0.0, residual_die_v)
    eoss = curves.eoss_j.at(voltage)
    snubber = .5 * csnub_f * voltage * voltage
    if outgoing_diode_forward_observed is None:
        qrr_typ = qrr_max = None
    elif outgoing_diode_forward_observed:
        qrr_typ, qrr_max = bus_v * qrr_typ_c, bus_v * qrr_max_test_c
    else:
        qrr_typ = qrr_max = 0.0
    return HardTurnOnScreen(eoss, snubber, qrr_typ, qrr_max)


def line_half_cycle_power(event_energy_j: Sequence[float], half_cycle_s: float = 1 / 120) -> float:
    """Convert one 60 Hz rectified line half-cycle's event energies to W."""
    if half_cycle_s <= 0 or not math.isfinite(half_cycle_s):
        raise ValueError("invalid line half-cycle")
    if any(not math.isfinite(value) or value < 0 for value in event_energy_j):
        raise ValueError("invalid event energy")
    return sum(event_energy_j) / half_cycle_s


def self_test() -> None:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as scratch:
        root = Path(scratch)
        (root / "vf.csv").write_text("current_a,vf_25c_v,vf_125c_v\n0.1,.5,.4\n58.2,1,.8\n150,1.1,.9\n")
        (root / "eoss.csv").write_text("vds_v,eoss_typ_uj\n1,.1\n400,31.68\n490,38\n")
        curves = InfineonTypicalCurves.from_csv(root / "vf.csv", root / "eoss.csv")
    interval = integrate_diode_interval([0, 1e-6, 2e-6], [1, 1, 1], curves)
    assert abs(interval.charge_c - 2e-6) < 1e-15
    assert abs(interval.dwell_s - 2e-6) < 1e-15
    assert interval.energy_25c_j > interval.energy_125c_j > 0
    assert interval.unmodeled_charge_c == 0
    crossing = integrate_diode_interval([0, 1e-6], [-1, 1], curves)
    assert abs(crossing.charge_c - .25e-6) < 1e-15
    screen = hard_turn_on_screen(400, 400, curves, outgoing_diode_forward_observed=True)
    assert abs(screen.eoss_typ_j - 31.68e-6) < 1e-12
    assert abs(screen.snubber_die_vds_proxy_j - 80e-6) < 1e-12
    assert abs(screen.reverse_recovery_typ_j - 920e-6) < 1e-12
    assert abs(line_half_cycle_power([1e-3]) - .12) < 1e-12


if __name__ == "__main__":
    self_test()
    print("loss primitive self-test PASS")

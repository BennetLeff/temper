#!/usr/bin/env python3
# provenance: commit=UNKNOWN dirty=UNKNOWN -- backfilled: predates the evidence-provenance gate and no self-declared commit exists in this file's own content. See .evidence-provenance-allowlist.
"""Measure whether ``_constraint_types`` is a pyo3-pyclass migration candidate.

Wave 4 Phase 2 proposed moving
``packages/temper-placer/src/temper_placer/_constraint_types/`` to Rust as
``#[pyclass]`` contract types, on the premise that doing so stops downstream
marshalling Python objects across the FFI boundary on every call.

This harness tests that premise numerically. It measures three things:

1. The pyo3 boundary floor -- the fixed cost of one FFI crossing, obtained by
   fitting ``sha256_hex`` at two input sizes and extrapolating to zero work.
   sha256 is linear in input length, so the intercept isolates crossing +
   argument conversion + return allocation from the hashing itself.
2. The cost of every genuine compute body in ``_constraint_types``. There are
   five methods; everything else in the package is declarative pydantic field
   schema.
3. The cost of a pydantic attribute read, which is what a ``#[pyclass]``
   ``#[getter]`` would replace.

A method is only worth moving to Rust if its Python cost exceeds the boundary
floor by enough to pay for the crossing. Run it and read the verdict column.

Usage:
    uv run python docs/evidence/2026-08-04-constraint-types-ffi-cost.py
"""

from __future__ import annotations

import argparse
import sys
import timeit

# The boundary floor is measured, not assumed. Any pyo3 entry point that is
# linear in its input works; sha256_hex is the cheapest one exported by a
# built temper extension.
_FFI_PROBE_SETUP = "import temper_design_bundle_python as _t; f = _t.sha256_hex"


def _ns_per_call(stmt: str, setup: str, number: int, repeat: int = 7) -> float:
    """Best-of-`repeat` nanoseconds per call.

    ``min`` rather than ``mean``: the distribution is bounded below by the
    true cost and has an unbounded right tail from scheduler noise, so the
    minimum is the best available estimator of the underlying cost.
    """
    best = min(timeit.repeat(stmt, setup=setup, repeat=repeat, number=number))
    return best / number * 1e9


def measure_ffi_floor() -> float:
    """Fixed cost of one pyo3 crossing, in ns, with the payload work removed."""
    small = _ns_per_call('f(b"x")', _FFI_PROBE_SETUP, number=200_000)
    large = _ns_per_call('f(b"x" * 1024)', _FFI_PROBE_SETUP, number=50_000)
    per_byte = (large - small) / 1023
    return small - per_byte  # intercept: cost at zero payload bytes


# Each entry is (label, stmt, setup, number). The bodies are transcribed
# verbatim from _constraint_types so the measurement is of the real code.
_COMPUTE_SITES: list[tuple[str, str, str, int]] = [
    (
        "PlacementConstraints.get_zone_for_component",
        'd.get("R1")',
        "d = {'R1': 'zoneA'}",
        200_000,
    ),
    (
        "EscapeClearance.compute_clearance",
        "math.sqrt(48) * 0.5 * 1.5",
        "import math",
        200_000,
    ),
    (
        "LossesConfig.get_active_losses",
        "c.get_active_losses()",
        "from temper_placer._constraint_types.config import LossesConfig, LossConfig; "
        "c = LossesConfig(overlap=LossConfig(weight=100.0), "
        "boundary=LossConfig(weight=50.0), wirelength=LossConfig(weight=10.0))",
        50_000,
    ),
    (
        "LossesConfig.get_weights",
        "c.get_weights()",
        "from temper_placer._constraint_types.config import LossesConfig, LossConfig; "
        "c = LossesConfig(overlap=LossConfig(weight=100.0), "
        "boundary=LossConfig(weight=50.0), wirelength=LossConfig(weight=10.0))",
        50_000,
    ),
    (
        "PlacementConstraints.get_net_class",
        'pc.get_net_class("SPI_CLK")',
        "from temper_placer._constraint_types.config import PlacementConstraints; "
        "pc = PlacementConstraints()",
        100_000,
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Fewer iterations; noisier numbers, same ordering.",
    )
    args = parser.parse_args()
    scale = 10 if args.quick else 1

    try:
        floor = measure_ffi_floor()
    except ImportError:
        print(
            "temper_design_bundle_python is not importable; build the Rust "
            "extensions first (uv sync).",
            file=sys.stderr,
        )
        return 2

    attr = _ns_per_call(
        "m.weight",
        "from temper_placer._constraint_types.config import LossConfig; m = LossConfig()",
        number=200_000 // scale,
    )

    print(f"pyo3 boundary floor (fixed cost of one crossing) : {floor:8.1f} ns")
    print(f"pydantic frozen attribute read                   : {attr:8.1f} ns")
    print(f"  -> a #[pyclass] getter replaces a {attr:.1f} ns read with a {floor:.0f} ns crossing")
    print()
    print(f"{'compute site':<46} {'python':>9}  {'vs floor':>9}  verdict")
    print("-" * 86)

    regressions = 0
    for label, stmt, setup, number in _COMPUTE_SITES:
        cost = _ns_per_call(stmt, setup, number=max(number // scale, 1000))
        ratio = cost / floor
        if ratio < 1.0:
            verdict = f"SLOWER in Rust ({1 / ratio:.0f}x)"
            regressions += 1
        elif ratio < 3.0:
            verdict = "no material win"
            regressions += 1
        else:
            verdict = f"candidate ({ratio:.1f}x headroom)"
        print(f"{label:<46} {cost:8.1f}n  {ratio:8.2f}x  {verdict}")

    print()
    print(
        f"{regressions}/{len(_COMPUTE_SITES)} compute sites would not benefit from "
        "crossing the boundary."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

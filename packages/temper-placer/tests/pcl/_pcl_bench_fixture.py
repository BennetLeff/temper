"""Shared fixture for the PCL Wave-4 Phase-2 perf A/B and its parity gate.

PR #714 is the reason this module exists. That migration verified bit-parity
on macOS and passed its differential at iterations ``[0,1,2,8,17,100]``, then
failed on Linux CI because its *benchmark* ran 120 iterations at lr 0.05 --
parameters the differential had never driven. The rule that came out of it:
**any benchmark must be covered by the differential at parameters at least as
extreme.**

The mechanism here is stronger than a convention: ``benchmarks/perf_ab.py``
and ``test_pcl_bench_fixture_parity.py`` both import THIS module, so the
benchmark literally cannot run on inputs the differential has not asserted
parity over. Changing the fixture changes both gates at once.

Neither PCL kernel accumulates across iterations -- ``resolve`` is a boolean
tree walk and ``_parse_distance_with_unit`` is a single multiply -- so there
is no iterative float divergence to compound. That is an argument for why the
#714 failure mode is absent, not a reason to skip the coverage.
"""

from __future__ import annotations

import random

from temper_placer.core.netlist import Component, Netlist

# Fixed shape and seed: an A/B ratio is only comparable across runs if both
# arms see byte-identical input every time.
BENCH_SEED = 20260804
BENCH_COMPONENTS = 400

_TAG_POOL = (
    "power",
    "signal",
    "mechanical",
    "hv",
    "lv",
    "gate_drive",
    "sensor",
    "mcu",
    "connector",
    "mounting",
    "thermal",
    "decoupling",
    "ferrite",
    "all",
    # Deliberate misses and case variants: these exercise the uppercase
    # membership test, the ComponentTag(value) ValueError path, and the
    # hierarchy walk -- i.e. every branch of `resolve`, not just the fast one.
    "BOGUS",
    "Power",
    "HV",
    "",
)


def bench_netlist() -> Netlist:
    """A deterministic 400-component netlist with mixed, misspelt tag sets."""
    rng = random.Random(BENCH_SEED)
    comps = []
    for i in range(BENCH_COMPONENTS):
        n = rng.randint(0, 3)
        tags = frozenset(rng.choice(_TAG_POOL) for _ in range(n))
        comps.append(Component(ref=f"U{i}", footprint="0603", bounds=(5.0, 5.0), tags=tags))
    return Netlist(components=comps, nets=[])


def bench_expr_specs() -> list[tuple]:
    """Expression shapes, in the spec form both namespaces can materialise.

    Depth 4 with mixed AND/OR/NOT: deeper and more branch-diverse than any
    single expression the differential's fixed corpus uses, so the benchmark
    can never reach a shape the parity test has not.
    """
    return [
        ("tag", "POWER"),
        ("tag", "HV"),
        ("ref", "U7"),
        ("not", ("tag", "MCU")),
        ("and", ("tag", "POWER"), ("not", ("tag", "HV"))),
        ("or", ("tag", "SIGNAL"), ("tag", "MECHANICAL")),
        (
            "and",
            ("or", ("tag", "HV"), ("tag", "LV")),
            ("not", ("and", ("tag", "DECOUPLING"), ("ref", "U3"))),
        ),
        (
            "or",
            ("and", ("tag", "ALL"), ("not", ("tag", "FERRITE"))),
            ("not", ("or", ("ref", "U1"), ("ref", "U2"))),
        ),
    ]


def build_expr(spec, ns):
    """Materialise a spec with namespace ``ns`` (live module or oracle)."""
    kind = spec[0]
    if kind == "tag":
        return ns.TagRef(getattr(ns.ComponentTag, spec[1]))
    if kind == "ref":
        return ns.ComponentRef(spec[1])
    if kind == "not":
        return ns.TagNot(build_expr(spec[1], ns))
    if kind == "and":
        return ns.TagAnd(build_expr(spec[1], ns), build_expr(spec[2], ns))
    if kind == "or":
        return ns.TagOr(build_expr(spec[1], ns), build_expr(spec[2], ns))
    raise AssertionError(f"bad spec {spec!r}")


def bench_distance_inputs() -> list:
    """Distance-parse inputs covering every branch the scanner has.

    Includes the Unicode-digit and C0-separator cases and both error paths,
    so the benchmark's cost profile is the real mixed workload rather than
    only the happy path -- and so a regression on any branch shows up.
    """
    rng = random.Random(BENCH_SEED + 1)
    units = ["", "mm", "mil", "in", "cm", "MM", "MIL"]
    values: list = []
    for _ in range(300):
        n = round(rng.uniform(0.0, 500.0), 4)
        values.append(f"{n}{rng.choice(units)}")
    values.extend(
        [
            "  7 mm ",
            "5\tmm",
            "\x1c5\x1c",  # C0 separators are CPython whitespace
            "１０mm",  # fullwidth digits
            "٣mil",  # Arabic-Indic digits
            "-5",  # negative accepted without a unit
            "5m",  # unknown unit -> PCLParseError
            "1e5",  # scientific notation -> unit error
            "",  # bare ValueError
            "-",  # bare ValueError
            0,
            1,
            -3,
            2.5,
            True,
            False,
            float("inf"),
            None,
        ]
    )
    return values


def bench_tier_inputs() -> list:
    return [1, 2, 3, "hard", "STRONG", "soft", "1", 0, 4, True, False, "x", 1.0, None]

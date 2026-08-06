"""Differential test: `py_unpack_2`'s BOUNDED unpack consume (issue #779).

The kernel's 2-target unpack (`x, y = position` in `filter_seed_kernel` and
`max_width, max_height = max_size` in `zone_adjustments_kernel`) must match
CPython's `_PyUnpackIterable` (UNPACK_SEQUENCE): at most THREE items are
consumed — the first two, then a single peek to decide "too many" — and the
iterable is never drained past that. The full-collect implementation this
replaces diverged in two observable ways:

1. **Infinite iterator -> hang.** `x, y = infinite_gen()` raises
   `ValueError: too many values to unpack (expected 2)` in CPython after
   consuming 3 items; the kernel hung forever in `collect`.
2. **Bounded generator over-consumption.** For a 3+ item generator the kernel
   drained all of it; CPython stops at the third peek. Observable with
   side-effecting iterators.

These pins close both gaps on BOTH call sites (seed position and `max_size`):
the side-effect consume count is pinned to exactly 3 (and exactly 2 on the
success path), and the infinite-iterator case is exercised in a
timeout-guarded SUBPROCESS so a regression back to full-collect fails the
test instead of hanging the suite.
"""

from __future__ import annotations

import json
import subprocess
import sys

import temper_design_bundle_python as _tdb
import tests.deterministic._seed_filter_py_oracle as _sf_oracle
import tests.deterministic._zone_adjuster_py_oracle as _za_oracle
from tests.core._contract_canon import canon_call

_DH = _tdb.deterministic_hubs
RS_FILTER = _DH.filter_seed_kernel
RS_ADJUST = _DH.zone_adjustments_kernel

_TOO_MANY = ("raised", "ValueError", "too many values to unpack (expected 2)")


def _oracle_map():
    return _sf_oracle.BottleneckMap(
        cell_size_mm=1.0,
        width=2,
        height=2,
        origin_xy=(0.0, 0.0),
        scores=(0.1, 0.1, 0.1, 0.1),
    )


def _rs_filter(seed, m):
    return RS_FILTER(
        dict(seed),
        m.cell_size_mm,
        m.width,
        m.height,
        m.origin_xy[0],
        m.origin_xy[1],
        list(m.scores),
        0.7,
        0.5,
        set(),
    )


def _rs_adjust(config):
    return RS_ADJUST(["Z"] * 6, config, 5, 0.5)


def _za_violations():
    return [
        _za_oracle.MappedViolation(type="clearance", components=[], zone="Z")
        for _ in range(6)
    ]


def _counting_gen(n, counter):
    def gen():
        for _ in range(n):
            counter["n"] += 1
            yield 0.5

    return gen()


def _za_config(counter):
    return {
        "Z": {
            "bounds": [(0, 0), (10, 10)],
            "max_size": _counting_gen(5, counter),
            "can_expand": ["right"],
        }
    }


# ---------------------------------------------------------------------------
# Inline side-effect pins: a bounded generator is consumed AT MOST 3 items.
# ---------------------------------------------------------------------------


def test_filter_seed_generator_consumes_at_most_three():
    """A 5-item generator position must be consumed exactly through the third
    peek (2 unpacked + 1 too-many peek), never drained to the end, on BOTH
    arms. The full-collect implementation consumed all 5."""
    m = _oracle_map()
    for arm in ("oracle", "shim"):
        counter = {"n": 0}
        pos = _counting_gen(5, counter)
        seed = {"R1": pos}
        if arm == "oracle":
            out = canon_call(_sf_oracle.filter_seed, seed, m, 0.7, 0.5, frozenset())
        else:
            out = canon_call(_rs_filter, seed, m)
        assert counter["n"] == 3, (
            f"{arm} consumed {counter['n']} items, expected 3 (bounded peek)"
        )
        assert out == _TOO_MANY, f"{arm} divergence: {out}"


def test_filter_seed_two_item_generator_consumes_exactly_two():
    """The success path consumes exactly 2 items — no third peek on a
    2-element generator (CPython's `_PyUnpackIterable` only peeks for the
    too-many decision) — and unpacks to a passing score on both arms."""
    m = _oracle_map()
    for arm in ("oracle", "shim"):
        counter = {"n": 0}
        pos = _counting_gen(2, counter)
        seed = {"R1": pos}
        if arm == "oracle":
            out = canon_call(_sf_oracle.filter_seed, seed, m, 0.7, 0.5, frozenset())
        else:
            out = canon_call(_rs_filter, seed, m)
        assert counter["n"] == 2, (
            f"{arm} consumed {counter['n']} items, expected 2"
        )
        # canon(True) is ("bool", True) — bool is checked before int.
        assert out == ("ok", ("bool", True)), f"{arm} divergence: {out}"


def test_max_size_generator_consumes_at_most_three():
    """Same bounded-consume pin on the OTHER call site (`max_size`): a
    5-item generator must stop at the third peek, not be drained, on both
    arms."""
    for arm in ("oracle", "shim"):
        counter = {"n": 0}
        config = _za_config(counter)
        if arm == "oracle":
            adjuster = _za_oracle.ZoneAdjuster(
                config, violation_threshold=5, expansion_per_violation=0.5
            )
            out = canon_call(adjuster.compute_adjustments, _za_violations())
        else:
            out = canon_call(_rs_adjust, config)
        assert counter["n"] == 3, (
            f"{arm} consumed {counter['n']} items, expected 3 (bounded peek)"
        )
        assert out == _TOO_MANY, f"{arm} divergence: {out}"


# ---------------------------------------------------------------------------
# Timeout-guarded subprocess: an infinite iterator raises IMMEDIATELY (never
# hangs) with the oracle's message, on both arms and both call sites.
# ---------------------------------------------------------------------------

# Runs in a fresh interpreter with a hard timeout. If the kernel ever
# regresses to a full `collect`, `itertools.count()` never terminates and the
# subprocess is killed by `timeout=`, failing the test instead of hanging the
# suite. Floats/outcomes are emitted as JSON.
_PAYLOAD = r"""
import json
import itertools

import temper_design_bundle_python as _tdb
import tests.deterministic._seed_filter_py_oracle as _sf
import tests.deterministic._zone_adjuster_py_oracle as _za


def outcome(fn):
    try:
        return ("ok", fn())
    except Exception as exc:  # noqa: BLE001 -- comparing failure modes IS the test
        return ("raised", type(exc).__name__, str(exc))


def oracle_map():
    return _sf.BottleneckMap(
        cell_size_mm=1.0, width=2, height=2, origin_xy=(0.0, 0.0),
        scores=(0.1, 0.1, 0.1, 0.1),
    )


out = {}

# --- seed position: infinite iterator ---------------------------------------
m = oracle_map()
seed = {"R1": itertools.count()}
out["seed_oracle"] = outcome(
    lambda: _sf.filter_seed(seed, m, 0.7, 0.5, frozenset())
)
seed = {"R1": itertools.count()}
out["seed_shim"] = outcome(
    lambda: _tdb.deterministic_hubs.filter_seed_kernel(
        dict(seed), m.cell_size_mm, m.width, m.height, m.origin_xy[0],
        m.origin_xy[1], list(m.scores), 0.7, 0.5, set(),
    )
)

# --- max_size: infinite iterator --------------------------------------------
violations = [
    _za.MappedViolation(type="clearance", components=[], zone="Z") for _ in range(6)
]
config = {
    "Z": {"bounds": [(0, 0), (10, 10)], "max_size": itertools.count(),
          "can_expand": ["right"]},
}
out["max_size_oracle"] = outcome(
    lambda: _za.ZoneAdjuster(config, violation_threshold=5).compute_adjustments(
        violations
    )
)
config = {
    "Z": {"bounds": [(0, 0), (10, 10)], "max_size": itertools.count(),
          "can_expand": ["right"]},
}
out["max_size_shim"] = outcome(
    lambda: _tdb.deterministic_hubs.zone_adjustments_kernel(
        ["Z"] * 6, config, 5, 0.5
    )
)

print(json.dumps(out, sort_keys=True))
"""


def test_infinite_iterator_raises_immediately_not_hangs():
    """An infinite-iterator unpack position (and max_size) raises the oracle's
    `ValueError: too many values to unpack (expected 2)` IMMEDIATELY on both
    arms — the full-collect implementation hung forever. Runs in a subprocess
    under a hard timeout so a regression fails the test rather than hanging
    the suite."""
    proc = subprocess.run(
        [sys.executable, "-c", _PAYLOAD],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, (
        f"infinite-iterator payload failed:\n{proc.stderr[-4000:]}"
    )
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    # every probe must raise the too-many ValueError, and oracle == shim.
    # (json.loads yields lists; the expectation is a tuple.)
    assert tuple(out["seed_oracle"]) == _TOO_MANY, (
        f"oracle seed arm: {out['seed_oracle']}"
    )
    assert tuple(out["seed_shim"]) == _TOO_MANY, f"shim seed arm: {out['seed_shim']}"
    assert tuple(out["max_size_oracle"]) == _TOO_MANY, (
        f"oracle max_size arm: {out['max_size_oracle']}"
    )
    assert tuple(out["max_size_shim"]) == _TOO_MANY, (
        f"shim max_size arm: {out['max_size_shim']}"
    )

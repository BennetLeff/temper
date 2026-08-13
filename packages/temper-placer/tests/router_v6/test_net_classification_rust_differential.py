"""Differential tests: ``router_v6.net_classification``'s Rust-delegating
predicates (``temper_io_types``'s ``is_ground_net``/``is_power_net_v6``/
``is_hv_net``/``is_signal_net_v6``/``classify_net_type_v6`` and the four
``is_*_pin`` bindings) vs the pre-migration Python implementation, the
R19 pinned oracle (see ``docs/plans/2026-08-04-002-docs-temper-goal-set-plan.md``
and ``docs/wave4-verdicts.yaml``'s removal_surfaces entry for this file).

The oracle here is built from ``net_classification._matches_any`` and the
``*_PATTERNS`` constants, which the production module retains verbatim,
unused by any delegating predicate, for exactly this purpose (see that
module's own docstring). This mirrors
``test_routability_check_rust_differential.py`` /
``test_channel_widths_rust_differential.py``'s shape: the pre-migration
logic is pinned in-repo (here: left in place in the production module
rather than copied into the test), and every production predicate is
diffed against it.

``core/net_classification.py`` migrated first (Wave 4 Phase 2) and shares
most of this module's Rust surface: ground/HV net patterns and all four
pin pattern sets are byte-identical between the two Python modules (see
this module's own docstring), so ``temper_io_types.is_ground_net``/
``is_hv_net``/``is_*_pin`` are reused as-is. Only power-net classification
needed a router_v6-specific kernel (``is_power_net_v6``): this module's
``POWER_NET_PATTERNS`` carries four extra entries core's does not
(``"+340V"``/``"DC_BUS"``/``"PWR_RTN"``/``"V_BUS"``), and its
``is_power_net`` adds a "starts with '+'" prefix heuristic core's does
not have.
"""

from __future__ import annotations

import random
import time

import pytest

from temper_placer.router_v6 import net_classification as nc

# ---------------------------------------------------------------------------
# Oracle: the pre-migration predicates, rebuilt from the pinned
# ``_matches_any``/``*_PATTERNS`` the production module retains for this
# purpose (R19). Does NOT call any of the production module's own
# (now Rust-delegating) is_*/classify_net_type functions.
# ---------------------------------------------------------------------------


def _oracle_is_ground_net(name: str, *, single_layer_mode: bool = False) -> bool:
    if single_layer_mode:
        return False
    # boundary="_-": 2026-08-13 hyphen-boundary fix -- see net_classification's
    # own bug-history note. Net-name patterns treat "-" as a boundary too.
    return nc._matches_any(name, nc.GROUND_NET_PATTERNS, boundary="_-")


def _oracle_is_power_net(name: str, *, single_layer_mode: bool = False) -> bool:
    if single_layer_mode:
        return False
    upper = name.upper()
    if nc._matches_any(upper, nc.POWER_NET_PATTERNS, boundary="_-"):
        return True
    return upper.startswith("+")


def _oracle_is_hv_net(name: str, *, single_layer_mode: bool = False) -> bool:
    if single_layer_mode:
        return False
    return nc._matches_any(name, nc.HV_NET_PATTERNS, boundary="_-")


def _oracle_is_signal_net(name: str, *, single_layer_mode: bool = False) -> bool:
    return not (
        _oracle_is_ground_net(name, single_layer_mode=single_layer_mode)
        or _oracle_is_power_net(name, single_layer_mode=single_layer_mode)
        or _oracle_is_hv_net(name, single_layer_mode=single_layer_mode)
    )


def _oracle_classify_net_type(name: str, *, single_layer_mode: bool = False) -> str:
    if _oracle_is_ground_net(name, single_layer_mode=single_layer_mode):
        return "ground"
    if _oracle_is_power_net(name, single_layer_mode=single_layer_mode):
        return "power"
    if _oracle_is_hv_net(name, single_layer_mode=single_layer_mode):
        return "hv"
    return "signal"


def _oracle_is_ground_pin(pin_name: str) -> bool:
    return nc._matches_any(pin_name, nc.GROUND_PIN_PATTERNS)


def _oracle_is_power_pin(pin_name: str) -> bool:
    return nc._matches_any(pin_name, nc.POWER_PIN_PATTERNS)


def _oracle_is_hv_pin(pin_name: str) -> bool:
    return nc._matches_any(pin_name, nc.HV_PIN_PATTERNS)


def _oracle_is_clock_pin(pin_name: str) -> bool:
    return nc._matches_any(pin_name, nc.CLOCK_PIN_PATTERNS)


# ---------------------------------------------------------------------------
# Corpus: curated names covering every pattern, every precedence edge, the
# '+' prefix heuristic, the four router_v6-only power patterns, and the
# word-boundary substring trap ("PE" in "SPEED"/"TYPE" must NOT match).
# ---------------------------------------------------------------------------

NAME_CORPUS: tuple[str, ...] = (
    "GND", "PGND", "CGND", "AGND", "DGND", "VSS", "gnd", "Gnd_1",
    "+3V3", "+5V", "+12V", "+15V", "VCC", "VDD", "VBUS",
    "+340V", "DC_BUS", "PWR_RTN", "V_BUS",  # router_v6-only power patterns
    "+24V", "+", "+_FOO",  # '+' prefix heuristic, no declared pattern match
    "AC_L", "AC_N", "PE", "DC_BUS+", "DC_BUS-", "SW_NODE",
    "SPEED", "TYPE", "OPEN", "EXPECT", "PERIPHERAL",  # "PE" substring trap
    "SDA", "SCL", "MISO", "MOSI", "RANDOM_NET", "",
    "GND_PE",  # matches both ground and hv -- precedence edge
    "VCC_AC_L",  # matches both power and hv -- precedence edge
    "GND\n", "GND\n\n", "GND_\n", "\nGND",  # trailing-newline trap
    "ß_gnd", "ı_gnd", "gndı",  # unicode case folding
)

PIN_NAME_CORPUS: tuple[str, ...] = (
    "GND", "VSS", "AGND", "DGND", "PGND", "CGND",
    "VCC", "VDD", "VIN", "VOUT", "PVCC", "VBUS", "PWR",
    "AC_L", "AC_N", "PE", "HV", "MAINS", "RECT",
    "CLK", "CLOCK", "XTAL1", "XTAL2", "OSC_IN", "OSC_OUT",
    "SPEED", "TYPE", "SDA", "SCL", "",
)

_NET_PREDICATES = (
    ("is_ground_net", _oracle_is_ground_net),
    ("is_power_net", _oracle_is_power_net),
    ("is_hv_net", _oracle_is_hv_net),
    ("is_signal_net", _oracle_is_signal_net),
)

_PIN_PREDICATES = (
    ("is_ground_pin", _oracle_is_ground_pin),
    ("is_power_pin", _oracle_is_power_pin),
    ("is_hv_pin", _oracle_is_hv_pin),
    ("is_clock_pin", _oracle_is_clock_pin),
)


@pytest.mark.parametrize(("fn_name", "oracle_fn"), _NET_PREDICATES)
def test_net_predicates_match_oracle_curated(fn_name, oracle_fn):
    prod_fn = getattr(nc, fn_name)
    for name in NAME_CORPUS:
        assert prod_fn(name) == oracle_fn(name), f"{fn_name}({name!r})"


def test_classify_net_type_matches_oracle_curated():
    for name in NAME_CORPUS:
        assert nc.classify_net_type(name) == _oracle_classify_net_type(name), name


@pytest.mark.parametrize(("fn_name", "oracle_fn"), _PIN_PREDICATES)
def test_pin_predicates_match_oracle_curated(fn_name, oracle_fn):
    prod_fn = getattr(nc, fn_name)
    for pin_name in PIN_NAME_CORPUS:
        assert prod_fn(pin_name) == oracle_fn(pin_name), f"{fn_name}({pin_name!r})"


def _random_names(rng: random.Random, n: int) -> list[str]:
    stems = [
        "GND", "PGND", "VCC", "+3V3", "+340V", "DC_BUS", "PWR_RTN", "V_BUS",
        "AC_L", "PE", "SW_NODE", "SPEED", "TYPE", "SDA", "SCL", "MISO",
        "+24V", "+", "RANDOM",
    ]
    suffixes = ["", "_1", "2", "_BUS", "X", "\n", "_PE", "_GND"]
    return [f"{rng.choice(stems)}{rng.choice(suffixes)}" for _ in range(n)]


def test_net_predicates_match_oracle_random_sweep():
    rng = random.Random(20260807)
    names = _random_names(rng, 500)
    for name in names:
        for fn_name, oracle_fn in _NET_PREDICATES:
            prod_fn = getattr(nc, fn_name)
            assert prod_fn(name) == oracle_fn(name), f"{fn_name}({name!r})"
        assert nc.classify_net_type(name) == _oracle_classify_net_type(name), name


def test_corpus_is_not_degenerate():
    """Anti-vacuity: the corpus must exercise every classification outcome
    and at least one ground/power and ground/hv precedence collision."""
    outcomes = {nc.classify_net_type(n) for n in NAME_CORPUS}
    assert outcomes == {"ground", "power", "hv", "signal"}

    assert nc.is_ground_net("GND_PE") and nc.is_hv_net("GND_PE"), (
        "corpus never exercises the ground vs hv precedence edge"
    )
    assert nc.classify_net_type("GND_PE") == "ground"

    assert nc.is_power_net("VCC_AC_L") and nc.is_hv_net("VCC_AC_L"), (
        "corpus never exercises the power vs hv precedence edge"
    )
    assert nc.classify_net_type("VCC_AC_L") == "power"

    # The router_v6-only power patterns and the '+' prefix heuristic are
    # both actually exercised, not just declared.
    for extra in ("+340V", "DC_BUS", "PWR_RTN", "V_BUS"):
        assert nc.is_power_net(extra), f"{extra!r} must be power (router_v6-only pattern)"
    assert nc.is_power_net("+24V"), "'+' prefix heuristic must classify as power"
    assert not nc.is_power_net("24V+"), "prefix heuristic must not match a trailing '+'"

    # The word-boundary substring trap: "PE" must not match as a bare
    # substring of "SPEED"/"TYPE".
    for false_positive in ("SPEED", "TYPE", "OPEN", "EXPECT", "PERIPHERAL"):
        assert not nc.is_hv_net(false_positive), false_positive


def test_pattern_constants_did_not_drift_from_rust():
    """The Rust holds its own copy of the pattern sets this module declares
    (netclass.rs's GROUND_NET_PATTERNS/HV_NET_PATTERNS/*_PIN_PATTERNS and
    POWER_NET_PATTERNS_V6). Every declared pattern must round-trip through
    the delegating predicate that owns it."""
    import temper_io_types as rs

    for patterns, predicate in (
        (nc.GROUND_NET_PATTERNS, rs.is_ground_net),
        (nc.POWER_NET_PATTERNS, rs.is_power_net_v6),
        (nc.HV_NET_PATTERNS, rs.is_hv_net),
        (nc.GROUND_PIN_PATTERNS, rs.is_ground_pin),
        (nc.POWER_PIN_PATTERNS, rs.is_power_pin),
        (nc.HV_PIN_PATTERNS, rs.is_hv_pin),
        (nc.CLOCK_PIN_PATTERNS, rs.is_clock_pin),
    ):
        for p in patterns:
            assert predicate(p), f"Rust does not recognise declared pattern {p!r}"


def test_single_layer_mode_forces_signal_for_every_corpus_name():
    """``_SINGLE_LAYER_MODE`` gating happens in the Python wrapper, not the
    Rust kernel -- confirm it still short-circuits every predicate,
    including the composed ones (``is_signal_net``/``classify_net_type``),
    for the full corpus."""
    nc.set_single_layer_mode(True)
    try:
        for name in NAME_CORPUS:
            assert nc.is_ground_net(name) is False, name
            assert nc.is_power_net(name) is False, name
            assert nc.is_hv_net(name) is False, name
            assert nc.is_signal_net(name) is True, name
            assert nc.classify_net_type(name) == "signal", name
    finally:
        nc.set_single_layer_mode(False)
    assert nc._SINGLE_LAYER_MODE is False


# ---------------------------------------------------------------------------
# R1b: performance A/B. Both arms are diffed through the oracle first --
# a speedup measured against a kernel computing something else is not a
# speedup (see test_core_contracts_perf.py, the established pattern for
# this repo's net-classification migrations).
# ---------------------------------------------------------------------------

PERF_NAME_COUNT = 4000
_REPEATS = 3


def _best(fn, repeats: int = _REPEATS):
    best = float("inf")
    result = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        result = fn()
        best = min(best, time.perf_counter() - t0)
    return best, result


def _report(label: str, py_s: float, rs_s: float) -> str:
    ratio = py_s / rs_s if rs_s > 0 else float("inf")
    line = f"{label}: python {py_s * 1e3:.3f} ms, rust {rs_s * 1e3:.3f} ms, {ratio:.2f}x"
    print(line)
    return line


def test_perf_classify_net_type():
    rng = random.Random(4242)
    names = _random_names(rng, PERF_NAME_COUNT)
    py_s, py_r = _best(lambda: [_oracle_classify_net_type(n) for n in names])
    rs_s, rs_r = _best(lambda: [nc.classify_net_type(n) for n in names])
    assert rs_r == py_r, "classify_net_type parity"
    _report(f"classify_net_type x{PERF_NAME_COUNT}", py_s, rs_s)


def test_perf_is_power_net():
    rng = random.Random(2718)
    names = _random_names(rng, PERF_NAME_COUNT)
    py_s, py_r = _best(lambda: [_oracle_is_power_net(n) for n in names])
    rs_s, rs_r = _best(lambda: [nc.is_power_net(n) for n in names])
    assert rs_r == py_r, "is_power_net parity"
    _report(f"is_power_net x{PERF_NAME_COUNT}", py_s, rs_s)

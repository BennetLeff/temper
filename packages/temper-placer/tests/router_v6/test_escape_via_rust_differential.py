"""R1a differential: ``router_v6/escape_via_generator`` vs its pinned oracle (cluster G, split).

**THIS SUITE IS DELIBERATELY RED.**  Gate G1 requires the differential that
pins the pre-migration implementation verbatim to exist and fail *before* the
Rust exists; every comparison resolves its Rust arm through
``tests/router_v6/_pending_rust.rust`` and fails with a named
``PendingRustError`` until Phase B supplies the pyfunction.

Arms
----
* **oracle** -- ``tests/router_v6/_escape_via_py_oracle.py``, a verbatim
  ``git show`` copy of ``escape_via_generator.py`` at
  ``143752893c177dc976da614566c64e4e53e4951f`` (``origin/main``).
* **rust** -- the pyfunctions Phase B will add, listed in
  :data:`REQUIRED_RUST_SYMBOLS` and bound in the adapter block below.

Comparison is by type-carrying signature (``tests/router_v6/_signature``).
**No tolerance anywhere** -- gate G2.  Exceptions are compared as values.

Traps this file pins explicitly
-------------------------------
``rotate_local_to_world`` is CPython's ``math.cos``/``math.sin`` -- host-libm
symbols, not ``f64::cos``/``f64::sin`` (B1).  A dlsym-free Rust mirror is
1 ulp out, and the corpus's non-quadrant rotation rows are where that becomes
observable (:func:`test_trap_rotation_uses_host_libm_trig`).

``math.sqrt((x - px) ** 2 + (y - py) ** 2)`` is two libm ``pow`` calls then
``sqrt``, and disagrees with ``math.hypot`` on ~17% of random pairs
(:func:`test_trap_sqrt_pow_form_is_not_hypot`) (B7/B6).

``angle = rot * math.pi / 2.0`` is measured **not** to be the B2 trap:
division by ``2.0`` is exact, so all three spellings agree
(:func:`test_trap_pi_over_two_is_exact_here`).  Recorded as a measured
non-divergence.

``dist < required - 0.001`` is **False** for NaN, so a NaN candidate is
ACCEPTED (:func:`test_nan_pitch_emits_nan_positioned_vias`).

Defect repaired since the first pin
-----------------------------------
D4: every via was labelled ``F.Cu`` regardless of the component's side,
because ``getattr(component, "side", 0)`` read an attribute ``Component``
does not have (the field is ``initial_side``).  **Repaired by #760**
(``aebaecd99``), and the oracle re-pinned onto the repaired module at
``143752893``.  The defect pin was inverted rather than deleted --
:func:`test_repaired_d4_layer_follows_the_component_side` now asserts the
layer *does* follow the side, so a re-introduction fails here.  See the
oracle header for the measurement on both sides of the repair.
"""

from __future__ import annotations

import ast
import math
import random
import subprocess

import pytest

import tests.router_v6._escape_via_py_oracle as ORACLE
from tests.router_v6._escape_via_builders import (
    build_component,
    build_dense_package,
    build_design_rules,
    build_pads,
)
from tests.router_v6._escape_via_cases import (
    BENCH_PACKAGES,
    BENCH_RULE_SETS,
    PACKAGES,
    RULE_SETS,
    STRATEGIES,
    VALID_PROBES,
    random_packages,
)
from tests.router_v6._pending_rust import missing_symbols, rust
from tests.router_v6._signature import sig

# ===========================================================================
# ADAPTER BLOCK -- the ONLY part of this file that knows the Rust arm exists.
# Phase B binds these; no assertion and no corpus row below changes.
# ===========================================================================

#: Migration target.  The kernel is a clearance predicate over pad geometry,
#: which is ``temper-geometry``'s subject (``clearance_geometry.rs``,
#: ``pad_geometry.rs``, and the ``dlsym`` libm helpers this kernel needs are
#: already there).  See the oracle header for why it should extend that
#: crate rather than found a "cluster G" one.
_RUST_MODULE = "temper_geometry"

REQUIRED_RUST_SYMBOLS: tuple[str, ...] = (
    "escape_generate_vias_py",
    "escape_is_position_valid_py",
)


def _rust(symbol: str):
    return rust(_RUST_MODULE, symbol)


# ===========================================================================
# END ADAPTER BLOCK
# ===========================================================================

_ORACLE_PIN_SHA = "143752893c177dc976da614566c64e4e53e4951f"
_ORACLE_NAMES: tuple[str, ...] = ("EscapeVia", "generate_escape_vias", "_is_position_valid")


def _capture(fn):
    try:
        return fn()
    except BaseException as exc:  # noqa: BLE001 - error parity is the point
        return exc


def _assert_same(label: str, oracle_fn, symbol: str, rust_fn):
    """The oracle arm runs first, so a broken oracle fails with its own error."""
    a = _capture(oracle_fn)
    fn = _rust(symbol)  # RED until Phase B lands
    b = _capture(lambda: rust_fn(fn))
    assert sig(a) == sig(b), f"{label}: oracle={a!r} rust={b!r}"


def _vias_as_data(vias):
    return [
        (v.position, v.net_name, v.pin_number, v.diameter, v.drill, v.via_type, v.layer)
        for v in vias
    ]


# ---------------------------------------------------------------------------
# G1 evidence
# ---------------------------------------------------------------------------


def _segments_from_source(src: str, names: tuple[str, ...]) -> dict[str, str]:
    tree = ast.parse(src)
    lines = src.splitlines()
    out: dict[str, str] = {}
    for node in tree.body:
        nm = getattr(node, "name", None)
        if nm in names:
            decos = getattr(node, "decorator_list", [])
            start = (min(d.lineno for d in decos) if decos else node.lineno) - 1
            out[nm] = "\n".join(lines[start : node.end_lineno])
    return out


def test_oracle_is_verbatim_copy():
    """Every definition in the oracle is character-identical to the pin."""
    rel = "packages/temper-placer/src/temper_placer/router_v6/escape_via_generator.py"
    try:
        src = subprocess.run(
            ["git", "show", f"{_ORACLE_PIN_SHA}:{rel}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover
        pytest.skip(f"pinned commit {_ORACLE_PIN_SHA} not present in this clone")

    original = _segments_from_source(src, _ORACLE_NAMES)
    with open(ORACLE.__file__, encoding="utf-8") as fh:
        copied = _segments_from_source(fh.read(), _ORACLE_NAMES)

    for name in _ORACLE_NAMES:
        assert name in copied, f"{name} missing from the oracle module"
        assert name in original, f"{name} missing from escape_via_generator.py at the pin"
        assert copied[name] == original[name], (
            f"escape_via_generator.py::{name} in the oracle is NOT verbatim -- "
            f"the pin is broken and the differential proves nothing"
        )


def test_rust_symbols_exist():
    """The Phase-B checklist.  RED until every kernel is ported."""
    missing = missing_symbols(_RUST_MODULE, REQUIRED_RUST_SYMBOLS)
    assert not missing, (
        f"{_RUST_MODULE} is missing {len(missing)} of {len(REQUIRED_RUST_SYMBOLS)} "
        f"escape_via kernels: {missing}"
    )


def test_bench_corpus_is_covered_by_differential():
    """Every benchmark row is a row the differential already compares."""
    assert BENCH_PACKAGES, "BENCH_PACKAGES is empty -- vacuous containment"
    assert BENCH_RULE_SETS, "BENCH_RULE_SETS is empty -- vacuous containment"
    for p in BENCH_PACKAGES:
        assert p in PACKAGES, f"BENCH_PACKAGES row {p[0]!r} absent from PACKAGES"
    for r in BENCH_RULE_SETS:
        assert r in RULE_SETS, f"BENCH_RULE_SETS row {r[0]!r} absent from RULE_SETS"


# ---------------------------------------------------------------------------
# generate_escape_vias
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("package", PACKAGES, ids=lambda p: p[0])
@pytest.mark.parametrize("strategy", ["dog-bone", "via-in-pad"])
def test_generate_escape_vias_bit_exact(package, strategy):
    rules_case = RULE_SETS[0]
    _assert_same(
        f"generate_escape_vias[{package[0]}, {strategy}]",
        lambda: _vias_as_data(
            ORACLE.generate_escape_vias(
                build_dense_package(package), build_design_rules(rules_case), strategy
            )
        ),
        "escape_generate_vias_py",
        lambda fn: fn(package[1:], rules_case[1:], strategy),
    )


@pytest.mark.parametrize("rules_case", RULE_SETS, ids=lambda r: r[0])
def test_generate_escape_vias_across_rule_sets(rules_case):
    package = next(p for p in PACKAGES if p[0] == "bga3_pitch_1p27")
    _assert_same(
        f"generate_escape_vias[rules={rules_case[0]}]",
        lambda: _vias_as_data(
            ORACLE.generate_escape_vias(
                build_dense_package(package), build_design_rules(rules_case), "dog-bone"
            )
        ),
        "escape_generate_vias_py",
        lambda fn: fn(package[1:], rules_case[1:], "dog-bone"),
    )


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_generate_escape_vias_strategy_dispatch(strategy):
    """Unknown strategies fall through both branches and return ``[]``.

    There is no ``else``, so a typo is silent.  Pinned as behaviour.
    """
    package = next(p for p in PACKAGES if p[0] == "bga3_pitch_1p27")
    _assert_same(
        f"generate_escape_vias[strategy={strategy!r}]",
        lambda: _vias_as_data(
            ORACLE.generate_escape_vias(
                build_dense_package(package), build_design_rules(RULE_SETS[0]), strategy
            )
        ),
        "escape_generate_vias_py",
        lambda fn: fn(package[1:], RULE_SETS[0][1:], strategy),
    )


@pytest.mark.parametrize("seed", [21, 22])
def test_generate_escape_vias_random_sweep(seed):
    rules = build_design_rules(RULE_SETS[0])
    for position, rotation, pitch, pins in random_packages(seed, 25):
        case = ("random", position, rotation, 0, pitch, "BGA", pins)
        _assert_same(
            f"random package seed={seed} pitch={pitch}",
            lambda c=case: _vias_as_data(
                ORACLE.generate_escape_vias(build_dense_package(c), rules, "dog-bone")
            ),
            "escape_generate_vias_py",
            lambda fn, c=case: fn(c[1:], RULE_SETS[0][1:], "dog-bone"),
        )


# ---------------------------------------------------------------------------
# _is_position_valid
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("probe", VALID_PROBES, ids=lambda p: p[0])
def test_is_position_valid_bit_exact(probe):
    label, x, y, radius, clearance, pads = probe
    _assert_same(
        f"_is_position_valid[{label}]",
        lambda: ORACLE._is_position_valid(
            x, y, radius, build_pads(pads), (0.0, 0.0), 0.0, clearance, _ignore_net=None
        ),
        "escape_is_position_valid_py",
        lambda fn: fn(x, y, radius, pads, clearance),
    )


def test_is_position_valid_ignores_its_ignore_net_argument():
    """``_ignore_net`` is underscore-prefixed and never read.

    Green today.  This is deliberate per the module's own inline comment
    ("If it overlaps source pin, it's effectively Via-in-Pad, not Dog-Bone"),
    so it is asserted as a *contract* rather than reported as a defect --
    the Rust mirror must not "helpfully" honour the argument.
    """
    pads = [(0.0, 0.0, 0.4, 0.4, "circle")]
    comp = build_pads(pads)
    results = {
        ORACLE._is_position_valid(0.1, 0.0, 0.225, comp, (0.0, 0.0), 0.0, 0.15, _ignore_net=v)
        for v in (None, "", "N0", "SOMETHING_ELSE")
    }
    assert results == {False}, f"_ignore_net changed the outcome: {results}"


def test_is_position_valid_short_circuits_on_the_first_failing_pad():
    """The scan returns on the first violating pad, so pad ORDER is
    observable through the number of distance computations even though the
    boolean result is order-independent."""
    first = next(p for p in VALID_PROBES if p[0] == "first_pad_fails")
    last = next(p for p in VALID_PROBES if p[0] == "last_pad_fails")
    a = ORACLE._is_position_valid(
        first[1], first[2], first[3], build_pads(first[5]), (0.0, 0.0), 0.0, first[4]
    )
    b = ORACLE._is_position_valid(
        last[1], last[2], last[3], build_pads(last[5]), (0.0, 0.0), 0.0, last[4]
    )
    assert a is False
    assert b is False
    # an empty pad list can only be True -- the loop body never runs
    assert ORACLE._is_position_valid(0.0, 0.0, 1.0, build_pads([]), (0.0, 0.0), 0.0, 1.0) is True


# ---------------------------------------------------------------------------
# The repaired defect (was pinned unfixed; now inverted) and the pinned NaN
# contract
# ---------------------------------------------------------------------------


def test_repaired_d4_layer_follows_the_component_side():
    """D4, REPAIRED by #760 (``aebaecd99``): the layer now tracks the side.

    **Was:** ``side = getattr(component, "side", 0) or 0`` read an attribute
    ``Component`` does not have -- the field is ``initial_side`` -- so the
    default fired unconditionally and ``side_to_layer_name(0)`` always
    returned ``'F.Cu'``.  A back-side component got pad coordinates that ARE
    mirrored and vias that were labelled front: the two halves of the same
    via disagreed.

    **Now:** ``side = component.initial_side or 0``.

    This is the *inversion* of the old defect pin, not its deletion.  It
    fails if the ``getattr`` form -- or any other side-blind resolution --
    comes back, which is the whole regression value the old pin had and the
    only thing that would catch a re-introduction.

    ``Component`` still has no ``side`` attribute; that is asserted, because
    a future ``side`` field would make the old ``getattr`` spelling start
    working again and quietly mask a regression here.
    """
    from temper_placer.core.netlist import Component

    assert not hasattr(
        Component(
            ref="X",
            footprint="F",
            bounds=(1.0, 1.0),
            pins=[],
            initial_position=(0.0, 0.0),
        ),
        "side",
    ), (
        "Component gained a `side` attribute -- the old `getattr(component, "
        '"side", 0)` spelling would now silently work; re-derive D4 before '
        "trusting this test"
    )

    rules = build_design_rules(RULE_SETS[0])
    layers_by_side = {}
    positions_by_side = {}
    for label in ("side_0", "side_1_back", "side_none"):
        case = next(p for p in PACKAGES if p[0] == label)
        vias = ORACLE.generate_escape_vias(build_dense_package(case), rules, "via-in-pad")
        assert vias, f"{label} produced no vias -- the case stopped exercising the path"
        layers_by_side[label] = {v.layer for v in vias}
        positions_by_side[label] = [v.position for v in vias]

    # `initial_side=None` short-circuits through the `or` to 0; that default
    # is pre-existing and D4 did not change it.
    assert layers_by_side == {
        "side_0": {"F.Cu"},
        "side_1_back": {"B.Cu"},
        "side_none": {"F.Cu"},
    }, f"the escape-via layer no longer follows initial_side: {layers_by_side}"

    # ... and the geometry still responds to the side.  Before the repair this
    # assertion was what made the mislabelling *wrong* rather than merely
    # unused; it is kept because label and geometry must now agree, and a
    # regression in either one alone breaks that agreement.
    assert positions_by_side["side_0"] != positions_by_side["side_1_back"], (
        "pad coordinates no longer differ by side -- the layer label and the "
        "geometry are no longer two independent witnesses of the same fact"
    )


def test_nan_pitch_emits_nan_positioned_vias():
    """``dist < required - 0.001`` is False for NaN, so NaN is ACCEPTED.

    A ``DensePackage`` with ``pitch_mm = NaN`` therefore yields one via per
    netted pad, each at ``(nan, nan)``.  A Rust mirror that early-returns on
    NaN, or that flips the test to ``!(dist >= required)``, produces a
    different count.
    """
    case = next(p for p in PACKAGES if p[0] == "pitch_nan")
    vias = ORACLE.generate_escape_vias(
        build_dense_package(case), build_design_rules(RULE_SETS[0]), "dog-bone"
    )
    assert len(vias) == 9, f"expected 9 NaN-positioned vias, got {len(vias)}"
    assert all(math.isnan(v.position[0]) and math.isnan(v.position[1]) for v in vias)

    # the same input under via-in-pad is unaffected: the pitch is not read
    in_pad = ORACLE.generate_escape_vias(
        build_dense_package(case), build_design_rules(RULE_SETS[0]), "via-in-pad"
    )
    assert all(math.isfinite(v.position[0]) for v in in_pad)


def test_dog_bone_feasibility_cliff_is_where_the_corpus_says():
    """The pitches straddling the dog-bone cliff, measured.

    With the default rule set the required separation is
    ``0.225 + 0.2 + 0.15 = 0.575`` and the candidate sits at
    ``pitch / 2 * sqrt(2)`` from its own pad, so placement fails below
    ~0.813 mm pitch.  Green today; it is asserted because the corpus's claim
    to cover "both sides of the cliff" is only true if this holds.
    """
    rules = build_design_rules(RULE_SETS[0])
    counts = {}
    for label in (
        "bga3_pitch_0p40",
        "bga3_pitch_0p50",
        "bga3_pitch_0p65",
        "bga3_pitch_0p80",
        "bga3_pitch_1p00",
        "bga3_pitch_1p27",
    ):
        case = next(p for p in PACKAGES if p[0] == label)
        counts[label] = len(
            ORACLE.generate_escape_vias(build_dense_package(case), rules, "dog-bone")
        )
    assert counts == {
        "bga3_pitch_0p40": 0,
        "bga3_pitch_0p50": 0,
        "bga3_pitch_0p65": 0,
        "bga3_pitch_0p80": 0,
        "bga3_pitch_1p00": 9,
        "bga3_pitch_1p27": 9,
    }, f"the feasibility cliff moved: {counts}"


# ---------------------------------------------------------------------------
# Traps
# ---------------------------------------------------------------------------


def test_trap_rotation_uses_host_libm_trig():
    """``rotate_local_to_world`` is CPython ``math.cos``/``math.sin`` (B1).

    The Rust mirror must resolve ``cos``/``sin`` through ``dlsym``
    (``pad_geometry.rs``'s ``dlsym_math``), not bind ``f64::cos``/``f64::sin``
    statically.  This test does not -- cannot -- compare against Rust; it
    pins the *shape* the Rust must reproduce: the exact two-op expressions
    ``x*c + y*s`` and ``-x*s + y*c``, with no reassociation and no ``mul_add``
    fusion (B7).
    """
    from temper_placer.geometry.kicad_transform import rotate_local_to_world

    rng = random.Random(31)
    for _ in range(500):
        x = rng.uniform(-10.0, 10.0)
        y = rng.uniform(-10.0, 10.0)
        theta = rng.uniform(-7.0, 7.0)
        c, s = math.cos(theta), math.sin(theta)
        expected = (x * c + y * s, -x * s + y * c)
        assert rotate_local_to_world(x, y, theta) == expected

    # a fused/reassociated spelling is NOT bit-equal in general -- measured,
    # so the "no reassociation" instruction is evidence-backed
    reassociated = 0
    for _ in range(5000):
        x = rng.uniform(-10.0, 10.0)
        y = rng.uniform(-10.0, 10.0)
        theta = rng.uniform(-7.0, 7.0)
        c, s = math.cos(theta), math.sin(theta)
        if (x * c + y * s) != (y * s + x * c):
            reassociated += 1
    # commuting the two addends is exact for f64 addition, so this must be 0;
    # asserted so a future reader does not over-claim the trap.
    assert reassociated == 0


def test_trap_sqrt_pow_form_is_not_hypot():
    """``sqrt((dx)**2 + (dy)**2)`` != ``hypot(dx, dy)`` (B7, and B6's point).

    Measured over 20 000 random pairs.  ``math.hypot`` is CPython's
    compensated ``vector_norm``; the module does not use it, and a Rust
    mirror that reaches for ``py_hypot`` (the helper ``creepage_check.rs``
    already has) is wrong here.
    """
    rng = random.Random(11)
    n = 20000
    vs_hypot = 0
    vs_mul = 0
    for _ in range(n):
        dx = rng.uniform(-50.0, 50.0)
        dy = rng.uniform(-50.0, 50.0)
        form = math.sqrt(dx**2 + dy**2)
        if form != math.hypot(dx, dy):
            vs_hypot += 1
        if form != math.sqrt(dx * dx + dy * dy):
            vs_mul += 1
    assert vs_hypot / n > 0.10, f"pow-form vs hypot disagreed on only {vs_hypot}/{n}"
    assert vs_mul > 0, "x**2 and x*x agreed on every pair -- re-measure before trusting"


def test_trap_pi_over_two_is_exact_here():
    """``rot * math.pi / 2.0`` is measured NOT to be the B2 trap.

    B2 records that ``math.pi / 2.0`` (the division) and ``FRAC_PI_2`` (the
    named constant) are 1 ulp apart in some spellings.  Here they are not:
    division by ``2.0`` is exact in binary floating point, so
    ``(v * PI) / 2.0``, ``v * (PI / 2.0)`` and ``v * FRAC_PI_2`` agree on
    **0 of 20 000** random ``v``.  Recorded as a measured non-divergence so
    nobody re-derives it, and so nobody "fixes" the Rust to use a different
    spelling on the assumption that it matters.
    """
    frac_pi_2 = 1.5707963267948966  # std::f64::consts::FRAC_PI_2
    rng = random.Random(5)
    disagreements = 0
    for _ in range(20000):
        v = rng.uniform(-1000.0, 1000.0)
        a = (v * math.pi) / 2.0
        if a != v * (math.pi / 2.0) or a != v * frac_pi_2:
            disagreements += 1
    assert disagreements == 0, (
        f"(v*PI)/2.0 diverged from v*(PI/2.0) or v*FRAC_PI_2 on {disagreements} "
        f"of 20000 -- the oracle header's 'measured non-divergence' is stale"
    )
    # and the quadrant values the module actually produces
    for rot in (0, 1, 2, 3):
        assert float(rot) * math.pi / 2.0 == rot * frac_pi_2


def test_pin_world_radius_is_outside_the_migration_boundary():
    """``pin_world_radius`` is already a shared, Rust-backed helper.

    The oracle imports it rather than copying it, exactly as #732's oracle
    imports ``kicad_transform``.  Asserted so a future reader does not
    mistake its absence from the pinned text for an omission.
    """
    from temper_placer.core.pin_geometry import pin_world_position, pin_world_radius

    assert ORACLE.pin_world_radius is pin_world_radius
    assert ORACLE.pin_world_position is pin_world_position
    # ... and it is genuinely shape-dependent, so the corpus's four pad
    # shapes are not decorative
    radii = {
        shape: pin_world_radius(
            build_component((0.0, 0.0), 0, 0, [("1", (0.0, 0.0), "N", 0.5, 0.3, shape)]).pins[0]
        )
        for shape in ("circle", "rect", "oval", "roundrect")
    }
    assert len(set(radii.values())) >= 2, f"pad shape stopped mattering: {radii}"

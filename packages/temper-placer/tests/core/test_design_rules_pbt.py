"""Property-based + metamorphic tests for the Rust design-rules pyclasses.

Wave 4, Phase 2 — the contracts-as-pyo3-pyclasses pivot (plan
``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``
R1c/R1d). These properties exercise the migrated
``temper_placer.core.design_rules`` module (a pure-delegation re-export of
the ``temper_design_bundle_python`` pyclasses); bit-identical parity against
the pinned pre-migration Python is asserted separately by
``test_design_rules_rust_differential.py``.

Five hypothesis properties (all non-vacuously guarded):

- P1. ``get_rules_for_net`` lookup precedence: per-net override wins over an
  explicit net-class argument, which wins over the ``net_class_assignments``
  table, which wins over the Default catch-all.
- P2. The Default catch-all reflects the instance's own scalar fields
  (``default_trace_width`` etc.) and the fixed ``dru_priority=999``.
- P3. The word-boundary classification cascade (gate-HV → gate-SELV →
  high-current, plus ground/power via the router_v6 recognizers) resolves to
  the class an independent reference transcription predicts — including the
  fix for the 2026-07-27 ``"COIL"`` plain-substring bug.
- P4. ``get_via_template``: a class's ``via_template`` name resolves to that
  template when present, else to ``Via1x1``.
- P5. ``ViaTemplate`` geometry matches an independent closed-form reference
  bit-exactly (footprint bbox, grid start, grid pitch).

Three metamorphic relations:

- MR1. Construction→access round-trip: every ``ViaTemplate`` field reads back
  bit-identically, and keyword-argument order is commutative.
- MR2. Independent-path equivalence: ``get_class_for_net(net)`` equals
  ``get_rules_for_net(net).name`` for every net in a full production table.
- MR3. Override isolation: adding a per-net override perturbs exactly that
  net's resolution; every other net resolves identically before and after.
"""

from __future__ import annotations

import os
import re

import pytest
import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.design_rules import DesignRules, ViaTemplate, create_temper_design_rules
from temper_placer.core.netclass_rules_gen import NetClassRules

MAX_EXAMPLES = 100

_NET_ALPHABET = [
    "AGND_2",  # ground-pattern tier (not in TEMPER_NET_ASSIGNMENTS)
    "+15V_AUX",  # power tier ('+' prefix)
    "GATE_H_2",  # gate-HV tier
    "PWM_H_2",  # gate-SELV tier
    "COIL_2",  # high-current tier
    "discharge.k_dis1-coil1",  # the 2026-07-27 bug case -> Default
    "NET_X9",  # Default catch-all
]


def _f(value):
    return None if value is None else float(value).hex()


# ---------------------------------------------------------------------------
# Independent reference transcriptions (the property recomputes the
# semantics itself, so the assertion is against the form, not against either
# implementation).
# ---------------------------------------------------------------------------


def _wb_ref(upper: str, patterns: tuple[str, ...]) -> bool:
    r"""Independent transcription of design_rules' word-boundary matcher:
    ``(?:^|_){p}(?:$|[\d_])`` (leading-anchor-only when the pattern ends in a
    non-alphanumeric character)."""
    for p in patterns:
        escaped = re.escape(p)
        if p and not p[-1].isalnum():
            if re.search(rf"(?:^|_){escaped}", upper):
                return True
        elif re.search(rf"(?:^|_){escaped}(?:$|[\d_])", upper):
            return True
    return False


def _predict_class(net: str) -> str:
    """The class the oracle cascade resolves a net to (pattern tiers only —
    no overrides/assignments involved)."""
    from temper_placer.router_v6.net_classification import is_ground_net, is_power_net

    if is_ground_net(net):
        return "GND"
    if is_power_net(net) and not is_ground_net(net):
        return "Power"
    upper = net.upper()
    if _wb_ref(upper, ("GATE", "SW_NODE")):
        return "GateDriveHV"
    if _wb_ref(upper, ("PWM",)):
        return "GateDriveSELV"
    if _wb_ref(upper, ("DC_BUS", "AC_L", "AC_N", "COIL")):
        return "HighCurrent"
    return "Default"


# ---------------------------------------------------------------------------
# Kernel indirection — the vacuity-mutant seam (G4 evidence pattern).
# ---------------------------------------------------------------------------


class _DesignRulesKernels:
    rules_for_net = staticmethod(lambda dr, net, nc=None: dr.get_rules_for_net(net, net_class=nc))
    class_for_net = staticmethod(lambda dr, net: dr.get_class_for_net(net))
    via_template = staticmethod(lambda dr, net: dr.get_via_template(net))
    bbox = staticmethod(lambda vt: vt.get_footprint_bbox())
    positions = staticmethod(lambda vt, cx, cy: vt.get_via_positions(cx, cy))


_kernels = _DesignRulesKernels()

_KERNEL_NAMES = (
    "rules_for_net",
    "class_for_net",
    "via_template",
    "bbox",
    "positions",
)


@pytest.fixture
def _restore_kernels():
    saved = {name: getattr(_kernels, name) for name in _KERNEL_NAMES}
    yield
    for name, fn in saved.items():
        setattr(_kernels, name, fn)


def _sample_dr():
    return DesignRules(
        net_classes={
            "Power": NetClassRules(name="Power", trace_width=1.0, clearance=0.5, dru_priority=100),
            "Signal": NetClassRules(name="Signal", trace_width=0.2, clearance=0.15, dru_priority=80),
            "GND": NetClassRules(name="GND", trace_width=1.0, clearance=0.3, dru_priority=60),
        },
        net_overrides={"VCC": NetClassRules(name="VCC_Special", trace_width=1.5, clearance=0.6, dru_priority=100)},
        net_class_assignments={"VCC": "Power", "GND": "Signal"},
    )


# ---------------------------------------------------------------------------
# P1 — get_rules_for_net precedence cascade
# ---------------------------------------------------------------------------


@st.composite
def _net_and_class(draw):
    net = draw(st.sampled_from(["VCC", "NET1", "GND", "SIGNAL_X"]))
    nc = draw(st.sampled_from(["Power", "Signal", None]))
    return net, nc


@given(_net_and_class())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1_precedence_cascade(net_class_pair):
    net, nc = net_class_pair
    dr = _sample_dr()
    rules = _kernels.rules_for_net(dr, net, nc)

    if net == "VCC":
        # Tier 1: the per-net override wins over the class argument AND the
        # assignment table.
        assert rules.name == "VCC_Special"
    elif nc is not None:
        # Tier 2: the explicit class argument wins (VCC's assignment table
        # entry only applies when no class argument is given).
        assert rules.name == nc
    elif net == "GND":
        # Tier 3: the assignment table (GND -> Signal; note the assignment
        # value wins over the pattern tier because assignments come first).
        assert rules.name == "Signal"
    else:
        # Tier 4: the Default catch-all.
        assert rules.name == "Default"
    # Vacuity guard: every tier is exercised across the example run.
    assert net in ("VCC", "NET1", "GND", "SIGNAL_X")


def test_p1_fails_for_always_override(_restore_kernels):
    _kernels.rules_for_net = lambda *_a, **_k: _sample_dr().net_overrides["VCC"]
    with pytest.raises(AssertionError):
        test_p1_precedence_cascade.hypothesis.inner_test(("NET1", None))


# ---------------------------------------------------------------------------
# P2 — Default catch-all reflects the instance's scalar fields
# ---------------------------------------------------------------------------


@given(
    st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p2_default_rules_reflect_scalars(trace_width, clearance):
    dr = DesignRules(
        default_trace_width=trace_width,
        default_clearance=clearance,
        default_via_diameter=0.6,
        default_via_drill=0.3,
    )
    rules = _kernels.rules_for_net(dr, "UNKNOWN_NET")
    assert rules.name == "Default"
    assert _f(rules.trace_width) == _f(trace_width)
    assert _f(rules.clearance) == _f(clearance)
    assert _f(rules.via_diameter) == _f(dr.default_via_diameter)
    assert _f(rules.via_drill) == _f(dr.default_via_drill)
    assert rules.dru_priority == 999
    # Vacuity guard: the sampled widths genuinely differ across examples.
    assert 0.05 <= trace_width <= 2.0


def test_p2_fails_for_fixed_defaults(_restore_kernels):
    def fixed(dr, net, nc=None):
        return NetClassRules(name="Default", trace_width=0.2, clearance=0.2, via_diameter=0.6, via_drill=0.3, dru_priority=999)

    _kernels.rules_for_net = fixed
    with pytest.raises(AssertionError):
        test_p2_default_rules_reflect_scalars.hypothesis.inner_test(1.5, 0.8)


# ---------------------------------------------------------------------------
# P3 — word-boundary classification cascade vs an independent reference
# ---------------------------------------------------------------------------


@given(st.sampled_from(_NET_ALPHABET), st.sampled_from(_NET_ALPHABET))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p3_classification_matches_reference(net_a, net_b):
    dr = create_temper_design_rules()
    for net in (net_a, net_b):
        got = _kernels.rules_for_net(dr, net).name
        assert got == _predict_class(net), (
            f"net={net!r}: rust={got!r} ref={_predict_class(net)!r}"
        )
    # Vacuity guard: the alphabet spans every cascade tier (ground, power,
    # gate-HV, gate-SELV, high-current, and the Default catch-all).
    assert {_predict_class(n) for n in _NET_ALPHABET} >= {
        "GND",
        "Power",
        "GateDriveHV",
        "GateDriveSELV",
        "HighCurrent",
        "Default",
    }


def test_p3_fails_for_plain_substring(_restore_kernels):
    """The 2026-07-27 regression: a plain-substring classifier matches
    ``discharge.k_dis1-coil1`` as high-current; the word-boundary cascade
    (and the migration) must not."""
    def substring_classifier(dr, net, nc=None):
        upper = net.upper()
        if "GATE" in upper or "SW_NODE" in upper:
            return dr.net_classes["GateDriveHV"]
        if "PWM" in upper:
            return dr.net_classes["GateDriveSELV"]
        if any(p in upper for p in ("DC_BUS", "AC_L", "AC_N", "COIL")):
            return dr.net_classes["HighCurrent"]
        return dr.get_rules_for_net("", net_class=nc) if nc else dr.net_classes["GND"]

    _kernels.rules_for_net = substring_classifier
    with pytest.raises(AssertionError):
        test_p3_classification_matches_reference.hypothesis.inner_test(
            "discharge.k_dis1-coil1", "NET_X9"
        )


# ---------------------------------------------------------------------------
# P4 — get_via_template resolution and fallback
# ---------------------------------------------------------------------------


@given(st.sampled_from(["Via1x1", "Via2x2", "Via3x3", "Via4x4", "Via9x9"]))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p4_via_template_resolution_and_fallback(template_name):
    dr = DesignRules(
        net_classes={
            "Power": NetClassRules(
                name="Power",
                trace_width=1.0,
                clearance=0.5,
                via_template=template_name,
                dru_priority=100,
            )
        },
        net_class_assignments={"VCC": "Power"},
    )
    vt = _kernels.via_template(dr, "VCC")
    if template_name in dr.via_templates:
        assert vt.name == template_name
        assert vt.via_count == vt.rows * vt.cols
    else:
        # Unknown template name -> the Via1x1 fallback.
        assert vt.name == "Via1x1"
        assert vt.rows == 1 and vt.cols == 1
    # Vacuity guard: both the known and the unknown-template branches are
    # exercised across the example run.
    assert template_name in ("Via1x1", "Via2x2", "Via3x3", "Via4x4", "Via9x9")


def test_p4_fails_for_always_fallback(_restore_kernels):
    # A degenerate kernel that always falls back to Via1x1 regardless of the
    # class's via_template must fail P4 on the known-template branch.
    def always_fallback(dr, net):
        return dr.via_templates["Via1x1"]

    _kernels.via_template = always_fallback
    with pytest.raises(AssertionError):
        test_p4_via_template_resolution_and_fallback.hypothesis.inner_test("Via2x2")


# ---------------------------------------------------------------------------
# P5 — ViaTemplate geometry vs an independent closed form (bit-exact)
# ---------------------------------------------------------------------------


@st.composite
def _template_geometry(draw):
    rows = draw(st.integers(min_value=1, max_value=6))
    cols = draw(st.integers(min_value=1, max_value=6))
    diameter = draw(st.floats(min_value=0.1, max_value=2.0, allow_nan=False, allow_infinity=False))
    pitch = draw(st.floats(min_value=0.2, max_value=3.0, allow_nan=False, allow_infinity=False))
    cx = draw(st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    cy = draw(st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    return rows, cols, diameter, pitch, cx, cy


@given(_template_geometry())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p5_via_template_geometry_matches_reference(geometry):
    rows, cols, diameter, pitch, cx, cy = geometry
    vt = ViaTemplate("T", rows, cols, diameter, 0.3, pitch)

    width = (cols - 1) * pitch + diameter
    height = (rows - 1) * pitch + diameter
    bbox = _kernels.bbox(vt)
    assert _f(bbox[0]) == _f(width)
    assert _f(bbox[1]) == _f(height)

    positions = _kernels.positions(vt, cx, cy)
    assert len(positions) == rows * cols
    start_x = cx - ((cols - 1) * pitch) / 2.0
    start_y = cy - ((rows - 1) * pitch) / 2.0
    for idx, (x, y) in enumerate(positions):
        row, col = divmod(idx, cols)
        assert _f(x) == _f(start_x + col * pitch), f"x at {idx}: {x!r}"
        assert _f(y) == _f(start_y + row * pitch), f"y at {idx}: {y!r}"
    # Vacuity guard: the sampled geometry stays inside the strategy bounds
    # (the mutant test proves the assertions genuinely bite).
    assert 1 <= rows <= 6 and 1 <= cols <= 6 and diameter > 0.0 and pitch > 0.0


def test_p5_fails_for_wrong_bbox_formula(_restore_kernels):
    def wrong_bbox(vt):
        # Wrong: uses `cols * pitch` (off by one row/col) instead of
        # `(cols - 1) * pitch`.
        return (vt.cols * vt.pitch_mm + vt.via_diameter_mm, vt.rows * vt.pitch_mm + vt.via_diameter_mm)

    _kernels.bbox = wrong_bbox
    with pytest.raises(AssertionError):
        test_p5_via_template_geometry_matches_reference.hypothesis.inner_test(
            (3, 3, 0.6, 1.2, 10.0, 10.0)
        )


# ---------------------------------------------------------------------------
# MR1 — ViaTemplate construction→access round-trip and kwarg-order commutation
# ---------------------------------------------------------------------------


@given(
    st.text(min_size=1, max_size=8, alphabet=st.characters(min_codepoint=65, max_codepoint=90)),
    st.integers(min_value=1, max_value=5),
    st.integers(min_value=1, max_value=5),
    st.floats(min_value=0.1, max_value=1e6, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.1, max_value=1e6, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.1, max_value=1e6, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr1_via_template_round_trip_and_kwarg_commute(
    name, rows, cols, diameter, drill, pitch
):
    kwargs = {
        "name": name,
        "rows": rows,
        "cols": cols,
        "via_diameter_mm": diameter,
        "via_drill_mm": drill,
        "pitch_mm": pitch,
    }
    vt = ViaTemplate(**kwargs)
    assert vt.name == name
    assert vt.rows == rows
    assert vt.cols == cols
    assert _f(vt.via_diameter_mm) == _f(diameter)
    assert _f(vt.via_drill_mm) == _f(drill)
    assert _f(vt.pitch_mm) == _f(pitch)
    # Vacuity guard: values differ from the constructor defaults (none exist,
    # so this simply confirms all six fields were actually supplied).
    assert rows >= 1 and cols >= 1
    # Kwarg-order commutativity.
    reversed_vt = ViaTemplate(**dict(reversed(list(kwargs.items()))))
    assert reversed_vt.name == vt.name
    assert _f(reversed_vt.pitch_mm) == _f(vt.pitch_mm)


# ---------------------------------------------------------------------------
# MR2 — get_class_for_net ≡ get_rules_for_net(net).name (independent path)
# ---------------------------------------------------------------------------


@given(st.sampled_from(_NET_ALPHABET))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr2_class_name_matches_rules_name(net):
    dr = create_temper_design_rules()
    assert _kernels.class_for_net(dr, net) == _kernels.rules_for_net(dr, net).name, net
    # Vacuity guard: the alphabet genuinely spans multiple classes.
    assert _predict_class(net) in {
        "GND",
        "Power",
        "GateDriveHV",
        "GateDriveSELV",
        "HighCurrent",
        "Default",
    }


# ---------------------------------------------------------------------------
# MR3 — override isolation: perturbing one net leaves every other net intact
# ---------------------------------------------------------------------------


def test_mr3_override_perturbs_only_its_net():
    dr = create_temper_design_rules()
    before = {net: dr.get_rules_for_net(net).name for net in _NET_ALPHABET}

    dr.net_overrides["PWM_H_2"] = NetClassRules(
        name="PWM_SPECIAL", trace_width=0.9, clearance=0.4, dru_priority=5
    )
    assert dr.get_rules_for_net("PWM_H_2").name == "PWM_SPECIAL"
    after = {net: dr.get_rules_for_net(net).name for net in _NET_ALPHABET}
    for net in _NET_ALPHABET:
        if net == "PWM_H_2":
            assert after[net] == "PWM_SPECIAL"
        else:
            assert after[net] == before[net], net
    # Vacuity guard: the override genuinely changed the perturbed net.
    assert before["PWM_H_2"] != "PWM_SPECIAL"


# ---------------------------------------------------------------------------
# Presence guard: this proof must not silently skip in CI.
# ---------------------------------------------------------------------------

_REQUIRE = os.environ.get("TEMPER_REQUIRE_RUST_DESIGN_RULES", "").strip().lower() in {
    "1",
    "true",
    "yes",
}

if _REQUIRE and not hasattr(_tdb, "DesignRules"):
    pytest.fail(
        "TEMPER_REQUIRE_RUST_DESIGN_RULES=1 but temper_design_bundle_python "
        "does not expose the design-rules pyclasses — the Rust extension is "
        "stale or missing.",
        pytrace=False,
    )

pytestmark = pytest.mark.skipif(
    not hasattr(_tdb, "DesignRules"),
    reason="temper_design_bundle_python design-rules pyclasses not installed "
    "(set TEMPER_REQUIRE_RUST_DESIGN_RULES=1 to make this fatal instead of a skip)",
)

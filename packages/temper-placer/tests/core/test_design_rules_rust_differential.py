"""Differential test: Rust design-rules pyclasses (temper_design_bundle_python)
vs the pinned Python oracle.

Wave 4, Phase 2 — the contracts-as-pyo3-pyclasses pivot (plan
``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``,
D5 / Phase B). This is the THIRD Wave-4 Phase 2 migration; it mirrors the
net-types and loop migrations
(``test_net_types_rust_differential.py`` / ``test_loop_rust_differential.py``)
exactly.

The Rust pyo3 pyclasses ``ViaTemplate`` and ``DesignRules`` (in
``temper_design_bundle_python``, from the ``temper-design-bundle`` crate) must
reproduce the pre-migration Python implementation of
``temper_placer/core/design_rules.py`` bit-identically. The pre-migration
implementation is pinned verbatim as the oracle
(``_design_rules_py_oracle.py``, commit e5bd461e2) and every assertion here
drives IDENTICAL inputs through both sides.

Comparison convention (mirrors the loop/net-types differential): objects are
canonicalized into plain comparable tuples before assertion. Floats are
compared as exact bit patterns via ``float.hex()``.

Design-rules-specific note: ``DesignRules`` is a MUTABLE dataclass whose
containers consumers build up in place (``dr.net_classes[net] = rules``,
``dr.net_class_assignments = {...}``, ``dr.differential_pairs.append(...)``,
``dr.net_topologies[net] = graph``, and the dynamically-attached
``dr.class_pairs``). The pyclass therefore holds its container fields as the
actual Python ``dict``/``list`` objects (``Py<PyDict>``/``Py<PyList>``) with
explicit getters AND setters, so in-place mutation and whole-field assignment
both persist — this differential suite asserts exactly those mutation paths
(``test_mutation_paths_persist_identically``).

The module-level constants (``TEMPER_NET_CLASSES``, ``TEMPER_NET_ASSIGNMENTS``,
``SAFETY_CONSTANT_AUTHORITY``) construct Pydantic ``NetClassRules`` objects and
stay Python-side in the delegation module; the differential suite pins them
equal to the oracle (``test_module_constants_identical``).
"""

from __future__ import annotations

import os

import pytest
import temper_design_bundle_python as _tdb

import tests.core._design_rules_py_oracle as _oracle

# Rust symbols under test — must exist or this file fails to collect (RED).
VIA_TEMPLATE = _tdb.ViaTemplate
DESIGN_RULES = _tdb.DesignRules

_NCR_FIELDS = (
    "name",
    "trace_width",
    "clearance",
    "dru_priority",
    "via_diameter",
    "via_drill",
    "via_template",
    "creepage_mm",
    "voltage_v",
    "target_impedance",
    "max_current_rating",
    "required_layer",
    "layer",
    "safety_category",
    "routing_strategy",
    "via_cost_multiplier",
    "layer_costs",
)


def _f(value):
    """Bit-exact float key: None stays None, else float.hex()."""
    return None if value is None else float(value).hex()


def _ncr_fields_clean(rules):
    """Canonicalize a NetClassRules object; floats by bit pattern, scalars
    verbatim, None-preserving (dru_priority is an int, kept exact)."""
    out = []
    for f in _NCR_FIELDS:
        v = getattr(rules, f)
        if isinstance(v, float):
            out.append(_f(v))
        elif isinstance(v, dict):
            out.append(tuple(sorted((k, _f(val)) for k, val in v.items())))
        else:
            out.append(v)
    return tuple(out)


def _vt_fields(vt):
    return (
        vt.name,
        vt.rows,
        vt.cols,
        _f(vt.via_diameter_mm),
        _f(vt.via_drill_mm),
        _f(vt.pitch_mm),
    )


def _pair_fields(pair):
    return (pair.net_pos, pair.net_neg)


def _bus_fields(bus):
    return (bus.name, tuple(bus.nets))


def _dr_fields(dr):
    """Extract every DesignRules field into a comparable mapping.

    Containers are canonicalized by sorted key; NetClassRules values via
    ``_ncr_fields_clean``; floats via ``_f``. ``class_pairs`` is a
    dynamically-attached attribute (NOT a dataclass field) and is compared
    separately where exercised.
    """
    return {
        "default_trace_width": _f(dr.default_trace_width),
        "default_clearance": _f(dr.default_clearance),
        "default_via_diameter": _f(dr.default_via_diameter),
        "default_via_drill": _f(dr.default_via_drill),
        "net_classes": tuple(
            sorted((k, _ncr_fields_clean(v)) for k, v in dr.net_classes.items())
        ),
        "net_overrides": tuple(
            sorted((k, _ncr_fields_clean(v)) for k, v in dr.net_overrides.items())
        ),
        "net_class_assignments": tuple(sorted(dr.net_class_assignments.items())),
        "differential_pairs": tuple(_pair_fields(p) for p in dr.differential_pairs),
        "bus_cohorts": tuple(_bus_fields(b) for b in dr.bus_cohorts),
        "net_topologies": tuple(sorted((k, v.net_name) for k, v in dr.net_topologies.items())),
        "via_templates": tuple(
            sorted((k, _vt_fields(v)) for k, v in dr.via_templates.items())
        ),
    }


def _ncr(**kwargs):
    """Build a NetClassRules object usable by both sides (same Pydantic class)."""
    from temper_placer.core.netclass_rules_gen import NetClassRules

    return NetClassRules(**kwargs)


def _sample_net_classes():
    return {
        "Power": _ncr(name="Power", trace_width=1.0, clearance=0.5, dru_priority=100),
        "Signal": _ncr(name="Signal", trace_width=0.2, clearance=0.15, dru_priority=80),
        "GND": _ncr(name="GND", trace_width=1.0, clearance=0.3, dru_priority=60),
    }


def _sample_dr_kwargs():
    return {
        "default_trace_width": 0.2,
        "default_clearance": 0.2,
        "default_via_diameter": 0.6,
        "default_via_drill": 0.3,
        "net_classes": _sample_net_classes(),
        "net_class_assignments": {"VCC": "Power", "GND": "GND"},
    }


# ---------------------------------------------------------------------------
# Module constants: the Python-side tables must not drift from the oracle.
# ---------------------------------------------------------------------------


def test_module_constants_identical():
    """TEMPER_NET_CLASSES / TEMPER_NET_ASSIGNMENTS / SAFETY_CONSTANT_AUTHORITY
    in the delegation module are bit-identical to the oracle's (both construct
    the same Pydantic NetClassRules from the same literals)."""
    from temper_placer.core import design_rules as wrapper

    assert set(wrapper.TEMPER_NET_CLASSES.keys()) == set(_oracle.TEMPER_NET_CLASSES.keys())
    for name in _oracle.TEMPER_NET_CLASSES:
        assert _ncr_fields_clean(wrapper.TEMPER_NET_CLASSES[name]) == _ncr_fields_clean(
            _oracle.TEMPER_NET_CLASSES[name]
        ), name
    assert wrapper.TEMPER_NET_ASSIGNMENTS == _oracle.TEMPER_NET_ASSIGNMENTS
    assert wrapper.SAFETY_CONSTANT_AUTHORITY == _oracle.SAFETY_CONSTANT_AUTHORITY
    assert wrapper.SAFETY_CONSTANT_AUTHORITY_NET_CLASSES == _oracle.SAFETY_CONSTANT_AUTHORITY_NET_CLASSES
    assert wrapper.SAFETY_CONSTANT_AUTHORITY_FIELDS == _oracle.SAFETY_CONSTANT_AUTHORITY_FIELDS


# ---------------------------------------------------------------------------
# ViaTemplate: construction, defaults, geometry (bit-exact).
# ---------------------------------------------------------------------------


def test_via_template_construction_all_fields_round_trip():
    kwargs = {
        "name": "Via2x2",
        "rows": 2,
        "cols": 3,
        "via_diameter_mm": 0.6,
        "via_drill_mm": 0.3,
        "pitch_mm": 1.2,
    }
    py_vt = _oracle.ViaTemplate(**kwargs)
    rust_vt = VIA_TEMPLATE(**kwargs)
    assert _vt_fields(rust_vt) == _vt_fields(py_vt)

    py_vt2 = _oracle.ViaTemplate("Via1x1", 1, 1, 0.6, 0.3, 1.0)
    rust_vt2 = VIA_TEMPLATE("Via1x1", 1, 1, 0.6, 0.3, 1.0)
    assert _vt_fields(rust_vt2) == _vt_fields(py_vt2)


@pytest.mark.parametrize(
    "vt_kwargs",
    [
        {"name": "Via1x1", "rows": 1, "cols": 1, "via_diameter_mm": 0.6, "via_drill_mm": 0.3, "pitch_mm": 1.0},
        {"name": "Via2x2", "rows": 2, "cols": 2, "via_diameter_mm": 0.6, "via_drill_mm": 0.3, "pitch_mm": 1.2},
        {"name": "Via3x4", "rows": 3, "cols": 4, "via_diameter_mm": 0.8, "via_drill_mm": 0.4, "pitch_mm": 1.5},
    ],
)
def test_via_template_bbox_bit_identical(vt_kwargs):
    py_bbox = _oracle.ViaTemplate(**vt_kwargs).get_footprint_bbox()
    rust_bbox = VIA_TEMPLATE(**vt_kwargs).get_footprint_bbox()
    assert float(rust_bbox[0]).hex() == float(py_bbox[0]).hex()
    assert float(rust_bbox[1]).hex() == float(py_bbox[1]).hex()


def test_via_template_via_count_identical():
    for vt_kwargs in (
        {"name": "Via1x1", "rows": 1, "cols": 1, "via_diameter_mm": 0.6, "via_drill_mm": 0.3, "pitch_mm": 1.0},
        {"name": "Via2x2", "rows": 2, "cols": 2, "via_diameter_mm": 0.6, "via_drill_mm": 0.3, "pitch_mm": 1.2},
        {"name": "Via4x4", "rows": 4, "cols": 4, "via_diameter_mm": 0.6, "via_drill_mm": 0.3, "pitch_mm": 1.2},
    ):
        assert VIA_TEMPLATE(**vt_kwargs).via_count == _oracle.ViaTemplate(**vt_kwargs).via_count


@pytest.mark.parametrize(
    "vt_kwargs",
    [
        {"name": "Via1x1", "rows": 1, "cols": 1, "via_diameter_mm": 0.6, "via_drill_mm": 0.3, "pitch_mm": 1.0},
        {"name": "Via2x2", "rows": 2, "cols": 2, "via_diameter_mm": 0.6, "via_drill_mm": 0.3, "pitch_mm": 1.2},
        {"name": "Via3x3", "rows": 3, "cols": 3, "via_diameter_mm": 0.6, "via_drill_mm": 0.3, "pitch_mm": 1.2},
        {"name": "Via2x3", "rows": 2, "cols": 3, "via_diameter_mm": 0.8, "via_drill_mm": 0.4, "pitch_mm": 1.5},
    ],
)
@pytest.mark.parametrize("center", [(0.0, 0.0), (10.5, -7.25), (123.456, 0.001)])
def test_via_template_positions_bit_identical(vt_kwargs, center):
    cx, cy = center
    py_pos = _oracle.ViaTemplate(**vt_kwargs).get_via_positions(cx, cy)
    rust_pos = VIA_TEMPLATE(**vt_kwargs).get_via_positions(cx, cy)
    assert len(rust_pos) == len(py_pos) == vt_kwargs["rows"] * vt_kwargs["cols"]
    for (rx, ry), (px, py_) in zip(rust_pos, py_pos):
        assert float(rx).hex() == float(px).hex(), f"x: rust={rx!r} py={px!r}"
        assert float(ry).hex() == float(py_).hex(), f"y: rust={ry!r} py={py_!r}"


# ---------------------------------------------------------------------------
# DesignRules: construction, defaults, equality, repr.
# ---------------------------------------------------------------------------


def test_design_rules_defaults_identical():
    py_dr = _oracle.DesignRules()
    rust_dr = DESIGN_RULES()
    assert _dr_fields(rust_dr) == _dr_fields(py_dr)
    assert set(rust_dr.via_templates.keys()) == {"Via1x1", "Via2x2", "Via3x3", "Via4x4"}


def test_design_rules_construction_all_fields_round_trip():
    kwargs = _sample_dr_kwargs()
    py_dr = _oracle.DesignRules(**kwargs)
    rust_dr = DESIGN_RULES(**kwargs)
    assert _dr_fields(rust_dr) == _dr_fields(py_dr)


def test_design_rules_equality_and_repr_identical():
    kwargs = _sample_dr_kwargs()
    assert _oracle.DesignRules(**kwargs) == _oracle.DesignRules(**kwargs)
    assert DESIGN_RULES(**kwargs) == DESIGN_RULES(**kwargs)
    assert repr(DESIGN_RULES(**kwargs)) == repr(_oracle.DesignRules(**kwargs))
    assert repr(DESIGN_RULES()) == repr(_oracle.DesignRules())
    # Different field values are unequal on both sides.
    assert DESIGN_RULES(default_trace_width=0.3) != DESIGN_RULES()
    assert _oracle.DesignRules(default_trace_width=0.3) != _oracle.DesignRules()


def test_create_temper_design_rules_identical():
    from temper_placer.core.design_rules import create_temper_design_rules

    py_dr = _oracle.create_temper_design_rules()
    rust_dr = create_temper_design_rules()
    assert _dr_fields(rust_dr) == _dr_fields(py_dr)
    assert len(rust_dr.net_classes) == 11


# ---------------------------------------------------------------------------
# get_rules_for_net: every lookup tier, bit-identical.
# ---------------------------------------------------------------------------


def test_get_rules_for_net_unknown_returns_default_identical():
    py_dr = _oracle.DesignRules()
    rust_dr = DESIGN_RULES()
    py_rules = py_dr.get_rules_for_net("UNKNOWN_NET")
    rust_rules = rust_dr.get_rules_for_net("UNKNOWN_NET")
    assert _ncr_fields_clean(rust_rules) == _ncr_fields_clean(py_rules)
    assert rust_rules.name == py_rules.name == "Default"
    assert float(rust_rules.trace_width).hex() == float(rust_dr.default_trace_width).hex()
    assert float(rust_rules.clearance).hex() == float(rust_dr.default_clearance).hex()
    assert float(rust_rules.via_diameter).hex() == float(rust_dr.default_via_diameter).hex()
    assert float(rust_rules.via_drill).hex() == float(rust_dr.default_via_drill).hex()
    assert rust_rules.dru_priority == py_rules.dru_priority == 999


def test_get_rules_for_net_tiers_identical():
    kwargs = _sample_dr_kwargs()
    kwargs["net_overrides"] = {"VCC": _ncr(name="VCC_Special", trace_width=1.5, clearance=0.6, dru_priority=100)}
    py_dr = _oracle.DesignRules(**kwargs)
    rust_dr = DESIGN_RULES(**kwargs)

    # Tier 1: explicit override wins over class assignment.
    assert _ncr_fields_clean(rust_dr.get_rules_for_net("VCC", net_class="Power")) == _ncr_fields_clean(
        py_dr.get_rules_for_net("VCC", net_class="Power")
    )
    # Tier 2: explicit net class argument.
    assert _ncr_fields_clean(rust_dr.get_rules_for_net("NET1", net_class="Power")) == _ncr_fields_clean(
        py_dr.get_rules_for_net("NET1", net_class="Power")
    )
    # Tier 3: net_class_assignments table.
    assert _ncr_fields_clean(rust_dr.get_rules_for_net("VCC2", net_class=None)) == _ncr_fields_clean(
        py_dr.get_rules_for_net("VCC2", net_class=None)
    )
    assert rust_dr.get_rules_for_net("VCC2").name == py_dr.get_rules_for_net("VCC2").name == "Power"


def test_get_rules_for_net_classification_cascade_identical():
    """The pattern-recognition cascade (ground → power → gate HV → gate SELV
    → high-current) resolves to the same class on both sides, using the real
    router_v6 ground/power recognizers (lazy-imported by both)."""
    py_dr = _oracle.create_temper_design_rules()
    rust_dr = _sample_full_design_rules()

    for net in ("PWR_RTN", "CGND", "+15V", "GATE_HS", "GATE_L", "PWM_HS", "PWM_L", "SW_NODE", "AC_L"):
        py_rules = py_dr.get_rules_for_net(net)
        rust_rules = rust_dr.get_rules_for_net(net)
        assert rust_rules.name == py_rules.name, (
            f"net={net}: rust={rust_rules.name} py={py_rules.name}"
        )
        assert _ncr_fields_clean(rust_rules) == _ncr_fields_clean(py_rules), net


def _sample_full_design_rules():
    """The Temper production table (via the factory), rebuilt per-side so the
    cascade branches resolve identically."""
    from temper_placer.core.design_rules import create_temper_design_rules

    return create_temper_design_rules()


def test_get_class_for_net_identical():
    kwargs = _sample_dr_kwargs()
    py_dr = _oracle.DesignRules(**kwargs)
    rust_dr = DESIGN_RULES(**kwargs)
    for net in ("VCC2", "NET1", "UNKNOWN_NET"):
        assert rust_dr.get_class_for_net(net) == py_dr.get_class_for_net(net), net


def test_get_via_template_identical():
    kwargs = _sample_dr_kwargs()
    # Power class has no via_template -> Default NetClassRules.via_template is
    # None -> falls back to Via1x1 on both sides.
    py_dr = _oracle.DesignRules(**kwargs)
    rust_dr = DESIGN_RULES(**kwargs)
    py_vt = py_dr.get_via_template("NET1")
    rust_vt = rust_dr.get_via_template("NET1")
    assert _vt_fields(rust_vt) == _vt_fields(py_vt)
    assert rust_vt.name == py_vt.name == "Via1x1"

    # A class WITH an explicit via_template resolves to that template.
    kwargs2 = dict(
        kwargs,
        net_classes={
            "Power": _ncr(name="Power", trace_width=1.0, clearance=0.5, via_template="Via2x2", dru_priority=100)
        },
        net_class_assignments={"VCC": "Power"},
    )
    py_dr2 = _oracle.DesignRules(**kwargs2)
    rust_dr2 = DESIGN_RULES(**kwargs2)
    assert _vt_fields(rust_dr2.get_via_template("VCC")) == _vt_fields(py_dr2.get_via_template("VCC"))
    assert rust_dr2.get_via_template("VCC").name == "Via2x2"

    # Unknown template name on the class -> fallback to Via1x1.
    kwargs3 = dict(
        kwargs,
        net_classes={
            "Power": _ncr(name="Power", trace_width=1.0, clearance=0.5, via_template="Via9x9", dru_priority=100)
        },
        net_class_assignments={"VCC": "Power"},
    )
    py_dr3 = _oracle.DesignRules(**kwargs3)
    rust_dr3 = DESIGN_RULES(**kwargs3)
    assert _vt_fields(rust_dr3.get_via_template("VCC")) == _vt_fields(py_dr3.get_via_template("VCC"))
    assert rust_dr3.get_via_template("VCC").name == "Via1x1"


def test_get_diff_pair_and_bus_cohort_identical():
    from temper_placer.core.bus_cohort import BusCohortConstraint
    from temper_placer.core.differential_pair import DifferentialPairConstraint

    pairs = [
        DifferentialPairConstraint(net_pos="USB_D+", net_neg="USB_D-"),
        DifferentialPairConstraint(net_pos="ADC_P", net_neg="ADC_N"),
    ]
    buses = [
        BusCohortConstraint(name="SPI_BUS", nets=["sclk", "sdi", "sdo"]),
        BusCohortConstraint(name="PWM_BUS", nets=["PWM_H", "PWM_L"]),
    ]
    kwargs = dict(_sample_dr_kwargs(), differential_pairs=pairs, bus_cohorts=buses)
    py_dr = _oracle.DesignRules(**kwargs)
    rust_dr = DESIGN_RULES(**kwargs)

    for net in ("USB_D+", "USB_D-", "ADC_N", "NOPE"):
        py_pair = py_dr.get_diff_pair_for_net(net)
        rust_pair = rust_dr.get_diff_pair_for_net(net)
        assert (rust_pair is None) == (py_pair is None), net
        if py_pair is not None:
            assert _pair_fields(rust_pair) == _pair_fields(py_pair), net

    for net in ("sclk", "PWM_L", "NOPE"):
        py_bus = py_dr.get_bus_cohort_for_net(net)
        rust_bus = rust_dr.get_bus_cohort_for_net(net)
        assert (rust_bus is None) == (py_bus is None), net
        if py_bus is not None:
            assert _bus_fields(rust_bus) == _bus_fields(py_bus), net


# ---------------------------------------------------------------------------
# Mutation paths: the pyclass containers must persist in-place mutation and
# whole-field assignment exactly like the dataclass.
# ---------------------------------------------------------------------------


def test_mutation_paths_persist_identically():
    from temper_placer.core.bus_cohort import BusCohortConstraint
    from temper_placer.core.differential_pair import DifferentialPairConstraint
    from temper_placer.core.net_graph import NetGraph

    def build_dr(cls):
        dr = cls()
        dr.default_clearance = 0.25  # scalar whole-field assignment
        dr.net_classes["Power"] = _ncr(name="Power", trace_width=1.0, clearance=0.5, dru_priority=100)
        dr.net_classes["Signal"] = _ncr(name="Signal", trace_width=0.2, clearance=0.15, dru_priority=80)
        dr.net_class_assignments = {"VCC": "Power", "GND": "Signal"}  # whole-dict assignment
        dr.net_class_assignments.update({"PWM_H": "Signal"})  # in-place update
        dr.net_overrides["VCC"] = _ncr(name="VCC_Special", trace_width=1.5, clearance=0.6, dru_priority=100)
        dr.differential_pairs.append(
            DifferentialPairConstraint(net_pos="USB_D+", net_neg="USB_D-")
        )
        dr.bus_cohorts.append(BusCohortConstraint(name="SPI_BUS", nets=["sclk", "sdi", "sdo"]))
        dr.net_topologies["SW_NODE"] = NetGraph(net_name="SW_NODE")
        dr.class_pairs = {("Power", "Signal"): {"clearance": 0.4, "because": "HV isolation"}}
        return dr

    py_dr = build_dr(_oracle.DesignRules)
    rust_dr = build_dr(DESIGN_RULES)
    assert _dr_fields(rust_dr) == _dr_fields(py_dr)
    assert float(rust_dr.default_clearance).hex() == float(py_dr.default_clearance).hex()
    assert rust_dr.get_rules_for_net("VCC").name == py_dr.get_rules_for_net("VCC").name == "VCC_Special"
    # The dynamically-attached class_pairs attribute reads back.
    assert rust_dr.class_pairs == py_dr.class_pairs
    assert rust_dr.class_pairs[("Power", "Signal")]["clearance"] == 0.4


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
        "stale or missing. Rebuild with `uv run --no-sync maturin develop "
        "--release --manifest-path packages/temper-design-bundle/Cargo.toml`.",
        pytrace=False,
    )

pytestmark = pytest.mark.skipif(
    not hasattr(_tdb, "DesignRules"),
    reason="temper_design_bundle_python design-rules pyclasses not installed "
    "(set TEMPER_REQUIRE_RUST_DESIGN_RULES=1 to make this fatal instead of a skip)",
)

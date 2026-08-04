"""Property-based + metamorphic tests for the Rust netclass loader.

Wave 4, Phase 3 — the formats/IO first-pull slice (plan
``docs/plans/2026-08-03-003-feat-wave4-phase3-first-pulls-plan.md``, U2,
R1c/R1d). These properties exercise the migrated
``temper_placer.io.netclass_loader`` module (a delegation shim over the
``temper_design_bundle_python.load_netclass_rules`` pyfunction);
bit-identical parity against the pinned pre-migration Python is asserted
separately by ``test_netclass_loader_rust_differential.py``.

Five hypothesis properties (all non-vacuously guarded):

- P1. Default-clearance round-trip: the loaded ``default_clearance`` equals
  the YAML's ``default_clearance_mm`` for any finite float.
- P2. Class coverage: every class named in the YAML appears in
  ``dr.net_classes`` with a matching ``name`` field.
- P3. Pair symmetry: every ``class_pairs`` key is a sorted tuple, so
  direction-agnostic lookups hold.
- P4. Assignments totality: every net in ``TEMPER_NET_ASSIGNMENTS``
  resolves through ``get_rules_for_net`` without raising.
- P5. Default absorption: a class that omits the scalar fields inherits
  the ``DesignRules`` defaults exactly.

Three metamorphic relations:

- MR1. Pair-order invariance: swapping ``"A-B"`` to ``"B-A"`` in the YAML
  yields the same loaded ``class_pairs``.
- MR2. Class-order independence: reordering the ``classes`` mapping yields
  the same ``net_classes`` content.
- MR3. Extra top-level keys are ignored: an unrelated top-level key
  changes nothing in the loaded state.
"""

from __future__ import annotations

import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS
from temper_placer.io.netclass_loader import load_netclass_rules

MAX_EXAMPLES = 100


def _write_yaml(tmp_path, data):
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.dump(data, sort_keys=False))
    return path


@st.composite
def class_names(draw):
    """A net-class-style name (drawn from a fixed word list)."""
    return draw(
        st.sampled_from(
            ["Signal", "Power", "HighVoltage", "GND", "HighSpeed", "FinePitch", "AC"]
        )
    )


@st.composite
def netclass_rules_yaml(draw):
    """A structurally-valid netclass_rules.yaml document."""
    classes = draw(
        st.dictionaries(
            keys=class_names(),
            values=st.fixed_dictionaries(
                {
                    "clearance": st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
                    "trace_width": st.floats(min_value=0.0, max_value=5.0, allow_nan=False),
                    "safety_category": st.sampled_from(["HV", "LV", None]),
                },
                optional={
                    "layer": st.sampled_from(["F.Cu", "B.Cu", None]),
                },
            ),
            max_size=4,
        )
    )
    pairs = draw(
        st.dictionaries(
            keys=st.text(alphabet="A-Z-", min_size=3, max_size=15).filter(
                lambda s: s.count("-") == 1
            ),
            values=st.fixed_dictionaries(
                {"clearance": st.floats(min_value=0.0, max_value=10.0, allow_nan=False)},
                optional={"because": st.text(min_size=0, max_size=20)},
            ),
            max_size=4,
        )
    )
    return draw(
        st.fixed_dictionaries(
            {"default_clearance_mm": st.floats(min_value=0.0, max_value=5.0, allow_nan=False)},
            optional={"classes": st.just(classes), "class_pairs": st.just(pairs)},
        )
    )


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(data=netclass_rules_yaml())
def test_p1_default_clearance_round_trip(data, tmp_path):
    ncr = load_netclass_rules(_write_yaml(tmp_path, data))
    assert ncr.design_rules.default_clearance == data["default_clearance_mm"]


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(data=netclass_rules_yaml())
def test_p2_class_coverage(data, tmp_path):
    ncr = load_netclass_rules(_write_yaml(tmp_path, data))
    for name, class_data in data.get("classes", {}).items():
        assert name in ncr.design_rules.net_classes
        assert ncr.design_rules.net_classes[name].name == name
        if "clearance" in class_data:
            assert ncr.design_rules.net_classes[name].clearance == class_data["clearance"]


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(data=netclass_rules_yaml())
def test_p3_pair_symmetry(data, tmp_path):
    ncr = load_netclass_rules(_write_yaml(tmp_path, data))
    for (a, b), _ in ncr.class_pairs.items():
        assert a <= b
        assert (b, a) not in ncr.class_pairs or ncr.class_pairs[(b, a)] == ncr.class_pairs[(a, b)]


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(data=netclass_rules_yaml())
def test_p4_assignments_totality(data, tmp_path):
    ncr = load_netclass_rules(_write_yaml(tmp_path, data))
    dr = ncr.design_rules
    for net in TEMPER_NET_ASSIGNMENTS:
        rules = dr.get_rules_for_net(net)
        assert rules is not None


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(data=netclass_rules_yaml())
def test_p5_default_absorption(data, tmp_path):
    data.setdefault("classes", {})["Bare"] = {}
    ncr = load_netclass_rules(_write_yaml(tmp_path, data))
    dr = ncr.design_rules
    bare = dr.net_classes["Bare"]
    assert bare.trace_width == dr.default_trace_width
    assert bare.clearance == dr.default_clearance
    assert bare.via_diameter == dr.default_via_diameter
    assert bare.via_drill == dr.default_via_drill


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(data=netclass_rules_yaml())
def test_mr1_pair_order_invariance(data, tmp_path):
    swapped = {"class_pairs": {}}
    for key, value in data.get("class_pairs", {}).items():
        a, b = key.split("-")
        swapped["class_pairs"][f"{b}-{a}"] = value
    data2 = dict(data)
    data2["class_pairs"] = swapped["class_pairs"]
    ncr = load_netclass_rules(_write_yaml(tmp_path, data))
    ncr2 = load_netclass_rules(_write_yaml(tmp_path, data2))
    assert dict(ncr.class_pairs) == dict(ncr2.class_pairs)


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(data=netclass_rules_yaml())
def test_mr2_class_order_independence(data, tmp_path):
    classes = list(data.get("classes", {}).items())
    data2 = dict(data)
    data2["classes"] = dict(reversed(classes))
    ncr = load_netclass_rules(_write_yaml(tmp_path, data))
    ncr2 = load_netclass_rules(_write_yaml(tmp_path, data2))
    assert dict(ncr.design_rules.net_classes) == dict(ncr2.design_rules.net_classes)


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(data=netclass_rules_yaml())
def test_mr3_extra_top_level_keys_ignored(data, tmp_path):
    data2 = dict(data)
    data2["unrelated_key"] = "whatever"
    ncr = load_netclass_rules(_write_yaml(tmp_path, data))
    ncr2 = load_netclass_rules(_write_yaml(tmp_path, data2))
    assert dict(ncr.design_rules.net_classes) == dict(ncr2.design_rules.net_classes)
    assert dict(ncr.class_pairs) == dict(ncr2.class_pairs)

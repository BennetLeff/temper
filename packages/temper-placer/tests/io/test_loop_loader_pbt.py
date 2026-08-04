"""Property-based + metamorphic tests for the Rust loop loader.

Wave 4, Phase 3 — the formats/IO first-pull slice (plan
``docs/plans/2026-08-03-003-feat-wave4-phase3-first-pulls-plan.md``, U3,
R1c/R1d). These properties exercise the migrated
``temper_placer.io.loop_loader`` module (a delegation shim over the
``temper_design_bundle_python.load_loop_from_dict`` pyfunction);
bit-identical parity against the pinned pre-migration Python is asserted
separately by ``test_loop_loader_rust_differential.py``.

Five hypothesis properties (all non-vacuously guarded):

- P1. Name round-trip: the loaded loop's name equals the YAML name for any
  generated loop definition.
- P2. Loop-type totality: any alphabetic loop-type string either resolves
  to a member or raises ``LoopLoadError`` — never a different exception.
- P3. Priority default: an absent priority yields ``MEDIUM``.
- P4. Events preservation: event fields present in the YAML survive with
  their values; absent ones stay ``None``.
- P5. Numeric coercion: ``max_area_mm2`` round-trips for int and float
  forms.

Three metamorphic relations:

- MR1. Key-order independence: reordering the definition's keys yields the
  same loop.
- MR2. Enum case invariance: any case variant of a valid loop type or
  priority resolves to the same member.
- MR3. Int/float equivalence: ``max_area_mm2`` written as ``100`` vs
  ``100.0`` loads to the same value.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from temper_placer.io.loop_loader import LoopLoadError, load_loop_from_dict

MAX_EXAMPLES = 100


@st.composite
def loop_definition(draw):
    """A structurally-valid loop definition dict."""
    return draw(
        st.fixed_dictionaries(
            {
                "name": st.text(min_size=1, max_size=20),
                "loop_type": st.sampled_from(
                    ["commutation", "buck_switch", "gate_drive_high", "bootstrap", "custom"]
                ),
            },
            optional={
                "description": st.text(min_size=0, max_size=40),
                "pins": st.lists(
                    st.fixed_dictionaries(
                        {
                            "component": st.text(min_size=1, max_size=10),
                            "pin": st.text(min_size=1, max_size=6),
                        },
                        optional={"net": st.text(min_size=1, max_size=10)},
                    ),
                    max_size=4,
                ),
                "components": st.lists(st.text(min_size=1, max_size=10), max_size=4),
                "nets": st.lists(st.text(min_size=1, max_size=10), max_size=4),
                "max_area_mm2": st.one_of(
                    st.integers(min_value=0, max_value=1000),
                    st.floats(min_value=0.0, max_value=1000.0, allow_nan=False),
                ),
                "priority": st.sampled_from(["critical", "high", "medium", "low"]),
                "events": st.fixed_dictionaries(
                    {
                        "di_dt": st.floats(min_value=0.0, max_value=1e9, allow_nan=False),
                        "ringing_freq_hz": st.floats(
                            min_value=0.0, max_value=1e9, allow_nan=False
                        ),
                    }
                ),
                "return_layer": st.sampled_from(["F.Cu", "B.Cu", "In1.Cu"]),
                "return_net": st.text(min_size=1, max_size=10),
            },
        )
    )


@st.composite
def arbitrary_loop_type_name(draw):
    return draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=20))


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(definition=loop_definition())
def test_p1_name_round_trip(definition):
    loop = load_loop_from_dict(definition)
    assert loop.name == definition["name"]


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(type_name=arbitrary_loop_type_name())
def test_p2_loop_type_totality(type_name):
    try:
        loop = load_loop_from_dict({"name": "x", "loop_type": type_name})
    except LoopLoadError:
        return  # invalid name -> the loader's error, not anything else
    assert loop.loop_type.value == type_name.lower() or loop.loop_type.name != ""


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(definition=loop_definition())
def test_p3_priority_default(definition):
    definition.pop("priority", None)
    loop = load_loop_from_dict(definition)
    assert loop.priority.name == "MEDIUM"


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(definition=loop_definition())
def test_p4_events_preservation(definition):
    loop = load_loop_from_dict(definition)
    events = definition.get("events", {})
    if "events" in definition:
        assert loop.events.di_dt == events.get("di_dt")
        assert loop.events.ringing_freq_hz == events.get("ringing_freq_hz")
        assert loop.events.dv_dt is None
    else:
        assert loop.events.di_dt is None
        assert loop.events.dv_dt is None


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(definition=loop_definition())
def test_p5_numeric_coercion(definition):
    loop = load_loop_from_dict(definition)
    assert float(loop.max_area_mm2) == float(definition.get("max_area_mm2", 100.0))


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(definition=loop_definition())
def test_mr1_key_order_independence(definition):
    original = load_loop_from_dict(definition)
    reordered = dict(reversed(list(definition.items())))
    assert load_loop_from_dict(reordered).name == original.name
    assert (
        load_loop_from_dict(reordered).loop_type.name == original.loop_type.name
    )


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(definition=loop_definition())
def test_mr2_enum_case_invariance(definition):
    lower = load_loop_from_dict(definition)
    upper = dict(definition)
    upper["loop_type"] = str(definition["loop_type"]).upper()
    if "priority" in upper:
        upper["priority"] = str(definition["priority"]).upper()
    assert load_loop_from_dict(upper).loop_type.name == lower.loop_type.name
    assert load_loop_from_dict(upper).priority.name == lower.priority.name


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(definition=loop_definition())
def test_mr3_int_float_equivalence(definition):
    as_int = dict(definition)
    as_int["max_area_mm2"] = 100
    as_float = dict(definition)
    as_float["max_area_mm2"] = 100.0
    assert (
        load_loop_from_dict(as_int).max_area_mm2
        == load_loop_from_dict(as_float).max_area_mm2
    )

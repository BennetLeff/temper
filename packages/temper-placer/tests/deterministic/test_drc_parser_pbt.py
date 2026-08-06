"""Property-based + metamorphic tests for the migrated DRC-report parse kernel.

Wave 4, Phase 5 (deterministic hubs slice). These properties exercise the
migrated ``temper_design_bundle_python.deterministic_hubs.process_drc_violation``
through the ``temper_placer.deterministic.feedback.drc_parser`` shim;
bit-identical parity against the pinned pre-migration Python is asserted
separately by ``test_drc_parser_rust_differential.py``.

Five hypothesis properties (R1c):

- P1. Totality: any raw-violation dict parses without raising and yields all
  ``DRCViolation`` fields.
- P2. Defaults: absent ``type``/``severity``/``description`` yield
  ``"unknown"``/``"error"``/``""``.
- P3. First-pos: only the FIRST item carrying a ``pos`` key contributes the
  position.
- P4. Items are description strings: each item's ``description`` becomes an
  entry in ``items`` (empty string for absent description).
- P5. Clearance extraction: a description carrying the ``clearance X mm;
  actual Y mm`` pattern fills ``required``/``actual`` with the parsed floats.

Three metamorphic relations (R1d):

- MR1. Item reorder with a single ``pos`` keeps the position unchanged (only
  the first pos-bearing item matters; reordering changes WHICH item is first,
  so pin: when exactly one item has pos, position is order-invariant).
- MR2. Unrelated fields: adding arbitrary extra top-level keys to the dict
  never changes the parsed violation.
- MR3. Description independence: a description without a clearance pattern
  leaves ``required``/``actual`` at ``None`` regardless of its other text.
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from temper_placer.deterministic.feedback.drc_parser import _process_raw_violation

_item_st = st.fixed_dictionaries(
    {
        "description": st.text(min_size=0, max_size=40),
    },
    optional={
        "pos": st.fixed_dictionaries({"x": st.floats(-1000, 1000), "y": st.floats(-1000, 1000)}),
    },
)

_payload_st = st.fixed_dictionaries(
    {},
    optional={
        "type": st.text(min_size=0, max_size=20),
        "severity": st.text(min_size=0, max_size=20),
        "description": st.text(min_size=0, max_size=80),
        "items": st.lists(_item_st, min_size=0, max_size=6),
        "unconnected_items": st.lists(_item_st, min_size=0, max_size=3),
        "extraneous": st.text(min_size=0, max_size=10),
    },
)

# Keys the kernel reads: an MR2 "extraneous key" must not collide with these
# (adding "type" to a payload that lacks it changes the DEFAULT, which is
# exactly what the mutation tests).
_KERNEL_KEYS = frozenset(
    {"type", "severity", "description", "items", "pos", "required", "actual"}
)


class TestProperties:
    @given(_payload_st)
    @settings(max_examples=100, deadline=None)
    def test_p1_totality(self, payload):
        v = _process_raw_violation(payload)
        assert isinstance(v.type, str)
        assert isinstance(v.items, list)
        assert isinstance(v.severity, str)

    @given(_payload_st)
    @settings(max_examples=100, deadline=None)
    def test_p2_defaults(self, payload):
        v = _process_raw_violation(payload)
        if "type" not in payload:
            assert v.type == "unknown"
        if "severity" not in payload:
            assert v.severity == "error"
        if "description" not in payload:
            assert v.description == ""

    @given(_payload_st)
    @settings(max_examples=100, deadline=None)
    def test_p3_first_pos_wins(self, payload):
        items = payload.get("items", [])
        pos_bearers = [i for i in items if "pos" in i]
        v = _process_raw_violation(payload)
        if pos_bearers:
            first = pos_bearers[0]["pos"]
            assert v.pos == (first["x"], first["y"])
        else:
            assert v.pos is None

    @given(_payload_st)
    @settings(max_examples=100, deadline=None)
    def test_p4_items_are_descriptions(self, payload):
        v = _process_raw_violation(payload)
        expected = [i.get("description", "") for i in payload.get("items", [])]
        assert v.items == expected

    @given(st.floats(0.001, 1e3, allow_nan=False, allow_infinity=False), st.floats(0.001, 1e3, allow_nan=False, allow_infinity=False))
    @settings(max_examples=60, deadline=None)
    def test_p5_clearance_extraction(self, req, act):
        # Values in [1e-3, 1e3] repr without exponent notation, so the
        # oracle's `[\d\.]+` clearance pattern matches the full literal — the
        # same range bound the oracle itself implies.
        desc = f"clearance {req} mm; actual {act} mm"
        v = _process_raw_violation({"description": desc})
        assert v.required == float(f"{req}") and v.required is not None
        assert v.actual == float(f"{act}") and v.actual is not None


class TestMetamorphic:
    @given(st.lists(_item_st, min_size=2, max_size=6))
    @settings(max_examples=80, deadline=None)
    def test_mr1_single_pos_order_invariant(self, items):
        pos_item = {"description": "Via at (1, 2)", "pos": {"x": 3.5, "y": 4.5}}
        # _item_st may itself carry a pos; strip any so exactly ONE pos-bearing
        # item exists (no filtering needed).
        stripped = [
            {k: v for k, v in i.items() if k != "pos"}
            if isinstance(i, dict)
            else {"description": str(i)}
            for i in items
        ]
        with_pos = stripped + [pos_item]
        without = [pos_item] + stripped
        v1 = _process_raw_violation({"items": with_pos})
        v2 = _process_raw_violation({"items": without})
        # exactly one pos-bearing item exists -> position is order-invariant
        assert v1.pos == v2.pos == (3.5, 4.5)

    @given(_payload_st, st.text(min_size=1, max_size=10), st.integers())
    @settings(max_examples=80, deadline=None)
    def test_mr2_extraneous_keys_noop(self, payload, extra_key, extra_value):
        assume(extra_key not in _KERNEL_KEYS)
        v1 = _process_raw_violation(payload)
        mutated = dict(payload)
        mutated[extra_key] = extra_value
        v2 = _process_raw_violation(mutated)
        assert (v1.type, v1.severity, v1.description, v1.items, v1.pos) == (
            v2.type,
            v2.severity,
            v2.description,
            v2.items,
            v2.pos,
        )

    @given(st.text(min_size=1, max_size=40))
    @settings(max_examples=80, deadline=None)
    def test_mr3_no_clearance_pattern_leaves_none(self, description):
        assume("mm" not in description)
        v = _process_raw_violation({"description": description})
        assert v.required is None
        assert v.actual is None

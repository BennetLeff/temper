"""Differential test: temper_drc_rs ``get_net_current`` vs the StackupGate table.

Wave 4 follow-up, Unit 2 — the "smallest stopped-at-differential-green" case.

``temper_drc_rs.get_net_current`` (the Rust kernel consolidated from
``packages/temper-ipc`` into ``packages/temper-drc-rs``) resolves expected
current by CASE-INSENSITIVE SUBSTRING matching against the
``NET_CURRENTS`` table; ``StackupGate._DEFAULT_NET_CURRENTS`` (the Python
exact-match ``dict.get`` authority) holds the SAME 9 keys and the SAME
``_DEFAULT_CURRENT`` (0.1 A) fallback. This file pins the lookup against the
Python table for every key plus case-variant, substring-superset and unknown
inputs, and records the exact-vs-substring divergence.

VERDICT (per the dispatch rule "keep the Python exact-match as the authority
and document the gap rather than flipping"):

- The Rust kernel agrees with the Python table on all 9 exact keys and on
  genuinely unknown nets (both fall back to 0.1 A).
- The Rust kernel DIVERGES on case variants (``"dc_bus+"`` -> 16.0 Rust vs
  0.1 Python) and on substring-supersets that are REAL, plausible net names
  for this board: ``"/DC_BUS+"`` and ``"Net-(C1-Pad1)-DC_BUS+"`` (KiCad
  hierarchical net forms, already asserted in ``tests/core/test_ipc2152.py``)
  and ``"SW_NODE_DC+"`` / ``"SW_NODE_DC-"`` (both are members of
  ``IECCreepageGate._HV_NET_PATTERNS`` in ``gates.py`` itself).
- The Rust kernel's substring walk also iterates a ``HashMap``, whose
  iteration order is per-process-arbitrary; a net name containing TWO table
  keys would therefore resolve to an order-dependent value.

Therefore StackupGate keeps the Python exact table as the authority:
``_resolve_net_current`` delegates to ``get_net_current`` only when the
kernel's answer agrees with the exact table, and keeps the Python value
otherwise. Behavior is therefore UNCHANGED from the pre-wiring gate; the
delegation is the wiring, the divergence is the documented gap.
"""

from __future__ import annotations

import pytest
import temper_drc_rs
from temper_placer.placer.cp_sat.gates import StackupGate

# The Python exact-match authority under test.
TABLE = StackupGate._DEFAULT_NET_CURRENTS
DEFAULT = StackupGate._DEFAULT_CURRENT


def _python_lookup(net_name: str) -> float:
    return TABLE.get(net_name, DEFAULT)


# ---------------------------------------------------------------------------
# Every table key — the Rust kernel must agree (the flip is safe HERE)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(TABLE))
def test_every_table_key_matches(key):
    rust = float(temper_drc_rs.get_net_current(key))
    assert rust == TABLE[key], f"Rust {key!r} -> {rust}, table {TABLE[key]}"


def test_unknown_nets_agree_on_default():
    for name in ("SOME_RANDOM_NET", "", "NONEXISTENT"):
        assert float(temper_drc_rs.get_net_current(name)) == DEFAULT
        assert _python_lookup(name) == DEFAULT


# ---------------------------------------------------------------------------
# The divergence, pinned as documentation (NOT flipped)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        # Case variants: Rust uppercases the input, Python exact-match does not.
        "dc_bus+",
        "ac_l",
        "+3v3",
        "Gate_H",
        # Substring-supersets that are real/plausible net names for this board.
        "/DC_BUS+",  # KiCad hierarchical net form
        "Net-(C1-Pad1)-DC_BUS+",
        "SW_NODE_DC+",  # member of gates.py _HV_NET_PATTERNS
        "SW_NODE_DC-",
        "+3V3_SENSE",
        "NET_SW_NODE_1",
    ],
)
def test_divergence_pinned_rust_widens_python(name):
    """Rust's case-insensitive substring match returns a table value where the
    Python exact table falls back to the default -- documented, not flipped."""
    rust = float(temper_drc_rs.get_net_current(name))
    py = _python_lookup(name)
    assert rust != py
    assert py == DEFAULT


def test_gate_keeps_python_authority_on_divergent_inputs():
    gate = StackupGate()
    for name in ("/DC_BUS+", "dc_bus+", "SW_NODE_DC+", "+3V3_SENSE", "Net-(C1-Pad1)-DC_BUS+"):
        assert gate._resolve_net_current(name) == DEFAULT


def test_gate_delegates_on_exact_keys_and_unknown_nets():
    gate = StackupGate()
    for key in sorted(TABLE):
        assert gate._resolve_net_current(key) == TABLE[key]
    for name in ("SOME_RANDOM_NET", ""):
        assert gate._resolve_net_current(name) == DEFAULT


def test_gate_behavior_unchanged_from_pre_wiring():
    """The exact table lookups the gate used before the wiring return the
    same values through the new resolution path."""
    gate = StackupGate()
    assert gate._resolve_net_current("DC_BUS+") == 16.0
    assert gate._resolve_net_current("AC_N") == 15.0
    assert gate._resolve_net_current("+15V") == 0.2
    assert gate._resolve_net_current("GATE_L") == 2.0


# ---------------------------------------------------------------------------
# The ambiguous-walk hazard, pinned as a documented non-contract
# ---------------------------------------------------------------------------


def test_substring_table_keys_are_pairwise_disjoint():
    """No table key is a case-insensitive substring of another table key, so
    the Rust HashMap-walk's per-process order cannot flip a value BETWEEN two
    exact keys. The hazard is confined to net names that are supersets of a
    key (pinned above)."""
    upper_keys = {k.upper() for k in TABLE}
    for a in upper_keys:
        for b in upper_keys:
            if a != b:
                assert a not in b

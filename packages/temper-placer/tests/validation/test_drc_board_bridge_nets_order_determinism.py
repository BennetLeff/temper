"""Cross-process determinism regression: ``temper_drc_rs.serialize_board_state``
must emit ``BoardState.nets`` in the same order every process sees it in.

## Background

The WASM-tier board producer (``tools/wasm/r2_serialize_board.py``) calls
``temper_drc_rs.serialize_board_state`` to turn a Python board dict into the
JSON snapshot consumed by ``r2_full_board_pass``. Traces, vias, and zones in
that JSON were verified byte-identical across independent parses; ``nets``
was not (goal-set R5: every finding must name its source artifact by content
hash, which requires the serialization to be a pure function of the board
content).

## Root cause (was misattributed)

The nondeterminism was originally attributed to Rust ``HashMap`` iteration
inside ``temper_design_bundle``'s ``extract_nets_pure``
(``packages/temper-design-bundle/src/parse_engine.rs``). That attribution is
WRONG: ``extract_nets_pure`` builds its output from an explicit
``order: Vec<String>`` populated in first-encounter order and iterates that
Vec, not a map — it is already order-preserving by construction.

The true source is one hop downstream, in THIS crate:
``board_py_bridge.rs::parse_nets_from_dict`` collected the Python ``nets``
dict's items into a ``HashMap<String, Vec<String>>``, and
``build_board_state`` then called ``.into_iter()`` on that map to build the
final ``nets: Vec<Net>``. Rust's default ``HashMap`` hasher (``RandomState``)
draws fresh per-process keys, so `.into_iter()` order is stable *within* one
process (all calls in one process agree) but differs *across* processes —
exactly the "spawn separate processes, not a same-process loop" signature
this test exercises. The fix (see ``board_py_bridge.rs``) replaced the
``HashMap`` intermediate with an order-preserving ``Vec<(String, Vec<String>)>``
built directly from ``PyDict::iter()``, which already yields the dict's
insertion order.

## What this test pins down

1. The *order contract* is first-encounter / input order, NOT sorted order
   (the payload's net names are deliberately not alphabetical, so a
   "silently sort instead" fix would also be caught).
2. ``N`` genuinely separate Python processes (``subprocess``, not a
   same-process loop -- a loop reuses the interpreter's already-seeded
   ``RandomState`` inside the shared, already-loaded ``temper_drc_rs``
   extension module and can never observe cross-process reseeding) must
   produce byte-identical ``serialize_board_state`` output.

Confirmed against the pre-fix code: 12/12 independent processes disagreed on
net order (0 of 12 identical to any other). Post-fix: 12/12 agreed, matching
input order. See the investigating agent's evidence writeup for the full
before/after transcript.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

# Enough net entries that two independent processes coincidentally landing on
# the same permutation by chance is negligible (>= 15! orderings) -- this is
# what makes "byte-identical across N runs" strong evidence rather than luck.
# Deliberately NOT alphabetically sorted, and not numerically sequential
# either, so neither "sorted()" nor "reversed()" could pass by coincidence.
_NET_NAMES = [
    "zz_top", "gnd", "aa_first", "power_in.vbus", "SW_NODE", "mid_net_07",
    "y", "hb.gate_hs.driver-p2", "ac_n", "safety-line", "rtd_pan.low-out",
    "en", "w1_2", "OVP_VREF_2V5", "io0",
]

_PAYLOAD = r"""
import json
import temper_drc_rs as _tdrc

net_names = %r

board_dict = {
    "board": {"width_mm": 100.0, "height_mm": 150.0, "margin_mm": 3.0},
    "components": [],
    "nets": {name: [f"C{i}"] for i, name in enumerate(net_names)},
    "net_classes": {name: "Signal" for name in net_names},
    "net_class_rules": {
        "Signal": {
            "trace_width_mm": 0.2,
            "clearance_mm": 0.2,
            "creepage_mm": None,
            "voltage_v": None,
            "max_current_rating": None,
            "safety_category": None,
            "required_layer": None,
            "routing_strategy": None,
        }
    },
}

out = _tdrc.serialize_board_state(board_dict)
print(out)
""" % (_NET_NAMES,)

# Cross-process is the point: PYTHONHASHSEED is irrelevant here (the payload
# never touches a Python set/dict-comprehension over the net names -- the
# dict is a literal built in insertion order every time). What varies across
# processes is Rust's HashMap RandomState inside the extension module, which
# is reseeded per process, not per PYTHONHASHSEED value. So this deliberately
# does NOT set PYTHONHASHSEED, unlike the sibling
# test_hash_seed_determinism.py -- a different nondeterminism source needs a
# different independent variable.
_N_RUNS = 12


def _run_once() -> str:
    proc = subprocess.run(
        [sys.executable, "-c", _PAYLOAD],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"payload failed:\n{proc.stderr[-4000:]}"
    return proc.stdout.strip().splitlines()[-1]


@pytest.fixture(scope="module")
def outputs() -> list[str]:
    """Raw serialize_board_state() JSON strings from N separate processes."""
    return [_run_once() for _ in range(_N_RUNS)]


def test_payload_actually_serializes_all_nets(outputs):
    """Guard against a vacuous pass: confirm every net actually appears."""
    parsed = json.loads(outputs[0])
    names = [n["name"] for n in parsed["nets"]]
    assert len(names) == len(_NET_NAMES), (
        f"expected {len(_NET_NAMES)} nets, got {len(names)}: {names}"
    )
    assert set(names) == set(_NET_NAMES)
    assert names != sorted(names), (
        "test is vacuous: input net names happen to be alphabetically "
        "sorted already, so this test cannot distinguish 'preserved input "
        "order' from 'silently sorted'"
    )


def test_serialize_board_state_is_byte_identical_across_processes(outputs):
    """The whole JSON string, not just names, must match across N processes."""
    baseline = outputs[0]
    mismatches = [(i, out) for i, out in enumerate(outputs[1:], start=1) if out != baseline]
    assert not mismatches, (
        f"serialize_board_state output depends on process identity: "
        f"{len(mismatches)} of {len(outputs) - 1} other runs disagree with run 0.\n"
        f"  run 0 nets order: {[n['name'] for n in json.loads(baseline)['nets']]}\n"
        + "\n".join(
            f"  run {i} nets order: {[n['name'] for n in json.loads(out)['nets']]}"
            for i, out in mismatches[:3]
        )
    )


def test_nets_order_matches_input_insertion_order_not_sorted(outputs):
    """Pin down *which* order is canonical: input order, not lexicographic.

    This is the order contract ``r2_serialize_board.py`` and every other
    producer of the K1 board dict already relies on (net names are built by
    iterating the parsed netlist in first-encounter order, per
    ``extract_nets_pure``'s contract) -- ``build_board_state`` must not
    silently switch it to sorted order.
    """
    parsed = json.loads(outputs[0])
    names = [n["name"] for n in parsed["nets"]]
    assert names == _NET_NAMES, (
        f"nets order does not match input insertion order.\n"
        f"  got:      {names}\n"
        f"  expected: {_NET_NAMES}\n"
        f"  (sorted() would give: {sorted(_NET_NAMES)})"
    )

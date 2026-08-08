"""Cross-process determinism for ``BoardState.net_class_rules`` JSON output.

``BoardState.net_class_rules`` (packages/temper-drc-rs/src/board.rs) used to
be a ``HashMap<NetClassName, NetClassRules>`` that derives ``Serialize``, so
``serde_json`` emitted its keys in ``HashMap`` iteration order -- and Rust's
default hasher (``RandomState``) reseeds per process, so that order is
stable within one process but differs across processes. This breaks
goal-set R5 (a finding must be able to name its source artifact by content
hash): a JSON snapshot of the same board hashes differently between two
otherwise-identical runs.

The defect is the same species as the ``nets``-ordering bug fixed in
``board_py_bridge.rs`` (commit 0e29a88d, ``parse_nets_from_dict``), and that
commit's own writeup flagged this one as the residual, not-yet-fixed sibling:
"BoardState.net_class_rules is a HashMap<NetClassName, NetClassRules> that
also derives Serialize, so its JSON key order is likewise process-dependent.
Currently masked because pcb/temper.kicad_pcb has exactly one net class
('Signal'); any board with 2+ classes would reproduce the same bug."

Why this test uses genuinely separate processes, not a same-process loop:
Rust's ``RandomState`` hasher is seeded once per process (analogous to
CPython's PEP 456 hash salt) -- no amount of in-process repetition can
observe cross-process reseeding. See
``packages/temper-placer/tests/deterministic/test_hash_order_determinism.py``
for the same reasoning applied to Python-level hash-order defects.

Fix: ``net_class_rules`` is now a ``BTreeMap``, which serializes in sorted
key order regardless of process/hasher seed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# 16 processes: with >=2 net classes there are >=2 possible HashMap
# iteration orders, and empirically (see 0e29a88d's writeup for the sibling
# `nets` bug) independent processes disagree essentially every time pre-fix.
# 16 is comfortably more than enough to make a coincidental all-agree run
# astronomically unlikely while keeping the test fast.
PROCESS_COUNT = 16

REPO_ROOT = Path(__file__).resolve().parents[4]

# A minimal K1-schema board dict (see board_py_bridge.rs::build_board_state's
# doc comment) with SIX net classes -- enough that a HashMap's bucket order
# has many possible permutations, not just the 2-outcome coin flip a
# 2-class board would give. `components`/`nets`/`net_classes` are omitted:
# board_py_bridge.rs's extractors default them to empty when absent.
_SNIPPET = """
import json
import sys

import temper_drc_rs

CLASSES = ["Signal", "Power", "HighVoltage", "GND", "HighSpeed", "ACMains"]

board_dict = {
    "board": {"width_mm": 100.0, "height_mm": 100.0, "margin_mm": 3.0},
    "net_class_rules": {
        name: {
            "name": name,
            "trace_width_mm": 0.2,
            "clearance_mm": 0.2 + i * 0.1,
            "creepage_mm": 0.0,
            "voltage_v": 0.0,
        }
        for i, name in enumerate(CLASSES)
    },
}

board_json = temper_drc_rs.serialize_board_state(board_dict)
# Non-vacuity: the field must actually be present with all 6 classes,
# otherwise a byte-identical empty/degenerate output would trivially pass.
parsed = json.loads(board_json)
assert set(parsed["net_class_rules"].keys()) == set(CLASSES), parsed
print("RESULT " + board_json)
"""


def _run_once() -> str:
    """Run the snippet in a fresh interpreter/process; return its JSON output.

    Each subprocess is a genuinely separate OS process, so Rust's
    per-process hasher reseed (if the defect is present) has an independent
    chance to reorder ``net_class_rules`` on every invocation.
    """
    preamble = f"import sys; sys.path[:0] = {sys.path!r}\n"
    proc = subprocess.run(
        [sys.executable, "-c", preamble + _SNIPPET],
        capture_output=True,
        text=True,
        env=dict(os.environ),
        cwd=str(REPO_ROOT),
        timeout=60,
    )
    assert proc.returncode == 0, (
        f"child process failed (rc={proc.returncode}):\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")]
    assert lines, f"child produced no RESULT line:\n{proc.stdout}"
    return lines[-1][len("RESULT ") :]


def test_net_class_rules_json_order_is_process_independent():
    """The same board must serialize to byte-identical JSON across processes.

    Pre-fix, this fails: 16 independent processes each pick their own
    ``HashMap`` iteration order for a 6-class ``net_class_rules``, so almost
    none of the 16 outputs agree. Post-fix (``BTreeMap``), every process
    sorts by key, so all 16 must be byte-identical.
    """
    outputs = [_run_once() for _ in range(PROCESS_COUNT)]
    baseline = outputs[0]
    disagreeing = [i for i, out in enumerate(outputs) if out != baseline]
    assert not disagreeing, (
        f"net_class_rules JSON depends on process (HashMap reseed): "
        f"{len(disagreeing)} of {PROCESS_COUNT - 1} other processes disagree "
        f"with process 0.\n  process 0        -> {baseline}\n"
        f"  process {disagreeing[0]:<8} -> {outputs[disagreeing[0]]}"
    )


def test_net_class_rules_key_order_is_sorted():
    """Pin *which* order became canonical: sorted by key (BTreeMap), not an
    arbitrary but-stable order -- so a fix that merely stabilizes on some
    other order (e.g. always first-encounter) still fails here.
    """
    out = _run_once()
    parsed = json.loads(out)
    keys = list(parsed["net_class_rules"].keys())
    assert keys == sorted(keys), (
        f"net_class_rules JSON key order is not sorted: {keys!r} "
        f"(expected {sorted(keys)!r} -- BTreeMap serializes in key order)"
    )

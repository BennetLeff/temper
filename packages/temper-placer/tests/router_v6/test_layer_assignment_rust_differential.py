"""R1a differential: ``router_v6/layer_assignment`` vs its pinned oracle (Wave-4 Phase 3).

**THIS SUITE IS DELIBERATELY RED until the Rust kernel is built and the
extension is rebuilt with it.** Every comparison resolves its Rust arm
through ``tests/router_v6/_pending_rust.rust`` and fails with a named
``PendingRustError`` naming the missing symbol until
``temper_rust_router.assign_layers_py`` exists in the built extension --
the same Phase-A convention ``test_net_ordering_rust_differential.py``
established; see ``tests/router_v6/_pending_rust.py``'s module docstring for
why (a skip or an xfail is not an acceptable "red" for gate G1).

Arms
----
* **oracle** -- ``tests/router_v6/_layer_assignment_py_oracle.py``, a
  verbatim ``git show`` copy of ``layer_assignment.py`` at
  ``550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5`` (``origin/main``).
* **rust** -- ``temper_rust_router.assign_layers_py``
  (``packages/temper-rust-router/src/layer_assignment.rs``).

Comparison is by type-carrying signature (``tests/router_v6/_signature``).
No tolerance anywhere.

Scope: why this differential only ever calls
``assign_layers(netlist, constraints=None, component_positions=None)``
-------------------------------------------------------------------------
``assign_layers`` has exactly one production caller
(``router_v6/verifier.py``'s ``assign_layers(netlist)``), and no test in this
repository ever passes it a custom ``constraints=`` list or a
``component_positions=`` array either (see the oracle module's docstring for
the repo-wide grep evidence). Under ``constraints=None,
component_positions=None`` the function collapses to walking
``DEFAULT_LAYER_CONSTRAINTS`` in order and taking the first
``re.fullmatch`` -- that is the entire surface this differential compares.
``_get_net_dominant_direction`` and the geometric/custom-constraint branches
are pinned in the oracle (so it is a faithful, complete copy) but are NOT
exercised here and have no Rust counterpart -- porting dead code would build
a second implementation nothing calls and no test (including this one) could
honestly pin.

Traps this file pins explicitly
--------------------------------
* **First-match-wins order is source order, not specificity.** ``GATE_GND``
  matches both the GATE_.* constraint (index 1) and the .*_GND constraint
  (index 5); index 1 must win (:func:`test_first_match_wins_is_source_order`).
* **Exact alternatives are not prefixes.** ``SW_NODE`` is a bare alternative
  in constraint 0, not ``SW_NODE.*``; ``SW_NODE2`` must fall through to the
  catch-all, not match constraint 0
  (:func:`test_exact_alternative_is_not_a_prefix_match`).
* **Suffix matching is a true suffix, not a substring test.** ``.*_GND``
  matches ``SENSOR_GND`` but not ``GNDX``
  (:func:`test_ground_suffix_is_not_a_substring_test`).
* **An embedded newline defeats even the ``.*`` catch-all**, because
  Python's ``.`` does not match ``\\n`` without ``re.DOTALL`` and
  ``re.fullmatch`` requires the WHOLE string consumed. That flips
  ``matched_constraint`` to ``None`` and the oracle takes a genuinely
  different branch: a two-layer ``allowed_layers`` and a different ``reason``
  string, not the four-layer catch-all
  (:func:`test_embedded_newline_defeats_the_catch_all`).
* **Vias-required is always True on every reachable path** -- every
  ``DEFAULT_LAYER_CONSTRAINTS`` entry lists all four layers, and even the
  newline-fallback's two-layer set has ``len() > 1`` -- checked as a
  property here rather than assumed
  (:func:`test_vias_required_is_always_true_here`).
* **Output order and duplicate-name overwrite semantics** must match
  ``dict``'s: last value wins, first-seen position is kept
  (:func:`test_duplicate_net_names_keep_first_position_last_value`).
"""

from __future__ import annotations

import ast
import string
import subprocess

import pytest
from hypothesis import given
from hypothesis import strategies as st

import tests.router_v6._layer_assignment_py_oracle as ORACLE
from tests.router_v6._pending_rust import missing_symbols, rust
from tests.router_v6._signature import sig

# ===========================================================================
# ADAPTER BLOCK -- the ONLY part of this file that knows the Rust arm exists.
# ===========================================================================

#: Migration target -- see the crate's module docstring for why
#: temper-rust-router (not temper-geometry) hosts this kernel: it is a
#: string/regex match over net names, not geometry.
_RUST_MODULE = "temper_rust_router"

REQUIRED_RUST_SYMBOLS: tuple[str, ...] = ("assign_layers_py",)


def _rust(symbol: str):
    return rust(_RUST_MODULE, symbol)


def _rust_assign_layers(net_names: list[str]):
    fn = _rust("assign_layers_py")  # RED until the extension is rebuilt
    return fn(net_names)


# ===========================================================================
# END ADAPTER BLOCK
# ===========================================================================

_ORACLE_PIN_SHA = "550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5"
_ORACLE_NAMES: tuple[str, ...] = (
    "Layer",
    "LayerConstraint",
    "LayerAssignment",
    "matches_pattern",
    "DEFAULT_LAYER_CONSTRAINTS",
    "assign_layers",
    "_get_net_dominant_direction",
)


def _build_netlist(net_names: list[str]):
    """A ``Netlist`` with no components and one zero-pin ``Net`` per name --
    everything ``assign_layers(netlist, constraints=None,
    component_positions=None)`` reads (only ``net.name``, per the loop's
    `for net in netlist.nets`)."""
    from temper_placer.core.netlist import Net, Netlist

    return Netlist(components=[], nets=[Net(name=n, pins=[]) for n in net_names])


def _oracle_rows(net_names: list[str]) -> list[tuple]:
    """The oracle's ``assign_layers`` output, reduced to the same
    ``(primary_layer_value, sorted(allowed_layers_values), vias_required,
    reason)`` shape the Rust kernel returns, in ``net_names`` order (the
    oracle's dict preserves first-insertion order under duplicates, same as
    a plain loop over ``net_names``)."""
    netlist = _build_netlist(net_names)
    out = ORACLE.assign_layers(netlist)
    rows = []
    seen: dict[str, tuple] = {}
    for name in net_names:
        a = out[name]
        seen[name] = (
            a.primary_layer.value,
            sorted(layer.value for layer in a.allowed_layers),
            a.vias_required,
            a.reason,
        )
    for name in net_names:
        rows.append(seen[name])
    return rows


def _rust_rows(net_names: list[str]) -> list[tuple]:
    raw = _rust_assign_layers(net_names)
    return [(primary, sorted(allowed), vias, reason) for primary, allowed, vias, reason in raw]


def _assert_same(net_names: list[str]):
    a = _oracle_rows(net_names)
    b = _rust_rows(net_names)
    assert sig(a) == sig(b), f"net_names={net_names!r}: oracle={a!r} rust={b!r}"


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
            continue
        # DEFAULT_LAYER_CONSTRAINTS is a module-level `Assign`, not a def --
        # `ast.FunctionDef`/`ClassDef` are the only node kinds with `.name`.
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            tgt = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            tgt = node.targets[0].id
        else:
            tgt = None
        if tgt in names:
            out[tgt] = "\n".join(lines[node.lineno - 1 : node.end_lineno])
    return out


def test_oracle_is_verbatim_copy():
    """Every definition in the oracle is character-identical to the pin."""
    rel = "packages/temper-placer/src/temper_placer/router_v6/layer_assignment.py"
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
        assert name in original, f"{name} missing from layer_assignment.py at the pin"
        assert copied[name] == original[name], (
            f"layer_assignment.py::{name} in the oracle is NOT verbatim -- "
            f"the pin is broken and the differential proves nothing"
        )


def test_rust_symbols_exist():
    """The Phase-A checklist. RED until the extension is rebuilt with the kernel."""
    missing = missing_symbols(_RUST_MODULE, REQUIRED_RUST_SYMBOLS)
    assert not missing, (
        f"{_RUST_MODULE} is missing {len(missing)} of {len(REQUIRED_RUST_SYMBOLS)} "
        f"layer_assignment kernels: {missing}"
    )


# ---------------------------------------------------------------------------
# Curated corpus -- one net name per DEFAULT_LAYER_CONSTRAINTS entry, plus
# the traps named in the module docstring.
# ---------------------------------------------------------------------------


def test_each_default_constraint_representative():
    reps = [
        "DC_BUS_P",  # constraint 0, prefix alt
        "SW_NODE",  # constraint 0, exact alt
        "AC_L",  # constraint 0, exact alt
        "GATE_H",  # constraint 1
        "SENSE_1",  # constraint 2
        "I_SENSE",  # constraint 2, exact alt
        "SPI_CLK",  # constraint 3
        "USB_DP",  # constraint 4
        "GND",  # constraint 5, exact alt
        "PGND",  # constraint 5, exact alt
        "SENSOR_GND",  # constraint 5, suffix alt
        "MYSTERY_NET",  # constraint 6, catch-all
    ]
    _assert_same(reps)


def test_first_match_wins_is_source_order():
    # GATE_GND matches both GATE_.* (index 1) and .*_GND (index 5).
    _assert_same(["GATE_GND"])


def test_exact_alternative_is_not_a_prefix_match():
    # SW_NODE is a bare alternative, not SW_NODE.* -- SW_NODE2 must fall
    # through past constraint 0 to the catch-all.
    _assert_same(["SW_NODE", "SW_NODE2", "SW_NODEX"])


def test_ground_suffix_is_not_a_substring_test():
    _assert_same(["GNDX", "XGND", "SENSOR_GND", "PGND", "AGND2"])


def test_embedded_newline_defeats_the_catch_all():
    # `.` does not match `\n`; the r".*" catch-all cannot fullmatch a name
    # with an embedded newline, so the oracle's "no constraint matched"
    # fallback (a DIFFERENT, two-layer allowed set) fires.
    _assert_same(["WEIRD\nNET"])


def test_empty_net_list():
    _assert_same([])


def test_empty_net_name():
    _assert_same([""])


def test_duplicate_net_names_keep_first_position_last_value():
    _assert_same(["GND", "SPI_CLK", "GND", "SPI_CLK"])


def test_vias_required_is_always_true_here():
    for names in (["DC_BUS_P"], ["WEIRD\nNET"], ["ANYTHING"]):
        rows = _rust_rows(names)
        assert all(row[2] is True for row in rows), rows


# ---------------------------------------------------------------------------
# Property-based sweep
# ---------------------------------------------------------------------------

_NET_NAME_ALPHABET = string.ascii_uppercase + string.digits + "_+-.\n"


@given(
    st.lists(
        st.text(alphabet=_NET_NAME_ALPHABET, min_size=0, max_size=24),
        min_size=0,
        max_size=12,
    )
)
def test_property_random_net_names(net_names: list[str]):
    _assert_same(net_names)

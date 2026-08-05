"""Differential test: netlist<->board reconciliation compute in Rust
(temper_design_bundle_python.validation) vs the pinned Python oracle
(Wave 4, Phase 4 — validation remainder slice).

``temper_placer/validation/netlist_reconciliation.py`` moves its compute —
the self-contained s-expression parser (``_sexp``), the design-netlist parse
navigation (``_field``/``_children``/``_instance_path_from_sheetpath`` and
the strict fail-closed checks), and the reconciliation decision logic
(``_component_findings``/``_net_findings``/``_resolve_design_net_paths``/
``reconcile``) — to the ``validation`` submodule of
``temper_design_bundle_python``. The Python module keeps the dataclasses
(``BoardNetlist``/``DesignNetlist``/``ReconciliationFinding``/
``ReconciliationReport``/``ReconciliationGateError``), the file I/O
(``extract_board_netlist``'s ``parse_kicad_pcb_v6`` call,
``parse_design_netlist``'s file read), and the board-side traversal
(``build_board_netlist`` reads the Component contract pyclass attributes).
Every error string raised by the parser/parse/reconcile is byte-identical
(they are plain str / ``!r`` interpolations — no no-format float repr), and
the shim re-wraps the kernel's ``PyValueError`` into
``ReconciliationGateError`` with ``from None`` (the oracle raises the gate
error directly, so ``__cause__`` is None on both sides).

Comparison convention: findings/reports/components/nets are compared with
exact ``==`` plus a type-carrying canonicalizer for the tuple/str/int
leaves; error strings are compared byte-for-byte via ``str(exc)``.

Sections:
- Differential bit-exactness (parser, parse, reconcile, error strings).
- PBT (hypothesis): five non-vacuous properties.
- Metamorphic relations: three, honestly bounded.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import temper_design_bundle_python as _tdb
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import tests.validation._netlist_reconciliation_py_oracle as _oracle
from temper_placer.core.netlist import Component, Pin
from temper_placer.validation.netlist_reconciliation import (
    BoardComponent,
    BoardNetlist,
    DesignComponent,
    DesignNetlist,
    ReconciliationGateError,
)
from temper_placer.validation.netlist_reconciliation import (
    build_board_netlist as shim_build_board_netlist,  # noqa: E402
)
from temper_placer.validation.netlist_reconciliation import (
    parse_design_netlist as shim_parse_design_netlist,  # noqa: E402
)
from temper_placer.validation.netlist_reconciliation import (
    reconcile as shim_reconcile,  # noqa: E402
)

# Rust symbols under test — must exist or this file fails to collect (RED).
PARSE_DESIGN_NETLIST = _tdb.validation.parse_design_netlist
RECONCILE = _tdb.validation.reconcile

# ---------------------------------------------------------------------------
# Canonicalization
# ---------------------------------------------------------------------------


def _canon_report(r) -> tuple:
    return (
        tuple(
            (f.kind, f.severity, f.detail, tuple(f.refs), tuple(f.paths))
            for f in r.findings
        ),
        r.design_components,
        r.board_components,
        r.matched_paths,
        r.design_nets_nonempty,
        r.board_nets,
    )


def _canon_design(d) -> tuple:
    return (
        tuple((c.ref, c.instance_path) for c in d.components),
        tuple(sorted((name, tuple(nodes)) for name, nodes in d.nets.items())),
        tuple(d.duplicate_refs),
    )


# ---------------------------------------------------------------------------
# Input construction
# ---------------------------------------------------------------------------

_REF = st.text(min_size=1, max_size=5).map(lambda s: f"C{abs(hash(s)) % 499}")
_PATH = st.text(min_size=1, max_size=12).map(lambda s: f"mod{abs(hash(s)) % 97}.inst{abs(hash(s)) % 977}")
_PIN = st.text(min_size=1, max_size=3).map(lambda s: f"p{abs(hash(s)) % 31}")
# Net names are rendered inside a JSON quoted token — control chars would
# make the token unparseable (json.loads rejects them).
_NETNAME = st.text(
    min_size=1, max_size=8, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"
)


def _comp(ref: str, sheetpath: str | None, nets: list[tuple[str, str]]) -> Component:
    pins = [Pin(name=p, number=p, position=(0.0, 0.0), net=n) for p, n in nets]
    return Component(ref=ref, footprint="temper:Test", bounds=(1.0, 1.0), pins=pins, sheetpath=sheetpath)


def _design(comps, nets) -> DesignNetlist:
    return DesignNetlist(
        components=[DesignComponent(ref=ref, instance_path=path) for ref, path in comps],
        nets=nets,
    )


def _netlist_text(comps, nets) -> str:
    """Render a design netlist .net file exactly like the real compiler
    (sheetpath (names "...:Top::<suffix>") shape)."""
    blocks = []
    for ref, suffix in comps:
        blocks.append(
            f'    (comp (ref "{ref}")\n'
            f'      (value "?")\n'
            f'      (footprint "fp")\n'
            f'      (sheetpath (names "/repo/main.ato:Top::{suffix}") (tstamps "0"))\n'
            f'      (tstamps "0"))'
        )
    net_blocks = []
    for code, (name, nodes) in enumerate(nets, start=1):
        node_str = " ".join(f'(node (ref "{r}") (pin "{p}"))' for r, p in nodes)
        net_blocks.append(f'    (net (code "{code}") (name "{name}") {node_str})')
    return (
        '(export (version "E")\n  (components\n' + "\n".join(blocks) + "\n  )\n  (nets\n"
        + "\n".join(net_blocks) + "\n  )\n)\n"
    )


def _write_netlist(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "default.net"
    p.write_text(text, encoding="utf-8")
    return p


def _run_parse_both(tmp_path: Path, text: str):
    path = _write_netlist(tmp_path, text)
    # Random netlists are not guaranteed valid — hypothesis can emit duplicate
    # net names / instance paths / pins. The oracle raises its own exception
    # class (pinned verbatim); the shim re-wraps into the module's. When BOTH
    # sides raise, compare the error strings (fail-closed parity); when both
    # parse, compare the canonical results. One-sided errors fail the assert.
    try:
        oracle = _canon_design(_oracle.parse_design_netlist(path))
    except (_oracle.ReconciliationGateError, ReconciliationGateError) as e:
        oracle = ("ERROR", str(e))
    try:
        shim = _canon_design(shim_parse_design_netlist(path))
    except (_oracle.ReconciliationGateError, ReconciliationGateError) as e:
        shim = ("ERROR", str(e))
    return oracle, shim


# ---------------------------------------------------------------------------
# Differential — the s-expression parser (via parse_design_netlist)
# ---------------------------------------------------------------------------


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    st.lists(st.tuples(_REF, _PATH), min_size=1, max_size=6),
    st.lists(
        st.tuples(_NETNAME, st.lists(st.tuples(_REF, _PIN), min_size=1, max_size=4)),
        min_size=1,
        max_size=5,
    ),
)
def test_parse_differential_random(tmp_path, comps, nets):
    oracle, shim = _run_parse_both(tmp_path, _netlist_text(comps, nets))
    assert shim == oracle


def test_parse_differential_hand_built(tmp_path):
    """Duplicate refs (tolerated as REUSE candidates), quoted strings with
    escapes, multiline + whitespace layout, and the empty-net declaration."""
    text = (
        '(export (version "E")\n'
        "  (components\n"
        '    (comp (ref "R1") (value "?")\n'
        '      (sheetpath (names "/a/b.ato:Top::x.r1") (tstamps "0")))\n'
        '    (comp (ref "R1") (value "?")\n'
        '      (sheetpath (names "/a/b.ato:Top::y.r2") (tstamps "0")))\n'
        "  )\n"
        "  (nets\n"
        '    (net (code "1") (name "gnd")\n'
        '      (node (ref "R1") (pin "1")))\n'
        '    (net (code "2") (name "sig") (node (ref "R1") (pin "2")))\n'
        '    (net (code "3") (name "declared_empty"))\n'
        "  )\n)\n"
    )
    oracle, shim = _run_parse_both(tmp_path, text)
    assert shim == oracle
    # Duplicate ref recorded with first-seen path order.
    assert shim[2] == (("R1", "x.r1", "y.r2"),)

    # Escaped quote inside a quoted token (the regex's `\\.` alternative).
    text2 = text.replace('"gnd"', '"g\\"n\\"d"')
    oracle, shim = _run_parse_both(tmp_path, text2)
    assert shim == oracle


def test_parse_error_strings_byte_identical(tmp_path):
    """Every parser/gate error is byte-identical, including the `!r` reprs
    and the character-index syntax position."""
    cases = [
        # unbalanced ')'
        "(export)\n)",
        # unbalanced '('
        "(export\n",
        # invalid syntax at a byte position (mid-text garbage)
        '(export (version "E"))\n  <garbage!!>\n',
        # missing export block
        "(components)\n",
        # zero components
        '(export (version "E")\n  (components\n  )\n  (nets\n'
        '    (net (code "1") (name "gnd"))\n  )\n)\n',
        # zero nets
        '(export (version "E")\n  (components\n'
        '    (comp (ref "R1")\n      (sheetpath (names "/a.ato:Top::x") (tstamps "0")))\n'
        "  )\n  (nets\n  )\n)\n",
        # two components blocks
        '(export (version "E")\n  (components\n  )\n  (components\n  )\n  (nets\n'
        '    (net (code "1") (name "gnd"))\n  )\n)\n',
        # missing required 'ref' field
        '(export (version "E")\n  (components\n    (comp (value "?"))\n  )\n  (nets\n'
        '    (net (code "1") (name "gnd"))\n  )\n)\n',
        # malformed ref field (not a string)
        '(export (version "E")\n  (components\n    (comp (ref 42))\n  )\n  (nets\n'
        '    (net (code "1") (name "gnd"))\n  )\n)\n',
        # no usable sheetpath
        '(export (version "E")\n  (components\n'
        '    (comp (ref "R1") (sheetpath (names "/plain" ) (tstamps "0")))\n'
        "  )\n  (nets\n"
        '    (net (code "1") (name "gnd"))\n  )\n)\n',
        # duplicate instance path
        '(export (version "E")\n  (components\n'
        '    (comp (ref "R1")\n      (sheetpath (names "/a.ato:Top::x.r1") (tstamps "0")))\n'
        '    (comp (ref "R2")\n      (sheetpath (names "/a.ato:Top::x.r1") (tstamps "0")))\n'
        "  )\n  (nets\n"
        '    (net (code "1") (name "gnd"))\n  )\n)\n',
        # duplicate net name
        '(export (version "E")\n  (components\n'
        '    (comp (ref "R1")\n      (sheetpath (names "/a.ato:Top::x") (tstamps "0")))\n'
        "  )\n  (nets\n"
        '    (net (code "1") (name "gnd"))\n    (net (code "2") (name "gnd"))\n  )\n)\n',
        # pin in more than one net
        '(export (version "E")\n  (components\n'
        '    (comp (ref "R1")\n      (sheetpath (names "/a.ato:Top::x") (tstamps "0")))\n'
        "  )\n  (nets\n"
        '    (net (code "1") (name "gnd") (node (ref "R1") (pin "1")))\n'
        '    (net (code "2") (name "sig") (node (ref "R1") (pin "1")))\n  )\n)\n',
        # zero-child '(comp)' node: node[0] renders the head atom 'comp' —
        # a plain gate error on BOTH arms (the s-expression parser always
        # stores the head, so the oracle's node[0] cannot IndexError here).
        '(export (version "E")\n  (components\n    (comp)\n  )\n  (nets\n'
        '    (net (code "1") (name "gnd"))\n  )\n)\n',
        # zero-child '(net)' node (same head-rendering class)
        '(export (version "E")\n  (components\n'
        '    (comp (ref "R1")\n      (sheetpath (names "/a.ato:Top::x") (tstamps "0")))\n'
        "  )\n  (nets\n    (net)\n  )\n)\n",
        # Unicode whitespace separates tokens exactly like Python's `\s`
        # with re.S: a bare token glued to \xa0 is TWO tokens, so the head
        # renders 'comp' (not 'comp\xa0') and the error strings stay
        # byte-identical. \xa0 is also non-printable: the repr-escaping
        # deviation would render a glued token differently, which is why
        # this split point must be pinned (P2-3).
        '(export (version "E")\n  (components\n    (comp\xa0\xa0)\n  )\n  (nets\n'
        '    (net (code "1") (name "gnd"))\n  )\n)\n',
        # \u2028 (line separator) and \u3000 (ideographic space) split the
        # same way.
        '(export (version "E")\n  (components\n    (comp\u2028)\n  )\n  (nets\n'
        '    (net (code "1") (name "gnd"))\n  )\n)\n',
        '(export (version "E")\n  (components\n    (comp\u3000)\n  )\n  (nets\n'
        '    (net (code "1") (name "gnd"))\n  )\n)\n',
    ]
    for text in cases:
        path = _write_netlist(tmp_path, text)
        # The oracle is pinned verbatim, so it raises its OWN exception class;
        # the shim re-wraps into the module's. Catch both, compare strings.
        with pytest.raises((_oracle.ReconciliationGateError, ReconciliationGateError)) as o_exc:
            _oracle.parse_design_netlist(path)
        with pytest.raises((_oracle.ReconciliationGateError, ReconciliationGateError)) as s_exc:
            shim_parse_design_netlist(path)
        assert str(s_exc.value) == str(o_exc.value), text


# ---------------------------------------------------------------------------
# Differential — reconcile
# ---------------------------------------------------------------------------


def _run_reconcile_both(board_comps, board_nets, design_comps, design_nets, dup_refs=()):
    board = BoardNetlist(
        components=[
            BoardComponent(ref=ref, sheetpath=sheetpath) for ref, sheetpath in board_comps
        ],
        # The module contract (build_board_netlist) stores board net node
        # sets as SETS; normalize any list-valued input the same way so the
        # oracle and the kernel see the identical deduped domain.
        nets={name: set(paths) for name, paths in board_nets.items()},
    )
    design = DesignNetlist(
        components=[DesignComponent(ref=r, instance_path=p) for r, p in design_comps],
        nets=design_nets,
        duplicate_refs=list(dup_refs),
    )
    return _canon_report(_oracle.reconcile(board, design)), _canon_report(shim_reconcile(board, design))

@settings(max_examples=50, deadline=None)
@given(
    st.lists(st.tuples(_REF, st.one_of(st.none(), _PATH)), min_size=0, max_size=6),
    st.lists(
        st.tuples(_NETNAME, st.lists(_PATH, min_size=0, max_size=4)),
        min_size=0,
        max_size=5,
    ),
    st.lists(st.tuples(_REF, _PATH), min_size=0, max_size=6),
    st.lists(
        st.tuples(_NETNAME, st.lists(st.tuples(_REF, _PIN), min_size=0, max_size=4)),
        min_size=0,
        max_size=5,
    ),
    st.lists(st.tuples(_REF, _PATH, _PATH), min_size=0, max_size=3),
)
def test_reconcile_differential_random(board_comps, board_nets, design_comps, design_nets, dup_refs):
    board_comps2 = [(r, sp or "") for r, sp in board_comps]
    oracle, shim = _run_reconcile_both(board_comps2, dict(board_nets), design_comps, dict(design_nets), dup_refs)
    assert shim == oracle


def test_reconcile_differential_hand_built():
    clean_board = [
        ("C1", "a.cap1"), ("C2", "b.cap2"), ("R1", "c.r1"),
    ]
    clean_nets = {"gnd": {"a.cap1", "b.cap2", "c.r1"}, "vcc": {"a.cap1", "b.cap2"}, "sig": {"c.r1"}}
    clean_design = [("C1", "a.cap1"), ("C2", "b.cap2"), ("R1", "c.r1")]
    design_nets = {
        "gnd": [("C1", "1"), ("C2", "1"), ("R1", "1")],
        "vcc": [("C1", "2"), ("C2", "2")],
        "sig": [("R1", "2")],
    }

    # Clean pair: zero findings.
    oracle, shim = _run_reconcile_both(clean_board, clean_nets, clean_design, design_nets)
    assert shim == oracle
    assert shim[3] == 3  # matched_paths

    # MISSING design component.
    oracle, shim = _run_reconcile_both(
        clean_board, clean_nets, clean_design + [("C3", "tank.c_tank3")], design_nets
    )
    assert shim == oracle
    assert any(f[0] == "MISSING" for f in shim[0])

    # RENUMBERED (same path, different ref).
    oracle, shim = _run_reconcile_both(
        clean_board, clean_nets, [("C9", "a.cap1"), ("C2", "b.cap2"), ("R1", "c.r1")], design_nets
    )
    assert shim == oracle
    assert any(f[0] == "RENUMBERED" for f in shim[0])

    # EXTRA board component.
    oracle, shim = _run_reconcile_both(
        clean_board + [("R9", "stale.r_old")],
        {**clean_nets, "orphan": {"stale.r_old"}},
        clean_design,
        design_nets,
    )
    assert shim == oracle
    assert any(f[0] == "EXTRA" for f in shim[0])

    # REUSE on the board side (one ref, two paths).
    oracle, shim = _run_reconcile_both(
        [("C1", "a.cap1"), ("C1", "b.cap2"), ("R1", "c.r1")],
        {"gnd": {"a.cap1", "b.cap2", "c.r1"}},
        clean_design,
        design_nets,
    )
    assert shim == oracle
    assert any(f[0] == "REUSE" for f in shim[0])

    # REUSE on the design side via duplicate_refs.
    oracle, shim = _run_reconcile_both(
        clean_board, clean_nets, clean_design, design_nets,
        dup_refs=[("C1", "a.cap1", "b.cap2")],
    )
    assert shim == oracle
    assert any(f[0] == "REUSE" for f in shim[0])

    # UNKEYABLE board footprint (empty sheetpath) reported, never dropped.
    oracle, shim = _run_reconcile_both(
        [("R99", ""), ("C1", "a.cap1")],
        {"gnd": {"", "a.cap1"}},
        [("C1", "a.cap1")],
        {"gnd": [("C1", "1")]},
    )
    assert shim == oracle
    assert any(f[0] == "UNKEYABLE" for f in shim[0])

    # NET-MISSING (design net absent on board).
    oracle, shim = _run_reconcile_both(
        clean_board, clean_nets, clean_design,
        {**design_nets, "new_net": [("R1", "2")]},
    )
    assert shim == oracle
    assert any(f[0] == "NET-MISSING" for f in shim[0])

    # NET-EXTRA (board net absent in design).
    oracle, shim = _run_reconcile_both(
        clean_board, {**clean_nets, "orphan": {"a.cap1"}}, clean_design, design_nets
    )
    assert shim == oracle
    assert any(f[0] == "NET-EXTRA" for f in shim[0])

    # NET-MEMBERSHIP from a design-side membership difference.
    oracle, shim = _run_reconcile_both(
        clean_board, clean_nets, clean_design,
        {**design_nets, "vcc": [("C1", "2"), ("C2", "2"), ("R1", "2")]},
    )
    assert shim == oracle
    assert any(f[0] == "NET-MEMBERSHIP" for f in shim[0])

    # NET-MEMBERSHIP from the dropped-net signature: design net declared
    # EMPTY but board side intact.
    oracle, shim = _run_reconcile_both(
        clean_board, clean_nets, clean_design,
        {**design_nets, "gnd": []},
    )
    assert shim == oracle
    assert any(f[0] == "NET-MEMBERSHIP" for f in shim[0])

    # Declared-but-empty design net with NO board counterpart is NOT a finding.
    oracle, shim = _run_reconcile_both(
        clean_board, clean_nets, clean_design,
        {**design_nets, "gnd_ref": []},
    )
    assert shim == oracle
    assert not shim[0]


def test_build_board_netlist_matches_oracle():
    """The shim's board-side traversal (unchanged Python) produces identical
    BoardNetlist data — the reconcile kernel's board-side input contract."""
    comps = [
        _comp("C1", "a.cap1", [("1", "gnd"), ("2", "vcc")]),
        _comp("R99", None, [("1", "gnd")]),
    ]
    oracle = _oracle.build_board_netlist(comps)
    shim = shim_build_board_netlist(comps)
    assert [(c.ref, c.sheetpath) for c in shim.components] == [
        (c.ref, c.sheetpath) for c in oracle.components
    ]
    assert shim.nets == oracle.nets


# ---------------------------------------------------------------------------
# PBT — five non-vacuous properties (R1c)
# ---------------------------------------------------------------------------


@settings(max_examples=40, deadline=None)
@given(st.lists(st.tuples(_REF, _PATH), min_size=1, max_size=6))
def test_prop1_reconcile_against_empty_board_reports_missing_for_every_design(comps):
    """Every design component is MISSING when the board side is empty, and
    the gate fails (never an empty report with a pass)."""
    # Findings are path-keyed, so the property's uniqueness precondition
    # holds only for distinct paths (hypothesis can draw duplicates).
    seen: set[str] = set()
    comps = [(r, p) for r, p in comps if not (p in seen or seen.add(p))]
    oracle, shim = _run_reconcile_both([], {}, comps, {"gnd": [("X", "1")]})
    assert shim == oracle
    missing = [f for f in shim[0] if f[0] == "MISSING"]
    assert len(missing) == len(comps)
    assert shim[0]  # findings non-empty (anti-vacuity)


def test_prop2_finding_kinds_are_exhaustive_and_codes_are_unique_per_finding():
    """Every finding kind is one of the documented taxonomy, and the same
    (kind, refs, paths) triple never appears twice."""
    board_comps = [("C1", ""), ("C1", "a.cap1"), ("C2", "b.cap2")]
    oracle, shim = _run_reconcile_both(
        board_comps, {"gnd": {"", "a.cap1", "b.cap2"}},
        [("C9", "a.cap1"), ("C3", "z.missing")],
        {"gnd": [("C9", "1")], "empty": []},
        dup_refs=[("C1", "a.cap1", "b.cap2")],
    )
    assert shim == oracle
    kinds = {f[0] for f in shim[0]}
    allowed = {"MISSING", "EXTRA", "RENUMBERED", "REUSE", "UNKEYABLE",
               "NET-MISSING", "NET-EXTRA", "NET-MEMBERSHIP"}
    assert kinds <= allowed
    assert len(shim[0]) == len({(f[0], f[3], f[4]) for f in shim[0]})


@settings(max_examples=40, deadline=None)
@given(
    st.lists(st.tuples(_REF, _PATH), min_size=0, max_size=6),
    st.lists(st.tuples(_NETNAME, st.lists(_PATH, min_size=0, max_size=4)), min_size=0, max_size=5),
)
def test_prop3_duplicate_board_components_always_fail_the_gate(comps, nets):
    """Two board footprints sharing one ref always yield a REUSE finding and
    a failing report."""
    board_comps = comps + ([(comps[0][0], "extra.path")] if comps else [("R1", "a"), ("R1", "b")])
    oracle, shim = _run_reconcile_both(
        board_comps, dict(nets), [("R1", "a")], {"gnd": [("R1", "1")]}
    )
    assert shim == oracle
    assert any(f[0] == "REUSE" for f in shim[0])


@settings(max_examples=40, deadline=None)
@given(st.lists(st.tuples(_REF, _PATH), min_size=1, max_size=6))
def test_prop4_identical_sides_always_pass(comps):
    """A board and design built from the same component list with matching
    nets reconcile with zero findings and full matched_paths."""
    # Zero findings requires unique REFS and unique PATHS: a reused ref is
    # a genuine REUSE finding and a repeated path a RENUMBERED candidate
    # even when both sides are identical (hypothesis can draw either).
    seen_refs: set[str] = set()
    seen_paths: set[str] = set()
    comps = [
        (r, p)
        for r, p in comps
        if r not in seen_refs
        and p not in seen_paths
        and not (seen_refs.add(r) or seen_paths.add(p))
    ]
    paths = [p for _, p in comps]
    board_comps = comps
    board_nets = {"gnd": set(paths)}
    design_nets = {"gnd": [(r, "1") for r, _ in comps]}
    oracle, shim = _run_reconcile_both(board_comps, board_nets, comps, design_nets)
    assert shim == oracle
    assert shim[0] == ()
    assert shim[3] == len(comps)


@settings(max_examples=40, deadline=None)
@given(
    st.lists(st.tuples(_REF, _PATH), min_size=1, max_size=5),
    st.lists(_PATH, min_size=0, max_size=4),
)
def test_prop5_net_membership_findings_are_symmetric_in_component_difference(comps, extra_paths):
    """When a net's board and design node sets differ, the NET-MEMBERSHIP
    finding names exactly the symmetric difference, sorted."""
    board_paths = {p for _, p in comps} | set(extra_paths)
    design_comps = comps
    design_nets = {"n1": [(r, "1") for r, _ in comps]}
    board_comps = design_comps
    board_nets = {"n1": board_paths}
    oracle, shim = _run_reconcile_both(board_comps, board_nets, design_comps, design_nets)
    assert shim == oracle
    memberships = [f for f in shim[0] if f[0] == "NET-MEMBERSHIP"]
    if board_paths != {p for _, p in comps}:
        assert len(memberships) >= 1
        # The finding's paths field is the sorted symmetric difference.
        expected_diff = sorted({p for _, p in comps} ^ board_paths)
        assert tuple(expected_diff) in {f[4] for f in memberships}


# ---------------------------------------------------------------------------
# Metamorphic relations (R1d)
# ---------------------------------------------------------------------------


def test_mr1_ref_permutation_preserves_finding_kinds():
    """Renumbering refs uniformly on BOTH sides (same path->ref mapping
    change) preserves the finding kinds: a clean pair stays clean, and a
    pair with a MISSING stays MISSING (kinds are path-keyed, not refdes)."""
    clean_board = [("C1", "a.cap1"), ("C2", "b.cap2")]
    clean_nets = {"gnd": {"a.cap1", "b.cap2"}}
    clean_design = [("C1", "a.cap1"), ("C2", "b.cap2")]
    design_nets = {"gnd": [("C1", "1"), ("C2", "1")]}

    def kinds_for(comps, nets, dcomps, dnets):
        _, shim = _run_reconcile_both(comps, nets, dcomps, dnets)
        return {f[0] for f in shim[0]}, shim[0] == ()

    base = kinds_for(clean_board, clean_nets, clean_design, design_nets)
    # Same renumber applied to both sides: clean stays clean.
    renumbered = kinds_for(
        [("C9", "a.cap1"), ("C8", "b.cap2")],
        {"gnd": {"a.cap1", "b.cap2"}},
        [("C9", "a.cap1"), ("C8", "b.cap2")],
        {"gnd": [("C9", "1"), ("C8", "1")]},
    )
    assert base[1] is True and renumbered[1] is True


def test_mr2_adding_a_net_that_exists_on_both_sides_does_not_break_clean():
    """Adding the same net to both sides preserves a clean reconciliation."""
    clean_board = [("C1", "a.cap1")]
    clean_nets = {"gnd": {"a.cap1"}}
    clean_design = [("C1", "a.cap1")]
    design_nets = {"gnd": [("C1", "1")]}
    base = _run_reconcile_both(clean_board, clean_nets, clean_design, design_nets)
    grown = _run_reconcile_both(
        clean_board, {**clean_nets, "vcc": {"a.cap1"}}, clean_design,
        {**design_nets, "vcc": [("C1", "2")]},
    )
    assert base[1][0] == () and grown[1][0] == ()
    assert grown[1][5] == base[1][5] + 1  # board_nets grew by exactly one


def test_mr3_duplicate_refs_reported_in_first_seen_order():
    """The design-side duplicate_refs findings follow the parse order
    (first-seen path pair), and permuting the parse order permutes the
    reported pair — the order is deterministic, not hash-based."""
    text1 = (
        '(export (version "E")\n  (components\n'
        '    (comp (ref "R1") (sheetpath (names "/a.ato:Top::x.r1") (tstamps "0")))\n'
        '    (comp (ref "R1") (sheetpath (names "/a.ato:Top::y.r2") (tstamps "0")))\n'
        "  )\n  (nets\n    (net (code \"1\") (name \"gnd\") (node (ref \"R1\") (pin \"1\")))\n  )\n)\n"
    )
    # Reorder the two components.
    a = '    (comp (ref "R1") (sheetpath (names "/a.ato:Top::x.r1") (tstamps "0")))\n'
    b = '    (comp (ref "R1") (sheetpath (names "/a.ato:Top::y.r2") (tstamps "0")))\n'
    # The two comp blocks are adjacent lines; swap them in one replace.
    text3 = text1.replace(a + b, b + a)
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        # Distinct filenames: _write_netlist uses a fixed 'default.net'.
        p1 = Path(td) / "order1.net"
        p2 = Path(td) / "order2.net"
        p1.write_text(text1, encoding="utf-8")
        p2.write_text(text3, encoding="utf-8")
        d1 = shim_parse_design_netlist(p1)
        d2 = shim_parse_design_netlist(p2)
    # First-seen path differs when the comp order swaps.
    assert d1.duplicate_refs == [("R1", "x.r1", "y.r2")]
    assert d2.duplicate_refs == [("R1", "y.r2", "x.r1")]

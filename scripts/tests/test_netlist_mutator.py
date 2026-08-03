"""Tests for scripts/netlist_mutator.py (plan 2026-08-02-021, R39 / U5).

Verifies the deterministic seeded mutation harness: the renumber mutation
permutes refs within one prefix and preserves the refdes set exactly, the
dropped-net mutation removes exactly one net's nodes and changes no other
net, the reused-refdes mutation makes exactly two components share one ref,
two runs with the same seed produce identical mutations, and each mutation on
the current netlist produces a parseable mutated netlist.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_domain_partition import parse_netlist as strict_parse  # noqa: E402
from netlist_mutator import (  # noqa: E402
    MutatorError,
    load_netlist,
    mutate_drop_net,
    mutate_renumber,
    mutate_reuse_refdes,
    pick_droppable_net,
    write_netlist,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_NETLIST = REPO_ROOT / "elec" / "build" / "default.net"

#: A small synthetic netlist exercising three C-prefix components, two
#: R-prefix components and one U-prefix component.
SYNTHETIC = """(export (version "E")
  (components
    (comp (ref "C1") (value "?") (footprint "?")
      (sheetpath (names "/x/main.ato:Top::a.cap1") (tstamps "0")))
    (comp (ref "C2") (value "?") (footprint "?")
      (sheetpath (names "/x/main.ato:Top::b.cap2") (tstamps "0")))
    (comp (ref "C3") (value "?") (footprint "?")
      (sheetpath (names "/x/main.ato:Top::c.cap3") (tstamps "0")))
    (comp (ref "R1") (value "?") (footprint "?")
      (sheetpath (names "/x/main.ato:Top::d.r1") (tstamps "0")))
    (comp (ref "R2") (value "?") (footprint "?")
      (sheetpath (names "/x/main.ato:Top::e.r2") (tstamps "0")))
    (comp (ref "U1") (value "?") (footprint "?")
      (sheetpath (names "/x/main.ato:Top::f.u1") (tstamps "0")))
  )
  (nets
    (net (code "1") (name "gnd")
      (node (ref "C1") (pin "1")) (node (ref "C2") (pin "1")) (node (ref "C3") (pin "1")))
    (net (code "2") (name "vcc")
      (node (ref "C1") (pin "2")) (node (ref "C2") (pin "2")) (node (ref "C3") (pin "2")))
    (net (code "3") (name "sig")
      (node (ref "R1") (pin "1")) (node (ref "R2") (pin "1")) (node (ref "U1") (pin "1")))
  )
)
"""


@pytest.fixture
def synthetic(tmp_path: Path):
    path = tmp_path / "default.net"
    path.write_text(SYNTHETIC)
    return load_netlist(path)


def _ref_counts(mutated) -> Counter:
    return Counter(c.ref for c in mutated.components)


# ---------------------------------------------------------------------------
# Renumber
# ---------------------------------------------------------------------------


def test_renumber_permutes_within_one_prefix_and_preserves_ref_set(synthetic) -> None:
    mutated, summary = mutate_renumber(synthetic, 7)
    assert summary["mutation"] == "renumber"
    assert summary["prefix"] == "C"  # most populated prefix
    assert summary["ref_set_preserved"] is True
    assert _ref_counts(mutated) == _ref_counts(synthetic)
    # Every C-prefix component still has a C ref; every path kept its path.
    for comp in mutated.components:
        if comp.instance_path in {"a.cap1", "b.cap2", "c.cap3"}:
            assert comp.ref.startswith("C")
    # At least one ref actually moved (a permutation that changes nothing is
    # not a renumber).
    assert len(summary["renumbered_paths"]) >= 1
    # Net nodes follow the permutation: a.cap1's pin 1 still lands on gnd.
    gnd_nodes = {ref for ref, _pin in mutated.net_by_name("gnd").nodes}
    assert len(gnd_nodes) == 3


def test_renumber_is_minimal_non_prefix_refs_untouched(synthetic) -> None:
    mutated, _summary = mutate_renumber(synthetic, 7)
    for comp in mutated.components:
        if comp.instance_path in {"d.r1", "e.r2", "f.u1"}:
            assert comp.ref in {"R1", "R2", "U1"}


# ---------------------------------------------------------------------------
# Drop-net
# ---------------------------------------------------------------------------


def test_drop_net_removes_exactly_one_nets_nodes(synthetic) -> None:
    mutated, summary = mutate_drop_net(synthetic, "gnd")
    assert summary["net"] == "gnd"
    assert summary["dropped_nodes"] == 3
    assert mutated.net_by_name("gnd").nodes == []
    for name in ("vcc", "sig"):
        assert len(mutated.net_by_name(name).nodes) == 3
    assert [c.instance_path for c in mutated.components] == [
        c.instance_path for c in synthetic.components
    ]


def test_drop_net_unknown_net_fails_closed(synthetic) -> None:
    with pytest.raises(MutatorError, match="no net named"):
        mutate_drop_net(synthetic, "does-not-exist")


def test_pick_droppable_net_is_deterministic(synthetic) -> None:
    assert pick_droppable_net(synthetic, 3) == pick_droppable_net(synthetic, 3)
    assert pick_droppable_net(synthetic, 3) in {"gnd", "vcc", "sig"}


# ---------------------------------------------------------------------------
# Reuse
# ---------------------------------------------------------------------------


def test_reuse_makes_exactly_two_components_share_one_ref(synthetic) -> None:
    mutated, summary = mutate_reuse_refdes(synthetic, 11)
    assert summary["mutation"] == "reuse"
    counts = _ref_counts(mutated)
    shared = [ref for ref, n in counts.items() if n > 1]
    assert len(shared) == 1
    assert shared[0] == summary["ref"]
    assert len(mutated.components) == len(synthetic.components)  # no add/remove
    # The duplicated ref's two paths are the ones the summary names.
    dup_ref = summary["ref"]
    dup_paths = [c.instance_path for c in mutated.components if c.ref == dup_ref]
    assert sorted(dup_paths) == sorted(summary["paths"])


# ---------------------------------------------------------------------------
# Determinism and parseability
# ---------------------------------------------------------------------------


def test_same_seed_produces_identical_mutations(tmp_path: Path, synthetic) -> None:
    out1 = tmp_path / "a.net"
    out2 = tmp_path / "b.net"
    m1, _s1 = mutate_renumber(synthetic, 7)
    m2, _s2 = mutate_renumber(synthetic, 7)
    write_netlist(m1, out1)
    write_netlist(m2, out2)
    assert out1.read_bytes() == out2.read_bytes()


def test_each_mutation_on_current_netlist_is_parseable(tmp_path: Path) -> None:
    """U5 test scenario 5: each mutation on the current netlist produces a
    parseable mutated netlist -- strictly for renumber/drop-net, and through
    the reconciliation's duplicate-ref-tolerant parser for reuse."""
    if not REAL_NETLIST.is_file():
        pytest.skip("compiled netlist not built (run `make netlist`)")
    from temper_placer.validation.netlist_reconciliation import parse_design_netlist

    orig = load_netlist(REAL_NETLIST)
    out = tmp_path / "mutated.net"

    m, _s = mutate_renumber(orig, 7)
    write_netlist(m, out)
    strict_parse(out)  # strict parser must accept a renumbered netlist
    parse_design_netlist(out)

    net_name = pick_droppable_net(orig, 3)
    m2, _s2 = mutate_drop_net(orig, net_name)
    write_netlist(m2, out)
    strict_parse(out)
    parse_design_netlist(out)

    m3, _s3 = mutate_reuse_refdes(orig, 11)
    write_netlist(m3, out)
    # Strict parser rejects the duplicate ref (expected -- that is why the
    # reconciliation has its own tolerant parser), the oracle's parser must
    # accept it so the REUSE finding can fire.
    with pytest.raises(Exception, match="duplicate component ref"):
        strict_parse(out)
    design = parse_design_netlist(out)
    assert len(design.duplicate_refs) == 1


def test_load_netlist_rejects_missing_file(tmp_path: Path) -> None:
    from check_domain_partition import GateError

    with pytest.raises(GateError, match="not found"):
        load_netlist(tmp_path / "missing.net")

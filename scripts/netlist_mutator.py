#!/usr/bin/env python3
"""Deterministic seeded mutation harness for the compiled design netlist
(plan 2026-08-02-021, R39 / U5).

Mutates a COPY of ``elec/build/default.net`` with one named, seeded mutation
per class, so the identity checks and the netlist<->board reconciliation
oracle can be proven against the classes they exist for:

  - ``renumber``     -- a set-preserving permutation of refs within one
                        ref-designator prefix (the wholesale-renumber class,
                        which ``preflight_identity``'s 95% refdes-overlap
                        check passes by construction because the refdes SET
                        never changes).
  - ``drop-net``     -- a net's nodes are removed from the design netlist
                        (the dropped-net class; the net stays declared but
                        empty, which is what the net-level membership
                        reconciliation reports as NET-MEMBERSHIP).
  - ``reuse``        -- one ref is assigned to two components (the reused-
                        refdes class; the strict netlist parsers reject the
                        result outright, which is exactly why the
                        reconciliation oracle's own parser tolerates
                        duplicate refs and reports a REUSE finding).

The mutations operate on a run-time copy: ``elec/build/default.net`` and
``elec/src`` are never edited. Each mutation is minimal (only the named
transformation), named, and reproducible from its seed (two runs with the
same seed produce identical output).

Parsing uses ``check_domain_partition.parse_netlist`` -- the same parser and
the same freshness-gated authority the identity and domain gates read, so
there is no third netlist opinion. The mutated output is re-serialised in
the KiCad-export ``.net`` sexp format the parser accepts, so every mutation
produces a parseable mutated netlist.

Usage:
  uv run python scripts/netlist_mutator.py --netlist elec/build/default.net \
      --mutate renumber --seed 7 --out /tmp/renumbered.net
  uv run python scripts/netlist_mutator.py --netlist elec/build/default.net \
      --mutate drop-net --seed 3 --net-name gnd --out /tmp/dropped.net
  uv run python scripts/netlist_mutator.py --netlist elec/build/default.net \
      --mutate reuse --seed 11 --out /tmp/reused.net
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_domain_partition import Netlist as StrictNetlist  # noqa: E402
from check_domain_partition import parse_netlist  # noqa: E402

_REF_PREFIX_RE = re.compile(r"^([A-Za-z]+)")


class MutatorError(RuntimeError):
    """Raised for a mutation that cannot be applied to the given netlist
    (e.g. no net with >= 2 nodes to drop, fewer than 2 components to swap).
    Fail-closed: never silently no-ops into an unmutated output."""


@dataclass(frozen=True)
class MutatedComponent:
    ref: str
    instance_path: str


@dataclass(frozen=True)
class MutatedNet:
    code: str
    name: str
    nodes: list[tuple[str, str]]  # (ref, pin)


@dataclass
class MutatedNetlist:
    """The mutation harness's comparison shape.

    Deliberately allows duplicate component refs (the reuse mutation produces
    them) -- unlike the strict ``check_domain_partition`` shape -- and keeps
    nets as (code, name, nodes) triples so a dropped net stays declared with
    an empty node list.
    """

    components: list[MutatedComponent]
    nets: list[MutatedNet]

    def component_paths(self) -> list[str]:
        return sorted(c.instance_path for c in self.components)

    def net_by_name(self, name: str) -> MutatedNet | None:
        for net in self.nets:
            if net.name == name:
                return net
        return None


MUTATIONS = ("renumber", "drop-net", "reuse")


# ---------------------------------------------------------------------------
# Load / serialize
# ---------------------------------------------------------------------------


def load_netlist(path: Path | str) -> MutatedNetlist:
    """Parse ``elec/build/default.net`` with ``check_domain_partition``'s
    parser (the canonical authority) and convert to the mutation shape."""
    strict: StrictNetlist = parse_netlist(Path(path))
    components = [
        MutatedComponent(ref=comp.ref, instance_path=comp.instance_path)
        for comp in strict.components.values()
    ]
    nets = [
        MutatedNet(code=code, name=name, nodes=list(nodes))
        for code, name in sorted(strict.nets.items(), key=lambda kv: kv[0])
        for nodes in [strict.net_nodes[code]]
    ]
    return MutatedNetlist(components=components, nets=nets)


def write_netlist(mutated: MutatedNetlist, path: Path | str) -> None:
    """Serialise the mutated netlist in the KiCad-export ``.net`` sexp format
    ``check_domain_partition.parse_netlist`` / the reconciliation parser
    accept. The sheetpath ``names`` field is reconstructed as a synthetic
    path ending in the instance path after ``::`` -- the only part either
    parser reads -- so the re-parsed instance paths are identical to the
    mutated ones."""
    comp_blocks = []
    for comp in sorted(mutated.components, key=lambda c: c.instance_path):
        comp_blocks.append(
            f'    (comp (ref "{comp.ref}")\n'
            f'      (value "?")\n'
            f'      (footprint "?")\n'
            f'      (sheetpath (names "/mutated/elec/src/main.ato:Top::{comp.instance_path}") '
            f'(tstamps "00000000000000000000000000000000"))\n'
            f'      (tstamps "00000000000000000000000000000000"))'
        )
    net_blocks = []
    for net in mutated.nets:
        node_blocks = "".join(
            f'\n        (node (ref "{ref}") (pin "{pin}"))' for ref, pin in net.nodes
        )
        net_blocks.append(
            f'    (net (code "{net.code}") (name "{net.name}"){node_blocks})'
        )
    Path(path).write_text(
        "(export (version \"E\")\n"
        "  (components\n"
        + "\n".join(comp_blocks)
        + "\n  )\n"
        "  (nets\n"
        + "\n".join(net_blocks)
        + "\n  )\n"
        ")\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


def _discover_prefixes(mutated: MutatedNetlist) -> dict[str, list[MutatedComponent]]:
    prefixes: dict[str, list[MutatedComponent]] = {}
    for comp in mutated.components:
        match = _REF_PREFIX_RE.match(comp.ref)
        prefix = match.group(1) if match else ""
        prefixes.setdefault(prefix, []).append(comp)
    return prefixes


def pick_renumber_prefix(mutated: MutatedNetlist) -> str:
    """Deterministically pick the ref prefix to renumber: the most populated
    prefix with >= 2 members (ties broken lexicographically). Never order-
    dependent on set iteration."""
    prefixes = _discover_prefixes(mutated)
    eligible = [
        (len(comps), prefix)
        for prefix, comps in prefixes.items()
        if prefix and len(comps) >= 2
    ]
    if not eligible:
        raise MutatorError(
            f"cannot renumber: no ref prefix has >= 2 components "
            f"({len(mutated.components)} component(s) total)"
        )
    return max(eligible)[1]


def pick_droppable_net(mutated: MutatedNetlist, seed: int) -> str:
    """Deterministically pick a net to drop: among nets with >= 2 nodes,
    ``sorted(net_names)[seed % len]``. Fails closed if no such net exists."""
    candidates = sorted(
        net.name for net in mutated.nets if len(net.nodes) >= 2
    )
    if not candidates:
        raise MutatorError(
            f"cannot drop a net: no net has >= 2 nodes "
            f"({len(mutated.nets)} net(s) total)"
        )
    return candidates[seed % len(candidates)]


def mutate_renumber(mutated: MutatedNetlist, seed: int) -> tuple[MutatedNetlist, dict]:
    """Set-preserving ref permutation within one prefix (the wholesale
    renumber class). Every component of the chosen prefix keeps the same
    suffix SET, so the refdes set is exactly preserved -- the property that
    makes refdes-overlap checks structurally blind to this class."""
    prefix = pick_renumber_prefix(mutated)
    prefix_comps = [
        comp for comp in mutated.components if comp.ref.startswith(prefix)
        and _REF_PREFIX_RE.match(comp.ref).group(1) == prefix
    ]

    ref_to_path = {comp.ref: comp.instance_path for comp in mutated.components}
    if len(ref_to_path) != len(mutated.components):
        raise MutatorError("cannot renumber a netlist that already has duplicate refs")

    suffixes = sorted(comp.ref[len(prefix):] for comp in prefix_comps)
    rng = random.Random(seed)
    new_suffixes = list(suffixes)
    rng.shuffle(new_suffixes)
    # A permutation that changes nothing is not a renumber -- resample until
    # at least one component actually changes ref.
    guard = 0
    while new_suffixes == suffixes and guard < 100:
        rng.shuffle(new_suffixes)
        guard += 1
    if new_suffixes == suffixes:
        raise MutatorError(f"seed {seed} produced an identity permutation for prefix {prefix!r}")

    path_to_new_ref = {
        ref_to_path[prefix + old]: prefix + new
        for old, new in zip(suffixes, new_suffixes, strict=True)
    }
    path_to_old_ref = {comp.instance_path: comp.ref for comp in mutated.components}
    renumbered_paths = sorted(
        path
        for path, new_ref in path_to_new_ref.items()
        if new_ref != path_to_old_ref[path]
    )

    new_components = [
        MutatedComponent(
            ref=path_to_new_ref.get(comp.instance_path, comp.ref),
            instance_path=comp.instance_path,
        )
        for comp in mutated.components
    ]
    new_nets = []
    for net in mutated.nets:
        new_nodes = []
        for ref, pin in net.nodes:
            path = _path_of(ref_to_path, ref, net)
            new_nodes.append((path_to_new_ref.get(path, ref), pin))
        new_nets.append(
            MutatedNet(code=net.code, name=net.name, nodes=new_nodes)
        )

    summary = {
        "mutation": "renumber",
        "seed": seed,
        "prefix": prefix,
        "renumbered_paths": renumbered_paths,
        "ref_set_preserved": sorted(c.ref for c in new_components)
        == sorted(c.ref for c in mutated.components),
    }
    return MutatedNetlist(components=new_components, nets=new_nets), summary


def _path_of(ref_to_path: dict[str, str], ref: str, _net: MutatedNet) -> str:
    """Resolve a net node's ref to its instance path. The unmutated netlist
    has unique refs, so this is a bijection; a missing ref is malformed input
    and must fail closed rather than silently renumbering a phantom node."""
    try:
        return ref_to_path[ref]
    except KeyError:
        raise MutatorError(
            f"net node references ref {ref!r} with no component -- malformed "
            "netlist, refusing to renumber"
        ) from None


def mutate_drop_net(mutated: MutatedNetlist, net_name: str) -> tuple[MutatedNetlist, dict]:
    """Remove a net's nodes from the design netlist (the dropped-net class).
    The net stays declared with zero nodes -- the signature the net-level
    membership reconciliation reports as NET-MEMBERSHIP against the intact
    board side. Exactly one net changes; every other net is untouched."""
    target = mutated.net_by_name(net_name)
    if target is None:
        raise MutatorError(f"no net named {net_name!r} in the netlist")
    dropped_nodes = len(target.nodes)
    new_nets = [
        MutatedNet(code=net.code, name=net.name, nodes=[] if net is target else list(net.nodes))
        for net in mutated.nets
    ]
    summary = {
        "mutation": "drop-net",
        "seed": None,
        "net": net_name,
        "dropped_nodes": dropped_nodes,
    }
    return MutatedNetlist(components=list(mutated.components), nets=new_nets), summary


def mutate_reuse_refdes(mutated: MutatedNetlist, seed: int) -> tuple[MutatedNetlist, dict]:
    """Assign one ref to two components (the reused-refdes class). The
    duplicated ref is chosen deterministically; the second component's
    original ref disappears from the ref set (two components cannot both keep
    distinct refs and share one)."""
    if len(mutated.components) < 2:
        raise MutatorError("cannot reuse a ref: fewer than 2 components")
    rng = random.Random(seed)
    # Deterministic path ordering, then seeded pick.
    ordered = sorted(mutated.components, key=lambda c: c.instance_path)
    idx_a, idx_b = rng.sample(range(len(ordered)), 2)
    comp_a, comp_b = ordered[idx_a], ordered[idx_b]
    if comp_a.ref == comp_b.ref:
        raise MutatorError(
            f"cannot reuse ref {comp_a.ref!r}: both chosen components already "
            "share it"
        )
    new_components = []
    for comp in mutated.components:
        if comp is comp_b:
            new_components.append(MutatedComponent(ref=comp_a.ref, instance_path=comp.instance_path))
        else:
            new_components.append(comp)
    summary = {
        "mutation": "reuse",
        "seed": seed,
        "ref": comp_a.ref,
        "paths": [comp_a.instance_path, comp_b.instance_path],
    }
    return MutatedNetlist(components=new_components, nets=list(mutated.nets)), summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--netlist", type=Path, default=Path("elec/build/default.net"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--mutate",
        choices=MUTATIONS,
        required=True,
        help="Mutation class to apply (renumber | drop-net | reuse).",
    )
    parser.add_argument("--seed", type=int, default=0, help="Deterministic seed.")
    parser.add_argument(
        "--net-name",
        help="Net to drop for --mutate drop-net (default: seeded pick).",
    )
    args = parser.parse_args()

    mutated = load_netlist(args.netlist)
    if args.mutate == "renumber":
        mutated, summary = mutate_renumber(mutated, args.seed)
    elif args.mutate == "drop-net":
        net_name = args.net_name or pick_droppable_net(mutated, args.seed)
        mutated, summary = mutate_drop_net(mutated, net_name)
    elif args.mutate == "reuse":
        mutated, summary = mutate_reuse_refdes(mutated, args.seed)
    else:  # pragma: no cover -- argparse choices prevent this
        raise AssertionError(f"unknown mutation {args.mutate!r}")
    write_netlist(mutated, args.out)
    print(f"Wrote {args.out} ({len(mutated.components)} components, {len(mutated.nets)} nets)")
    for key, value in sorted(summary.items()):
        print(f"  {key}: {value}")


if __name__ == "__main__":
    sys.exit(main())

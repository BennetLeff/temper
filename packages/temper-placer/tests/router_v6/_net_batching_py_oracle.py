"""Verbatim pre-migration oracle for the Phase E batch E5 net-batching Rust
orchestration (Rust Orchestration Engine plan 2026-08-09-001, Phase E E5).

This file is a byte-exact snapshot of the PORTABLE batch-loop orchestration
bodies of ``router_v6/net_batching.py`` AS COMMITTED at the dispatch base
(origin/main cfc9415c1), extracted verbatim:

- ``order_nets_for_batching`` (the net grouping: hub-flag / pin-count / name
  total order plus the diff-pair adjacency post-pass) and its helpers
  ``_extract_ref_to_block`` / ``_net_touches_hub`` / ``HUB_BLOCKS`` /
  ``DEFAULT_BATCH_SIZE`` and the three ``_*_RE`` regex constants.
- ``_chunks`` (batch construction: the ``range(0, len, max(1, size))``
  slice generator).
- ``_shrink_channel_widths`` (budget accounting: reducing each channel
  edge's remaining capacity by what earlier batches already consumed).
- ``_consume_capacity`` (budget accounting: subtracting each
  successfully-routed net's ``trace_width_mm + clearance_mm`` from the
  capacity of every channel edge it used).

The batch-loop pieces that stay Python are NOT extracted: the subprocess
driver (``_run_target_in_subprocess`` / ``_batch_worker_entry`` /
``_write_shared_context`` / ``_watch_peak_rss_kb`` / ``_run_subset_subprocess``),
the solve dispatch (``_solve_subset`` -> ``ModelBuilder`` +
``solve_topology_rust``), ``run_net_batched_stage3`` itself, and the
evidence records (``NetBatchResult`` / trace).  ``_extract_ref_to_block``
and ``_net_touches_hub`` stay Python in the shim but are reproduced here
verbatim because ``order_nets_for_batching`` (the differential surface)
calls them.  See the shim header for the E5 boundary argument.

The ``temper_placer`` imports below resolve to the pinned pre-E5 modules
(the pieces E5 did NOT migrate).  Do NOT edit: it is the reference.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from temper_placer.core.netlist import Net
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.diff_pair_inference import DiffPair, infer_differential_pairs
from temper_placer.router_v6.topology_extraction import NetTopology

#: Blocks whose atopile ``Sheetpath`` prefix identifies them as high
#: boundary-net-count "hub" blocks on ``pcb/temper.kicad_pcb``.
#:
#: MEASURED this task (script: scratchpad ``block_analysis.py``, direct
#: regex extraction of each footprint's ``(property "Sheetpath" ...)`` from
#: ``pcb/temper.kicad_pcb``, cross-tabulated against which nets connect
#: components in more than one top-level block): ``mcu`` has 20
#: boundary-crossing nets and ``safety`` has 13 — both far above the next
#: block (9, ``rtd_pan``). This corroborates (does not byte-for-byte
#: reproduce — different counting methodology, not re-derived here) the
#: task brief's cited "18 and 11 boundary nets" for the same two blocks.
#: Every other block (``discharge`` 6, ``power_in`` 8, ``hb`` 8,
#: ``power_mgmt`` 3, ``ct_sense`` 5, ``aux_supply`` 4, ``tank`` 2,
#: ``thermal`` 2) is a clear second tier.
HUB_BLOCKS: frozenset[str] = frozenset({"mcu", "safety"})

#: Default batch size. The reduction survey's own arithmetic
#: (docs/evidence/2026-08-07-sat-model-reduction-options.md S2): peak raw
#: vars per batch ~= B * 204,490 channel edges; B=10 estimates ~2.04M
#: vars, corroborated by an existing MEASURED data point (a 2.6M-variable
#: model already survived construction under the same 8GB ulimit -v cap).
DEFAULT_BATCH_SIZE = 10

_FOOTPRINT_START_RE = re.compile(r'\n\s*\(footprint\s+"')
_SHEETPATH_RE = re.compile(r'\(property\s+"Sheetpath"\s+"([^"]*)"')
_REFERENCE_RE = re.compile(r'\(property\s+"Reference"\s+"([^"]*)"')


def _extract_ref_to_block(pcb_source_path: Path | str) -> dict[str, str]:
    """Map component ref -> top-level atopile block name.

    Re-reads the raw ``.kicad_pcb`` text for each footprint's
    ``Sheetpath`` property (e.g. ``"mcu.mcu"`` -> block ``"mcu"``).  This
    information does not survive into the parsed ``ParsedPCB``/``Net``
    dataclasses (checked this task: no ``sheetpath``/``hierarchy`` field
    exists on either), so it is re-derived directly from the board file,
    the same raw-text-regex technique ``_apply_placements_to_pcb`` already
    uses elsewhere in this codebase for other footprint-level properties.
    """
    text = Path(pcb_source_path).read_text(encoding="utf-8")
    starts = [m.start() for m in _FOOTPRINT_START_RE.finditer(text)]
    starts.append(len(text))
    ref_to_block: dict[str, str] = {}
    for i in range(len(starts) - 1):
        block_text = text[starts[i] : starts[i + 1]]
        sp_match = _SHEETPATH_RE.search(block_text)
        ref_match = _REFERENCE_RE.search(block_text)
        if not sp_match or not ref_match:
            continue
        sheetpath = sp_match.group(1)
        top_block = sheetpath.split(".")[0] if "." in sheetpath else sheetpath
        ref_to_block[ref_match.group(1)] = top_block
    return ref_to_block


def _net_touches_hub(net: Net, ref_to_block: dict[str, str], hub_blocks: frozenset[str]) -> bool:
    for comp_ref, _pin_name in getattr(net, "pins", None) or ():
        if ref_to_block.get(comp_ref) in hub_blocks:
            return True
    return False


def order_nets_for_batching(
    nets: Sequence[Net],
    pcb_source_path: Path | str | None,
    *,
    hub_blocks: frozenset[str] = HUB_BLOCKS,
) -> list[int]:
    """Return net indices in batching order: low-fan-out-first, hubs last.

    Primary key: whether the net touches a hub block (``mcu`` or
    ``safety`` — see :data:`HUB_BLOCKS`). Non-hub nets sort first, hub
    nets sort last, matching the task brief's "low-fan-out-first with hubs
    last" guidance (mcu/safety are the two blocks with dramatically higher
    boundary-net counts than any other block on this board, so routing
    them last defers the SAT model's hardest, most cross-cutting
    congestion to the end, after channel capacity for everything else is
    already committed and easy to reason about).

    Secondary key: ascending pin count ("low fan-out first") — the same
    convention ``_select_sat_nets`` already uses elsewhere in this
    codebase for selective SAT routing (top-N nets by ascending pin
    count). Fewer pins means a smaller, easier-to-satisfy per-net
    footprint, so routing those first fills in the "easy" capacity
    consumption before anything contentious.

    Tertiary key: net name, for full determinism.

    A post-pass moves each differential pair's second net to immediately
    follow its partner in the resulting order, so same-batch placement is
    likely (though not strictly guaranteed at a batch boundary) --
    ``ModelBuilder._create_diff_pair_constraints`` silently drops a pair
    that spans two batches (looks up both members in the *same* model's
    ``net_to_idx``; a batch-local model simply never sees the missing
    member), so keeping pairs adjacent is what makes the per-batch model
    actually enforce the pair's coupled-routing constraint instead of
    silently not applying it.
    """
    ref_to_block = _extract_ref_to_block(pcb_source_path) if pcb_source_path else {}

    def sort_key(i: int) -> tuple[bool, int, str]:
        net = nets[i]
        touches_hub = _net_touches_hub(net, ref_to_block, hub_blocks)
        pin_count = len(getattr(net, "pins", None) or ())
        return (touches_hub, pin_count, net.name)

    order = sorted(range(len(nets)), key=sort_key)

    name_to_idx = {net.name: i for i, net in enumerate(nets)}
    diff_pairs = infer_differential_pairs([n.name for n in nets])
    for pair in diff_pairs:
        p_i = name_to_idx.get(pair.p_net)
        n_i = name_to_idx.get(pair.n_net)
        if p_i is None or n_i is None or p_i == n_i:
            continue
        try:
            order.remove(n_i)
        except ValueError:
            continue
        insert_at = order.index(p_i) + 1
        order.insert(insert_at, n_i)

    return order


def _chunks(seq: Sequence[int], size: int) -> Iterable[list[int]]:
    for i in range(0, len(seq), max(1, size)):
        yield list(seq[i : i + size])


def _shrink_channel_widths(
    channel_widths: dict[str, ChannelWidths],
    consumed: dict[str, float],
    edge_lookup: dict[str, tuple[str, tuple[float, float], tuple[float, float]]],
) -> dict[str, ChannelWidths]:
    """Return a copy of *channel_widths* with each consumed edge's
    capacity reduced by the width already committed to it by earlier
    batches (floored at 0 -- a fully consumed edge simply admits no more
    nets, rather than producing a negative/contradictory AtMostK bound).

    This is the batching-specific mechanism that makes the shared,
    physical "how much copper can this channel carry" resource — the one
    thing ``constraint_model.py`` actually encodes as a cross-net SAT
    constraint — hold across batch boundaries and not just within one
    batch's model.
    """
    if not consumed:
        return channel_widths

    deltas_by_layer: dict[str, dict[tuple[float, float], tuple[float, float]] | Any] = {}
    for edge_id, amount in consumed.items():
        if amount <= 0:
            continue
        loc = edge_lookup.get(edge_id)
        if loc is None:
            continue
        layer_name, u, v = loc
        deltas_by_layer.setdefault(layer_name, {})[(u, v)] = (
            deltas_by_layer.setdefault(layer_name, {}).get((u, v), 0.0) + amount
        )

    new_widths = dict(channel_widths)
    for layer_name, deltas in deltas_by_layer.items():
        widths = channel_widths.get(layer_name)
        if widths is None:
            continue
        new_edge_widths = dict(widths.edge_widths)
        for (u, v), amount in deltas.items():
            key = None
            if (u, v) in new_edge_widths:
                key = (u, v)
            elif (v, u) in new_edge_widths:
                key = (v, u)
            if key is None:
                continue
            new_edge_widths[key] = max(0.0, new_edge_widths[key] - amount)
        new_widths[layer_name] = replace(widths, edge_widths=new_edge_widths)
    return new_widths


def _consume_capacity(
    consumed: dict[str, float],
    topo_by_net: dict[str, NetTopology],
    nets_subset: Sequence[Net],
    design_rules: Any,
) -> None:
    if design_rules is None:
        return
    name_to_net = {n.name: n for n in nets_subset}
    for net_name, ntopo in topo_by_net.items():
        net = name_to_net.get(net_name)
        if net is None:
            continue
        rule = design_rules.get_rules_for_net(net.name)
        net_width = rule.trace_width_mm + rule.clearance_mm
        for edge_id in ntopo.uses_channels:
            consumed[edge_id] = consumed.get(edge_id, 0.0) + net_width

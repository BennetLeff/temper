# mypy: ignore-errors
"""
Router V6: Net ordering for A* pathfinding.

Part of temper-N6 decomposition — split from astar_pathfinding.py.
"""

from __future__ import annotations

import os

from temper_placer.router_v6.channel_mapping import ChannelMapping

# EXPERIMENT (2026-08-18): net-ordering mode selector.
#
# The production order is "smallest-footprint first" (see the docstring
# below): within a conflict cluster nets sort by (bottleneck_asc, area_asc,
# not_is_power), so the WIDE HV nets -- which owe 12.6mm HV<->SELV creepage
# and carry 3-5mm trace widths -- route AFTER the narrow SELV signals have
# already claimed the corridors. Whether that is the reason nine nets never
# close had never been measured, because no lever existed to change it.
#
# This selector is the lever. ``TEMPER_NET_ORDER_MODE`` is read once per
# call and defaults to ``"baseline"``, which takes the identical code path
# the module has always taken -- same keys, same comparisons, same result.
# The alternative modes are measurement instruments, not a new default:
# nothing in this repository sets the variable, so the shipped behaviour is
# unchanged unless an experiment sets it explicitly.
#
#   baseline    production order (smallest-footprint-first). Default.
#   hv_first    HV/ACMains nets sort ahead of everything else, both within
#               each conflict cluster and by promoting HV-bearing clusters
#               to the front. Inside each group the production key still
#               applies, so this changes only the HV-vs-SELV relative order.
#   width_desc  strict widest-trace-first over the whole net list, with the
#               production key as tiebreak. Ignores clustering entirely --
#               the most aggressive form of "wide copper lands first".
_ORDER_MODES = ("baseline", "hv_first", "width_desc")


def _order_mode() -> str:
    """The ordering mode for this call.

    Unset/empty -> ``"baseline"``. An unrecognised value is a hard error
    rather than a silent fallback to production order: an experiment that
    typoed its mode would otherwise report the baseline's numbers as the
    treatment's, which is the specific way a measurement lies.
    """
    mode = os.environ.get("TEMPER_NET_ORDER_MODE", "").strip() or "baseline"
    if mode not in _ORDER_MODES:
        raise ValueError(
            f"TEMPER_NET_ORDER_MODE={mode!r} is not one of {_ORDER_MODES}"
        )
    return mode


def _net_trace_width_mm(net_name: str, design_rules=None) -> float:
    """SSOT trace width for *net_name*, or 0.0 when it has no real class.

    Used only by the ``width_desc`` experiment mode. Resolved through the
    netclass SSOT (``_netclass_trace_width`` against the board's OWN
    ``design_rules``) rather than a name-keyword table, so the width used
    for ordering is the same width the router will actually stamp.

    A default-constructed ``DesignRules()`` carries no
    ``net_class_assignments`` and resolves EVERY net to 0.0 -- measured
    before this parameter existed -- which would have made ``width_desc``
    a silent no-op that reported itself as a real ordering. The rules must
    be threaded in from the call site.
    """
    from temper_placer.router_v6.trace_width_assignment import _netclass_trace_width

    tw = _netclass_trace_width(design_rules, net_name)
    return float(tw.width_mm) if tw is not None else 0.0


# Netclass names the SSOT treats as mains-referenced / high-voltage copper.
_HV_CLASS_NAMES = frozenset({"HighVoltage", "ACMains"})


def _is_hv_like(net_name: str, design_rules=None) -> bool:
    """True for nets that carry HV/ACMains copper.

    Deliberately the UNION of two sources, because neither alone covers the
    nine nets under investigation:

    * ``net_classification.is_hv_net`` -- the router's own name classifier,
      the same predicate ``_net_policy._should_route`` consults. Measured
      against the nine target nets it returns True for only ``SW_NODE`` and
      ``ac_n``; ``+170V_BUS``, ``DC_BUS_RTN`` and ``PWR_RTN`` are all False.
      That is the name-classifier gap ``_net_policy``'s own docstring
      records at SS1.4.
    * the netclass SSOT assignment -- ``design_rules.get_rules_for_net``
      resolving to ``HighVoltage``/``ACMains``.

    Taking the union means ``hv_first`` promotes the copper that is
    ACTUALLY high-voltage, not merely the copper whose name happens to look
    it. Using ``is_hv_net`` alone would have left the widest nets on the
    board -- the +170V bus and its return -- sorting as ordinary signals,
    and the experiment would have measured almost nothing.
    """
    from temper_placer.router_v6.net_classification import is_hv_net

    if is_hv_net(net_name):
        return True
    if design_rules is None:
        return False
    get_rules = getattr(design_rules, "get_rules_for_net", None)
    if get_rules is None:
        return False
    rules = get_rules(net_name)
    return getattr(rules, "name", None) in _HV_CLASS_NAMES


def _compute_net_order(
    channel_mapping: ChannelMapping,
    bottleneck_widths: dict[str, float] | None = None,
    design_rules=None,
) -> list[str]:
    """
    Compute routing order for nets using spatial conflict awareness.

    Algorithm:
      1. Compute bounding boxes for each net from its waypoints.
      2. Build a conflict graph: two nets conflict if their bounding boxes
         overlap sufficiently (overlap / smaller_area > 0.1).
      3. Find connected components (clusters of mutually-overlapping nets).
      4. Within each cluster, sort by (bottleneck_asc, area_asc, not_is_power)
         when bottleneck_widths is provided; otherwise (area_asc, not_is_power).
         Smallest-footprint nets route first so they claim narrow corridors
         before larger nets spread through the region.  Power nets are a
         tiebreaker, not a primary sort key -- per the Bottleneck Lemma,
         routing a small net before a large net never makes the large net
         unroutable.
      5. Route isolated clusters first, then largest clusters.

    Rationale:
      The rip-up cascade occurs when a large-footprint net consumes
      space that a small-footprint net later needs.  Routing small nets
      first ensures they claim their narrow corridors before larger nets
      spread through the region.  Adding bottleneck widths gives priority
      to nets with the narrowest routing corridors — they have fewer
      routing options and must be routed before competitors claim their
      only viable path.

    Args:
        channel_mapping: Channel mapping with waypoints per net.
        bottleneck_widths: Optional dict mapping net_name to bottleneck
            width in mm.  When provided, nets with narrower bottlenecks
            route earlier within their cluster.

    Proof of correctness (induction):
      Base case: Two nets with zero bounding-box overlap.
        Assigned to separate clusters.  Their routing order cannot
        affect each other — the board has independent regions.
      Induction: Within a cluster of k overlapping nets, routing
        net 1 (smallest footprint or narrowest bottleneck) first gives
        it a clean grid.  When net k routes, it finds space that
        net 1 through net k-1 didn't need.  By induction on k,
        all nets in the cluster have at least the same routing
        opportunity as random ordering.
      Bottleneck lemma: routing net A (bottleneck=0.5mm) before net B
        (bottleneck=5mm) never makes B unroutable that wouldn't already
        be unroutable (B has 10x more routing options).
    """
    nets = list(channel_mapping.channel_paths)

    if len(nets) <= 1:
        return nets

    # 1. Compute bounding box for each net
    bboxes: dict[str, tuple[float, float, float, float]] = {}
    bbox_areas: dict[str, float] = {}
    for net_name in nets:
        path = channel_mapping.channel_paths[net_name]
        waypoints = path.waypoints
        if not waypoints:
            bboxes[net_name] = (0, 0, 0, 0)
            bbox_areas[net_name] = 0.0
            continue
        xs = [w[0] for w in waypoints]
        ys = [w[1] for w in waypoints]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        bboxes[net_name] = (min_x, min_y, max_x, max_y)
        bbox_areas[net_name] = (max_x - min_x) * (max_y - min_y)

    # 2. Build conflict graph.  Two nets conflict if their bounding
    #    boxes overlap more than 10% of the smaller net's area.
    #    This threshold prevents false clusters from slightly-overlapping
    #    nets that route in entirely different channels.
    threshold = 0.1
    conflict: dict[str, set[str]] = {n: set() for n in nets}
    net_list = list(nets)
    for i in range(len(net_list)):
        a = net_list[i]
        ax1, ay1, ax2, ay2 = bboxes[a]
        area_a = bbox_areas[a]
        if area_a <= 0:
            continue
        for j in range(i + 1, len(net_list)):
            b = net_list[j]
            bx1, by1, bx2, by2 = bboxes[b]
            area_b = bbox_areas[b]
            if area_b <= 0:
                continue
            # Compute overlap
            ox = max(0.0, min(ax2, bx2) - max(ax1, bx1))
            oy = max(0.0, min(ay2, by2) - max(ay1, by1))
            overlap = ox * oy
            min_area = min(area_a, area_b)
            if min_area > 0 and overlap / min_area > threshold:
                conflict[a].add(b)
                conflict[b].add(a)

    # 2b. Find connected components (clusters) via BFS
    visited: set[str] = set()
    clusters: list[list[str]] = []
    for net in nets:
        if net in visited:
            continue
        queue = [net]
        cluster: list[str] = []
        while queue:
            n = queue.pop()
            if n in visited:
                continue
            visited.add(n)
            cluster.append(n)
            # sorted(): conflict[n] is a set, whose iteration order depends
            # on PYTHONHASHSEED (randomized per-process by default). Without
            # this, BFS discovery order -- and therefore the tie-break for
            # nets with identical cluster_sort_key tuples below -- silently
            # varies across process runs, making net routing order (and all
            # downstream track geometry / DRC results) non-reproducible even
            # with a fixed seed passed to route_pcb.
            for neighbor in sorted(conflict[n]):
                if neighbor not in visited:
                    queue.append(neighbor)
        clusters.append(cluster)

    # 3. Within each cluster, sort by (bottleneck_asc, area_asc, not_is_power).
    #    Smallest-footprint nets route first to claim narrow corridors before
    #    larger nets spread through the region.  This matches the Bottleneck
    #    Lemma: routing a small-area net before a large-area net never makes
    #    the large net unroutable.  Power nets are a tiebreaker only.
    def cluster_sort_key(net_name: str) -> tuple:
        name_upper = net_name.upper()
        is_power = any(x in name_upper for x in ["GND", "VCC", "HV", "AC_", "+", "VBUS"])
        if bottleneck_widths is not None:
            bw = bottleneck_widths.get(net_name, float("inf"))
            return (bw, bbox_areas.get(net_name, float("inf")), not is_power)
        return (bbox_areas.get(net_name, float("inf")), not is_power)

    mode = _order_mode()

    # Capture the REAL board's ordering input (net name -> waypoints) when
    # ``TEMPER_CHANNEL_DUMP`` names a file. This is what makes the
    # ``_astar_ordering_py_oracle`` differential run against the production
    # net set rather than a synthetic fixture -- the distinction AGENTS.md
    # records as the reason a genuinely-running differential can still prove
    # nothing ("a differential test only proves what you feed it").
    _chan_dump = os.environ.get("TEMPER_CHANNEL_DUMP", "").strip()
    if _chan_dump:
        import json as _json

        with open(_chan_dump, "w", encoding="utf-8") as _fh:
            _json.dump(
                {
                    n: [list(w) for w in channel_mapping.channel_paths[n].waypoints]
                    for n in nets
                },
                _fh,
            )

    def _dump(order: list[str]) -> list[str]:
        """Record the decided order when ``TEMPER_NET_ORDER_DUMP`` names a
        file. Measurement instrumentation: the ordering hypothesis cannot be
        checked without seeing the order actually used, and inferring it
        from routed output confounds "ordered late" with "failed".
        """
        path = os.environ.get("TEMPER_NET_ORDER_DUMP", "").strip()
        if path:
            import traceback

            caller = "".join(traceback.format_stack(limit=4)[:-1]).replace("\n", " | ")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(
                    f"# mode={mode} n={len(order)} "
                    f"design_rules={'yes' if design_rules is not None else 'NONE'} "
                    f"bottlenecks={'yes' if bottleneck_widths is not None else 'NONE'}\n"
                )
                fh.write(f"# caller: {caller}\n")
                for i, n in enumerate(order):
                    fh.write(f"{i}\t{n}\n")
        return order

    # ``width_desc`` discards the cluster decomposition entirely: the whole
    # point of the mode is that the widest copper lands first GLOBALLY, not
    # first-within-its-own-neighbourhood. The production key is retained as
    # the tiebreak so nets of equal width keep today's relative order.
    if mode == "width_desc":
        widths = {n: _net_trace_width_mm(n, design_rules) for n in nets}
        return _dump(
            sorted(nets, key=lambda n: (-widths[n], *cluster_sort_key(n), n))
        )

    if mode == "hv_first":
        hv = {n: _is_hv_like(n, design_rules) for n in nets}
        # Within a cluster, HV ahead of SELV; production key inside each group.
        for cluster in clusters:
            cluster.sort(key=lambda n: (not hv[n], *cluster_sort_key(n)))
        # And promote any cluster that contains HV copper ahead of the rest,
        # otherwise a cluster-level reordering would still let a whole
        # cluster of SELV signals commit copper before the HV cluster runs.
        clusters.sort(
            key=lambda c: (
                not any(hv[n] for n in c),
                -len(c),
                sum(bbox_areas.get(n, 0) for n in c),
            )
        )
        result = []
        for cluster in clusters:
            result.extend(cluster)
        return _dump(result)

    for cluster in clusters:
        cluster.sort(key=cluster_sort_key)

    # 4. Sort clusters: isolated first, then by cluster size descending
    clusters.sort(key=lambda c: (-len(c), sum(bbox_areas.get(n, 0) for n in c)))

    # 5. Flatten
    result = []
    for cluster in clusters:
        result.extend(cluster)
    return _dump(result)

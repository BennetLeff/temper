"""Companion to ``2026-08-12-router-model-memory-probe.py`` — same measurement,
non-degenerate ``net_channel_vars``.

WHY THIS EXISTS. The original probe generates its variables as
``net_idx = i % 110``, ``channel_id = edge_id(i % 204490)``. Because
``204490 == 110 * 1859`` **exactly**, ``i % 110`` is a function of
``i % 204490``, so the two indices are not independent: the probe's
``(net_idx, channel_id)`` pairs take only **204,490** distinct values no
matter how many variables it creates. ``ConstraintModel.net_channel_vars``
— which is keyed by exactly that pair — therefore ends up ~10x smaller in
the probe than in any real model, where every (net, edge) pair is distinct
by construction. Verified, not assumed: the original probe at N=2,000,000
reports ``len(cm.net_channel_vars) == 204490``.

That degeneracy does not matter for the pre-U1 number (the cost was in the
22.5M CPython objects, and the dict held refcounted aliases of them), but it
matters a great deal afterwards, when the reverse index is one of the two
things left.

This probe uses ``net_idx = i // EDGES``, ``channel_id = edge_id(i % EDGES)``,
so every pair is distinct and ``len(net_channel_vars) == N``. At
N = 2,044,900 that is exactly the production **per-batch** model shape:
``DEFAULT_BATCH_SIZE = 10`` nets over the board's 204,490-edge skeleton.

Usage:  python3 docs/evidence/2026-08-12-router-model-memory-probe-distinct-keys.py [N]

provenance: commit=08ea097d505c78c6437581c150ebfba71d725445 dirty=false
"""

import gc
import sys

import temper_design_bundle_python as t

mb = t.model_builder

EDGES = 204_490
NETS = 110
FULL = NETS * EDGES  # 22,493,900 — the monolithic model


def rss_kb() -> int:
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    raise RuntimeError("VmRSS not found")


def edge_id(i: int) -> str:
    return "F.Cu_E%d_(%.6f, %.6f)_(%.6f, %.6f)" % (
        i,
        123.456789,
        98.765432,
        124.567891,
        99.876543,
    )


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10 * EDGES

    gc.collect()
    base = rss_kb()
    cm = mb.ConstraintModel()
    for i in range(n):
        net_idx = i // EDGES
        cm.add_variable(
            mb.NetChannelVar(
                name="uses_N%d_%s" % (net_idx, edge_id(i % EDGES)),
                net_idx=net_idx,
                channel_id=edge_id(i % EDGES),
            )
        )
    gc.collect()
    after = rss_kb()
    delta = after - base

    print("N=%d  distinct net_channel_vars keys=%d" % (n, len(cm.net_channel_vars)))
    print(
        "model RSS delta=%.3f GB  bytes/var=%.1f" % (delta / 1048576, delta * 1024 / n)
    )
    print(
        "EXTRAPOLATED to %d vars (monolithic): %.2f GB"
        % (FULL, delta * 1024 * FULL / n / 1e9)
    )

    gc.collect()
    b2 = rss_kb()
    lst = cm.variables
    gc.collect()
    a2 = rss_kb()
    print(
        ".variables materialisation delta=%.3f GB  bytes/entry=%.1f  len=%d"
        % ((a2 - b2) / 1048576, (a2 - b2) * 1024 / n, len(lst))
    )


if __name__ == "__main__":
    main()

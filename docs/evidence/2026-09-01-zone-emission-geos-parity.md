<!-- provenance: commit=8ff19d6873c4766471b12d3c169810e5dbd741a9 dirty=true (refreshed measurement on current main; script and evidence updated together) -->

# Zone-emission GEOS parity spike (2026-09-01)

## Verdict

`packages/temper-placer/src/temper_placer/router_v6/zone_emission.py`
`_convex_hull_from_positions` is **JUSTIFIED-KEEP**. The production function
remains the Shapely/GEOS owner. This spike did not establish a safe Rust
replacement.

## Contract and falsifiers

The relevant observable is the point stream consumed by zone emission after
`.4f` formatting, plus the polygon region delivered to the existing board
outline clipper. Raw GEOS ring bytes are not an independent requirement, but
vertex count, ring-start order, and formatted points are observable when they
reach the KiCad zone s-expression. A port would be falsified by a formatted
point mismatch, a region difference, or a changed degenerate geometry.

The measurement used a fail-closed, version-pinned Shapely/GEOS installation
(2.1.2 / GEOS 3.13.1) and an independent unlimited-mitre offset construction.
It replayed the checked-in production inputs from board sha256
`00a27419b82101e3518ddbf9d174f8359d76940c495ca1e5bd3d9cc32d7ac4d9`: 35 exact
`_zone_pour_stitch` groups (the `run_collect_pad_positions` mapping, the
current clustering and exemption decision, and each emitted group) and 4
exact `_power_islands` single-hull calls (the `_pads_by_net` collector,
`_dedupe_positions`, and `cluster=False`). The zone groups cover eligible nets `ac_n`, `ac_l`,
`+170V_BUS`, `PWR_RTN`, `hb-gnd`, `SW_NODE`, `tank.c_tank1-p2`, `DC_BUS_RTN`,
`w1_1`, `w1_2`, `power_in.ntc-no`, and `tank-out`; the power calls cover
`+3V3`, `vcc`, `+15V`, and `V_BUS_SENSE`. It also covered acute/obtuse
triangles, rectangles, two-point and collinear stadiums, and 1,000 seeded
random hulls.

## Measured results

Eleven of the 39 production calls had polygon analytic comparisons: 7
`_zone_pour_stitch` groups and all 4 `_power_islands` calls. The other 28
stitch groups were Point/LineString observations with `compared=false`. The
polygon model diverged at `.4f` for `ac_n`, `hb-gnd`, and `V_BUS_SENSE`.
`ac_l` followed the production four-vertex singleton-square fallback, so no
GEOS Point.buffer comparison was claimed. The acute triangle differed by
1,981.35 mm² and the obtuse triangle by 5.25 mm². The two-point and
collinear cases both reproduced GEOS's 66-vertex stadium observation, whose
ring-start order is not represented by the analytic polygon model. Across
1,000 random cases, all 1,000 were compared, 29 had formatted mismatches,
and the guarded maximum symmetric difference was 11,349.720251428833 mm²
(the guard suppresses a known GEOS overlay artifact when
`equals_exact(..., 1e-12)` is true, while preserving raw-region differences
otherwise).

These results falsify the earlier proposed independent unlimited-mitre port;
they are not exhaustive proof of every GEOS version or edge case. The exact
GEOS limited-mitre branch and degenerate LineString construction remain
unproven against every clustered production call shape, and downstream clip
and board-byte equivalence was therefore not claimed.

## Re-decision condition

Reopen only with a GEOS-version-pinned Rust transcription that is compared to
the external Shapely oracle on every clustered production pad set and both
power-island/fallback consumers, including all degenerate and adversarial
mitre-limit cases, at the emitted `.4f` point/region contract. Include a
downstream zone s-expression comparison before removing the Python owner.

## Reproduction

```text
uv run --no-sync python tools/measurements/zone_emission_geos_parity_spike.py
```

The harness is intentionally under `tools/measurements/` (not `scripts/`),
so no script manifest entry is required. It reads only the checked-in board
and uses a fixed random seed (`20260901`).

---
title: "U3 zone-pour differential promotion"
date: 2026-08-30
module: temper-placer
tags: [router, routing, zone-fill, connectivity, drc, promotion]
status: measured
---

<!-- provenance: measurement_run=33282068940 job=99178784746 head_sha=9877a2004d6647f0541fb2e28e9f3e60a50d9974 merge_sha=de6ee25c869e337c8f41a59b7aa5a168c12fb2a board_commit=c24d0381044e6c77621d18a7616b5e945bb4419b board_sha256=a65bb65c5247493637f9acb510769e604d0e407b256e87e1845160609052b13f dirty=false in CI -->

# U3 zone-pour differential now passes on the production board

## Verdict

U3 is promoted. The strict `xfail` in
`packages/temper-placer/tests/placer/cp_sat/test_zone_pour_production_measurement.py`
was obsolete: the same-run production-board differential measured a reduction
of 20 `unconnected_items`, exceeding the unchanged required margin of 2.
The test continues to require three DRC samples per arm, strictly more zone
entries in the pours-on arm, and the existing `>= 2` improvement threshold.

This promotion does not change a threshold, ratchet, board file, or DRC
ceiling. The earlier negative result in
`docs/evidence/2026-07-28-zone-pour-differential-verdict.md` is superseded for
this board/code state; its historical measurements remain intact.

## Measurement identity and environment

The measurement came from GitHub Actions Regression Suite run
`33282068940`, job `99178784746`, at the PR merge ref
`de6ee25c869e337c8f41a59b7aa5a168c12fb2a` (the PR head was
`9877a2004d6647f0541fb2e28e9f3e60a50d9974`). The checked-in board was
unchanged in the run:

- board source commit: `c24d0381044e6c77621d18a7616b5e945bb4419b`
- `pcb/temper.kicad_pcb` SHA-256:
  `a65bb65c5247493637f9acb510769e604d0e407b256e87e1845160609052b13f`
- board census: 168 components; the routed outputs below emitted 151 and
  167 zone entries respectively
- CI container: `ghcr.io/bennetleff/temper-ci:latest`; the repository's
  pinned Docker build specifies KiCad `10.0.5~ubuntu24.04.1`, and the KiCad
  DRC truth gate passed before this measurement

The job rebuilt all discovered pyo3/maturin extensions before measuring and
passed both freshness checks:

```
10 discovered, 10 checked: fresh=10 stale=0 unloadable=0 missing=0 tool-errors=0
PASSED -- 10/10 extension module(s) fresh.
Verified 10 extension(s): fresh and importable.
```

No `Traceback`, routing exception, or fail-closed rasterizer error occurred
in either route. The only failure in the job was the expected strict-XPASS
exit from the now-promoted assertion itself.

## Clean same-run differential

Each arm routed the same 168-component production board once. Routing
completed with no exception in either arm:

| | pours OFF | pours ON |
|---|---:|---:|
| `enable_zone_pours` | `False` | `True` |
| route wall time | 982.4 s | 1124.4 s |
| completion rate | 0.1333 | 0.1333 |
| emitted zone entries | 151 | 167 |
| `unconnected_items` (median) | **272** | **252** |
| improvement (OFF − ON) | | **20** |

The zone-entry increase (`167 > 151`) proves the two arms are not the same
measurement. Every DRC sample completed and returned data:

| arm | sample 1 | sample 2 | sample 3 |
|---|---:|---:|---:|
| pours OFF — total violations | 433 | 433 | 433 |
| pours OFF — unconnected items | 272 | 272 | 272 |
| pours ON — total violations | 616 | 616 | 616 |
| pours ON — unconnected items | 252 | 252 | 252 |

The first-sample per-type delta printed by the test (ON − OFF) was:

| violation type | delta |
|---|---:|
| `clearance` | +53 |
| `copper_edge_clearance` | +4 |
| `hole_to_hole` | +10 |
| `holes_co_located` | +90 |
| `isolated_copper` | −2 |
| `shorting_items` | +16 |
| `via_dangling` | +12 |

No other violation type changed in that sample. These per-type changes are
reported for diagnosis; U3's promoted contract is the measured connectivity
improvement, the non-vacuous zone-entry difference, and complete DRC samples.

## Retained guard contract

The test still fails loudly if any of these conditions is violated:

1. `kicad-cli` is unavailable (explicit skip, not a false pass).
2. Either route produces suspiciously small output or no DRC samples.
3. The pours-on route emits no additional zone entries.
4. The median connectivity improvement is below
   `_MIN_UNCONNECTED_IMPROVEMENT = 2`.

The promotion removes only the strict-xfail marker and its obsolete
negative-result commentary. It does not relax any of those guards.

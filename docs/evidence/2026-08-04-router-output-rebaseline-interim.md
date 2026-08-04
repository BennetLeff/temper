# Router-output DRC gate: the red is environmental (#652 Part 1)

**Status: diagnosis complete, re-baseline NOT landed.** This records why the gate is red and
what it measures in each environment. It changes no constant — landing those is a ratchet
decision requiring attribution per `AGENTS.md`.

- Date: 2026-08-04
- Issue: [#652](https://github.com/BennetLeff/temper/issues/652) Part 1
- Commit measured: PR #673 (`fix/netclass-rules-mm-aliases`) — the wave4 `_mm` heal
- Gate: `test_production_board_routing_drc_regression`
  (`packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py`)

## 1. Headline

The gate is red because **the thresholds were measured in a different environment than the one
that enforces them.** Nothing regressed.

Both provenance blocks in the test file record `kicad-cli 10.0.4, macOS arm64`. The gate runs
on `ubuntu-latest` inside `ghcr.io/bennetleff/temper-ci`, whose KiCad came from
`ppa:kicad/kicad-10.0-releases` — an **unpinned rolling PPA that now serves 10.0.5**.

## 2. Same commit, both environments

Measured on PR #673, on the same board, with byte-identical router output:

| Metric | macOS arm64 / kicad 10.0.4 (N=15) | Linux `temper-ci` / kicad 10.0.5 (N=5) | Threshold |
|---|---|---|---|
| `total` | 1395 (1368–1406) | **1502** (1499–1502) | 1436 |
| `shorting_items` | 138 (119–141) | 123 | 178 |
| `unconnected_items` | **460** (zero scatter) | **460** (zero scatter) | 463 |

The Linux figures are from the `regression` job on PR #673
([run 30881777884](https://github.com/BennetLeff/temper/actions/runs/30881777884)):
`_DrcSample(runs=5, total=1502, shorting_items=123, unconnected=460, totals=[1499, 1502, 1502, 1502, 1502])`.

**`total` differs by +107 from environment alone. `unconnected_items` is identical.** That
split is the signature: `unconnected_items` is connectivity, which is environment-independent;
`total` and `shorting_items` are geometric, and are not. A regression would not respect that
boundary.

## 3. When it went red, and why

| Date | Commit | `..._TOTAL_DVIOLATIONS` | vs CI's ~1502–1524 |
|---|---|---|---|
| 2026-07-28 | `5b9c05dbb` | 1810 | passes |
| 2026-07-29 | `2382e168c` | 1560 | passes |
| 2026-08-02 | `a2fdfd1bb` | **1436** | **fails — red from here** |

The gate went red at the exact commit that lowered the threshold below what CI measures. The
prior values were loose enough to cover the environment gap by accident; #568's tightening
removed that slack. #652 independently recorded CI at `total` 1524 on 2026-08-02 with "zero
scatter within runs", consistent with 1502 here on a later commit.

## 4. Router determinism premise — HOLDS

The re-baseline depends on `route_pcb()` being reproducible. Three fresh in-process calls over
the committed placement produced **byte-identical output** (`sha256 7d37fe1cbcdbc318…`), route
wall time median 51.1 s. Consistent with `docs/evidence/2026-07-27-router-determinism.md`; that
doc's separate open caveat (17 runs never reproduced the committed board's 53.1% completion) is
untouched here and remains open.

DRC sampling used the bounded-concurrency runner from #633; N=15 cost 5.4 s wall.

## 5. The generalizable finding: the oracle was unpinned

`ci.Dockerfile` installed `kicad` with no version constraint from a PPA that serves only the
newest 10.0.x and drops the previous one. **Every DRC baseline in this repo — including every
entry in `power_pcb_dataset/drc_ceiling.json` — is measured against a binary that could change
with no commit landing.** It already did: 10.0.4 → 10.0.5.

Pinned in this PR to `10.0.5~ubuntu24.04.1`, with the version recorded at build time. When the
PPA drops that version the image build now fails loudly instead of the counts moving silently.

Note the two environment differences are **still confounded**: the container differs from the
macOS host in both OS/arch and KiCad patch version. This document does not separate them, and
does not need to — the actionable conclusion is the same either way: measure where you enforce.

## 6. What is NOT the cause

An earlier hypothesis — that the 2026-08-03 K3 relay swap (`de59c0458`) caused the rise — is
**not supported**. That commit is a real gap: it re-measured `PRODUCTION_COMMITTED_BOARD_*`
(1283→1425, 425→428) and the DRC ceiling but left `PRODUCTION_ROUTER_OUTPUT_*` untouched. It
cannot be the cause, because CI already measured 1524 on 2026-08-02, before it landed.

## 7. Established: #673 improved connectivity by 3

`unconnected_items` measures **460** in *both* environments against a committed baseline of
**463**, with zero scatter in every sample. Attributable to #673 restoring escape-via
generation — `escape_via_generator.py:86` raised `AttributeError` on `rules.via_diameter_mm`
before that fix, so escape vias were never generated. This is a real improvement, and it means
a re-baseline should *lower* `PRODUCTION_ROUTER_OUTPUT_UNCONNECTED` 463 → 460, not raise it.

## 8. To close #652 Part 1

Not landed here, deliberately — these are ratchet changes.

- [ ] Run `regression.yml` via `workflow_dispatch` with `measure_router_baseline=true`
      (added in this PR) to get N≥11 in the enforcing container
- [ ] Re-baseline `PRODUCTION_ROUTER_OUTPUT_*` against those numbers, with a provenance block
      naming the container and the pinned `kicad-cli` version
- [ ] Close the `de59c0458` gap (§6) in the same change
- [ ] Decide whether the *committed-board* constants and `drc_ceiling.json`, also measured on
      macOS 10.0.4, need the same treatment — **not investigated here**, but the same
      environment mismatch applies to them by construction

## 9. Unrelated failure seen in the same run

`tests/placer/cp_sat/test_parallel_drc_helper.py::test_timeout_reaps_the_process_group` failed
with "grandchild survived the timeout" in the container while passing locally. Process-group
reaping under the container's PID namespace — from #633, unrelated to this gate and not
investigated here. Flagged so it is not lost.

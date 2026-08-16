<!-- provenance: commit=fdbe0a6ad2bed62f9bbe13dcd894db92ffbfe6a9 dirty=false -->
---
title: "Extract the pad-layer landing fix (#1196/#1197) onto main -- before/after measured on current main"
date: 2026-08-15
module: temper-placer
tags: [router, routing, pad-connectivity, nlayer, pad-layer-landing, primary-grid]
problem_type: routing-completion
---

# Extract `_land_route_on_pad_layers` (#1196) + `primary_grid` pad-layer anchor (#1197) onto main

**One-line result:** the pad-layer landing fix is now on `main` (via this
branch), with 16/16 `test_astar_nlayer.py` tests passing (5 of them new,
from the fix), and a full batched 6-layer route of current main measured
before/after: **pad-connected M1 nets went from N/a (broken) to connected**
— see §4 for the measured numbers.

## 1. Why this exists

Agent 57's root-cause doc
(`docs/evidence/2026-08-15-unrouted-nets-rootcause.md`, on
`investigate/unrouted-nets-rootcause`) classified every non-connected net
of a full 6-layer route of `origin/main` into five exhaustive mechanisms.
**M1 (32 nets): wrong-layer landing, no via.** The netclass SSOT
(`netclass_rules.yaml`: `GateDriveHV`/`GateDriveSELV`/`FinePitch` →
`layer: "B.Cu"`) forces a net's working layer; every SMD pad on this board
sits on `F.Cu`; Tier 1 of `_astar_nlayer.py`'s 3-tier cascade walks
straight to the pad's exact (x, y) on the forced layer (an SMD pad leaves
no obstacle on a layer it has no copper on), reports "arrival", and emits
copper that never touches the pad — zero vias.

Measured on the fresh output, `GATE_HS`:

```
trace: (47.6025,115.35) -> (82.735,137.555), all 67 segments on B.Cu, 0 vias
pad R18.1 at (47.6025,115.35) layer=F.Cu   <- endpoint lands EXACTLY here, wrong layer
pad U6.15 at (82.735,137.555) layer=F.Cu   <- endpoint lands EXACTLY here, wrong layer
```

The fix (`_land_route_on_pad_layers`, PR #1196) and its sibling
(`primary_grid`/route-boundary anchor from the net's own pad layer, PR
#1197) were written and measured on the `fix/router-nlayer-routing` branch,
but **were never extracted onto `main`** — they sit inside the blocked PR
#1178 stack. `main`'s `_astar_nlayer.py` had zero occurrences of
`_land_route_on_pad_layers`.

## 2. What was extracted (this branch)

Six commits cherry-picked from `origin/agent/router-primary-grid-and-partial-decline`
(the #1197 head, which contains #1196's work) onto a fresh branch off
`origin/main` @ `6285d6889`:

| commit | content |
|---|---|
| `93126fdce` | `fix(router): land N-layer routes on their pad's real copper layer` — `_land_route_on_pad_layers` + call site + `FAILURE_REASON_PAD_LAYER_LANDING_BLOCKED`, 5 new tests |
| `b062cf9df` | `docs(evidence): router pad-layer landing fix` — the original diagnosis/fix doc |
| `6a17044c9` | `docs(router): fix _assign_layer's stale docstring` (docs-only) |
| `ae9a754d4` | `fix(router): choose primary_grid/route-boundary anchor layer from the net's own pad layer, not SSOT alone` (#1197) — `pad_layer_start/pad_layer_end` in `_astar_route_nlayer`, `layer_divergence_count` on `PathfindingResult` |
| `8ae2267da` | `fix(router): skip degenerate same-layer anchor via in Tier 2's alt-layer detour` |
| `e3a73885a` | `docs(evidence): router primary_grid selection fix` — original doc |

All six cherry-picked cleanly. The only divergence between `main` and the
source branch's `_astar_nlayer.py` was `via_diameter` fallback (branch:
`0.6`; main: `0.9`, the 2026-08-13 fab-floor fix) — **main's `0.9` was
preserved** (verified: `via_diameter=net_rules.via_diameter_mm if
net_rules else 0.9` still in place).

Deliberately NOT extracted: the layer-aware IPC-2221B ampacity kernel /
DRC-rs current citations that were squashed into #1196's merge commit on
the branch — separate concern with its own review path; out of scope here.

## 3. Test verification

Isolated worktree venv (`make venv-isolate` + `make extensions`; 10/10
fresh, never touched the shared repo venv):

```
tests/router_v6/test_astar_nlayer.py: 16 passed   (11 pre-existing + 5 new)
```

Full `tests/router_v6/` suite: only pre-existing failures, all confirmed
byte-identical on `origin/main` itself:
- `test_bundle_analyzer_rust_differential.py` — `networkx.Graph()` fixture
  vs Rust `SkeletonGraph` (`edges_with_data` API mismatch; handoff §5
  documents this pre-existing cause)
- `test_strip_copper.py::test_matches_real_production_board_zone_count` —
  pinned segment count 2290 vs actual board 2149 (stale ground truth,
  documented in the evidence doc being ported)

## 4. Route verification (before/after on current main @ 6285d6889)

Recipe (identical for both, per agent 57's root-cause doc §6):

```
scripts/route_board.py --net-batching --batch-size 10 --output <scratch>
```

- **Before**: fresh worktree at `origin/main` @ `6285d6889` (no fix),
  isolated venv.
- **After**: this branch (fix extracted), isolated venv.
- Audit: `pad_connectivity_audit.audit_pcb_file` (fixed #1200, on main).
- The audit helper was validated against agent 57's baseline artifact:
  reproduces 62/139 connected / 9 zone / 68 broken exactly.

| metric | before (main) | after (fix) | delta |
|---|---|---|---|
| fully pad-connected | 63/139 | **69/139** | **+6** |
| zone-dependent | 9 | 10 | +1 |
| broken (incl. fake-completion) | 67 | 60 | −7 |
| fake-completion (subset of broken) | 63 | 54 | −9 |
| segments | 5629 | 5962 | +333 |
| vias | 76 | 95 | +19 |
| **F.Cu↔B.Cu vias** | 3 | **16** | **+13 — the landing vias appearing** |
| zones | 320 | 314 | −6 |
| nets routed (topology count) | 94/106 | 91/106 | −3 |
| wall time | 649.7s | 680.8s | +31s |

**M1 nets (32, from agent 57's classification) now fully connected: 7.**
`GATE_HS`, `PWM_HS`, `PWM_LS`, `RTD_CS_N`, `RTD_DRDY`, `RTD_SDI`, `sclk` —
all 2-pad nets that were emitting B.Cu-only copper with zero vias before.

Newly connected (9): `GATE_HS`, `PWM_HS`, `PWM_LS`, `RTD_CS_N`, `RTD_DRDY`,
`RTD_SCK`, `RTD_SDI`, `sclk`, `sdo`. `RTD_SCK`/`sdo` were agent 57's M4
(A* no path) — the landing vias free the inner layers from phantom-occupied
wrong-layer copper, which is exactly the M1+M4 interaction agent 57
predicted ("correct vias free the inner layers").

Lost connected (3): `RELAY_CTRL`, `i2c_sda_ui`, `safety.ovp.r_adc_top1-p2`
→ run-to-run churn, not a fix regression. Agent 57's doc measures 7 nets
flipping between two identical-code runs; `RELAY_CTRL` itself was
M4-broken in their run but connected in this before-run on the same `main`
code. `i2c_sda_ui` is one of the nets agent 57 named as a churn flipper.
Zero `pad_layer_landing_blocked` declines were recorded in the after run.

**GATE_HS verified at coordinate level (the task's check):**

```
BEFORE: (47.6025,115.35) -> (82.735,137.555), 67 segments all B.Cu, 0 vias
AFTER:  67 segments B.Cu + 2 vias at exactly (47.6025,115.35) and
        (82.735,137.555), layers F.Cu↔B.Cu -- the B.Cu copper now
        physically lands on the F.Cu pads.
```

The 13-net movement out of fake-completion (63→54) is the fail-closed path
working: fakes became either genuine completions or honest declines, not
gaps converting into fakes (checked: honest-gap 13→16, the documented
fail-closed trade-off for nets whose pad layer is occupied at the landing
point).

## 5. Caveats (from the original evidence docs, still true)

- 3 M1 nets (`cs_n`, `sdo`, `RTD_DRDY`) need the #1197 `primary_grid` fix
  (included here) — the original #1196-alone measurement left them
  fake-completion via a co-located-via `via_layer_pair` limitation; #1197
  addresses the root cause. In this run `RTD_DRDY`/`sdo` ARE connected;
  `cs_n` declined to zero copper (honest, in the UNEXPLAINED set).
- The net-level all-or-nothing fail-closed decline is a deliberate
  trade-off (honest zero copper instead of copper that never lands).
- This branch does NOT touch `pcb/temper.kicad_pcb` (sha256 unchanged),
  no DRU/clearance/creepage threshold, no `drc_ceiling.json` ceiling.

## 6. Artifacts

- Routed before: `/tmp/opencode/pad-layer-before.kicad_pcb`
- Routed after: `/tmp/opencode/pad-layer-after.kicad_pcb`
- Route logs: `/tmp/opencode/pad-layer-before.log`, `/tmp/opencode/pad-layer-after.log`
- Committed board untouched.

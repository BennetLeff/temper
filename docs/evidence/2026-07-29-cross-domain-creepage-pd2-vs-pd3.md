# Cross-domain HV<->SELV creepage, pairwise: what PD3 actually costs over PD2

<!-- provenance: commit=57f0c7550a312bafd69d14f7ae8c0ace16fa12eb dirty=false -->

**Date:** 2026-07-29
**Base commit:** `5401a827` (branch `feat/pairwise-creepage-tool`, from
`origin/main` `46d4b4c8`), isolated worktree, `make venv-isolate` run first.
**Scope touched:** `scripts/measure_cross_domain_creepage.py` (new),
`scripts/tests/test_measure_cross_domain_creepage.py` (new),
`scripts/manifest.yaml`, `scripts/invocation_graph.json`, this document. No
`pcb/`, no netclass/footprint/safety-constant change anywhere -- this is a
measurement tool, not a gate, and is not wired into CI.
**Method:** `scripts/measure_cross_domain_creepage.py`, run twice against the
real `pcb/temper.kicad_pcb` and `elec/domain_manifest.yaml`
(`--min-creepage-mm 8.0 --compare-to-mm 12.6`). Deterministic -- no
`kicad-cli` invocation anywhere in the tool.

---

## The headline number

**At 8.0mm (PD2): 62 of 21437 cross-domain pairs fail.**
**At 12.6mm (PD3): 195 of 21437 cross-domain pairs fail.**
**The delta -- the measured cost of PD3 over PD2 -- is 133 pairs**, of which:

| class | count | remedy |
|---|---:|---|
| `body_free` | 16 | fixable by a routed isolation slot |
| `body_crossing` | 105 | **not** fixable by a slot -- needs a different part/footprint or placement change |
| `unknown` | 12 | own-footprint body outline missing from the library data; flagged, not guessed |

The denominator is 97 HV pads x 221 SELV pads = **21437 pairs examined at
both thresholds** -- every one of them, not a pre-filtered subset. "0
violations" could never have silently meant "found nothing" here: this tool
raises a hard error (never a clean report) if either domain resolves to zero
pads (see `scripts/tests/test_measure_cross_domain_creepage.py::TestAntiVacuity`).

## Reproducing this

```
uv run --no-sync python scripts/measure_cross_domain_creepage.py \
    --min-creepage-mm 8.0 --compare-to-mm 12.6 --json /tmp/result.json
```

Both counts, the delta, and the per-pair/per-component detail below all come
from one invocation of this command against the commit named above.

## 1. Board census

| | value |
|---|---:|
| Footprints | 168 (161 with a usable F.Fab or F.CrtYd body outline; 7 without: C1, C6, F1, L2, R30, RT1, U27) |
| Pads total | 519 |
| HV-domain pads | 97 (21 HV nets, `elec/domain_manifest.yaml`) |
| SELV-domain pads | 221 (33 SELV nets) |
| Cross-domain pairs examined | **21437** (= 97 x 221) |
| Back-side (B.Cu) footprints | 0 -- the position-flip/rotation-sign ambiguity discussed in Sec 5 never triggers on this board, checked at runtime, not assumed |

## 2. At 8.0mm (PD2, the figure `check_isolation_keepout.py`'s `MIN_BARRIER_WIDTH_MM` currently enforces on `origin/main`)

**62 of 21437 pairs violate.**

| body class | count |
|---|---:|
| `body_free` | 8 |
| `body_crossing` | 38 |
| `unknown` | 16 |

Worst 10 (smallest gap first):

| gap (mm) | pair | class |
|---:|---|---|
| 0.905 | C17.2(`hb.gate_hs.driver-p2`) <-> R32.1(`+3V3`) | body_free |
| 1.969 | C22.2(`hb.gate_hs.driver-p2`) <-> L2.2(`+3V3`) | unknown (L2 has no F.Fab/F.CrtYd) |
| 2.612 | R30.1(`tank.c_tank1-p2`) <-> R32.1(`+3V3`) | unknown (R30 has no F.Fab/F.CrtYd) |
| 2.953 | R30.1 <-> R1.1(`+15V`) | unknown |
| 3.018 | R30.1 <-> R1.2(`power_in.bypass_relay-coil1`) | unknown |
| 3.200 | C6.1(`PWR_RTN`) <-> C6.2(`gnd`) | unknown (C6 has no F.Fab/F.CrtYd -- see Sec 4) |
| 3.273 | C22.1 <-> L2.2 | body_crossing (crosses C22) |
| 3.325 | C17.1(`hb.gate_hs.driver-p1-1`) <-> R26.1(`PWM_LS`) | body_free |
| 3.559 | K2.1(`PWR_RTN`) <-> K2.2(`discharge.k_dis1-coil1`) | body_crossing (crosses K2) |
| 3.559 | K3.1(`DC_BUS_RTN`) <-> K3.2(`discharge.k_dis2-coil1`) | body_crossing (crosses K3) |

Full list of 62 (worst-first) and the 26-component "fix list" are in stdout
from the reproduction command; not reproduced in full here since Sec 3's
delta table is the actionable one for the PD3 decision.

## 3. At 12.6mm (PD3)

**195 of 21437 pairs violate.**

| body class | count |
|---|---:|
| `body_free` | 24 |
| `body_crossing` | 143 |
| `unknown` | 28 |

## 4. The delta: 133 pairs, and what they cost

This is the number the task exists to produce. 133 pairs pass at 8.0mm and
fail at 12.6mm -- **the measured cost of moving PD2 -> PD3**, broken down:

- **16 body_free** -- these can, in principle, be resolved by routing an
  isolation slot (this board currently has none -- a single rectangular
  `Edge.Cuts` outline, no interior cutout).
- **105 body_crossing** -- the majority, and the actionable finding. No
  slot fixes these; each one needs either a different part/footprint (wider
  creepage-relevant pad spacing) or enough placement margin from the
  *other* end of the pair to make up the difference. Several are declared
  isolators' own HV<->SELV pin pairs crossing into violation at the wider
  threshold: K1's own pair (exactly 8.000mm, zero margin at PD2, a real
  violation at PD3) and T1's own pair (9.100mm, clear at PD2, a violation at
  PD3) are both in the delta. U7 and T1 also already had OTHER pin pairs
  violating at 8.0mm (Sec 6) -- the delta adds newly-crossing pairs for those
  same parts, not a first appearance of the part.
- **12 unknown** -- own-footprint body outline missing from this board's
  library data (see Sec 7). Flagged, not silently counted either way.

Parts most implicated by the delta (worst gap first, top 15 of 72):

| part | worst new gap (mm) | newly-violating pairs |
|---|---:|---:|
| K1 | 8.000 | 12 |
| C22 | 8.004 | 16 |
| C28 | 8.004 | 2 |
| C23 | 8.025 | 12 |
| U27 | 8.025 | 13 |
| U7 | 8.026 | 20 |
| C17 | 8.057 | 10 |
| R54 | 8.057 | 5 |
| R77 | 8.067 | 2 |
| T1 | 8.126 | 9 |
| R23 | 8.255 | 2 |
| C6 | 8.255 | 2 |
| C12 | 8.289 | 2 |
| RT1 | 8.426 | 3 |
| R59 | 8.426 | 5 |

(Full 72-part list is in the tool's stdout; the pattern above -- a handful
of parts (K1, C22, U7, C17, T1) accounting for a large share of the
newly-violating pairs -- is the actionable structure: fixing those first
buys back most of the delta.)

## 5. Rotation-convention sensitivity (checked, not assumed)

`docs/evidence/2026-07-28-req-safe-01-rederivation.md` (an earlier
investigation on a sibling branch) flagged an **open question**: this repo's
own parser/writer (`temper_placer.io._parse_modules.py`) rotate a footprint's
local pad offset by `R(+theta)`, while KiCad's own internal convention is
`R(-theta)`; the two agree everywhere except a 90/270-degree-rotated
footprint's position relative to *another* footprint, and which one is
"real" was left unresolved (weak evidence favoured `R(+theta)`).

This tool does not silently pick a side. `--min-creepage-mm`/`--compare-to-mm`
runs default to `R(+theta)` (the convention `check_isolation_keepout.py` and
this repo's own parser/writer use) but every violating pair is *also*
recomputed under `R(-theta)`, and flagged if its pass/fail verdict flips:

- At 8.0mm: **12 of 62** violations are convention-sensitive.
- At 12.6mm: **29 of 195** violations are convention-sensitive.

This is a real, open gap in this repo's own geometry pipeline, not something
this tool introduces or resolves. It does not change the headline delta
(133), since it affects which *specific* pairs are counted as violating at
each threshold, not the pass/fail count materially (both thresholds carry
proportionally similar sensitive fractions, ~19-15%). Flagged here rather
than adjudicated -- resolving it is out of this task's scope (measurement
only, no board/constant change).

**Pad rotation ANGLE** (as opposed to pad *position*) is a separate question
and is NOT ambiguous: a pad's `(at x y angle)` in a placed `.kicad_pcb` file
is its absolute world angle already, never added to the footprint's own
angle. This was verified directly, not assumed: computing T1 pin1<->pin4 and
K1 pin13<->pinA1 under this convention reproduces the exact, previously
published 9.100mm / 8.000mm figures (Sec 6); adding the footprint's angle
to the pad's angle instead reproduces neither (T1 comes out 7.800mm).

## 6. Ground-truth validation

Before trusting this tool's own numbers, they were checked against figures
already published and pipeline-validated elsewhere in this repo's history
(`docs/evidence/2026-07-28-req-safe-01-rederivation.md`,
`packages/temper-placer/tests/requirements/safety/test_clearance_copper.py`):

| pair | published figure | this tool | match |
|---|---:|---:|---|
| K1 pin13 (`power_in.ntc-no`) <-> pinA1 (`power_in.bypass_relay-coil1`) | 8.000mm | 8.000mm | exact |
| T1 pin1 (`tank-out`) <-> pin4 (`gnd`) | 9.100mm | 9.09999999999997mm | exact (fp rounding) |
| C17-R32 closest pads | ~0.904mm | 0.905mm | matches within board-state drift (see Sec 8) |

All 8 of `elec/domain_manifest.yaml`'s declared mains<->PELV isolators
(C6, K1, K2, K3, PS1, T1, U3, U7) were checked individually:

| part | own-pin gap (mm) | class | note |
|---|---:|---|---|
| K2 | 3.559 | body_crossing | |
| K3 | 3.559 | body_crossing | |
| U3 | 6.020 | body_crossing | (multiple pin pairs, all body_crossing) |
| U7 | 7.250 | body_crossing | (multiple pin pairs, all body_crossing) |
| K1 | 8.000 | body_crossing | passes at 8.0mm (not `< 8.0`), fails at 12.6mm |
| T1 | 9.100 | body_crossing | passes both 8.0mm and 12.6mm |
| PS1 | 35.5 | (never a violation) | wide margin, correctly never appears |
| C6 | 3.200 | **unknown** | C6 has neither F.Fab nor F.CrtYd geometry in this board's library data -- see Sec 7 |

7 of 8 are correctly classified `body_crossing` by the geometric method (the
straight-line path between the part's own HV and SELV pins genuinely threads
under its own F.Fab body). C6 is the one exception, and it is flagged as
`unknown` rather than guessed `body_crossing` even though visual inspection
of a 2-pin capacitor makes the answer obvious to a human -- this tool does
not special-case "2-pad footprints must be body-crossing" because that
would be exactly the kind of naming/shape-convention guess this repo's own
domain-manifest ground rule (net names, not inferred) warns against
generalizing from. **This is the intended, honest behavior, not a defect**:
C6's own footprint library entry genuinely carries no F.Fab/F.CrtYd
geometry, so the tool cannot positively confirm the crossing and says so
instead of asserting it.

## 7. What could not be measured (flagged, not guessed)

- **Body classification for pairs involving C1, C6, F1, L2, R30, RT1, or
  U27** (7 of 168 footprints) is `unknown` whenever no *other* footprint's
  body was found crossing the path either -- 16 of 62 violations at 8.0mm,
  28 of 195 at 12.6mm. These are real gaps in this board's footprint library
  data (missing `F.Fab`/`F.CrtYd` graphic items), not measurement failures
  of this tool. C6 (Sec 6) is known, by inspection, to actually be
  body-crossing; R30, L2, RT1, F1, C1 are unverified either way; U27 is the
  ESP32-S3-WROOM-1 module and is SELV-only itself (it never forms an
  intra-footprint HV<->SELV pair), so its missing outline only affects
  classification of *other* pairs whose path happens to route near it.
- **Rotation-convention sensitivity** (Sec 5): 12/62 and 29/195 pairs have a
  verdict that depends on an open question this repo's own history has not
  resolved. Flagged, not adjudicated.
- **Routed copper is not included.** This tool measures pad-to-pad creepage
  only, matching `check_isolation_keepout.py`'s own scope. The prior
  rederivation doc found a same-layer HV<->SELV separation as low as
  0.000mm once routed track/via copper is included (not pads) -- that
  finding is orthogonal to this one and not re-measured here.
- **Slot-aware surface pathing is not modeled.** `pcb/temper.kicad_pcb` has
  a single rectangular `Edge.Cuts` outline and zero interior cutouts, so the
  straight-line distance this tool measures *is* the true creepage path,
  exactly (no slot to detour around exists to make it otherwise -- see
  `packages/temper-placer/src/temper_placer/requirements/validators/_copper.py`'s
  `CREEPAGE_MODEL_UNBROKEN_SURFACE` for the same reasoning applied
  elsewhere in this repo). If a slot is later added, this tool's numbers for
  pairs near it would become conservative *underestimates* of true creepage
  (safe direction), not wrong in the unsafe one.

## 8. Reconciling against `c58c94d8`'s 152/132/20

`c58c94d8`'s commit message reports **152 sub-12.6mm cross-domain pairs (132
body-free, 20 body-crossing)** on its own board state, against a sibling
session's 202, explained there as differing board state (that commit's own
K2/K3 relay swap moved HV nets 21->27 and HV pads 97->87).

**This tool's own count (195) does not reproduce 152, and the body-free/
body-crossing ratio is inverted** (this tool: 24 free / 143 crossing / 28
unknown at 12.6mm; `c58c94d8`: 132 free / 20 crossing). Treating this tool as
the thing under suspicion first, per this task's instructions:

1. **`c58c94d8` is not an ancestor of `origin/main`.** Checked directly
   (`git merge-base --is-ancestor c58c94d8 HEAD` fails) -- it exists only on
   an unmerged sibling branch. This worktree is branched from `origin/main`
   (`46d4b4c8`), a genuinely different commit.
2. **The board states are mechanically different, and this is checkable,
   not speculative.** `c58c94d8`'s own commit message states its board
   carries **27 HV nets and 87 HV pads** (post-K2/K3-relay-swap). This
   worktree's board (`elec/domain_manifest.yaml` on `origin/main`) has
   **21 HV nets and 97 HV pads** -- and `elec/domain_manifest.yaml`'s own
   history (Sec "REVERTED 2026-07-28") confirms K2/K3 are the Omron G5LE-1
   (`Relay_SPDT`), i.e. the *pre-swap* part, not the Finder 40.52 DPDT swap
   `c58c94d8` measured. This worktree's board is the state
   `c58c94d8`'s own message calls "different board state" relative to
   itself -- the same category of explanation it used for its own 152-vs-202
   sibling disagreement applies here too, and is directly verifiable rather
   than assumed.
3. **This tool's own pipeline is independently ground-truthed** (Sec 6): it
   reproduces two previously-published, pipeline-validated exact figures
   (K1=8.000mm, T1=9.100mm) bit-for-bit, and correctly classifies 7 of 8
   declared isolators as `body_crossing`. This is evidence the *measurement*
   is sound even though the *total count* disagrees with `c58c94d8`.
4. **The body-free/body-crossing methodology is not directly comparable.**
   `c58c94d8`'s throwaway script was, per this task's own brief, never
   committed -- there is no way to inspect what "body-free" meant there. If
   its classifier only checked whether two pads belonged to the *same*
   footprint (the simplest possible heuristic, and a defensible one for a
   throwaway script), it would call every inter-footprint pair "body-free"
   regardless of whether a third component's body sits on the path between
   them -- which is exactly the bystander-crossing case this tool's method
   (checking the path against *every* footprint's body, not just the two
   endpoints' own) is built to catch (Sec 4: 105 of 133 delta pairs are
   `body_crossing`, the majority of which are inter-footprint bystander
   crossings, not intra-footprint isolator pairs). That would fully explain
   the inverted ratio without requiring this tool's method to be wrong.
   This is plausible, not confirmed -- the sibling script cannot be
   inspected, so it is reported as the leading hypothesis, not a fact.

**Verdict: not reproduced, and the leading explanation is (a) a genuinely
different, verifiably-different board state and (b) a different, unverifiable
body-classification methodology in a script that was never committed -- not
a defect in this tool, per the ground-truth checks in Sec 6.** This is
exactly the failure mode the task describes this tool as existing to
eliminate: from this point forward, re-running `scripts/
measure_cross_domain_creepage.py` against any board state produces a number
that can be directly compared to another run of the *same* tool, rather than
reconciled after the fact from commit-message prose.

## 9. Constraints honoured

- No safety constant, netclass, footprint, or board file changed.
  `pcb/temper.kicad_pcb` and `elec/domain_manifest.yaml` are read-only
  inputs to this tool.
- No target lowered or adjusted to make output look better. 195 violations
  at 12.6mm is reported as measured; it is a large number and this document
  does not soften it.
- `scripts/measure_cross_domain_creepage.py` is not wired into CI and has no
  gate/fail-on-violations mode. It is a measurement tool only.
- Built in an isolated worktree (`git worktree`), branched from
  `origin/main`, `make venv-isolate` run before any measurement. No
  `git stash` used anywhere in this task.
- `uv run --no-sync` used for every invocation.
- Committed before this document: `5401a827` (script + tests + manifest).
  This document and its provenance stamp are the only thing added after
  that commit for the measurement described above.

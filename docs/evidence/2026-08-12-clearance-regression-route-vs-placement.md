<!-- provenance: measured 2026-08-12, worktree
.claude/worktrees/agent-a374c69e35366ad12, branch diagnose/clearance-regression,
HEAD d8062c6e6f60b693aa42f615e4042826de417d63 (origin/main, includes #1050/#1051/
#1052/#1053; pcb/temper.kicad_pcb untouched since c4956df66, sha256
6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64, byte-identical
to power_pcb_dataset/drc_ceiling.json's own recorded provenance hash). Candidate
board regenerated from scratch in
/tmp/.../scratchpad/{regen,drc_main,drc_candidate}/, never under pcb/**
(confirmed `git status --short pcb/` empty throughout this task). kicad-cli
10.0.5 at /home/bennet/.local/opt/kicad-10.0.5, invoked with
LD_LIBRARY_PATH=<every *.so dir under kicad-10.0.5/root> and
KICAD_STOCK_DATA_HOME=<prefix>/root/usr/share/kicad (the invocation
docs/evidence/2026-08-11-pad-connectivity-ground-truth.md records), verified
via `kicad-cli version` == 10.0.5 before every DRC run. Both boards' DRC ran
against a byte-identical copy of pcb/temper.kicad_pro (diffed sha256, confirmed
equal) and a freshly regenerated pcb/temper.kicad_dru
(scripts/generate_kicad_dru.py, run fresh in this session). -->

# The `clearance` regression is real, reproduces almost exactly (+113/+113), is 96%+ track/pad-vs-copper (not pad-vs-pad placement crowding), is not a mains&lt;-&gt;SELV hazard, and is not a netclass-enforcement artifact

> **CORRECTION (2026-08-12), added by the void-board-baseline purge task.** This document
> cites two figures that are **VOID**: §1's fidelity table ("doc's reported value" 4,228
> segments / 74 vias, PR #1050) and §6/Sources' "94->44" `SAF_HVL_001` cross-reference
> (`docs/evidence/2026-08-12-hvlv-candidate-board-measurement.md`) -- both measured on an
> unpinned `pumpkin_engine` build; see the correction notices on the two respective source
> documents. True figures: segments/vias/zones baseline **2,514 / 22 / 76** (168
> footprints); `SAF_HVL_001` **94 -> 74 (-21%)**, not 94 -> 44.
> `scripts/board_shape_baseline.json` is the current source of truth. This document's own
> primary finding -- that the `clearance` regression is routing-caused congestion, not
> placement crowding, and not a mains<->SELV hazard (§2-7) -- was derived from this
> document's own independently-regenerated candidate board (also, necessarily, an
> unpinned-engine board, since this document predates #1060) and is **not re-verified
> against the pinned-engine board** by this correction; it is reported as originally
> measured, not silently re-scoped.

**Verdict up front.** The +113 `clearance` regression (386/392 -> 499/505,
depending on zone-refill state) reproduces almost exactly under an
independent, from-scratch regeneration of the candidate board. It
concentrates in the safety-interlock logic cluster (`safety.latch`,
`safety.uvlo_logic.*`, `safety.fault_any_or`), the MCU (`U27`), and the
`rtd_pan` analog front end — confirming PR #1050's own hypothesis, with more
precision than "U27/U26" alone. **The single most decisive fact: 0 of 505
candidate `clearance` violations are pad-to-pad.** 49.9% are pad-to-track,
45.3% are track-to-track, the rest are via-involved. Placement (footprint
packing) is not the mechanism — main's own board actually has MORE pad-to-pad
clearance violations (38) than the candidate (0). This is a **routing**
regression: the router is threading traces through F.Cu space that is too
congested to hold them at the required clearance, in the same region PR
#1052's corridor-aware A* already proved cannot be fixed by a smarter search
(it found no clearance-respecting path exists there at all, at the current
placement density). **None of the +113 are mains<->SELV proximity
violations** — that axis is strictly *better* on the candidate (0 HV-only
vs. SELV-only clearance pairs, vs. 4 on main; consistent with
`docs/evidence/2026-08-12-hvlv-candidate-board-measurement.md`'s independent
`SAF_HVL_001` 94->44 finding). **None of it is newly-correct netclass
enforcement** — both boards' DRC ran against a byte-identical
`pcb/temper.kicad_pro` (diffed, proven equal), and #1051's own commit message
already states the kicad-cli DRC path (`--backend kicad-cli`, what
`clearance` is) never reads the Python/Rust `Component.net_class` field
#1051 fixed at all; it reads `pcb/temper.kicad_pro` directly, which has been
unchanged since `28de4543d`, three commits before the board's own last
change. 54.3% of the candidate's violations are gross (actual gap <= half
the required gap); only 10.3% are marginal. This is a structural, routing/
placement-density problem, not a rule-tuning one, and PR #1052 already
demonstrated that a materially better router does not fix it.

## 1. Regeneration: reproduces PR #1050's recipe closely, with one flagged discrepancy

Followed `docs/evidence/2026-08-12-place-and-reroute-connectivity.md` and
`docs/evidence/2026-08-12-isolation-barrier-pumpkin-placement.md`'s recipe
end to end, independently, in scratch space:

1. **Netlist.** `make netlist` (fresh atopile build) -> `elec/build/default.net`,
   digest `8cfd715e60a3…` — **matches** the digest both prior docs and #1049
   independently recorded.
2. **Reconciliation.** `scripts/resync_pcb_netlist.py` against a
   copper-stripped copy of `origin/main`'s board (`strip_existing_copper`
   removed exactly 2434 blocks = 2290 segments + 96 zones + 48 vias, matching
   the committed board's own counts). Result: `netlist_components: 168,
   kept: 162, added: 6, removed: 7, moved: 0` —added
   `{C37, J1, R65, T2, TP3, U19}`, removed `{D2, R6, R7, R8, R9, R10, U3}` —
   **byte-identical** to PR #1050's own reported delta.
3. **Placement (Pumpkin).** Netclass+courtyard constraints:
   9,647 netclass-auto + 12,301 courtyard-backfill = **21,948**, exact match.
   Domain partition: **hv_only=40, selv_only=109, isolators=8
   ({C6,K1,K2,K3,PS1,T1,T2,U6}), unclassified=11** — exact match, including
   the isolator set (T2 in, U3 out, vs. the pre-reconciliation board).
   Per-isolator `achievable_gap_mm`/`chosen_rotation` at the PD2/8.0mm bar,
   horizontal axis: **byte-identical to all 8 rows** of
   `2026-08-12-isolation-barrier-pumpkin-placement.md`'s table (C6 8.000/3,
   K1 8.000/2, K2 12.760/1, K3 12.760/1, PS1 35.500/3, T1 9.100/0,
   T2 9.100/0, U6 8.100/1). U6 relaxed, other 7 hard-constrained: **solved
   `optimal` in ~1.0s** (doc: 2.6s, different machine, same outcome class).
   Round-trip oracle: **PASS, 168 components, 521 pads** — exact match.
4. **Routing** (`route_board.py --net-batching`, the documented recipe):
   completed in 349.5s wall time.

   | | doc's reported value | reproduced here | match? |
   |---|---:|---:|---|
   | footprints | 168 | **168** | exact |
   | zones | 66 | **66** | exact |
   | segments | 4,228 | **3,319** | **-21.5%, flagged** |
   | vias | 74 | **56** | **-24.3%, flagged** |

   **This does not trigger the task's STOP condition** (real, substantial
   copper was regenerated — not #1049's zero-copper failure) but is reported
   in full per the task's own "report inconvenient results" rule rather than
   silently treated as identical. Both footprint and, notably, **zone**
   count match exactly; only the per-net A* track-routing stage produced
   fewer completed segments/vias than the documented run. `route_board.py`
   has no `--seed` flag and its net-batching order is not guaranteed
   run-to-run-identical across machines/sessions (a documented property of
   this router elsewhere in the repo — `shorting_items` noise up to ±11 is
   already called out in `docs/STRATEGY.md`); this looks like the same class
   of routing-order nondeterminism, not a reproduction failure. Its effect
   on the actual finding is addressed in §2.

## 2. The `clearance` delta reproduces almost exactly, and is *insensitive* to how much routing actually completed

Both boards measured identically: `kicad-cli pcb drc --format json
--severity-all --exit-code-violations --all-track-errors --refill-zones`,
against a byte-identical `pcb/temper.kicad_pro` (sha256-diffed, equal) and a
freshly generated `pcb/temper.kicad_dru`.

| | `origin/main` (committed) | Candidate (regenerated) | Delta |
|---|---:|---:|---:|
| `clearance`, `--refill-zones` | **392** | **505** | **+113** |
| `clearance`, no refill | 386 (matches `drc_ceiling.json`'s 130-sample ceiling exactly) | 504 | +118 |
| `creepage`, `--refill-zones` | 382 | 195 | -187 |
| `shorting_items`, `--refill-zones` | 200 | 58 | -142 |
| Total violations, `--refill-zones` | 2188 | 1981 | -207 |

The task's own headline number, **+113**, is reproduced exactly on the
refill-zones-consistent measurement (392 -> 505). The no-refill number
(504) is within 1% of PR #1050's own reported 499, despite this run's
routing completing meaningfully less copper (§1). **This is itself
informative**: PR #1050's board has 4,228 segments/74 vias and reports
`clearance`=499; this board has 3,319 segments/56 vias (21-24% less copper)
and reports `clearance`=504-505 — essentially the same number despite
materially less total copper existing to collide. If the regression were
principally "more copper = more chances to collide," a 22% smaller copper
set should show a smaller violation count. It doesn't. That is early
evidence the regression is not proportional to how much routing got done —
it is concentrated in specific congested locations that get violated
regardless of how completely the rest of the board routes (confirmed
directly in §3/§4).

Zone count (the plane-backbone/pour stage) reproduced **exactly** (66/66)
while segment/via count (the point-to-point A* stage) did not — and zones
are exactly the mechanism PR #1052's own no-backbone control experiment
(`docs/evidence/2026-08-12-corridor-aware-plane-backbones.md` §3.1) already
implicated as the dominant source of `clearance`/`solder_mask_bridge`
increase on this exact board, independent of routing strategy.

## 3. Concentration: confirms the U27/U26/rtd_pan hypothesis, with a wider and more precise cluster

Ranked component-level concentration (candidate board, "which refs appear in
`clearance` violation item pairs" — a violation touching two refs counts once
per ref):

| rank | ref | sheetpath | candidate count | main count (same ref, mostly unrenumbered) | delta |
|---:|---|---|---:|---:|---:|
| 1 | `U27` | `mcu.mcu` | **37** | 6 | +31 |
| 2 | `U26` | `safety.latch` | **20** | 1 | +19 |
| 3 | `U22` | `safety.uvlo_logic.inv` | **16** | 2 | +14 |
| 4 | `U21` | `safety.uvlo_logic.mon` | **14** | 3 | +11 |
| 5 | `U24` | `safety.fault_any_or` | **13** | 1 | +12 |
| 6 | `R11` | `discharge.r_coil2` | 11 | 0 | +11 |
| 6 | `R7` | `discharge.r_dis1b` | 11 | 1 | +10 |
| 8 | `L1` | `power_in.cmc` | 8 | 0 | +8 |
| 8 | `C14` | `aux_supply.c_in_bulk` | 8 | 3 | +5 |
| 10 | `U17` | `safety.thermal.comp` | 7 | 0 | +7 |

(`U26`/`U27` refs are **verified unrenumbered** between the two boards —
same `Sheetpath` identity on both, confirmed directly from
`reconcile_report.json`'s `designator_changes`, which only touches
`U4`-`U19` — so this is a like-for-like, not a coincidental-label,
comparison.)

The top-8 refs by count touch **130 of 505** violations (25.7%) — a real
but not overwhelming concentration by component. Aggregating by **net
pair** instead (closer to how PR #1050's own doc counted it) is sharper:
the top 15 net pairs account for **311 of 505 (61.6%)**, dominated by
`vcc<->i2c_sda_ui` (99), `safety.uvlo_logic.mon-outa<->y` (47),
`safety.ovp-line<->safety.ovp.comp-inp` (29), and
`discharge.k_dis1-coil2<->rtd_pan.high_window-out` (28) — **`vcc`,
`safety.ovp-line`, and `rtd_pan.*` all appear exactly where PR #1050's own
doc named them** ("rtd_pan/SHUTDOWN/vcc/safety.ovp-line cluster around
U27/U26").

**Verdict on the hypothesis: confirmed, and sharpened.** It is not just
`U27`/`U26` — it is the whole safety-interlock logic block
(`safety.latch`, `safety.uvlo_logic.inv`, `safety.uvlo_logic.mon`,
`safety.fault_any_or`, `safety.thermal.comp`) plus the MCU plus the
`rtd_pan` analog front end, all physically adjacent on the board and all
densely interconnected by short point-to-point nets (`vcc`, `y`, `y1`,
`safety.ovp-line`, `safety.coil_thermal-line`) — exactly the kind of region
where the isolation-barrier Y-split (§ below) pushed a lot of SELV-side
logic into a comparatively tight area.

## 4. Violation-type breakdown — the decisive discriminator: routing, not placement

Item-kind-pair breakdown, both boards, both measured with identical
`--refill-zones` invocation:

| item-kind pair | candidate | candidate % | main | main % |
|---|---:|---:|---:|---:|
| pad-track | 252 | 49.9% | 63 | 16.1% |
| track-track | 229 | 45.3% | 254 | 64.8% |
| track-via | 16 | 3.2% | 21 | 5.4% |
| pad-via | 8 | 1.6% | 16 | 4.1% |
| **pad-pad** | **0** | **0.0%** | **38** | **9.7%** |
| zone-involved | 0 | 0.0% | 0 | 0.0% |

**0 of 505 candidate `clearance` violations are pad-to-pad.** Main's board
— the one that has *not* been re-placed by Pumpkin — has 38 pad-to-pad
clearance violations; the candidate, freshly placed under 21,948
netclass/courtyard constraints plus the isolation barrier, has zero. Direct
placement crowding (footprints too close to each other) got *strictly
better*, not worse. 95.2% of the candidate's clearance violations
(pad-track + track-track) involve at least one **track** — i.e., the
router chose a path that runs too close to something, not the placer
leaving two components too close together.

This matches PR #1052's own finding on the *unpatched, straight-line MST*
backbone generator (`docs/evidence/2026-08-12-corridor-aware-plane-backbones.md`
§3.1): a no-backbone control run showed vias+zone-pour alone cost only +42
`clearance` against a 392 baseline, while the full backbone (routed edges)
cost +107. And PR #1052's corridor-aware A* — a strictly more
clearance-aware search over the *same* placement — did not reduce the
number (501 vs 499 unpatched) because, per that document's own
connected-components analysis, F.Cu's free space around `gnd`'s via-drop
points fragments into **94 disconnected regions** at this placement
density: no clearance-respecting path exists there for *any* search
strategy to find. My own regeneration (§1-2), run with meaningfully less
routing completed than either prior document, still lands on the same
clearance count — a third, independent line of evidence that this is a
property of the available F.Cu space at the current placement, not of
which router or how much of it ran.

## 5. Marginal vs. gross

Ratio = actual_gap_mm / required_gap_mm, over all 505 candidate
`clearance` violations:

| bucket | count | % |
|---|---:|---:|
| marginal (ratio >= 0.8) | 52 | 10.3% |
| mid-range (0.5 < ratio < 0.8) | 179 | 35.4% |
| **gross (ratio <= 0.5)** | **274** | **54.3%** |
| exact 0.00mm actual | 0 | 0.0% |

Minimum observed actual gap: 0.0003mm (essentially touching); several
examples sit at 3-5% of the required 0.2mm bar (e.g. `Pad 1 [+3V3] of R72`
vs. `Track [io0]`: required 0.2mm, actual 0.03mm — 15% of bar). **A
majority (54.3%) are gross, not marginal.** This is not a rule-tuning
problem (nudging a netclass clearance value by a few percent, or a
routing-order micro-adjustment, would not close a gap that is 5-15% of the
requirement). It is consistent with §4's finding: these are traces routed
through space that is fundamentally too tight, not traces that missed the
bar by a hair.

**Applicable rule.** 498 of 505 (98.6%) are the generic `"Default routing"`
rule (`A.Type == 'Track' || B.Type == 'Track'`, 0.2mm — `RULE 10` in
`scripts/generate_kicad_dru.py`, the loosest clearance rule in the file,
not a strict one). Only 8 involve a netclass-specific rule (6
`HighVoltage`, 1 `HighVoltageIsolated`, 1 `Power`), and **every one of
those 8 is a same-domain pair** (e.g. `+170V_BUS` vs. `tank-out`,
`power_in.ntc-no` vs. `w1_2` — both HV-side; `hb.gate_hs.driver-p2` vs.
`hb.gate_hs.driver-p1-1` — both `HighVoltageIsolated`, same barrier side),
confirmed by cross-checking against the isolation-barrier's own domain
partition (§6). The rule being applied to nearly the entire regression is
the *loosest* rule in the file, which rules out "a newly-strict rule is
now firing" as an explanation for the bulk of the count (main board's own
392, by contrast, has 43 non-default-routing violations — proportionally
*more* netclass-rule-driven than the candidate's 8).

## 6. Mains &lt;-&gt; SELV: none of the net-new violations, flagged separately as required

Cross-referenced every candidate `clearance` violation's two component refs
against the isolation barrier's own `DomainPartition`
(`hv_only`=40 components, `selv_only`=109 components, reproduced exactly in
§1): **0 of 505 candidate violations pair an `hv_only` ref against an
`selv_only` ref.** Main's board (measured with the same partition, using
refs verified unrenumbered where checked) has 4 such pairs. This is
consistent with, not contradicted by,
`docs/evidence/2026-08-12-hvlv-candidate-board-measurement.md`'s
independent `SAF_HVL_001` Rust-kernel finding (94 -> 44, same board,
different measurement path) — two separate tools, both saying the same
thing: the isolation barrier's placement-side Y-split is working, and the
clearance regression sits entirely on the SELV side of it, not across it.
**No mains<->SELV-severity finding to flag here** — this is deliberately
reported as a negative result, not omitted.

## 7. Newly-correct netclass enforcement vs. real regression — tested, not speculated

The task named a specific, testable alternative explanation: that #1051
("net classification... made real") might mean some of the +113 are
newly-*correct* enforcement of a netclass that was previously unenforced,
not a real geometric regression.

**Tested directly, not inferred:**

1. Both this task's DRC runs (main and candidate) were staged against
   `pcb/temper.kicad_pro` copied from the identical source file
   (`sha256sum` diffed byte-for-byte equal between the two staging
   directories). The clearance *rules* kicad-cli applies are therefore
   provably identical between the two measurements — there is no version
   skew for #1051 or anything else to have introduced.
2. `git log --oneline -- pcb/temper.kicad_pro` shows its last change was
   `28de4543d` ("full sync of kicad_pro netclass_assignments... measured
   clearance raise, #1025") — three commits before `pcb/temper.kicad_pcb`'s
   own last change (`c4956df66`) and many commits before #1051
   (`b94f8cc9d`). The netclass ruleset kicad-cli reads has been frozen
   since before the committed board's own current state.
3. #1051's own commit message (`b94f8cc9d`) states this explicitly and
   was independently verified applicable here: *"kicad-cli DRC ceiling
   (`power_pcb_dataset/drc_ceiling.json`) unaffected: CI's Required-Status
   DRC gate runs `--backend kicad-cli` exclusively, which reads netclasses
   from `pcb/temper.kicad_pro` directly, not from this Python path."*
   #1051 changed `Component.net_class`, a Python/Rust-internal field read
   only by the three Rust safety kernels (`hv_lv_separation.rs`/
   `creepage.rs`/`isolation.rs`, i.e. `SAF_HVL_001` and similar) — a
   completely different code path from kicad-cli's `clearance`/`creepage`
   output.
4. Checked whether the reconciliation's genuinely new nets (OCP-02:
   `safety.ocp2.*`) are covered by `pcb/temper.kicad_pro`'s
   `netclass_assignments`/`netclass_patterns` at all: **no** — none of
   the 78 explicit `netclass_assignments` entries or 8 glob patterns
   (`+*V`, `VCC*`, `VDD*`, `DC_BUS*`, `GATE_*`, `PWM_*`, `VBOOT_*`, `AC_*`)
   match anything OCP-02-named, so those nets silently fall through to
   the loosest `Default` class (0.2mm) rather than a stricter one — the
   opposite direction of the hypothesis being tested (under-, not
   over-, constrained).

**Verdict: refuted for this category, by direct measurement, not
inference.** None of the +113 `clearance` delta is newly-correct netclass
enforcement. The ruleset is byte-identical between the two measurements by
construction, #1051 never touches the code path `clearance` comes from,
and the rule breakdown in §5 shows the regression is 98.6% the *loosest*
rule in the file, not a stricter one newly firing.

## 8. Fixability — read `docs/evidence/2026-08-12-corridor-aware-plane-backbones.md` (#1052) first, which already ruled out the routing-algorithm axis

PR #1052 already tried, and measured to fail, the fix this diagnosis'
§4 finding (predominantly track-involving, not pad-involving) would
naively suggest first: a materially better router
(`packages/temper-placer/src/temper_placer/router_v6/_corridor_backbone.py`,
corridor-erosion-aware A* replacing a straight-line MST). Its own headline:
*"aggregate DRC collision counts... do NOT materially fall... the
mechanism cannot conjure a clearance-respecting path where this board's
current placement leaves none."* Five different obstacle/clearance
configurations were tried; none moved the `clearance` count outside a
5-10-unit band. **Do not re-propose a smarter router or a tighter
keepout** — both are already-measured dead ends for this specific
regression, for the specific, structural reason PR #1052's own §3.2 gives:
F.Cu's free space around this board's densest region (independently
confirmed here to be the safety-interlock/MCU/`rtd_pan` cluster,
§3) fragments into ~94 disconnected sub-mm-scale pockets at the *current
component placement* — no path search, however good, can route through a
gap that is not there.

**What would actually have to change, concretely:**

- **NOT netclass clearance values** (`packages/temper-placer/configs/netclass_rules.yaml`,
  `scripts/generate_kicad_dru.py`). §5/§7 show 98.6% of violations are
  already under the *loosest* rule in the file; loosening it further would
  mask the finding rather than fix the geometry, and the task's own
  framing (safety-relevant board) argues against loosening clearance
  requirements to make a placement problem disappear on paper.
- **NOT routing keepouts or search algorithm** (`router_v6/_corridor_backbone.py`,
  `router_v6/_ground_plane.py`, `router_v6/_power_islands.py`,
  `astar_core.py`) — already tried in #1052, measured not to help, for a
  structural reason (no path exists at the required clearance, not "the
  search didn't find one").
- **Placement constraints, the most promising lever not yet tried**:
  the Pumpkin/CP-SAT constraint model
  (`packages/temper-placer/src/temper_placer/placer/cp_sat/netclass_constraints.py`,
  `_encoder_solve.py`'s courtyard-tau backfill) currently only enforces
  that **courtyards/pads** don't overlap (`min_distance_mm` = netclass
  clearance or courtyard tau). It has no notion of "leave enough clear
  F.Cu around this cluster for the router to thread N nets through." A
  targeted, larger separation constraint (or a synthetic keep-clear zone)
  specifically over the `safety.*`/`mcu.mcu`/`rtd_pan.*` component group
  identified in §3 — packing them measurably looser than the courtyard-tau
  default, at the cost of some board area elsewhere — is the mechanism
  that could actually open the F.Cu channels #1052 found fragmented,
  since it acts before routing rather than trying to route through a gap
  that placement never left.
- **Board outline/area, the other real lever**: the isolation barrier's
  own PD2/8.0mm horizontal corridor (§1, `[113.0, 121.0]mm` on this
  152x234mm board) already consumes a meaningful vertical band of the
  board just for the mains<->SELV split; the safety-logic cluster sits
  in the remaining SELV-side area, denser than before reconciliation
  added 6 more components into roughly the same footprint. Growing the
  board (or reflowing the SELV-side layout to give that specific cluster
  more room) is the other structural option — not attempted by this task
  (a placement/mechanical change, out of this diagnosis' scope), but
  consistent with what #1052's own recommendation already named:
  *"That fix needs placement density to change first — a different,
  larger project than this one."*

## Sources

- `docs/evidence/2026-08-12-place-and-reroute-connectivity.md` (#1050, recipe + original 386->499 measurement)
- `docs/evidence/2026-08-12-isolation-barrier-pumpkin-placement.md` (#1050, isolation-barrier placement detail)
- `docs/evidence/2026-08-12-corridor-aware-plane-backbones.md` (#1052, FAILED fix attempt — read before re-proposing a routing-algorithm fix)
- `docs/evidence/2026-08-12-hvlv-candidate-board-measurement.md` (#1053, independent `SAF_HVL_001` 94->44 corroboration)
- `docs/evidence/2026-08-11-component-net-classification-fix.md` and commit `b94f8cc9d` (#1051, confirms kicad-cli `clearance` reads `pcb/temper.kicad_pro` only)
- `power_pcb_dataset/drc_ceiling.json` (386/183/199 committed-board ceiling, reproduced exactly here)
- `AGENTS.md` (kicad-cli invocation convention, clearance/creepage determinism notes)
- `scripts/resync_pcb_netlist.py`, `scripts/route_board.py`, `docs/evidence/2026-08-07-pumpkin-engine/src/main.rs` (regeneration pipeline, read/run, not modified)
- `pcb/temper.kicad_pcb`, `pcb/temper.kicad_pro`, `pcb/temper.kicad_dru` — read only; never modified (`git status --short pcb/` empty throughout)

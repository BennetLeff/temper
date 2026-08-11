# Creepage: rule audit, root-cause clustering, and a DRU-generator fix

**Date:** 2026-08-11
**Branch:** `fix/board-creepage-safety`
**Board:** `pcb/temper.kicad_pcb` unchanged by this PR — sha256
`6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64`
(commit `b11a78a5b`). This is a **pipeline fix** (`scripts/generate_kicad_dru.py`
only) — the board file is never edited.
**Tool:** `kicad-cli 10.0.5` (matches CI's pinned version,
`.github/docker/ci.Dockerfile`), via
`temper_placer.validation._drc_api.run_drc` (`--all-track-errors`,
single-thread-pinned), after regenerating `pcb/temper.kicad_dru` from
`scripts/generate_kicad_dru.py` — the same protocol every prior
`drc_ceiling.json` `_march` entry uses.

## Summary

- **The creepage rule's headline figure (8.0mm, PD2, IEC 60335-1 Table 17
  row iv reinforced) is internally consistent and well-derived** — but it
  rests on a Pollution-Degree-2 exception (a sealed, gasketed PCB
  compartment isolated from the coil/heatsink forced-air path) that **this
  board's as-built mechanical design does not have**. This was already
  found and flagged as an open, unresolved owner decision on 2026-08-02
  (`docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md`) and remains
  unresolved today (no compartment geometry, no keepout zone, no commit
  touching `docs/CHASSIS_AIRFLOW_DESIGN.md`/`docs/ASSEMBLY_GUIDE.md`/
  `docs/ENVIRONMENTAL_SPEC.md` since). **If that decision is ever resolved
  honestly against the current mechanical design, the correct bar is
  PD3/12.6mm, not PD2/8.0mm — which would *raise*, not lower, the true
  violation count.** This PR does not touch that decision (a full-tree
  retarget with its own re-solve wall, already investigated and found to
  make several isolators infeasible without a redesign) — it is surfaced
  here because it means today's 186/188 ceiling is very likely an
  *undercount* of the board's real IEC 60335-1 exposure, not an overcount.
- **The creepage count's run-to-run nondeterminism (185–187 across every
  prior 120+ sample measurement) is already fully explained, not a
  loose end.** `docs/evidence/2026-08-04-drc-measurement-determinism.md`
  traced it to KiCad's own creepage-check `std::set<std::pair<const
  BOARD_ITEM*, const BOARD_ITEM*>>` pair-dedup container, keyed and
  ordered by raw process pointer values — an upstream defect (KiCad issue
  #20048) with no flag, thread-pin, or post-processing that reaches it
  from a kicad-cli caller. Reproduced directly in this session (below).
- **Root cause of a real, fixable slice of the 186–188: `scripts/
  generate_kicad_dru.py`'s DRU rule generator has a same-side exclusion
  gap.** `elec/domain_manifest.yaml` (the hand-reviewed domain SSOT) and
  `packages/temper-placer/configs/netclass_rules.yaml`'s own commentary
  both establish that `GATE_HS`/`GATE_LS` (netclass `GateDriveHV`) and the
  UCC21550 gate driver's own secondary bias nets (netclass
  `HighVoltageIsolated`) are members of the **same HV domain** as
  `HighVoltage`/`ACMains` — they float with the switch node, one gate
  resistor downstream, not a third domain and not the SELV side of the
  barrier. But three of the generator's five creepage-bearing rules ("AC
  Mains to LV", "HV to LV", "HighVoltageIsolated to LV") never excluded
  `GateDriveHV` from their "everything else is LV" condition, and "HV to
  LV" never excluded `HighVoltageIsolated` either — so pairs that are
  genuinely on the *same* side of the mains/SELV barrier were being
  charged the full 8.0mm reinforced creepage figure meant for a real
  cross-barrier boundary. **This is a false positive against the
  project's own domain model, not a cosmetic DRC nit and not a real
  shock-hazard pair** — both sides float at the same potential relative to
  `SW_NODE`.
- **Fixed in `scripts/generate_kicad_dru.py`** (the pipeline, not the
  board): added the missing `GateDriveHV`/`HighVoltageIsolated`
  same-side exclusions to the three affected rules, and two new rules
  (`GateDriveHV to ACMains`, `GateDriveHV to HighVoltageIsolated`)
  supplying the correct functional clearance figure for the newly-exempt
  pairs — reusing the number (0.5mm) already accepted for the sibling
  `GateDriveHV`-`HighVoltage` pair (`RULE 6`), not a new value.
- **Measured, 40 samples, kicad-cli 10.0.5:** creepage **185–187 → 169–171**
  (ceiling 188 → **172**, −16), clearance **368 → 365, fully deterministic
  on both sides** (a bonus improvement, not the target category — the same
  rule gap was also over-tightening a `clearance` constraint on these
  pairs). **Zero other category moved** — `copper_edge_clearance`,
  `hole_clearance`, `hole_to_hole`, `annular_width`, `courtyards_overlap`,
  `drill_out_of_range`, `via_diameter`, `tracks_crossing`,
  `shorting_items`, `track_width`, `solder_mask_bridge` are byte-identical
  before/after. No regression in any category, including the two
  (`shorting_items`, `track_width`) another agent currently owns.
- **The residual 169–171 is not a handful of repeat offenders — it is a
  systemic, board-wide placement/routing interleaving problem**,
  independently corroborated by three prior, unrelated investigations
  (below). A second, larger, *not-shipped* finding (a real netclass
  mis-assignment for `ac_l`/`ac_n`/`SW_NODE`/`+170V_BUS` in
  `pcb/temper.kicad_pro`) is documented in §5 — it is directionally
  correct but **raises** creepage and clearance when applied, so it is
  reported, not landed, per the "never raise a ceiling to make a gate
  pass" / "a fix that raises another category is a regression" rules.

---

## 1. Is the creepage rule correct? — yes in arithmetic, no in mechanical prerequisite

`scripts/generate_kicad_dru.py`'s `HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD2_MM
= 8.0` derivation is correct IEC 60335-1 Table 17 row iv (>250–400V working
voltage, material group IIIa/IIIb, reinforced = 2× basic), and is aligned
with every other enforcement point in the tree: the REQ-SAFE-01 validator
matrix (`packages/temper-placer/src/temper_placer/requirements/validators/
clearance.py:302-333`, aligned to PD2 since commit `9a3233a60`,
2026-07-30), `isolation_constants.MIN_BARRIER_WIDTH_MM = 8.0`, the CP-SAT
placer's corridor/keepaway margins (both derived from the same constant),
`elec/src/constraints.ato`, and the PCL solver config — all 8 enforcement
points named in `docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md` §3.2
agree at 8.0mm, confirmed unchanged today (`clearance.py:302-333` still
reads 8.0/4.0 reinforced/basic; `isolation_constants.py:45` still reads
8.0; `git log --since=2026-08-02` on the CHASSIS_AIRFLOW/ASSEMBLY_GUIDE/
ENVIRONMENTAL_SPEC docs and on the board for a `keepout`/compartment
addition is empty — `grep -c keepout pcb/temper.kicad_pcb` is still `0`).

**The unresolved half:** PD2 is only a legitimate exception to IEC
60335-2-6 cl. 29.2's PD3-by-default rule for cooking appliances if a real,
sealed, gasketed PCB compartment separate from the coil/heatsink forced-air
duct exists and is verified. `docs/evidence/2026-08-01-pd2-enclosure-
legitimacy.md` (2026-08-02, still the most recent word on this) found the
committed design has **none** of that: no vent/cutout/compartment geometry
on the board outline, no cover/gasket/partition part or drawing anywhere in
the repo, `docs/CHASSIS_AIRFLOW_DESIGN.md` describes forced air moving
"bottom chassis intake → 80mm fan → IGBT-heatsink duct → rear exhaust"
across the same cavity the PCB sits in, and the "gasketed PCB compartment"
exists only as a release-time assembly *instruction*
(`docs/ASSEMBLY_GUIDE.md` Phase 4.2: *"Install the covered, gasketed PCB
compartment... Do not release the assembly as PD2 if the cover, gasket, or
partition is absent or damaged"*) — never a designed, committed artifact.
That document's own recommendation — build the compartment, or explicitly
retarget to PD3/12.6mm — is still open nine days later; nobody has picked
an option. **This PR does not resolve it**: retargeting the whole tree to
12.6mm is a coordinated, all-8-points-at-once change with its own
already-measured wall (`docs/evidence/2026-07-30-pd3-inter-component-
creepage-board-expansion.md`: 196 violating HV↔SELV pad pairs at 12.6mm on
this board's geometry, and several isolators — including `K1`, `T1`, `U3`,
`U7` — landing in an infeasible set even after substitution), squarely a
placement-architecture decision, not a DRU-generator bugfix. It is
reported here, prominently, because **not knowing this makes 186/188 read
as "the" safety number when it is very likely a floor, not a ceiling** on
a mains-connected board a person touches.

---

## 2. Why creepage is nondeterministic — already explained, reproduced here

`docs/evidence/2026-08-04-drc-measurement-determinism.md` (2026-08-04)
traced creepage's run-to-run scatter to KiCad's own `DRC_TEST_PROVIDER_
CREEPAGE`, which deduplicates reported violation pairs through
`std::set<std::pair<const BOARD_ITEM*, const BOARD_ITEM*>> m_reportedPairs`
— a container ordered by **raw pointer value**, which is not reproducible
across process invocations. Pinning kicad-cli's worker thread pool to 1
(the fix that stabilized `clearance` and `shorting_items` in the same
investigation) does nothing for creepage, because the defect does not need
two workers — it is a single-threaded ordering artifact of the dedup
container itself. This is a known, filed upstream bug: KiCad issue
[#20048](https://gitlab.com/kicad/code/kicad/-/issues/20048), reported
against 9.0.0, still reproducing on 10.0.5. **No kicad-cli invocation,
flag, or post-processing reaches it** — a pair suppressed by the
pointer-ordered dedup upstream never reaches the CLI's JSON output at all,
so canonicalizing our side cannot recover it.

Reproduced directly in this session: the baseline band (185–187, `n=30`,
this session) and the post-fix band (169–171, `n=40`, this session) are
each internally scattered by exactly the same mechanism, and — this is the
useful confirmation — **the scatter's width is unchanged by this fix**
(baseline range width 2, post-fix range width 2; the whole band shifted
down by exactly 16, the count of pairs this fix statically removes from
ever being candidates). That is consistent with a fixed-size dedup-ordering
artifact riding on top of a now-smaller true candidate set, not a new or
different instability introduced by the change.

No action taken on this in this PR — `drc_ceiling.json`'s "observed max +
1 headroom" convention for `creepage` remains the correct response to an
upstream, unreachable defect. The only structural fix
(`docs/evidence/2026-08-04-creepage-rust-backend-survey.md`'s
recommendation to move `creepage` measurement to the in-repo Rust DRC
backend) is out of scope here — a real backend-equivalence project, not a
DRU-rule fix.

---

## 3. Root-cause clustering of the 186 (baseline, this session)

Measured against the *unmodified* generator (`git stash` of this PR's one
file, single sample, `n=1` — categories other than `creepage` are
established-deterministic per the 130-sample 2026-08-07 record cited in
`drc_ceiling.json`, so a single sample suffices to corroborate them; the
nondeterministic-band claims below are the `n=30`/`n=40` measurements):

- **Not a handful of repeat offenders.** The 186 baseline violations touch
  **~85 distinct components** and **~150 distinct net pairs**; no net pair
  repeats more than twice. The single most-implicated component (`U7`, the
  UCC21550 isolated gate driver) accounts for 16 of 186 (8.6%) — a
  component whose whole *job* is straddling the barrier, so a high count
  there is expected, not anomalous.
- **Severity is loaded toward near-zero margin, not marginal misses.** 43
  of 186 (23%) measure under 0.5mm actual creepage distance (many at
  exactly 0.0000mm — literally touching or crossing copper), 61/186 (33%)
  under 1mm, 123/186 (66%) under 4mm (half of the 8.0mm requirement).
- **75% involve at least one already-routed track** (a `Track [...] on
  F.Cu, length NN mm` item, not two bare pads) — meaning the majority
  cannot be resolved by moving a component alone; the copper that violates
  is already committed to a specific path by the router. Only 47/186 (25%)
  are pure pad-to-pad pairs, and even those cluster in the same
  already-saturated neighborhoods (`U7`/`R20`/`R23`/`R30`/`C17`) that
  independent placement-density work already found have no free space to
  move into (§4).
- **By rule:** 155 "HV to LV", 31 "HighVoltageIsolated to LV" — i.e. every
  one of the 186 is a genuine mains/HV↔SELV boundary check by rule
  *category*; the false positives found here are about which *net pairs*
  that category wrongly includes (same-domain pairs), not about the rule
  category being wrong wholesale.
- **38 of 186 (20%) are HV↔HV pairs by the project's own domain model**
  (`elec/domain_manifest.yaml`) — i.e., same side of the one barrier that
  matters, charged the reinforced cross-barrier figure anyway. Broken down
  by KiCad netclass pair and DRU rule that fired:

  | netclass pair | rule | count |
  |---|---|---:|
  | `Default` × `HighVoltage` | "HV to LV" | 18 |
  | `HighVoltage` × `HighVoltageIsolated` | "HV to LV" | 9 |
  | `GateDriveHV` × `HighVoltage` | "HV to LV" | 5 |
  | `Default` × `HighVoltageIsolated` | "HighVoltageIsolated to LV" | 4 |
  | `GateDriveHV` × `HighVoltageIsolated` | "HighVoltageIsolated to LV" | 2 |

  This PR fixes the middle three rows (16 of the 38) — the `GateDriveHV`
  and `HighVoltage`↔`HighVoltageIsolated` same-side exclusion gaps in the
  DRU generator itself. The `Default`-paired rows (22 of the 38) are a
  *different* root cause — a real netclass-assignment defect in
  `pcb/temper.kicad_pro`, not a DRU-rule gap — documented but **not fixed**
  in this PR; see §5 for why.

---

## 4. Is the residual (169–171) a placement/routing problem? — yes, independently corroborated three times

Three prior, unrelated investigations converge on the same structural
finding, none written for this task:

1. **No single straight line separates this board's HV and SELV pads.**
   `origin/safety/mains-selv-isolation-barrier` (commit `645154b7`, cited
   in `docs/evidence/2026-08-08-selv-hv-pour-barrier-drc-spike.md` §1): an
   exhaustive search over axis-aligned barrier positions and all 180° of
   orientation still misclassifies 28–32% of pads, because HV/SELV pad
   centroids are only 5.9mm apart on a 152×234mm board.
2. **The routed copper has already consumed the space a barrier corridor
   would need.** `docs/evidence/2026-08-04-r24-barrier-resolve.md` §6:
   *"as routed, copper covers 31,087 of 35,568 mm² (87.4%), and all 101 HV
   copper pads have no admissible HV-side space at all. No placement
   change can fix that... a keepout must be placed before the pour, not
   carved out after."* (The one placement move that document did land —
   `R24` to `(81.0, 21.5)`, for barrier-*line* admissibility, a
   board-architecture precondition unrelated to the per-pair DRC creepage
   check — is confirmed still in place on the current board and,
   consistent with that document's own measurement, changes nothing about
   the DRC creepage count on its own.)
3. **A real-geometry isolation-barrier check finds the same thing from a
   third angle.** `docs/evidence/2026-08-08-selv-hv-pour-barrier-drc-spike.md`
   §4e: running the (unmerged, unadopted) `IsolationBarrierCheck` against
   the real board's 96 zones with the `origin/safety/mains-selv-isolation-
   barrier` candidate line reports 398 crossing/near-miss violations on
   *copper geometry* — independent corroboration, via polygon intersection
   rather than pad centroids, that HV and SELV copper is interleaved
   across whichever side of any single candidate line the other domain
   occupies.

This session's own data is consistent with all three: the residual 171 is
smeared, near-zero-margin, majority-already-routed — exactly the signature
a genuinely interleaved layout with no HV-side headroom left in the pour
would produce, not a small number of correctable placements. **Fixing the
residual for real requires either (a) a keepout-established-before-the-
pour re-route — a router-architecture project, not a DRU or placement
change, and one that would necessarily rewrite the copper `shorting_items`/
`track_width` currently owned by a concurrent workstream on this board — or
(b) a substantial HV/SELV re-placement, already attempted at comparable
scope (`docs/evidence/2026-08-04-r24-barrier-resolve.md` §3's "control"
re-solve moved 167 refs by 7.07 m and was not written specifically because
the churn was judged worse than the gain).** Neither is attempted in this
PR — see "Boundaries" in the task brief and the concurrent-agent conflict
already hit once during this session (§6).

---

## 5. A real, larger, *not-shipped* finding: `pcb/temper.kicad_pro` netclass mis-assignment

The 22 `Default`-paired rows in §3's table trace to a genuine defect:
`pcb/temper.kicad_pro`'s `net_settings.netclass_assignments` has stale or
wrong-case entries for `ac_l`/`ac_n` (assigned under `"AC_L"`/`"AC_N"` —
uppercase, which never matches the real, lowercase net names — KiCad/JSON
key lookup is exact-string, and `packages/temper-placer/src/temper_placer/
core/design_rules.py`'s `TEMPER_NET_ASSIGNMENTS` — the Python-side SSOT —
already has these correct at lines 242-243/251/255) and no entry at all
for `SW_NODE` or `+170V_BUS` (present in `design_rules.py` at lines
251/255 but absent from `kicad_pro`). All four are declared members of the
`HV` domain in `elec/domain_manifest.yaml`. Because `scripts/generate_
kicad_dru.py`'s rules key on `NetClass`, and these four nets resolve to
KiCad's `Default` netclass (0.2mm baseline, no creepage protection at
all), they are simultaneously (a) wrongly subjected to the 8.0mm
reinforced creepage check against their own same-domain neighbors when
paired with a properly-classified `HighVoltage`/`HighVoltageIsolated` net
(the 22 rows above), and (b) **under-protected** against genuinely LV/SELV
neighbors they were never checked against at all, because a `Default`-vs-X
pair as the *A* side never matches any of Rules 2/4/4b's
`A.NetClass == 'ACMains'`/`'HighVoltage'`/`'HighVoltageIsolated'`
conditions.

**Correcting this (verified in an isolated scratch measurement, not
shipped):** adding the four correctly-cased/named entries to `pcb/
temper.kicad_pro`'s `netclass_assignments` — `ac_l`/`ac_n` → `ACMains`,
`SW_NODE`/`+170V_BUS` → `HighVoltage`, matching `design_rules.py` exactly
— measured **creepage 171 → 183 (+12) and clearance 365 → 372 (+7)** on
top of this PR's DRU fix. This is the expected shape of "the rule was too
lax, hides real ones" (per the task's own framing): fixing the
misclassification removes the 22 same-domain false positives but *reveals*
more genuine, previously-invisible violations where `ac_l`/`ac_n`/
`SW_NODE`/`+170V_BUS` sit too close to real LV/SELV copper that was never
checked against them before. **Net effect is a regression on two
categories, one of them outside this PR's scope** — per the task's own
rule ("a fix that cuts creepage but raises another category is a
regression") and "never raise a ceiling to make a gate pass," this is
**not landed**. `PWR_RTN` (also `Default` in `kicad_pro`, also `HV`-domain
in the manifest, and the fifth net this class of defect touches) is
**deliberately left alone entirely** — its correct classification is
`GND`, not `HighVoltage` (`design_rules.py:345`), and `scripts/check_hv_
netclass_coverage.py`'s own module docstring already flags `PWR_RTN`
as a known, open, human-decision-required case with "an order-of-magnitude
larger blast radius" than the others, explicitly out of that gate's
enforced scope — this PR does not relitigate it.

This is reported, not fixed, as a genuine safety-relevant finding for a
human to schedule: it means the true, fully-correctly-classified creepage
picture on this board is at minimum 183 (measured), not 171 — a `+12`
gap this PR's fix does not and should not paper over by silence, even
though shipping it would move the ceiling backward.

---

## 6. A process note: worktree contention with a concurrent research agent

During this session, a research sub-agent spawned to synthesize prior
evidence docs was found to have live write access to this same worktree
(not the isolated fork sandbox its tool contract implies) and, on its own
initiative, made two uncommitted edits outside its assigned read-only
scope: once to `packages/temper-placer/configs/netclass_rules.yaml`
(a `HighVoltageIsolated.creepage_mm` placer-hint correction, independently
plausible but unverified by this session and out of scope for a DRC-count
fix — that config value is explicitly inert, gated behind an unset
feature flag), and once again after being told to stop and having the
first edit reverted. Both were reverted before landing; neither is part of
this PR. The task's principal (this session's own launcher) later
confirmed a second, legitimate concurrent agent is working the same board
for `shorting_items`/`track_width` and resolved file ownership explicitly.
Recorded here in case a reviewer notices `netclass_rules.yaml` was touched
and reverted in this branch's working history — it is not part of the
diff and was never intended to be.

---

## 7. Measured before/after — all categories

40 samples, `kicad-cli 10.0.5`, `--all-track-errors`, DRU regenerated
before each run, single-thread-pinned (`temper_placer.validation._drc_api.
run_drc`'s standard protocol), board unchanged (`pcb/temper.kicad_pcb`
sha256 `6928b7c8...50544b64` throughout):

| category | before | after | Δ |
|---|---:|---:|---:|
| `creepage` | 185–187 (ceiling 188) | **169–171 (ceiling 172)** | **−16** |
| `clearance` | 368 (deterministic) | **365 (deterministic)** | **−3** |
| `copper_edge_clearance` | 10 | 10 | 0 |
| `hole_clearance` | 105 | 105 | 0 |
| `hole_to_hole` | 3 | 3 | 0 |
| `annular_width` | 4 | 4 | 0 |
| `courtyards_overlap` | 11 | 11 | 0 |
| `drill_out_of_range` | 4 | 4 | 0 |
| `via_diameter` | 4 | 4 | 0 |
| `tracks_crossing` | 1 | 1 | 0 |
| `shorting_items` | 199 | 199 | 0 |
| `solder_mask_bridge` | 154 | 154 | 0 |
| `track_width` | 199 | 199 | 0 |
| **error total** | 1247–1249 | **1228–1230** | **−19** |
| all 9 warning categories | 489 (stable) | 489 (stable) | 0 |

`copper_edge_clearance`/`hole_clearance`/`hole_to_hole` (this PR's other
three nominally-assigned categories) are unchanged: their violations are
real physical routing/placement proximity defects (a via/track too close
to the board edge; two drilled holes 0.28–0.30mm apart against a 0.4995mm
minimum) — not DRU-rule-generator bugs, and fixing them means touching
`pcb/temper.kicad_pcb`'s routed geometry, which is out of this PR's
scope (pipeline-only, and overlapping the concurrently-owned routing
workstream). No fix is claimed for them here.

---

## Files

- Fix: `scripts/generate_kicad_dru.py` (three rule-condition exclusions,
  two new same-side rules)
- This document
- Cited, pre-existing (unmodified by this PR):
  `docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md`,
  `docs/evidence/2026-08-04-drc-measurement-determinism.md`,
  `docs/evidence/2026-08-04-creepage-rust-backend-survey.md`,
  `docs/evidence/2026-08-04-r24-barrier-resolve.md`,
  `docs/evidence/2026-08-08-selv-hv-pour-barrier-drc-spike.md`,
  `docs/evidence/2026-07-30-pd3-inter-component-creepage-board-expansion.md`,
  `scripts/check_hv_netclass_coverage.py`,
  `elec/domain_manifest.yaml`,
  `packages/temper-placer/configs/netclass_rules.yaml`,
  `packages/temper-placer/src/temper_placer/core/design_rules.py`

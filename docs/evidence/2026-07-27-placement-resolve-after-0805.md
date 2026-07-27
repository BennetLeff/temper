# Re-establishing the 0-violation domain-clearance result after r_avdd_top's 0603→0805 footprint change

**Date:** 2026-07-27
**Scope:** `pcb/temper.kicad_pcb` (resynced + re-solved). No `elec/src/*.ato` changes
(parts settled, per task constraint). Driver scripts used to run the resync/solve/audit
were scratch files under `/private/tmp/.../scratchpad/`, not committed (this doc reports
their exact invocations and output instead).

**Base:** worktree started 218 commits behind and 4 ahead of
`docs/methodology-loop-discipline` (the 4 "ahead" commits were a stale
squash-merge + auto-generated chore commits, not unique work — same pattern
documented in the two prior 2026-07-27 evidence docs). Fixed via repoint,
not rebase: `git fetch origin && git checkout -B <branch>
origin/docs/methodology-loop-discipline`. `scripts/assert-base.sh
docs/methodology-loop-discipline` confirmed exit 0 (HEAD `b2899b2a`) before
any implementation.

---

## 0. Why this task exists

`r_avdd_top` (the TPS3700 rail-monitor divider's top resistor,
`rtd_pan.r_avdd_top` in `elec/src/modules.ato`) moved from Panasonic ERA-3A
(0603) to ERA-6A (0805) on 2026-07-27, per
`docs/evidence/2026-07-27-era-resistor-resolution.md` — the 0603 series
does not stock the 619 kΩ decade at all; only the 0805 (ERA-6A) family
does. `elec/src/modules.ato` already carried the explicit footprint
override (`r_avdd_top.footprint = "Resistor_SMD:R_0805_2012Metric"`,
verified present at lines 1710–1713) — that part of the fix predates this
task and was not touched here.

The domain-clearance CP-SAT solve that had previously reduced
`pcb/temper.kicad_pcb` from 22 → 0 REQ-SAFE-01 violations
(`docs/evidence/2026-07-27-domain-clearance-constraint.md`) ran against the
*old* 0603 footprint. An 0805 courtyard is larger, so that 0-violation
result's provenance no longer matched the current footprint until
re-derived. This doc re-derives it.

---

## 1. Falsifier (stated before starting) and whether it fired

**Falsifier:** "The re-solve is unnecessary if the 0805 courtyard is
smaller than the clearance margin already applied [to r_avdd_top's
domain-crossing pairs]."

**Checked directly, two ways, before touching the board:**

1. **Is `r_avdd_top` (R45) even party to a domain-clearance constraint?**
   Generated the current constraint set
   (`generate_domain_clearance_constraints`) against the real board and
   filtered for R45: **0 of 7843 constraints involve R45.** R45's two nets
   are `vcc` (an RTD-module-local bias rail, net code 75 in
   `elec/build/default.net`) and the micro-net
   `rtd_pan.rail_monitor-ina_p` — neither is in
   `_real_board_fixture.py`'s `_NET_DOMAINS` classifier (`gnd`, `+15V`,
   `+3V3`, `ZCD_ISO`, `+170V_BUS`, `PWR_RTN`, `DC_BUS_RTN`, `zcd`, `ac_l`,
   `ac_n`). R45 has never been a domain-crossing pair member, so its
   courtyard growing cannot introduce a *new* domain-clearance violation —
   this is a stronger and more direct statement than comparing slack to
   courtyard growth (there is no margin to compare against; the pair set is
   empty).
2. **Direct measurement, before any re-solve:** ran
   `verify_iec60335_compliance` against the resynced-but-not-yet-resolved
   board (old, unmoved CP-SAT positions + the new 0805 footprint already
   applied by the resync) — **`passed=True, error_count=0, warning_count=0`,
   127/127 components matched.** Confirms (1) empirically: the footprint
   growth alone did not regress the safety-validator result.

**Verdict: for r_avdd_top specifically, the falsifier holds** — the
0-violation *safety-validator* result was never actually put at risk by
this footprint change, because r_avdd_top was never in a checked pair.

**This did not mean "stop."** The mandatory resync (task step 1, needed
regardless of r_avdd_top, per six other part changes since the last
resync) also added one brand-new component absent from the previously
solved board: `safety.fault_or3` (U25, a `SN74HC4075DR`, added because the
current netlist has one and the old board didn't). The resync — correctly,
per its own documented contract — placed it in an out-of-outline staging
position, **absolute `(20.0, 272.75)`**, against a real board outline of
`(20,20)`–`(172,254)` (origin `(20,20)`, size `152×234`): **18.75 mm past
the bottom edge.** That is not a valid, fabricable placement irrespective
of r_avdd_top, so **a re-solve was necessary anyway** — just not for the
reason the falsifier as literally framed was testing. Both things are
reported plainly rather than picking the version that makes the falsifier
look more decisive than it was.

---

## 2. Step 1 — resync (`scripts/resync_pcb_netlist.py`)

Ran dry-run first, then for real (both against
`elec/build/default.net`, itself rebuilt fresh via `make netlist`, 76/76
assertions passed, exit 0):

```json
{
  "netlist_components": 170, "old_board_footprints": 169, "new_board_footprints": 170,
  "kept_count": 168, "footprint_swapped_count": 1, "added_count": 1, "removed_count": 0,
  "designator_changes": [["safety.latch","U25","U26"], ["mcu.mcu","U26","U27"]],
  "footprint_swapped": [["rtd_pan.r_avdd_top","R45",
      "Resistor_SMD:R_0603_1608Metric","Resistor_SMD:R_0805_2012Metric"]],
  "added": [["safety.fault_or3","U25"]],
  "removed": [], "moved_count": 0, "moved": [], "net_count": 165
}
```

Matched by `Sheetpath` module-instance identity, per the tool's contract
(not by reference designator — two designators were reassigned in this
same pass, `U25`→`U26` and `U26`→`U27`, exactly the kind of collision the
task warned about).

**Confirmed the 0805 footprint reached the board** — direct read of
`pcb/temper.kicad_pcb` after the resync, ground-truthed with `awk` (not
just the tool's own self-report):

```
(footprint "Resistor_SMD:R_0805_2012Metric" ...)
  (property "Reference" "R45")
  (property "Footprint" "Resistor_SMD:R_0805_2012Metric")
  (property "Sheetpath" "rtd_pan.r_avdd_top")
  (fp_rect (start -1.68 -0.95) (end 1.68 0.95) (layer "F.CrtYd") ...)   ; was (-1.48 -0.73)/(1.48 0.73)
  (pad "1" ... (net 159 "vcc"))
  (pad "2" ... (net 101 "rtd_pan.rail_monitor-ina_p"))
```

Board footprint count: **169 → 170** (168 kept + 1 footprint-swapped + 1
added). Segments/vias/zones stayed **0/0/0** both before and after (no
routing exists yet; out of this task's scope).

---

## 3. Step 2 — re-solve (`solve_placement`, domain-clearance constraints)

**Constraint generation:** `generate_domain_clearance_constraints` against
the resynced real board: **7843 constraints** (up from the prior pass's
7715 — tracking `matched_components_in_placement` going 126/126 → 127/127
now that `U25`/`fault_or3` resolves to a classified net). `R45` confirmed
absent from all 7843 (§1).

**Solve invocation:** `solve_placement(netlist=..., board=...,
extra_constraints=domain_constraints, timeout_ms=120_000, seed=0)` — no
other PCL constraints loaded (`configs/pcl/temper_production.yaml` is
still stale against the current netlist, same scope decision the prior
R24 pass made and documented in its §7.1; re-authoring it is a separate,
uncommitted follow-up, not part of this task).

**Result:**

```
Solver status: optimal   solve_time_ms=33526   wall=33.5s
Placed refs: 170 / 170
components_updated=170  components_skipped=0
```

`status=optimal`, 170/170 placed, well under the 120s timeout budget
given (comparable to the prior pass's 27.6s on 169 components / 7715
constraints — the modest increase tracks the +1 component / +128
constraints). **Feasibility in 152×234mm confirmed — the falsifier-analog
"infeasible/unknown" outcome from the prior pass's own checklist did not
fire again.**

**Write-back:** `solve_placement()` returns positions in the CP-SAT
model's local `(0,0)`-based frame; `write_placements_to_pcb()` expects
absolute KiCad coordinates. This board's origin is `(20, 20)` (confirmed:
`parse_kicad_pcb(...).board.origin == (20, 20)`), and — as the prior R24
evidence doc found and flagged as an unfixed latent bug —
`cli/__init__.py`'s `optimize --no-loop` path does **not** apply this
offset. Rather than routing through that known-buggy CLI path, the
solve/write driver used here applies `board.origin` explicitly before
constructing each `PlacementUpdate` (the same workaround the prior pass
used; the CLI bug itself remains unfixed, out of scope here too — see §6).

**Sanity-checked directly** (not just trusted from the write result):

- `U25` (`fault_or3`): pre-resolve `(20.0, 272.75)` (18.75mm past the
  board's bottom edge) → post-resolve **`(25.08, 213.14, 270°)`**,
  comfortably inside `(20,20)`–`(172,254)`.
- `R45` (`r_avdd_top`): pre-resolve `(31.88, 235.57)` → post-resolve
  **`(67.58, 222.57, 180°)`**, also inside bounds.
- **All 170/170 components moved** between the pre- and post-resolve
  board (re-parsed and diffed both files directly) — this was a fresh,
  independent CP-SAT solve with no warm-start/hint positions, so the
  entire layout is a new solution, not an R45/U25-only patch. Routing
  state is unaffected either way (0 segments/vias/zones before and
  after — this task is placement-only).

---

## 4. Step 3 — R24 post-solve audit (`audit_domain_clearance`)

Regenerated the 7843 domain-clearance constraints fresh against the
resolved board, then recomputed real Euclidean center-to-center distance
from the *solved, written* absolute coordinates (not the solver's own
"optimal" claim) for every one:

```
constraints audited (candidates): 7843
AUDIT mismatches: 0
```

**0 mismatches across 7843 constraints.** This is the check the task
named as mattering most — it does not trust CP-SAT's own status, it
recomputes `math.dist` from the coordinates actually written to
`pcb/temper.kicad_pcb`.

---

## 5. Before / after violation counts

| Measurement | Before (resynced, pre-resolve; old positions + new 0805 footprint) | After (resolved + rewritten board) |
|---|---|---|
| `verify_iec60335_compliance` | `passed=True, error_count=0, warning_count=0` | `passed=True, error_count=0, warning_count=0` |
| `matched_components_in_placement` | 127/127 | 127/127 |
| Domain-clearance constraints generated | 7843 | 7843 (regenerated fresh, same count) |
| R24 audit mismatches | not applicable (no solve to audit yet) | **0 / 7843** |

**0 → 0.** The safety-validator count never actually regressed (§1) — but
report this precisely, not as "nothing needed to change": the *placement*
was not valid before the re-solve regardless (U25 off-board, §1), and the
re-solve is what makes the written board fabricable, even though it
happens not to have moved the REQ-SAFE-01 error count.

---

## 6. Test suite and gates

| Check | Result |
|---|---|
| `make netlist` | **76/76 assertions PASSED**, exit 0 |
| `tests/requirements/safety/test_clearance.py` + `test_isolation.py` + `tests/placer/cp_sat/test_domain_clearance.py` | **67 passed, 0 failed** |
| `test_temper_board_clearance_compliance` | **PASSED** (normal assertion, not xfail; guard `assert matched_components_in_placement > 0` present and satisfied — 127 > 0, `tests/requirements/safety/test_clearance.py:512`) |
| `scripts/check_domain_partition.py` | **exit 0** — 0 domain crossings, 0 isolator-barrier breaches, 0 protective-impedance chain defects, over 165 compiled nets / 170 components, 39 declared nets / 2 domains / 10 isolators checked |
| `scripts/capacity_budget_gate.py` | **exit 0** — 0 defects (3 packages / 165 nets / 36 pins / 27 SET-path inputs inspected) |
| `scripts/mpn_fabrication_gate.py` | **exit 0** — **0 new violations** (120 parts inspected, 10 pre-existing allowlist entries, 17 unchecked-prefix MPNs reported not silently passed) — stays green, not regressed |
| `test_production_board_drc_regression` (unrelated pre-existing ratchet, bonus check) | **PASSED** (kicad-cli DRC on the re-solved board) |

`test_production_board_routing_drc_regression` (the companion routing
variant of the bonus DRC check) was started but deliberately stopped
before completion — it requires actual routed copper, which is out of
this task's scope (board is 170 footprints / 0 segments / 0 vias / 0
zones both before and after, per the task's own framing of "placement
only"). Its result is UNVERIFIED.

---

## 7. What remains UNVERIFIED / out of scope

- **`test_production_board_routing_drc_regression`** — stopped before
  completion (§6); pass/fail unknown. Requires routing, which this task
  does not touch.
- **`configs/pcl/temper_production.yaml`** — still stale against the
  current netlist (carried forward from the prior R24 pass's own §7.1;
  unchanged by this task). Not loaded into this re-solve, same scope
  decision as before.
- **`cli/__init__.py`'s `optimize --no-loop` origin-offset bug** — still
  present and unfixed in the CLI itself (documented by the prior R24 pass,
  re-confirmed present in this pass by inspection, not re-tested against
  the CLI directly). This task's own solve/write driver works around it
  (§3) rather than fixing the CLI path, consistent with the prior pass's
  scope boundary.
- **The two designator reassignments from the resync**
  (`safety.latch` U25→U26; `mcu.mcu` U26→U27) — accepted on the strength
  of the `Sheetpath`-based resync tool (already independently validated in
  `docs/evidence/2026-07-27-pcb-netlist-resync.md`), not re-derived from
  the schematic a second time here.
- **Whether the wholesale 170/170 repositioning (no warm-start) changed
  anything relevant to future routing quality** — not evaluated; routing
  is untouched (0 segments/vias/zones) and out of scope.
- **`VoltageDomain.ISOLATED` / REQ-SAFE-02 barrier-geometry gaps** — both
  pre-existing, both carried forward unchanged from the prior R24 doc, not
  reassessed here (net-name/topology gap in the first case, no real
  routed-copper extraction pipeline in the second).

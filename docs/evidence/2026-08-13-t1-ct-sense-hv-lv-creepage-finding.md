<!-- provenance: commit=a3fbaff37afd739b72f2b109847813b30ceb8e88 (origin/fix/board-schematic-resync, worktree
/home/bennet/Desktop/temper-t1-isolator-safety, branch investigate/t1-isolator-hv-lv-creepage), dirty=false
for pcb/** throughout (git status --porcelain clean at every measurement below; pcb/temper.kicad_pcb
sha256=b7d865b7946f55dcc0d907cccbbee12f730fd1878b30d417bd56004d1091c1d6, pcb/temper.kicad_pro
sha256=f2d90755af04fea40357be3ba2ef94368a01b1afc34c450b42fad0b9e15a51ac, both unchanged before/after).
kicad-cli 10.0.5. Worktree given its own `.venv` via `make venv-isolate`; all 10 pyo3/maturin extensions
verified fresh (`scripts/check_stale_extensions.py` -> PASSED 10/10) AND independently import-tested
(`python -c "import <module>"` for all 10, all OK) both before and after the DRC measurements below.
`make netlist` run in this worktree (`elec/build/default.net`, digest 8cfd715e60a3...). No pcb/** file was
ever opened for writing; pcb/temper.kicad_dru is a gitignored, regenerated artifact
(scripts/generate_kicad_dru.py), not a tracked input. No subagents were dispatched. -->

# T1 (ct_sense.ct, OCP-01's Coilcraft CST3015) carries 8 real HV<->LV clearance/creepage violations, worst 0.3715mm against an 8.0mm (really 12.6mm) requirement -- caused by an unrelated SELV trace and via routed within 0.4mm of its live mains-referenced primary pads, not by a manifest gap and not by the footprint

**Verdict, up front.**

1. **The 8 violations are real, reproduced firsthand, and deterministic.** kicad-cli 10.0.5
   `pcb drc` against the untouched, committed `pcb/temper.kicad_pcb` (paired with a freshly
   regenerated `pcb/temper.kicad_dru`) reports exactly 8 `clearance`/`creepage` violations
   touching a `T1` pad, identical byte-for-byte across two independent runs. Worst creepage:
   **0.3715mm** against an enforced **8.0mm** requirement (**21.5x short**) -- matching the
   secondhand "0.37mm" figure almost exactly (Sec 2).
2. **The domain-manifest gap the task asked me to check for is real, but it does not cause or
   inflate T1's 8 violations.** `hb-gnd` and `s1` are indeed absent from
   `elec/domain_manifest.yaml` -- but they are **T2's** nets (`safety.ocp2.ct`, OCP-02's CT, a
   different physical part than `T1`), not T1's. T1's own analogous secondary net, `I_SENSE`, is
   *also* undeclared (a real, independent gap), but none of the 8 violations touch it. Every one
   of the 8 is between T1's two **primary** pads (`tank-out`, `PWR_RTN`) -- both correctly
   declared `HV` in the manifest -- and two genuinely-SELV nets (`y`, `rtd_pan.rail_monitor-outa`)
   whose absence from the manifest's SELV list does not change how kicad-cli's `HV to LV` DRU rule
   grades them, because that rule only tests the HV side's classification (Sec 3). **Not a
   rule-scoping artifact for T1.**
3. **Physically: pad-to-track and pad-to-via, not pad-to-pad, not intrinsic to the footprint.**
   The offending copper is a via and three track segments belonging to an RTD rail-monitor
   comparator (TPS3700, `elec/src/modules.ato:1945-1984`) whose own components (`U12`, `U13`,
   `U14`, `R39`, `R42`) sit 60-110mm away from T1 -- the nearest *other* component to T1 is 25mm
   away. This is a **routing defect**, not a placement-density necessity or a footprint defect:
   `temper:CST3015`'s own primary-row-to-secondary-row pad separation is a clean **9.1mm**
   edge-to-edge (computed from the footprint's own pad geometry, confirmed by zero T1-internal
   violations anywhere in the board's 1,400-violation DRC output) -- comfortably inside the
   currently-enforced 8.0mm bar (Sec 4).
4. **The 8.0mm bar itself is understated.** This repo's own prior, already-published
   determination (`docs/evidence/2026-08-12-pollution-degree-resolution.md`) found PD3, not PD2,
   governs this board today because the PD2 sealed-compartment prerequisite does not exist --
   re-verified firsthand in this session (`scripts/check_pd2_compartment_evidence.py` still fails,
   same as it did on 2026-08-12). The honestly-required reinforced creepage for this exact
   mains/DC-bus<->SELV barrier (IEC 60335-1 Table 17 row iv, >250-400V, material group IIIa/IIIb)
   is **12.6mm at PD3**, not the 8.0mm PD2 figure `scripts/generate_kicad_dru.py` currently emits
   (`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:180-204`). Against the honest bar, T1's worst
   measured creepage is **33.9x short**, and even the footprint's own intrinsic 9.1mm
   primary-secondary separation falls 3.5mm short of PD3 (Sec 5).
5. **This is a real safety finding: a live, mains-referenced primary conductor pad sits 0.37mm
   from unrelated low-voltage sensing copper.** It is fixable by rerouting (there is no placement
   obstruction in the way), not by a footprint or part change -- unlike the tank-node case this
   board already has on record. Recommended fix in Sec 6.

---

## 1. What T1 is, on this board (branch `origin/fix/board-schematic-resync`)

Confirmed directly against `pcb/temper.kicad_pcb` and the netlist compiled from `elec/src` in
this worktree (`make netlist`, `elec/build/default.net`):

- `T1`, footprint `temper:CST3015`, at `(53.21, 148.91)`, rotation 90 -- exactly matching the
  task brief.
- `(comp (ref "T1") ... (sheetpath (names ".../main.ato:Top::ct_sense.ct")))` -- `T1` is
  `ct_sense.ct`, OCP-01's Coilcraft CST3015-100ED current sense transformer, as the task states.
- `T2`, the *other* `temper:CST3015` on this board, is `safety.ocp2.ct` -- OCP-02's second CT
  (Option A, wired 2026-08-07 per `docs/hardware/OCP02_DECISION_BRIEF.md`). **This matters**: the
  task's `hb-gnd`/`s1` nets belong to `T2`, not `T1` (Sec 3.3).

T1's four pins, traced from the compiled netlist:

| Pad | Net | Domain (per `elec/domain_manifest.yaml`) |
|---|---|---|
| 1 (P1) | `tank-out` | HV -- declared |
| 2 (P2) | `PWR_RTN` | HV -- declared |
| 3 (S1) | `I_SENSE` | **undeclared** (not in HV or SELV list) |
| 4 (S2) | `gnd` | SELV -- declared |

`I_SENSE` (T1's own secondary net) is a real, independent manifest gap -- confirmed absent by
`grep -n I_SENSE elec/domain_manifest.yaml` (no hits) -- but it is not implicated in any of the 8
violations below (Sec 3.2).

---

## 2. Reproducing the 8 violations firsthand

```
$ /home/bennet/.local/bin/kicad-cli pcb drc --format json --severity-all \
    --output t1_drc.json pcb/temper.kicad_pcb
Found 1400 violations
Found 426 unconnected items
```

Filtered to violations that name a `T1` pad (excluding `RT1`, an unrelated NTC thermistor whose
own ref happens to substring-match), restricted to `clearance`/`creepage`:

| # | Type | Rule | Required | Actual | T1 item | Other item |
|---|---|---|---:|---:|---|---|
| 1 | clearance | HV to LV | 2.0mm | 0.4625mm | Pad 2 (`PWR_RTN`) | Track `rtd_pan.rail_monitor-outa` |
| 2 | clearance | HV to LV | 2.0mm | 0.6850mm | Pad 2 (`PWR_RTN`) | Track `rtd_pan.rail_monitor-outa` |
| 3 | clearance | HV to LV | 2.0mm | 0.4850mm | Pad 2 (`PWR_RTN`) | Track `rtd_pan.rail_monitor-outa` |
| 4 | clearance | HV to LV | 2.0mm | **0.3715mm** | Pad 2 (`PWR_RTN`) | Via, net `y` |
| 5 | creepage | HV to LV | 8.0mm | 0.4625mm | Pad 2 (`PWR_RTN`) | Track `rtd_pan.rail_monitor-outa` |
| 6 | creepage | HV to LV | 8.0mm | **0.3715mm** | Pad 2 (`PWR_RTN`) | Via, net `y` |
| 7 | creepage | HV to LV | 8.0mm | 6.5444mm | Pad 1 (`tank-out`) | Track `rtd_pan.rail_monitor-outa` |
| 8 | creepage | HV to LV | 8.0mm | 5.4894mm | Pad 1 (`tank-out`) | Via, net `y` |

**Exactly 8**, worst creepage **0.3715mm** -- both match the task brief's secondhand figures.
Confirmed deterministic: reran the identical `kicad-cli pcb drc` command a second time
(independent process invocation); the 8 violations' `(type, description)` tuples are byte-for-byte
identical across both runs (sorted-list comparison, all `True`). Not saturated at kicad-cli's
known reporting caps either: whole-board `clearance` came back 374 (cap 499) and `creepage` 168
(cap 199) -- both below their caps, so this is a true count, not a truncated one
(cf. `docs/evidence/2026-08-12-uncapped-drc-measurement.md`'s cap figures).

`pcb/temper.kicad_pcb` and `pcb/temper.kicad_pro` were never opened for writing (`git status
--porcelain` clean throughout; sha256 unchanged, recorded in this document's provenance header).
`pcb/temper.kicad_dru` was freshly generated by `scripts/generate_kicad_dru.py` (gitignored,
generated artifact, not a tracked input) to supply the rule kicad-cli needs -- this is a read-only
regeneration of a derived file, not an edit to the board.

---

## 3. Is this a rule-scoping / manifest-gap artifact? No, for T1.

### 3.1 What the task's memo got right, and what it named wrong

The task's memo is correct that `hb-gnd` and `s1` are absent from `elec/domain_manifest.yaml` --
confirmed independently: `grep -n 'hb-gnd\|s1' elec/domain_manifest.yaml` returns nothing. But
tracing both nets against the compiled netlist (`elec/build/default.net`) shows they are **`T2`'s**
pins, not `T1`'s:

```
(net (code "39") (name "hb-gnd")
  ...
  (node (ref "T2") (pin "1") (pintype "stereo")))   <- T2 pad 1 (P1, primary)
(net (code "117") (name "s1")
  (node (ref "T2") (pin "3") (pintype "stereo")))   <- T2 pad 3 (S1, secondary)
```

`hb-gnd` is T2's primary pin 1 (paired with `DC_BUS_RTN` on pin 2 -- both should be HV, the exact
analogue of T1's declared `tank-out`/`PWR_RTN`). `s1` is T2's secondary pin 3 (the exact analogue
of T1's own undeclared `I_SENSE`, Sec 1). **Neither net has anything to do with `T1`.**

### 3.2 Does this gap inflate or misattribute T1's own violations? Measured: no.

None of the 8 violations in Sec 2 touch `I_SENSE` (T1's own undeclared secondary net) -- both
items in every one of the 8 are either a T1 *primary* pad (`tank-out`/`PWR_RTN`, both correctly
declared HV) or copper on an unrelated net (`y`, `rtd_pan.rail_monitor-outa`, both traced to a
purely SELV circuit, Sec 3.4). Checked directly against the full 1,400-violation dump: only 2
violations anywhere on the board even mention `I_SENSE` by net name (a `solder_mask_bridge` and a
`shorting_items` finding against `SHUTDOWN`, both unrelated to T1's HV pads and to this
investigation).

### 3.3 The gap *is* real and *does* misattribute -- for `T2`, not `T1`

Checked whether `hb-gnd`/`s1` cause the same kind of grading problem on their own component: yes.
`hb-gnd` and `s1` are absent from `pcb/temper.kicad_pro`'s `netclass_assignments` dict too
(`assn.get('hb-gnd')` -> not found; same for `s1`), so both fall through to the `Default`
netclass -- meaning `hb-gnd`, which is actually T2's HV-referenced primary pin (paired with the
already-`HighVoltage`-classified `DC_BUS_RTN` on the same footprint), gets graded as the **LV
side** of the `HV to LV` / `HighVoltageIsolated to LV` rules instead of the HV side. Directly
measured: 10 DRC violations name `hb-gnd`, including 5 `clearance`/`creepage` entries against
`HV to LV` and `HighVoltageIsolated to LV` rules (actual distances 0.65-5.75mm). Whether that
under-classification net *increases or decreases* T2's reported violation count is a separate
investigation (T2 was out of this task's scope, and the rule pairing for an HV net misgraded as
LV is not the same computation as a correctly-graded HV pin, so the count cannot be inferred by
inspection) -- flagged here as a genuine, adjacent defect worth its own follow-up, not fixed in
this document (see "What this document does not do", Sec 7).

### 3.4 Why the manifest gap can't be the cause here: the `HV to LV` rule's own condition

```
(rule "HV to LV"
   (condition "A.NetClass == 'HighVoltage' && B.NetClass != 'HighVoltage'
     && B.NetClass != 'HighVoltageTank' && B.NetClass != 'ACMains'
     && B.NetClass != 'GateDriveHV' && B.NetClass != 'HighVoltageIsolated'")
   (constraint clearance (min 2.0mm))
   (constraint creepage (min 8.0mm)))
```
(`scripts/generate_kicad_dru.py:970-981`)

This rule only requires the **A** (HV) side to be classified `HighVoltage` -- it does not require
the **B** side to be declared `SELV`. `y` and `rtd_pan.rail_monitor-outa` are absent from both
`elec/domain_manifest.yaml`'s SELV list and `pcb/temper.kicad_pro`'s `netclass_assignments`
(confirmed: `assn.get('y')` / `assn.get('rtd_pan.rail_monitor-outa')` both `NOT FOUND`), so they
fall to the `Default` netclass -- which still satisfies `B.NetClass != 'HighVoltage'` (and every
other exclusion). **Declaring them SELV in the manifest would not change which rule fires or its
threshold**; `Default` and `SELV` are graded identically by this rule's condition. So even a
complete fix of every manifest gap found in this session leaves T1's 8 violations exactly as
measured. This is the opposite outcome from the `hb-gnd` case in Sec 3.3, where the gap changes
which *side* of the rule a net lands on because the net itself should have been `HighVoltage`.

### 3.5 Confirmed the LV-side nets really are SELV, not a second misclassification

Traced `y` and `rtd_pan.rail_monitor-outa` to source: both are pins of a TPS3700 window
comparator, `RTDSensing.rail_monitor` (`elec/src/modules.ato:1945-1984`), powered from
`power.vcc`/`power.gnd` (the SELV 3.3V logic rail) and monitoring `RTD_AVDD`, an internal analog
rail of the RTD front-end -- no HV node is read, driven, or referenced anywhere in this circuit.
This is unambiguously SELV. The undeclared status is a real documentation/coverage gap (it means
`scripts/check_isolation_keepout.py`'s SELV-pad count is undercounted, and this circuit escaped
whatever audit surface depends on the manifest's SELV list), but it is not a misclassification
that changes T1's grading.

---

## 4. What is physically too close, and is it intrinsic to the footprint?

### 4.1 Kind of violation: pad-to-track and pad-to-via

All 8 violations pair a T1 **pad** (never a T1 track, since T1 has no traces routed to its own
pins beyond the pad itself in this region) against either a **routed track segment** (net
`rtd_pan.rail_monitor-outa`) or a **via** (net `y`). None are pad-to-pad (footprint-internal) or
pad-to-pour.

### 4.2 Why this is a routing defect, not a placement-density problem

The offending copper's *source* components are far from T1:

| Ref | Position | Distance from T1 (53.21, 148.91) |
|---|---:|---:|
| `U12` | (123.63, 63.51) | ~114mm |
| `U13` | (147.7, 42.48) | ~135mm |
| `U14` | (32.59, 220.8) | ~90mm |
| `R39` | (162.46, 96.02) | ~127mm |
| `R42` | (162.56, 92.81) | ~130mm |

Yet the violating track segments and via sit at `(38-44, 148-153)` -- 5-15mm from T1 -- because
the route for these nets passes directly beside T1 en route to/from those far-away components,
not because any of those components is physically crowding T1. Checked the area directly: **no
other component's footprint origin sits within 25mm of T1** (nearest are `R36` at (28.48, 143.45)
and `R20` at (25.6, 145.91), both ~25mm away) -- there is no placement congestion forcing a route
through this gap. This is exactly the class of finding the task memo flagged as possible: a
router path threaded thin (0.25mm) SELV signal copper within fractions of a millimeter of a live
mains-referenced pad, in an otherwise open area of the board.

### 4.3 The footprint's own geometry: not intrinsic

Computed directly from `temper:CST3015`'s own pad coordinates (`pcb/temper.kicad_pcb`, both `T1`
and `T2` instances, which share the identical footprint at two different rotations -- used both to
cross-check, since internal pad-to-pad geometry is rotation-invariant):

```
pad 1 (P1, 9.0x4.8mm) center (7.68, -6.85)   pad 3 (S1, 3.0x4.6mm) center (-6.88, 6.95)
pad 2 (P2, 9.0x4.8mm) center (-7.68, -6.85)  pad 4 (S2, 3.0x4.6mm) center (6.88, 6.95)

edge-to-edge gap, pad 1 <-> pad 4: 9.1000mm
edge-to-edge gap, pad 2 <-> pad 3: 9.1000mm
edge-to-edge gap, pad 1 <-> pad 3: 12.4933mm
edge-to-edge gap, pad 2 <-> pad 4: 12.4933mm
```

The tightest primary-to-secondary separation **within the footprint itself is 9.1mm**, exceeding
the currently-enforced 8.0mm (PD2) reinforced-creepage bar by 1.1mm. This is corroborated by the
DRC data: of T1's 1,400-violation-wide neighborhood, zero violations are T1-pad-vs-T1-pad --
kicad-cli itself never flags the footprint against its own geometry. **`temper:CST3015`'s land
pattern is not the defect for the currently-enforced bar.** (Sec 5 below revisits this once the
honest, PD3-governed 12.6mm bar is substituted -- the footprint's margin flips negative there.)

---

## 5. What the standard actually requires, checked against the repo's own prior determination

### 5.1 Which table, which tier

T1's crossing is `PWR_RTN`/`tank-out` (mains/DC-bus referenced, HV domain) against SELV `gnd` --
a genuine barrier crossing (this is what the isolator is *for*, per the task brief), so **Table
17 reinforced insulation** governs (not Table 18 functional, which is for same-domain HV<->HV
pairs like the tank-node finding this repo already investigated). `docs/specs/
HIGH_VOLTAGE_CLEARANCE_SPEC.md:146-204` derives this board's working voltage into Table 17 row iv
(>250V, <=400V) at Material Group IIIa/IIIb:

| Pollution Degree | Basic | Reinforced |
|---|---:|---:|
| PD2 | 4.0mm | **8.0mm** |
| PD3 | 6.3mm | **12.6mm** |

`scripts/generate_kicad_dru.py`'s `HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD2_MM` (8.0mm) is
exactly this PD2 figure -- the number the 8 violations above are graded against.

### 5.2 PD2 or PD3, checked fresh on this branch

Re-ran the repo's own gate for this, first-hand, on this exact board state:

```
$ uv run --no-sync python scripts/check_pd2_compartment_evidence.py
PD2 compartment-evidence gate -- tree currently claims PD2 (8.0mm reinforced creepage)
Evidence file: .../docs/specs/pd2_compartment_evidence.yaml (present: False)
=== VIOLATIONS: 1 ===
  VIOLATION .../pd2_compartment_evidence.yaml does not exist -- the tree claims PD2/8.0mm
  (generate_kicad_dru.py's HV_CREEPAGE_ENFORCED_MM) but no compartment evidence artifact
  has been committed
FAILED -- 1 violation(s).
```

This reproduces, on `origin/fix/board-schematic-resync` today, the same finding
`docs/evidence/2026-08-12-pollution-degree-resolution.md` already reached and cited for the
tank-node case: IEC 60335-2-6 cl. 29.2's Addition makes PD3 the default microenvironment for a
cooking appliance; PD2 is an unearned exception here because no gasketed PCB compartment exists
(no cover/gasket/partition/inspection geometry, no evidence YAML, board outline still a plain
rectangle). **The same board-wide PD2/PD3 policy question governs T1's `HV to LV` reinforced bar
just as much as it governed the tank node's functional bar** -- this is not a tank-specific
finding, it is a property of the whole board's unmet compartment prerequisite.

**On the standard's own condition, the honestly-required creepage for T1's barrier is 12.6mm, not
the 8.0mm this repo currently enforces.**

### 5.3 What that means for T1, both ways

| Bar | Required | T1 worst measured (0.3715mm) shortfall |
|---|---:|---:|
| Currently enforced (PD2) | 8.0mm | **21.5x short** |
| Honestly required (PD3, per this repo's own prior finding, re-verified today) | 12.6mm | **33.9x short** |

And the footprint's own intrinsic 9.1mm primary-secondary separation (Sec 4.3), which clears the
enforced 8.0mm bar by 1.1mm, is **3.5mm short of the honest 12.6mm PD3 bar**. This does not change
today's 8 measured violations (kicad-cli is grading against the enforced 8.0mm figure, and the
footprint passes that), but it means the footprint has essentially no margin against the standard
this repo has already determined actually governs -- worth carrying forward as a latent risk, not
reported as a 9th violation, since it is not what kicad-cli currently flags.

This document does not change `HV_CREEPAGE_ENFORCED_MM`, any DRU threshold, or any netclass/
creepage/clearance value, per the task's hard constraint -- the PD2-vs-PD3 question is reported,
not resolved or acted on, here.

---

## 6. Recommendation

**This is real and fixable by routing -- not a footprint or part-selection problem.** The fix is
local to two nets that have no business being anywhere near T1:

1. Reroute the `rtd_pan.rail_monitor-outa` track segments currently passing through
   `(38-44, 148-153)` and relocate the `y`-net via currently at `(43.3725, 151.59)` to restore at
   least 8.0mm (the currently-enforced bar) -- or, to be honest against the PD3 finding in Sec 5,
   12.6mm -- of clearance from T1's `tank-out`/`PWR_RTN` pads.
2. No placement change to T1 or to the RTD comparator's own components (`U12`-`U14`, `R39`,
   `R42`) is required -- they are already 60-135mm from T1. The area immediately around T1 is open
   (nearest other component 25mm away), so there is room to route around it.
3. Separately, and lower priority: declare `I_SENSE` (T1's own secondary net) as SELV, and
   `hb-gnd` (HV) / `s1` (SELV) for T2, in `elec/domain_manifest.yaml`. This does not change any of
   the 8 violations measured here (Sec 3.4), but it closes a real coverage gap this task's memo
   correctly flagged (just misattributed to the wrong transformer) and, per Sec 3.3, corrects a
   genuine under-classification (`hb-gnd` graded as LV instead of HV) that does affect T2's own
   DRC grading. Not fixed in this document -- it is a `T2`/OCP-02 investigation, out of this
   task's scope, and doing it here would risk conflating two unrelated findings.

---

## 7. What this document does not do

- **Changes no `pcb/**` file, no DRU rule, no netclass value, no creepage/clearance constant.**
  `git status --porcelain` shows only this document; `pcb/temper.kicad_pcb` and
  `pcb/temper.kicad_pro` sha256 are unchanged from the provenance header's opening measurement to
  this line.
- **Does not fix the `hb-gnd`/`s1`/`I_SENSE` manifest gaps.** Real, confirmed absent, and (for
  `hb-gnd`) shown to cause a genuine misgrading on `T2` -- but that is a different component and a
  different investigation from what this task asked about `T1`. Flagged, not fixed, per Sec 3.3
  and Sec 6 item 3.
- **Does not resolve the PD2-vs-PD3 policy question.** Re-confirms, first-hand, on this branch,
  that this repo's own prior determination (PD3 governs, 12.6mm) still holds -- but does not
  change `HV_CREEPAGE_ENFORCED_MM` or any other enforcement point, per the task's hard constraint.
- **Does not execute the reroute.** Sec 6 states what would close the finding; running the
  place+route pipeline and re-measuring is the natural next PR, not this one.
- **Does not investigate `T2` (`safety.ocp2.ct`, OCP-02's CT) further than what was needed to
  correctly scope `T1`'s own finding.** Sec 3.3's `hb-gnd` numbers are a byproduct of that scoping
  check, not a complete `T2` audit.

---

## Files

- This document: `docs/evidence/2026-08-13-t1-ct-sense-hv-lv-creepage-finding.md`
- Board/netlist read directly: `pcb/temper.kicad_pcb`, `pcb/temper.kicad_pro`,
  `elec/build/default.net` (built via `make netlist` in this worktree), `elec/domain_manifest.yaml`,
  `elec/src/modules.ato`
- Rule/config sources: `scripts/generate_kicad_dru.py`, `pcb/temper.kicad_dru` (regenerated,
  gitignored), `packages/temper-placer/configs/netclass_rules.yaml`,
  `scripts/check_pd2_compartment_evidence.py`, `scripts/check_isolation_keepout.py`
- Prior evidence relied on: `docs/evidence/2026-08-12-pollution-degree-resolution.md`,
  `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`, `docs/evidence/2026-08-12-uncapped-drc-measurement.md`
- Not modified by this document: `pcb/**`, `elec/domain_manifest.yaml`, any netclass, DRU rule, or
  `power_pcb_dataset/drc_ceiling.json` entry.

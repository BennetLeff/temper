<!-- provenance: commit=765859caa branch=analysis/thermal-constraint-derivation worktree=/home/bennet/Desktop/temper/.claude/worktrees/thermal-derivation dirty=true (this doc + one thermal_management.yaml edit for the constraint determined stale) -->

# Are the three violated thermal constraints real requirements or stale premises? Derivation against component/mechanical data

## Verdict

**Two of three are real physical requirements the board genuinely violates.
One is not — and is worse than merely stale, because the number pinned to
it (8mm) is a well-attested figure from a *different* physical domain
(reinforced electrical creepage/clearance) that has nothing to do with the
component pair it is attached to.**

1. **IGBT alignment for shared heatsink — REAL, VIOLATED, worse than the
   declared 76.35mm/1mm framing suggests.** `HS1` (Wakefield-Vette
   392-120AB) is a single extruded heatsink genuinely shared by both IGBTs
   plus two TO-220 rectifiers (`docs/hardware/BOM.md:542`), with die-cut
   TIM pads sized per TO-247 (`BOM.md:544`) and 4 individual mounting sets
   (`BOM.md:546`) — this is not a template artifact, it is a real,
   specific, BOM-costed mechanical assembly. `U5`/`U6` are not just
   76.35mm apart and at mismatched edge distances (~21mm vs ~95mm from the
   board's top edge) — their footprints are placed at **90° different
   rotations** (`pcb/temper.kicad_pcb:7969`, `270.0°`; `:8008`, `180.0°`),
   meaning their TO-247 tab planes face perpendicular directions. No
   single flat heatsink face can contact both regardless of how close
   together they are moved. This is a genuine, currently-unfixable-by-
   nudging mechanical defect.
2. **Heatsink NTC adjacency — STALE AS WRITTEN, but only because the
   distance metric is meaningless, not because the underlying safety
   concern is fake.** `R60`'s footprint is an explicitly-labeled
   **stand-in** 2-pad axial pad (`elec/src/modules.ato:2412-2414`: "no
   NTC/thermistor lib in the committed fp-lib-table. The lug-mount part is
   wired via flying leads anyway"). The real component (Vishay
   `NTCALUG01A104GA`) is an M3-ring-lug thermistor bolted directly to the
   heatsink with 38.1mm AWG24 PTFE leads (`modules.ato:2402-2409`,
   `docs/hardware/BOM.md:414`) — a physically separate part from where
   `R60`'s PCB pads sit. PCB-plane distance from `R60` to `U5`/`U6` is not
   a proxy for sensor-to-heatsink distance at all, so 122–213mm measured
   against a KiCad footprint is not evidence of anything. **But** the
   38.1mm lead length is a real, hard mechanical fact this document *did*
   derive, and it is worth checking against the true installed distance —
   see below; this is a genuine open question, not a closed one.
3. **Gate resistor to bootstrap cap, ≥8mm — STALE, MISCATEGORIZED, config
   edit made.** The bootstrap cap (`C17` = `hb.gate_hs.boot_cap`) is a
   Murata `GRM32ER71H106KA12L`, 10µF/50V **X7R ceramic**, 1210 package
   (`elec/src/modules.ato:145-149`, `docs/hardware/BOM.md:19`) — not an
   electrolytic. X7R is rated to 125°C with a well-behaved capacitance-vs-
   temperature curve; it does not have the electrolyte-driven,
   life-halves-per-10°C failure mode the *neighboring* `C_BUS1`/`C_BUS2`
   constraint (lines 100-107 of the same file) correctly invokes for the
   *actual* electrolytic bus caps. The gate resistor's (`R23`) own
   dissipation, independently derived below from the IGBT's real
   datasheet gate charge and the board's real switching frequency, is
   ≈0.13–0.25W — comfortably inside its 0.5W rating, and not the kind of
   power level that drives an 8mm keepout for any capacitor, let alone a
   125°C-rated ceramic. Separately, and more damningly: **8.0mm is not an
   arbitrary-looking number in this repo — it is the recurring IEC
   60335-1/UCC21550-datasheet reinforced-insulation creepage/clearance
   figure**, used for HV-to-SELV domain barriers no fewer than 9 times
   elsewhere in `docs/hardware/*.md` (`COMPONENT_COMPATIBILITY_VERIFICATION.md:338`,
   `PROTECTION_CHAIN_REVIEW.md:108`, `GROUNDING_EMI_STRATEGY.md:198,389,399`,
   `LMR51430_THERMAL_ANALYSIS.md:165,284`, `OCP02_*` files, `DESAT_REDESIGN_SPIKE.md:56`,
   `2026-07-29-open-safety-gate-actions.md:52`). `R23` and `C17` are both
   inside the *same* floating high-side gate-drive domain (both riding on
   the bootstrap rail relative to the switch node) — there is no
   HV-to-SELV barrier between them to which a creepage figure would even
   apply. The most likely history: an isolation-clearance constant
   leaked into a thermal-sounding "keep the hot part away from the
   sensitive part" template line. Config edit made below.

**The board does violate the derived version of constraint (1)** (arguably
more clearly than the declared one, once rotation is included) **and does
not violate any derivable version of constraint (3)** (3.13mm is not close
to a problem at ≈0.13–0.25W into a 125°C-rated ceramic). **Constraint (2)
cannot be fully resolved either way** — the *declared* form is definitely
meaningless (PCB distance to a flying-lead part), but whether the *actual*
lead-length-limited installation satisfies the real safety intent (sensor
touching the heatsink body) is data this repo does not contain (chassis
layout / heatsink-to-board offset) — flagged as a genuine gap, not
resolved by asserting either verdict.

---

## Method

- Read `docs/evidence/2026-08-12-thermal-emi-declaration-drift.md`
  (PR #1071, branch `fix/thermal-emi-config-drift`, not yet on `main` —
  fetched via `git fetch origin fix/thermal-emi-config-drift`) for the
  reconnected component identities and the three measured violations. That
  document explicitly declined to judge whether the mm figures are real;
  this document picks that up.
- Traced each constraint's named component to its `elec/src/modules.ato`
  module (source of truth for value/footprint/MPN) and cross-checked
  against `docs/hardware/BOM.md`'s reconciled entries and
  `pcb/temper.kicad_pcb`'s actual footprint placements
  (`(at x y rot)`) and `Sheetpath` properties (not modified — verified via
  `git status`/`git diff` before writing this document).
- For the gate-resistor dissipation, derived power independently from the
  real IGBT datasheet gate charge (`docs/hardware/MILLER_CURRENT_ANALYSIS.md:140`,
  itself sourced from `IKW40N120H3_Documentation.md`), the real gate-drive
  rail (15V, `elec/src/modules.ato:189`), and the real committed switching
  frequency (47kHz, `docs/hardware/TANK_COIL_SPECIFICATION.md:58`,
  `elec/src/main.ato:188`) — not from the declared config comment
  ("2-5W", `thermal_management.yaml`'s own `because` text, which this
  investigation found to be roughly 10-40x too high).
- Did not modify `pcb/**`. The only file changes are this document and one
  edit to `thermal_management.yaml` for the constraint determined stale
  (§3), with the reasoning recorded inline in the YAML.

---

## Constraint 1: IGBT alignment/edge-mount for shared heatsink

**Declared:** `on_side` (flush to top edge) + `aligned` (X-axis, 1.0mm
tolerance) for `[Q1, Q2]` → real components `U5`/`U6`
(`packages/temper-placer/configs/constraints/thermal_management.yaml:20-32`).

**Is the shared-heatsink premise real?**

Yes, unambiguously. `docs/hardware/BOM.md:542`:

> `HS1 | Shared Heatsink (2×TO-247 + 2×TO-220) | 392-120AB | Wakefield-Vette | 1 | Extruded, 120x125x135.8mm, 0.5°C/W natural / 0.2°C/W forced convection`

This is a single, specific, currently-sourced part (qty 1), explicitly
shared across all four power devices, corrected into the BOM on 2026-07-16
against `docs/plans/2026-07-16-001-feat-active-bus-discharge-and-thermal-bom-plan.md`
(replacing an earlier Aavid 62960 candidate — `BOM.md:557-559`). It is
backed by:

- `TIM_HV | TIM/Isolator, TO-247 (IGBTs) | SP400-0.009-00-58 | Bergquist | 2 | Sil-Pad 400, 0.009", TO-247 die-cut` (`BOM.md:545`) — two individually-sized insulator pads, one per IGBT, both pressing against the *same* heatsink body.
- `HW_MOUNT | ... M3x10 pan-head + insulating shoulder washers + Belleville washers | 4 sets` (`BOM.md:546`) — one mounting set per device (2 IGBT + 2 TO-220), all onto the one part.
- `elec/src/modules.ato:1570-1584` (`ThermalSystem` docstring): "heatsink (Wakefield-Vette 392-120AB), Sil-Pads and mounting hardware are chassis BOM."
- Independent corroboration in `docs/hardware/SYSTEM_THERMAL_BUDGET.md:148-154` and `docs/CHASSIS_AIRFLOW_DESIGN.md` (both describe a single shared "IGBT Heatsink" as the cooling path, though both predate the 2026-07-16 HS1/FAN1 MPN correction and cite stale dimensions/fan model — noted so their dimensional figures aren't relied on, only their qualitative "one shared heatsink" framing, which BOM.md independently confirms with current data).

`thermal_management.yaml`'s own `because` text ("TO-247 IGBT packages
require board edge mounting for external heatsink access," "IGBTs aligned
horizontally for shared heatsink mounting and symmetrical thermal design
for manufacturing") is not a generic template guess here — it accurately
describes a mechanical assembly that exists in this design's real BOM.

**Is the board's layout compatible with it?**

No, on two independent grounds, one of which the original evidence
document did not check:

| Check | `U5` (`hb.power_loop.q_high`) | `U6` (`hb.power_loop.q_low`) | Compatible with one flat heatsink face? |
|---|---|---|---|
| Position (`pcb/temper.kicad_pcb:7969`, `:8008`) | `(23.72, 233.25)` | `(100.07000000000001, 159.33)` | 76.35mm apart in X, ~74mm difference in edge-distance (Y) |
| **Footprint rotation** | **270.0°** | **180.0°** | **90° apart — tab planes face perpendicular directions** |

The rotation finding is new to this document (not measured in
`2026-08-12-thermal-emi-declaration-drift.md`). Both use the identical
footprint (`Package_TO_SOT_THT:TO-247-3_Vertical`), so the 90° rotation
difference is not a package-variant artifact — it is a real difference in
which direction each device's mounting tab faces. An extruded heatsink
(`HS1`) has one flat mounting profile running its length; it cannot
simultaneously contact two tabs that face perpendicular to each other. **A
correct fix is not "move them 76mm closer" — it requires re-rotating one
device**, which the declared 1.0mm/X-axis-only `aligned` constraint does
not even capture (it can be satisfied while rotations remain
incompatible).

**Verdict: REAL, VIOLATED.** Cannot independently derive the exact
"1.0mm" tolerance figure (`HS1`'s mechanical drawing — hole pattern, flat
face width — is not in this repo; no `datasheets/*wakefield*` or
`*392-120*` file exists). But the qualitative violation does not depend on
that number: current placement fails even a generous tolerance (edge
distance differs by ~74mm against any plausible single-digit-mm
requirement) and fails on an axis (rotation) no numeric tolerance was
checking at all. **This is reported as a hardware/placement finding, not
loosened.**

---

## Constraint 2: heatsink NTC adjacency

**Declared:** `adjacent`, `Q1`↔`TH_HEATSINK`, ≤10mm
(`thermal_management.yaml:113-118`), reconnected to `U5`/`U6`↔`R60`.

**Is `R60` board-mounted, or a flying-lead stand-in?**

Flying-lead stand-in, stated explicitly in source, not inferred:

`elec/src/modules.ato:2402-2414`:
```
# NTC thermistor: 100k at 25C, B25/85=4190K, lug-mount on heatsink
ntc = new Resistor  # Using Resistor as NTC placeholder
...
# VERIFIED 2026-07-16: Vishay BCcomponents NTCALUG01A104GA — standard
# lug sensor, R25=100k +/-2%, B25/85=4190K +/-1.5%, AWG#24 PTFE leads
# 38.1mm, M3 ring lug, AEC-Q200, 1500VAC lug-to-terminal isolation
...
# Stand-in 2-pad axial footprint; no NTC/thermistor lib in the committed
# fp-lib-table. The lug-mount part is wired via flying leads anyway.
ntc.footprint = "Resistor_THT:R_Axial_DIN0204_L3.6mm_D1.6mm_P2.54mm_Vertical"
```

`docs/hardware/BOM.md:414` confirms the same part in the M3-lug package
class, not a PCB SMD/THT sensor package. `R60`'s KiCad footprint
(`pcb/temper.kicad_pcb:5708-5715`, `Resistor_THT:R_Axial_DIN0204...`, an
axial resistor footprint) is exactly the placeholder the source comment
describes — a routing anchor for the two wire-lead connections, not a
representation of where the physical sensor body sits. **PCB-plane
distance from this footprint to `U5`/`U6` (122–213mm, per the
reconnection document) is therefore not measuring what the constraint
claims to measure.** The constraint as written (a distance check between
two `(x, y)` points on the PCB) is unenforceable in any meaningful sense
against this component — this is the "meaningless as written" branch, not
the "board violates it" branch.

**Does the underlying safety concern (over-temp protection needs to sense
the actual heatsink) still apply?**

Yes — this is not a reason to delete the requirement, only to change what
it must check. `docs/hardware/SAFETY_INTERLOCK_DESIGN.md:288-289`: "1.
Primary: Bonded to IGBT heatsink with thermal paste. 2. Secondary: Near
heatsink mounting point." `elec/src/modules.ato:2390` / `ThermalComparator`
implements THM-01, an 85°C trip / 70°C recovery over-temperature
protection path that is explicitly load-bearing on a mains-connected
cooktop (`docs/hardware/PROTECTION_CHAIN_REVIEW.md`,
`docs/hardware/BOM.md:410-421`). If the physical NTC lug is not actually
bonded to the heatsink body, THM-01 protects nothing — it would report
whatever temperature the flying leads happen to be sitting at.

**What this document could verify, and what it could not:**

- Verified: the sensor is designed to be a lug bolted to the heatsink,
  connected by 38.1mm of leadwire, not a PCB-position-dependent sensor.
- Verified: 38.1mm is a *hard* limit — the lug cannot physically be
  installed more than 38.1mm of lead-run from wherever its two PCB
  termination pads are, `+/-` routing slack.
- **Not verifiable from this repo:** where the heatsink physically sits
  relative to the PCB in the finished assembly (chassis/enclosure
  drawing, not present — `docs/CHASSIS_AIRFLOW_DESIGN.md` describes duct
  geometry but not a heatsink-to-PCB offset dimension; no mechanical
  assembly/interconnect drawing exists in-repo). Without that, it is not
  possible to say whether 38.1mm of lead is *enough* to reach from the R60
  pad location to the real, physically-installed `HS1` body, or whether
  the THM-01 sensor is stranded short the way the declared PCB-distance
  check accidentally-almost-caught.

**Verdict: STALE AS WRITTEN (the PCB-distance metric is not meaningful
for a flying-lead part) — but the underlying safety requirement is real
and unresolved, not dismissed.** This is reported prominently per the
task's instruction: **THM-01 is the mains-cooktop over-temperature
protection path, and this investigation cannot confirm from repo data
that the sensor is actually within physical reach of the heatsink it must
monitor.** What is missing to close this out: a chassis/enclosure
mechanical drawing (or equivalent as-built measurement) giving the
heatsink's position relative to the PCB's `R60` pad location, checked
against the 38.1mm lead budget.

---

## Constraint 3: gate resistor to bootstrap cap, ≥8mm

**Declared:** `separated`, `R_GATE_HIGH`↔`C_VCC2`, ≥8mm
(`thermal_management.yaml:81-87`), reconnected to `R23`
(`hb.gate_hs.rg_on`) ↔ `C17` (`hb.gate_hs.boot_cap`). Measured: 3.13mm
(`R23` at `(46.14, 115.35)`, `C17` at `(46.12, 118.48)` —
`pcb/temper.kicad_pcb:4574`, `:428`).

**Thermal, or electrical?**

### Gate resistor's actual dissipation (thermal side)

`R23`/`R27` (`rg_on`, both high- and low-side) are 2.2Ω, 1206, 0.5W-rated
(`elec/src/modules.ato:160-163`). The design's own code carries a
hardcoded assumption, not a derivation:

```
# Power assertion: gate resistor must handle average dissipation (temper-ip1.3)
p_rg_avg: power = 0.25W
assert rg_on.power_rating >= p_rg_avg * 1.5
```
(`elec/src/modules.ato:171-173`)

Independently derived here from real datasheet/board data instead of that
constant:

- Gate charge `Q_G` = 185nC (datasheet) / 240nC (conservative), both
  **at V_GE = 15V**, `docs/hardware/MILLER_CURRENT_ANALYSIS.md:140`
  (source: `IKW40N120H3_Documentation.md`).
- Gate-drive rail: 15V (`elec/src/modules.ato:189`, "boot cap charges to
  full VDD (15V)").
- Switching frequency: 47kHz, the corrected/committed operating point
  (`docs/hardware/TANK_COIL_SPECIFICATION.md:58`, `elec/src/main.ato:188`).

Standard gate-drive-loss upper bound (total charge+discharge energy
delivered by the drive rail per switching cycle, `E ≈ Q_G × V_DD`,
`P = E × f_sw`; this is an upper bound on `R23`'s own share since it
ignores the driver IC's internal output resistance, for which no figure
is recorded in this repo — noted as a real gap, biased conservative):

```
P = 185nC × 15V × 47kHz ≈ 0.130 W   (datasheet Q_G)
P = 240nC × 15V × 47kHz ≈ 0.169 W   (conservative Q_G)
```

This brackets the design's own assumed 0.25W (a bit more conservative
than either independently-derived figure, consistent — not contradicted).
**`R23` dissipates on the order of 0.13–0.25W, well inside its 0.5W
rating** (25-50% derating, unremarkable for an SMD resistor). This is not
"tens of milliwatts" but it is nowhere near the "2-5W" the config's own
`because` field claims (`thermal_management.yaml:83`, "Gate resistors can
get hot during high-frequency switching... 2-5W" appears on the sibling
`R_SNUB` line, not this one — but this line's own text, "Gate resistors
can get hot during high-frequency switching," implies a magnitude this
derivation does not support).

### Bootstrap cap's actual thermal sensitivity

`C17` = Murata `GRM32ER71H106KA12L`, 10µF/50V, **X7R**, 1210
(`elec/src/modules.ato:145-149`; `docs/hardware/BOM.md:19`, "10µF 50V
X7R"). X7R is a Class II ceramic dielectric rated to 125°C with a
specified capacitance-vs-temperature envelope (±15% over -55 to 125°C per
the EIA designation) — it does not have the electrolyte-driven,
life-halves-per-10°C aging mechanism. That mechanism is real in *this
design*, but for a different, correctly-identified pair: `C_BUS1`/`C_BUS2`
(`thermal_management.yaml:100-107`), which the BOM confirms are genuinely
electrolytic bus capacitors (`docs/hardware/BOM.md`'s bus-cap section,
"4×1800µF" electrolytic per the 2026-07-26 revision note). The
`R_GATE_HIGH`/`C_VCC2` line appears to generalize that same "keep hot
resistor away from sensitive cap" template onto a component pair where the
cap in question is not, in fact, the sensitive kind.

At ≈0.15W into an SMD resistor, board-level local temperature rise a few
mm away is typically a handful of °C at most (no in-repo copper-spreading
or board-thermal-resistance model exists to compute an exact figure — not
invented here); against a 125°C-rated ceramic sitting in a 50°C-ambient
design (`thermal_management.yaml:11`, `max_junction_temp`/`ambient_temp`
metadata), there is no plausible thermal mechanism at this power level
that needs an 8mm keepout.

### Where "8mm" actually comes from in this repo

Searching for "8mm"/"8 mm" across `docs/hardware/*.md` turns up the same
figure, with the same value, used repeatedly for a *different* physical
concept — reinforced electrical creepage/clearance (IEC 60335-1 / UCC21550
datasheet reinforced-isolation rating), not thermal spacing:

- `docs/hardware/COMPONENT_COMPATIBILITY_VERIFICATION.md:338,342`: "UCC21550: 8mm minimum (exceeds reinforced)... PCB layout must maintain >8mm creepage per UCC21550 requirements."
- `docs/hardware/PROTECTION_CHAIN_REVIEW.md:108`: "Creepage/clearance — ≥8 mm."
- `docs/hardware/GROUNDING_EMI_STRATEGY.md:198,389,397,399`: "Creepage distance >8mm between ground domains," "Creepage/clearance >8mm for basic insulation," "Across isolation barrier | 8mm | 12mm."
- `docs/hardware/LMR51430_THERMAL_ANALYSIS.md:165,284`: ">8mm clearance from high-voltage nets (isolation)," ">8mm creepage to HV copper."
- `docs/hardware/DESAT_REDESIGN_SPIKE.md:56`, `docs/hardware/OCP02_*.md` (multiple): the same 8.0mm reinforced-creepage constant, `MIN_BARRIER_WIDTH_MM = 8.0mm`.
- `docs/hardware/2026-07-29-open-safety-gate-actions.md:52`: "Required minimum barrier width: 8.0mm (REINFORCED creepage)."

Nine-plus independent uses, all electrical isolation, all exactly 8.0mm.
`R23`/`C17` are not separated by an isolation barrier — both are inside
the same floating high-side gate-drive domain riding on the bootstrap
rail relative to the switch node (`elec/src/modules.ato:174-176`,
`:189-192`); there is no HV-to-SELV (or any other cross-domain) boundary
between them for a creepage figure to apply to. This is circumstantial,
not a commit-history-proven paper trail, but it is a strong, specific,
repeatedly-corroborated match, and a far more plausible origin for "8mm"
on a thermal line than an independent thermal derivation that appears
nowhere in this repo.

**Verdict: STALE / MISCATEGORIZED.** Neither the thermal rationale (cap
is ceramic, not electrolytic; resistor dissipation is ~0.15-0.25W, not
watts) nor a plausible reapplication as an electrical clearance rule
(same floating domain, no barrier) holds up. **The board's actual 3.13mm
gap is not a violation of any real requirement this investigation could
identify.** Config edit made below (`thermal_management.yaml`), reasoning
recorded inline; the sibling `R_GATE_LOW`/`C_VCC1` line was already
flagged unresolvable in the prior document (`C_VCC1` has no real
counterpart in this topology) and is left as-is here.

---

## Summary table

| # | Constraint | Real or stale | Derived figure | Board violates derived requirement? |
|---|---|---|---|---|
| 1 | IGBT alignment for shared heatsink | **Real** | Exact mm tolerance not derivable (no `HS1` mechanical drawing in-repo); qualitatively, current placement fails by a wide margin on *two* axes, one (90° rotation mismatch) the declared constraint didn't even check | **Yes — violated**, and by more than the declared framing shows |
| 2 | Heatsink NTC adjacency | **Stale as written** (PCB distance meaningless for a flying-lead part); underlying safety intent real and unresolved | Cannot derive — needs chassis/heatsink-to-PCB mechanical drawing (not in repo) to check against the real 38.1mm lead budget | **Cannot determine** — flagged prominently as an open THM-01 (mains over-temp protection) question, not resolved either way |
| 3 | Gate resistor / bootstrap cap clearance | **Stale / miscategorized** | `R23` dissipation ≈0.13–0.25W (derived from real `Q_G`=185-240nC, 15V rail, 47kHz — supersedes the code's own unsourced 0.25W constant with a grounded figure of the same order); `C17` is 125°C-rated X7R ceramic, not electrolytic; "8mm" matches this repo's own reinforced-creepage constant used 9+ times elsewhere for an unrelated (cross-domain electrical) purpose | **No** — no real requirement identified for the board to violate |

## Config change

`packages/temper-placer/configs/constraints/thermal_management.yaml`: the
`R_GATE_HIGH`/`C_VCC2` constraint (lines 81-87 as previously written) is
rewritten to record this investigation's finding inline rather than
deleted outright, per the task's instruction to make the reasoning
visible where a constraint is removed as unenforceable. Constraints 1 and
2 are left untouched — 1 because it is real and violated (reported below,
not weakened), 2 because rewriting it would require deciding the open
lead-reach question this document could not resolve, and guessing at a
replacement number here would create exactly the kind of unbacked figure
this whole investigation was launched to find.

## What remains open (not resolved here, on purpose)

- **Constraint 1** is a hardware/placement finding: `U5`/`U6` need
  correction on both position (currently ~74mm edge-distance mismatch) and
  **rotation** (currently 90° apart) before a single `HS1` heatsink face
  can contact both tabs. This is not a config-loosening opportunity — it
  is a real board defect.
- **Constraint 2** needs a chassis/enclosure mechanical drawing (heatsink
  position relative to the PCB) that does not exist in this repo, to
  determine whether the NTC's 38.1mm lead budget can actually reach the
  installed `HS1` body. Until that exists, THM-01's real-world efficacy
  cannot be confirmed from this repo alone — flagged for the hardware/
  mechanical owner as a safety-relevant gap, not asserted as either
  passing or failing.
- **`HS1`'s own mechanical drawing** (hole pattern, mounting-face
  dimensions) is not in-repo (`datasheets/` has no Wakefield-Vette file);
  without it, constraint 1's *exact* correct tolerance number cannot be
  computed, only its qualitative violation.
- **UCC21550's internal output-stage resistance** is not recorded in this
  repo; the gate-resistor power derivation above is therefore an upper
  bound (assumes negligible driver-side resistance), not an exact split.
  This does not change the conclusion (even the full upper bound is
  ~0.17-0.25W, far below any level that would threaten a 125°C-rated
  ceramic), but is noted so the number isn't read as more precise than it
  is.

# SELV Isolation Redesign — Floating the Control Domain, Removing the Star Join

**Date:** 2026-07-26
**Scope:** `elec/src/main.ato`, `elec/src/modules.ato`, `elec/src/components.ato`
**Trigger:** `docs/hardware/IEC60335_CRITICAL_COMPONENTS.md` §2 and the "isolation
barrier is shorted by the star-point join" entry in `docs/STRATEGY.md`
identified that `power_return ~ gnd` (a single-point star join) shorted the
Mean Well IRM-10-15 auxiliary supply's 4.2 kVAC isolation barrier, tying the
MCU, safety interlock, and user-touchable RTD probe to a node that tracks AC
Neutral. The user decided: remove the star join and float the SELV domain
properly. This document is the record of that change.

**A note on scope before anything else:** this document describes the
codebase actually found in this worktree at the time of the change. Some
detail supplied in the task brief (specific resistor values for OVP-01, a
`CoilThermalComparator`/THM-02 module, a `SecondaryOCPComparator`/OCP-02
module) does not exist in this revision of `elec/src/modules.ato` — this was
verified directly by reading the file, not assumed. Everything below is
reported against what is actually committed here, with any mismatch from the
brief called out explicitly where it matters (principally the OVP-01
section).

---

## 1. Falsifier, stated before implementing

**Falsifier:** *If, after this change, `elec/build/default.net` still shows
the SELV ground (`gnd`) and the HV power return (`power_return` /
`PWR_RTN`) collapsed into a single net record — or if any non-isolation-device
component appears with pins on both nets — the domain has not actually been
floated, regardless of what the source diff appears to do.*

**Result: the falsifier did NOT fire.** Verified directly against the built
netlist (§6). `gnd` and `PWR_RTN` are two separate net records. The only
component reference designators with pins on both are `C6` (the pre-existing
Y1 PE-bonding capacitor), `PS1` (the AuxSupply's IRM-10-15 module — ACN on
`PWR_RTN`, VN on `gnd`, i.e. its own primary/secondary split), `T1` (the
current-sense transformer — primary on `PWR_RTN`, secondary on `gnd`), and
`U3` (the new H11L1 optocoupler added in this change — LED cathode on
`PWR_RTN`, output-side GND on `gnd`). Every one of these is a deliberate
isolation device straddling the barrier by design; none is a short.

---

## 2. What was removed

```
main.ato: power_return ~ gnd  # Single-star-point ground join near doubler caps
```

deleted. Before this change, `gnd` (SELV) and `power_return` (the Delon/cascade
voltage-doubler midpoint, which tracks AC Neutral through the common-mode
choke, `modules.ato: ac_n ~ cmc.W2_1 ~ dc_bus.gnd_ref`) were the same net.
After: they are not.

---

## 3. SELV ground reference decision: bond `gnd` directly to PE

A floated SELV domain with **no** defined reference is not safe either — it
capacitively couples to nearby HV nodes and drifts with EMI, which is exactly
the failure mode a floating domain is supposed to avoid. A reference had to
be chosen, and the choice was: **bond `gnd` directly (0 Ω, DC) to protective
earth (`pe`)**, not to `power_return`.

New signal and connections (`main.ato`):

```
signal pe            # Protective earth, from the external AC connector
...
power_in.pe ~ pe
...
gnd ~ pe  # SELV ground reference: bonded to protective earth, NOT to power_return
```

**Reasoning, checked against the existing Y-cap arrangement rather than
asserted:**

- PE already physically exists at the AC input connector and already has a
  bond point on the HV side: `modules.ato`'s Y1 capacitor,
  `dc_bus.gnd_ref ~ y_cap_pe ~ pe` (2.2 nF, "Class I appliance pattern...
  without a DC short," per its own comment). Extending the same physical PE
  conductor to also directly bond `gnd` is the minimal-new-hardware option
  and reuses a conductor this design already treats as a real safety
  reference.
- This is the standard answer for a Class I appliance (PE present) with an
  internal SELV domain: it gives the domain a real, low-impedance reference,
  and it means a *single* HV→SELV insulation fault has a low-impedance fault
  path to trip branch overcurrent protection, rather than leaving an
  ungrounded domain — which includes the user-touchable RTD probe — free to
  rise to a dangerous potential with nothing to trip.
- **Checked, not asserted, against the Y-cap:** the Y1 cap's job
  (`power_return` → PE, high-impedance, AC/EMI-only, explicitly "without a DC
  short" per its own comment) is completely undisturbed. The new `gnd`→PE
  bond is a separate, direct wire that never touches `power_return`.
  `power_return` and `gnd` remain two different nets at DC, coupled only
  through whatever impedance exists PE → Y-cap → `power_return` — i.e. still
  isolated at DC, which is the entire point of this change. There is no
  "capacitor in series with the bond" conflict: the Y-cap stays where it was,
  doing what it did.
- **EMC implication, checked rather than assumed:** referencing the
  low-power digital domain to PE/chassis instead of to the internally
  generated, AC-N-tracking `power_return` is the more common and generally
  quieter choice — PE/chassis tends to act as a more stable reference plane
  than a node that moves with line current. The one real requirement this
  creates, and one this schematic cannot itself enforce, is a **layout
  requirement**: the `gnd`→PE bond and the Y-cap's `power_return`→PE bond
  should land at the same physical PE stud/point near the AC inlet, to keep
  the loop area between the two earth references small. **UNVERIFIED at the
  schematic level** — flagged for the layout stage, not resolved here.

---

## 4. Complete crossing survey

Every crossing was re-derived from source in this pass (not copied from the
brief) and cross-checked against the brief's list. Table below states, per
crossing: what it is, its disposition, and the evidence.

| # | Crossing | Source location | Disposition | Evidence |
|---|---|---|---|---|
| 1 | **AuxSupply transformer (the barrier itself)** | `modules.ato: AuxSupply`, `psu = new IRM_10_15` | **Isolated.** Mean Well IRM-10-15, 4.2 kVAC I/O withstand, IEC/EN 61558-1/-2-16 + 62368-1 (per `IEC60335_CRITICAL_COMPONENTS.md`). Now that the star join is gone, this barrier is no longer shorted. | Netlist: `PS1` pin 2 (ACN) on `PWR_RTN`, pin 4 (VN) on `gnd` — two different nets, as designed. |
| 2 | **ZCD divider → MCU** | `modules.ato: PowerInput`, was `power_in.zcd ~ mcu.zcd_in.line` | **Newly isolated.** Added an H11L1 optocoupler (verified datasheet: Everlight H11LX series, DPC-0000022 Rev 5). LED (driven by the existing HV-side divider + zener clamp through a new 430 Ω series resistor, ~5 mA, >3× the 1.6 mA guaranteed turn-on threshold) stays on the HV side, referenced to `dc_bus.gnd_ref`. Output (open-collector, 10 kΩ pull-up to `vcc_3v3`) is SELV. This was the project's own pre-existing TODO ("Option A: Add optocoupler (H11L1)"); this change implements it. | Netlist: `ZCD_ISO` net = `{U23.38 (MCU IO13), U3.4 (opto Vo), R10.2 (pull-up)}` — zero HV pins. `U3` (the opto) itself straddles `PWR_RTN`↔`gnd` only through its own internal isolation, confirmed above. |
| 3 | **OVP-01 bus sense (comparator divider)** | `main.ato: safety.dc_bus.line ~ dc_bus_plus`, `safety.dc_bus.reference ~ gnd`; `modules.ato: OVPComparator` r_div_top1-3/r_div_bot | **STILL CROSSING — not fixed.** The divider (3×430 kΩ over 10 kΩ, ~1.3 MΩ total) runs from `dc_bus_plus` (HV) to `power.gnd`, which chains to Top's `gnd` (now floated SELV, PE-bonded). This is a real, if high-impedance, resistive bridge across the barrier. See §5 for why this was not fixed in this pass. | Netlist: `+170V_BUS` net includes `R51.1` (one of the three 430 kΩ dividers); the corresponding bottom leg lands on `gnd` (confirmed: OVPComparator's `r_div_bot.p2 ~ power.gnd`, which chains through `SafetyInterlock.power_3v3.gnd` to Top `gnd`). |
| 4 | **OVP-01 ADC bus sense (second, independent divider)** | `modules.ato: OVPComparator.adc_v_bus` (510 kΩ / 10 kΩ) | **STILL CROSSING — not fixed. Not in the brief's table; found in this pass.** A second, independent resistive path from the same `dc_bus_plus` node into `power.gnd`, feeding the MCU's bus-voltage ADC input. Same disposition and same reasoning as #3 — it is a second instance of the identical problem, not a duplicate. | Netlist: `R57` (510 kΩ, `r_adc_top`) pin 1 on `+170V_BUS`; `R58` (10 kΩ, `r_adc_bot`) pin 2 confirmed on `gnd`. |
| 5 | **Gate drivers (UCC21550)** | `modules.ato: HalfBridge`; `main.ato: hb.power_15v.gnd ~ gnd` | **Already isolated, confirmed (not just asserted).** UCC21550BDW, 5 kVrms reinforced isolation (UL FPPT2.E181974, per `IEC60335_CRITICAL_COMPONENTS.md`). GNDI/VCCI (primary/control side) are on `gnd`; VSSA (floats on `switch_node` via the negative-bias zener) and VSSB (`dc_bus.hv_minus`) are the secondary/floating side and are **not** on `gnd`. | Netlist: `U7` (the UCC21550) pin 4 (GNDI) = `gnd`; pin 9 (VSSB) = `DC_BUS_RTN`; pin 14 (VSSA) = a separate local net (`hb.gate_hs.driver-p2`, the zener-clamped rail below `SW_NODE`) — confirmed absent from `gnd`. |
| 6 | **Current sense CT (T1)** | `main.ato: ct_sense.primary_out ~ power_return` (primary), `ct_sense.i_sense.reference ~ gnd` (secondary) | **Already isolated, confirmed.** CST2010-100L current transformer — inherently isolated by construction (1500 Vrms winding-winding, per its own component comment). Primary (tank return current) and secondary (burden/bias) are physically separate windings. | Netlist: `T1` pin 2 (primary) = `PWR_RTN`; pin 4 (secondary) = `gnd`. Two different nets, bridged only by the transformer's magnetic coupling. |
| 7 | **Bus discharge relays (K_DIS1/K_DIS2)** | `modules.ato: BusDischarge` | **Already isolated, confirmed.** Omron G5LE-1 SPDT: coil (SELV, `power_15v`/`gnd`) drives the NC contacts (HV, `hv_plus`/`mid`/`hv_minus`) through the relay's mechanical/dielectric isolation — coil-contact dielectric 2000 VAC, impulse 4.5 kV (per the module's own verified comment), comfortably above the ≤170 VDC the contacts actually break. | Source-level: `BusDischarge` declares `hv_plus`/`mid`/`hv_minus`/`gnd` as entirely separate signal namespaces, connected only via `k_dis1`/`k_dis2`'s coil↔contact relay isolation, never a direct net tie. |
| 8 | **Bypass relay (mains soft-start, K_BYPASS / bypass_relay)** | `modules.ato: PowerInput` | **Already isolated, confirmed.** Same pattern as #7: Omron G4A-1A-E, coil driven from SELV (`power_15v`/`gnd` via `q_relay_drv`), contacts (`COM`/`NO`) switch the HV AC line path. | Source-level: `bypass_relay.COM`/`NO` only ever connect to `cmc`/`d1` (HV); coil pins (`coil1`/`coil2`) only ever connect to `r_relay_drop`/`d_flyback`/`q_relay_drv` (SELV). No shared net. |
| 9 | **Mains relay control (`power_in.gnd ~ gnd`)** | `main.ato` | **Confirmed: coil return only, not an HV return.** `power_in.gnd` inside `PowerInput` is used only by the relay gate-driver MOSFET source, the gate pulldown, and the coil-supply return (`power_15v.gnd`) — never by any AC_L/AC_N/rectifier node. | Source-level: grep of every use of `gnd` inside `PowerInput` confirms it touches only `r_gate_pd.p2`, `q_relay_drv.S`, `power_15v.gnd` — none of which are HV nodes. |
| 10 | **Heatsink NTC (NTC_HS)** | `modules.ato: ThermalComparator`; heatsink is chassis BOM | **Isolated by the sensor's own construction; installation UNVERIFIED.** The divider (`ntc.p1`/`ntc.p2`) is entirely SELV (`power.vcc`/`power.gnd`). The NTC itself (Vishay NTCALUG01A104GA) has a documented 1500 VAC lug-to-terminal isolation rating (`IEC60335_CRITICAL_COMPONENTS.md`, confirmed from the datasheet) — so even if the heatsink it's bolted to sits at some elevated or floating potential (it's separated from the IGBT tabs by Sil-Pads, per `ThermalSystem`'s docstring, chassis BOM, not in `elec/src`), the sensing terminals stay isolated from the lug up to 1500 VAC by the part's own construction. **UNVERIFIED:** correct physical Sil-Pad installation and the resulting heatsink potential are mechanical/chassis-level facts this schematic cannot confirm. |
| 11 | **Coil NTC** | Not present in this codebase | **N/A in this revision.** The brief's crossing table lists a `CoilThermalComparator`/THM-02 module with a coil-mounted NTC. This does not exist anywhere in `elec/src/modules.ato` in this worktree (confirmed by `grep -n "CoilThermalComparator\|THM-02" elec/src/*.ato` returning no matches) — only the heatsink `ThermalComparator` is present and wired. Reported as a discrepancy from the brief rather than silently reconciled; if THM-02 is added later, its sensor mounting will need the same isolation review as #10, and — per the BOM's own note that the heatsink instance uses the lug package while a coil instance would use a plain axial footprint — should not assume the same 1500 VAC lug-to-terminal credit without checking which footprint/package is actually specified. |
| 12 | **OCP-02 / secondary current sense** | Not present in this codebase | **N/A in this revision.** `SecondaryOCPComparator` does not exist in `elec/src/modules.ato` in this worktree (confirmed by grep, no matches). Not part of this change. |
| 13 | **AuxSupply.enable** | `modules.ato: AuxSupply` | **Not a live crossing.** `enable.reference ~ power_in.gnd` (HV side) is declared but `enable.line` is never connected to anything in `Top` (`main.ato`) — it's a dangling, non-required `ElectricLogic`. No current path exists across it either way. | Source-level: no `aux_supply.enable` reference anywhere in `main.ato`. |
| 14 | **USB / I2C UI nets** | `main.ato: usb_dn/usb_dp/i2c_sda_ui/i2c_scl_ui` | **Not currently a physical crossing.** These are SELV (MCU-referenced) and bare, unconnectored signals — no physical USB or I2C connector is instantiated anywhere in `elec/src` (matches `IEC60335_CRITICAL_COMPONENTS.md`'s own finding). Noted for completeness: if a connector is ever populated at the enclosure boundary, it becomes a new user-accessible interface needing its own ESD/surge review, separate from the HV/SELV barrier this document addresses. | Source-level: no connector component instantiated on these nets. |

**Net count of "still crossing" items after this change: 2** (rows 3 and 4,
both parts of OVP-01's bus sensing). Everything else is either already
isolated by a real component with a checked rating, structurally isolated by
the module's own signal namespace, not a live crossing today, or not present
in this codebase revision.

---

## 5. OVP-01: the 170 V / 340 V question, resolved from source

**What was asked:** does the OVP divider actually sense 170 V while being
calibrated for 340 V, invalidating OVP-01's trip point by 2×?

**Resolved, directly from source, independent of any comment:**
`dc_bus_plus` (what `safety.dc_bus.line` senses) is the **positive
half-bus of the Delon/cascade voltage doubler** (`PowerInput`), referenced to
`power_return`/`dc_bus.gnd_ref` — the doubler **midpoint** — not to
`dc_bus_minus`. Proof that does not depend on any comment: `PowerInput`'s own
`c_bus1` is sized against `v_bus_half` (170 V), not the 340 V full bus —
`assert c_bus1.voltage_rating >= v_bus_half * 1.25` (250 V ≥ 212.5 V passes;
against 340 V it would need 425 V and fail). `dc_bus_plus - dc_bus_minus`
spans the full 340 V bus; `dc_bus_plus` alone is +170 V nominal.

**But — checked against what is actually committed here, not assumed from
the brief:** in this worktree's `OVPComparator`, `r_ref_top = 12 kΩ`,
`r_ref_bot = 10 kΩ` (V_ref = 1.50 V), and **there is no hysteresis resistor
at all** in this revision (a separate, pre-existing gap, not touched here).
The module's own inline comment already treats `v_bus.line` as the half-bus
and explicitly doubles the result: *"V_bus_half_trip = 1.50 × 130 = 195V;
V_bus_full_trip = 195V × 2 = 390V."* Recomputing independently: divider ratio
10 kΩ / (3×430 kΩ + 10 kΩ) = 1/130; trip when `dc_bus_plus` reaches
1.50 V × 130 = **195 V** — a sensible ~15% margin over the 170 V half-bus
nominal, comfortably under the 250 V-rated bus capacitors. **This is
correctly calibrated for a half-bus sense**, and is *not* fail-open in this
codebase.

**The actual bug that was present, and is fixed here, was the net name, not
the resistor values.** `main.ato` declared `dc_bus_plus.override_net_name =
"+340V_BUS"` with a `# +340V` comment. That name asserts exactly the wrong
thing about the node — and it is precisely the kind of error that, if trusted
instead of the topology, would lead someone to retune `r_ref_top` for a
340 V-nominal reading (e.g. to ~1.1 kΩ / 2.97 V), which would move the real
trip point to ~390-400 V on a node that physically cannot exceed roughly
170-250 V without the bus capacitors having already failed — making OVP-01
fail-open. **Fixed in this change:** the net renamed to `+170V_BUS` with a
comment stating the half-bus reality and pointing at this document; the
`aux_supply.power_in.vcc ~ dc_bus_plus # Half-bus input (~170VDC)` comment
(already correct) is now consistent with the renamed net instead of
contradicting it; `OVPComparator`'s docstring rewritten to state the
half-bus identity, show the derivation, and warn explicitly against
retuning `r_ref_top` toward a 340 V-referenced value.

**Two remediation options for the still-crossing sense path (§4, rows 3-4),
laid out rather than implemented, per instruction not to unilaterally
re-tune or add an isolator without a design decision:**

| Option | Description | Consequence |
|---|---|---|
| **A. Half-bus sense, HV-side comparator, isolated fault flag** | Keep sensing `dc_bus_plus` relative to `power_return` (matches the existing 12k/1.5V calibration, which is already correct for this). Move the comparator itself to the HV side, referenced to `power_return`, powered from a new small HV-referenced bias supply (does not exist today — a real part addition). Carry only the resulting digital fault bit across the barrier via an opto (same pattern as the ZCD fix in this change). | Smaller isolator (digital, not linear), reuses a calibration that's already right. Requires a new low-power supply referenced to `power_return` specifically (neither the existing `vcc_15v_ls`, which floats on `hv_minus`, nor anything else in this design floats on `power_return` today) — a real, nontrivial addition. |
| **B. Full differential bus sense** | Sense `dc_bus_plus - dc_bus_minus` (the true full 340 V bus) with an isolated amplifier (e.g. AMC1311/AMC1301-class, already named as a candidate class elsewhere in this codebase for the unrelated OCP-02 problem). | Directly matches the top-level `v_ovp_trip = 390V` spec without the half/full mental translation this document had to do. Needs a reference at `dc_bus_minus`/`hv_minus` — a *second* isolation domain (this design already treats `hv_minus`-referenced circuits, e.g. `power_15v_ls`, as a domain distinct from both `gnd` and `power_return`), so this is not free either. |

**Recommendation: Option A.** It reuses the calibration that is already
correct in this codebase, and the "new HV-referenced bias supply" it needs is
a bounded, well-precedented piece of engineering (a small zener/linear
regulator tap off the half-bus, referenced to `power_return` — structurally
similar to what already exists for `power_15v_ls` off `hv_minus`), versus
Option B's need for a second, different isolated-amplifier part and a
`hv_minus`-referenced sense network. **Not implemented in this change** —
both options require a real part addition (a bias supply plus an opto, or an
isolated amplifier) that was not verified against a datasheet in this pass,
per the instruction to add real parts properly or leave them stated as
unimplemented.

**Bus-imbalance question, flagged as asked:** sensing only the positive
half-bus (either as currently wired, or under Option A) cannot detect a fault
where the two half-buses diverge — e.g. one leg's capacitor bank degrades or
one rectifier diode leg fails such that only the *negative* half-bus rises.
**This matters for OVP-01's purpose.** The doubler's own symmetry (both
halves fed from the same AC diode pair driven by the same line) makes a
purely one-sided overvoltage fault less likely than a symmetric one, but it
is not impossible (e.g., an unbalanced load between the two bus-discharge
strings, or an aged capacitor in only one bank) and a single-rail sense would
miss it. Option B (full differential sense) does not have this blind spot.
This is a real gap in both the current wiring and Option A, not fixed here.

---

## 6. Netlist evidence

`make netlist` (foreground, `elec/src/main.ato:Top`) — **exit 0**, no
assertion failures (76/76 PASSED, 0 FAILED; verified by grepping the build
log for `FAILED`, which returns nothing). `make schematics` — exit 0, oracle
pass: "463 pin assignments, 98 nets -- connectivity partitions isomorphic."

Positive confirmation the grounds are separate (from `elec/build/default.net`,
parsed programmatically, not eyeballed):

```
net 1  "gnd"       74 pins  (SELV: MCU, RTD ADC, safety comparators, gate-
                              driver control side, opto output side, etc.)
net 2  "+170V_BUS"  11 pins  (HV: renamed from "+340V_BUS")
net 6  "PWR_RTN"    17 pins  (HV: power_return / doubler midpoint)
```

Overlap check — reference designators appearing in *both* the `gnd` and
`PWR_RTN` node lists:

```
C6   -- y_cap_pe (Y1 cap): p1 on PWR_RTN, p2 on gnd  (pre-existing, unchanged)
PS1  -- IRM-10-15 (AuxSupply): ACN(2) on PWR_RTN, VN(4) on gnd
T1   -- CST2010-100L (current sense transformer): primary(2) on PWR_RTN, secondary(4) on gnd
U3   -- H11L1 (new, this change): cathode(2) on PWR_RTN, GND(5) on gnd
```

No other reference designator appears on both nets. Every overlap is a
deliberate isolation device (capacitor, transformer, transformer, or
optocoupler) straddling the barrier by pin, never by a direct tie. This is
the positive, netlist-level proof the falsifier in §1 asked for.

---

## 7. ERC results

`kicad-cli sch erc --severity-all --format report -o <file> pcb/temper.kicad_sch`
(the hierarchical root sheet, covering all 6 sub-sheets including
`power_input.kicad_sch` and `safety_interlock.kicad_sch`) — **exit 0**.

**447 violations, all severity `warning`, zero `error`.** All 447 fall into
exactly three categories, verified by extracting every distinct violation
type in the report:

- `lib_symbol_issues` (152) — "the current configuration does not include
  the symbol library ''" — every symbol in the design, including
  pre-existing ones, is flagged; this is an artifact of the sandbox's KiCad
  environment not having a symbol-library table configured, not a design
  defect.
- `footprint_link_issues` (149) — "the current configuration does not
  include the footprint library '<X>'" for every footprint family used
  (`Capacitor_SMD`, `Resistor_THT`, `Package_DIP`, etc.) — same root cause.
  `Package_DIP` appears in this list because the new H11L1 (`U3`) is the
  first DIP-6 part in the design; it gets the identical warning class every
  other part already gets, not a new kind of finding.
- `endpoint_off_grid` (146) — cosmetic pin/wire grid-snapping artifacts from
  `gen_schematics.py`'s auto-placement, pre-existing for other parts too.

**No violation of any electrically-meaningful type** (no floating power pin,
no pin-not-driven, no conflicting drivers, no unconnected required pin)
appears anywhere in the report. `U3` (the new opto) is flagged only with the
same two generic library warnings and one grid warning every other component
receives — nothing specific to its isolation function or wiring. **This is
reported honestly as a mostly-inconclusive ERC result on real electrical
topology**, because the sandbox's KiCad has no configured symbol/footprint
libraries and can't check ratsnest-level connectivity issues that require
resolved symbols — but it is a clean result on everything ERC in this
environment is actually able to check, and it introduced no new violation
class.

---

## 8. `elec/src/*.ato` changes (committed)

- `main.ato`: added `signal pe`; renamed `dc_bus_plus`'s net to `+170V_BUS`
  with a corrected comment; deleted `power_return ~ gnd`; added
  `gnd ~ pe`; added `power_in.pe ~ pe` and `power_in.vcc_3v3 ~ vcc_3v3`;
  rewrote the "GROUND ARCHITECTURE" comment block; repointed the ZCD
  connection at `power_in.zcd_out.line` instead of the now-internal-only
  `power_in.zcd`.
- `modules.ato`: added `import H11L1`; added `vcc_3v3` and `zcd_out` to
  `PowerInput`; added the opto LED-drive and output-pullup circuit in the ZCD
  section, replacing the stale TODO; rewrote `OVPComparator`'s docstring with
  the half-bus derivation and the two remediation options; rewrote
  `RTDSensing`'s docstring (item 9 below).
- `components.ato`: added the `H11L1` component (verified pinout, see §4
  row 2).
- `pcb/*.kicad_sch`: regenerated via `make schematics` (generated files, not
  hand-edited, per the header in `scripts/gen_schematics.py`).

## 9. `RTDSensing` docstring

Updated to state what is actually true after this change: the RTD probe is
SELV, galvanically isolated from HV by the AuxSupply transformer, and now
referenced to PE rather than to AC Neutral (since the star join is gone) —
but the unqualified claim "separated from AC mains potential" was removed,
because it is not yet fully true end-to-end while the OVP crossing (§4 rows
3-4) still bridges `gnd` resistively back toward the HV half-bus. The new
docstring says this explicitly rather than repeating a claim the netlist
would still only partially support.

---

## 10. What remains unresolved, ranked

1. **OVP-01 bus-sense crossing (§4 rows 3-4).** Two resistive paths
   (~1.3 MΩ and ~520 kΩ) still connect the HV half-bus into the floated SELV
   ground. This is the single largest remaining item — it means `gnd` is not
   yet on a domain with zero galvanic connection to HV, only a
   high-impedance one. Two options laid out in §5, neither implemented.
2. **OVP-01 has no hysteresis resistor** in this revision (`r_hyst` does not
   exist). Pre-existing, not introduced by this change, not fixed here —
   flagged because it compounds with #1 (an unstable trip near threshold
   makes the resistive HV/SELV bridge see more transient current, not less).
3. **Layout requirement for the new `gnd`→PE bond** (§3): must land at the
   same physical PE point as the Y-cap's `power_return`→PE bond to keep loop
   area small. UNVERIFIED — a PCB-layout fact, not a netlist one.
4. **H11L1's PCB creepage/clearance across the barrier** is UNVERIFIED. The
   5000 Vrms Viso figure confirmed from the datasheet is a 1-minute
   dielectric withstand spec, not independently confirmed here as a
   reinforced-insulation-coordination rating (creepage/clearance in mm) at
   this design's working voltage. Needs layout-stage verification, same
   category as the CT1 finding in `IEC60335_CRITICAL_COMPONENTS.md`.
5. **ZCD opto timing** (LED drive current, rise/fall through the H11L1) is
   sized by hand-calculation, not bench-verified against the soft-start
   timing budget the original raw-ADC ZCD approach used. Flagged, not
   assumed correct.
6. **Heatsink NTC and any future coil NTC installation** (§4 rows 10-11):
   isolation credit depends on correct physical Sil-Pad installation
   (heatsink) and, if a coil sensor is ever added, on confirming which
   package variant (lug vs. plain axial) is actually used — chassis/assembly
   facts this schematic cannot verify.
7. **`CoilThermalComparator`/THM-02 and `SecondaryOCPComparator`/OCP-02 do
   not exist in this codebase revision**, despite being referenced in the
   task brief's crossing list. Reported as a discrepancy, not silently
   reconciled — if/when those modules are added, they need this same
   isolation review from scratch, not an assumption that this document
   already covered them.
8. **Bus-imbalance blind spot for OVP-01** (§5): sensing only one half-bus
   cannot catch a fault where the two halves diverge. True today and true
   under remediation Option A; not true under Option B.

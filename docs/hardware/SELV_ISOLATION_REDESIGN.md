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

**A note on scope before anything else:** this work was originally done
against a worktree that turned out to be based on a stale point in
`docs/methodology-loop-discipline` — it predated `CoilThermalComparator`
(THM-02), `SecondaryOCPComparator` (OCP-02), and `LogicUVLOComparator`
(UVL-02) all landing on that branch, and predated a retune of `OVPComparator`
that this document had originally (and, on that stale tree, correctly)
described as already-sensible. The worktree has since been rebased onto the
current tip of `docs/methodology-loop-discipline` (verified: `git log
--oneline -1` → the commit is on top of that branch's tip; `grep -c "module
CoilThermalComparator\|module SecondaryOCPComparator\|module
LogicUVLOComparator" elec/src/modules.ato` → all three present), and every
finding below — the crossing table, the OVP section, the netlist pin counts,
and the ERC numbers — was re-derived against the rebased tree, not carried
forward from the stale one. Where the stale-tree version of this document
said something that the rebased tree contradicts, that is called out
explicitly rather than silently corrected (see §5 in particular).

---

## 1. Falsifier, stated before implementing

**Falsifier:** *If, after this change, `elec/build/default.net` still shows
the SELV ground (`gnd`) and the HV power return (`power_return` /
`PWR_RTN`) collapsed into a single net record — or if any non-isolation-device
component appears with pins on both nets — the domain has not actually been
floated, regardless of what the source diff appears to do.*

**Result: the falsifier did NOT fire, on the rebased tree.** Verified
directly against the built netlist (§6), regenerated after rebasing onto the
current tip of `docs/methodology-loop-discipline` (which adds
`CoilThermalComparator`/THM-02, `SecondaryOCPComparator`/OCP-02,
`LogicUVLOComparator`/UVL-02, and several BOM part-number replacements on top
of what this document was originally checked against). `gnd` (80 pins, up
from 74 pre-rebase — the two new fully-SELV comparator modules, THM-02 and
UVL-02, each add SELV-only pins) and `PWR_RTN` (17 pins, unchanged) are two
separate net records. The only component reference designators with pins on
both — unchanged by the rebase — are `C6` (the pre-existing Y1 PE-bonding
capacitor), `PS1` (the AuxSupply's IRM-10-15 module — ACN on `PWR_RTN`, VN on
`gnd`), `T1` (the current-sense transformer — primary on `PWR_RTN`, secondary
on `gnd`), and `U3` (the H11L1 optocoupler added in this change — LED cathode
on `PWR_RTN`, output-side GND on `gnd`). Every one of these is a deliberate
isolation device straddling the barrier by design; none is a short. Neither
of the two new live SELV modules (THM-02, UVL-02) introduced a new overlap —
consistent with both being entirely internal to the SELV domain (§4).
OCP-02 is not instantiated (§4), so it contributes nothing to the netlist at
all yet.

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
| 11 | **Coil NTC (THM-02, `CoilThermalComparator`)** | `modules.ato: CoilThermalComparator`; instantiated and wired in `SafetyInterlock` (`coil_thermal = new CoilThermalComparator`, `coil_thermal.power ~ power_3v3`, `coil_thermal.fault.line ~ fault_any_or.C1`) | **Isolated by the sensor's own construction, same as row 10; installation UNVERIFIED.** The `ntc` element is instantiated *inside this module* (`ntc.mpn = "NTCALUG01A104GA"` — the identical part, and identical 1500 VAC lug-to-terminal isolation credit, as the heatsink sensor), entirely SELV-referenced (`power.vcc`/`power.gnd`). It is meant to be thermally mounted to the coil — part of the resonant tank, which swings at HV/switch-node potential — at PCB/mechanical assembly time. Because the isolation is a property of the NTC part itself (lug vs. sense-terminal internal isolation), not of the schematic wiring, the SELV sense circuit is isolated from whatever potential the coil surface is at, **provided** the part is actually mounted so its lug (not its sense leads) makes any incidental contact. **UNVERIFIED:** correct mechanical mounting/creepage against the coil is a chassis/assembly fact this schematic cannot confirm — same category and same caveat as row 10, not a new kind of gap. Note: `SafetyInterlock.coil_ntc_sense` (the MCU-visible analog tap, mirroring `ntc_sense` for the heatsink) is declared but never connected to anything in `main.ato` — firmware has no readout of coil temperature, only the hardware comparator trip. That is a completeness gap, not an isolation gap. | Netlist: confirmed no new overlap between `gnd` and `PWR_RTN` after this module's parts were added (§1, §6) — `gnd` grew from 74→80 pins, `PWR_RTN` unchanged at 17, with the same 4 straddling designators. Source: `grep -n "coil_ntc\|coil_thermal" elec/src/modules.ato elec/src/main.ato` confirms `coil_thermal.power ~ power_3v3` and no Top-level connection for `coil_ntc_sense`. |
| 12 | **OCP-02 / secondary current sense (`SecondaryOCPComparator`)** | `modules.ato: SecondaryOCPComparator`; **NOT instantiated** in `SafetyInterlock` — `# ocp2 = new SecondaryOCPComparator` is commented out, along with its power/bus connections and its fault test point | **Dormant — not a live crossing today, but self-documents a real future one.** The module is defined (shunt in `DC_BUS_RTN`, INA240A1 current-sense amp, TLV3201 comparator) but never instantiated, so nothing about it appears in the netlist and it does not interact with `gnd` or `power_return` at all right now. Its own docstring already flags, in detail, that *if* it is ever wired up with `power ~ power_3v3` (the pattern every other comparator in this design uses), the INA240A1's `REF1`/`REF2`/`GND` pins — tied to `power.gnd` in the module — would sit at roughly **-170 V common-mode** against `DC_BUS_RTN` (since `dc_bus_minus` is the negative half-bus, ~-170 V relative to `power_return`, and `power.gnd` would be the SELV `gnd`, no longer even nominally close to `power_return` now that the star join is gone) — far outside the INA240A1's -4 V to +80 V absolute maximum, and likely destructive. This SELV-float change does not create that problem (the module isn't live) and does not fix it either; it is an orthogonal, already-flagged, pre-existing design gap that whoever instantiates OCP-02 in the future must resolve (isolated supply + isolated fault path referenced to `DC_BUS_RTN`, per the module's own docstring) rather than wiring it to `power_3v3` as written. | Netlist: `grep -n "ocp2 = new\|ocp2\\.power" elec/src/modules.ato` shows both commented out; no `ocp2`/`SecondaryOCPComparator`-associated reference designator appears anywhere in `elec/build/default.net`. |
| 13 | **UVL-02 logic-rail UVLO (`LogicUVLOComparator`)** | `modules.ato: LogicUVLOComparator`; instantiated and wired in `SafetyInterlock` (`uvlo_logic = new LogicUVLOComparator`, `uvlo_logic.power ~ power_3v3`) | **Not a crossing at all — entirely internal to SELV.** This module monitors `power_3v3` (the board's own SELV logic rail) against the TPS3700's internal ~394.5 mV bandgap-derived reference; both its power and its sense divider are `power.vcc`/`power.gnd`, which are `power_3v3`'s vcc/gnd — already SELV before and after this change. No HV node is read, driven, or referenced anywhere in this module. `uvlo_logic.fault.line` is deliberately routed only to a test point (`SafetyInterlock.tp_uvlo2_fault`), not into the fault-OR tree, because THM-02 already took the one remaining spare SET-path input — that is a documented, intentional aggregation-capacity limitation unrelated to isolation, and is **not touched by this change** (per explicit instruction). | Netlist: `uvlo_logic`'s parts (TPS3700 `mon`, dividers, `SN74LVC1G38 inv`) all resolve onto SELV nets (`gnd`/`+3V3`); none appear in the `PWR_RTN`/`+170V_BUS` overlap check in §1/§6. |
| 14 | **AuxSupply.enable** | `modules.ato: AuxSupply` | **Not a live crossing.** `enable.reference ~ power_in.gnd` (HV side) is declared but `enable.line` is never connected to anything in `Top` (`main.ato`) — it's a dangling, non-required `ElectricLogic`. No current path exists across it either way. | Source-level: no `aux_supply.enable` reference anywhere in `main.ato`. |
| 15 | **USB / I2C UI nets** | `main.ato: usb_dn/usb_dp/i2c_sda_ui/i2c_scl_ui` | **Not currently a physical crossing.** These are SELV (MCU-referenced) and bare, unconnectored signals — no physical USB or I2C connector is instantiated anywhere in `elec/src` (matches `IEC60335_CRITICAL_COMPONENTS.md`'s own finding). Noted for completeness: if a connector is ever populated at the enclosure boundary, it becomes a new user-accessible interface needing its own ESD/surge review, separate from the HV/SELV barrier this document addresses. | Source-level: no connector component instantiated on these nets. |

**Net count of "still crossing" items after this change: 2** (rows 3 and 4,
both parts of OVP-01's bus sensing). One additional item (row 12, OCP-02) is
not a live crossing today but is a self-documented crossing waiting to
happen if instantiated as currently written. Everything else is either
already isolated by a real component with a checked rating, structurally
isolated by the module's own signal namespace (including the two new fully-
SELV comparator modules, THM-02 and UVL-02, neither of which touches HV at
all), or not a live crossing today.

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

**Checked against what is actually committed on the rebased tree (this
supersedes an earlier version of this document written against a stale
worktree that had `r_ref_top = 12 kΩ` and no hysteresis resistor at all —
that configuration doesn't exist here; see the scope note at the top of this
document): `OVPComparator` currently has `r_ref_top = 1.1 kΩ`, `r_ref_bot =
10 kΩ` (giving V_ref = 3.3 × 10/11.1 = 2.973 V, before hysteresis loading),
and `r_hyst = 287 kΩ` feeding back from `comp.OUT` to the bus-sense node
`comp.INP`.**

**OVP-01 is fail-open as currently valued — confirmed by direct calculation,
not by trusting the module's own inline comment.** The module's inline
comment (`modules.ato`, above `r_ref_top.value = 1.1kohm`) derives "trip
399.8V and release 385.0V" — but derives it by treating `v_bus.line`
(`dc_bus_plus`) as if it can reach that voltage directly, which requires
`dc_bus_plus` to be the *full* 340 V bus. It is not: it is the +170 V
half-bus, proven independent of any comment via `c_bus1`'s own sizing
assertion above. Recomputing what the divider actually requires of the
physical node it senses: with `r_hyst` (287 kΩ) loading the sense node in
parallel with `r_div_bot` (10 kΩ) while the output is low, the effective
bottom-leg resistance is (10 kΩ ∥ 287 kΩ) ≈ 9.66 kΩ against a 1.29 MΩ top leg
— ratio ≈ 1/135.6. Trip requires `dc_bus_plus` ≈ 2.973 V × 135.6 ≈ **403 V**
(matching the module's own "399.8V" figure to within rounding/Thevenin
modeling differences). **`dc_bus_plus` cannot reach 400 V without the
250 V-rated bus capacitors having already failed catastrophically.** OVP-01
as currently valued cannot trip before the hardware it exists to protect is
destroyed — it is fail-open, exactly as `docs/STRATEGY.md`'s own
"OVP-01 is fail-open" entry (written independently, landed on this branch
before this rebase) concludes.

**The root cause is the same net-name error in both cases, whether the
divider is 12k/1.5V or 1.1k/287k:** `main.ato` declared
`dc_bus_plus.override_net_name = "+340V_BUS"` with a `# +340V` comment. The
1.1 kΩ/287 kΩ value's own justifying comment explicitly reasons from that
name — "the divider senses the FULL bus... main.ato declares dc_bus_plus as
+340V_BUS" — and retunes the reference to match a 340 V-nominal reading,
which is precisely how trusting a wrong net name over the actual topology
produces a fail-open comparator. The *prior* 12 kΩ/1.50 V value (preserved,
and mischaracterized as "the bug," in the same inline comment) was, per the
corrected understanding, the physically sensible one: 1.50 V × 130 = 195 V
trip at `dc_bus_plus` itself — a sensible ~15% margin over the 170 V
half-bus nominal, comfortably under the 250 V-rated caps, and consistent
with the 390 V full-bus-equivalent spec via the same "×2" relationship the
inline comment already uses for the half/full translation.

**Fixed in this change:** the net renamed to `+170V_BUS` with a comment
stating the half-bus reality and pointing at this document, so the specific
error that produced this fail-open value cannot recur by the same path;
`OVPComparator`'s docstring rewritten to state the half-bus identity, show
the fail-open derivation against the values as they actually are, and warn
explicitly against re-deriving `r_ref_top`/`r_hyst` from the net name rather
than the topology. **NOT re-tuned in this change** — see below for why, and
for the two options.

**Two remediation options for the still-crossing sense path (§4, rows 3-4),
laid out rather than implemented, per instruction not to unilaterally
re-tune or add an isolator without a design decision:**

| Option | Description | Consequence |
|---|---|---|
| **A. Half-bus sense, HV-side comparator, isolated fault flag** | Sense `dc_bus_plus` relative to `power_return` using values re-derived for the *actual* 170 V half-bus (e.g. back toward the 12 kΩ/1.50 V family this document traced above, retuned properly rather than reused blindly). Move the comparator itself to the HV side, referenced to `power_return`, powered from a new small HV-referenced bias supply (does not exist today — a real part addition). Carry only the resulting digital fault bit across the barrier via an opto (same pattern as the ZCD fix in this change). | Smaller isolator (digital, not linear), and the reference calculation is simple (already worked out once in §5, just needs a hysteresis resistor added and re-verified against worst-case corners the way UVL-02 was). Requires a new low-power supply referenced to `power_return` specifically (neither the existing `vcc_15v_ls`, which floats on `hv_minus`, nor anything else in this design floats on `power_return` today) — a real, nontrivial addition. |
| **B. Full differential bus sense** | Sense `dc_bus_plus - dc_bus_minus` (the true full 340 V bus) with an isolated amplifier (e.g. AMC1311/AMC1301-class, already named as a candidate class elsewhere in this codebase for the unrelated OCP-02 problem). | Directly matches the top-level `v_ovp_trip = 390V` spec without the half/full mental translation this document had to do. Needs a reference at `dc_bus_minus`/`hv_minus` — a *second* isolation domain (this design already treats `hv_minus`-referenced circuits, e.g. `power_15v_ls`, as a domain distinct from both `gnd` and `power_return`), so this is not free either. |

**Recommendation: Option A.** The reference math is simple and already
derived in this document (§5 above) — it needs a real hysteresis resistor
added and the whole divider re-verified against worst-case corners (same
discipline UVL-02's design doc applied), not invented from scratch — versus
Option B's need for a second, different isolated-amplifier part and a
`hv_minus`-referenced sense network. **Not implemented in this change** —
both options require a real part addition (a bias supply plus an opto, or an
isolated amplifier) that was not verified against a datasheet in this pass,
per the instruction to add real parts properly or leave them stated as
unimplemented. **The current 1.1 kΩ/287 kΩ values must not ship as-is either
way** — they are fail-open regardless of which option is chosen.

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

All numbers below are from the **rebased** tree (`docs/methodology-loop-discipline`
tip at the time of this run, plus this change), regenerated from a clean
`elec/build`/`pcb/*.kicad_sch` (both removed and rebuilt, not reused from the
pre-rebase run).

`make netlist` (foreground, `elec/src/main.ato:Top`) — **exit 0**, no
assertion failures (76/76 PASSED, 0 FAILED; verified by grepping the build
log for `FAILED`, which returns nothing). `make schematics` — exit 0, oracle
pass: "502 pin assignments, 104 nets -- connectivity partitions isomorphic"
(up from 463/98 pre-rebase, consistent with THM-02 and UVL-02 adding parts).

Positive confirmation the grounds are separate (from `elec/build/default.net`,
parsed programmatically, not eyeballed):

```
net 1  "gnd"       80 pins  (SELV: MCU, RTD ADC, safety comparators, gate-
                              driver control side, opto output side, THM-02
                              and UVL-02 comparators, etc. -- up from 74
                              pre-rebase, all the growth from the two new
                              fully-SELV modules)
net 2  "+170V_BUS"  11 pins  (HV: renamed from "+340V_BUS")
net 6  "PWR_RTN"    17 pins  (HV: power_return / doubler midpoint, unchanged)
```

Overlap check — reference designators appearing in *both* the `gnd` and
`PWR_RTN` node lists (unchanged by the rebase):

```
C6   -- y_cap_pe (Y1 cap): p1 on PWR_RTN, p2 on gnd  (pre-existing, unchanged)
PS1  -- IRM-10-15 (AuxSupply): ACN(2) on PWR_RTN, VN(4) on gnd
T1   -- CST2010-100L (current sense transformer): primary(2) on PWR_RTN, secondary(4) on gnd
U3   -- H11L1 (new, this change): cathode(2) on PWR_RTN, GND(5) on gnd
```

No other reference designator appears on both nets — in particular, neither
`SecondaryOCPComparator` (not instantiated, contributes nothing) nor any part
of `CoilThermalComparator`/`LogicUVLOComparator` (both fully SELV) shows up
here. Every overlap is a deliberate isolation device (capacitor, transformer,
transformer, or optocoupler) straddling the barrier by pin, never by a direct
tie. This is the positive, netlist-level proof the falsifier in §1 asked for.

---

## 7. ERC results

`kicad-cli sch erc --severity-all --format report -o <file> pcb/temper.kicad_sch`
(the hierarchical root sheet, covering all 6 sub-sheets including
`power_input.kicad_sch` and `safety_interlock.kicad_sch`) — **exit 0**, run
against the rebased/regenerated schematics.

**492 violations, all severity `warning`, zero `error`** (up from 447 on the
stale tree, proportional to the larger design — THM-02 and UVL-02 add parts,
each with the same generic warnings every part gets). All 492 fall into
exactly the same three categories as the pre-rebase run, verified by
extracting every distinct violation type in the report:

- `lib_symbol_issues` (167, up from 152) — "the current configuration does
  not include the symbol library ''" — every symbol in the design, including
  pre-existing ones, is flagged; this is an artifact of the sandbox's KiCad
  environment not having a symbol-library table configured, not a design
  defect.
- `footprint_link_issues` (164, up from 149) — "the current configuration
  does not include the footprint library '<X>'" for every footprint family
  used (`Capacitor_SMD`, `Resistor_THT`, `Package_DIP`, etc.) — same root
  cause, same library set as before (no new library name appears).
  `Package_DIP` appears in this list because the new H11L1 (`U3`) is the
  first DIP-6 part in the design; it gets the identical warning class every
  other part already gets, not a new kind of finding.
- `endpoint_off_grid` (161, up from 146) — cosmetic pin/wire grid-snapping
  artifacts from `gen_schematics.py`'s auto-placement, pre-existing for
  other parts too.

**No violation of any electrically-meaningful type** (no floating power pin,
no pin-not-driven, no conflicting drivers, no unconnected required pin)
appears anywhere in the report, on either the pre- or post-rebase tree. `U3`
(the new opto) is flagged only with the same generic library and grid
warnings every other component receives — nothing specific to its isolation
function or wiring. **This is reported honestly as a mostly-inconclusive ERC
result on real electrical topology**, because the sandbox's KiCad has no
configured symbol/footprint libraries and can't check ratsnest-level
connectivity issues that require resolved symbols — but it is a clean result
on everything ERC in this environment is actually able to check, the
violation count scaled proportionally with the larger (rebased) design
rather than jumping, and no new violation class appeared after rebasing in
three new modules (THM-02, OCP-02's definition, UVL-02).

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
  section, replacing the stale TODO; rewrote `OVPComparator`'s docstring —
  after the rebase, against the real `1.1kΩ`/`287kΩ` values — with the
  half-bus derivation, the fail-open conclusion, and the two remediation
  options; rewrote `RTDSensing`'s docstring (item 9 below).
  `CoilThermalComparator`, `SecondaryOCPComparator`, and
  `LogicUVLOComparator` were brought in by the rebase (not authored in this
  change) and are otherwise untouched — including `uvlo_logic.fault.line`'s
  deliberate test-point-only termination, left exactly as landed.
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

1. **OVP-01 is fail-open (§4 rows 3-4, §5).** `r_ref_top=1.1kΩ`/`r_hyst=287kΩ`
   require `dc_bus_plus` to reach ~400 V to trip; it physically cannot
   without the 250 V-rated bus capacitors already having failed. This is the
   single most urgent item in this entire document — it is not merely an
   unresolved isolation crossing, it is a protection gate that cannot
   perform its function at all in its current values. Independently
   confirmed by `docs/STRATEGY.md`'s own "OVP-01 is fail-open" entry, landed
   on this branch before this rebase.
2. **The same two dividers are also still HV/SELV crossings** (~1.3 MΩ and
   ~520 kΩ resistive paths from the HV half-bus into the floated SELV
   ground) independent of the fail-open tuning problem above. Two
   remediation options laid out in §5, neither implemented — fixing #1
   (retuning) without also fixing this would still leave `gnd` galvanically
   (if weakly) connected to HV.
3. **OCP-02 (`SecondaryOCPComparator`) is not instantiated, and its own
   docstring already documents that instantiating it as currently written
   (`power ~ power_3v3`) would expose the INA240A1 to ~170 V of common-mode
   against its -4 V/+80 V absolute maximum** — a second fail-destructively
   gate waiting behind a `# ocp2 = new SecondaryOCPComparator` comment.
   Pre-existing, not introduced here, but directly relevant to anyone
   picking this branch up next.
4. **Layout requirement for the new `gnd`→PE bond** (§3): must land at the
   same physical PE point as the Y-cap's `power_return`→PE bond to keep loop
   area small. UNVERIFIED — a PCB-layout fact, not a netlist one.
5. **H11L1's PCB creepage/clearance across the barrier** is UNVERIFIED. The
   5000 Vrms Viso figure confirmed from the datasheet is a 1-minute
   dielectric withstand spec, not independently confirmed here as a
   reinforced-insulation-coordination rating (creepage/clearance in mm) at
   this design's working voltage. Needs layout-stage verification, same
   category as the CT1 finding in `IEC60335_CRITICAL_COMPONENTS.md`.
6. **ZCD opto timing** (LED drive current, rise/fall through the H11L1) is
   sized by hand-calculation, not bench-verified against the soft-start
   timing budget the original raw-ADC ZCD approach used. Flagged, not
   assumed correct.
7. **Heatsink NTC and coil NTC (THM-02) installation** (§4 rows 10-11):
   isolation credit for both depends on correct physical mounting — Sil-Pad
   installation (heatsink tab-to-sink) and adequate creepage/clearance for
   the coil-mounted sensor against the tank winding — both chassis/assembly
   facts this schematic cannot verify.
8. **`coil_ntc_sense` (THM-02's MCU-visible analog tap) is declared but
   never wired to anything in `main.ato`** — firmware has no readout of coil
   temperature, only the hardware comparator's trip. A completeness gap
   found during this pass, not an isolation gap, and not fixed here (outside
   this document's scope).
9. **Bus-imbalance blind spot for OVP-01** (§5): sensing only one half-bus
   cannot catch a fault where the two halves diverge. True today and true
   under remediation Option A; not true under Option B.

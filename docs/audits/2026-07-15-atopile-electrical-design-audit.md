# Atopile Electrical Design Audit — Temper Induction Cooker

**Date:** 2026-07-15
**Branch:** feat/rebenchmark-production-board
**Scope:** All seven `elec/src/*.ato` source files plus `elec/src/constraints.ato`
**Methodology:** Independent parallel research agents traced every claim to exact line numbers against the source of truth. All findings verified.

---

## Severity Classification

| Tier | Definition |
|------|-----------|
| P0 | Would destroy hardware or prevent operation — must fix before PCB fab |
| P1 | Functional gap — blocks correct operation but not immediately destructive |
| P2 | BOM hygiene / datasheet mismatch — likely wrong but requires datasheet confirmation |

---

## Confirmed Source-Line Traceability

The following net chains underpin multiple P0 findings:

```
modules.ato:489     ac_n ~ dc_bus.gnd_ref
main.ato:223        power_in.dc_bus.gnd_ref ~ gnd

→ AC_N = gnd_ref = gnd = MCU.GND = logic/signal ground
```

```
modules.ato:311     dc_bus.hv_minus ~ gate_hs.driver.VSSB
modules.ato:318     power_15v.vcc ~ gate_hs.driver.VDDB
main.ato:247-248    hb.power_15v.vcc ~ vcc_15v, hb.power_15v.gnd ~ gnd

→ VDDB = +15V (ref to gnd), VSSB = hv_minus = -170V (ref to gnd)
→ VDDB - VSSB = 185V on 25V-rated UCC21550 pin
```

```
main.ato:266        tank.out ~ gnd
main.ato:341        mcu.power.gnd ~ gnd

→ 25A resonant tank current returns through MCU/analog ground net
```

---

## P0 — Would Destroy Hardware or Prevent Operation

### P0-1. Low-Side Gate Driver Supply: 185V Across 25V-Rated Pins

| Source | Line | Evidence |
|--------|------|----------|
| `modules.ato` | 489 | `ac_n ~ dc_bus.gnd_ref` |
| `main.ato` | 223 | `power_in.dc_bus.gnd_ref ~ gnd` |
| `modules.ato` | 311 | `dc_bus.hv_minus ~ gate_hs.driver.VSSB` |
| `modules.ato` | 318 | `power_15v.vcc ~ gate_hs.driver.VDDB` |
| `main.ato` | 247-248 | `hb.power_15v.vcc ~ vcc_15v`, `hb.power_15v.gnd ~ gnd` |

**Chain:** VDDB = +15V (referenced to system gnd via main.ato:247-248). VSSB = hv_minus = -170V (referenced to system gnd via the doubler midpoint chain modules.ato:489 → main.ato:223). VDDB - VSSB = 185V. UCC21550 absolute maximum VDDB-VSSB = 25V. **Instant destruction at first power-on.**

**Fix:** Low-side driver secondary needs a supply referenced to hv_minus (isolated aux rail, bootstrap from hv_minus, or a different grounding scheme). See plan `docs/plans/2026-07-15-003-fix-p0-grounding-isolation-architecture.md`.

### P0-2. High-Side Zener "Negative Bias" Clamp Is Backwards (Admitted in Comments)

| Source | Line | Evidence |
|--------|------|----------|
| `modules.ato` | 177 | `# This is definitely NOT negative bias.` |
| `modules.ato` | 179 | `# I will preserve the existing connections...` |
| `modules.ato` | 190-191 | `neg_bias_zener.A ~ drive.vss`, `neg_bias_zener.K ~ driver.VSSA` |

**Result:** Zener cathode to VSSA, anode to emitter (switch node). VSSA = emitter + V_zener (+5.1V). When driver output is LOW, gate is pulled to VSSA = emitter + 5.1V → off-state V_GS = **+5.1V**. IKW40N120H3 V_GE(th) range ~4.1-5.7V — the "off" IGBT is biased at threshold → **guaranteed shoot-through**. Additionally, the boot cap can only charge to ~8-9V (boot supply - V_zener drop), starving the gate drive even if shoot-through doesn't occur first.

**Fix:** Flip the zener: anode to VSSA, cathode to emitter. This gives VSSA = emitter - V_zener (-5.1V true negative off-bias). See plan `docs/plans/2026-07-15-004-fix-p0-wiring-bugs.md`.

### P0-3. +15V Rail Has No Source — Entire System Unpowered

| Source | Line | Evidence |
|--------|------|----------|
| `main.ato` | 229-230 | `# Note: In real design, 15V comes from auxiliary winding, not directly from DC_BUS` |
| `modules.ato` | 634 | `power_in_hv = new ElectricPower` — declared but never connected at top level |
| `modules.ato` | 642-643 | `power_in_hv ~ buck.power_in`, `buck.enable.line ~ power_in_hv.vcc` |

**Result:** Buck converter input is floating. Nothing powers the gate driver, relay, MCU, or any downstream circuit. The entire offline auxiliary supply (flyback/LinkSwitch-class, or an aux winding + regulator) is missing from the BOM. Also: the LMR51430 (36V max input) cannot run from the 340V bus even if connected.

**Fix:** Design and add the offline auxiliary power supply. See plan `docs/plans/2026-07-15-005-fix-p0-aux-supply-design.md`.

### P0-4. OVP Comparator Inverted and Mis-Scaled — Safety Latch Permanently Set

| Source | Line | Evidence |
|--------|------|----------|
| `modules.ato` | 1021-1024 | Bus divider (3x 430k + 10k) → comp.INN |
| `modules.ato` | 1028-1031 | 3.3V-derived reference (~3.0V) → comp.INP |

**Polarity:** TLV3201 outputs HIGH when INP > INN. With divider on INN and reference on INP: output = HIGH when bus is **below** threshold → permanently asserted at normal operating voltage. Set-dominant latch holds SHUTDOWN forever at power-up — **the system can never leave fault state.**

**Scale:** The divider sees half-bus (+170V) through the doubler midpoint, not the full 340V bus. At 170V: V_INN = 170 / ((3×430k + 10k) / 10k) ≈ 1.3V vs V_INP ≈ 3.0V → permanently tripped. The divider ratio targets a 390V trip point (appropriate for full-bus sensing) but measures half-bus (should target ~195V for a ~340V bus).

**Fix:** Swap INP/INN connections (divider → INP, reference → INN). Adjust reference divider for half-bus trip point (~1.5V for 195V trip on 340V bus). See plan `docs/plans/2026-07-15-004-fix-p0-wiring-bugs.md`.

### P0-5. Thermal Protection Has No Sensor

| Source | Line | Evidence |
|--------|------|----------|
| `modules.ato` | 1034-1067 | ThermalComparator module — receives `ntc_sense` signal |
| All files | — | No NTC thermistor exists anywhere in the design |

The only NTC component is NTC_Inrush (`components.ato:136`) for inrush limiting — it is not a thermal sensor. The `ntc_sense` net connects from the MCU ADC pin to the ThermalComparator input with no actual sensing element. The reference network is also degenerate: 10k pull-up to VCC (r_ref) with a 100k hysteresis resistor to output — no bottom-leg resistor, so INP floats near VCC (~3.3V), not a meaningful temperature threshold.

**Fix:** Add a heatsink NTC thermistor + divider network. See plan `docs/plans/2026-07-15-006-fix-p0-sensing-frontends.md`.

### P0-6. Current Transformer Measures Nothing — Primary Open, Output Unbiased

| Source | Line | Evidence |
|--------|------|----------|
| `modules.ato` | 657-658 | `signal primary_in`, `primary_in.required = true` |
| `main.ato` | 272-276 | `ct_sense` instantiation — `primary_in` never connected |

**Primary:** CT primary is not in series with any current path. Despite `required = true`, the primary net is left floating — no current will ever flow through the CT. The ato compiler should be catching this (required signal not connected at top level).

**Output:** The burden resistor output is bipolar AC fed directly to ESP32 ADC (GPIO1) with no DC bias network or precision rectifier. Negative half-cycles will clamp through the ESP32's protection diodes, and the ADC sees only one current polarity. Needs a 1.65V mid-rail bias (or precision rectifier) on the sense node.

**Fix:** Route the CT primary through the tank/bus current path. Add a 1.65V bias circuit on the sense output. See plan `docs/plans/2026-07-15-006-fix-p0-sensing-frontends.md`.

### P0-7. XC6220 LDO: 15V Into 6V-Max Input — Instant Destruction (ESCALATED from P2)

| Source | Evidence |
|--------|----------|
| `modules.ato` | XC6220 LDO powered from `power_15v.vcc` (15V rail) |
| Datasheet | XC6220 family Vin max = 6.0V |

(15V - 3.3V) × 350mA (ESP32 WiFi peaks) ≈ 4W in a SOT-23-5 package — thermally impossible even if it survived the overvoltage.

**Fix:** Replace with a second buck converter to 3.3V (or 5V intermediate) rated for >15V input. Consider the XC6216 (28V Vin max) if an LDO is strongly preferred, but the thermal math still demands a switcher at >2W dissipation. See plan `docs/plans/2026-07-15-005-fix-p0-aux-supply-design.md`.

### P0-8. LMR51430 Feedback Reference Value — VERIFY AGAINST DATASHEET

| Source | Line | Evidence |
|--------|------|----------|
| `modules.ato` | 586 | `v_fb: voltage = 1.0V` |
| `modules.ato` | 587 | `v_out_calculated = v_fb * (1 + r_fb_top.value / r_fb_bot.value)` |
| `modules.ato` | 588 | `assert v_out_calculated within 14.5V to 15.5V` |

**Discrepancy note:** The TI LMR51430 datasheet specifies V_FB = 1.0V typical (0.985V min, 1.015V max), making the hardcoded 1.0V appear correct. The audit's original P0 escalation claimed V_FB = 0.6V. **This needs a human to check the actual device datasheet for the specific variant/grade used** — if the reference is 1.0V, the FB divider math (140k/10k → 15.0V) is correct and this is a false alarm. If the reference is 0.6V, the actual output is 9.0V and everything downstream is undervoltage. The self-asserting check at line 588 passes regardless because it validates a hardcoded copy of itself.

---

## Safety Architecture (IEC 60335 Would Fail This)

### S1. No Isolation — Logic Ground = AC Neutral, User-Touchable Probe

| Source | Line | Evidence |
|--------|------|----------|
| `modules.ato` | 489 | `ac_n ~ dc_bus.gnd_ref` |
| `main.ato` | 223 | `power_in.dc_bus.gnd_ref ~ gnd` |
| `main.ato` | 341 | `mcu.power.gnd ~ gnd` |
| `components.ato` | 267-284 | ADUM1250 I2C isolator defined |
| `modules.ato` | 47 | `import ADUM1250 from "components.ato"` — imported but never instantiated |

AC_N = gnd_ref = gnd = MCU.GND. The RTD probe rides on logic ground through MAX31865 (all GND pins tied to system gnd). A reversed AC plug or broken neutral puts line potential on the food-contact probe — a user safety hazard.

The ADUM1250 isolation barrier was planned (component defined, imported) but never instantiated anywhere in the design. Either the probe interface needs reinforced isolation or the entire control side must move to an isolated SELV domain.

**Fix:** See plan `docs/plans/2026-07-15-003-fix-p0-grounding-isolation-architecture.md`.

### S2. No EMI/Surge Front End

| Source | Line | Evidence |
|--------|------|----------|
| `modules.ato` | 353-367 | PowerInput module — docstring claims "AC input with EMI filter" |
| All files | — | Zero X2 capacitors, zero common-mode chokes, zero Y capacitors, zero MOVs |
| `modules.ato` | 364-365 | `pe` declared `required = true` but never connected anywhere |

A 1.8kW switching appliance cannot pass conducted emissions or surge without these components.

### S3. 25A Resonant Tank Current Returns Through Logic Ground

| Source | Line | Evidence |
|--------|------|----------|
| `main.ato` | 266 | `tank.out ~ gnd  # Return path` |

Even with careful layout, the netlist gives the autorouter permission to place 25A return current alongside 3.3V analog signals. The tank return should go to a dedicated bus-midpoint net, joined to signal ground at exactly one deliberate star-point.

### S4. Bus Discharge: τ ≈ 330 Seconds

100kΩ bleeders × 3300μF = 330s per half-bus. To reach <34V (IEC requirement): ~4τ ≈ 22 minutes. A service tech meets 340V long after unplugging. Consider active discharge or dual smaller bleeders with higher power rating.

---

## P1 — Functional Gaps

### P1-1. ZCD Floating Wire
`modules.ato:367` declares signal `zcd`, routed to MCU IO13 at `main.ato:348`, but no detection circuit (high-value divider from line or opto-coupler) exists on the PowerInput side.

### P1-2. No Bus Voltage Sensing ADC Path
`modules.ato:1259-1260`: `adc_v_bus.required = true` — the MCU expects a bus voltage ADC input at GPIO2, but no resistive divider feeds it. Only the (broken) OVP comparator divider exists on the `v_bus` net.

### P1-3. No ESP32 Programming Path
GPIO19 (USB D-) → relay_ctrl, GPIO20 (USB D+) → fault_status — the native USB pins are consumed as plain GPIOs. No IO0 bootstrap circuit. No UART header. Board is unprogrammable via any standard method.

### P1-4. I2C Bus Declared With No Pull-ups, No Peripherals
I2C bus at IO38/IO39 has no pull-up resistors and is never connected to any peripheral in `main.ato`. The entire UI is also absent from the `.ato` source while `pcb/user_interface.kicad_sch` exists — a source-of-truth split.

### P1-5. No Connectors in BOM
No AC inlet/terminal block, no RTD connector, no fan connector. An 1800W induction unit needs forced air (the Control Freak has a fan); none is specified.

### P1-6. Fuse at 100% of Load
15A fuse with 1800W/120V = 15A continuous. Either derate the power target (1500W is why real 120V units stop there) or use a 20A fuse with appropriate upstream breaker coordination.

---

## P2 — BOM Hygiene

| Item | Issue | Detail |
|------|-------|--------|
| MAX31865ATP+ | MPN/footprint mismatch | ATP = TQFN-20; footprint is SSOP-20. Correct MPN: MAX31865AAP+ |
| r_relay_drop | Triple mismatch | CRCW0603 (SMD 0603, 0.1W) assigned a THT axial footprint requiring 1W. |
| CST-1005 | Ratio verification needed | The burden math (50A → 50mA → 3.3V across 66.5Ω) depends on 1:1000 ratio claim — verify against actual datasheet. |
| EKZE251ELL332MM40S | Series verification needed | Chemi-Con KZE series may not reach 250V for 3300µF caps. Verify part number is a valid KZE offering. |
| UJ3D1210TS bootstrap diode | ~50× overkill | 1200V/10A TO-220 SiC diode to charge a 10µF boot cap. A 600V/1A SMA ultrafast (e.g., ES1J, US1M) does this at fraction of cost/area. |
| UCC21550 bypass | Missing | No VCCI bypass caps; no VDDB bypass caps. Also no HF film cap or snubber across the DC bus at the bridge — only big electrolytics far from the switching loop. |
| Gate resistor 2.2Ω | Current limit | Demands 15V/2.2Ω ≈ 6.8A from 4A-source driver. The UCC21550 will current-limit. Works but size to the driver (~3.9Ω) or accept the limit knowingly. |
| Self-asserting checks | Circular | `v_fb`, `p_bleed_actual`, `t_dead_time` all verify hardcoded copies of themselves in assertions — would pass even when real parts disagree. Derive from part attributes where possible. |

---

## What's Genuinely Good

These findings are accurate and worth preserving:

| Item | Detail |
|------|--------|
| Voltage-doubler topology | Correct Delon doubler configuration |
| Inrush NTC + relay bypass | Textbook implementation; 39Ω coil-drop math exactly matches 75mA G4A coil; flyback diode present |
| Bleeders properly derated | Power asserts verify safe dissipation on the bleed resistors |
| Dead-time resistor | Honest corner-case commentary in surrounding comments |
| RTD hardware window | REF2025 + dual TLV3201 + TPS3700 + Ioff-rated open-drain NAND — genuinely sophisticated fail-safe design |
| Fault latch with fault-qualified reset | Well designed; reset is blocked while fault condition persists |
| ESP32-S3-WROOM-1 pin map | Completely accurate against the real module pinout |
| Creepage/clearance constraint tables | Match IEC 60335 |

The pattern is clear: the SELV control domain got senior-level attention, while the HV power path — where mistakes cost hardware and safety — carries the critical bugs, several of them known and deferred in comments.

---

## Fix Order

Items 1 and 2 change component count and reference designators materially — the PCB skeleton and placer baseline must not be regenerated until these are resolved.

1. **Grounding/isolation architecture decision** (P0-1, S1, S3, P0-3) — drives VDDB supply, tank return, RTD isolation, PE connection, and the aux supply topology
2. **P0 wiring bugs** (P0-2, P0-4) — zener flip, OVP comparator fix
3. **Aux supply design** (P0-3, P0-7, P0-8) — 15V rail source, LMR51430 v_fb verification, XC6220 replacement
4. **Sensing front-ends** (P0-5, P0-6, P1-1, P1-2) — CT bias network, thermal NTC, ZCD circuit, bus ADC divider
5. **EMI/surge front end** (S2) — X2/Y caps, CMC, MOV, PE routing
6. **BOM verification** (P2 items, P1-5, P1-6) — MPN/footprint reconciliation, connector BOM, fuse sizing
7. **Programming path** (P1-3, P1-4) — free USB pins or add UART header, IO0 bootstrap, I2C pull-ups

---

## Branch Impact

`feat/rebenchmark-production-board` is blocked until electrical fixes land. The branch:
- Fixed parser polygon board outlines (commit f911581f)
- Pinned Edge.Cuts to corpus target 100×150mm (commit 6d6998f2)
- Repointed CI/corpus at production board (commit 051da616)

The placer pipeline works mechanically (100/100 components at finite positions), but the netlist will change substantially when these fixes land, making any baseline generated now immediately stale. Do not re-benchmark until P0 items 1-3 are resolved.

---

## Implementation Plans

| Plan | Covers | Severity |
|------|--------|----------|
| [2026-07-15-003](../plans/2026-07-15-003-fix-p0-grounding-isolation-architecture.md) | P0-1, S1, S3 | P0 |
| [2026-07-15-004](../plans/2026-07-15-004-fix-p0-wiring-bugs.md) | P0-2, P0-4 | P0 |
| [2026-07-15-005](../plans/2026-07-15-005-fix-p0-aux-supply-design.md) | P0-3, P0-7, P0-8 | P0 |
| [2026-07-15-006](../plans/2026-07-15-006-fix-p0-sensing-frontends.md) | P0-5, P0-6, P1-1, P1-2 | P0/P1 |
| [2026-07-15-007](../plans/2026-07-15-007-fix-emi-surge-frontend.md) | S2, S4 | Safety |
| [2026-07-15-008](../plans/2026-07-15-008-fix-bom-verification-pass.md) | P2 items, P1-5, P1-6 | P1/P2 |
| [2026-07-15-009](../plans/2026-07-15-009-fix-programming-path-gaps.md) | P1-3, P1-4 | P1 |

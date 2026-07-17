---
title: "feat: active bus discharge (<60s to safe) + thermal system BOM"
type: feat
status: pending
date: 2026-07-16
origin: PR #217 BOM-hardening session (passive-bleeder discharge-time warning in modules.ato PowerInput)
depends_on: []
blocks: []
---

# feat: Active Bus Discharge + Thermal System BOM

Proposal only — no schematic changes in this document. All MPNs below were
verified against a manufacturer datasheet or live distributor listing on
2026-07-16 unless explicitly marked `VERIFY`.

## Part 1: Active bus discharge

### Problem

Each 170V half-bus carries 2x 1800uF (EKMQ251VSN182MA50S) = 3600uF, bled
only by a passive 22k/2W resistor (CRGP2512F22K). Discharge time constant
is 22k x 3600uF ~= 79s; reaching <34V takes ln(170/34) = 1.61 tau ~= 2.1
minutes per half-bus and the existing source comment estimates ~9 minutes
to fully safe levels. Target: **<60s to <34V** after mains removal.

Stored energy at stake: 0.5 x 3600uF x 170V^2 ~= 52 J per half-bus.

### Recommended: Option A — relay-switched discharge (fail-safe NC contact)

Use a relay whose **normally-closed** contact inserts a discharge resistor
string across each half-bus. The coil is held energized from the switched
+12V rail whenever the unit runs; *any* loss of power (unplug, fuse,
aux-supply fault) drops the coil and engages discharge. This is fail-safe
by construction — no MCU involvement required.

| Item | Part | Verified facts |
|---|---|---|
| Relay, 1 per half-bus (2 total) | Omron **G5LE-1 DC12** | SPDT (has NC), contacts 10A / 250VAC, 12V coil, 360 ohm / ~33mA / 400mW (Omron G5LE datasheet; Newark 35K4530) |
| Discharge resistor, 2 in series per half-bus (4 total) | Vishay **AC05000004701JAC00** | AC05 cemented wirewound, 4.7k 5%, 5W, axial ~7.5x18mm body, AEC-Q200, all-welded (Vishay AC05 series; TME/Newark/DigiKey listings) |

Sizing (per half-bus, 2x 4.7k in series = 9.4k):

- tau = 9.4k x 3600uF = 33.8s -> 170V to 34V in 1.61 tau ~= **54s**. Meets <60s.
- Peak power at contact closure: 170^2 / 9.4k = 3.1W across the string,
  ~1.5W per resistor — inside the 5W continuous rating even in the
  abnormal case of a stuck-closed contact with the bus still energized
  (this is why two 5W parts in series beat a single smaller resistor:
  the string survives indefinitely; no single-point fire risk).
- Contact stress: initial current 170/9.4k = 18mA at up to 170VDC.
  NOTE (VERIFY at design-in): G5LE DC contact ratings are specified to
  30VDC/10A; low-current 170VDC resistive break at 18mA is well inside
  typical clearance capability for this class but is not a cataloged
  point — confirm against Omron's DC load curve or add an RC snubber
  across the contact. The load is purely resistive and break energy is
  small; alternatively use two contacts in series (one relay per rail
  leg) if the curve disallows it.
- Coil budget: 2 coils x 33mA = 66mA from +12V, only while running.
  Drive both coils from the existing relay-driver pattern (AO3400A
  low-side switch + SS14 flyback), or hard-wire to the switched 12V rail
  so discharge engages on any rail collapse.

### Alternative: Option B — depletion-FET constant-current bleeder

Two-terminal, no moving parts: normally-ON depletion MOSFET as a
constant-current sink across each half-bus, gated OFF while the unit runs.

| Item | Part | Verified facts |
|---|---|---|
| Depletion FET, 1-2 per half-bus | Microchip **DN2540N5-G** | N-ch depletion (normally on), 400V, IDSS >= 150mA, 500mA max, RDS(on) 25 ohm max, TO-220, 15W (Microchip/Supertex DN2540 datasheet; DigiKey 4902540) |

- Configured as a ~40mA current sink (source resistor ~ VGS(off)/40mA),
  discharge is linear: Q = 3600uF x (170-34)V = 0.49C -> **~12s**.
- Dissipation while discharging starts at 170V x 40mA = 6.8W, decaying;
  needs a small TO-220 heatsink (part is 15W rated with sink). 400V
  rating gives 2.3x margin over the 170V half-bus.
- Requires a gate-disable path (optocoupler or small enhancement FET
  pulling the gate below VGS(off)) powered from the 12V rail, otherwise
  it burns 6.8W continuously during operation. Failure of the disable
  path is safe-but-hot: the bleeder conducts and the FET heats — thermal
  design must tolerate it.

**Recommendation: Option A.** It reuses an already-proven relay-drive
pattern from PowerInput, is fail-safe on any power loss, dissipates zero
watts in normal operation, and every part is a stocked commodity. Option B
is faster (~12s) but adds an HV-side gating circuit whose failure mode is
a continuously hot component.

### Where it connects

In `PowerInput` (elec/src/modules.ato), the voltage-doubler half-buses are
the c_bus1||c_bus1b and c_bus2||c_bus2b banks that r_bleed1/r_bleed2
currently parallel. Each discharge string (relay NC contact + 2x 4.7k in
series) goes directly across one half-bus, physically adjacent to the
snap-in capacitor bank, in parallel with (not replacing) the passive 22k
bleeders — the passive parts remain the backstop if a relay contact fails
open.

## Part 2: Thermal system BOM (2x TO-247 IGBT + 2x TO-220 rectifier, ~30W)

Assumed split: ~10W per IGBT, ~5W per rectifier (refine against measured
switching losses). Budget: keep sink temperature rise <=25C over ambient
so junctions stay comfortable with SilPad interfaces.

| # | Item | Part | Verified facts | Est. |
|---|---|---|---|---|
| 1 | Shared heatsink, all 4 devices | Wakefield-Vette **392-120AB** | Extruded, 120 x 125 x 135.8mm, black anodized, 0.5 C/W natural / 0.2 C/W forced convection, marketed for IGBTs/rectifiers, DigiKey 345-1173-ND in stock | 30W x 0.5 C/W = 15C rise even fanless; 6C with fan. Generous margin; drill/tap M3 pattern for 2x TO-247 + 2x TO-220 |
| 2 | Fan, 12V | Sunon **MF60251V1-1000U-A99** | 60x60x25mm axial, 12V, 23.5 CFM, 4500 RPM, ~1W / 87mA max, 27-30 dBA, Vapo bearing, 2-wire leads (Sunon spec D06077210G; DigiKey 6198741) | Powered from switched 12V rail (fan + both discharge relay coils ~160mA total). Mount blowing along fin channels |
| 3 | TIM / isolator, TO-247 (qty 2) | Bergquist **SP400-0.009-00-58** | Sil-Pad 400, 0.009", die-cut -58 (TO-218/TO-247 outline), DigiKey 529931 | IGBT tabs are at bus potential — electrical isolation from the grounded sink is mandatory |
| 4 | TIM / isolator, TO-220 (qty 2) | Bergquist **SP400-0.007-00-54** | Sil-Pad 400, 0.007", die-cut -54 (TO-220 outline), DigiKey 529923 | Same isolation argument for the rectifier tabs |
| 5 | Mounting hardware | M3 x 10 pan-head machine screws + insulating shoulder washers + spring (Belleville) washers, 4 sets | Commodity; `VERIFY` exact shoulder-washer part (e.g. Keystone or Aavid accessory series) fits TO-247 3.6mm mounting hole before ordering | Screw-mount preferred over clips on a drilled shared extrusion; torque per Sil-Pad guidance (~0.6-0.8 N-m) |
| 6 | Compact per-device alternative (only if the shared extrusion doesn't fit the enclosure) | Ohmite **WA-T247-101E** (TO-247) + Aavid/Boyd **530002B02500G** (TO-220) | WA-T247-101E: 32 x 23.4 x 16mm clip-on, 11 C/W natural / 8 C/W @ 500 LFM, DigiKey 2202818 in stock. 530002B02500G: TO-220 vertical board-level, DigiKey 1216384 | **Marginal at 10W/IGBT** (80C rise even at 500 LFM) — acceptable only with direct fan impingement and re-measured losses; the shared extrusion is the engineering recommendation |

Notes for layout:

- The 392-120AB is heavy (~1kg class): mount to chassis, not PCB; devices
  lead-formed or on a daughter edge. If enclosure height caps out, pick a
  shorter 392-series length at design-in (`VERIFY` the specific length's
  C/W from the Wakefield 392 profile datasheet — only 392-120AB was
  verified in stock here).
- Fan airflow path should also wash the CMC / bus capacitors bank; the
  EKMQ capacitors' life doubles per ~10C reduction.
- Add the fan to the BOM as a spared line item; Vapo bearing at 60C
  ambient is the wear item of the system.

## Implementation status (2026-07-16)

Option A is IMPLEMENTED in `elec/src/modules.ato` (`BusDischarge`,
commits f6ec8abb + b5674c3e): relay strings, coil drivers on IO47
(DISCHARGE_CTRL), and RC contact snubbers (the G5LE datasheet caps DC
switching at 125VDC, so the 170VDC/18mA break required them — see the
module docstring for the verified numbers). Remaining:

- **Firmware TODO**: IO47 startup/fault sequencing — requirement
  recorded in `firmware/README.md` (gpio_init is still stubbed).
- Thermal: fan power circuit implemented in `ThermalSystem`
  (`elec/src/modules.ato`) — 39R dropper brings 15V into the fan's
  verified 4.5-13.8VDC range. Heatsink, Sil-Pads and hardware remain
  chassis-BOM lines (below); they are not PCB components.

## Acceptance criteria (when implemented)

1. Bench: bus discharge from 340V total to <34V on both halves in <60s
   after mains removal, MCU unpowered.
2. Stuck-relay abnormal test: discharge string across an energized
   half-bus for 30 min — no resistor >125C surface.
3. Thermal: at max continuous cook power, sink rise <=25C over ambient
   with fan; IGBT case <=90C.

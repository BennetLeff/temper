# AR-FAULT attempt-001 — boost-switch-short fault stress on the actual board

Task: **AR-FAULT** · Attempt: **attempt-001** · Campaign: 2026-09-17-pfc-campaign
Board: `zapote/power-entry/shunt-repair/candidate/` (schematic `49db3ee4`, PCB `34e6fba9`,
manifest `136c94c3`). Contract C1.1 `0accd9bc`. HEAD `95d1d528` == dispatch `source_revision`.

**Hypothesis / changed variable.** The AR-VERIFY finding "a boost-switch-short bus fault puts
≈586.7 V across the bridge device (1.02× on a 600 V part)" is a derived device stress. Changed
variable: **none** — this is a source-only assessment of the existing routed candidate. I trace the
actual fault loops and test whether 586.7 V exists as a device stress. It does not.

**How the claim was built.** `AR-VERIFY/attempt-001/raw/compute_ar_verify.py:415` computes
`round(v_bus + v_peak_132, 2)` = `400 + 186.676` = **586.68 V**. It is an explicit sum of the bus
potential and the line peak, not a traced node.

## 1. Topology (from the authored netlist, named)

`source-manifest.json` → `raw/netlist_fault_loop.json`:

- `plus` = U1.PLUS + U8.1 · `a1` = U8.2 + U9.drain + U10.A1/A2 · `PFC_BUS_PLUS_390V` =
  U10.K + c1..c4 + + c_hf + + U52.1 · `PFC_BUS_MINUS` = U9.source + U12.1 + caps − + U11.GND
- `minus` = U1.MINUS + U12.2 (shunt U12 = 10 mΩ between bridge MINUS and bus minus)
- Bridge U1 GBJ2510 (1000 V/25 A, IFSM 350 A, I²t 510 A²s); switch U9 STW65N65DM2AG (650 V,
  Rds_on 0.042 Ω typ); boost diode U10 C3D20065D (650 V); inductor U8 760800301 (180 µH ±20 %,
  Isat 43 A typ, DCR 20 mΩ max); fuse F1 0034.3129 (FST 5×20, 16 A/250 V time-lag).

Standard positive CCM boost: `plus → U8 → a1 → {U9 → bus− | U10 → bus+}`.

## 2. Boost-switch short (U9 D-S) — the traced loop

After the short `a1 = PFC_BUS_MINUS`, so the inductor is across the bridge DC output:

`mains L → F1 → CMC U3 (1→4) → NTC U4 / bypass relay U5 (l2→ac1) → bridge AC1 → upper diode →
PLUS → U8 → a1 → shorted U9 → PFC_BUS_MINUS → U12 → bridge MINUS → lower diode → AC2 → CMC (3→2) → mains N`.

- **Bus capacitor is NOT in this loop.** U10 (anode `a1`, cathode `hv_plus`) is now **reverse-biased
  by the full bus**. `hv_plus` has no other path to the fault. The 179 J in the bank does *not*
  discharge into the shorted switch.
- **Node voltages seen:** U9 Vds ≈ 0 (it is the short); U10 reverse ≈ 400 V; bridge AC terminals
  = line peak **186.676 V**; bridge output tracks the rectified line. **No node is 586.7 V.**
- **Real stress is current/energy, not voltage.** L limits di/dt (1.04 MA/s → Isat 43 A in ~42 µs);
  after saturation the current is source-impedance limited — see §4.

## 3. Boost-diode short (U10 K-A) — does it put the bus on the bridge?

After the short `a1 = hv_plus`, DC-coupled through U8 to bridge PLUS:

- **Standing (switch off):** bridge PLUS = **400 V**, bridge MINUS = 0, U9 Vds = **400 V**. The bus
  *is* placed on the bridge output. But the bridge's own upper device (AC→PLUS) prevents an AC node
  rising above PLUS, and its lower device (MINUS→AC) prevents one falling below MINUS: the line
  **cannot** put an AC node at the opposite rail. So a bridge device blocks at most ~**400 V**
  (= V_bus), not 400 + 186.7. 586.7 V needs one AC node at 400 V *and* the other at −186.7 V at the
  same instant; the second is blocked by its own clamp. It needs an additional open-circuit clamp
  fault — a bridgeless/totem-pole stage would be required for V_bus+V_line to be a real device node.
- **If U9 conducts** (UCC28180D still sees a 400 V bus on VSENSE, so nothing signals a stop):
  `hv_plus → shorted U10 → a1 → U9(on) → PFC_BUS_MINUS` is a direct **bank discharge** — 179.2 J
  total, ~145 J into U9, ~34 J into the shunt, peak ~7.7 kA, τ ≈ 116 µs. **F1 is not in this loop.**

## 4. V / I / E exposure

| Quantity | Value | Basis |
|---|---:|---|
| Bulk bank c1..c4 | 2240 µF, 450 V each (LGX2W561MELC50) | manifest values + ato ratings |
| HF film c_hf | 0.47 µF, 630 V (B32672P6474K000) | manifest + ato |
| Stored energy @400 V | **179.24 J** | ½·C·V², C = 2240.47 µF |
| @390 V nameplate / @450 V rating | 170.4 J / 226.8 J | same |
| Bleed path | 300 kΩ, τ = 672 s, 0.53 W, 1657 s to 34 V | U53+U54; no active discharge part |
| Switch-short peak current | **null — parametric** | line impedance unknown |
| — board-only upper bound | 6152.5 A | (186.676 − 2.1)/(0.020+0.010), ideal source |
| — examples over assumed R_unknown | 3691 A @20 mΩ · 1420 A @100 mΩ · 559 A @300 mΩ · 179 A @1 Ω | `raw/compute_result.json` |
| Switch-short device energy | **null** | needs line impedance **and** F1 I²t |
| Diode-short bank discharge | 179.2 J (145 J into U9) | Rds_on 0.042 + shunt 0.010, τ 116 µs |

## 5. Interruption

- **F1 (Schurter 0034.3129, 16 A/250 V time-lag)** is in the line-fed switch-short loop, so a
  line-frequency fault is interrupted *in principle*. Clearing time is **not established** — no
  pre-arcing I²t / time-current curve is captured anywhere in this tree (`BOM.md:77`).
- **The bus-capacitor discharge is internal** (caps → U10 → U9 → shunt) and does **not** pass
  through F1: nothing on the board interrupts it.
- Line-frequency current and capacitor discharge have different timescales (ms→10s of ms vs 116 µs)
  and different energy sources; they must not be conflated.

## 6. MOV — explicitly out of the loop

U7 (V150LA10AP) is connected **line-to-neutral**: `l1` (after F1) to `AC_N_RECTIFIED_INPUT`. Neither
bus rail reaches it. It is in **neither** internal fault loop. **No MOV clamp figure is used
anywhere in this assessment** (the AR-VERIFY ~400 V clamp assumption is not admissible here).

## 7. Device / protection requirements

- **Voltage class:** the single-fault blocking requirement is ~**400 V** (bus) on a diode short and
  the line peak (186.7 V) on a switch short. A **600 V** device gives ~1.5× on the 400 V case. The
  586.7 V figure does **not** force an 800/1000 V part; on this board U1 is already 1000 V.
- **Current/energy:** the switch short is a fault-current problem. The surviving bridge must be
  cleared inside **IFSM 350 A / I²t 510 A²s**.
- **Additions:** (1) capture F1's pre-arcing I²t and coordinate it with the prospective current;
  (2) add bus-side protection (DC fuse / crowbar / fast controller overcurrent shutdown) for the
  internal discharge loop; (3) resolve the line impedance.

## 8. Evidence / accounting

- Case census: expected 1; attempted 1; **valid 1**; failed 0; unsupported 0; unrun 0.
- Solver invocations 0; model/CAD/BOM edits 0; bench work none; no commits, no stash.
- Checker: `not_applicable` by dispatch → **no receipt**; per ADMISSION.md this is **evidence, not
  a validated run**. `hardware_qualification = NOT_PERFORMED`.
- Raw: `raw/compute_fault.py`, `raw/compute_result.json`, `raw/netlist_fault_loop.json`,
  `raw/pcb_fault_loop.txt` (201 copper elements across the 13 loop nets), `raw/extract_pcb.py`,
  `raw/input_hashes.json`, `raw/checkpoint.md`, `raw/capture_failures.json`.
- Unresolved findings: line impedance; F1 I²t; NTC state; controller response; C3D20065D surge;
  LGX datasheet not independently captured.
- **Recommended next observation:** obtain the AC source/line impedance (and F1's I²t curve) and
  recompute the prospective fault current; that single number decides whether F1 clears before the
  bridge's 350 A IFSM is exceeded.

---

**The single most important missing input:** the **AC source/line impedance at the fault** — it sets
the prospective fault current, which (with F1's uncaptured pre-arcing I²t) decides whether the
line-fed switch-short is cleared before the bridge's 350 A IFSM / 510 A²s I²t is destroyed.

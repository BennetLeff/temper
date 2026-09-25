# power-stage-120v: full-bridge induction power stage

Status: **source compiled and audited; native schematic/PCB not started; physical NOT RUN.**
Design basis and justification: `docs/hardware/power-section-120v/` (POWER-SECTION.md,
LOSS-REFACTOR.md, COIL-MC.md). Front-end decision: `docs/adr/2026-09-25-front-end-architecture-brief.md`.

One board carries the mains entry, EMI filter, bridge rectifier and film bus, the full
bridge with both UCC21550 drivers next to the MOSFETs, the resonant capacitor bank and tank
current transformer, the DC-bus shoot-through OCP, isolated bus-voltage sense, the
thermal-cutoff-gated gate supply, and the SELV 15 V supply. The ESP32 controller, current-sense,
thermal, interlock and RTD boards connect through one SELV header.

## Build and verify

```sh
cd zapote/power-stage-120v
# 1. Compile (writes build/, which is gitignored)
uv tool run --offline --from "atopile==0.2.69" ato --non-interactive build \
    elec/src/power_stage_120v.ato:PowerStage120V
# 2. Per-instance part identity (vendored from harness-lab)
uv tool run --offline --from "atopile==0.2.69" python tools/circuit_export.py \
    "$PWD" "$PWD/build/resolved-components.json" \
    --entry-file elec/src/power_stage_120v.ato --entry PowerStage120V
# 3. Audit the fresh build, then (after a reviewed source change) freeze it
rustc --edition=2021 -O audit.rs -o /tmp/ps_audit
/tmp/ps_audit build/default.net build/default.csv build/resolved-components.json
cp build/default.net build/default.csv build/resolved-components.json frozen/
# 4. Mutation tests run against the frozen copies
rustc --edition=2021 --test audit.rs -o /tmp/ps_audit_t && /tmp/ps_audit_t
```

`frozen/` holds the reviewed build outputs. The netlist and resolved export embed absolute
source paths, so a rebuild elsewhere differs only in those paths. The netlist and BOM were
byte-identical, after path normalization, between two builds in different checkouts.
`build-receipt.json` pins the hashes. Current result: 91 components, 67 nets. The audit
passes, and 17/17 tests pass, 16 of them deliberate miswires that must fail.

**Part identity comes from `resolved-components.json` and the CSV, never from `default.net`.**
Atopile 0.2.69 writes a footprint-aliased part into the netlist's libsource field. In this
build, every 0603 resistor appears as `RC0603FR-071KL` and the LM4040 as `AO3400A`. The CSV BOM
and the per-instance resolved export are correct, and the audit cross-checks them for every
designator. `tools/circuit_export.py` is a verbatim copy of `harness-lab/circuit_export.py`
from `archive/rev38-power-entry-2026-09-25`.

## Controller header J4 (Molex Micro-Fit 3.0, 2x8, SELV)

| Pin | Net | Direction / meaning |
| ---: | --- | --- |
| 1 | V15_SELV | Out: IRM-20-15 output for the controller, fan and sensor boards |
| 2, 4, 15, 16 | SELV_GND | Return |
| 3 | V3V3 | In: from the controller's 3.3 V regulator; powers the SELV sides of U1, U2, U4, U7 |
| 5 / 6 | PWM_HA / PWM_LA | In: leg A high / low gate commands |
| 7 / 8 | PWM_HB / PWM_LB | In: leg B high / low (four independent signals allow phase-shift control) |
| 9 | PERMIT | In: active high. Low, floating or unpowered holds both drivers' DIS high (outputs off) |
| 10 | BUS_OCP_OK | Out: high = bus current below ~91 A. Low = shoot-through trip **or** HOT side unpowered (ISO7710F defaults low). Feed the interlock latch that drops PERMIT |
| 11 / 12 | VBUS_P / VBUS_N | Out: AMC1311 differential output. V(P) − V(N) ≈ bus voltage / 120 (unity-gain amplifier; 198 V → 1.65 V; confirm gain and common-mode on the datasheet) |
| 13 / 14 | CT_S1 / CT_S2 | Out: tank CT secondary (1:100). The burden and OCP/phase comparators are on the current-sense board; retune its burden for the full-bridge peak |

Required on the controller side (not on this board):
- the latch that drops PERMIT on BUS_OCP_OK low, tank OCP, over-temperature or a watchdog timeout (the interlock board)
- a CT zero-crossing phase comparator that inhibits switching before the tank goes capacitive
- the SELV_GND to PE bonding decision

## Domains and barrier

HOT reference is `LEG_RET`, the leg side of the 1 mΩ shunt; layout must star it at shunt pad 2.
Only these parts may cross HOT↔SELV, and the audit enforces each pin's side:

- UCC21550 (U1, U2)
- AMC1311 (U4)
- ISO7710F (U7)
- CST3015 (T1)
- IRM-20-15 (PS1)

Creepage and clearance for the ~200 V bus and ~430 V-peak tank nodes are layout work (PCB
rules not yet written).

## Safety chain implemented in hardware

| Fault | Path |
| --- | --- |
| Hard short or bridge failure | F1 20 A slow-blow ceramic |
| Shoot-through / MOSFET short | 1 mΩ shunt → TLV3201 (~91 A) → ISO7710F → BUS_OCP_OK low → interlock latch → PERMIT low → DIS |
| Tank over-current / pan fault | CT → current-sense board comparators → interlock latch |
| Heatsink or glass over-temperature | Off-board Microtemp cutoffs in the J3 loop open the IRM-05-15 input: all gate drive, HOT 5 V and BUS_OCP_OK drop. No electronics or firmware involved |
| Controller hang / reset | Interlock-board watchdog; PERMIT floating = disabled |
| Gate-supply loss | UCC21550 UVLO holds outputs low; 10 kΩ gate-source hold-off |
| Line surge | TMOV20RP175E (175 Vrms, 455 V clamp) ahead of 650 V MOSFETs |

## Open before native board / fabrication

1. **Coil measurement** (COIL-MC.md). Sets the resonant bank value (0.54 µF now, for 70 µH / 32 kHz), CT burden and frequency limits.
2. **Parts to confirm against manufacturer drawings:**
   - Phoenix 1711026 order code
   - Littelfuse 102071 clip current rating (≥ 20 A)
   - TDK B82726S2203A020 pin numbering
   - Molex 0430451612 order code
   - 942C AC voltage rating vs frequency (≈236 V rms at line crest, 35 kHz)
3. **Footprints to draw or vendor:**
   - `temper:TMOV20RP_ReviewOnly`
   - `temper:B82726S2_ReviewOnly`
   - three `temper:CDE_942C_*_Axial_ReviewOnly`
   - `temper:Diode_Bridge_GBJ2510` (exists on the power-entry branch)
   - `lib:SOIC16W_Isolated`, `temper:CST3015` (in `pcb/libs`)
4. **Under-glass cutoff rating:** needs a glass-underside temperature measurement at the 482 °F setpoint; heatsink cutoff about 120 °C, from available G4A ratings.
5. **Bench:** dead time (39 kΩ ≈ 348 ns nominal), gate resistors, snubber value, OCP trip calibration, ZVS at light load.

Physical assembly, powered test, EMI, insulation and certification: **NOT RUN**.

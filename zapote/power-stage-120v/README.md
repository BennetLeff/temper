# power-stage-120v: full-bridge induction power stage

Status: **source compiled and audited; 240 × 160 mm four-layer placement
generated; native-06 routed and checked for renewed D4 review; physical NOT RUN.**
Design basis and justification: `docs/hardware/power-section-120v/` (POWER-SECTION.md,
LOSS-REFACTOR.md, COIL-MC.md). Front-end decision: `docs/adr/2026-09-25-front-end-architecture-brief.md`.

One board carries the mains entry, EMI filter, bridge rectifier and film bus, the full
bridge with both UCC21550 drivers next to the MOSFETs, the resonant capacitor bank and tank
current transformer, the DC-bus shoot-through OCP, isolated bus-voltage sense, the
thermal-cutoff-gated gate supply, and the SELV 15 V supply. The SELV controller (ESP32 plus the
integrated interlock, thermal-sense and RTD front end) connects through one SELV header (J4). Tank
over-current sensing is on this board (T1, U10–U13 → bus_fault); zapote/current-sense is a
bench-qualification unit only.

Native construction records: [progress](BUILD-PROGRESS.md),
[toolchain](TOOLCHAIN.md), [local footprints](FOOTPRINTS.md),
[earlier native results](NATIVE-02.md), [current routing](ROUTING.md),
[placement review](PLACEMENT-REVIEW.md), [oracle assessment](ORACLE-REVIEW.md),
[placement decisions](DECISIONS.md),
[return-current rules](RETURN-PATHS.md), and
[insulation preflight](RULES-PREFLIGHT.md). The revised 240 × 160 mm outline
and four layers are approved; the revised placement needs renewed D4 review.
D5 conditionally permits an 8.0 mm placement floor on
verified group IIIa-or-better laminate with one functional PE bond; insulation
qualification and airflow remain open. See [D5 basis](D5-BASIS.md).

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
byte-identical, after path normalization, between two independent source snapshots (see the receipt).
`build-receipt.json` pins the hashes. Current result: 114 components, 75 nets. The audit
passes, and 48/48 tests pass, including deliberate miswires and the reference-bias regression.

**Part identity comes from `resolved-components.json` and the CSV, never from `default.net`.**
Atopile 0.2.69 writes a footprint-aliased part into the netlist's libsource field. In this
build, every 0603 resistor appears as `RC0603FR-071KL` and the LM4040 as `AO3400A`. The CSV BOM
and the per-instance resolved export are correct, and the audit cross-checks them for every
designator. `tools/circuit_export.py` is a verbatim copy of `harness-lab/circuit_export.py`
from `archive/rev38-power-entry-2026-09-25`.

## Fault interface

J4.10 now provides **BUS_FAULT**, low when both comparators are healthy and
high on either trip. U8 is a NAND; U9 is the non-F, default-high ISO7710.
This matches [the interlock's](../interlock/INTERFACES.md) active-high fault
contract without a polarity adapter. Input-side power loss defaults high
only with the output supply valid. HOT5 brownout, controller-supply loss,
return-wire faults and complete shutdown timing remain unqualified; see
[FAULT-INTERFACE.md](FAULT-INTERFACE.md).

## Controller header J4 (Molex Micro-Fit 3.0, 2x8, SELV)

| Pin | Net | Direction / meaning |
| ---: | --- | --- |
| 1 | BIAS_GOOD_J4 | Out: BIAS_GOOD (U40) through R146 220 k, high while the bias monitors are good and the heartbeat runs (stage 48, OPEN-ITEMS B13 H2). The controller must read it high-Z (≥ 1 MΩ pull-down). Was V15_SELV (PS1) until stage 38; the controller is powered through its J13 |
| 2, 4, 15, 16 | SELV_GND | Return |
| 3 | V3V3 | In: controller 3.135–3.465 V rail matching the interlock contract; powers the SELV sides of U1, U2, U4, U9 |
| 5 / 6 | PWM_HA / PWM_LA | In: leg A high / low gate commands |
| 7 / 8 | PWM_HB / PWM_LB | In: leg B high / low (four independent signals allow phase-shift control) |
| 9 | PERMIT | In: active high. Low, floating or unpowered holds both drivers' DIS high (outputs off) |
| 10 | BUS_FAULT | Out: healthy low; high on shunt OCP (≈61 A), bus OVP (≈280 V) or tank-CT over-current either polarity (≈55 A; DC corner band 50.9–59.5 A). U13 ORs the isolated bus fault with the tank-CT comparators on the SELV side. Fully unpowered HOT side defaults high while the controller supply is valid. |
| 11 / 12 | VBUS_P / VBUS_N | Out: AMC1311 differential output. V(P) − V(N) ≈ bus voltage / 120 (unity-gain amplifier; 198 V → 1.65 V; confirm gain and common-mode on the datasheet) |
| 13 | CT_ZC | Out: tank-current zero crossing (TLV3201 push-pull, 3.3 V logic). Undefined with no tank current: the controller must ignore it when idle |
| 14 | CT_MON | Out: biased tank-current waveform through 1 kΩ: 1.65 V + I_tank × 15 mV/A (1:100 into 1.5 Ω). The host input must be high impedance (≥ 10 MΩ assumed by the model) |

Required on the controller side (not on this board):
- the active-high-fault latch that drops PERMIT on BUS_FAULT high, tank OCP, over-temperature or a watchdog timeout
- phase control from CT_ZC that inhibits switching before the tank goes capacitive (the comparator is on this board; the inhibit logic is not)
- integration respecting the single functional PE bond implemented on this board

## Domains and barrier

HOT reference is `LEG_RET`, the leg side of the 1 mΩ shunt; layout must star it at shunt pad 2.
Only these parts may cross HOT↔SELV, and the audit enforces each pin's side:

- Infineon 2EDR8259X (U1, U2; UCC21550 until stage 28, DECISIONS 31)
- AMC1311 (U4)
- ISO7710 (U9)
- CST3015 (T1)
- IRM-20-15 (PS1)

The controller return has one removable functional 0 Ω PE link. It is not
a protective-earth path and does not waive HOT-to-controller insulation.

Provisional creepage and clearance rules are applied to the routed board. The full-bridge differential
RMS and peak voltages across each barrier remain unverified; the historical
tank peak is not a sufficient basis for selecting creepage bands. See
[RULES-PREFLIGHT.md](RULES-PREFLIGHT.md).

## Safety chain implemented in hardware

| Fault | Path |
| --- | --- |
| Hard short or bridge failure | F1 25 A time-delay ceramic (Eaton Bussmann MDA-25-R: 10 kA @ 125 Vac, 1.5 kA @ 250 Vac) in 30 A 01220088Z clips |
| Shoot-through / MOSFET short | 1 mΩ DC-return shunt → TLV3201 (nominal ≈61 A) → NAND gate → ISO7710 → BUS_FAULT high → interlock latch → PERMIT low → DIS |
| Elevated DC bus | Bus divider → TLV3201 (nominal ≈280 V) → NAND gate → ISO7710 → BUS_FAULT high → interlock latch → PERMIT low → DIS; this inhibits restart but does not clamp bus voltage |
| Tank over-current / pan fault | CT (T1) → on-board comparators U10/U11, ORed with the bus fault in U13 → bus_fault → controller interlock latch |
| Heatsink or glass over-temperature | Off-board Microtemp cutoffs in the J3 loop open the IRM-05-15 input: gate drive and HOT 5 V drop; BUS_FAULT defaults high if controller 3.3 V remains valid. No electronics or firmware involved |
| Controller hang / reset | Interlock-board watchdog; PERMIT floating = disabled |
| Gate-supply loss | 2EDR8259X UVLO and active output clamp hold outputs low; 10 kΩ gate-source hold-off |
| Line surge | TMOV20RP175E (175 Vrms, 455 V clamp) ahead of 650 V MOSFETs |

## Open before fabrication and powered qualification

1. **Coil measurement** (COIL-MC.md). Sets the resonant bank value (0.54 µF now, for 70 µH / 32 kHz), CT burden and frequency limits.
2. **Parts to confirm against manufacturer drawings:**
   - J1 is Phoenix 1714971 (MKDS 5/2-9,5, UL/CSA group B 30 A; stage 27) for L/N only; J6 is a Phoenix 1704004 PE branch from the chassis stud. J2/J5 and the four disconnect terminals use Würth 74650074; assembly, temperature and spacing qualification remain open.
   - ~~Littelfuse 102071 clip current rating~~ (10 A): replaced by 30 A 01220088Z clips. The fuse is now Eaton Bussmann MDA-25-R (25 A, 10 kA @ 125 Vac), DECISIONS.md 2026-10-08
   - ~~TDK B82726S2203A020 pin numbering~~ (confirmed from datasheet 2026-09-25: windings 1-4, 2-3)
   - ~~Molex 0430451612 order code~~: a real, current Micro-Fit 3.0 2×8 vertical part that matches the footprint and pinout. Its mate is 43025-1600 + 43030-0007 (`validation-results/08-manufacturing-package/native-21/owner-items/order/ORDER-PACKAGE.md` §1c). Only the post-hole check against Molex drawing 430451612_sd is left
   - 942C AC voltage rating vs frequency (≈ 236 V rms at line crest, 35 kHz): CDE's 1200 Vdc curves (942C.pdf p.4) have no 0.22 µF trace. The 0.33 µF trace allows ≈ 270 V rms at 35 kHz (read from the plot), and the smaller value allows more, so it passes at 25 °C. The hot-spot rating stays a bench item
3. **Footprint qualification:** all current local footprints are now
   in `libraries/`. [FOOTPRINTS.md](FOOTPRINTS.md) records their drawing
   references and provisional formed-lead, retention and assembly limits.
4. **Under-glass cutoff rating:** needs a glass-underside temperature measurement at the 482 °F setpoint; heatsink cutoff about 120 °C, from available G4A ratings.
5. **Bench:** dead time (39 kΩ ≈ 348 ns nominal), gate resistors, snubber value, OCP trip calibration, ZVS at light load.

Physical assembly, powered test, EMI, insulation and certification: **NOT RUN**.

The release gates (two tiers: bench prototype lot vs mains-connected / product release) are in
`validation-results/08-manufacturing-package/native-21/fab/FAB-NOTE.md`. The owner decisions M6, M10
and M11 are in DECISIONS.md (2026-10-08). The integrated SELV controller that drives J4 is captured in
`zapote/controller/`.

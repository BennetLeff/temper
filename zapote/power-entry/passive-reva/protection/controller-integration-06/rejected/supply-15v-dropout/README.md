# A5 HOT15/5V supply candidate

Source identity: Temper/Zapote revision `5dde29ab3e2f1223c2d33c129ced2cf647238307`.
The frozen consumer is `zapote/power-entry/passive-reva/protection/f2-shutdown-04/source-07/elec/src/power_entry_f2_shutdown_revb.ato`.
This directory is a standalone integration candidate; it does not modify that
receipt-bound source or claim installed hardware qualification.

## Decision

Select **Mean Well IRM-10-15 → TPS7A4701RGW (HOT15) + TPS54202DDCR (5 V)**.

The IRM-10-15 is retained as the producer candidate (15 V, 0.67 A, ±2.5%
output tolerance; its OVP range is 17.25–20.25 V). The raw output never feeds
UCC27511ADBVR. TPS7A4701 is a 36 V, 1 A LDO with 2.5% overall accuracy and a
15 V ANY-OUT setting, so the 20.25 V producer OVP is reduced to a bounded HOT15
rail. TPS54202 is a 4.5–28 V, 2 A synchronous buck; TI's 8–28 V, 5 V/2 A
reference design covers the complete IRM envelope and supplies the logic5
port. The 5 V converter is intentionally independent so the existing
`sup_aux` and `sup_logic` checks can observe either rail missing.

Candidate B was an all-linear variant (IRM-10-15 → TPS7A4701 at 15 V and a
second TPS7A4701 at 5 V). It is rejected because a 20.25 V input dissipates
`(20.25-5)*I5`; even 100 mA is 1.53 W in the 5 V regulator, while the selected
buck avoids that heat and has explicit 2 A current limit/hiccup behavior.

## Netlist and rail contract

```text
IRM-10-15 AC input (external branch protection required)
  OUT+ = AUX_RAW (14.625..20.25 V including stated OVP range)
  OUT- = PFC_BUS_MINUS / HOT_GND

AUX_RAW -> TPS7A4701RGW VIN (pins 15,16), EN pin 13 tied to VIN
TPS7A4701 OUT pins 1,20 -> AUX15 (HOT15 consumer port)
TPS7A4701 FB/SENSE pin 3 -> OUT
ANY-OUT pins 4 (6P4V2), 5 (6P4V1), 9 (0P8V) -> HOT_GND; other program pins open
NR pin 14 -> 1 uF -> HOT_GND; IN >= 10 uF and OUT >= 20 uF ceramic

TPS3700DDCR VDD pin 5 -> LOGIC5, GND pin 2 -> HOT_GND
AUX15 -> 3.83 MOhm / 100 kOhm -> TPS3700 INB_N pin 4
TPS3700 OUTB pin 6 (open-drain active-low) -> AUX15_OV_N, 10 kOhm pull-up to LOGIC5
The host must AND AUX15_OV_N with `clear_ok`; this is an overvoltage cut path,
not a status-only telemetry signal. OUTA is unused (UV remains the retained
TPS3890 path).

AUX_RAW -> TPS54202DDCR VIN pin 3; GND pin 1 -> HOT_GND
TPS54202 SW pin 2 -> 15 uH -> LOGIC5; BOOT pin 6 -> 100 nF -> SW
FB pin 4: 100 kOhm (LOGIC5 to FB), 13.3 kOhm (FB to HOT_GND)
EN pin 5: 1 MOhm from AUX_RAW, 100 kOhm to HOT_GND
LOGIC5 is the buck output, with >=22 uF at the load.
```

The 1 MΩ/100 kΩ EN divider gives approximately 1.33 V at 14.625 V and
1.84 V at 20.25 V, below the TPS54202 5.5 V EN limit and above its 1.28 V
rising threshold. The pulldown leaves the buck disabled with no producer.

The selected run contract is:

| Port | Conditional operating range | Source/condition |
|---|---:|---|
| `AUX_RAW` | 14.625–20.25 V | IRM-10-15 15 V ±2.5%, stated OVP range |
| `AUX15` | 14.25–15.75 V while RUN is permitted | TPS7A4701 15 V ANY-OUT, <=75 mA, measured dropout <=0.30 V at low line; TPS3700 must assert `AUX15_OV_N=0` before the upper bound |
| `LOGIC5` | 4.75–5.25 V while logic is permitted | TPS54202 5 V reference design, <=0.20 A design load; UVLO/thermal/inductor validation pending |
| UCC27511A VDD | 4.5–18 V recommended | TI UCC27511A; `AUX15` supervisor must remove RUN outside the port range |

The 15 V LDO's 36 V input rating gives margin over 20.25 V; its output does
not follow the producer OVP. The independent TPS3700 monitor is powered from
logic5 so an AUX15 high-side failure does not remove the monitor's supply. Its
3.83 MΩ/100 kΩ trip is a nominal calculation and needs tolerance/temperature
verification. The 5 V buck's 28 V recommended input rating is
also above 20.25 V. Upstream excursions above 20.25 V remain outside the
IRM source contract and need a separate transient test; the LDO absolute
rating alone is not an acceptance claim.

`ARM` and `PERMIT` are not generated here. They remain explicit inputs to the
revB protection module, with their HOT/SELV ownership and edge protocols to be
integrated by the host. No tied-healthy signal is used to claim closure.

## Sources and pin maps

- [Mean Well IRM-10 specification](https://www.meanwell.com/Upload/PDF/IRM-10/IRM-10-SPEC.PDF): 15 V/0.67 A, ±2.5%, OVP 17.25–20.25 V (source fact retained by `INTERFACE-DESIGN.md`).
- [TI TPS7A4700/TPS7A4701 datasheet](https://www.ti.com/lit/ds/symlink/tps7a47.pdf): 3–35 V recommended input, 36 V absolute, 1 A, 2.5% overall accuracy, ANY-OUT 15 V table, RGW pin map, 216 mV typ dropout at 0.5 A and 307 mV typ at 1 A.
- [TI TPS54202 datasheet](https://www.ti.com/lit/ds/symlink/tps54202.pdf): 4.5–28 V input, 2 A output, pin map (GND1/SW2/VIN3/FB4/EN5/BOOT6), 5 V/2 A reference design, UVLO and EN thresholds.
- [TI UCC27511A datasheet](https://www.ti.com/lit/ds/symlink/ucc27511a.pdf): retained driver recommended VDD 4.5–18 V and 20 V absolute maximum.
- [TI TPS3700 datasheet](https://www.ti.com/lit/ds/symlink/tps3700.pdf): 1.8–18 V monitor supply, 0.4 V adjustable comparator reference, open-drain OV/UV outputs, SOT-23-6 pin map.

The ATO source is [source/hot15_logic5_supply.ato](source/hot15_logic5_supply.ato).

## Evidence boundary

The SPICE deck is a monotone screening model of regulator dropout, UVLO,
soft-start and load; it is not a vendor transient model or a physical clamp
proof. It checks normal startup, low-line dropout, 20.25 V OVP, collapse and
recovery, and a 5 V load step. Before schematic release, characterize IRM
startup/overload hiccup, regulator dropout at the real 75 mA load and hot
temperature, buck inductor/ripple/EMI, and rail-order behavior with the real
F2 supervisor. Keep ARM/PERMIT integration and the upstream AC branch fuse as
separate ownership rows.

Run the screening checks from this directory:

```text
ngspice -b ngspice/supply_interface.cir -o /tmp/a5-supply-ngspice.log
cargo test --manifest-path rail-contract/Cargo.toml
```

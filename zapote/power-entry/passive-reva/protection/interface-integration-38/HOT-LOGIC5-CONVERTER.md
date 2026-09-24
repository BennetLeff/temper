# Rev38 HOT logic5 converter candidate

Status: **Atopile circuit candidate joined and exact-pin audited; electrical and physical qualification OPEN.**
`elec/src/hot_logic5_converter.ato` defines one source path from
`AUX_PROTECTED`/`HOT0` to `HOT_LOGIC5`/`HOT0`. Its input must join **after**
the LTC4368 cutoff. No bypass from `AUX15_PRECUT` or `RAW_AUX24` to the
5 V rail is allowed. The module is now joined in
`power_entry_integrated_38.ato`.

## Circuit and exact pins

The selected IC is [TI TPS54202DDCR](https://www.ti.com/lit/ds/symlink/tps54202.pdf),
the SOT-23-6, 4.5–28 V input, 2 A synchronous buck. It has internal 5 ms
typical soft start and 500 kHz nominal switching. The [TI 5 V reference
design](https://www.ti.com/lit/ds/symlink/tps54202.pdf) uses a 15 µH
inductor, two 22 µF output capacitors, 100 kΩ/13.3 kΩ feedback, and a
75 pF feedforward capacitor. The [official EVM guide](https://www.ti.com/lit/ug/slvuap3a/slvuap3a.pdf)
confirms the 510 kΩ/105 kΩ EN divider and component positions. These are
reference starting values at a broader 8–28 V input range and a 2 A test
load; they are not a qualified Rev38 load budget.

| DDC pad | Function | Rev38 net or connection |
| ---: | --- | --- |
| 1 | GND | `HOT0`; Kelvin return for feedback bottom |
| 2 | SW | `BUCK_SW` to 15 µH inductor and BOOT capacitor |
| 3 | VIN | `AUX_PROTECTED` after the cutoff |
| 4 | FB | `BUCK_FB`, 100 kΩ top/13.3 kΩ bottom and 75 pF across top |
| 5 | EN | 510 kΩ from `AUX_PROTECTED`, 105 kΩ to `HOT0` |
| 6 | BOOT | 100 nF to `BUCK_SW` |

TI specifies **5.5 V maximum recommended on EN**, so EN cannot connect to
the 15 V protected rail directly. The nominal resistor divider alone gives
2.56 V at 15 V input; TI's internal EN source current adds to that node.
Even at 18 V input the nominal resistive value is 3.07 V. The divider
provides converter startup control, not the independently required HOT
rail-good or safety permission. The actual enable thresholds, hysteresis,
source slew and reset ordering need measurement.

| Function | Exact candidate MPN | Nominal and package | Basis |
| --- | --- | --- | --- |
| Buck | `TPS54202DDCR` | SOT-23-6 | TI data sheet and EVM |
| VIN ceramics ×2 | [`C3225X7R1H106K250AC`](https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=C3225X7R1H106K250AC) | 10 µF, 50 V, X7R, 1210 each | TDK production part; total 20 µF nominal |
| VIN HF, BOOT | `GRM188R71H104KA93D` | 100 nF, 50 V, X7R, 0603 each | Existing Rev38 local capacitor; TI requires BOOT-to-SW 100 nF |
| Inductor | [`XGL6060-153MEC`](https://www.coilcraft.com/en-us/products/power/shielded-inductors/molded-inductor/xgl/xgl6060/xgl6060-153/) | 15 µH ±20%, 31.1 mΩ max DCR at 25 °C; 4.4 A at 20% L drop at 25 °C | Coilcraft; **custom land pattern still needed** |
| VOUT ceramics ×2 | [`C3225X7R1E226M250AB`](https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=C3225X7R1E226M250AB) | 22 µF, 25 V, X7R, 1210 each | TDK production part; 44 µF nominal |
| FB top/bottom | [`ERA3AEB104V`](https://industrial.panasonic.com/ww/products/pt/high-precision-chip-resistors/models/ERA3AEB104V) / [`ERA3AEB1332V`](https://industrial.panasonic.com/ww/products/pt/high-precision-chip-resistors/models/ERA3AEB1332V) | 100 kΩ / 13.3 kΩ, 0.1%, ±25 ppm/K, 0603 | Panasonic; TI 5 V reference ratio |
| FB feedforward | `GRM1885C1H750JA01D` | 75 pF, 50 V, C0G, 0603 | TI EVM BOM; directly across 100 kΩ top |
| EN top/bottom | `CRCW0603510KJNEA` / `CRCW0603105KFKEA` | 510 kΩ, 5% / 105 kΩ, 1%, 0603 | TI EVM BOM; not a precision rail threshold |

The installed KiCad footprint `Package_TO_SOT_SMD:SOT-23-6` exists.
`TBD_REVIEW_ONLY:HOT_LOGIC5_XGL6060_15UH` is deliberately an unimplemented
footprint marker. The selected Coilcraft part shares the XGL6060 mechanical
family with the Rev38 18 µH buck inductor, but both need a manufacturer
land-pattern comparison and a native footprint before a PCB can be released.

## Electrical screens and supply accounting

With TI's 0.581–0.611 V FB range and the nominal 100 kΩ/13.3 kΩ pair,
`VOUT = VFB × (1 + 100/13.3)` gives **5.077 V nominal** at 0.596 V FB.
Allowing independent ±0.1% resistor initial tolerances and independently
adverse ±25 ppm/K movement across an illustrative 100 K difference from
the 25 °C reference gives a **feedback-only** 4.919–5.237 V range. This
omits FB input current, resistor aging, line/load effects, output ripple,
transient overshoot and layout. It is **not** a guaranteed 5 V terminal
window. Check all connected logic absolute and recommended VDD limits, and
the 4.531 V nominal HOT supervisor falling threshold, against measured
waveforms before calling the receiver rail valid.

Ideal inductor ripple at 15 V → 5 V, 500 kHz and 15 µH is **0.444 A
peak-to-peak**; at the −20% inductance tolerance edge it is 0.556 A.
At the IC's 28 V recommended input ceiling these are 0.548/0.685 A.
These numbers do not include inductance change with DC bias or temperature.
At 2 A nominal load the latter screen implies 2.343 A ideal peak, below
Coilcraft's published 2.9 A at 10% inductance loss at 25 °C. It does not
establish usable 2 A output from the Rev38 AUX source or a hot-temperature
inductor/IC limit.

**Cutoff startup load changes:** the new buck connects **20.1 µF nominal**
directly across `AUX_PROTECTED`/`HOT0` (two 10 µF parts plus 100 nF). At
15 V this bank's ideal charge is **301.5 µC**, before the existing direct
AUX loads and cutoff VOUT capacitor. This value must enter LTC4368 GATE
slew, shunt and MOSFET inrush/SOA calculations. Its effective capacitance
under 15 V DC bias, tolerance, temperature and aging is unknown.

The buck output adds 44 µF nominal to the joined netlist's 25 × 100 nF
HOT-logic bypass, making **46.5 µF nominal** downstream of the inductor.
Its ideal charge to 5 V is **232.5 µC**. If all capacitance charged linearly
through TI's *typical* 5 ms soft start, the arithmetic average capacitor
current would be 46.5 mA, excluding logic load; neither a peak nor a
guaranteed startup-current bound follows. The old 75 mA logic5 allowance
is historical, and the 2 A IC rating is not a current allocation from the
IRM-20-24 → 15 V buck → cutoff chain.

## Validation and open gates

The standalone and joined modules compiled with cached Atopile 0.2.69 using
`ato build -b hot_logic5_converter -b integrated -t netlist -t bom`. Its generated netlist
places TPS54202 pad 3 on `aux_protected`, pad 1 on `hot0`, pad 2 on
`buck_sw`, pad 6 on `buck_boot`, pad 4 on `buck_fb`, and pad 5 on
`buck_en`; the output inductor alone joins `buck_sw` to `hot_logic5`.
The generated **CSV BOM** retains every selected MPN. `audit.rs` now checks
the exact MPN and pin/net mapping in both the standalone and joined builds,
including negative mutations for a switch/output short and pre-cutoff VIN
bypass. As elsewhere in
Rev38, Atopile's netlist `libsource part` can alias MPNs when several
classes share one footprint; use the CSV BOM to audit component identity.
No native schematic/PCB or physical measurement was made.

Before this becomes a qualified producer: obtain DC-bias/effective-value
curves for both MLCC banks; tally worst-state and startup `I_5V(t)` at all
temperature and rail-order cases; bound the required upstream power and
cutoff inrush with relay and PFC startup overlapping; test the actual
feedback loop and load steps at light-load pulse skip and full intended
load; measure 5 V overshoot, undervoltage and reset timing under AUX
cutoff, shorts, source hiccup and repeated starts. Layout must keep VIN
and GND capacitor loops short, SW copper controlled, and the FB trace and
Kelvin return away from SW, following TI's layout guidance. The receiver
must remain disarmed whenever this rail or its supervisor is outside the
accepted operating region.

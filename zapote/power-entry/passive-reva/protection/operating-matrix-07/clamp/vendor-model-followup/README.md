# Diodes Inc. BAV23C alternative-model clamp screen

This is an isolated, bounded simulation of the UCC28180 ISENSE clamp. It
does not edit the selected Vishay `BAV23C-E3-08` candidate, the canonical
source, or the existing assumed model. The model tested here is from **Diodes
Incorporated**, while the selected part and PDF in the adjacent `clamp/`
directory are Vishay parts. The shared name does not make them the same
manufacturer or a qualified drop-in.

## Source identity

Primary source URL:
`https://www.diodes.com/spice/download/1530/BAV23C.spice.txt`

Retained source: `diodes-bav23c.spice.txt`, SHA-256
`aa03e4db0360c580a2ab13f1a9054ae32ca9739b31d8653d37e3d8376c732c6d`.
The source declares `DI_BAV23C`, a 200 V / 0.400 A / 50 ns Diodes Inc.
switching diode, with `IS=237 nA`, `RS=0.260 ohm`, `BV=200 V`, `IBV=100 nA`,
`CJO=3.05 pF`, `N=2.69`, and `TT=72 ns`. Diodes' source disclaimer says the
model is supplied “as is” without a warranty that the model or a simulation
is error-free. The temperature results below are therefore model behavior,
not vendor production limits.

The fixture uses the original 220-ohm path:

```text
shunt ── 220 ohm ── ISENSE
                         │
                    cathode
                    BAV23C die
                    anode
                         │
                        GND
```

The fixture is the common-cathode orientation required for a negative
ISENSE excursion. The reversed netlist is retained as a negative topology
control.

## Results

The Rust checker (`vendor_clamp_checks.rs`) owns the arithmetic and passes two
unit tests. The exact command was:

```text
rustc --edition=2021 --test vendor_clamp_checks.rs -o vendor_clamp_checks_tests
./vendor_clamp_checks_tests
rustc --edition=2021 -O vendor_clamp_checks.rs -o vendor_clamp_checks
./vendor_clamp_checks vendor-clamp.log vendor-clamp-temp-control.log \
  vendor-clamp-fault-temp.log vendor-clamp-reversed.log
```

At the **maximum PCL threshold anchor** of -0.438 V, ngspice's default 27 °C
model point is `ISENSE=-0.417126 V`, `I_D=94.88 µA`. At the explicit temperature
points, the same shunt gives:

| model temperature | ISENSE | diode current | shift from -0.438 V | 1 µA / 2 mV screen |
| ---: | ---: | ---: | ---: | --- |
| -40 °C | -0.436703 V | 5.89 µA | 1.30 mV | fail (current) |
| -20 °C | -0.434348 V | 16.6 µA | 3.65 mV | fail |
| 25 °C | -0.418288 V | 89.6 µA | 19.7 mV | fail |
| 85 °C | -0.368078 V | 318 µA | 69.9 mV | fail |
| 125 °C | -0.322463 V | 525 µA | 115.5 mV | fail |

The shift/current relation is checked from the actual resistor equation,
`I = (ISENSE - VSHUNT) / 220 ohm`. The chosen 1 µA and 2 mV values remain
engineering screens; they are not TI requirements. The alternative model
does not pass that screen, including at 25 °C. This result is materially
different from the adjacent assumed model and is evidence that an assumed
model cannot establish low-disturbance PCL behavior.

For the declared -5 V shunt excursion, the model holds the controller-side
node **above** TI's -1.1 V pin target at every tested temperature:

| model temperature | ISENSE | diode current |
| ---: | ---: | ---: |
| -40 °C | -0.877403 V | 18.739 mA |
| 25 °C | -0.793733 V | 19.119 mA |
| 85 °C | -0.713783 V | 19.483 mA |
| 125 °C | -0.659357 V | 19.730 mA |

These currents are the model's DC result through the 220-ohm path. They are
not a transient SOA or board-thermal qualification. The reversed topology
control at -1.5 V leaves ISENSE at -1.499950 V and fails the -1.1 V target,
so the polarity check is causally exercised.

## Effective trip-point extraction

The fixed -0.438 V comparison above is not itself a trip-point result. A
second Rust-checked fixture sweeps the shunt from -0.05 V to -1.50 V at each
temperature and linearly interpolates the shunt voltage required for the
controller-side pin to reach the TI SOC target (-0.285 V), the typical PCL
target (-0.400 V), and the maximum PCL threshold anchor (-0.438 V). The
10-milliohm source shunt converts each shunt voltage to the effective current
`I = |VSHUNT| / 0.010 ohm`; the ideal column is the same calculation with no
clamp shift. Results are model-only:

| temperature | SOC shunt / current | PCL typical shunt / current | PCL max anchor shunt / current |
| ---: | ---: | ---: | ---: |
| -40 °C | -0.28508 V / 28.508 A | -0.40066 V / 40.066 A | -0.43933 V / 43.933 A |
| -20 °C | -0.28528 V / 28.528 A | -0.40203 V / 40.203 A | -0.44189 V / 44.189 A |
| 25 °C | -0.28783 V / 28.783 A | -0.41512 V / 41.512 A | -0.46423 V / 46.423 A |
| 85 °C | -0.31019 V / 31.019 A | -0.50305 V / 50.305 A | -0.60122 V / 60.122 A |
| 125 °C | -0.36082 V / 36.082 A | -0.67188 V / 67.188 A | -0.84948 V / 84.948 A |

Relative to the ideal 10-milliohm shunt, the model's PCL-max current increase
is approximately 0.30% (-40 °C), 0.89% (-20 °C), 5.99% (25 °C), 37.26%
(85 °C), and 93.95% (125 °C). At the PCL-max crossings, the corresponding
model diode currents are 6.04 µA, 17.7 µA, 119 µA, 742 µA and 1.87 mA.
These values explain why the 1 µA / 2 mV screen is not the only useful metric:
the model predicts a temperature-dependent shift of the actual controller
trip point. It still does not establish the real part's temperature behavior.

The extraction command was:

```text
ngspice -b -o vendor-clamp-thresholds.log vendor-clamp-thresholds.cir
rustc --edition=2021 --test vendor_threshold_checks.rs -o vendor_threshold_checks_tests
./vendor_threshold_checks_tests
rustc --edition=2021 -O vendor_threshold_checks.rs -o vendor_threshold_checks
./vendor_threshold_checks threshold_m40.tsv threshold_m20.tsv threshold_25.tsv \
  threshold_85.tsv threshold_125.tsv
```

## Interpretation and next options

This alternative model supports three narrow conclusions:

1. The controller-side placement and polarity are the right topology to
   test. Reversing the die fails the pin-voltage protection check.
2. A manufacturer model with ordinary temperature behavior predicts
   substantial forward conduction around the -0.438 V PCL point. It does not
   support the existing nominal assumption of negligible current.
3. The -5 V DC screen is above -1.1 V at ISENSE, but its roughly 19 mA diode
   current must still be checked against pulse duration, repetition, resistor
   pulse energy, package power and board temperature.

The Diodes Inc. model cannot qualify the Vishay BAV23C-E3-08. Before adopting
either part, obtain a guaranteed low-current `VF(min)`/`VF(max)` versus
temperature and tolerance, or characterize assembled parts at the actual
PCL crossing and inrush waveform. If a vendor supplies bounds, replace the
single nominal diode with a Rust-checked bounded sweep. Do not select a new
part from this screen alone.

All fixture/source/output hashes are retained in the parent worktree's
transcript; the main outputs are the four `vendor-clamp*.log` files and the
Rust checker in this directory.

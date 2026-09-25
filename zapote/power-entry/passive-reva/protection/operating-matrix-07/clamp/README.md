# ISENSE clamp candidate (bounded simulation)

This output is an isolated, reviewable application of
`isense-clamp-candidate.patch` to a copy of the frozen source.  The canonical
source at `/private/tmp/temper-pkgs-1-4/elec/src/power_entry_passive_reva.ato`
was not edited.

## Source and export

- Pre-fix source SHA-256: `dd31c0addd5a5a5764955efca44d50d6fe89747f88c937e4c127398349b701d8`
- Candidate source SHA-256: `4d63a25896e3bd3ed9cb242c2d074a225de71acdb3351bfcbae24b2f73c6fdbb`
- Pinned command: `uv tool run --offline --from atopile==0.2.69 ato --non-interactive build elec/src/power_entry_passive_reva.ato:PowerEntryPassiveReva`
- Export command: existing `harness-lab/circuit_export.py`, entry `PowerEntryPassiveReva`
- Candidate netlist SHA-256: `8b7f452b8a92f410140dfb75476115455f894aba550ea5541976a325cfa6da55`
- Candidate BOM SHA-256: `8a03053637e9debff46a2c97004d0ea161decd78b5c85735cbf2a11a64beb69c`

Atopile compiled and the resolved-component export completed successfully.
The exported graph has U35 = `BAV23C-E3-08`, SOT-23 pin 1 on the resolved
`PFC_BUS_MINUS`/control-ground net, pin 3 on `isense` (the controller side of
U18's 220 ohm resistor), and pin 2 on an explicit `a_unused` net with no other
node.  U18 pin 2 remains on `minus` (the bridge-return shunt node).  These
relationships are checked by the Rust checker, not inferred from the BOM.

## SPICE model and tests

`clamp.inc` contains one selected die of the common-cathode BAV23C.  The
official Vishay datasheet was downloaded from
`https://www.vishay.com/docs/86374/bav23c.pdf` (SHA-256
`b05e055b9bddac73647119b108d61535c80f89b2ad12087d4cee28bb18106d96`).  A
three-minute search found no official Vishay SPICE deck; therefore the model
in `clamp.inc` is explicitly **ASSUMED**, chosen only to exercise the
polarity and resistor path.  Datasheet values (250 V minimum reverse rating,
1.0 V maximum VF at 100 mA and 25 °C, 1.25 V at 200 mA and 25 °C,
−55…150 °C operating range) are source facts, not guarantees of this model or
of the released assembly.

The five netlists use ngspice 45.2:

```text
ngspice -b -o clamp_pcl.log clamp_pcl.cir
ngspice -b -o clamp_negative.log clamp_negative.cir
ngspice -b -o clamp_reversed.log clamp_reversed.cir
ngspice -b -o clamp_temperature.log clamp_temperature.cir
ngspice -b -o clamp_temperature_negative.log clamp_temperature_negative.cir
rustc --edition=2021 -O clamp_checks.rs -o clamp_checks
./clamp_checks build/default.net build/default.csv clamp_pcl.log clamp_negative.log clamp_reversed.log clamp_temperature.log clamp_temperature_negative.log
rustc --edition=2021 -O source_graph_negative.rs -o source_graph_negative
./source_graph_negative /private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/source-build-01/build/default.net
```

The Rust-owned result is:

```text
PASS graph; pcl_isense=-0.437982 V pcl_diode=7.993e-8 A;
negative_isense=-0.953767 V negative_diode=0.018392 A;
reversed_isense=-5.000 V (expected fail)
```

The temperature screen is deliberately allowed to fail. It uses a chosen
loading screen of 1 µA and 2 mV (not a datasheet requirement):

| temperature | −0.438 V PCL loading | −5 V pin minimum |
| ---: | --- | --- |
| −20 °C | PASS, 2.28 nA, 0.001 mV | PASS, −0.994 V |
| 25 °C | PASS, 70.2 nA, 0.015 mV | PASS, −0.956 V |
| 85 °C | **FAIL**, 1.865 µA, 0.410 mV | PASS, −0.901 V |
| 125 °C | **FAIL**, 9.590 µA, 2.110 mV | PASS, −0.864 V |

The Rust checker exits 1 when those chosen PCL loading limits fail, while
retaining every row. This is an assumed-model sensitivity result, not a claim
that BAV23C violates a vendor limit; the model has no vendor temperature-curve
binding. `models/bav23c-assumed-v1.inc` retains the first model, which failed
the nominal PCL loading screen, and `models/bav23c-assumed-v2.inc` is the
current assumed model.

At the −0.438 V PCL point, the controller-side node changes by 18 µV and the
assumed model conducts 80 nA.  At a −5 V shunt excursion, the actual 220 ohm
path carries 18.392 mA and the clamp holds ISENSE at −0.954 V.  The current is
checked from `(V_ISENSE − V_SHUNT) / 220 ohm`; 5 mA is not treated as an
unconditional inrush bound.  Reversing the diode leaves ISENSE at −5 V and
fails the −1.1 V pin-minimum requirement as intended.

## Limits

Subsequent primary-source review is in `datasheet-audit/report.md`. Vishay's
typical forward curves show substantially more low-voltage conduction than
the assumed v2 model. Consequently, even its nominal passing result cannot
establish that the selected part leaves current limiting undisturbed. TI
does name BAV23C as a commonly used choice, but requires verification of its
forward-voltage window over temperature. The 1 uA / 2 mV loading limits are
chosen engineering screens, not published controller limits. No part is
qualified by the present clamp simulation.

This is a topology and nominal-model screen.  It does not establish the
UCC28180 transient response, inrush/short waveform, pulse SOA, resistor pulse
stress, BAV23C forward-voltage limits over −55…150 °C and tolerance, board
thermal behavior, or production qualification.  The candidate remains a
proposal until those conditions are separately bounded and verified.

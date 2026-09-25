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
in `clamp.inc` is explicitly **typical/assumed**, chosen only to exercise the
polarity and resistor path.  Datasheet values (250 V minimum reverse rating,
1.0 V maximum VF at 100 mA and 25 °C, 1.25 V at 200 mA and 25 °C,
−55…150 °C operating range) are source facts, not guarantees of this model or
of the released assembly.

The three netlists use ngspice 45.2:

```text
ngspice -b -o clamp_pcl.log clamp_pcl.cir
ngspice -b -o clamp_negative.log clamp_negative.cir
ngspice -b -o clamp_reversed.log clamp_reversed.cir
rustc --edition=2021 -O clamp_checks.rs -o clamp_checks
./clamp_checks build/default.net build/default.csv clamp_pcl.log clamp_negative.log clamp_reversed.log
```

The Rust-owned result is:

```text
PASS graph; pcl_isense=-0.437982 V pcl_diode=7.993e-8 A;
negative_isense=-0.953767 V negative_diode=0.018392 A;
reversed_isense=-5.000 V (expected fail)
```

At the −0.438 V PCL point, the controller-side node changes by 18 µV and the
assumed model conducts 80 nA.  At a −5 V shunt excursion, the actual 220 ohm
path carries 18.392 mA and the clamp holds ISENSE at −0.954 V.  The current is
checked from `(V_ISENSE − V_SHUNT) / 220 ohm`; 5 mA is not treated as an
unconditional inrush bound.  Reversing the diode leaves ISENSE at −5 V and
fails the −1.1 V pin-minimum requirement as intended.

## Limits

This is a topology and nominal-model screen.  It does not establish the
UCC28180 transient response, inrush/short waveform, pulse SOA, resistor pulse
stress, BAV23C forward-voltage limits over −55…150 °C and tolerance, board
thermal behavior, or production qualification.  The candidate remains a
proposal until those conditions are separately bounded and verified.

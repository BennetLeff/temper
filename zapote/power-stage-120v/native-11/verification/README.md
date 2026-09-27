# Native-11 verification, 2026-09-27: tank-CT detector

Board SHA-256: `2fec2924d64cf0e6a45b7a131b2797488e0edf13edecde1a21d45162febe1cbb`.

Native-11 is native-09's routing plus the tank-CT detector. The detector fixes
the task-06 finding that T1's secondary left the board with no burden
([validation-results/06](../../validation-results/06-controller-interface/README.md)).

The source now has 135 parts and 83 nets:
- the frozen build is in `build-receipt.json`
- the audit passes 53 tests
- the trip model is `tools/ct_detector/`

Native-10 is the placement. All 114 previous poses are unchanged; the 21 new
parts sit on a new SELV island lobe at T1's secondary (x 158–183.5,
y 61.8–86), with the fault OR beside J4. This is not a fabrication or
powered-operation release, and the placement change needs renewed D4 review.

## Changes from native-09

- **CT termination:** T1.3/T1.4 terminate at the burden (R39) and its
  capacitor (C42), 5 mm from the CT pins. CT_S1/CT_S2 no longer reach J4.
- **Header:** J4.13 is CT_ZC (digital zero crossing), J4.14 is CT_MON (biased
  waveform through 1 kΩ), and J4.10 is now OR(isolated bus fault, CT
  over-current either polarity).
- **Routing:** batch 06 (`tools/routes.py`) adds the detector, its plane ties
  and four west lanes (OC_NEG, OC_POS, ZC, MON), ordered so they don't cross.
  The lanes hop J4's bus-sense pair on B.Cu. Batch 03's U9 output now ends at
  U13 as BUS_FAULT_ISO.
- **SELV island:** the island polygon gains the east lobe, with a chamfer
  keeping 8 mm to SW_B's column step. The original x 158 edge moves to 157.5.
  It sat at exactly 8.000 mm from the In2 BUS_P fill, which the pinned
  Shapely oracle flagged as borderline; it now has 8.5 mm.

## Results

| Check | Result | Evidence |
| --- | --- | --- |
| Full KiCad DRC, fill + three repeats | 0 copper/clearance/courtyard findings; 0 schematic mismatch; 28 library + 3 silk warnings (unchanged); board bytes stable | `drc-*.json` |
| Opens | Only the intended R5 Kelvin split; LEG_RET clusters identical to native-09. Every new net is one connected cluster | `connectivity.json` |
| All-layer 8 mm barrier | 0 (Rust checker) and 0 (pinned Shapely oracle) | `barrier.json`, `barrier-oracle.json` |
| Source/native identity | PASS, 135 parts | `source-parity.json` |
| Saved copper identity | PASS, 6 route batches | `copper-identity.json` |
| Stackup gate | pass (JLC041622-7628, 1.653 mm) | `stackup.json` |
| JLCPCB 2 oz limits | PASS | `jlc-dfm.json` |
| Hardware surface | 0 hits | `hardware-surface.json` |
| Power screens | Unchanged from native-09: local row 0.886, western neck 0.457, SW_B 8.474 mm | `power-probes/` |
| Board tests | 44/44 (retargeted to native-10/11) | — |

Previews: [front](../previews/front.png), [inner return](../previews/inner-return.png),
[inner bus](../previews/inner-bus.png), [back](../previews/back.png).

## Not carried over

The owner's label and 3D-model presentation revision was applied to native-09.
Its tools expect the 114-part board, so it still has to be extended to the
21 new parts. Designator text size is still below JLCPCB's minimum (task 08).

# Source authority and model differences

The working tree has local changes; commit identity alone does not identify
these experiments. `source-identity.json` records full hashes of the explicitly
named files examined for this revision.

| Artifact | Status | Controller feedback | ISENSE clamp |
|---|---|---|---|
| Root `elec/src/power_entry_passive_reva.ato` | Retained 54-component baseline source | `hv_plus` / bank VB feeds upper divider | BAT54H,115; A at shunt.p2, K at control ground, before 220 Ω filter |
| `source-build-07/elec/src/power_entry_passive_reva.ato` | Historical rejected 133-part supervisor experiment | `diode_positive` / local VD feeds upper divider | Same declared BAT54H orientation/location |
| `operating-matrix-07/accepted-baseline-11/cold.cir` | Accepted authored simulation baseline, not a board export | `Rfb1 vb vsense 1meg` | `DCLAMP 0 isense BAV23C_ASSUMED_V2`, negative clamp after 220 Ω |
| Revision 08 `candidate/cold.cir` | New unqualified simulation candidate | `Rfb1 vd vsense 1meg` | Retained assumed simulation clamp; physical discrepancy remains open |

The restored baseline is established by [IMPLEMENTATION](../IMPLEMENTATION.md),
[restoration verification](../REDUCTION-VERIFICATION.md), and the
[passive baseline README](../../README.md). These explicitly reject source-build-07
and native-05 as evidence for the restored candidate. Its successful compile
receipt proves what was built then, not that it is the accepted design now.

Therefore moving feedback to VD is a **new candidate change**, consistent with
the planned diode-side-feedback ECO. It is not a correction to match an already
accepted physical protection circuit. The retained board has no installed F2,
larger local film reservoir, or integrated experimental protection block.

## Protection boundaries

F1 is present in the retained source: holder 0031.2510 with link 0034.3129,
in series with AC_L before the CMC. K1 is only the NTC bypass relay. Neither the
accepted SPICE model nor the new candidate contains a dynamic F1 clearing law.

F2 is a proposed offboard fuse, A70QS50-14F with US141/Z331153 holder. The
accepted model represents its healthy conductive path by an ideal switch and
prescribes opening in faults. It is not a controllable precharge actuator.
Default-off, reset and fresh-arm contracts belong to gate enable. Fuse
coordination and real fault interruption remain unqualified.

Independent VD and VB overvoltage detectors exist in the authored simulation
and separate protection experiments. Their presence is not evidence they are
installed on the restored 54-part board. BYPASS-NEG deliberately disabled the
external detector aggregate, so its excursion alone does not justify adding a
duplicate comparator to the experiment.

## Clamp limitation

The two diode mappings differ in part, polarity and connection point. With
negative shunt voltage, A-at-shunt/K-at-ground is reverse biased, whereas the
model's A-at-ground/K-at-ISENSE orientation is the intended negative clamp.
This connectivity observation is not a VF, leakage, breakdown or survival
guarantee. The source's SOD-123F package designation agrees with the
[Nexperia BAT54H product page](https://www.nexperia.com/product/BAT54H), checked
2026-09-21. No part or footprint substitution is made here.

The campaign's assumed BAV23C results cannot validate that physical BAT54H
connection. Correct topology, controller input protection and current-limit
interaction must be bound to one selected physical implementation before any
source-faithful converter claim. TI's
[UCC28180 datasheet, §8.3.14](https://www.ti.com/lit/ds/symlink/ucc28180.pdf)
requires negative ISENSE protection that does not clamp before the worst-case
0.438 V PCL threshold and prevents exceeding 1.1 V negative magnitude across
temperature and component variation. Simply reversing a Schottky diode is
not evidence that those competing requirements are met.

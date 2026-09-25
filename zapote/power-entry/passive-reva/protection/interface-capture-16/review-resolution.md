# Parent review disposition

The raw Luna capture review is retained unmodified and is not design authority.

- **Accepted:** revision15 omitted the LT4363 output-bulk floor and ceramic
  capacitance ratio. C4 is now a220uF target, with effective bulk floor/ratio
  acceptance and a300uF total-output maximum allocation. C3 becomes1.5uF to
  retain the ramp allocation. Exact parts and dynamic evidence remain open.
- **Rejected correction:** the handback called this “input bulk” and specified
  AUX_RAW/Q1 drain. The cited requirement says near Q1 source and refers to
  downstream converter input capacitance. Retain bulk at the protected output,
  not upstream of the pass device; account for the nearby sense resistor.
- **Clarified scope:** SHDN remains service-only. Driver/PFC shutdown is the
  hardware stop path. Coupling permission loss to AUX shutdown would remove
  the HOT decoder/latch supply. The bench addendum now says this explicitly.
- **Clarified rearm:** the missing producer needs a boot-low default and proof
  that the previous permission low reached the HOT latch clear path. The
  handback's “LT4363 reset acknowledgement” is not this condition and was
  rejected. No new acknowledgement hardware is implied.
- **Accepted timing limit:**1us pulse spacing is only a stimulus. The physical
  producer's5V thresholds, setup/hold and clear recovery remain unqualified.
- **Pin tables:** LT4363 MSOP12 -1, SN74HCS74 PW, ISO7741 DW16 and SN74LVC1G08 DBV
  functions were checked against manufacturer tables. Custom symbols retain
  those pin numbers. Q1 uses KiCad's standard G=1/D=2/S=3 symbol; D1 K=1/A=2.
- **Net-auditor handback:** the initial worker claimed diode/fixed-high
  mutation checks but its tests did not exercise those actual faults. Parent
  rejected that version and requested tests on complete known-good graphs,
  structural parsing and singleton NC checks. Only the corrected, rerun
  auditor is acceptance evidence.

Primary references: [LT4363](https://www.analog.com/media/en/technical-documentation/data-sheets/4363fb.pdf),
[SN74HCS74](https://www.ti.com/lit/ds/symlink/sn74hcs74.pdf),
[ISO774x](https://www.ti.com/lit/ds/symlink/iso7740.pdf),
[SN74LVC1G08](https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf),
[FDB33N25](https://www.onsemi.com/download/data-sheet/pdf/fdb33n25-d.pdf).

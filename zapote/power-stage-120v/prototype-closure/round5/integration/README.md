# Round 5 independent integration review

Status: **IN PROGRESS — no completed-revision or first-power approval.**

This packet reviews the joined target firmware, supervisor and sensor PCBs,
protection hardware, and executable circuit model. It owns no product source.
The preserved round4 source and interface identities are in
`intake-manifest.json`; final round5 identities will be recorded separately.
The native19 baseline is SHA-256
`3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b`.

## Intake verified

- Fresh standalone compilation of the preserved supervisor source passes all
  28 source-connected tests. This checks the actual Rust capture, not target
  timing, board routing, or physical component behavior.
- The previous TPS3825 pin error has an exact-family regression and the source
  now puts RESET on pin3/NC and MR on pin4/5V.
- A completed attempt now deliberately clears LATCH_OK through a dedicated
  session-end gate. A new physical RESET, POST and START are required. The
  earlier incidental RC-tail behavior is not used to claim latch retention.
- Current-comparator inputs now have separate 20k resistors and CT clamps.
  The earlier missing protection is corrected structurally; CT, clamp-energy,
  reference backfeed and timing qualification remain distinct work.

The fresh baseline test output is
`output/temper-prototype-closure/round5/integration/baseline-supervisor-tests.txt`.

## Required integration checks

1. Compare final generated MCU, ADC and connector pins against the actual target
   bindings and routed board connectivity, including pin-one orientation and
   supply direction. Any ECO must name the old and new interface.
2. Exercise shutdown, cold RESET, physical START, expired one-shots, completed
   stop, stale/rejected data, power loss and restoration using the implemented
   code and hardware-connected topology. Check defaults physically implemented
   by bias parts as well as software Boolean fixtures.
3. Inspect power-domain crossings, sensor input limits, regulator budget,
   watchdog ownership and ADC/capture bandwidth. Compare actual sample timing
   with the logic and model admission predicates.
4. Check common-period PWM commits and four-channel inhibit against the selected
   peripheral APIs and pin bindings. Independent physical waveform capture is
   additional to target compilation or host peripheral mocks.
5. Join exact protection parts, precharge values, catch routes and field port
   modes with the model. Preserve failed cases, timestep sensitivity, missing
   cross-leg couplings and unqualified device behavior.
6. Review final board rules, routing/return paths, enclosure bounds, harness
   terminations, thermal contact, service and probe access. A nominal geometry
   intersection result does not close insulation or tolerance requirements.

## Review findings and progress

`findings.json` records the live dispositions. Review has identified missing
heartbeat bias, a per-branch POST mismatch, incorrect ADC command CRC placement,
the STM32 heartbeat pin direction, ADC FIFO startup synchronization, downstream
MCPWM inversion during inhibit, and an HS400 mounting-hole pitch error.

The ADC command correction passes the independent `check_adc_command.c` oracle:
three manufacturer-protocol vectors pass, whereas the earlier builder failed
all three. The test calls the actual builder. Its CRC constants were independently
checked with `binascii.crc_hqx`, using seed FFFF; output conversion-frame CRC and
input command CRC have different positions. Final source pinning is pending.

The protection calculation source independently compiles and passes six tests;
all three demand tables reproduce byte-for-byte. Twenty frozen artifact hashes
matched, and the three STEP files reimported with 22, 3 and 664 valid solids.
The anode and cathode each form one connected solid with no overlap; their
2.64 mm separation is confirmed and remains unaccepted against a final
insulation rule. These receipts predate correction of the independently found
HS400 44.7 mm versus specified 45 mm mounting pitch and must be refreshed after
that correction.

The catch sensor's 59 connected pins independently agree between source,
native schematic connectivity and PCB net assignments. Unnamed schematic
internal nets were compared as complete pin-equivalence classes; J1/J2 boundary
names were compared literally. This is connectivity evidence, not an independent
DRC, insulation, or installed-fit result. The isolated board checkpoint does not
complete the central supervisor or the five other sensor boards.

This review must not turn digital incompleteness into a generic hardware-only
hold. Final findings will distinguish implemented and independently checked
work, unresolved digital/supplier decisions, and physical qualification.

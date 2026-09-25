# Standalone RTD unit handoff

This is the standalone RTD unit, generated from `elec/src/rtd_unit.ato:RTDUnit`.
The retained `rtd_pan.*` instance paths identify the same circuit instances in
source, native CAD, models, BOM, and Rust inputs. The separate host connector is
`unit_io`. Full cooker integration and the MCU/buck boards are future goals.

`candidate/section.kicad_pcb` is a 60 × 60 mm, four-layer, 36-component board.
`candidate/section.kicad_sch` and its local libraries are the corresponding
source-derived schematic. The source04 checkpoint has 119 unique pads with exact
source/native pin-net agreement. Native KiCad 10.0.4 ERC and DRC include all
severities and explicit schematic parity; the source04 reports have zero
violations, unconnected items, and parity findings. Reports retain KiCad's
ignored-check inventory. These native results do not replace circuit qualification
or the separate Rust engineering report.

## Electrical boundary

J1 is the four-wire PT100 probe connector, JST B4B-XH-A(LF)(SN): pin 1 FORCE+,
2 SENSE+, 3 SENSE−, 4 FORCE−. The specified probe harness is at most 500 mm,
24–26 AWG, with at most 1 Ω per conductor including contacts for the accuracy
allocation. Wider lead-resistance sweeps are robustness evidence.

J2 is Samtec FTSH-105-01-F-D. Viewed by native pad number:

| Pin | Interface |
|---|---|
| 1 | upstream +3V3 input |
| 2, 3 | common ground, two physical contacts |
| 4 | RTD_SCK input |
| 5 | RTD_SDI input |
| 6 | RTD_SDO output |
| 7 | RTD_CS_N input |
| 8 | RTD_DRDY output |
| 9 | RTD_HW_FAULT, active-high through upstream pullup |
| 10 | SHARED_REF_2V5 output |

The MAX31865 analog supply and window comparators use filtered RTD_AVDD.
The digital supply, REF2025, rail supervisor, final fault NAND, and fault pullup
use upstream +3V3. This keeps a local analog-rail fault observable while upstream
power exists. Loss of upstream power cannot produce a powered-high fault output;
the receiving host must inhibit heating on loss of supply/communication.

The 2.5 V reference is one physical output intended for later OVP/OCP2 consumers.
Those consumers are absent from this unit. Any host load must satisfy the final
circuit reference-load contract; two names never imply two independent references.

The external host must inhibit power until a fresh valid RTD sample, consume
the hardware fault independently, and meet the remaining host shutdown latency.
Firmware protocol and caller tests are retained evidence, not a placed MCU or
completed cooker integration. Actual MCU GPIO assignments belong to that later
unit; the connector pin roles above are this unit's physical contract.

## Layout and replay

Astra authored all component positions, explicit trace polylines, vias, and zones
through the existing native Python adapter. No placement optimizer or autorouter
was used. `routes-*.json` and their evidence receipts preserve the edits and
input/output hashes. F.Cu carries short analog branches, host CS, and the filtered supply
pour; In1.Cu is ground; In2.Cu is a second ground plane with explicitly routed
BIAS/VBIAS segments; B.Cu carries host interfaces and upstream power. The eleven
authored ground stitches connect signal layer-transition returns.

The unit manufacturing contract specifies 35 µm minimum finished copper,
0.20 mm minimum copper spacing and trace width, and 0.70/0.30 mm through vias.
Most local supply branches are 0.30 mm. These are authored unit constraints,
not a fabrication vendor certificate. No high-current cooker path or mains
isolation boundary exists on this standalone board.

## Evidence and lessons

- `bom/pcb-bom.csv` and `bom/source-inventory.json`: exact 36-instance PCB BOM.
- `evidence/root-source04-identity/`: independent complete source/native census.
- `evidence/drc-source04-01.json`, `erc-source04-01.json`: native results.
- `evidence/front-final.pdf`, `returns-final.pdf`: layer review exports.
- `evidence/native-final-02/receipt.json`: three final native DRC/parity runs and
  ERC, with complete candidate input hashes and unchanged-byte assertions.
- `evidence/firmware-protocol/`: frozen composed host source, binaries, and
  15 sensor/readiness plus 60 state-machine passing tests; interface evidence.
- `evidence/root-cache-regression-01/`: frozen causal KiCad cache experiment.
- `evidence/cache-regression-context-fixed/` and `...-legacy/`: maintained replay.
- `../tests/native_filled_zone_regression.py`: portable frozen-fixture regression.
- `evidence/native-open-correction/receipt.json`: a saved intentional RTDIN−
  trace open produced the specific Rust connectivity finding; explicit copper
  restoration and re-extraction removed exactly that finding, with no new ones.
  The same restored copy passed native DRC, connectivity and parity. This scoped
  feedback proof retains the other baseline engineering findings unchanged.

Read the reviewed learning before editing a filled native board:
[`kicad-stale-zone-fill-via-net-corruption-2026-09-10.md`](../../../docs/solutions/architecture-patterns/kicad-stale-zone-fill-via-net-corruption-2026-09-10.md).
Clear stale filled polygons in both scratch replacement and append destination
before mutation. Setting a via's net before saving was insufficient: the explicit
legacy mutation reassigns via nets during native refill; the corrected adapter
preserves all seven ground identities. The number corrupted varies; net identity
is the regression invariant.

Physical accuracy, probe wiring, powered shutdown, EMC, fabrication, and assembly
tests are **NOT RUN**. No parts or fabrication have been ordered. The layout engineering checks have no failing findings. The overall Rust report
remains **INDETERMINATE** for guaranteed local-brownout timing, a named later
characterization/integration obligation described below.
The scoped future procedure is in `BENCH-OUTLINE.md`; it records no performed
physical work.


## Standalone acceptance boundary

`evidence/acceptance-final/receipt.json` binds the exact board, source, executable,
Rust sources, native observations, model, firmware interface files, and reports.
The saved suite has **53 passing tests**. Its real-board report has **zero failing
findings** and one explicit timing indeterminate. Three final native DRC/parity
runs and ERC have zero included findings. This qualifies the standalone layout
under its declared engineering assumptions; it does not certify a powered cooker.

The circuit model covers healthy operation, all four individual conductor opens,
short transitions, local rail-loss static ownership, and upstream-loss host
inhibit. The passive corner model bounds the probe hardware detector at 2 ms;
the external host has a 15 ms allocation. TPS3890's 18 µs falling-delay figure
is **nominal**, with no guaranteed maximum in the cited table. The modeled
<100 ms safety chain also includes brownout: its timing remains conditional.
Characterization must close the allocated brownout and host response budgets,
or trigger redesign, before integration acceptance. Upstream loss has no
powered-high output guarantee.

The current bound load is 8.448898 mA against the unit's 10 mA allocation,
including shorted RTD excitation. External SHARED_REF_2V5 load is limited to
100 µA and 10 nF. The 100 °C error allocation is 1.46 °C against the specified
±2 °C criterion; 250 °C is separately bounded at 1.87 °C. Control/contact and
physical stability/temperature verification remain in the bench procedure.

Return validation uses the actual adjacent plane for each signal layer and
exact interval splitting of native filled polygons. It proves **projected trace
centerline coverage**, with same-terminal antipad allowances based on observed
copper dimensions, native 5 µm polygon error, and nearby connected ground entry.
It is not a field-solver or full trace-width/fringing proof. Orthogonal pad bounds
are used for local proximity. Connected return paths are length-bounded, so a
nearby via reached through a long detour fails. The saved pre-correction board
produces 14 return findings with the final executable; the corrected board has
none. `evidence/acceptance-final/return-correction.json` records that comparison.

Read [LESSONS.md](LESSONS.md) before the next unit and
[BENCH-OUTLINE.md](BENCH-OUTLINE.md) before physical work. Each later section is
a separate goal; full-cooker composition and cross-unit routing follow those goals.


The dated [procurement snapshot](bom/availability-review.md) covers all 20 BOM
groups. TLV3201AIDBVR was listed at zero by both checked distributors, and the
precision RREF needs authorized-channel confirmation. The exact BOM remains
unchanged; parts with missing stock require procurement resolution before a
build. No alternative part is electrically qualified by this snapshot.

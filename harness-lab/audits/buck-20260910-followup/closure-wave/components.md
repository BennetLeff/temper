# Temper buck component-selection closure

Date: 2026-09-10
Repository review base: `a75ca538d87d6578917d0cb3a50da7f14ebdc210`

## Decision

Do not change the authoritative source, circuit contract, BOM, production PCB,
approved registry, or frozen fixtures in this wave. The justified outcome is a
conditional C9 candidate and an open qualification gate:

`C9 -> Samsung CL32B106KBJZW6E` is the preferred orderable replacement for
`GRM32ER71E106KA12L`, pending (1) an exact manufacturer land/termination
review against the existing footprint and (2) effective-capacitance evidence at
the actual input-bias, AC-amplitude, temperature, tolerance, and aging corner.

The current C9 MPN remains source-declared and unverified. The Murata live
filter returned zero exact base-part matches; this does not prove obsolescence,
but it prevents treating the current identity as qualified. The Samsung part is
not a generic 1210 assumption: its exact manufacturer page identifies the
candidate and its electrical construction. It is still not a drop-in approval.

## Retained Samsung evidence

Primary exact page: <https://product.samsungsem.com/mlcc/CL32B106KBJZW6.do>
(rendered 2026-09-10; page created 2026-09-09 00:45:40 KST).

The page reports base `CL32B106KBJZW6`, packaged MPN
`CL32B106KBJZW6E`, Mass Production, X7R `-55 to +125 °C`, 10.0 uF,
`±10%`, 50.0 Vdc, and 1210 (3225): length `3.20±0.30 mm`, width
`2.50±0.20 mm`, thickness `2.50±0.20 mm`. The E package code is embossed,
7-inch reel, normal package; Samsung's Z/R package codes are the horizontal
low-acoustic option, so the selected E suffix does not claim that feature.

The exact rendered DC-bias graph was read at approximately 7–8 uF near
16.5 Vdc, with the page's 1 kHz / 1 Vrms graph condition. This is a visual
typical-data estimate, not a guaranteed minimum. Samsung also exposes separate
AC-amplitude and temperature graphs; the temperature graph observed in the
retrieval uses 25 Vdc bias. These conditions cannot be combined into a
production floor, and no tolerance/aging minimum was inferred.

Samsung's component-library page records the same exact electrical and package
values and says its CAD/footprint data are reference-only:
<https://weblib.samsungsem.com/mlcc/mlcc-ec-data-sheet.do?partNumber=CL32B106KBJZW6>.
The rendered sheet did not expose a numeric manufacturer land pattern. The
candidate therefore has an exact body/termination identity (soft termination)
but no retained exact land dimensions that authorize changing the footprint.

## Mechanical and stress assessment

C9 in `pcb/temper.kicad_pcb` uses `Capacitor_SMD:C_1210_3225Metric`, with two
`1.15 x 2.7 mm` pads centered at `±1.475 mm` (1.8 mm inner gap). The Samsung
body envelope fits the nominal 1210 body, but body-size equality does not prove
that these pad lengths, paste apertures, termination overlap, underside
orientation, or assembly process satisfy Samsung's soft-termination guidance.
Samsung's MLCC catalog explicitly lists this exact base part as
`Soft Termination(3mm)` (Samsung ADS list, PDF p.39):
<https://weblib.samsungsem.com/resources/file/support/software_library/Samsung_ADS_List_v202110.pdf>.
Samsung's current assembly guidance says recommended land dimensions are
determined by evaluating the actual set and board, and directs the designer to
note actual size and termination shape:
<https://m.samsungsem.com/resources/file/global/support/product_catalog/MLCC_Automotive_2512.pdf>
(PDF p.43). Thus soft termination does not by itself require a new footprint
or exotic mounting orientation. The standard IPC 1210 land can proceed through
documented board-level assembly review; vendor CAD is useful corroboration,
not an automatic prerequisite.

Quantitatively, the current pads are 1.15 mm wide by 2.7 mm long, with 2.95 mm
center spacing and 1.8 mm inner gap. The Samsung nominal body is 3.20 mm long
and 2.50 mm wide (max 3.50 x 2.70 mm). Therefore the nominal pad-to-body
comparison is a 0.70 mm pad length shortfall relative to the full body length
when considered end-to-end, while the 1.8 mm gap is 0.7 mm less than the
nominal body width. These numbers describe the existing IPC geometry; they are
not a solder-joint acceptance result. Review should check paste, fillet,
termination overlap, tombstoning, and board-flex risk on the assembled board.
The mechanical disposition is consequently **review required, footprint
redesign not presently indicated**.

The candidate's 50 V rating exceeds twice the proposed 16.5 V VIN maximum,
consistent with the TI LMR51430 voltage-selection guidance. That rating does
not establish effective capacitance. The only retained bias number is typical
and measured at a different AC/bias combination, so the capacitor evidence
gate remains open. This is an electrical design-validation item, rather than a
reason to reject the part or redesign the 1210 footprint now.

## Practical C9 margin method

Use the Samsung curve only as a typical-data screen. At each actual C9 bias
and ripple-amplitude point, record the vendor typical effective capacitance
and separately apply explicit engineering assumptions for initial tolerance,
temperature, aging, and measurement uncertainty. For example, a review may
choose a screening multiplier `M = M_tolerance * M_temperature * M_aging`
and require `C_typical * M >= C_required`; every factor must be named,
source-backed where available, and treated as an assumption when it is not a
manufacturer guarantee. Do not turn the approximately 7–8 uF at 16.5 V,
1 kHz/1 Vrms observation into a guaranteed floor. If a conservative screen
fails, test the assembled candidate or choose a higher-margin part; do not
quietly invent a derating factor.

For C9 specifically, derive `C_required` from the measured VIN ripple and the
LMR51430 input-current waveform, including ESR/ESL and the 20 MHz bandwidth
definition. The output-capacitor ripple bound in the broader proposal is not
automatically C9's requirement. A useful acceptance package is: worst VIN,
load transitions and PFM condition; measured C9 terminal ripple; impedance or
capacitance at the stated DC bias and AC amplitude; and tolerance/aging
assumptions carried into the uncertainty budget. This separates an achievable
design-margin demonstration from an unavailable guaranteed combined-corner
vendor floor.

## L2 closure

Retained exact Bourns source: `../../buck-20260909/sources/bourns-srp1265a.pdf`, SHA-256
`30b470999b737a6350ce5b09a917a5f12090c2e0895a78ddc15285e3d44ec649`.
Primary URL: <https://www.bourns.com/docs/Product-Datasheets/SRP1265A.pdf>.

For `SRP1265A-5R6M`, Bourns specifies at 25 °C: 5.6 uH, ±20%, Q minimum 20,
15 MHz typical SRF, 8.5 mOhm typical DCR, 10.0 mOhm maximum DCR, `Irms=12.5 A`
and `Isat=23 A`. Bourns defines Isat as the current causing a 20% inductance
drop and Irms as the current causing a 40 °C temperature rise; operating range
is -55 to +150 °C. The datasheet includes the exact-part L-versus-I chart.

Those ratings are useful screening evidence, but neither the headline Isat nor
the chart establishes a guaranteed 20%-drop current at the proposed 105 °C
hotspot. The 8.35 A criterion (`1.25 x 6.68 A`) remains a proposed design
criterion derived from the TI maximum high-side peak-current limit, not a
Bourns guarantee. L2's source declaration should retain the rating kind as
Irms in any future schema/source reconciliation; it must not be used as a
converter peak-current limit.

## Proposed edits and exact next action

No source patch is justified yet. When both gates close, the eventual reviewed
patch would update C9's MPN, tolerance, and voltage fields in
`elec/src/modules.ato` and the matching circuit contract/BOM records, with a
component receipt that names the exact curve conditions and accepted land
pattern. Do not silently change C9 to Samsung or change the existing footprint
from this memo.

Next action: perform a documented assembly review of the existing IPC 1210
land using Samsung's actual-size/termination guidance, then qualify the
candidate with the condition-specific C9 margin method above. No footprint
redesign is required solely because the candidate is soft-terminated. In
parallel, obtain a
Bourns exact-part hot L(I,T) curve or measure the assembled L2 at 105 °C and
the declared current waveform. A passing harness run alone cannot close either
component-evidence requirement.

The retained sources, relative to this document, are:

- `../murata-live/cout-bias-25-lowac.json` (SHA-256 `6f47cf05dc55fd7ead0a41ae8970d7dd6abf80320f97010c047faf7f77c2c292`)
- `../murata-live/cout-temperature-3v465-lowac.json` (SHA-256 `4072aee1f55057c4e64c12bdb1ed856fcad18bfdf9ac2686d9fc96d462a537d0`)
- `../../buck-20260909/sources/bourns-srp1265a.pdf` (SHA-256 above)

The Murata JSON files are C11/C12 evidence retained for context; they must not
be applied to C9.

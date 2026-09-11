# Buck component source reconciliation — 2026-09-10

This audit records the source/BOM reconciliation for `BuckConverter3V3`. It
does not constitute a component approval receipt, measured performance, or a
guaranteed effective-capacitance floor. The approved-evidence registry and
production PCB remain unchanged.

## C9 — Samsung replacement selected in authoritative design sources

Updated consistently in:

- `elec/src/modules.ato::BuckConverter3V3.c_in`
- `docs/hardware/BOM.md` §2.1
- `scripts/part_stress_limits.yaml` entry `buck3v3_c_in_dc_bias`
- `harness-lab/engineering/circuit-contract.json` component `c_in`

Selected MPN: `CL32B106KBJZW6E` (Samsung Electro-Mechanics), nominal 10 µF,
±10%, 50 Vdc, X7R, 1210 (3225), mass production, soft termination.

Primary exact sources:

- Product page: <https://product.samsungsem.com/mlcc/CL32B106KBJZW6.do>
- Samsung component-library sheet:
  <https://weblib.samsungsem.com/mlcc/mlcc-ec-data-sheet.do?partNumber=CL32B106KBJZW6>
- Samsung ADS catalog exact row (`CL32B106KBJZW6`, p.39):
  <https://weblib.samsungsem.com/resources/file/support/software_library/Samsung_ADS_List_v202110.pdf>
- Samsung assembly guidance (actual-board land review, p.43):
  <https://m.samsungsem.com/resources/file/global/support/product_catalog/MLCC_Automotive_2512.pdf>

The exact product page gives body dimensions 3.20±0.30 × 2.50±0.20 ×
2.50±0.20 mm and identifies the E suffix as embossed 7-inch normal packaging.
The exact typical DC-bias graph was visually approximately 7–8 µF around
16.5 Vdc at 1 kHz/1 Vrms. This observation is not a guaranteed minimum and
does not combine bias, AC amplitude, temperature, tolerance and aging.

C9 retains the standard KiCad `Capacitor_SMD:C_1210_3225Metric` footprint:
pads 1.15 × 2.7 mm, centers ±1.475 mm, 1.8 mm inner gap. Samsung's guidance
says the recommended land is determined by the actual board and set; therefore
soft termination does not force a footprint redesign. Assembly review must
still check paste, overlap, fillet, tombstoning and board-flex behavior.

Electrical qualification remains a separate gate. Derive the required C9
effective value from measured VIN ripple and the LMR51430 input-current
waveform. Use the Samsung curve for typical-data sensitivity only; apply named
tolerance/temperature/aging/uncertainty factors as engineering assumptions,
never as manufacturer guarantees. The source update is a design selection,
not a claim that the buck has passed ripple, startup or transient tests.

### C9 input-ripple sensitivity calculation

TI's LMR51430 Rev. A input-capacitor guidance recommends X5R/X7R, a voltage
rating twice maximum VIN, and gives a typical 4.7 uF-or-higher high-frequency
decoupler; its 500 kHz example uses two 4.7 uF, 50 V parts with approximately
10 mOhm ESR and 1 A current rating (section 9.2.2.6):
<https://www.ti.com/lit/ds/symlink/lmr51430.pdf>.

No current circuit contract or TI application section declares a numeric
`DeltaVIN` limit for this board. Therefore 50 mV and 100 mV below are labeled
sensitivity points, not adopted requirements; the required value cannot be
declared until the converter VIN budget is written down.

For a transparent first-order screen, let `D=3.3/VIN` and use the ideal
switched-input charge estimate
`C_required = Iout*D*(1-D)/(f_sw*DeltaVIN_C)`. At 500 kHz and 1 A, the
required effective C for 50 mV capacitive ripple is:

| VIN | D | C required (ideal, 50 mV) | C required (ideal, 100 mV) |
|---:|---:|---:|---:|
| 13.5 V | 0.2444 | 7.39 uF | 3.69 uF |
| 15.0 V | 0.2200 | 6.86 uF | 3.43 uF |
| 16.5 V | 0.2000 | 6.40 uF | 3.20 uF |

These are design calculations, not TI limits. A deliberately conservative
screen that assumes 10 mOhm ESR and subtracts a 10 mV ESR step from a 50 mV
total budget raises the 13.5 V/1 A value to approximately 9.24 uF. The
Samsung typical curve is approximately 7 uF at 16.5 V under 1 kHz/1 Vrms;
applying the exact part's 10% initial-tolerance factor as a review assumption
gives approximately 6.3 uF before temperature, aging, AC amplitude and
uncertainty. That fails the 50 mV/10 mOhm screen, while it clears the 100 mV
screen with substantial nominal margin. This does **not** prove either pass or
failure because the actual C9 requirement, ESR/ESL, switching waveform, and
combined operating conditions must be measured or modelled.

At the 0.5 A continuous point, the ideal values above halve (3.69/3.43/3.20
uF for 50 mV at 13.5/15/16.5 V). The 1 A, 10 ms pulse is therefore the
dominant input-capacitor charge screen, although pulse source impedance and
control behavior remain outside this arithmetic. The exact minimum external
action is to set and document a VIN-ripple budget, then measure C9 terminal
ripple and effective impedance at 13.5, 15 and 16.5 V across both load points.

## C11/C12 context

The exact selected MPN `GRM32ER71E226KE15L` is Murata 22 uF, ±10%, X7R, 25 V.
The former ±20% source/contract/BOM text was a stale tolerance field, not a
deliberate qualification margin, and is now corrected to ±10%. The effective
capacitance under DC bias, temperature, aging and AC conditions is still a
separate qualification item; nominal tolerance must not be substituted for
that evidence.

The exact selected MPN `C0603C104K5RACTU` is KEMET 100 nF, ±10%, X7R, 50 V.
The buck source/contract fields for C10 and C13 had stale 25 V and 10 V
minimum declarations and are now corrected to the actual 50 V part rating;
the BOM already identified this MPN as 50 V. This metadata correction does not
claim that the parts retain 100 nF under bias.

The copied Murata JSON files are output-capacitor evidence only and must not be
applied to C9:

- `sources/cout-bias-25-lowac.json`, SHA-256
  `6f47cf05dc55fd7ead0a41ae8970d7dd6abf80320f97010c047faf7f77c2c292`
- `sources/cout-temperature-3v465-lowac.json`, SHA-256
  `4072aee1f55057c4e64c12bdb1ed856fcad18bfdf9ac2686d9fc96d462a537d0`

## L2 — exact source retained; hot criterion remains open

`SRP1265A-5R6M` remains unchanged. The retained exact Bourns datasheet is
`sources/SRP1265A.pdf`, SHA-256
`30b470999b737a6350ce5b09a917a5f12090c2e0895a78ddc15285e3d44ec649`.

Bourns specifies at 25 °C: 5.6 µH ±20%, 10 mΩ maximum DCR, 12.5 A Irms
(40 °C rise), and 23 A Isat (20% inductance drop). Those figures do not prove
the proposed 8.35 A 20%-drop criterion at a 105 °C hotspot. Close that gate
with an exact-part hot L(I,T) curve or a measurement of the assembled part at
the declared hotspot and current waveform.

### Bounded alternate search (screening only)

Three public exact-part records were retained as a bounded comparison. None
is a drop-in approval for the existing Bourns footprint or closes the hot
criterion by itself:

| Candidate | Manufacturer-published data | Disposition |
|---|---|---|
| `XGL1712-562MED` | Coilcraft: 5.6 uH ±20%, 2.8 mOhm max DCR, Isat 12.0/18.2/32.0 A at 10/20/30% drop, Irms 24.6/33.9 A at 20/40 C rise; AEC-Q200, 165 C maximum part temperature | Strongest public temperature qualification, but larger/different land and no exact assembled hot proof; no source change proposed. |
| `744373965056` (WE-LHMI) | Würth: 5.6 uH, 10 mOhm DCR, performance current 13.3 A, Isat 18.3 A at 10% drop and 33 A at 30% drop; active production page | Electrical screen is promising, but the published page does not provide a combined hot L(I,T) guarantee or existing-footprint match. |
| `SRP1038CC-5R6M` | Bourns/DigiKey: 5.6 uH, 19.3 mOhm max, 12 A shielded wirewound, active listing | Lower current and different package; no reason to prefer it over the exact installed Bourns part. |

Source records (retrieved 2026-09-10):

- Coilcraft exact table: <https://www.coilcraft.com/en-us/products/power/high-voltage-inductors/xgl/xgl1712/xgl1712-562/> (lines 315–316, 375–380)
- Würth exact series row: <https://www.we-online.com/en/components/products/WE-LHMI?sq=74437346033> (row `744373965056`)
- DigiKey exact listing: <https://www.digikey.com/en/products/detail/bourns-inc/SRP1038CC-5R6M/21263826>

The alternate search does not justify a footprint or MPN change. The minimal
outside action remains one exact-part hot L(I,T) curve at the declared
hotspot, or an assembled measurement, plus a documented load-waveform
criterion. Do not treat the published 25 °C Isat/Irms numbers as guaranteed
combined-corner floors.

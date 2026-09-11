# Exact passive component follow-up

**Later live retrieval:** [Murata follow-up](murata-live/README.md) now retains
C11/C12 exact-part bias and temperature curves. C9's exact MPN returned no
live catalog match and remains unverified; earlier wording below that broadly
supports the Murata nominal identities must not be applied to C9. The original
retrieval narrative is retained as history, not the current availability status.

Scope was limited to `C9 GRM32ER71E106KA12L`, `C11/C12 GRM32ER71E226KE15L`,
`C10/C13 C0603C104K5RACTU`, and `L2 SRP1265A-5R6M`. Repository source was
checked from the requested base (`a75ca538d87d6578917d0cb3a50da7f14ebdc210`);
the agent made no repository changes. The host subsequently retained this
reviewed report and its new source PDF in this audit directory. The exact contract remains
`harness-lab/engineering/circuit-contract.json:5-13` and the values are in
`elec/src/modules.ato:1444-1498`.

## Primary-source results

### C10/C13: KEMET/Yageo exact part

The exact manufacturer spec sheet is available at
<https://search.kemet.com/download/specsheet/C0603C104K5RACTU>. It identifies
`C0603C104K5RACTU` (alias `C0603C104K5RAC7867`) as SMD Comm X7R, 0.1 uF,
10%, 50 VDC, 0603/1608, -55 to +125 °C. The rendered source states 1 kHz,
1 Vrms capacitance measurement, 10% tolerance, 50 VDC rating, X7R and 3%
aging loss per decade hour (generated 2026-09-09). It was downloaded to
[`sources/C0603C104K5RACTU.pdf`](sources/C0603C104K5RACTU.pdf); SHA-256 is
`a74d666c69e2798691fea970c43141fb2d25fabff3710494d68dcd35fcef4040`.

This confirms C13's `100 nF +/-10%` declaration. C10's source declaration
(`modules.ato:1453-1458`) omits tolerance; the exact part is nevertheless a
10% part, so the C10 BOM/source is under-specified. Its buck operating
declaration is 25 V, while the part rating is 50 V. KEMET's same page warns
that its K-SIM responses are typical simulations, not specifications; no
part-specific guaranteed DC-bias minimum was obtained. The 10% initial
tolerance and 3%/decade aging figure do not justify promoting 100 nF to an
effective capacitance floor under bias and temperature.

### L2: Bourns exact part

The exact manufacturer datasheet is retained in the repository and copied for
this audit to
`/tmp/temper-buck-followup-20260910/component-sources/SRP1265A.pdf`.
The durable identical source is
[`../buck-20260909/sources/bourns-srp1265a.pdf`](../buck-20260909/sources/bourns-srp1265a.pdf).
SHA-256: `30b470999b737a6350ce5b09a917a5f12090c2e0895a78ddc15285e3d44ec649`.
Primary URL: <https://www.bourns.com/docs/Product-Datasheets/SRP1265A.pdf>.

On the exact `SRP1265A-5R6M` row (PDF page 1), Bourns specifies 5.6 uH at
100 kHz/1 V, +/-20%, Q min 20, typical SRF 15 MHz, typical DCR 8.5 mOhm,
maximum DCR 10.0 mOhm, Irms 12.5 A and Isat 23 A. General notes define Isat
as the current producing a 20% inductance drop and Irms as the current causing
40 °C temperature rise; the operating range is -55 to +150 °C. Bourns also
warns that circuit design, PCB trace size/thickness, airflow and cooling set
actual part temperature and must be verified in the end application. The
datasheet includes an L-vs-I chart for the exact 5R6M and is more useful than
the headline current values, but it is not a guaranteed 105 °C curve.

The source's `l_out.current_rating = 12.5A` (`modules.ato:1462-1467`) is
therefore an Irms rating, not a saturation or converter peak-current limit.
The contract's 12.5 A label is potentially misleading unless the rating kind
is made explicit. No independent hot-spot 105 °C L(I,T) evidence is retained.

### C9 and C11/C12: Murata exact parts

Murata's exact product-search PDF endpoint is the appropriate primary route:

- C9: <https://www.murata.com/en-global/api/pdfdownloadapi?cate=luCeramicCapacitorsSMD&partno=GRM32ER71E106KA12%23>
- C11/C12: <https://www.murata.com/en-global/api/pdfdownloadapi?cate=luCeramicCapacitorsSMD&partno=GRM32ER71E226KE15%23>

The C11/C12 endpoint was indexed by Murata as `GRM32ER71E226KE15#`, with L
and K package variants and a 22 uF, 25 V, X7R, 1210 construction; the indexed
page says its data are typical and directs users to the approval sheet for
full specifications. TI's exact LMR51430XDDCR EVM guide independently lists
`GRM32ER71E226KE15L` as 22 uF, 25 V, +/-10% in its Table 5-1 BOM
(<https://www.ti.com/lit/ug/sluuch0/sluuch0.pdf>, PDF page 7); that guide is
primary evidence for the exact part/tolerance match but supplies no transient
waveforms or DC-bias curves. The exact C9 and C11/C12 URLs returned Murata
product-page HTML rather than downloadable PDFs in this retrieval. The
retained `.html` files are page responses (SHA-256
`22d75a9670fab189dea8cdd7672e91f58a9eed18d5476d4ce51728e80781c80`), not
evidence documents. No Murata DC-bias/temperature curves or approval sheets
for either exact part were retained. The +/-10% C11/C12 evidence conflicts with
the Temper source's +/-20%; the source should remain unchanged until its
approval-sheet policy is resolved, but the discrepancy is now documented with
an exact TI reference. Do not use the similar `GRM32DR...` family as evidence
for C9 `GRM32ER...`.

Thus the nominal identities, 25 V rating and X7R dielectric are supported;
guaranteed effective capacitance under bias/temperature/aging is unavailable.
The current manifest's `capacitor_effective_value` and contract's required
`capacitor_effective_capacitance_dc_bias` remain correctly unresolved.

## Bounded calculations for the proposed envelope

For ideal CCM, use `D = VOUT/VIN`,
`dI = (VIN-VOUT)D/(L f) = VOUT(1-D)/(L f)`.
At maximum proposed VIN=16.5 V, nominal VOUT=3.3 V, Lmin=4.48 uH
(5.6 uH -20%), and fmin=450 kHz, `D=0.2` and `dI=1.3095 A`.
The 1.0 A, 10 ms pulse gives an ideal CCM peak screening estimate of
`1.0 + dI/2 = 1.6548 A`, so the proposed 1.65 A number is reasonable for
that pulse, with no allowance for control overshoot, tolerance beyond the
stated L corner, or transient response. At 0.5 A continuous load, the ideal
CCM valley would be `0.5 - dI/2 = -0.1548 A`; CCM is therefore inadmissible
as an operating-bound assumption at that point and the converter will enter
DCM/PFM. The 0.5 A CCM arithmetic must not be used as a guaranteed peak bound.
At nominal 5.6 uH/500 kHz, the same calculation gives `dI=0.9429 A` and a
1 A-load CCM screening peak of 1.4715 A.

The proposed VOUT upper envelope 3.465 V is another relevant ripple corner,
and it can bound a static output corner as well as limit overshoot. It is not a
control-loop guarantee. At VIN=16.5 V, VOUT=3.465 V, L=4.48 uH and f=450 kHz, `D=0.21`
and `dI=1.3578 A`; a 1 A-load CCM screening peak would be 1.6789 A. Since
the formula assumes steady CCM, this corner does not bound the transient
itself; independent waveform evidence is required.

For a first-order triangular-ripple capacitor bound, ignoring ESR,
`C >= dI/(8 f dV)`. At 1.3095 A, 450 kHz and 50 mVpp this gives 7.275 uF
of effective total output capacitance. If 5 mOhm aggregate ESR is assumed,
the ESR step is 6.55 mV and the remaining 43.45 mV implies 8.37 uF. These
are screening bounds only: the 0.1 A/us load step, control-loop response,
ESL, layout and PFM pulse skipping can dominate, so acceptance must measure
the actual waveform with the proposed 20 MHz bandwidth and 3.135–3.465 V
window. Nominal `2 x 22 uF + 100 nF` cannot be promoted to that floor without
exact DC-bias/temperature/aging evidence or a conservative measured floor.

For the proposed fault criterion, TI's LMR51430 datasheet gives a typical
high-side peak limit 4.76 A and maximum 6.68 A
(<https://www.ti.com/lit/ds/symlink/lmr51430.pdf>, PDF page 5). A defensible
engineering acceptance choice is to require the exact inductor's measured or
manufacturer-supplied 20%-drop current at the 105 °C hotspot to exceed
`1.25 x 6.68 = 8.35 A`; 25% is an explicitly proposed margin, not a Bourns or
TI requirement. The 23 A Bourns Isat headline at its specified test condition
is not proof of 8.35 A at 105 °C. The required evidence is an exact-part
L(I,T) curve or thermal/current test at 105 °C, plus the board's loss and
temperature measurement method. At 1.65 A normal peak, the headline Isat is
not the limiting condition; the fault/saturation requirement is.

## Closure status and retrieval path

Closed by exact primary sources: C10/C13 nominal value, 10% tolerance, 50 V
rating, X7R, temperature range and aging statement; L2 exact nominal,
tolerance, DCR, Irms, Isat definitions and operating range. The exact Bourns
PDF is hash-retained above. Exact Murata nominal family identity and C11/C12
25 V/X7R/1210 are indexed by Murata, but the approval sheets and curves are
not retained.

Still unavailable: exact Murata C9/C11/C12 tolerance approval sheets and
DC-bias/temperature/aging curves; guaranteed effective capacitance for all
five capacitor placements; and L2's exact hot-spot L(I,T) or saturation margin
at 105 °C. The C9/C11/C12 +/-20% source claims should remain unchanged until
the exact Murata approval sheets resolve the apparent +/-10% ordering-code
conflict. C10's missing tolerance should be corrected in any future source
reconciliation, because the exact KEMET/Yageo sheet says 10%.

Concrete retrieval: obtain Murata approval sheets (not merely generic GRM
series pages) from the exact product pages above or Murata support, request
DC-bias curves at the actual DC voltages and temperature corners, and retain
the PDF bytes, revision/date and SHA-256. Request Bourns exact 5R6M hot-current
data if the datasheet chart cannot establish a 105 °C curve; otherwise measure
the assembled footprint at the declared hotspot under the deferred physical
validation plan. Populate only a reviewed, non-synthetic component receipt
after these artifacts are independently reviewed; the current approved
registry remains empty.

## Sources

- KEMET/Yageo exact C0603C104K5RACTU specification: https://search.kemet.com/download/specsheet/C0603C104K5RACTU
- Bourns SRP1265A datasheet: https://www.bourns.com/docs/Product-Datasheets/SRP1265A.pdf
- Murata exact C9 product-search endpoint: https://www.murata.com/en-global/api/pdfdownloadapi?cate=luCeramicCapacitorsSMD&partno=GRM32ER71E106KA12%23
- Murata exact C11/C12 product-search endpoint: https://www.murata.com/en-global/api/pdfdownloadapi?cate=luCeramicCapacitorsSMD&partno=GRM32ER71E226KE15%23
- TI LMR51430 Rev. A datasheet: https://www.ti.com/lit/ds/symlink/lmr51430.pdf
- TI LMR51430EVM user guide (exact C11/C12 BOM listing): https://www.ti.com/lit/ug/sluuch0/sluuch0.pdf

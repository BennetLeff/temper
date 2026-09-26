# DC-link clamp and surge coordination

Status: owner supplied the axial-package selection on 2026-09-25;
MRT130KP295CV is D3 in the source. The approved capacitor revision is regenerated and verified in native-02;
see [NATIVE-02.md](NATIVE-02.md).
The requested design target is stand-off above the maximum
restart-inhibit threshold, ≤520 V at returned tank current, and at least
2 J absorption. The 2 J figure is a requested minimum, not a proved upper
bound on reachable tank energy.

| Candidate | Manufacturer pulse rating at 25 °C | Disposition |
| --- | --- | --- |
| Microchip MRT130KP295CV | 295 V stand-off; 410 V max at 282 A, 6.4/69 µs | Best provisional candidate; axial body about 13 × 8 mm. |
| Littelfuse AK10-380C-Y | 380 V stand-off; 520 V max at 10 kA, 8/20 µs | No stated clamp margin for added loop inductance. |
| Littelfuse 30KPA300A | 300 V stand-off; 484 V max at 62 A, 10/1000 µs | Does not substantiate ≤520 V at approximately 100 A. |

Sources: [Microchip DS00005551B](https://ww1.microchip.com/downloads/aemDocuments/documents/HRDS/ProductDocuments/DataSheets/130-kW-Transient-Voltage-Suppressor-TVS-Device-00005551.pdf),
[Littelfuse AK10](https://www.littelfuse.com/assetdocs/tvs-diode-ak10-y-series-datasheet?assetguid=db4a5d09-f3a3-4e23-9dca-f7688553f66d),
[Littelfuse 30KPA](https://www.littelfuse.com/assetdocs/littelfuse_tvs_diode_30kpa_datasheet.pdf?assetguid=79942834-59ae-4f4e-978d-abfaf38dffcf).

For the Microchip candidate, the 410 V rating excludes lead/PCB inductance.
The longer 10/1000 µs rating allows about 87 A, and rectangular pulses need
the manufacturer's waveform derating. At 100 A and 410 V, 2 J corresponds
to about 49 µs of rectangular conduction; this arithmetic does not qualify
that pulse at the intended board temperature. Repeated pulses accumulate
heat: [MicroNote 133](https://ww1.microchip.com/downloads/aemDocuments/documents/HRDS/ApplicationNotes/ApplicationNotes/MicroNote133.pdf).

The static upper OVP corner is approximately 286 V using REF25=2.520 V,
0.1% threshold resistors, the 1% high-side bus divider, 0.1% bottom resistor
and +5 mV comparator threshold error. It leaves only about 9 V below 295 V
stand-off before omitted leakage, temperature and dynamic effects. Do not
select the 275 V variant against a nominal 280 V restart threshold.

Selection must be followed by a bounded current-versus-time pulse, hot
ambient and repetition/duty specification, and a clamp-loop inductance
budget. Placement should put the clamp across BUS_P/HV_RET at the bus
capacitors, with a short broad return. Measure the capacitor and MOSFET
terminal voltages, not only the TVS body. A data-sheet terminal clamp does
not itself prove the board stays below 520 V. No physical test has run.

## Mains surge coordination

The TVS also receives surge energy through the rectifier and input filter.
Do not size it only for tank shutdown. The upstream TMOV20RP175E and the
downstream TVS have different voltage/current curves; their quoted clamp
voltages are measured under different pulse conditions and do not define
how current divides. In particular, the TVS data sheet specifies a **300 V
minimum breakdown at 5 mA**, not a guaranteed approximately 330 V turn-on.
Its lower onset can make it conduct before the upstream MOV substantially
limits the surge. Choke leakage inductance, saturation, winding resistance,
rectifier paths and board parasitics affect that interaction.

The certification lab must establish applicable IEC 61000-4-5 or other
product-standard surge levels, source impedances, coupling modes, polarities,
phase angles and repetition sequence. No test level has been selected here.
For that agreed matrix, capture voltage and current at both suppressors and
the DC link; integrate each device's v(t)i(t), check hot-temperature pulse
and repetition limits, rectifier/fuse stress, and post-test leakage/function.
Include line-to-line and applicable line-to-earth cases, and assess PE-open
behavior as required by the governing product standard. A TVS survival claim
does not establish the MOV, fuse, bridge or insulation passes.

Place the TVS at C5/C6 on a short, wide BUS_P/HV_RET loop; keep formed leads
short while respecting the package bend requirements. Measure peak voltage
at the bus capacitors and MOSFET terminals. The 520 V target includes layout
inductance and remains a measurement criterion, not a demonstrated bound.
The approved C5/C6 pair is 5.4 µF bulk (two 2.7 µF, 1000 V), and the four
approved 100 nF leg capacitors raise the nominal DC link to **5.8 µF**.
All four local capacitors return to HV_RET to preserve R5 shoot-through
sensing. Use the installed bank, tolerances and initial voltages in the
shutdown/surge assessment; the historical 4.5 µF/600 V oracle estimates
are not bounds or qualifications of this revised bus.

## Procurement

The 2026-09-25 pcbparts/DigiKey lookup lists the exact base MPN as active,
but zero stock, a 100-piece minimum and USD 46.2154 per piece at that break.
It lists the base MPN as non-RoHS; Microchip offers E3 ordering variants.
These are time-sensitive catalog observations, not a quote or an order.
Keep the approved base MPN explicit; do not silently substitute a different
suffix or clamp family. Confirm sample availability, finish and cost before
ordering the prototype. The distributor's 282 A field labels the pulse as
10/1000 µs, contradicting Microchip's 6.4/69 µs condition; use the manufacturer
data sheet for the rating.
[Distributor listing](https://www.digikey.com/en/products/detail/microchip-technology/MRT130KP295CV/7611955).

# DC-link clamp candidate assessment

Status: candidate researched; package preference pending; no TVS is yet in
the source. The requested design target is stand-off above the maximum
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

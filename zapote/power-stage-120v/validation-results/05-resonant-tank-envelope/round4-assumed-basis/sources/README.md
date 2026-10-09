# Sources for the round-4 assumed basis

Only `../../sources/942C.pdf` is in the repo, and it was already committed for task 05.
The other PDFs were fetched on 2026-10-09 and are not committed. To reproduce
`outputs/digitized-*.csv`, fetch them again and check the hashes below.

| Ref | Document | Where it is used | URL | SHA-256 |
| --- | --- | --- | --- | --- |
| [ON] | onsemi, *AND9201/D: The Effect of Pan Material in an Induction Cooker*, Rev. 0, January 2015. p. 4 Table 1 lists the pans: Duxtop 304 (18/10) sauté pan; 5-ply skillet with an AISI 430 exterior, Al core and 304 interior; Midea 430 SS; cast iron; aluminium. p. 7 Fig. 9 gives series L and Fig. 10 series R, 1 kHz–1 MHz, HP bridge, small signal. p. 2 text: "At 30 kHz, the resistance is 3.2 Ω for the cast iron pan to 0.3 Ω for the aluminum pan." p. 9: "The type of magnetic material does not have an appreciable impact on the losses." | Pan anchors: kl, r and α for cast iron, 430 and 5-ply; the aluminium fault load; no-pan coil q and γ | https://people.ee.ethz.ch/~mzahner/PPS-Magnetfelder/material/Literatur%20diverses/AN9201_Induction_cooker_pan_material.PDF (an ETH course mirror of the onsemi note) | `eca2fff5ed04c94cb68f5773f32c72729ff398732005168263e90fad4bce5417` |
| [IFX] | Infineon, *UG-2023-15: EVAL-IHW25N140R5L 2 kW induction heating evaluation board with reverse conducting R5L IGBT*, user guide Rev. 1.0, 2023-08-04, p. 21 Fig. 16, "Resonant load parameters across the frequency range": L and R with and without a vessel, 0–50 kHz | Kit coil and vessel anchor: kl, r, q, α, β, γ. This is the same chart TANK_COIL_SPECIFICATION.md §5 reads | https://www.infineon.com/dgdl/Infineon-EVAL-IHW25N140R5L-UserManual-v01_00-EN.pdf?fileId=8ac78c8c8afe5bd0018b18c78e023a8d | `db2816dd3bf8de650bca0331b98cad343c0dc334fd736775006436f57d285940` |
| [CDE] | Cornell Dubilier, *Type 942C catalogue* (no printed revision; PDF dated 2021-11-16). p. 1 specifications; p. 3 1200 Vdc and 1600 Vdc tables; p. 4 "RMS Voltage vs Frequency @ 25 °C" | Capacitor bound (`scripts/cap_rating.py`) | https://www.cde.com/resources/catalogs/942C.pdf | `f99395446ba25a0adcef85862ff9eaee90bac68fae6664decccab1ebea3e4310` |
| [PAS] | A. Pascual, J. Acero, C. Carretero, S. Llorente, J. M. Burdío, "Electromagnetic Modeling and Analysis of Multimaterial Cookware for Domestic Induction Heating", *IEEE Access* 11, pp. 79275–79284, 2023, doi 10.1109/ACCESS.2023.3298571. pp. 79275–79276: the inductor–load system is modelled as a series R_eq–L_eq, and domestic IH runs at 20–100 kHz. p. 79279: 145 mm / 24-turn inductor of 32-strand 0.3 mm Litz; stainless modelled as σ = 1.1·10⁶ S/m, µr = 100. p. 79281: 180 mm / 19-turn inductor; small-signal measurements over 20–100 kHz. Values appear only in figures, so no number is digitized from it. | Model form (series R_eq/L_eq), frequency band, and coil geometry plausibility | https://zaguan.unizar.es/record/128032/files/texto_completo.pdf | `25fae25d716c0c54be97e5a6d9685a7900eae6fc1501aa8559e4e30323b84419` |
| [MDPI] | 180 mm, 110 µH no-load coil study, *Electronics* 12(19):4145 (MDPI, 2023), Table 3. The repo transcribes it in `zapote/inverter/evidence/provisional-coil-pan-model.md`: cast iron (89.76 µH, 4.21 Ω), stainless (81.81 µH, 3.36 Ω), Silit Silargan (69.07 µH, 2.48 Ω) | Cross-check anchors only | https://www.mdpi.com/2079-9292/12/19/4145 | Not re-fetched: mdpi.com returned HTTP 403 on 2026-10-09. The title, authors and test frequency are not verified here |

Repository sources used as given: `docs/hardware/TANK_COIL_SPECIFICATION.md` (row 1: ±10 %;
row 5: ≤0.40 Ω at 40 kHz); `docs/hardware/power-section-120v/coil_mc.rs` (PANS and COIL_Q);
`zapote/power-stage-120v/DECISIONS.md` (2026-10-08: tank ≤22 A RMS, 11.1 A hold, Kelvin band
47.52–97.98 A, 120–127 V nameplate with design coverage to 140 V);
`firmware/components/power/fullbridge_adapter.c` (35–60 kHz);
`firmware/components/power/input_limits.c` (η_min 0.93, tank_limit_a 22);
`../round3/sources/a3-thresholds.json` (CT static band 50.558–60.014 A);
`../sources/cst3015.pdf` (CT 1:100, 638 V·µs, 88 A thermal reference).

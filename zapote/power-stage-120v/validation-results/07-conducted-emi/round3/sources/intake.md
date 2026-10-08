# Coordinator model search, 2026-09-27

## KEMET Y-SIM / K-SIM browser retrieval

Opening <https://ksim3.kemet.com/?pn=R463N410000N1M> returned **No match found**.
The visible catalog (version 3.0.7.15) was then selected: Film → R46 → 22.5 mm
→ 560 V → 1 µF `R46KN4100JHP1M`. This is a DIFFERENT part number and voltage
code; use as a related-series model scenario, not exact-part qualification.

At 25°C and zero DC bias, the export saved
`Imp-ESR_R46KN4100JHP1M.csv` (100 Hz–10 MHz, 1 part, combined disabled).
The second export `R46KN4100JHP1M_SPICE_Model.CKT` uses a **10 kHz center
frequency**; it is not a broadband ESR model. Exported L1+L2 is about 12.85 nH.
Fit the broadband CSV rather than promoting the 10 kHz resistance to all
frequencies. No exact-part equivalence has been asserted.

## TDK choke model

TDK's official library lists **B82726S2203A020**:
<https://www.tdk-electronics.tdk.com/en/180512/design-support/design-tools/inductors/model-libraries-for-smt-and-leaded-inductors/inductors-readme-and-history/2988012>.
Version 1.35, assembled 2024-12-11. The readme calls models typical and limits
expected accuracy to below the first resonant frequency. Model existence does
not certify attenuation at 30 MHz.

Library index:
<https://www.tdk-electronics.tdk.com/en/523002/design-support/design-tools/inductors/model-libraries-for-smt-and-leaded-inductors/ltspice>.
The Unix and Windows download links are:

- <https://www.tdk-electronics.tdk.com/download/2988014/af8b9b278e314891424930e4e9597a78/b8272x-lt-ux-en-tar.tar>
- <https://www.tdk-electronics.tdk.com/download/2988030/80645eab006af2c586e8875c0ef7dd27/b8272x-lt-wi-en-zip.zip>

CLI returned HTTP 403. A normal browser reaches the Important notes and License
Agreement page, with an accept button. **Coordinator has requested user
confirmation; do not accept or bypass the license gate until that answer
arrives.** Copy/modify/redistribution restrictions mean vendor files must not
be included in a public commit without permission. Meanwhile digitizing the
published datasheet curve is an available independent procedure.

BR1 official product page also lists a SPICE model:
<https://www.diodes.com/part/view/GBJ2510>. Its May-2025 DS21221 Rev.11-2 p.2
gives a typical 85 pF junction capacitance at 1 MHz and 4 V reverse bias;
that point alone is not Cj at 170 V. Exact PDF is already downloaded into A6's
`round3/sources/gbj2510.pdf` (read-only peer copy allowed).

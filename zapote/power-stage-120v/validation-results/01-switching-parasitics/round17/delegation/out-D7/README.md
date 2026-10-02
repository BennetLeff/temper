**C38–C41 / B32652A0104K000: no verified ESL range yet; retain 5/10/20 nH only as an assumed sensitivity sweep—TDK lists an exact model, but downloading it requires license acceptance.**

**C5/C6 / B32656G0275J000: no verified ESL range yet; TDK also lists an exact model, and the local-capacitor sweep must not be promoted to a bulk-capacitor specification.**

## Method and result

D-7 audited the frozen BOM, netlist and native-17 board identities at
`f9b13b483d6d4ed52439d4da419c7670bab6966c`, then followed the TDK product
page to its series datasheet, general technical information and film-model
library. [evidence.json](evidence.json) records input hashes and the six
reference/part matches. No identity contradiction was found. Design files,
existing decks and round-17 results were not changed.

The investigation found **part-specific models**, not merely a family
estimate. TDK's public PSpice library README lists `B32652A0104K` and
`B32656G0275J` in `TDK_B32651-8.lib`, version **1.10**, assembled
**2025-03-21**. The ordering suffix `000` is absent from these model names;
matching the electrical part stem is established, but the modeled lead
geometry cannot be established without the archive. TDK describes the models
as typical and limits expected accuracy to below the first resonance. An
extracted model inductance would therefore be a typical model parameter,
not a production or mounted-assembly bound. [S2]

No model inductance was extracted. Direct `curl` returned HTTP 403. An
independent retry with a browser user-agent and TDK referrer returned HTTP
200 **HTML**, not a tar archive; its title and canonical link identify
TDK's license-acceptance page. `tar tf` rejected it. The browser download
also returned no usable file. The form explicitly requires accepting a
license agreement; that action was not performed. These outcomes are
recorded in [source-status.json](source-status.json). Do not treat an HTTP
success or the `.tar` filename as proof of model acquisition.

## Source numbers and what they establish

| Item | Verified source fact | ESL implication |
| --- | --- | --- |
| B32652A0104K000 | 100 nF ±10%, nominal 15 mm pitch; product page gives 18 × 9 × 17.5 mm maximum body and untaped leads of 6−1 mm | Package identity, not ESL. [S1, S3] |
| B32656G0275J000 | Model list: 2.7 µF ±5%; series drawing B1: B32656G is four-pin, 37.5 mm primary pitch | A two-terminal model still needs its four-lead connection/reference-plane definition. [S1, S2] |
| Family impedance graph | B3265*A/G/J/T, June 2026, printed p. 37, unnumbered “Impedance Z versus frequency f (typical values)” | Graph located, but no trustworthy part-specific SRF was read; no inferred ESL reported. [S1] |
| General self-inductance rule | October 2025, printed p. 20, §2.5, relates maximum inductance to capacitor length **and lead length**, at 1 nH/mm | It does not establish the existing “≤ ~20 nH” mounted bound without the lead geometry and reference plane. [S4] |

The prior `PACKAGE-INDUCTANCE.md` bound needs qualification: body length
alone omits the lead-length term in its own cited rule. The datasheet's
supplied lead length does not say how far the installed body sits above
the board or where the electrical reference plane lies. This is a
limitation in the interpretation of an evidence document, not a
board/netlist/datasheet contradiction.

The script provides `L = 1 / ((2π f_SR)² C)` arithmetic without inventing
an SRF. Its default output gives the **implied**, unmeasured resonance
frequencies of the inherited 5/10/20 nH choices, for comparison with a
future impedance measurement:

| Assumed ESL | 100 nF implied SRF | 2.7 µF implied SRF |
| --- | --- | --- |
| 5 nH | 7.118 MHz | 1.370 MHz |
| 10 nH | 5.033 MHz | 0.969 MHz |
| 20 nH | 3.559 MHz | 0.685 MHz |

Numbers above come from [esl_arithmetic.py](esl_arithmetic.py) and
[evidence.json](evidence.json), using nominal capacitance. They are
arithmetic transformations of assumptions, **not curve readings or vendor
ESL evidence**. No reading uncertainty is assigned because no reading was
made. A future SRF interval must be propagated inversely with its square,
with capacitance uncertainty included separately.

## Mounting, FEM and sweep recommendation

The brief establishes that FEM reaches the PCB pads and excludes the
capacitor body and leads above the board. Added ESL must represent only
that omitted part path, referenced to those pads. Do not add PCB loop
inductance again. Conversely, do not subtract a guessed lead inductance
from an uninspected vendor model. Establish the modeled cut length,
terminal pairing and measurement plane first; include any remaining
assembly lead length exactly once.

The current five-port deck has a further limitation visible in
`d2/leg_matrix5.cir`: `Lesl6`, `Lesl38` and `Lesl39` share `LESL`.
`Cbulk5` has no separate component ESL, while its path uses heuristic
`LBULK`. Thus independently sourced bulk and local values would require
separate parameters and an explicit C5 component/path split in later
work. This report does not edit that deck.

For now, retain the local **5/10/20 nH exploratory sweep** for continuity;
there is no source-supported reason here to narrow it, and it is not a
proven enclosure of production parts. For bulk, **no vendor-supported
range is recommended yet**. If exploratory bulk sensitivity uses those
same values, label them assumptions and vary bulk independently from the
local capacitors. Do not close FINDINGS M4 on this report.

## Sources

- **S1:** TDK, *Film Capacitors—Capacitors for Snubbering, Resonant Circuits,
  Power Factor Correction (PFC)*, **B3265*A/G/J/T, June 2026**;
  printed pp. 3–4 (drawings A1/B1), p. 37 (typical impedance graph).
  [Official series PDF](https://product.tdk.com/system/files/dam/doc/product/capacitor/film/mkp_mfp/data_sheet/20/20/db/fc_2009/mkp_b32651_658.pdf).
- **S2:** TDK, *B3265* High pulse handling, PSpice—Readme and History*,
  **v1.10, 2025-03-21**, sections History, Readme and library listing;
  [public README](https://www.tdk-electronics.tdk.com/en/2970296/design-support/design-tools/film-capacitors/model-libraries/film-capacitors-readme-and-history/2976028),
  [download table](https://www.tdk-electronics.tdk.com/en/2970300/design-support/design-tools/film-capacitors/model-libraries/pspice),
  [exact Unix archive link](https://www.tdk-electronics.tdk.com/download/2976030/8705da5784307ba596394f297843723b/tdk-b32651-8-ps-ux-en-tar.tar).
- **S3:** TDK Product Center, [B32652A0104K000](https://product.tdk.com/en/search/capacitor/film/snubbering_pfc/info?part_no=B32652A0104K000),
  Size / Electrical Characteristics / Other tables; live page, accessed 2026-10-02.
- **S4:** TDK, *Film Capacitors—General technical information*,
  **October 2025**, printed pp. 20–21, §§2.5–2.6:
  [official PDF](https://en.tdk.eu/download/530754/bb7f3c742f09af6f8ef473fd34f6000e/pdf-generaltechnicalinformation.pdf).
- **S5:** TDK, [Important notes and License Agreement](https://www.tdk-electronics.tdk.com/en/2905240/design-support/design-tools/important-notes-and-license-agreement),
  live page, accessed 2026-10-02; model access requires license acceptance.

## Reproduce and limits

From the repository root, using Python 3.12 and only its standard library:

```sh
python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D7/esl_arithmetic.py
```

To calculate from a future actual reading, pass both `--capacitance-nf`
and `--srf-mhz`; record the reading, source, lead geometry and uncertainty
alongside the result. The script does not turn entered values into evidence.

**Owner action:** accept the TDK license if appropriate and obtain the
archive, then provide its local path for an exact-model extraction and
lead-plane audit. Save the archive SHA-256 and model revision at that
point. No vendor model has been obtained or redistributed here; there is
therefore no model hash to report. If model lead geometry remains
unspecified, request it from TDK or measure a sample at the intended
mounting geometry. D-7 numeric closure remains incomplete until then.

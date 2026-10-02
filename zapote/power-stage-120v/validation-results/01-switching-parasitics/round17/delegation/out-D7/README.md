**C38–C41 / B32652A0104K000: TDK's typical full-model resonance implies 1.060 nH; use an exploratory 1.060–20 nH sweep including the vendor-model anchors and legacy stress points, not a production bound.**

**C5/C6 / B32656G0275J000: TDK's typical full-model resonance implies 19.200 nH; sweep independent bulk ESL at 11.364 / 19.200 / 23.447 nH as model-informed sensitivity points, not a mounted-part bound.**

## Method

The user authorized TDK license acceptance; the coordinator then downloaded
the exact B3265* PSpice Unix archive through TDK's official table. Its
SHA-256 is `5eb5219af01c3fdaf80e68343fe9815960cc9d6696e216eccc9ddb78d9574df2`.
[model_analysis.py](model_analysis.py) rejects any other archive hash,
reads members without unpacking them into the repository, and evaluates
the complete equivalent circuit. The library is **TDK_B32651-8.lib,
v1.10, 2025-03-21**. [model-evidence.json](model-evidence.json) records
archive/member hashes, parameter locations, calculations and the independent
ngspice check. No licensed source model is committed.

The exact electrical-part subcircuits are `B32652A0104K` (library lines
269–282) and `B32656G0275J` (9287–9300). The `000` ordering suffix is
absent from the model names. The frozen BOM/netlist/native-17 part identities
match at source revision `f9b13b483d6d4ed52439d4da419c7670bab6966c`;
[evidence.json](evidence.json) records the six references and input hashes.
No board/netlist/datasheet contradiction was found.

TDK's `BASE1` is **not a single series RLC**. It contains RC dispersion,
two series-connected `R || L` sections, `Cs1`, `Ls1`, and an overall
parallel leakage resistor. Consequently, taking `Ls1` alone or simply
adding all three inductors does not reproduce the resonance. The script
computes the first capacitive-to-inductive zero of the full complex
impedance, then applies `L_equiv = 1 / ((2π f_SR)² C_nominal)`.
This is a resonance-equivalent scalar, not a broadband replacement model.

## Numbers and sources

All model numbers in this table are extracted or calculated by the
committed script and output; they are typical-model results, not measured
parts or curve readings.

| Quantity | B32652A0104K / local | B32656G0275J / bulk |
| --- | --- | --- |
| Nominal capacitance | 100 nF | 2.7 µF |
| Model `Cs1` | 100.04 nF | 2.7013 µF |
| Model `Ls1` | 0.56365 nH | 11.364 nH |
| Model `Lp61`, shunted by `Rp61` | 0.95082 nH, 0.0037462 Ω | 4.1527 nH, 0.0041465 Ω |
| Model `Lp71`, shunted by `Rp71` | 2.120 nH, 0.11376 Ω | 7.9304 nH, 0.18227 Ω |
| Low-frequency sum of inductive branches | 3.63447 nH | 23.4471 nH |
| Full-model first SRF | 15.458225 MHz | 0.699020721 MHz |
| SRF-equivalent ESL using nominal C | **1.060037 nH** | **19.199787 nH** |
| Full-model real impedance at SRF | 0.105917 Ω | 0.0129195 Ω |

The inductive branches alone contribute a frequency-dependent effective
inductance `Ls1 + Lp61/(1+(ω Lp61/Rp61)²) +
Lp71/(1+(ω Lp71/Rp71)²)`. The other RC sections still contribute to the
full terminal impedance. Neither end of that expression's range is a
physical tolerance limit for the capacitor.

ngspice **45.2**, in PSpice compatibility mode (`ngbehavior=ps`), loaded
the full vendor library **byte-unmodified**. Both models were driven by
an AC current source and compared over **6001 points, 1 kHz–1 GHz**.
Maximum relative complex-impedance differences were **5.54e-9 local**
and **3.08e-6 bulk**, below the stated **1e-5 numerical-check tolerance**.
The interpolated ngspice resonances were **15.458233 MHz** and
**0.699021210 MHz**, within **7.01e-7 relative** of the analytical roots.
The output includes representative frequency points. This wide sweep
checks implementation agreement only; it does **not** validate physical
model accuracy above resonance. TDK's README describes typical parts and
expects accurate results only below the first resonance. [S2]

There is no plot-reading uncertainty: these are numerical model values.
Model-fit accuracy, production spread and mounting-reference uncertainty
are unspecified; the numerical residual must not be presented as their
uncertainty. The family impedance graph was located at printed p. 37 of
the June 2026 series datasheet, but no part-specific curve was digitized
or used to claim independent physical validation. [S1]

## FEM boundary, mounting and recommended sweeps

The brief establishes that FEM reaches the PCB pads and excludes the
capacitor body and leads above the board. Added capacitor impedance must
represent that omitted path, without adding PCB loop inductance twice.
The model header and archive README do not specify cut-lead length,
mounting standoff, measurement reference plane or the four-pin terminal
pairing. The models expose only `A1` and `A2`. Thus the typical model is
available, but transfer to the mounted assembly remains conditional.
Do not subtract a guessed lead term or silently assume the supplied
lead length is the model's reference condition.

The local part has nominal 15 mm pitch, maximum 18 × 9 × 17.5 mm body
and supplied 6−1 mm leads. B32656G is a four-pin part with nominal
37.5 mm primary pitch. [S1, S3] The general technical rule relates
inductance to both capacitor length and lead length at 1 nH/mm. [S4]
The earlier `PACKAGE-INDUCTANCE.md` claim “≤ ~20 nH” therefore does not
establish a mounted bound without a defined lead geometry/reference plane.

Recommended scalar sensitivity points, all in nH:

- **Local: 1.060037 / 3.63447 / 5 / 10 / 20.** The first two are the
  resonance-equivalent value and low-frequency inductive-branch sum.
  The remaining points retain the inherited exploratory sweep; they are
  assembly stress assumptions, not vendor tolerances. Adding the lower
  typical anchor is warranted; narrowing to it is not.
- **Bulk: 11.364 / 19.199787 / 23.4471**, independently for C5 and C6.
  These are the model's explicit series term, resonance-equivalent value
  and inductive-branch sum. They test scalar-model sensitivity; they do
  not bound added lead inductance or guarantee assembly coverage.

When practical, use the full licensed frequency-dependent model for a
separate typical comparison. A scalar ESL plus the existing fixed ESR
cannot preserve all of its loss and dispersion.

The existing five-port deck `d2/leg_matrix5.cir` shares `LESL` between
`Lesl6`, `Lesl38` and `Lesl39`; `Cbulk5` has no separate component ESL
and its path uses heuristic `LBULK`. A later integration must separate
local and bulk parameters, and C5's part/path terms. This report changes
no deck, board or existing round-17 result.

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
  live page, accessed 2026-10-02; user authorized license acceptance before the successful download.

## Reproduce and remaining qualification

After accepting TDK's license, download the S2 archive to a private local
path. Do not add the archive or library to git. From the repository root:

```sh
python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D7/model_analysis.py /path/to/tdk-b32651-8-ps-ux-en-tar.tar --ngspice /opt/homebrew/bin/ngspice
python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D7/esl_arithmetic.py
```

Python 3.12 uses only the standard library. The optional ngspice check
places an unmodified temporary library and deck outside the repository,
then removes them. It needs no MOSFET model because this is a capacitor-only
AC test. Omitting `--ngspice` runs just the analytical extraction. The
separate arithmetic script also accepts an externally measured capacitance
and SRF; input values alone do not establish evidence.

**Owner/integration decisions:** adopt separate bulk/local model inputs;
obtain TDK's model lead/reference-plane definition or measure an installed
sample; retain assembly margin until that is known. The vendor-typical
ESL question is answered, but a mounted maximum and physical switching
qualification remain open. FINDINGS M4 may now cite verified typical
models; it must not become an unconditional physical bound.

# D-7: exact-part capacitor models and what their ESL means

**C38–C41, B32652A0104K000:** use **1–3 nH as a typical-model sensitivity range**, alongside the existing 5/10/20 nH assembly sensitivities; the complete TDK model gives **1.060 nH SRF-equivalent ESL**, not a guaranteed mounted range.

**C5/C6, B32656G0275J000:** use **19–22 nH as a typical-model sensitivity range below resonance**, centered near **19.200 nH SRF-equivalent ESL**; no justified mounted upper bound or validated MHz range was found.

These recommendations add part-specific centers; they do **not** justify deleting the wider mounting sensitivities or passing the board. The two capacitors should not share one ESL parameter. This report changes no design or upstream simulation files.

## Source identity and applicability

Study base: `1f09223516cc37d00f73b5e5e6d33a0197d7a30d`; inspected 2026-10-02 by GPT-6 Astra. Board identity is `native-17/section.kicad_pcb`; BOM identity is `frozen/default.csv`, relative to `zapote/power-stage-120v/`.

TDK's [B3265* LTspice model listing](https://www.tdk-electronics.tdk.com/en/2970304/design-support/design-tools/film-capacitors/model-libraries/ltspice) links the [Unix archive](https://www.tdk-electronics.tdk.com/download/2975958/9fc7efe428b49230f1257e9bef7990b8/tdk-b32651-8-lt-ux-en-tar.tar). The [readme/history](https://www.tdk-electronics.tdk.com/en/2970296/design-support/design-tools/film-capacitors/model-libraries/film-capacitors-readme-and-history/2975956) identifies version 1.10, assembled 21 March 2025, and lists **both** electrical codes. This replaces the earlier unsuccessful model search, not the board's physical qualification.

- Archive SHA-256: `e534e423ccaf7566b3eef32fb8120ffff53bb27e33a7cd17e5eca50a10f55f0a`.
- `TDK_B32651-8.sub` SHA-256: `45ee84837444e3d7abe714c4ee14c7b939fd78c2618101cdcd85bf04f41489e6`.
- Exact subcircuits: `B32652A0104K` (line 269) and `B32656G0275J` (line 9287); common base begins line 42. Readme assembly time is 11:49:10 CET; library header generation time is 11:29:54 CET on the same date.
- These are **typical linear models**, with the vendor's stated accuracy expectation limited to frequencies below the first resonance. No ESL tolerance, sample distribution, terminal fixture drawing or installed lead length appears in the downloaded model/readme.
- User explicitly approved accepting the TDK Design Tools licence before download. Licence section B.4 restricts copying/transfer/modification; the restricted archive and model are **not committed**. The committed reader consumes the locally licensed archive, checks its digest, and emits derived results. No model values are silently substituted from a different part.

The [TDK B3265*A/G/J/T datasheet, June 2026](https://product.tdk.com/system/files/dam/doc/product/capacitor/film/mkp_mfp/data_sheet/20/20/db/fc_2009/mkp_b32651_658.pdf) resolves the omitted packaging suffix: `000` denotes straight untaped leads, nominal supplied length 6 mm with −1 mm tolerance. This does **not** establish that the model was measured at that length. Printed p.14 identifies B32652A0104+*** as 100 nF, 1000 V, 9 × 17.5 × 18 mm (w × h × l); K is ±10%. Printed p.29 identifies B32656G0275+*** as 2700 nF, 33 × 48 × 42 mm, second pitch P1=20.3 mm; J is ±5%. Do not use the separate M-tolerance row, which has a different body. Drawings A1/B1 on pp.3–4 give 15 mm two-pin pitch and 37.5 mm four-pin pitch respectively. Product pages independently confirm [local](https://product.tdk.com/en/search/capacitor/film/snubbering_pfc/info?part_no=B32652A0104K000) and [bulk](https://product.tdk.com/en/search/capacitor/film/snubbering_pfc/info?part_no=B32656G0275J000) identities. Board footprint descriptions and BOM match these electrical/mechanical identities; no board-versus-vendor contradiction was found in this limited check.

## Method and results

Run from repository root, with the archive downloaded through TDK's licensed download flow:

```sh
python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D7/read_model.py "$HOME/Downloads/tdk-b32651-8-lt-ux-en-tar.tar"
```

Output is [model-results.json](model-results.json). The standard-library script reads the model without extracting it into Git. It stamps the downloaded resistor/capacitor/inductor graph into an admittance matrix, injects unit AC current, and solves for terminal impedance. SRF is the capacitive-to-inductive zero of Im(Z), bracketed and bisected. It then computes `L_SRF = 1 / ((2π f_SRF)^2 C)`. This is **not** the frequency of minimum |Z| for a lossy model. It cross-checks nodal impedances against independent series/parallel reduction and checks a known series RLC circuit. No Rust or workspace builds are involved.

| Quantity | Local B32652A0104K | Bulk B32656G0275J |
| --- | ---: | ---: |
| Nominal C used for SRF reduction | 100 nF | 2.7 µF |
| Model main series capacitance Cs | 100.04 nF | 2.7013 µF |
| Bare internal series inductor Ls | 0.56365 nH | 11.364 nH |
| Full model SRF | 15.458225 MHz | 0.699021 MHz |
| SRF-equivalent L, nominal C | 1.060037 nH | 19.199787 nH |
| SRF-equivalent L, model Cs | 1.059613 nH | 19.190547 nH |

The model includes lossy inductive branches and dielectric dispersion. Its named Ls is only one element, so neither Ls alone nor the sum of all internal inductors is a substitute for terminal ESL. Numerical precision in JSON is for reproducibility, not physical accuracy.

Define a frequency-local ideal-series-L fit by `L_eq(f) = [Im(Z(f)) + 1/(2πf C_nom)]/(2πf)`. This subtracts a **chosen constant** capacitance; it is not a unique physical extraction of body inductance.

| Frequency | Local L_eq | Bulk L_eq | Validity |
| --- | ---: | ---: | --- |
| 0.1 MHz | −16.756 nH | 21.327 nH | Below both SRFs; local negative value exposes capacitance/dispersion sensitivity, not a negative physical inductor |
| 0.5 MHz | 2.363 nH | 19.492 nH | Below both SRFs |
| 1 MHz | 2.699 nH | 18.836 nH | Bulk beyond vendor's accuracy expectation |
| 2 MHz | 2.602 nH | 17.493 nH | Bulk beyond vendor's accuracy expectation |
| 5 MHz | 2.148 nH | 14.133 nH | Bulk beyond vendor's accuracy expectation |
| 10 MHz | 1.459 nH | 12.301 nH | Bulk beyond vendor's accuracy expectation |
| 20 MHz | 0.891 nH | 11.621 nH | Both beyond vendor's accuracy expectation |

The recommended local 1–3 nH is a rounded sensitivity envelope around the 0.5–10 MHz fit and the SRF reduction; bulk 19–22 nH brackets the 0.1–0.5 MHz fit and SRF reduction. Neither is a statistical interval nor a production bound. Above resonance the table reports mathematical model output only. In particular the bulk's approximately 11–19 nH MHz behavior cannot validate fast switching edges. Use the complete model where its validity and licence permit; any lumped substitute loses frequency-dependent damping as well as reactance.

The datasheet's printed p.37 impedance chart is labeled typical and is a family chart. No curve was digitized or assigned an exact-part SRF here. The direct exact-electrical-code model is stronger evidence, but still does not specify its physical measurement fixture. The previous `PACKAGE-INDUCTANCE.md` “≤ ~20 nH” statement relies on a general length heuristic; absent an explicit lead/reference-plane accounting, it is not a demonstrated mounted upper bound. This study does not replace that uncertainty with an invented guaranteed number.

## Mounting, four-pin geometry, and FEM boundary

The h→0 FEM closure ends at PCB pads and removes its artificial component bridge. It omits capacitor body and above-board leads. TDK's model is a two-terminal fit even for the four-pin part. There is no separate terminal-current or mutual-inductance matrix, and no exposed lead-length parameter. Packaging lead length must not be confused with seated height: part of a supplied lead passes through the PCB or is clipped. Adding all supplied lead length to both the vendor model and the board model could double-count; adding none could miss the above-board segment. The physical reference plane is unresolved.

On the frozen native board, C5/C6 local pads 1/2 are `bus_p` at x=0 and y=0/20.3 mm; pads 3/4 are `hv_ret` at x=37.5 mm and y=0/20.3 mm. Thus both wires on each electrode may carry current. Their sharing depends on how the PCB feeds them, and the magnetic coupling means four pins do **not** imply half of a two-pin ESL. `d2/leg_matrix5.cir` represents P5 as C6.1→C6.3; transferring a two-terminal vendor fit to that specific closure does not prove equivalent excitation of all four physical leads. Resolve this with TDK's fixture description or a mounted four-terminal impedance measurement matched to the FEM pad ports.

The five-port deck also uses the same `LESL` for C6 and C38/C39, while C5 sits behind `LBULK` without a separate named capacitor ESL. The exact-part models do not support tying local and bulk ESL together. Treat this as a model-configuration finding for the owner; no upstream deck is changed. Check what LBULK already includes before adding another term.

## Handback and remaining qualification

This completes vendor model discovery and repeatable model arithmetic. It narrows the **typical-model question**, not the assembly's uncertainty interval. Retain the existing local 5/10/20 nH sensitivities, add the 1–3 nH typical cases, and independently vary bulk around its sourced 19–22 nH low-frequency values. Do not certify a board from any one scalar choice. Obtain installed terminal height, current-sharing fixture, and impedance measurement through and beyond resonance before deleting cases or asserting a worst-case range.

The LTspice archive was also tried unmodified in ngspice 45.2: `lt` compatibility rejected its nested subcircuit parameter syntax, while `ps`/`ltps` rejected LTspice-specific `Rpar` annotations. No SPICE run is claimed as validation. The committed nodal/reduction cross-check verifies arithmetic on the supplied model; it is not independent physical validation. A compatible official PSpice download was identified but the browser transfer failed; no modified vendor model is distributed to work around that failure.

## Verification receipt

- Model replay: Python 3.14, pinned archive, closed-form RLC sanity check and nodal-versus-series/parallel checks passed; parent independently reproduced the committed JSON byte-for-byte.
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=packages/temper-placer/src .venv/bin/python scripts/import_linter_gate.py`: **5 contracts kept, 0 broken; 0 new violations**. Private environment contains only import-linter/PyYAML and dependencies; no workspace sync. An initial invocation without the PATH override selected uv and failed before analysis; it was not a passing check.
- `python3 scripts/regen_derived.py --check`: **all derived artifacts consistent**.
- `git diff --check`: passed.
- Source board SHA-256: `16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`.
- Frozen BOM SHA-256: `08708ee5d1e7d66789f5b168dc018306bc972f8865a8afd7d33e3269120bed67`.

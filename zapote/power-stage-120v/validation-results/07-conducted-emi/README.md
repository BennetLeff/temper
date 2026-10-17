# 07 Conducted EMI pre-check — blocked intake

- **Board:** `native-13/section.kicad_pcb`, SHA-256 `8056fc952675bc6987bcc9d32c12a88eebc4cec9bc3696f8cbd4876700a39129`.
- **Kit/source revision:** `36ba41f249eea0b9c78c9d7bdd6e38ea04bb37f9` on `codex/ps-sim-07`; checked 2026-09-27 with ngspice 45.2 and KiCad 10 Python. Operator: Codex (GPT-6).
- **Evidence class:** exact structural (PCB pad locations and part identity); datasheet primary source (package dimensions); simulation/model-based only for kit smoke test. No EMI performance result or physical measurement.
- **Verdict:** **BLOCKED**. The exact specified X capacitor does not match either saved C1/C2 footprint. The master plan requires stopping on a committed-design contradiction. No conducted margin or board PASS is claimed.

## Summary

Both C1 and C2 have 22.50 mm between native-13 pad centers. Their saved board value is `R463R410000M1M`. The [KEMET R46 datasheet](sources/KEM_F3095_R46_X2_310_110C.pdf) specifies **27.5 ± 0.4 mm** lead spacing for that exact ordering-code family: a **5.0 mm nominal mismatch**, at least 4.6 mm beyond the stated tolerance. The same row gives a **32 × 20 × 11 mm** body (length × height × width), whereas the KiCad footprint name encodes 26.5 × 10.5 mm. These are part/land-pattern contradictions, not a quantified EMI failure. They require owner review of the part and layout without an unvalidated part substitution.

The simulator [smoke test](outputs/smoke_test.txt) ended `SMOKE PASS` (16 checks). It confirms that the starter kit runs on this host; it does not validate the EMI deck's physical source or predict terminal emissions.

## Method and sources

The reproducible [pitch check](scripts/check_x_cap_pitch.py) reads the saved PCB with KiCad Python, checks the exact `GetValue()` for C1/C2, measures each pair of pad centers, and compares them with the [source-bound dimensions](inputs/part_dimensions.json). Its full [output](outputs/x_cap_pitch.json) records the source and board hashes and the actual pad nets. Manufacturer data come from KEMET datasheet `F3095_R46_X2_310_110C` dated 2026-05-13: p. 1 decodes `R` as 27.5 mm lead spacing; p. 2 decodes packaging `00`; p. 3 specifies 27.5 ± 0.4 mm mechanical pitch; p. 10 lists `R463R4100(1)M1(2)` at 1 µF and 32 × 20 × 11 mm. `(1)=00` and `(2)=M` expand to `R463R410000M1M`. Source URL: <https://content.kemet.com/datasheets/KEM_F3095_R46_X2_310_110C.pdf>; saved PDF SHA-256 `5a3131ce8de7445130b777cab1a5e1a17e6b5f3343faddfe19735221db205094`.

The exact L1 code `B82726S2203A020` is in the [TDK May 2026 datasheet](https://www.tdk-electronics.tdk.com/inf/30/db/ind_2008/b82726s22x3.pdf), p. 4: 1.6 mH nominal **per winding**, 18 µH typical stray inductance and 4.5 mΩ typical DC resistance per winding, at the listed measurement conditions. The p. 4 inductance tolerance is −30/+50%; p. 5 has a typical impedance curve for windings in parallel, but no tabulated winding capacitance or self-resonance value. Its [source record](sources/tdk-b82726s2203a020.json) preserves the downloaded PDF SHA-256 `e8002bfe4af13edf3709f33d21d9b2f834dd04223707abdaffad9293116f3f46`; only its URL and hash are retained because TDK's document notice restricts redistribution. No choke capacitance was inferred by eye from the plot.

The official [47 CFR 18.307(a)](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-18/subpart-C/section-18.307) table for induction cooking ranges was read on 2026-09-27; eCFR said Title 47 was current through 2026-09-24. A [sourced transcription](sources/ecfr-47cfr18.307-table.json) preserves both quasi-peak and average limits. In the intended 0.15–30 MHz span these are 66→56 / 56→46 dBµV (QP/average) from 0.15–0.5 MHz, 56 / 46 from 0.5–5 MHz and 60 / 50 from 5–30 MHz, with the tighter value at a boundary. Section 18.307(e) excepts the [18.301 operating bands](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-18/subpart-C/section-18.301). The shell download of eCFR returned a `Request Access` page, so the local JSON is explicitly a transcription, not a claimed hash of the official HTML. No detector comparison was made.

## Unresolved EMI model inputs and topology

No `margins.csv` or `spectrum_dm_cm.png` was produced because the stop rule applies before an acceptance sweep. These inputs remain missing or unqualified:

| Input | Status and effect |
| --- | --- |
| Task 01 switch-node edges | No board-specific `sw_edge_s` is available. A 1–20 V/ns range is permitted only for a provisional sensitivity, not a nominal board verdict. |
| Task 03 insulating pad | No selected pad or verified thickness, permittivity and tab overlap area; switch-node-to-PE capacitance `CPE` cannot be fixed. |
| KEMET C1/C2 ESR and ESL | The PDF gives 1 kHz dissipation factor, not a validated 150 kHz–30 MHz ESR/ESL pair. The kit's 10 mΩ and 15 nH are placeholders. |
| L1 high-frequency behavior | Datasheet gives a typical impedance curve, but no numeric winding capacitance. The kit's 15 pF is a placeholder; a measured or justified curve fit is needed. |
| Other paths | MOV capacitance, rectifier junction capacitance, bus-capacitor ESL, coil/pan-to-earth capacitance, harness/PE bond and asymmetries are unmeasured here. |

The starter `emi_transfer.cir` at kit SHA-256 `6cf73924c30f57bd96bac61bd879112861b0fd7b32eb26a38bf9f6b3f1c93ef5` is not a board source model yet. Its `Vcm swcm 0` followed by `Ccpe swcm bus_n` injects through a capacitor **to the DC return**; the physical low-side tabs Q3/Q6 are on `sw_a`/`sw_b` and capacitively couple **to the PE-bonded heatsink**. The two switch nodes are driven in anti-phase, so equal capacitive currents may cancel at the PE path while unequal pads, edges and stray paths leave residual CM current. A single ideal 1 V CM source cannot establish either the cancellation or its residual. The deck's DM drive is an ideal 1 V bus differential source, not a board-derived ripple-current spectrum. It also omits the MOV, rectifier junction capacitance and bus ESL called for by the task. Consequently its placeholder reference transfer numbers cannot be promoted to emission predictions or acceptance margins. The kit runner ignores the second `--raw` run's exit status; any future use must inspect both full logs and verify the raw frequency/vector count before post-processing.

## Results and sensitivity

The only board-specific numerical result is the 5.0 mm C1/C2 nominal lead-spacing mismatch in `outputs/x_cap_pitch.json`. Dominant EMI mode, minimum 6 dB peak margin, and sensitivities to CPE, LCM, edge time and coil-to-earth capacitance are **undetermined**. The smoke test's transfer check is a starter-kit regression with placeholders, not a board prediction. No final PASS/FAIL against 47 CFR 18.307 is supported.

## Open items and physical confirmation

The board owner must resolve the exact C1/C2 part-to-footprint conflict, then revalidate the resulting saved board and part identities. Task 01 must provide board-derived edge times; task 03 must identify and characterize the actual insulating pad. Obtain the remaining exact-part parasitics or measure impedance, replace the placeholder EMI source with an anti-phase two-node model that preserves PE return paths, and rerun DM/CM analyses with checked raw data. A conducted-EMI pre-scan using a calibrated LISN and the relevant detectors remains the physical confirmation; this desk result cannot release fabrication or establish regulatory compliance.

## Reproduce

From the repository root in this worktree:

```sh
cd zapote/power-stage-120v/validation-plan/sim-kit
python3 smoke_test.py
cd ../../../..
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
  zapote/power-stage-120v/validation-results/07-conducted-emi/scripts/check_x_cap_pitch.py
shasum -a 256 zapote/power-stage-120v/native-13/section.kicad_pcb \
  zapote/power-stage-120v/validation-results/07-conducted-emi/sources/*.pdf
```

The kit's locally fetched official Infineon model hashes were checked against `models/fetch_models.sh`: ZIP `5a6341084202debb0f8f230b8809c090434ea9526c8e0defe3d2e07a832ff48d`, extracted library `02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b`. Vendor files are ignored and not duplicated here. The original `outputs/smoke_test.txt` and `outputs/x_cap_pitch.json` are retained.

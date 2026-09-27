# 01 Layout parasitics and switching transient — partial result

The [round-2 complementary-drive check](round2/README.md) validates both modeled gate commands, deadtime and light-load behavior with clearly labeled reference inductances. It does not change this board-level blocked verdict.

- Board: `native-13/section.kicad_pcb`, SHA-256 `8056fc952675bc6987bcc9d32c12a88eebc4cec9bc3696f8cbd4876700a39129`
- Date: 2026-09-27. Source/kit commit: `36ba41f249eea0b9c78c9d7bdd6e38ea04bb37f9` on `codex/ps-sim-01`. Operator: Codex simulation worker.
- Tools: KiCad 10.0.4 board reader, Python 3.12.12 and Shapely 2.1.2, ngspice 45.2. Vendor model: Infineon `IPW65R018CFD7_L1`; model file SHA-256 is in [source review](sources/SOURCE-REVIEW.md).
- Evidence class: exact structural (native pad, track and via census), heuristic/model-based (sampled plane-pair inductance terms), and simulation/model-based *only for the kit smoke tests*. No physical qualification is claimed.
- **Verdict: BLOCKED.** The official TDK source does not supply numeric local-capacitor ESL or self-resonant frequency. The sampled bus/return planes do not continuously overlap along the specified pad-centre paths, so the prescribed plane-pair formula cannot supply complete `LD_HS`, `LS_HS`, `LD_LS`, `LS_LS`, or `LCS`. Gate source-return pairing is unresolved. No board-bound switching sweep was run with deck placeholders.

## Summary

The supplied simulation kit passed all 16 smoke checks with the pinned Infineon model; the [complete output](outputs/smoke-test.txt) is preserved. The [native copper census](inputs/copper.json.gz) (lossless gzip) contains 388 pads, 642 tracks, 177 vias and 31 filled-zone polygons. The [analytic output](outputs/loop_inductance.json) reports pad-centre paths, sampled filled-zone overlap, gate-output track lengths and a single-via formula value, while leaving every complete leg total and deck parameter `null`. For example, A's C39 BUS_P pad to Q2 drain has paired In2 BUS_P/In1 HV_RET overlap for 9.38 of 19.76 mm; B's C40 to Q5 has overlap for 7.97 of 20.91 mm. The rest cannot be assigned zero inductance. These figures are geometric estimates, not bounds on the complete loop.

## Method and assumptions

`tools/copper_dump.py` read the exact native-13 board with KiCad Python. [via_probe.py](scripts/via_probe.py) extracted actual pad positions and via drills from the same board; the two files' board hashes agree. [loop_inductance.py](scripts/loop_inductance.py) samples every 0.5 mm along selected pad-centre chords, intersects In2 BUS_P and In1 HV_RET or LEG_RET filled zones, and applies `L = μ0 d ℓ / w` only to sampled intervals with zone overlap. `d = 0.5 mm` comes from `stackup.json`. It reports the uncovered path length separately. The copper census polygons fill any holes, and a pad-centre chord is not a field-solved current path; the terms are approximate and cannot certify a low or high limit.

The three 0.8 mm power vias near Q3 source and the three near R5 return have known native positions and drills. The output gives the runbook's single-via formula over the F.Cu–In1 dielectric as a heuristic local term (0.155 nH); it assigns no bank equivalent because mutual inductance and current sharing are unknown. Through-hole MOSFET and capacitor pads span all copper layers. The Infineon L1 model already includes its own package inductances, so package L is not added to the board values. Gate-output trace lengths are exact sums for their unbranched nets and reproduce the older native-06 values, but the gate-return conductors have not been paired section by section. The `leg_*-gate_*` net sums include hold-off branches and are not treated as series path lengths.

## Results and acceptance criteria

| Criterion | Answer |
| --- | --- |
| Normal S1/S3 VDS ≤ 520 V | **BLOCKED** — board `LD/LS/LCAP/LG` values are unresolved; kit smoke peaks use placeholders. |
| Fault S2 at 280 V ≤ 585 V | **BLOCKED** — no board-bound 61/71 A waveform or margin. |
| Off-device VGS below VGS(th),min − 0.5 V | **BLOCKED** — no board-bound gate-path inductance or sweep. |
| Die VGS within transient limits | **BLOCKED** — no board-bound sweep and source-bound limit table. |
| S1 ZVS at nominal dead time; minimum current | **BLOCKED independently by deck scope** — `01-switching/leg.cir` keeps the high-side gate off, imposes a single low-side turn-off or hard turn-on, and has no complementary gate transition or dead-time parameter. A disappearing hard-turn-on spike cannot establish the minimum ZVS current. |
| Low-to-high inductance sensitivity | **BLOCKED** — no defensible nominal inductance from which to form corners. |

The starter deck also lacks explicit 10 kΩ gate hold-off resistors and a full-tank case. These are separate model gaps from missing ESL. `common/run_ngspice.py` does not expose the process return code, preserves only a short log tail, and ignores the raw second-run status. Any future sweep must record full logs and independently verify return codes, required measures and raw time windows. Since the required inputs already block the sweep, no board-bound deck was run, no peak was reported, and the required half-timestep confirmation and waveforms were not attempted.

## Sensitivity and dependent work

The covered plane-pair terms range from about 0.12 to 1.15 nH on sampled intervals, but incomplete overlap and capacitor ESL can dominate the actual loop. Scaling these partial terms by 0.7/1.5 would not yield meaningful leg corners. `LCAP`, `LBULK`, the four `LD/LS` terms, `LCS`, and `LG` remain `null` in the machine-readable output.

Task 02 cannot use a board-bound overshoot or simulated turn-off time from task 01; its existing bounded detector calculations remain separate. Task 05 cannot use a minimum-ZVS-current table from this deck. Task 07 cannot use a board-bound switch-node edge time or dv/dt. The placeholder smoke results must not be transferred to those tasks as board predictions.

## Open items and physical confirmation

Obtain manufacturer or measured ESL/self-resonance for the exact B32652A0104K000 local capacitor, and bind its source file/hash and test conditions. Establish continuous paired-current paths, pad/via current sharing and source-return paths on native-13 (field solve or verified geometry), then map board-only inductance terms to every deck parameter. Extend the switching deck with complementary timing and hold-off resistors before making a ZVS claim. A corrected board-bound simulation must run the specified grid, stop on the first failed criterion, retain full logs/raw waveforms, and halve the timestep for the reported peaks. Final confirmation is oscilloscope measurement of VDS, accessible gate/source-pin waveforms and switch-node timing at staged low-voltage bring-up, with quantified probe and package-parasitic uncertainty rather than a claim to measure die VGS directly, followed by fault tests under an approved hardware procedure.

## Reproduce

From the repository root at the stated source commit, with the vendor models installed and SHA-verified by `validation-plan/sim-kit/models/fetch_models.sh`:

```sh
P=zapote/power-stage-120v
R=$P/validation-results/01-switching-parasitics
python3 "$P/validation-plan/sim-kit/smoke_test.py" > "$R/outputs/smoke-test.txt" 2>&1
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 "$P/tools/copper_dump.py" "$P/native-13/section.kicad_pcb" "$R/inputs/copper.json"
python3 -c 'import gzip,pathlib,sys; p=pathlib.Path(sys.argv[1]); p.with_suffix(".json.gz").write_bytes(gzip.compress(p.read_bytes(), compresslevel=9, mtime=0)); p.unlink()' "$R/inputs/copper.json"
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 "$R/scripts/via_probe.py" "$P/native-13/section.kicad_pcb" "$R/inputs/vias-and-pads.json"
/Users/bennet/Miniforge3/bin/python3 "$R/scripts/loop_inductance.py" "$R/inputs/copper.json.gz" "$R/inputs/vias-and-pads.json" "$P/stackup.json" "$R/outputs/loop_inductance.json"
```

All extracted numeric values in this report come from those committed scripts and outputs. Source availability and the missing ESL are documented in [SOURCE-REVIEW.md](sources/SOURCE-REVIEW.md).

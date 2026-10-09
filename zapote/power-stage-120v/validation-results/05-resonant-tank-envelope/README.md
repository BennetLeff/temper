# 05 Resonant tank operating envelope

## Current status: round 4, assumed basis (2026-10-09). See [round4-assumed-basis/](round4-assumed-basis/README.md)

**ASSUMED / pre-measurement.** No coil or pan has been measured. The coil and pan values are
digitized from published charts:
- onsemi AND9201 (2015) p. 7;
- Infineon UG-2023-15 (2023) p. 21 Fig. 16;
- cross-checked against MDPI Electronics 12(19):4145 and Pascual et al., IEEE Access 11 (2023).

The basis covers L0 = 70 µH ±10 %, R_ac = 0.245 Ω (0.17–0.41) at 40 kHz, and five pan classes.
On it, the documented **135-case grid is complete**: 5 pan classes × 3 corners × 108/120/140 V ×
1710/855/300 W, plus 27 supplemental offset-pan cases and tolerance and alternative-bank runs. It
ran under the native-21 envelope: 35–60 kHz, f ≥ 1.05·f_res, tank ≤ 22 A RMS, 11.1 A input hold.

**Verdict:**
- **Fits the envelope.** ZVS margin (f/f_res ≥ 1.23), capacitor voltage (≤184 V RMS, ≤367 V peak) and the CT (≥2.8 A below the minimum CT trip) all fit.
- **The 942C blocker is resolved by a conservative bound, and the parts fail it.** The bound is I_allow ≥ I(70 °C, 100 kHz)·√(f/100 kHz), cross-checked against the 25 °C curves. At the 22 A ceiling, C21/C22 exceed it in 90/135 cases (up to 1.64×). They also exceed the best estimate in 30/135 cases (up to 1.045×).
- **Recommended fix.** 5 × 942C16P1K-F (0.50 µF), which passes the bound everywhere, or a bench hot-spot measurement.
- **Shunt OCP.** Envelope tank peaks (47.3–47.7 A) reach the 47.52 A low edge of the shunt OCP band.

**Design response (stage 13, DECISIONS.md 2026-10-09):**
- **Bank:** 5 × **TDK B32654A1104K000** (0.50 µF, 1600 Vdc / 500 Vac, 7.3 A at 85 °C / 100 kHz), not the 942C16P1K-F, which does not fit the slot.
- **Rating evidence:** an independent review found the √f bound valid but about 1.4× pessimistic for the 942C. On CDE's own curve shapes the as-built bank is 1.08–1.17× over. The TDK bank is 0.86× on TDK's own 85 °C current-vs-frequency curve (read by eye, ±10 %).
- **Resonance:** this round's 0.50 µF run covers it (minimum f/f_res 1.21).

What the bench measures first:
1. loaded L/R per pan class over 25–60 kHz;
2. bank hot-spot (middle TDK cap of the tightly stacked column) at 22 A, 35–45 kHz, ΔT ≤ 20 K;
3. tank peak against the actual trip thresholds.

The round-1 text below and rounds 3 and 4A are history. They used the earlier `coil_mc.rs` pan
classes and no 22 A envelope.

---

## Round 1 (2026-09-27): partial result

- **Board:** `native-13/section.kicad_pcb`, SHA-256 `8056fc952675bc6987bcc9d32c12a88eebc4cec9bc3696f8cbd4876700a39129` (presentation revision; native-09 references in older documents are stale).
- **Kit/source revision:** `36ba41f249eea0b9c78c9d7bdd6e38ea04bb37f9`; 2026-09-27; ngspice 45.2; Python 3; Codex GPT-6.
- **Evidence class:** simulation/model-based for tank quantities; conditional bounded calculation for isolated-capacitor bleed; physical-test requirement for coil/pan values, capacitor temperature and trip waveform.
- **Verdict: BLOCKED.** Nine of 135 planned pan/line/power cases were retained. The exact CDE 942C allowable current for the actual 34–55 kHz frequencies and hot local temperature is not supplied; the 0.22 µF curve is absent. Task 01 has no minimum-ZVS-current threshold. The ideal bridge deck cannot model trip ring-down or rectified shunt current. No whole-envelope pass or fail is claimed.

## Summary

The completed cases cover the **low-L/low-R cast-iron corner** at 108, 120 and 140 V RMS, each at 1,710, 855 and 300 W. All nine frequency searches achieved their targets between 34.61 and 54.63 kHz, above this corner's 30.09 kHz resonance. The largest simulated tank peak is **51.52 A** (140 V, 1,710 W), 36.48 A below the task's 88 A T1 screen. The largest capacitor peak is **452.07 V**, with **224.96 V RMS**, **26.44 A bank RMS**, and **10.77 A RMS nominal share** in each 0.22 µF part (108 V, 1,710 W). That 10.77 A must **not** be compared as a verdict with CDE's 10.3 A specified only at 70 °C/100 kHz.

## Method and assumptions

- The starter `05-tank/tank.cir` drives ideal ±`|√2·VRMS·sin(2π·60t)|` through series R-L-C for one 8.3333 ms line half-cycle. It omits MOSFET drops, the task document's requested ≈348 ns dead time, phase shift and bursts. It is an ideal **frequency-control-only** stress experiment, not a full controller or physical coil simulation.
- `find_freq.py` transcribes the five `PANS` ranges from `docs/hardware/power-section-120v/coil_mc.rs`. It sets nominal CRES = 0.54 µF, loaded coil L = 70 µH × `kl`, pan R40 = 70 × `r40`, coil R = 70 × `q`, and searches strictly above `1/(2π√LC)` up to 60 kHz. The `--limit 9` run stopped after the first pan corner because its exact capacitor acceptance input was unavailable. The code supports the entire grid when that input is resolved.
- Nominal capacitor current sharing uses parallel capacitance ratios 0.22:0.22:0.10. The actual ±10% capacitance tolerance, ESR variation, lead impedance and hot-spot temperature were not simulated. The `triply_clad_GUESS` class is explicitly a prior estimate and was not run here.
- R39 = 1.5 Ω and C42 = 100 nF on native-13; the CSV's secondary voltage and volt-time columns are **ideal 1:100 ratio, R39-only sinusoid estimates**. The CT core, C42 and secondary loading transient are absent from the tank deck. Coilcraft's 1 Ω terminating value is a reference example for 1 V at 100 A, not a permitted burden range. The task's “burden within datasheet” criterion needs a defined dynamic burden check.
- The deck includes no bridge or shunt conduction state, so `rectified_leg_return_i_rms_a` remains blank in `cases.csv`. Tank RMS current cannot be silently relabeled as R5 current for task 03.

## Results

`outputs/cases.csv` contains every retained case, all five ngspice measures, frequency, nominal current split, CT and bleed estimates, and run IDs. Each `outputs/runs/<run_id>/` has `params.inc`, a copied deck, a `result.json`, and the full replay log `ngspice-full.txt`. The wrapper checks the required `.meas` fields, finite values, replay exit status and agreement with the replayed measures. `outputs/smoke-test.txt` records **16/16 PASS** before any sweep. The model library copy is intentionally absent from the run folders; its verified SHA-256 is `02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b`.

| Retained-case quantity | Extreme | Basis / qualification |
| --- | ---: | --- |
| Tank RMS current over full line half-cycle | 26.44 A | 108 V, 1,710 W; this is not mid-line crest RMS |
| Tank peak / T1 primary peak | 51.52 A | 140 V, 1,710 W; task's 88 A screen clears by 36.48 A only in retained cases. The datasheet calls 88 A a DC thermal reference, not an absolute peak rating. |
| Capacitor bank peak / RMS voltage | 452.07 V / 224.96 V | 108 V, 1,710 W; 55.18 mJ at peak. CDE's 25 °C p. 4 curve does not establish the hot-condition limit for the exact 0.22 µF part. |
| C21/C22 nominal current share | 10.77 A RMS each | CDE p. 3 gives 10.3 A only at 70 °C/100 kHz; actual point is 34.61 kHz. **Rating unresolved.** |
| C23 nominal current share | 4.90 A RMS | CDE p. 3 gives 9.2 A at 70 °C/100 kHz; actual-frequency/current limit unresolved. |
| R22–R25 each, peak voltage | 113.02 V | Below Yageo's 200 V continuous working maximum in retained cases; computed with an ideal four-resistor equal division. |
| R22–R25 each, mean power | 6.73 mW | Below 125 mW (half of 0.25 W at 70 °C); local assembled temperature is unmeasured. |
| Ideal CT secondary burden peak / half-cycle volt-time | 0.773 V / 7.10 V·µs | Based on R39 = 1.5 Ω, ideal 1:100 sine; below Coilcraft's 638 V·µs table value, but not a CT transient simulation. |

The required peak timestep check repeated both retained full-power extremes with maximum step 50 → 25 ns. The largest peak change was **0.017%**, below the runbook's 2% threshold (`outputs/timestep-check.json`).

`extract_switching.py` independently checked raw ngspice exit status and the **8.3333 ms** raw end time. At ideal drive zero crossings with line amplitude ≥20% of crest, 503/503 full-power and 794/794 light-power crossings have the expected inductive current sign. Current magnitude ranges **8.22–43.44 A** at 108 V/1,710 W and **4.50–22.36 A** at 140 V/300 W. The sign is a model result, **not ZVS proof**: task 01 could not supply the minimum current, and an ideal drive has no dead-time commutation. See `outputs/switching-current.png` and the two switching CSV/JSON pairs. `zvs_map.png` is absent because a yes/no boundary would be invented.

The **conditional isolated-capacitor bleed** calculation starts from the largest retained 452.07 V peak and assumes zero coil current and no bridge/diode path after trip. With four 470 kΩ resistors and 0.54 µF, τ = 1.015 s and the 60 V crossing is **2.05 s**; at +1% resistance and +10% capacitance, **2.28 s** (`outputs/partial-summary.json`). This is below the task's 10 s flag *only under that isolation assumption*. The actual OCP-trip ring-down and voltage after coil-energy transfer remain **BLOCKED** because the ideal deck lacks the bridge-off topology.

## Sensitivity and open items

The nine cases do not cover the other pan classes or L/R/q corners, capacitor tolerance and thermal conditions, burst/phase-shift control, or startup and trip behavior. Their maxima are **observed partial maxima**, not bounds on the board. CDE `942C.pdf` p. 4 plots 1200 V family voltage versus frequency only at 25 °C and only for 0.10/0.33/0.90 µF; p. 3 gives exact part current values at 70 °C/100 kHz. An applicable hot-condition current/voltage curve or manufacturer confirmation for **942C12P22K-F at 34–60 kHz** is required before assigning a capacitor verdict. Do not use the DC rating or the 100 kHz current as a 34 kHz limit. Task 01's ZVS threshold and a bridge/CT trip model are separate blockers.

The physical checks remain loaded-coil L and pan R across pan classes, sustained capacitor can/hot-spot temperature, tank current and voltage waveforms over a line cycle, switching-node/dead-time behavior, CT secondary waveform, and post-trip capacitor voltage. The 60 V threshold here is the task document's SELV-like touch screen, not a claim of product compliance.

## Reproduce

From `zapote/power-stage-120v/validation-plan/sim-kit`, run `python3 smoke_test.py` and require `SMOKE PASS`. Then from this result directory:

```sh
python3 scripts/find_freq.py --limit 9
python3 scripts/check_timestep.py
/Users/bennet/Miniforge3/bin/python3 scripts/extract_switching.py cast_iron-low-108v-1710w
/Users/bennet/Miniforge3/bin/python3 scripts/extract_switching.py cast_iron-low-140v-300w
python3 scripts/analyze_partial.py
MPLCONFIGDIR=/tmp/tank05-mpl /Users/bennet/Miniforge3/bin/python3 scripts/plot_partial.py
```

With source limits and the missing physical topology resolved, omit `--limit 9` to run the documented 135-case grid. The ignored, exact vendor model files remain in the kit; neither is committed here.

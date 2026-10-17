# D22 round 2 — nonlinear line interaction and prototype decisions

**Disposition: HOLD powered filter/PCB release.** This round adds a two-way nonlinear **differential-mode, averaged-load diagnostic**. It finds failure scenarios hidden by the earlier one-way RF transfer calculation. It does not reproduce a deployed controller, real coil/pan, semiconductor switching edges, common-mode coupling, or an installed appliance. The earlier 9.280 dB modeled RF margin remains evidence for its original geometry and excitation only.

Baseline is native19 PCB SHA256 `3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b`, at local reviewed commit `3b8e64f51aac95bad4a4a6eaba216dd9e262a8bf`. No native source, board, upstream D22 evidence, or thresholds were edited by this workstream.

## New evidence

Thirty fresh ngspice 45.2 transients ran: 24 diagnostic cases and six 0.5 µs refinements of 2 µs cases. Each covers 300 ms with discharged initial capacitors, nonlinear four-diode rectification, source impedance, both filter stages, and bus-voltage-dependent load current in the **same solve**. The filter therefore changes bus voltage and the load current, and that current changes the filter. This closes the earlier one-way-model limitation at the averaged-load level only.

Five runner tests pass. Refinement compares startup peak/I²t, bus maxima, currents, powers and startup energy; all six comparisons are below the declared 2% numerical screen. Near-zero bus minima are excluded from relative-error acceptance. This is a metric convergence screen, not full waveform agreement, cycle stability or a hardware pass. See [results.csv](results.csv), [convergence.csv](convergence.csv) and [evidence.json](evidence.json). Raw waves and all generated decks remain under `output/temper-prototype-closure/round2/d22/run03/`; compact deck/log archive and hashes are retained here.

| Simulated diagnostic | Result | Decision |
|---|---|---|
| Conductance-shaped 1500 W command, 100/120/140 V RMS, continuous | 14.50/12.21/10.54 A input RMS; damper 0.119/0.173/0.236 W | This load law is materially less stressful; actual delivered power is lower than command because of modeled losses. It is not a released 1500 W envelope. |
| Regularized constant-power command, same line corners | 23.01/17.66/16.13 A input RMS; damper 54.64/22.32/17.14 W. Refined 100 V case: 22.95 A, 54.15 W, only 1144 W delivered | Reject this diagnostic behavior against 15 A input allocation and selected 5 W damper. Neither the old RF margin nor a fuse solves controller/filter interaction. |
| 140 V crest connection, load disabled for first 40 ms | Refined 118.23 A peak, 0.8089 A²s over first 40 ms; bus reaches 367.62 V | Gate disable cannot stop passive rectifier charging. The prior 280 V conditional shutdown corner is not a bound for this connection model. |
| Same connection, damper open | Refined bus 391.53 V | Damper failure changes startup stress. This is not a measured appliance surge value. |
| Exploratory 10 Ω series precharge, ideal bypass at 20 ms; four line phases | Refined crest: 18.02 A peak, 0.05834 A²s, startup bus 196.83 V, precharge resistor 0.4556 J. Later diagnostic burst reaches 222.74 V | Reserve a controlled precharge/inrush function for engineering design. Ten ohms and 20 ms are experiment parameters, **not selected parts, timing or a release**. Startup comparison is before either load law is enabled; subsequent load uses conductance law. |

The constant-power cases remain regularized at low voltage and current-limited, so the simulation does not demand infinite current at a zero crossing. Even so, they are unacceptable screens. No claim is made that existing firmware actually implements this law. A continuous 1500 W constant-power demand at 100 V also leaves no allowance for loss under a 15 A input budget, before considering power factor.

## Explicit model limits

- Native19 values: original 1 µF X capacitors, 5.4 µF bus film plus 0.4 µF local bypass. Added D22 stage: 2.2 µF input X, 4.7 µF output X, 4.7 µF/3.9 Ω damping, 30 kΩ bleed. Two 18 µH **differential loop** leakage equivalents represent the two coupled chokes; this is not 18 µH per conductor. New/old leakage are swept together to 9/27 µH as sensitivity, not guaranteed hot limits. Film ESR is assumed 35 mΩ; winding loop resistance 9 mΩ is typical cold, not hot maximum.
- Source loop impedance is assumed 0.1 Ω/20 µH or 1 Ω/500 µH; connection ramps in 10 µs at phase 0°/90°, plus 180°/270° in the precharge experiment. This is not a measured test source, LISN, contact bounce or IEC surge generator.
- Diodes are generic nonlinear forward fits with assumed `Is=1 nA, N=1.5, Rs=5 mΩ, Cjo=85 pF`; they are **not a manufacturer GBJ2510 model**. Reverse recovery, temperature, MOV conduction, line switch dynamics, fuse action, inductor saturation and core loss are absent. The model cannot certify component stress or fuse coordination. Missing MOV behavior may change bus peaks and transfer energy into the MOV; it is not a reason to assume the peak disappears safely.
- The load starts at 40 ms. Conductance law is `Pcmd*Vbus/Vrms²`. Diagnostic CPL is `min(30 A, Pcmd*Vbus/max(Vbus²,60²))`, clipped to zero for negative voltage. The algebraic CPL law has instantaneous response; a real regulator has finite bandwidth. Diagnostic burst is 50 Hz, 50% duty with ideal command edges. These are failure probes, not nominal predictions, deployed firmware or a measured pan envelope. No small-signal converter impedance or closed-loop stability proof is supplied. The ±10% capacitor sensitivity scales film values together, including bus film; it is not the selected parts' independent tolerance distribution.
- The standalone DM line model excludes switching-node/chassis/coil capacitances and both-leg fast parasitics. D17 exported fresh native19 copper, but no solved new A/B matrix was available to this workstream at report time. Cooling proposes PE-bonded sink and live-side shims over 1 mm AlN; actual overlap, dielectric data, thickness tolerance, edge fields and PE/harness inductance are not frozen. **No new RF attenuation or emissions margin is asserted.**

## Component and construction follow-through

Fresh primary-source checks on 2026-10-04 confirm the selected choke's 20 A rating refers to 60°C/50 Hz; its 18 µH leakage and 4.5 mΩ per winding are typical +20°C figures. The manufacturer gives low-level inductance conditions, not a hot pulsed-current loss guarantee. Retain the supplier/measurement gate; the 8 W filter heat allocation fails for several diagnostic load laws. [TDK B82726S22*3, pp. 4–6](https://product.tdk.com/system/files/dam/doc/product/emc/emc/line-filter/data_sheet/30/db/ind_2008/b82726s22x3.pdf).

The selected AC05 is rated 5 W at 40°C and 4.7 W at 70°C. Its flameproof coating is not proof of safe sustained overload or a defined fusing action. The actual pulse shape, repetitive energy, mounting and temperature require qualification. [Vishay AC family, pp. 1, 8–9](https://www.vishay.com/doc?28730=).

TDK's capacitor current curves are sinusoidal-frequency limits with specified ambient/ESR conditions. Apply the actual current spectrum and thermal rise, including the new low-frequency interaction, rather than comparing total RMS to a single high-frequency chart point. No capacitor thermal pass is claimed. [TDK B3292*C/D, pp. 13–14](https://product.tdk.com/system/files/dam/doc/product/capacitor/film/emi/data_sheet/20/20/db/fc_2009/x2_b32921_928.pdf).

The GBJ2510 350 A single-half-sine surge and 510 A²s/8.3 ms figures do not establish repetitive inrush life. A simulated non-sinusoidal 40 ms source I²t is not directly comparable: it includes currents into X capacitors that bypass the bridge and uses a different waveform/temperature. Do not mark the bridge protected from this table. [Diodes GBJ2510, p. 2](https://www.diodes.com/datasheet/download/GBJ2510.pdf).

KLDR020 retains its 12 s minimum at 200% current; 20 A is not a 15 A limiter. Its high-fault-current total-clearing figure is not the complete lower-current coordination curve. Preserve the [previous inlet proposal](../../../../../docs/research/mit-product-design/readiness/power/emi-closure/inlet-integration.md) as a candidate and obtain actual prospective-current, wire, switch and assembly withstand evidence. This round grants no coordination pass. [Littelfuse KLDR, pp. 4–7](https://www.littelfuse.com/assetdocs/kldr-classcc-fuse-datasheet-final?assetguid=8f8c3052-d0e1-411d-9a86-62bff0e1cf9a).

Cooling received the verified no-cover Schurter drawing: 34×26 mm cutout with +0.2/0 tolerance, 1–4 mm panel, 36×29 mm bezel, conservative 33.8×26 mm body, 33.5 mm rear depth plus 10.6 mm terminal projection. **21.3 mm is terminal spacing, not body width.** The 20 A table lists typical 5.2 mΩ/pole (1.17 W/pole at 15 A), not a hot assembly bound. Exact crimp/boot/bend envelopes remain additional. [Schurter TA35, pp. 3, 7](https://www.schurter.com/en/datasheet/typ_TA35_Rocker_2Pole.pdf).

## Integration handoff

1. Keep power PCB and filter release on HOLD until the actual line-dependent control law, pan envelope and startup function are coupled. Do not increase the damper/fuse rating to hide a diagnostic failure.
2. Keep probe access to bus voltage and provide an input-current measurement plan. Enforce the 15 A RMS input allocation over line/control modes; bus/tank trip thresholds alone do not establish that input limit. Their measurement windows and control behavior need design.
3. Design a pulse-rated precharge/bypass function before the filter, including fail-open/fail-closed relay, welded contact, power interruption, reclose, and resistor overtemperature. The experimental 10 Ω result is useful starting evidence. No board footprint or relay has been selected here; retain an explicit interface reservation rather than routing an unsupported circuit.
4. Reserve inlet fuse/holder/switch and connector/service space separately from the 110×80×50 mm filter. Keep PE unswitched/unfused with a dedicated bond. Sink/AlN/live-shim construction requires electrical isolation review and a new CM coupling model.
5. Recompute switched RF source/receiver interaction after new A/B extraction and actual assembly coupling are available. Close hot choke/capacitor/damper data, fault coordination and physical LISN/thermal/discharge tests on the first guarded unit before siblings.

## Reproduction

From the worktree root, run `sh zapote/power-stage-120v/prototype-closure/round2/d22/run.sh`. It checks pinned source/model inputs, builds a standalone Rust runner with `rustc`, runs five tests, and creates a fresh output directory. It does not build shared PyO3 crates or modify upstream evidence. Expect approximately 1.5 GB of text waveforms. `STATUS=SIMULATED_DIAGNOSTIC_ONLY` means numerical completion only. A missing vector, malformed/nonfinite/truncated trace, changed deck in explicit replay mode, wrong ngspice version, or failed convergence cannot produce that status.

The first exploratory run rejected duplicate rounded timestamps because ngspice's default output precision was too short. The deck now sets 15 digits; the parser retained its monotonicity check. `run01` is incomplete and `run02` predates the precharge experiment; use `run03` and this manifest only.

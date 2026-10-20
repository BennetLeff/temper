# Current Rev C fixed-local feedback validation

The manufacturing circuit uses one local100 pF capacitor on all three ranges. **Fixture limit and Rev D candidate: see `fixture-envelope.md`** (100 Ω range fails 45° above about 300 pF per DUT terminal; a 22 Ω LO isolation resistor restores ≥55°). Current evidence is `matrix-final_fixedgrid.md` (42cases), `matrix-final_fixedcorners.md` (84pairedcorners), `matrix-final_fixedlead.md` (48lead cases), `matrix-final_fixedfda.md` (12FDA differential/CM port checks), `matrix-final_fixedinvariance.md` (8bridge cases), `internal-loops-fixed.md` (15internalGM cuts), and `fixed-summary.md`. The fixed grid includes5nH local-CF lead and100nH RF-jumper lead; separate extremes test0/10nH local and0/100nH RF. Final100kΩ coil cases use19200points/decade to resolve narrow return trajectories. These are sensitivity assumptions, not extracted parasitics.

`sh run.sh --check` reanalyzes saved arrays, verifies trueDC, all crossings, completeness, expected negative historical controls, bridge invariance, and the analytic oracle. `--full` reruns the simulations with unmodified vendor models and deterministic declaration-order conditioning. It can take substantial time. Generated `*-order*` files record initialization attempts, not alternate circuits; accepted order/deck/data are separately named. Original models remain in `sources/ti/models`.

Everything below describes retained development evidence. The names `final` and `rev_c` predate the last compensation correction and do not by themselves identify the manufacturing circuit. Only the `fixed*` studies above match its local100pF TIA network; the FDA network is unchanged from the immediately preceding studies.

---

# Coupled-chain return-ratio evidence

This directory contains the actual final-network loop tests and labelled exploratory history. The active final topology is `final-template.cir`: retained TI AFE with100pF/10pF/5pF range compensation, and FDA22Ω-before-takeoff/1kΩ||100pF/4.32Ω network. Official vendor models are included by relative path and remain unmodified. The final solver helper and true-DC seed live in `../solver-resolution-rev-c-final/`.

## Accepted model evidence and explicit negative control

- `matrix-final_grid.md`:42 range/load/fixture cases.
- `matrix-final_corners.md`:84 paired R/C/supply corners.
- `matrix-final_lead.md`:84 nominal20nH/50nH feedback-path stresses. **The100Ω+50nH envelope fails the45° criterion**, motivating a compact selector layout. It is retained as a negative control, not called an accepted envelope.
- `matrix-final_compact.md`:32 low-range10/15/20/25nH combined-corner cases.20nH minimum45.43°;25nH can fall below45°.
- `matrix-final_fda.md`:two differential FDA loops and conditional external common-mode-port checks on each range. The latter do not measure the internal common-mode servo's margin.
- `internal-loops-final.md`:15 independent ideal-controlled-source cuts covering source, source follower, HIGH follower, LOW follower and TIA on each range.
- `matrix-final_invariance.md` and `bridge-invariance-final.md`:32 actual1/10/100/1000Ω bridge runs, with explicit DC and finite-precision limitations.
- `return-ratio-oracle/`:analytic stable/unstable/multiple-crossing regressions and an independent SPICE bilateral fixture.
- `final-summary.md`:complete-count, crossing-angle and AC-mesh checks. It asserts the expected50nH low-range failure rather than suppressing it.

`final_*` files contain successful final-network analyses, but a successful simulation does not mean every circuit variant meets the margin criterion. `final_damp`, `final_cflead`, `final_series` and `final_local` are **rejected compensation explorations**; none is in the BOM. Files without the `final_` prefix are historical diagnosis/preceding-FDA topology and must not be transferred to the manufacturing target.

## Method and reproduction

`loop_matrix.rs` uses two current injections, finite-bridge de-embedding and the bilateral Tian return ratio. It keeps all actual FDA DC bias currents and upstream amplifier loading. Its explicit operating-point guards reject false internal MID references, AC-input DC offsets, nonfinite arrays, incomplete sweeps and aborted analyses. Each accepted declaration order is recorded. The reordered circuit preserves every physical component line exactly; only numerical matrix ordering changes. `.nodeset` guesses are released during Newton solution. No transient-OP fallback is accepted.

The coil cases use4800 AC points/decade from1Hz to1GHz to resolve narrow multiple-crossing features. Other cases use120 points/decade; internal controlled-source cuts use240. The summary checks adjacent return-difference phase steps below30°. That sampled criterion cannot exclude every unresolved hidden feature, so no unconditional pole-count/Nyquist proof is claimed. All crossings and their directions remain in the raw CSVs.

```sh
sh run.sh --check  # validate delivered data and method regressions
sh run.sh --full   # regenerate final full-chain sweeps, then check them
```

Requires Rust and ngspice45.2 with KLU/PSpice compatibility. `NGSPICE` may override the executable path. The measured platform is macOSarm64; solver behavior on another version is not guaranteed. Compiler outputs are temporary. Failed initialization trials are retained for diagnosis; their failure is expected. KLU small-signal noise analysis is unsupported and is not part of this validation.

The physical feedback-inductance assumption, final layout and pre-order disposition are documented in `../../docs/analog-validation-rev-c.md` and the independent geometry receipts. Typical-model margins and bounded transients support a prototype, not guaranteed hardware performance.

The additional `matrix-final_leadwide.md` contains 28 nominal 100 nH feedback-lead cases on the 5 kΩ and 100 kΩ ranges. `final_cfcompact` is a rejected exploratory sweep: changing low-range CF among 56/68/82/100/120/150 pF did not establish robust 25–50 nH acceptance. Its results are retained, but do not change the selected 100 pF value.

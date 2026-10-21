# Rev E codec front end and range relays

`codec-template.cir` is the Rev E front end ([design](../../docs/rev-e-front-end.md)): the OPA810 difference stage driven by the TAC5112 DAC, the retained TIA core, and four 1k/1k, 560 pF, 1 µF, 470 Ω legs into 40 kΩ codec inputs. It replaces the FDA/ADS9224R chain. `codec-seed.inc` holds its DC seed. All cases carry the Rev D extracted board string (`_revd_risolo22`). The relay cases follow [range-switching §6](../../docs/rev-e-range-switching.md). Criterion: every downward crossing ≥ 45°; reference floor Rev D as built, 51.3° and |1+T| ≥ 0.573.

| Mode | Cases | Worst phase margin | Min. abs(1+T) | Verdict |
|---|---:|---:|---:|---|
| `codecbase`: codec load, jumpers (no relays) | 64 | 51.30° | 0.573 | equals Rev D: the codec network loads TIA_OUT like the FDA did |
| `fixedrelay`, nominal parasitics | 64 | 48.64° | 0.536 | passes |
| `fixedrelay`, stress parasitics | 64 | **38.48°** | 0.422 | **fails**; every range at 38–42° |
| `fixedrelay`, attribution (one stress value at a time) | 18 | 44.81° (TIA_OUT pad copper 10 pF) | 0.495 | dC −3.8°, Ccc −2.2°, Cpp −1.3°, Coc −0.8°, L_rel and Rc ≈ 0 |
| `fixedrelayrout22`: relay bus behind 22 Ω, stress | 64 | 41.81° | 0.467 | rejected (nominal 49.29°) |
| **`fixedrelaycng100`: + 100 pF C0G, DUT_LO to ground**, nominal | 64 | 59.95° | 0.665 | passes |
| same, stress | 64 | **55.97°** | 0.608 | passes, above the Rev D floor |
| same, attribution / weld | 18 / 3 | 58.45° / 59.78° | 0.642 / 0.665 | passes |
| same, `drive` / `high` / `low` loops (stress) | 4 each | 48.29° / 57.23° / 57.87° | 0.563 / 0.704 / 0.718 | passes; `drive` is the lowest margin left |
| `codecbasecng100`: the capacitor without relays | 64 | 60.95° | 0.685 | reference: what the capacitor gives alone |

**Mechanism and fix.** The relays add capacitance at TIA_OUT: pad copper, contact-to-coil capacitance, and pole-to-pole capacitance to SOURCE_BUF. With C104 = 100 pF and only a few pF at the summing node, the TIA feedback factor is near 1, so it crosses over near 60 MHz, where the OPA2810's output resistance and that load add phase lag. A fixed 100 pF from DUT_LO to ground, ahead of R_iso, lowers the high-frequency loop gain. This is the same noise-gain shaping that the fixture strays already provide (the `stray100` cases gave about 75°). The fixture strays then add to it.
- **Why DUT_LO and not TIA_SUM.** DUT_LO is a virtual ground sensed by the LOW follower, so the capacitor carries only the TIA's error voltage. The error it causes is linear, the same as fixture stray, and the three-standard calibration removes it.
- **Noise.** The capacitor changes no noise row at two significant figures (`../rev-e-codec/`, transfer `riso22_lo100`).
- **Rejected alternatives.**
  - Isolating the relay bus behind a resistor (`fixedrelayrout<R>`): the bus capacitance then loads the RF path instead, which only buys 3°.
  - Spot checks of other C104 values and a larger R_iso, not committed, did not restore 45° either.

**Still guessed.** The stress values of Ccc, Cpp, L_rel and dC are estimates (range-switching §6). Re-extract after the relay layout and rerun `fixedrelaycng100` with extracted values.

Run one mode with `$LCR_LOOP_BUILD/matrix final_<mode>`. Set `SHARD=i/n` to split it across processes; each shard writes `matrix-final_<mode>-shard{i}of{n}.md`. Concatenate the table rows in shard order to get `matrix-final_<mode>.md`.

---

# Current Rev C fixed-local feedback validation

The manufacturing circuit uses one local100 pF capacitor on all three ranges. **Fixture limit and Rev D candidate: see `fixture-envelope.md`** (100 Ω range fails 45° above about 300 pF per DUT terminal; a 22 Ω LO isolation resistor restores ≥55°; with extracted board parasitics the floor is 51.7°). Current evidence is `matrix-final_fixedgrid.md` (42cases), `matrix-final_fixedcorners.md` (84pairedcorners), `matrix-final_fixedlead.md` (48lead cases), `matrix-final_fixedfda.md` (12FDA differential/CM port checks), `matrix-final_fixedinvariance.md` (8bridge cases), `internal-loops-fixed.md` (15internalGM cuts), and `fixed-summary.md`. The fixed grid includes5nH local-CF lead and100nH RF-jumper lead; separate extremes test0/10nH local and0/100nH RF. Final100kΩ coil cases use19200points/decade to resolve narrow return trajectories. These are sensitivity assumptions, not extracted parasitics.

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

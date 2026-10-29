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

**Still guessed.** The stress values of Ccc, Cpp, L_rel and dC are estimates (range-switching §6). Re-extract after the relay layout and rerun `fixedrelaycng100` with extracted values. Done: see `reverelaycng100` below; the board part is now extracted, the relay-internal values are still estimates.

## Rev E extracted board (`reverelaycng100`)

`reverelaycng100` is `fixedrelaycng100` re-run on the Rev E layout extraction (`../layout-parasitics/README-rev-e.md`, board `2f6486c4…`) instead of the Rev D board and its leads.

- **Board model.** Every extracted board capacitance of 1 fF or more is a SPICE element on the harness nodes: sum, low, tia, hi, lowbuf, highbuf, source, and the unselected-branch nodes ru{k} and rgu{k}. They come from `reve_extracted.rs`, which `assemble_reve.py` generates.
  - TIA_OUT carries all of its copper, relay pads included, so `dc = 0`.
  - SOURCE_BUF board copper to GND and to DUT_HI is new. It was not modelled before.
- **Inductance.** The RF lead is the extracted free-space value (64.93 / 64.41 / 92.44 nH) plus the unchanged L_rel. The C104 lead is 5.04 nH, plus a 10 nH stress case.
- **Relay-internal estimates.** Coc, Ccc, Cpp, L_rel and Rc keep their NOMINAL/STRESS values.
- **Corners.** The nominal relay set runs on the nominal board (`_bnom`). The stress set runs on the high board (`_bhigh`).
- **Unchanged elements.** The 100 pF DUT_LO capacitor and R_iso 22 Ω are kept.
- **Reproduce.** `matrix final_reverelaycng100`, then `python3 reve_summary.py matrix-final_reverelaycng100.md`. 257 rows. All crossings are downward.
- **Baseline.** `fixedrelaycng100` was re-run in the same session and reproduced its committed table exactly.

| Loop (worst case) | `fixedrelaycng100` (estimates) | **`reverelaycng100` (extracted)** | Verdict |
|---|---|---|---|
| TIA, nominal set, 64 cases | 59.95° / 0.665 | **60.88° / 0.673** | passes |
| TIA, stress set, 64 cases | 55.97° / 0.608 | **58.10° / 0.628** | passes; extracted TIA_OUT ≤ 14.6 pF < 10.53 + 10 pF allowance |
| TIA, weld (two relays closed) | 59.78° / 0.665 | 60.69° / 0.675 | passes |
| `high` follower, stress, 6 cases | 57.23° / 0.704 | 56.34° / 0.695 | passes |
| `low` follower, stress, 6 cases | 57.87° / 0.718 | 56.35° / 0.691 | passes |
| **`drive` (source driver X6A), stress, 6 cases** | 48.29° / 0.563 | **38.46° / 0.451** (100 Ω, open, stray 0; 5 k / 100 k: 41.6–42.2°) | **FAILS 45°** |
| `drive`, nominal relay set + nominal board | — | 47.87° (100 Ω) / 51.40–51.46° (5 k, 100 k) | passes; 100 Ω is below the 51.3° Rev D floor |

**Attribution, `drive` loop, 100 Ω, open DUT, stray 0** (`reverelay_loops_drv*` rows):

| Relay set / board | Margin |
|---|---|
| stress / high | 38.46° |
| nominal / high | 45.06° |
| stress / nominal | 41.38° |
| nominal / nominal | 47.87° |
| stress / high, with every board capacitor on SOURCE_BUF removed | 46.39° |

Two things together pull the loop below 45°:

- **SOURCE_BUF board copper costs 7.9°** at the stress corner: 13.2 pF to GND and 3.0 pF to DUT_HI at the high corner. It is an 80 mm route: U6 → In2 down x 188.8 → a 36 mm bus at y 129.6. It also runs broadside over DUT_HI on B.Cu.
- **The relay stress capacitances on SOURCE_BUF cost 6.6°**: Ccsel_s 5 pF, Cpp 2 pF and Cocs 2 pF. These are unverified estimates.

Neither alone fails. The 100 Ω range is worst because DUT_HI (10 pF to GND) loads the driver through only 100 Ω of RG. Even with all the board copper removed, the stress set gives only 46.4°. Shortening the route alone therefore cannot restore the old 48°.

**Proposed fix (not implemented in CAD).** Fit a 0603 isolation resistor of **47 Ω** between U6A's output/feedback node and the SOURCE_BUF route:

- U6.1 and U6.2 stay tied at the pin.
- The resistor goes before the via at (169.66, 88.96).

Results with the resistor (`_srciso47` rows):

- **`drive` at stress / high: 47.33° / 47.38° / 47.24°** (100 Ω / 5 k / 100 k).
- With 1000 pF stray: 51.65° / 47.38° / 47.24°.
- Nominal / nominal: 50.29°.
- The TIA loop is unchanged at 58.16°, and the followers are unchanged.

Smaller resistors are not enough: 22 Ω gives 43.1°, and 10 Ω gives 40.6°.

**Cost of the fix.** The resistor adds 47 Ω in series with RG:

- On the 100 Ω range the source resistance rises from 100 to 147 Ω.
- That lowers the maximum DUT current and the drive headroom.
- Accuracy is unaffected, because DUT_HI is sensed by HIGH_BUF and the current by the TIA.

**Better long-term fix.** Bench-measure the TQ2SA Ccc and Cpp, which are the stress values driving the other 6.6°. Also shorten SOURCE_BUF by placing U6A's output near the relay row, or un-stacking it from DUT_HI.

### As-built R104 board (`reverelaycng100_r104`)

Board `cf379f85…`, commit a04880a87, extracted as `reve_r104` (`../layout-parasitics/README-rev-e.md`). R104 is fitted and SOURCE_BUF is un-stacked from DUT_HI.

**Topology.** X6A output and feedback node → C(SRC_DRV) → R104 47 Ω → SOURCE_BUF bus. The bus carries C(SOURCE_BUF board), RG, the relay contact capacitances, and the coupling to DUT_HI, now 0.23 pF high (was 3.0).

- **Harness mechanics.** The case names carry `_r104_srciso47`. Board elements on SOURCE_BUF land on `srcbus`; SRC_DRV elements land on the X6A node.
- **Unchanged.** Everything else is as in `reverelaycng100`.
- **Size.** 206 rows. All crossings are downward. Reproduce with `matrix final_reverelaycng100_r104`, then `python3 reve_summary.py matrix-final_reverelaycng100_r104.md`.

| Loop (worst case, PM / min abs(1+T)) | `fixedrelaycng100` (estimates) | `reverelaycng100` (`2f6486c4`, no R104) | **`reverelaycng100_r104` (as built)** |
|---|---|---|---|
| TIA, nominal set, 64 cases | 59.95° / 0.665 | 60.88° / 0.673 | **60.88° / 0.673** |
| TIA, stress set, 64 cases | 55.97° / 0.608 | 58.10° / 0.628 | **58.07° / 0.629** |
| TIA, weld | 59.78° / 0.665 | 60.69° / 0.675 | **60.69° / 0.676** |
| `drive`, stress / high board, 6 cases | 48.29° / 0.563 | 38.46° / 0.451 | **46.77° / 0.590** (100 Ω, stray 0; 5 k / 100 k 47.0–47.2°; 51.42° at 1000 pF on 100 Ω) |
| `drive`, nominal / nominal | — | 47.87° / 0.563 | **49.80° / 0.622** (100 Ω); 52.33–52.37° (5 k, 100 k) |
| `high`, stress | 57.23° / 0.704 | 56.34° / 0.695 | **56.49° / 0.699** |
| `low`, stress | 57.87° / 0.718 | 56.35° / 0.691 | **56.34° / 0.691** |

**Every loop passes 45°.** The `drive` loop still sits below the 51.3° Rev D floor.

**What is left on the `drive` loop, 100 Ω range, open DUT, stray 0 (stress relays / high board = 46.77°):**

| Change | Margin |
|---|---|
| nominal relays, high board | 48.62° |
| stress relays, nominal board | 47.30° |
| board capacitors on SOURCE_BUF removed (SRC_DRV kept) | 49.22° |

The remaining sensitivity is in the relay contact-capacitance stress estimates (Ccc, Cpp, Coc on SOURCE_BUF), which are UNVERIFIED. Bench-measure them before relying on the last 2°.

### Four-terminal BNC board with K4 reference relay (`kelvincng100`)

Board SHA-256 `80d44838…`, uncommitted at extraction time, extracted as `reve_bnc` (`../layout-parasitics/README-rev-e.md`). R104 stays fitted.

**Topology.**

- **Followers.** The HIGH and LOW followers now sense through the POT terminals. The `_kelvin` tag moves X6B +IN to `hpot` and X7B +IN to `lpot`, and the follower loop break moves with them.
- **Resistors.** R105 (1 k, HCUR–HPOT), R106 (1 k, LCUR–LPOT) and R107 (1 k, REF_A–LCUR) are in the netlist.
- **K4.** Ccc to ground on each side. When open, Coc spans HCUR–REF_A. When closed, Rc + L_rel spans the same pair (`k4_netlist`).
- **Board strays.** From `reve_bnc_extracted.rs`.

**Grid.** Every case runs four loops: TIA, drive, HIGH and LOW.

- **Relay sets.** Nominal relays on the nominal board (caplead 5.04 nH). Stress relays on the high board (caplead 10 nH).
- **DUTs.** Open, short and matched on all three ranges, plus `coil50u` on the 100 Ω range.
- **Fixtures.**
  - `nocable`.
  - `coax1m`: four 1 m RG-58 leads, each 101 pF / 252.5 nH, lossless, in 20 sections, shield at board ground. HCUR and HPOT meet at the DUT high node; LCUR and LPOT meet at the DUT low node.
  - `cur`: lumped HCUR/LCUR stray. 100 / 220 / 470 / 1000 pF on the 100 Ω range; 1000 pF on 5 k and 100 k.
  - `k4closed`: K4 closed, leads unplugged, DUT open, on each range.

360 rows, run as `SHARD=i/4` and concatenated.

**Result: every loop passes 45° in every case.** Columns are worst PM / min abs(1+T).

| Loop | `reverelaycng100_r104` | **`kelvincng100`, worst** | Worst fixture | No-cable / `cur` / K4 closed (stress) |
|---|---|---|---|---|
| `drive`, stress | 46.77° / 0.590 | **46.83° / 0.588** | coax, 100 k short | 46.85° / 46.84° / 46.85° |
| `drive`, nominal | 49.80° / 0.622 | **50.29° / 0.615** | no cable | coax 51.75°, `cur` 52.11°, K4 50.74° |
| TIA, stress | 58.07° / 0.629 | **57.21° / 0.491** | coax, 100 Ω short | 60.02° / 70.45° / 59.92° |
| TIA, nominal | 60.88° / 0.673 | **59.82° / 0.588** | coax | 62.37° / 71.22° / 62.74° |
| `high`, stress | 56.49° / 0.699 | **57.05° / 0.610** | coax, 100 Ω matched | 57.78° / 57.78° / 57.80° |
| `low`, stress | 56.34° / 0.691 | **55.89° / 0.643** | coax, 100 Ω matched | 56.90° / 56.89° / 56.90° |
| `high` / `low`, nominal | — | 57.27° / 56.64° | coax | ≥ 57.55° |

**Effect of the Kelvin re-layout.**

- **Without a cable** it changes nothing material: `drive` gains 0.06° and the followers gain about 1.3° and 0.6°.
- **The 1 m cable set costs** 2.8° on TIA (stress) and 1° on LOW. TIA min abs(1+T) falls to 0.49.
- **The lumped `cur` stray raises TIA margin** to 70–71°. It is not the worst case for any loop.

**K4 closed, leads unplugged.** Stable on every range. Worst margins are `drive` 46.85° (stress) / 50.74° (nominal), TIA ≥ 59.92° and followers ≥ 56.90°.

**Multiple crossings with the cable.** Ten TIA `coax1m` rows cross unity three times: down at about 13–20 MHz (90–141°), up at 14–25 MHz, then down again at 41–42 MHz (58–68°). An example is r100 open, stress: 19.72 MHz / 92.3° down, 23.67 MHz / 111.3° up, 41.49 MHz / 58.25° down, min abs(1+T) 0.500.

`kelvin_summary.py` scans every `<name>_return.csv` for crossings of the negative real axis left of −1 and finds **0 in all 360 rows**. The extra unity crossings therefore cannot encircle −1. The table PM is the worst downward crossing.

**Caveats.**

- The BNC jack capacitance (1.5–3.5 pF) and the K4 Coc/Ccc values are estimates.
- The cable is lossless and the shield is ideal.
- The board file was uncommitted at extraction time.

**Reproduce:**

```
$LCR_LOOP_BUILD/matrix final_kelvincng100
python3 kelvin_summary.py matrix-final_kelvincng100.md
```

The `kelvin_summary.py` check needs the `_return.csv` files from a `--full` run. `run.sh --check` re-analyses existing outputs.

Run one mode with `$LCR_LOOP_BUILD/matrix final_<mode>`. Set `SHARD=i/n` to split it across processes; each shard writes `matrix-final_<mode>-shard{i}of{n}.md`. Concatenate the table rows in shard order to get `matrix-final_<mode>.md`.

---

# Current Rev C fixed-local feedback validation

The manufacturing circuit uses one local100 pF capacitor on all three ranges. **Fixture limit and Rev D candidate: see `fixture-envelope.md`** (100 Ω range fails 45° above about 300 pF per DUT terminal; a 22 Ω LO isolation resistor restores ≥55°; with extracted board parasitics the floor is 51.7°). Current evidence is `matrix-final_fixedgrid.md` (42cases), `matrix-final_fixedcorners.md` (84pairedcorners), `matrix-final_fixedlead.md` (48lead cases), `matrix-final_fixedfda.md` (12FDA differential/CM port checks), `matrix-final_fixedinvariance.md` (8bridge cases), `internal-loops-fixed.md` (15internalGM cuts), and `fixed-summary.md`. The fixed grid includes5nH local-CF lead and100nH RF-jumper lead; separate extremes test0/10nH local and0/100nH RF. Final100kΩ coil cases use19200points/decade to resolve narrow return trajectories. These are sensitivity assumptions, not extracted parasitics.

`sh run.sh --check` reanalyzes saved arrays, verifies trueDC, all crossings, completeness, expected negative historical controls, bridge invariance, and the analytic oracle. `--full` reruns the simulations with unmodified vendor models and deterministic declaration-order conditioning. It can take substantial time. Generated `*-order*` files record initialization attempts, not alternate circuits; accepted order/deck/data are separately named. Original models remain in `sources/ti/models`.

Everything below describes retained development evidence. The names `final` and `rev_c` predate the last compensation correction and do not by themselves identify the manufacturing circuit. Only the `fixed*` studies above match its local100pF TIA network; the FDA network is unchanged from the immediately preceding studies.

---

# Coupled-chain return-ratio evidence

This directory contains the actual final-network loop tests and labelled exploratory history. The active final topology is `final-template.cir`: retained TI AFE with100pF/10pF/5pF range compensation, and FDA22Ω-before-takeoff/1kΩ||100pF/4.32Ω network. Official vendor models are included by relative path and remain unmodified. The final solver helper and true-DC seed live in `../solver-resolution-rev-c-final/`.

## Source stage, 280 pF as two 560 pF (`source_stage.py`, 2026-10-29)

`source_stage.py` breaks the U5 (OPA810) difference-stage loop with the same bridge-injection return ratio as `loop_matrix.rs`; it first reproduces the committed `codecbase` TIA row (19.5149 MHz / 95.04°). C34/C35 270 pF → C34+C114 and C35+C115, 2 × 560 pF C0G in series (280 pF), with 0.5 pF midpoint stray and 1.5 nH per part: phase margin 59.73° (60.13° before; 58.74° at 2 pF / 3 nH stress). Source gain at 85 kHz −0.025 dB / −0.56°, under 0.003 dB at 27 kHz; V and I share the source, so it cancels in Z. Common-mode rejection at ±5 % capacitor corners: −37.4 dB at 85 kHz (−37.7 dB with 270 pF). Output: `source_stage.json`.

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

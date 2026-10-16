# Candidate 46: rail-monitor ICs on 125 °C grades, built as stage 46 (native21s46)

**Verdict: card REJECT against s45, but the B3 rows that reject it are the hot-copper model, not this change.** The s45
card was scored before the hot-copper lane (OPEN-ITEMS S17) merged. On hot copper, s45 itself reads release **−17.9 K**
(U29 LM339BIDR against its 85 °C TA limit; integrator run `runs-native21/s45/c45hot`). s46 reads **−0.7 K**, bound by the
R10 2512 terminal derating. The monitor ICs are no longer the binding rows: the worst is U29 at +22.1 K against 125 °C.
Board native21s46 `7bfe8b76…`, copper identical to s45, chain CHAIN_DONE with no spine owner (SPINE_LOCK PASS).

```
REJECT native21s46 vs validation-results/10-benchmark/scorecard-native21s45.json: cheaper [], better []; b3_laminate_margin_K worse: -51.1 vs benchmark -30.2 (tolerance 1.0); b3_rated_part_margin_K worse: -51.3 vs benchmark -32.3 (tolerance 1.0); b3_release_margin_K worse: -0.7 vs benchmark 1.2 (tolerance 1.0); costlier on ['parts_usd_at_500_v2'] with no performance gain; neither cheaper/simpler nor better than the benchmark
```

Branch `claude/native21-s46-monitor-grades` from `4d9104a9e` (board of record s45 with the hot-copper B3 model). The
integrator decides (`DECISIONS-DRAFT.md`, item 62).

## 1. What changed (BOM only, 6 instances)

| Role | Designators | s45 | s46 | JLC (2026-10-15) | Stock / need at 500 | $ at need |
|---|---|---|---|---|---:|---:|
| `reference` (RailMonitor) | U17 / U19 / U21 | TL431BIDBZR (C41283) | **TL431BQDBZR** | C190245 | 17,789 / 1,500 | 0.0744 |
| `comparator` (RailMonitor) | U29 / U30 / U31 | LM339BIDR (C22416291) | **LM2901BIDR** | C22427890 | **1,966 / 1,500** | 0.1266 |

Source: `results/parts-s46.md` (`scripts/parts46.py`, from the cached JLC detail records in `scripts/jlc-raw`).

- **TL431BQDBZR** (TI SLVS543S): Table 6.13 p.14 gives the same Vref 2.483–2.507 V and VI(dev) 34 mV max as the BI
  grade; TA −40..125 °C (6.4 p.5); DBZ pinout 1 = K, 2 = REF, 3 = A (p.4), unchanged.
- **LM2901BIDR** (TI SLCS006Z): 6.8 p.8, VIO ±5.5 mV and IB 50 nA held over −40..125 °C; TA −40..125 °C (6.4 p.6);
  Table 5-1 p.4 is the LM339B pinout; orderable on p.28. `LM2901BQDR` does not exist (only LM2901BQDRQ1, 25 at JLC).
- **Buy LM2901BIDR early:** 1,966 at JLC against 1,500 needed.
- **Pads and nets:** both keep their footprints (SOT-23, SOIC-14). `default.net` differs from s45 only in the 4
  libsource / libpart lines naming the comparator; nodes and nets are unchanged. `default.csv` and
  `resolved-components.json` change in exactly the 6 instances.
- **Source:** `elec/src/f6_parts.ato` BiasComparator → LM2901BIDR, BiasReference → TL431BQDBZR (with docstrings). Built
  with atopile 0.2.69 offline plus `circuit_export.py`, refrozen to `frozen/` and `native-21/frozen/` (path normalised
  to `ps-integrate`).
- **Cost:** +$0.12 per board on the v2 (dated-read) pricing, 171.71 → 171.83. Lines stay at 94, Extended at 69.

### U5 (REF25) is not changed: no 125 °C part matches it (`scripts/ref25_46.py` → `results/ref25-s46.md`)

There is no LM4040A25Q. TI's 125 °C Q grades of the LM4040 are C and D only:
- LM4040C25QDBZR (±0.5 %, ±38 mV over the full range, SLOS456Q p.11): C2872469, **133** at JLC against 500 needed;
- LM4040D25QDBZR: 0 at JLC;
- the other TI 2.5 V shunts rated −40..125 °C in SOT-23-3 have ≤ 104 at JLC.

The C25Q would also degrade the bands it sets (control: the A25I mapping reproduces `ocp_band17.json` 69.89–116.44 A):
- OCP low corner 69.89 → 69.29 A. After the −2.123 A Kelvin shift that is 67.17 A, +3.00 A over the 64.17 A floor;
  64.63 A (+0.46 A) if the network runs at 105 °C.
- OVP upper corner 288.02 → **290.18 V (+2.16 V)**. That breaks the "OVP upper corner must not rise" rule that the D3,
  C5/C6 and ALT-BIAS ledger rows use against 286 V.

U5 stays LM4040A25IDBZR. Its S16 probe-sweep row (`b3-ratings/monitor-probes-2026-10-15/README.md`, report-only, not a
gate row) reads −4.5 K against 85 °C at the release case.

## 2. Bands on the 125 °C basis (`scripts/bands46.py` → `results/bands-s46.md`)

`bands46.py` reads the monitor MPNs and divider values from the freeze, asserts the evaluated parts are the frozen ones,
and runs the S16 study's `model.py` / `monitor_wc.evaluate` unchanged on a −10..125 °C range (100 K TCR excursion; s45
was −10..85 °C, 60 K). Two controls are asserted: **R1**, the s45 values at 60 K reproduce `c45/results/bands-s45.json`
to 1e-4; **R2**, the study's s43 values at 100 K reproduce its `sensitivity_dt['100K']` to 1e-4. The divider values
(1c-4420) are unchanged, and no re-centre is needed.

| Threshold | s45 worst case | s46 worst case | s46 RSS | Rail limit | Rail margin WC, s45 → s46 | RSS, s45 → s46 | s46 WC, rails hot too |
|---|---|---|---|---:|---:|---:|---:|
| neg UV (release ≤) | 1.8146–1.9044 | 1.8132–1.9059 | 1.8318–1.8871 | 1.9654 | +0.0610 → +0.0595 | +0.0783 → +0.0782 | +0.0580 |
| neg OV (trip ≥) | 2.1825–2.2942 | 2.1801–2.2967 | 2.2048–2.2716 | 2.0757 | +0.1068 → +0.1045 | +0.1293 → +0.1291 | +0.1029 |
| span UV (release ≤) | 15.5689–16.4788 | 15.5315–16.5182 | 15.7726–16.2703 | 16.575 | +0.0962 → **+0.0568** | +0.3103 → +0.3047 | +0.0302 |
| span OV (trip ≥) | 17.5692–18.5984 | 17.5266–18.6434 | 17.8000–18.3622 | 17.425 | +0.1442 → +0.1016 | +0.3815 → +0.3750 | +0.1016 |

Joint RSS is unchanged: span UV 6.0σ, span OV 6.4σ.

Catch side (Q = committed F6 qualification basis, H = hard ratings, target 0.5 % of the threshold):

| Threshold | Q catch s45 → s46 | H catch s45 → s46 | Verdict Q / H, s45 → s46 |
|---|---:|---:|---|
| neg UV | +0.0603 → +0.0589 | +0.3090 → +0.3077 | PASS / PASS → PASS / PASS |
| neg OV | +0.1058 → +0.1033 | +3.2058 → +3.2033 | PASS / PASS → PASS / PASS |
| span UV | +0.0689 → **+0.0315** | +3.2746 → +3.2348 | MARGINAL / PASS → MARGINAL / **MARGINAL** |
| span OV | −0.5984 → −0.6434 (18 V Q) | +2.4016 → +2.3566 | FAIL / PASS → FAIL / PASS |

- **Span UV H is MARGINAL on the rail side:** +0.057 V worst case, under the 0.080 V (0.5 %) target. This is the price of
  admitting 125 °C on the monitor islands (the band widens with the extra 40 K of TCR), not of the new parts.
- **Span OV** upper corner 18.643 V: against the 19 V hot-load re-run ceiling it is **+0.357 V** (was +0.402 V). The
  2EDR8259X VDD ratio is **0.888** of 21 V (was 0.886).
- **TL431BQ:** IK 5.612–7.342 mA over the operating span, 9.827 mA at the 24 V fault case (24.97 mW, 5.1 K self-heat).

## 3. B3 rows at the monitors (hot-copper BASIS, `b3-ratings/margins.json` on the s46 board)

The B3 gate's `MONITORS` rows now carry the grade of the part in the freeze: `MONITOR_GRADES` maps MPN → (kind, basis,
limit), `bom_mpns()` reads `native-21/frozen/default.csv`, and `probe_rows()` refuses an unknown or mismatched MPN.

| Ref | Part | c18 @ 61 °C est (release) | Margin vs 125 °C | Worst over BASIS |
|---|---|---:|---:|---|
| U29 | LM2901BIDR | 102.9 | +22.1 | c28: 106.0 / +19.0 |
| U31 | LM2901BIDR | 101.6 | +23.4 | |
| U30 | LM2901BIDR | 96.6 | +28.4 | |
| U17 | TL431BQDBZR | 92.7 | +32.3 | c28: 94.8 / +30.2 |
| U21 | TL431BQDBZR | 85.5 | +39.5 | |
| U19 | TL431BQDBZR | 82.0 | +43.0 | |
| U16 / U20 / U18 | TLVH431BQDBZR (unchanged) | 101.2 | +23.8 / +41.5 / +44.8 | |

On s45 (hot copper) the same islands were U29 −17.9 K and U17 −7.7 K against 85 °C. All monitor rows now clear.

**The release still fails, on copper rows:** release −0.7 K at c18 @ 61 (R10 2512 terminal derating, 132.6 vs 131.9 °C);
then R20 +2.7, R12 +3.2, R18 +4.0 K. Ratchet laminate −51.1, rated part −51.3, advisory −17.5 K. The `b3_ratings` gate
is FAIL. This is the tank-ceiling question for the integrator, not a monitor question.

## 4. Card (`10-benchmark/scorecard-native21s46.json`) and compare (`results/compare.txt`)

Every gate other than `b3_ratings` passes; `cu_temp_basis` is True (new on the card since s45). Fields that move
against the s45 card:

| Field | s45 card | s46 | Why |
|---|---|---|---|
| b3_release_margin_K | +1.2 | −0.7 | hot copper (s45 hot: −17.9) |
| b3_laminate / rated_part_margin_K | −30.2 / −32.3 | −51.1 / −51.3 | hot copper (s45 hot: the same) |
| b3_nominal_h10 / c28_h25 peak °C | 165.0 / 147.2 | 171.3 / 163.6 | hot copper |
| parts_usd_at_500 (legacy) / v2 | 201.60 / 171.71 | 201.31 / 171.83 | the two new lines |
| ledger | 3 / 37 / 54 / 0 | 3 / 38 / 53 / 0 | LM2901BIDR is PARTIAL (LM339BIDR was UNAUDITED) |

Everything else equals s45: D5 8.047 / 8.507, RES_A 13.375, Kelvin 67.77, OCP pickup 4.17 A, fuse ratio 0.993, DFM
PASS 765, jet strip 1.72 mm, FIT 410 0 0 412 0, 94 BOM lines, 358 placements. There is no hot-copper s45 card to
compare like for like; against s44 and s43 the card is also REJECT on the same three B3 fields.

## 5. Copper and placements are identical to s45

- **Geometry** (`results/geom-s45-s46.json`, s45 `26ce9531` against s46 `7bfe8b76`): footprints, pads, tracks, arcs,
  vias, zone outlines and Edge.Cuts identical. Only 6 field changes: U17 / U19 / U21 and U29 / U30 / U31 `Value` / `MPN`.
- **`copper_key.py`:** `d33d77ac…`, the same as s45 and s45hot.
- **`fill_hash.py`:** area hash `39fe161d` on both, symmetric difference 0.0967 mm² (worst 0.0286 mm², F.Cu / n_ls;
  `results/fill-hash-s45-s46.txt`).
- **`track_cleanup21.py`:** 0 edits (`results/cleanup-s46.json`). `s46_necks.json` and `coil-pickup/s21b/result-s46.json`
  equal s45's apart from hashes (0.993, 4.17 A).
- **Task 04 / B3 outputs:** re-solved on this board. The B3 `outputs/` files committed at the base were the cold-copper
  solve; these are the hot-copper solve (`copper_temp_model: hot-iterated`), which is why the peaks move.

## 6. Source checks, CPL, ledger and sourcing

- **`audit.rs`:** 6 IDENTITY entries move. The s45 audit on the new freeze fails on exactly those 6. New test
  `stage46_monitor_grades_hold`. **88 / 88** tests; PASS on `build/` and both frozen copies.
- **`verify_source.py`:** asserts monitor MPN and footprint (`source-check.json` PASS).
- **`pin_functions21.py`:** TL431BQDBZR gets the DBZ table; LM2901BIDR uses the LM339B table; a `QUAD_COMPARATORS` net
  check. `pin-functions21.json` regenerated (eco-pin-table for all 6).
- **CPL audit:** the EasyEDA records for C190245 / C22427890 were fetched (raw in `runs-native21/s46/ee-raw`) and
  distilled into `sources/easyeda-footprints.json`. `pin-evidence.json` and `pin-evidence-datasheets.json` gain both.
  C22427890 is settled on EasyEDA / DB footprint agreement, since its EasyEDA symbol has no pin names. Result: U17 / U19
  / U21 CORRECTED 180°, U29–U31 CORRECTED 270°; totals OK 284 / NEEDS-PREVIEW 31 / CORRECTED 32, unchanged.
- **Datasheet ledger** (`scripts/ledger46.py`, idempotent):
  - TL431BIDBZR → **TL431BQDBZR**, PARTIAL; B3 rows 92.7 / 94.8 °C against 125 °C.
  - LM339BIDR (UNAUDITED) → **LM2901BIDR**, PARTIAL: VS 18.64 / 36 V, VIN 1.783 / 13.531 V, IOL 0.505 / 25 mA, T 102.9
    / 106.0 °C against 125 °C.
  - 2EDR8259X "VDD at the span OV trip" → 18.64 V.
- **Ledger hot-copper refresh** (`scripts/ledger_b3_refresh46.py`, idempotent; applies to s45 equally):
  - The merged hot-copper lane re-solved `margins.json` but left **30 stale keyed B3 citations in 10 entries**; the
    ledger gate refuses them. This script moves each cited est_c to the margins.json row and recomputes the checks.
  - Derived ratings are re-derived on their own curves: CSS2H P allowed = 5 W × (170 − T) / 100; RC1206 derating
    0.25 × (155 − T) / 85. CSS2H c28 terminal 184.6 °C is past the 170 °C zero-power point, so that check now compares
    the terminal temperature with 170 °C (gap row).
  - CC1206JKNPOCBN102 / GRM1885C1H472JA01D: the FET-row copper bound used as their release check reads **126.1 °C > 125
    °C** on hot copper. The release check moves to the caps' own pad estimates (`scripts/cap_probes46.py`, the B3 gate's
    estimator): **116.7 °C (C20) / 120.3 °C (C56)** at c18 @ 61; the bound stays as a gap row. At c22 / c28 the pads
    read 131.1 / 171.0 and 135.5 / 177.4 °C (gap rows, airflow route).
  - `gate.py` PASS: 94 lines, 3 VERIFIED / 38 PARTIAL / 53 UNAUDITED / 0 VIOLATION. `tests/test_gate.py` 24 ok.
- **Sourcing:** `apply_lcsc.py` maps both MPNs; `STOCK-2026-10-13-addendum-s46.csv`; `study-2026-10-15/run_all.sh` s46
  step builds `snapshot/s46/` (earlier steps rerun byte-identical); `SNAPSHOT-2026-10-15.csv` re-keys 2 rows.
- **Other:** `native-21/ECO.md` note; `kelvin_budget.py` / `kelvin_plane.py` gain `native21s46` (OCP divider
  unchanged); `monitor_sweep.py` adapted to the new MONITORS shape; `test_b3_hot_copper.py` extended.

## 7. Tests (with `native-21/section.kicad_pcb` = the s46 board `7bfe8b76`)

| Test | Result |
|---|---|
| `audit.rs --test` | 88 / 88 |
| `verify_source.py` | PASS |
| `b3-ratings/test_b3_hot_copper.py` | 28 ok, 0 fail |
| `gates/test_cu_temp_basis.py` | 47 ok |
| ledger `tests/test_gate.py` / `gate.py` | 24 ok / PASS |
| `gates/test_track_geometry.py` | 7 / 7 |
| `gates/test_spine_lock.py` | 11 / 11 |
| `layout/test_track_cleanup21.py` | 45 / 45 |
| `gates/test_jet_strip_height.py` | 7 / 7 |
| `gates/scoped/test_scoped.py` | 16 / 16 |

## 8. Chain runs

```sh
R=/Users/bennet/Desktop/temper/worktrees/runs-native21/s46
cp runs-native21/s45/pass-j1/copper-dump.json $R/pass-j1/          # s45's pass (sha 3d07e4f3)
TASK04_WORKERS=4 sh native-21/layout/gates/chain.sh native21s46 $R/pass-j1 $R/c46     # CHAIN_DONE, board 7bfe8b76
python3 -I native-21/layout/gates/scorecard.py native21s46 $R/c46 --audit PASS --json validation-results/10-benchmark/scorecard-native21s46.json
python3 -I native-21/layout/gates/scorecard.py --card validation-results/10-benchmark/scorecard-native21s46.json \
    --compare validation-results/10-benchmark/scorecard-native21s45.json
python3 -I validation-results/11-candidates/c46-monitor-grades/scripts/bands46.py      # and ref25_46, parts46, cap_probes46
python3 -I validation-results/11-candidates/c46-monitor-grades/scripts/ledger46.py
python3 -I validation-results/11-candidates/c46-monitor-grades/scripts/ledger_b3_refresh46.py
```

Chain log `$R/chain46.log`: DRC 0, D5 8.047 / 8.507, RES_A 13.375, DFM PASS 765, Kelvin 67.77, ZIP `dc69389e…`.

## 9. Notes and limits

- **Mismatches found:**
  - no LM4040A25Q exists, so U5 stays on the 85 °C grade (section 1);
  - the B3 gate's advisory `MON_R` / `mon_volts` still use the s42 divider values (advisory only, negligible power;
    not changed here);
  - the 30 stale ledger B3 citations and the 126.1 °C cap bound came from the hot-copper merge (section 6).
- **Not done:** the FMEA C1–C7 re-run, the 15.5 V droop campaign at the span-UV corner (15.53 V), and JLC previews of the
  6 changed CPL lines.
- **Not edited:** DECISIONS.md, OPEN-ITEMS.md, firmware, and FAB-NOTE's board / Gerber SHA.
- **Not staged:** `fab/assembly-drawing.pdf`, `validation-plan/enclosure-fit/plan-result.json`, the datasheets
  (`runs-native21/s46/dl/`), `.npz` caches, and the untracked `native-21/section.kicad_pcb` copy.

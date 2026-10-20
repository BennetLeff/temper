# Stage 54: BOM integration record

Integration writer, 2026-10-19, worktree `ps-c54` (branch `claude/native21-s54-geometry`, base 19b948e13). This is
BOM-only work on the stage-52 recipe (`11-candidates/s52-proto-bom/README.md`). No copper edit: `native-21/layout/copper.json`
holds the lead's edit and was not touched. Not done here: commits, `chain.sh`, `passes.sh`, `datasheet-ledger/ledger.json`.

## 1. Changes (lead decisions)

| Refs | Stage 53 | Stage 54 | Source |
|---|---|---|---|
| R10 / R12 / R18 / R20 (`R68Gate2512`) | 25121WF680JT4E, 1 W (C50371) | **PS122WF680JT4E**, UniRoyal PS12 2 W (C2793964) | c54-release-margins |
| R71 / R72 / R74 / R75, R131 (`Bias4k99`) | 0603WAF4991T5E, 0.1 W (C23046, Basic) | **ERJ-PA3F4991V**, Panasonic (C4036134, Extended) | c54-release-margins |
| R44 / R45 (`r_ct_hi_bot`, `r_ct_lo_top`) | RT0603BRD0710KL, 10 k | **RT0603BRD0711KL**, 11 k (C728581, R35's line) | c54-ct-band patch 01 |
| C126–C129 | 6SVPC220MV | **unchanged** (16SVPK220M has 0 at JLC / LCSC) | lead |
| firmware | `TANK_PEAK_TRIP_MAX_A` 64.5 A | **62.5 A** | c54-ct-band patch 02 |

## 2. Files touched

**Source and frozen exports**

- `elec/src/parts.ato`: `R68Gate2512` takes the new MPN and docstring. The `R11kThin` docstring now names R44 / R45.
- `elec/src/f6_parts.ato`: `Bias4k99` takes the new MPN and manufacturer (Panasonic), plus a docstring.
- `elec/src/power_stage_120v.ato`: patch 01 (R44 / R45 on `R11kThin`, 11 kohm; the CT comment).
- `frozen/` and `native-21/frozen/`: `default.csv`, `default.net`, `resolved-components.json`. The pairs are byte-identical.
  - **Method.** `python3 tools/build_source.py <scratch>` (pinned offline atopile 0.2.69), then the scratch path is
    replaced by the frozen files' embedded `.../worktrees/ps-integrate/zapote/power-stage-120v` path.
  - **Control.** The same build on the unmodified 19b948e13 source reproduces the committed `default.csv` and
    `default.net` exactly after that substitution.
  - **Hashes.** `build_sha256` holds the scratch build's own hashes. The `supervisor.ato` `source_sha256` entry, which
    is in the committed file, is kept.
  - **What changed.** Only the 13 components change: MPN, manufacturer and value. There are 372 components, 187 nets,
    and the same number of BOM lines.
  - `default.layouts.json` and `manifest.json` are unchanged.
- `native-21/verification/verify_source.py` adds stage-54 asserts (R_on PS12, the ERJ-PA3 4.99 k line, R44 / R45
  RT0603BRD0711KL 11 kohm, and no old MPN left). `source-check.json` was regenerated.
- `audit.rs`:
  - IDENTITY takes the R_on and 4.99 k rows (patch 01 already had r_ct_*).
  - New `stage54_checks`: a whitelist per footprint (PS12 / 25121WF on 2512; ERJ-PA3 / 0603WAF on 0603).
  - New test `stage54_bom_holds`, plus patch 01's `s53_ct_references_fail`.

**B3 thermal**

- `b3-ratings/b3_ratings_gate.py` takes four patches:
  - release-margins `b3-gate.patch` (`GATE_R_MPN`);
  - ct-band 03 (`ct_rows`);
  - J1 `b3-gate-j1-row.patch` (`TERMINALS`, `terminal_rows`).
  - The J1 patch's last hunk conflicts with patch 03 on the same `pr = ...` line. It was merged by hand:
    `probe_rows + module_rows + ct_rows + terminal_rows`.
- `b3-ratings/test_b3_terminal.py`: new, from the J1 patch.
- `b3/make_heat_sources.py`: ct-band 03 + 04 (R40–R46 heat rows; R39 at (I/200)^2 × 3 ohm).
- `b3-convergence/thermal_body.py`: ct-band 03 (`chip0603` spec and mapping).
- `b3-convergence/inputs/part-bodies.json` (**adapted, not in any patch**):
  - R10 / R12 / R18 / R20 mpn → PS122WF680JT4E. `body_runs` writes this MPN into the run files, and `GATE_R_MPN` rates by
    it. Without this edit the stage-54 board would still be rated at 1 W.
  - New entries for R40 / R41 / R43 / R44 / R45 / R46. `body_runs.py:252` and `build_network_parts` index `PART_BODIES[ref]`
    for every heat row, so patch 03 alone would raise a KeyError on R40 in the chain. Footprint, pose and fab / courtyard
    boxes were read with `extract_bodies.py` from the s53 board of record (82af7bd93e62); they are identical on the c54
    board. R44 / R45 take the s54 MPN.
- `b3-convergence/report_convergence.py`: a `chip0603` limit row. This file is not in the chain.
- `b3-ratings/temp-ratings-2026-10-15/scripts/ratings_table.py`: `res()` rows for PS122WF680JT4E (2 W, 70 → 155 C) and
  ERJ-PA3F4991V (0.25 W, 105 → 155 C, the ambient line).
  - Only the ledger pipeline reads this table (`temp_ratings.py` → `results.json` → `ledger_temps.py`); no chain gate does.
  - `results.json` was not regenerated.

**BOM / CPL / stock**

- `scripts/apply_lcsc.py`: PS122WF680JT4E → C2793964 and ERJ-PA3F4991V → C4036134 (Extended).
- `sourcing/STOCK-2026-10-19-c54.csv`: a new dated read (JLC part API 2026-10-19: 3,856 / 4,339; `READ_COLS` format).
  Neither MPN is in the snapshot, so without this read the stock gate counts both lines short.
- `sourcing/study-2026-10-15/scripts/jlc-raw/detail_C2793964.json` and `detail_C4036134.json`: copied from
  `c54-release-margins/scripts/jlc-raw`. `bom_pricing` and `run_all.sh` read them.
- `sourcing/study-2026-10-15/run_all.sh`: an s54 block on the s52 template (the two new JLC records). It needs
  `snapshot/s54/bom-jlcpcb.s54.csv` from the chain's fab BOM.
- `native-21/layout/gates/test_stock_gate.py`: s54 checks.
  - A two-line BOM clears on the default `--stock` list from the c54 read.
  - Negative control: with the list cut before 2026-10-19, both lines are short.
  - The fab BOM check activates once the chain has regenerated `fab/bom-jlcpcb.csv`.

**Firmware / commissioning**

- Patch 02 is applied: `tank_freq.h`, `n21_binding.h/.c`, `test_tank_freq.c`, `test_n21_binding.c`, and the B17 rule in
  the table tool.
- `firmware/tools/commissioning_board_table.py`: patch 01 (R44 / R45 overrides) and patch 02 (B17). `mpn_ohms` gains the
  PS12 and ERJ-PA3 families, with test cases in `test_commissioning_board_table.py`.
- `firmware/components/power/COMMISSIONING.md` was re-rendered with `--write`, which changes three lines:
  - frozen-BOM sha;
  - B9 band **67.36–79.32 A**, nominal 73.19 A;
  - B17 **62.5 A, 4.86 A under 67.36 A**.

## 3. Commands and results

| Check | Result |
|---|---|
| `rustc --edition=2021 -O audit.rs` → scratchpad, run on `frozen/` and `native-21/frozen/` | PASS, 372 components / 187 nets (both) |
| `rustc --edition=2021 --test audit.rs` → scratchpad | **96 / 96** (rustc writes straight to the scratchpad, so no shared cargo target is involved) |
| `python3 -I native-21/verification/verify_source.py` | PASS (`source_hashes_match`, `two_frozen_exports_identical`) |
| `cmp` of all 5 files, `frozen/` vs `native-21/frozen/` | identical |
| test_b3_hot_copper / test_b3_airflow / **test_b3_terminal** | 0 / 0 / 0 failures |
| test_stock_gate | PASS (incl. the 2 new s54 checks) |
| test_bom_pricing / test_cu_temp_basis / test_pin_absmax | PASS / all controls / all controls |
| scoped/test_scoped.py | 16 / 16 |
| test_track_geometry / test_spine_lock / test_trim_tails / test_jet_strip_height / native-21/layout/test_track_cleanup21 | PASS / PASS / 0 / 0 / PASS |
| CPL audit `selftest()` | ok |
| firmware host tests (`cmake -S firmware/test`, ctest) | **31 / 31**, incl. tank_freq_tests and n21_binding_tests |
| `pytest firmware/tools/test_commissioning_board_table.py` | 40 passed |
| `commissioning_board_table.py --write`, then `--check` | PASS: COMMISSIONING and BRING-UP. The tool also prints its existing owner FINDING (the 28 A Kconfig range against the 24 A H bank) |
| `depmap_check.py --card scorecard-native21s53.json` | C1 lists the same missing-producer entries as at s52 (cu_temp_basis / pin_absmax / kelvin_floor / bom_* / price_*); C1b–C6 PASS |
| `datasheet-ledger/gate.py` (report written to the scratchpad) | **FAIL, expected**: the new MPNs are not in the ledger (section 5) |
| `datasheet-ledger/tests/test_gate.py` | 7 failures, all from the same missing entries and from line 63's named-PARTIAL `25121WF680JT4E` |

**Combined B3 gate on the s53 run files** (copied read-only from the ps-integrate `b3-ratings/runs`, board 82af7bd93e62):

- **Existing rows.** All 104 rows per case equal the committed `margins.json`. The metrics are unchanged on the s53 MPNs:
  release +1.3 K, rated part −51.0 K, laminate −50.8 K.
- **New rows per case.** The 7 CT rows R39–R46 (release: R39 +14.7 K, R40–R46 ≥ +22.3 K; c28: R39 +6.9 K) and J1:
  - release 98.8 / 105 C, +6.2 K;
  - c22 +12.6 K;
  - c28 +12.3 K.
- **With the run files' R_on MPN set to PS122WF680JT4E.** The release margin is **+3.8 K**, bound by the laminate 1 mm-block
  copper peak. The rated-part margin is **−42.1 K**. R10 is +12.9 K at release and +1.2 K at c22. This is the
  c54-release-margins prediction.
- **Control.** An unlisted 2512 MPN (RC2512FK-0768RL) stops the gate.

**Other checks:**

- **Heat rows.** `make_heat_sources.py` runs: 46 parts. R44 / R45 are 0.757 mW at 11 k, R39 34.6 / 64.8 mW. Every heat
  row has a body and a spec (R40–R46 → chip0603). The generated `b3/inputs/*.json` were restored to HEAD; the chain
  regenerates them.
- **Pricing.** On a simulated s54 fab BOM (the current fab BOM with the four line changes), `parts_usd_at_500_v2` goes
  174.99 → **175.30** and `parts_usd_at_5` 275.09 → 275.54. The stock gate shows 0 lines short at 20 boards.

## 4. Left for the lead (not done here)

- **Chain.** It regenerates `fab/bom-jlcpcb.csv`, the CPL audit, `b3/inputs`, `margins.json` and the netlist-derived
  KiCad files. The new resistors get the standard chip rule (OK) in the CPL audit, as C50371 / C23046 did.
- **Sourcing.** After the chain: `cp fab/bom-jlcpcb.csv sourcing/study-2026-10-15/snapshot/s54/bom-jlcpcb.s54.csv`, then
  `run_all.sh`.
- **Stage tag entries.**
  - `kelvin_budget.BAND_BEFORE` / `FLOOR["native21s54"]`: there is none, and the code falls back to a default band.
  - `commissioning_board_table.STAGE_FACTS["54"]`, once s54 is the board of record.
- **Prose not changed.**
  - COMMISSIONING H14 still says 0.05 A. c54-ct-band proposes "Closed by c54-ct-band. B17 is 4.86 A …".
  - `06-controller-interface/cmti/cmti_table.py:389` uses 64.55 A as the OCP band minimum.
  - `round3/thresholds.py:103` `expected_mpn` still lists R44 / R45 as 10 k. Every caller passes overrides, and the table
    tool now overrides R44 / R45 (patch 01). The script's own no-override `main` was already stale before s54 (R33, R35,
    R39, R43, R46), so this is not a new break.
- **Patches not applied.** These are the OPEN-ITEMS / ledger patches:
  - `c54-ct-band/patches/05-open-items-s29.patch`;
  - `c54-j1-thermal/patches/open-items-S21-J1.patch` and `ledger-1714971.patch`;
  - `c54-release-margins/results/ledger-patch.json`;
  - `c54-touch-current/results/ledger.patch` and `open-items.patch` (out of this brief).

## 5. Ledger edits needed (`datasheet-ledger/ledger.json`, the ledger lane)

The gate's own FAIL lines:

```
FAIL  BOM MPN missing from ledger: ERJ-PA3F4991V (R131,R71,R72,R74,R75)
FAIL  BOM MPN missing from ledger: PS122WF680JT4E (R10,R12,R18,R20)
FAIL  [RT0603BRD0710KL] designators differ from BOM: ledger-only ['R44', 'R45'], BOM-only []
FAIL  [RT0603BRD0711KL] designators differ from BOM: ledger-only [], BOM-only ['R44', 'R45']
WARN  ledger entry not in BOM (stale): 0603WAF4991T5E
WARN  ledger entry not in BOM (stale): 25121WF680JT4E
```

1. **Add PS122WF680JT4E** (R10, R12, R18, R20), replacing 25121WF680JT4E. `c54-release-margins/results/ledger-patch.json`
   carries the entry: PARTIAL, R_on release ratio 0.378, c22 0.754. Move 25121WF680JT4E to `alternates` or delete it.
2. **Add ERJ-PA3F4991V** (R71, R72, R74, R75, R131), replacing 0603WAF4991T5E (same file).
3. **RT0603BRD0710KL**: drop R44 and R45 from the designators.
4. **RT0603BRD0711KL**: add R44 and R45. The CT band rows are 67.36–79.32 A at the 85 C basis, and R44 / R45 run at
   0.757 mW.
5. Skip the release-margins patch's 6SVPC220MV → 16SVPK220M replacement: C126–C129 stay 6SVPC220MV.
6. `tests/test_gate.py:63`: the named-PARTIAL list names `25121WF680JT4E`. It becomes `PS122WF680JT4E`.
7. Optional: re-run `temp_ratings.py` / `ledger_temps.py` so `results.json` carries the two new rating rows.

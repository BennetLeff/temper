# Candidate 30: LS pocket / U42 re-lay, built as stage 40 (native21s40)

**Verdict: ACCEPT against s38** (`results/compare.txt`). Board native21s40 `33ed17f3`, chain CHAIN_DONE with no
spine owner (SPINE_LOCK PASS against the s38 baseline). Cheaper on parts at 500 ($202.24 -> $202.21), BOM lines (93 -> 92)
and JLC extended lines (67 -> 66); better on return-path open changes (18 -> 15) and track geometry. Every gate matches
s38: all pass except `b3_ratings`, which fails on both boards (DECISIONS 51; s40 laminate -38.3 K vs -38.0 K, inside the
card's 1.0 K tolerance). Ledger violations stay at 1 (IPW65R018CFD7).

```
ACCEPT native21s40 vs validation-results/10-benchmark/scorecard-native21s38.json: cheaper ['parts_usd_at_500', 'bom_lines', 'jlc_extended_lines'], better ['return_path_open_changes', 'track_acute_corners', 'track_fold_backs', 'track_right_angle_corners']
```

Built on the board of record s38 (`b5bf428d`, integration `f8cca7d21`, rebased onto `59281e65a` for the DECISIONS 51
B3 model) on branch `claude/native21-c30-ls-pocket`; stage 40 commit `b66113971`. Scored against `../../10-benchmark/scorecard-native21s38.json`.

| Goal | Stage 40 |
|---|---|
| 30a: U44 becomes an ISO6721FB HS-B -> LS link; FMEA §6b reverts to §6a | **Done.** U44 at (3.25, 47.25, 270) in U42's pocket; D20 (second BAT54S) on the LS vote; FMEA §6c records the revert |
| 30b: C161's n_ls pad reaches a via / plane <= 3 mm; U45 exception 6.0 -> 3.0 | **Done.** C161's own via (0.42 mm) now lands in the In1 n_ls plane; `bypass_check.py` counts only plane-landing vias and U45 is at the standard 3.0 mm |
| S10 return-path fixes, inside HS-B / LS | MON_GOOD_HA's four open changes closed; the GOOD node, now counted, keeps one (U45.1's via). 18 -> 15 |
| U42 stays RECOM R24C2T25 | Unchanged part and pose |
| Barrier, D5, RES_A, Kelvin / OCP, enclosure fit unchanged or better | See section 1 |

## 1. Results

| Metric | s38 | s40 | Note |
|---|---|---|---|
| Board sha256 | `b5bf428d` | `33ed17f3` | chain run 2 (`$R/c2`); run 1 failed, see below |
| DRC errors / unconnected | 0 / 0 | 0 / 0 | |
| Barrier / RES_A creepage | PASS / 13.375 mm | PASS / 13.375 mm | RES_A on B.Cu, unchanged |
| D5 min (all / HV) | 8.047 / 8.507 mm | 8.047 / 8.507 mm | |
| SPINE_LOCK | PASS (owner selv) | PASS (no owner) | one test-point label shift, see below |
| Enclosure fit (in / collide / ...) | 403 / 0 / 0 / 405 / 0 | 403 / 0 / 0 / 405 / 0 | RUST 0 |
| JLC DFM | PASS, 747 vias | PASS, 754 vias | +7 |
| Bypass check | PASS (U45 at 6.0 mm exception) | PASS, U45 at 3.0 mm | U44.1 C159 2.81, U44.8 C160 2.72, U45 C161 0.42 mm |
| Return-path open changes | 18 | 15 | asserted worst 2.72 mm PASS |
| Kelvin band low / high | 67.77 / 116.44 | 67.77 / 116.44 | Kelvin copper untouched |
| OCP pickup | 4.17 A | 4.17 A | `result-s40.json` |
| Fuse-copper min ratio | 0.993 | 0.993 | `s40_necks.json` |
| Task 04 | 39 / 0 failed | 39 / 0 failed | bus_p span 2.835 % |
| B3 laminate / rated-part margin | -38.0 / -63.9 K | -38.3 / -64.1 K | FAIL on both (DECISIONS 51). FET row and bank caps +0.2-0.4 K; U41 -1.6..-2.0 K and U42 -1.0 K cooler from the added n_ls copper |
| B3 peaks (legacy, not compared) | 162.1 / 135.0 C | 165.4 / 136.7 C | nominal_h10 / c28_h25 |
| EMI / touch / CMTI | 12.4 dB / 0.241 mA / 1.579 | unchanged | |
| Parts at 500 / at 5 | $202.24 / $306.87 | $202.21 / $306.62 | CA-IS3720LW out; ISO6721FB, BAT54S, 10 k, 100 nF in |
| BOM lines / placements / JLC extended | 93 / 348 / 67 | 92 / 351 / 66 | single-source lines 18 -> 17 |
| JLC assemblable share at 500 | 0.849 | 0.848 | -0.001: dearer in `compare()`, which still accepts because performance improves |
| Track acute / right-angle / fold-backs | 205 / 103 / 44 | 199 / 101 / 43 | any-angle 678.5 -> 680.3 mm |
| Ledger | 3 / 30 / 59 / 1 | 3 / 29 / 59 / 1 | VERIFIED / PARTIAL / UNAUDITED / VIOLATION |
| ERC power_pin_not_driven | 1 | 1 | |

**Return-path opens left (15).** bus_fault_hot x3, ocp_ok_hot, ovp_ok_hot x2, permit x3, bus_fault_iso, bus_fault,
bias_good x3 are SELV or Kelvin nets outside the HS-B / LS island and outside this candidate. The fifteenth is the GOOD
node's B -> F change into U45.1 (104.4, 99.65): see section 3. An In2 n_ls patch was tried there; its ring covered 7 of
16 samples, not a majority, so it was dropped.

**Chain run 1 (`$R/chain1-failed.log`, `R=worktrees/runs-native21/s40`) failed twice, both fixed in run 2.** (1) SPINE_LOCK: the F vote n_ls pour pushed
TP30 off its F spot, the test-point numbering shifted (TP34 -> TP35) and the spine compare saw a renamed SELV pad; the
pour's east edge is now x 58.4. (2) D5 8.042 mm: the In1 LS-block west extension came within 8 mm of a SELV pour; it is
now built with an 8.2 mm keep-off (`merge_zone(..., selv_mm=8.2)`), and D5 returns to 8.047. In run 2 the chain's test-point
numbering still shifts once: TP37 now names the selv_gnd point at (30.48, 114.05) instead of (30.48, 120.94). SPINE_LOCK
passes with it.

**Cost.** About -$0.03 per board at 500 and -$0.25 at 5: the CA-IS3720LW line goes, and the ISO6721FB, BAT54S, 10 k and
100 nF lines gain one designator each. The QUEUE's estimate of about -$1.93 is not reached.

## 2. Netlist (30a)

- `elec/src/f6_bias.ato`: `HighBiasSelv` removed. `bias_hb` is a `HighBiasLink` like `bias_ha`: U44 ISO6721FBDR
  (`bias_hb.link`), C159 / C160 its VCC1 / VCC2 caps (`clink1` / `clink2`), output MON_GOOD_HB. The reverse channel is
  wired as on U43 (INA to GND2, OUTA open), which `audit_f6.rs` checks for both links.
- `Heartbeat`: `vote_b` (D20, BAT54S) ANDs MON_GOOD_HB into the LS good node through its MID -> K2 half (MID on the
  node, A1 open). A BAT54A would hold both halves but adds a BOM line. U46's A input (HSB_GOOD) no longer carries a
  verdict: `rgate` (R135, 10 k) holds it at v3v3, so U46 is the M1b buffer (the pump is AC-coupled).
- `elec/src/power_stage_120v.ato`: `c_ref_xfer_5` (C168, 100 nF 0603, the C153-C156 part). pwm_hb's B.Cu -> F.Cu via at
  (34.4, 110.6) was served by the old verdict isolator's SELV-side decoupler at 2.0 mm; with that part gone the change
  measured 16.5 mm and failed the asserted `return_path19` limit. C168 sits 2.6 mm from it.
- Count 348 -> 351 (+D20, +R135, +C168; U44 / C159 / C160 change role). BOM lines 93 -> 92 (CA-IS3720LW out; ISO6721FBDR,
  BAT54S, 10 k, 100 nF lines gain a designator). `audit.rs` PASS, 83 / 83 tests; `verify_source.py` PASS.

## 3. Layout (stage 40 copper, `patches21.add_stage40`)

Method: the frozen s38 copper with `incr21.py`'s prune step (`INCR21_PRUNE=1`): base copper that served a moved part's old
pads, or meets a new pad, is dropped, then `add_stage40` re-lays. SELV / PE copper is exempt from the old-pad prune (the
spine's; edited by hand), so C47's selv_gnd path through the old U44.9 land survives; the two old U44 SELV stubs left
open are ripped explicitly. `passes40.sh` j1 was clean (0 unconnected, 0 errors).

- **U44 pose.** `spot_scan.py` on the s38 board: (3.25, 47.25, 270) is the only legal straddling pose. East of the
  pocket U42's courtyard, the SELV 8 mm floor and sw_b's F corner close every row. HS pins north on the n_hb bank (B
  n_hb pour joins it); LS pins south on U42's n_ls pocket (F n_ls pour merged with U42's heat-spread). Two of the
  pocket's 18 n_ls stitch vias moved for C160.
- **HS-B side.** monitor-v5 / monitor-good leave on two B.Cu lanes beside sw_b's B run, then In2 into the island; the
  router joins them to U39.5 and U31 (`C140.1 - R124.1` is s38 copper).
- **LS side.** ls_v5 and MON_GOOD_HB run east on In1 lanes under the pocket (y 46.1 / 46.6, between v24_raw and the
  HV_RET plane; the corridor is opened locally, `S40_OPEN_IN1`).
- **Vote relocated (decision).** The LS In1 corridor east of x 55 is full (n_ls, leg_ret, v15_ls, kelvin_p/n, ls_v5,
  v24_raw, MON_GOOD_HA) and no legal via exists at x 56-125, y 44-51, so MON_GOOD_HB cannot run to the LS block. D18 and
  D20 move beside U43 (east of v24_raw's branch); MON_GOOD_HA and MON_GOOD_HB become short, and the GOOD node takes
  MON_GOOD_HA's old corridor lane to the LS block. FMEA-neutral under 19.11.2's component faults; the one layout
  consequence (one corridor trace now carries both HS vetoes) is in FMEA §6c.
- **R135** sits on the old SELV pocket's v3v3 / hsb_good vias. **C168** north of the C47 selv_gnd via, clear of TP17.
- **Return paths.** Beside the vote no inner plane of any net fills (the In1 corridor, the unfilled hv_ret / bus_p trunk
  outlines): an F n_ls pour over an In1 n_ls patch (priority 2 over the unfilled hv_ret outline), stitched by two n_ls
  vias. MON_GOOD_HA's F -> B change beside U43: U41's F / B heat-spread pours reach 1.65 mm west (x 46.35 keeps 8 mm to
  the SELV planes; 46.0 gave 7.87 mm). The GOOD node's In1 -> F change in the LS block moves 1.6 mm onto the LS-block In1
  plane, with an F n_ls patch and a stitch. GOOD's B -> F change into U45.1 (104.4, 99.65) stays open: it sits in an In1
  island that hb_rc / hb_tx's In1 runs close off, monitor_ls-uv's In2 run passes 0.7 mm away, and the only legal spot
  for the via is that one.
- **30b.** C161 sits in a pocket walled at x 100.3-100.8 on every layer (monitor_ls-ref F, vsense_in In1, ocp_kelvin_p
  In2, bus_fault_hot B). The In1 n_ls LS-block plane reaches into it from the south (y >= 90.75) under bus_fault_hot's
  x 100.35 run, where In2's ocp_kelvin_p run lies directly under that line (SI1 counts it coupled; `return_path19` PASS).
  North of y 90.75 it stays off: bus_fault_hot's x 99.05 run and jog have no Kelvin track under them (a first try put
  8 samples of it over n_ls and failed SI1). C161's s38 via at (99.5, 95.035), 0.42 mm from its n_ls pad, now lands in
  that plane.
- **Track geometry.** New right angles in the lanes are mitred; a router-made redundant second path to R124.1 (with
  1-4 deg near-folds) is avoided by routing to the s38 C140.1 - R124.1 copper instead.

## 4. Records

- `gates/return_path19.py`: MON_GOOD_HB and the GOOD node (`monitor_ls-good`) added to the reported signals (LS_REF):
  the GOOD node now runs the LS corridor. Its pre-existing U45.1 change is counted from here on.
- `gates/bypass_check.py`: plane-backed (net, mm) pairs count only vias that land in a filled pour of that net on a
  non-F layer (pcbnew `HitTestFilledArea`). U45 n_ls 6.0 -> 3.0. U44 rows are ISO6721FB rows (1/4, 8/5) at 3.0 mm.
  On the s38 board the new rule fails U45 (5.97 mm), as intended.
- Datasheet ledger: CA-IS3720LW removed; ISO6721FBDR U43, U44; BAT54S-7-F + D20; 10 k + R135; 100 nF + C168. Gate: one
  VIOLATION (IPW65R018CFD7, DECISIONS 49), none added.
- FMEA: `../c24-monitor-fmea/FMEA.md` §6c (M1b as drawn; §6b retired; R135 rows; the vote relocation).
- `08-manufacturing-package/native-21/stage30-heartbeat/README.md`, `spot_scan.py` (D20, R135).
- Kelvin scripts: native21s40 DIVIDER / BAND_BEFORE / FLOOR (stage-38 values; the Kelvin copper is untouched).

## 5. Reproduce

```
git show f8cca7d21:zapote/power-stage-120v/native-21/layout/copper.json > $R/base-s38.json
$KPY native-21/layout/dump_pads.py <s38 board>/section.kicad_pcb $R/base-s38_pads.json
sh validation-results/11-candidates/c30-ls-pocket/passes40.sh $R/base-s38.json $R/p40
sh native-21/layout/gates/chain.sh native21s40 $R/p40/j1 $R/c1
python3 -I native-21/layout/gates/scorecard.py native21s40 $R/c1 --audit PASS --json validation-results/10-benchmark/scorecard-native21s40.json
python3 -I native-21/layout/gates/scorecard.py --card validation-results/10-benchmark/scorecard-native21s40.json \
    --compare validation-results/10-benchmark/scorecard-native21s38.json
```

`scripts/` holds the layout aids used on the way (view / probe / quick_check); they are not gates.

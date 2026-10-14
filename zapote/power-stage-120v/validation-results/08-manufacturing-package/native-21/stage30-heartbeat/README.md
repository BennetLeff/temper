# Stage 30 heartbeat: placement evidence (DECISIONS 33)

- `spot_scan.py` lists the legal poses of a stage-30 part on the routed s29 board (courtyards, barrier, clearances;
  see its docstring).
- `jlc_fetch.py` caches the JLC part records it read in `jlc-raw/`.

## HS-A link U43 (ISO6721FB)

```
python3 -I spot_scan.py <s29 copper-dump.json> U43 47 65 --box 38,48,72,80 --step 0.5 --top 15
```

U43 sits beside U41 at (47.0, 66.25, 90), as `native-21/layout/place.py` STAGE30 records. It routes in
`patches21.add_stage30`.

## HS-B: why its verdict crosses to SELV (U44 ISO7710F), not to LS

```
python3 -I spot_scan.py <s29 copper-dump.json> U44 30 40 --box 0,26,48,80 --step 0.5 --top 40 --margin 0.0
```

The scan returns two clusters of legal ISO6721FB poses: x 3.5–4.5 / y 36–47, on the top edge of U42's n_ls pocket, and
x 17–18.5 / y 76.5–77.

The first cluster was placed at (3.5, 47.0, 270) and routed in the stage-30 passes. The HS-B links did not close:
- HS-B nets: the rows y 47–60 are blocked on all four layers across x 0–26. U42's LS pocket covers x ≈ 2–17, the SELV
  8 mm floor reaches x ≤ 20.5, In2 carries the protected `bus_p` trunk for y ≤ 51, and B.Cu the protected `n_hb` strip.
  Only grandfathered power copper crosses that band.
- LS side: `ls_v5` and `mon_good_hb` did not close either.
- Making same-group pours permeable did not change the result.

These are router outcomes on the intermediate stage-30 board, not a committed rerunnable proof. The second cluster
was not route-tested; it is an open simplification candidate (the ISO6721FB is about $1.93 cheaper per board at 500
than the ISO7710FDWR, `sourcing/STOCK-2026-10-13-addendum-s30.csv`).

### As built

- U44 is an ISO7710FDWR (reinforced, default LOW) at U34's stage-29 pose (25.6, 110, 0), with C159 / C160 at C141 /
  C142's poses (`place.py` S29_RENAME).
- Its output HSB_GOOD gates the SELV heartbeat NAND U46.
- HSB_GOOD leaves U44's SELV pocket on one authored In2 (selv_gnd plane) leg of 25.9 mm (`patches21.add_stage30`). The
  pocket is closed by the permit / PWM / bias_good bundle, which occupies both F and B, and by the 8 mm floor to HS-A:
  no via fits between the bundles.
- That leg was chosen over In1 because B.Cu carries only bias_good and permit above it: 0 mm of asserted
  return-path signals, against 13.7 mm of pwm_lb / pwm_hb on F.Cu over an In1 leg (`python3 -I inner_leg_overlap.py <copper-dump.json>`; asserted nets as in `return_path19.py`).
- The FMEA coverage note is `validation-results/11-candidates/c24-monitor-fmea/FMEA.md` §6b.
- Stage 31 (DECISIONS 34): U44 is now a Chipanalog CA-IS3720LW (default LOW, same land pattern), and U9 / U32 are
  CA-IS3720HW (`validation-results/11-candidates/c31-bom/README.md`).

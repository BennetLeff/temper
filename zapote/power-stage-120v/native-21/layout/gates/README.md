# native-21 gate tools

Committed copies of the stage pass / gate scripts (they used to live in a session scratchpad and were lost
when it was wiped, 2026-10-12).

    sh passes.sh OUTROOT [HISTORY_ROOT ...]    # routing passes until clean (OUTROOT/passes.out)
    sh chain.sh TAG PASSDIR BUILDDIR          # board build + every gate + Kelvin + B3 + fab package
    sh regate.sh BUILDDIR                     # barrier (Rust), DFM, copper exports, task 04 A4 cases

Before `chain.sh`, add the TAG's `DIVIDER` / `BAND_BEFORE` / `FLOOR` entries to
`validation-results/02-protection-timing/kelvin/kelvin_{plane,budget}.py`. Keep OUTROOT / BUILDDIR outside
the repo (they are large). Clear `board_only21.json` test points before routing passes; `chain.sh`
re-plans them.

`zone_priority_gate.py [copper.json]` (stage 17b, run first by `chain.sh`): fails when two different-net pours on one
layer sit closer than their clearance at the same priority, since KiCad's fill order would then decide the contested
copper. `patches21.ZONE_WINNERS` declares each such pair's winner; `resolve_zone_priorities` keeps every existing order.
`fill_hash.py BUILDDIR...` hashes the filled pours of builds (copper-dump.json) to show two rebuilds fill identically.

Stage 18 (DECISIONS item 18): RES_A to SELV / PE is 12.6 mm on F.Cu / B.Cu (`rules21.RES_A_CREEPAGE`). `barrier21.py`'s
first line reports it per outer layer, `barrier_gate21.py` adds a per-outer-layer Rust run (`res_a_outer`), and
`chain.sh` runs `validation-results/08-manufacturing-package/native-21/stage18-res-a-creepage/res_a_creepage18.py`.

    $KP gates/bypass_check.py BOARD OUT.json    # stage 19 (N1, from 365151b62): local 100 nF within limits at U10-U13, U15, U24, U25, U29-U31, U40 (regate.sh runs it)
    $KP gates/bypass_spots.py BOARD REF SUP RET # free spots for a 0603 bypass beside an IC's supply pin (scanner behind place.py STAGE19_MOVES)
    python3 gates/trim_tails.py DRC.json copper.json [--write]   # drop the dangling router tails DRC reports (K6); rebuild and re-run DRC after

After a clean `passes.sh`, `native-21/layout/copper.json` is the pass output: copy it aside before any `git checkout`
(it is overwritten in place, and a checkout restores the previous stage's copper).

Stage 19 (DECISIONS item 19), also run by `chain.sh`:

    $KP ../../validation-results/.../stage19-pi-si/pi_distances19.py BOARD [--json OUT] [--control]
        # PI1 / PI2: RECOM U41 / U42 VOUT+ and TPS7A47 U26 OUT / IN / NR pins to their caps, asserts <= 3 mm
    python3 gates/return_path19.py COPPER_DUMP.json [--json OUT] [--control [--expect NET=mm,...]]
        # SI1 / SI2: per fast signal, the reference under every track point and each layer change's
        # transfer-cap distance; asserts bus_fault_hot on ocp_kelvin_p end to end, every ct_zc / pwm_hb change
        # <= 3 mm and the 19b transfer caps' plane vias (C153-C156)

Clear `board_only21.json` `test_points` before `passes.sh` (stale test pads sit on the router's paths); `chain.sh`
re-plans them from the clean pass. After the passes, `trim_tails.py DRC.json copper.json --write` drops the router's
dangling stubs (K6); rebuild before the chain.

Stage 19c (DECISIONS item 19c) and the benchmark (item 22, `validation-results/10-benchmark/`):

    python3 gates/xfer_spots.py COPPER_DUMP.json COURTYARDS.json X,Y [X,Y ...] [--no-planes] [--ignore-ref REF] [--ignore-net NET]
        # free 0603 poses for a v3v3-selv_gnd transfer cap within reach of one or more layer changes
    python3 gates/scorecard.py TAG BUILDDIR --audit PASS --json CARD.json      # right after chain.sh
    python3 gates/scorecard.py --card CARD.json --compare validation-results/10-benchmark/scorecard-native21s19c.json
        # ACCEPT / REJECT against the benchmark (rule fixed 2026-10-13)

`return_path19.py` asserts ct_zc and every PWM input from 19c on; on 19b it fails (pwm_ha 7.59, pwm_la 5.11 mm).

Stage 33 (DECISIONS 38, chain cache trap; `validation-results/11-candidates/c33-six-layer/CACHE-PROOF.md`): task 04's
and B3's caches share one model key, so a change to any model input misses both:

    python3 gates/model_key.py [--list]   # every task-04 / B3 script, heat inputs, stackup file(s), $SHEET_BARREL

SELV-spine lock (13-coupling contract WS4 ↔ WS5, `validation-results/13-coupling/README.md` §8 and §10 item 1):

    python3 -I gates/spine_lock.py native-21/verification/TAG-all-copper.json.gz [--owner selv]
        # the spine region x 30-110 / y 130-180 must match the locked baseline (selv_spine_lock.json, s32 export):
        # default = every track / via / pad / pour in the region (any lane that does not own the spine);
        # --owner selv = only the contract nets, the selv_gnd / v3v3 planes and J4 + the transfer caps
    python3 -I gates/test_spine_lock.py        # 11 controls: mutations per mode, and s31 must fail

A lane that has to change the spine re-issues `selv_spine_lock.json` (new baseline export and board hash) under its own
DECISIONS item. It does not loosen the gate.

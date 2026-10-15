# native-21 gate tools

Committed copies of the stage pass / gate scripts (they used to live in a session scratchpad and were lost
when it was wiped, 2026-10-12).

    sh passes.sh OUTROOT [BASE.json [FILLS]]   # routing passes on a frozen base until clean (OUTROOT/passes.out)
    python3 router_bench.py OUTDIR [--seed N] # rip seeded signal nets, re-route, report closure / errors / barrier
    sh chain.sh TAG PASSDIR BUILDDIR          # board build + every gate + Kelvin + B3 + fab package
    sh regate.sh BUILDDIR                     # barrier (Rust), DFM, copper exports, task 04 A4 cases

Before `chain.sh`, add the TAG's `DIVIDER` / `BAND_BEFORE` / `FLOOR` entries to
`validation-results/02-protection-timing/kelvin/kelvin_{plane,budget}.py`. Keep OUTROOT / BUILDDIR outside
the repo (they are large). `passes.sh` routes on the accepted copper.json (or BASE) frozen, as the stage-33+
candidate passes scripts did, and builds without the test points (BOARD_ONLY21_NO_TEST_POINTS); `chain.sh` re-plans
them on the result. `router_bench.py` restores copper.json when it ends; like `passes.sh` and `chain.sh` it is one
writer of the layout files.

Step timing (laps.sh): `incr_iter.sh`, `passes.sh`, `chain.sh` (and its parallel blocks) and `regate.sh` append each
step's wall time to `steps.jsonl` in their output dir (BUILDDIR, OUTROOT, OUTROOT/iN); `LAPS=0` turns it off.

    python3 laps.py BUILDDIR_OR_OUTROOT       # per script: seconds per step, slowest first

DRC tiers (2026-10-15, one board, kicad-cli 10.0.4, no refill): the full rules take 146 s, 48 s without the three
creepage constraints, 2.1 s with no custom rules (refill + connectivity alone, KiCad Python API: 12 s). The routing
passes and `router_bench.py` check with `DRC_FAST` (`drc_rules_fast.py`: the build's copy of the rules without the
creepage constraints; every clearance rule stays, and barrier21 bounds the creepage groups in plan view on every build).
`chain.sh` unsets `DRC_FAST`: the gated board always gets the full rules.

Pour-cut repair (`INCR21_SETTLE=N`, off by default; `router_bench.py --settle N`): incr21 judges pour connectivity
on the previous build's fills, so a new track that cuts a pour could leave pairs it believes joined. `incr_iter.sh`
then refills and asks KiCad's own connectivity (`fast_conn.py`, ~12 s; its counts matched kicad-cli DRC on 5 boards)
and routes what is still open, frozen, up to N rounds before the DRC. Measured 2026-10-15 (`router_bench.py --nets 30
--max-tracks 40`, seeds 23 / 29 / 31, sorted DRC pairs): open 85 -> 5, 78 -> 4, 92 -> 5 with `--settle 0` and the
same with `--settle 3`, which added 56-65 s per build. Every pair left open was one incr21 had already tried and
failed, none a pour cut, so it stays off until a board shows pour cuts.

    $KP fast_conn.py BOARD.kicad_pcb OUT.json [--save]   # refill + KiCad connectivity -> DRC-shaped unconnected pairs

Determinism: KiCad's DRC lists the same unconnected pairs in a different order from run to run, and incr21 joins
pairs in list order, so incr21 sorts each DRC file's pairs (2026-10-15). Router comparisons made before that
(different copper from identical inputs) are not like for like.

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

`passes.sh` leaves the test points off its builds (stale test pads sit on the router's paths); `chain.sh` re-plans them
from the clean pass. After the passes, `trim_tails.py DRC.json copper.json --write` drops the router's
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

`chain.sh` runs it in the copper block (BUILDDIR/spine-lock.json) and fails the chain on any difference; set
`SPINE_OWNER=selv` for the SELV-side lane only. A lane that has to change the spine re-issues `selv_spine_lock.json` (new baseline export and board hash) under its own
DECISIONS item. It does not loosen the gate.

Track-geometry hygiene (DECISIONS 43): `python3 -I gates/track_geometry.py TAG-all-copper.json.gz` counts right-angle and
acute corners (with 0° fold-backs) at two-segment vertices per net and layer, and any-angle track length;
`test_track_geometry.py` holds 7 controls. The scorecard reports them: acute corners and fold-backs as a strict ratchet,
right angles (+5) and any-angle length (+25 mm) with a small allowance for new routes.

Track-geometry cleanup (stage 37, candidate 37): `python3 native-21/layout/track_cleanup21.py COPPER.json
TAG-all-copper.json.gz --out native-21/layout/copper.json --report R.json` removes fold-backs, opens acute corners, mitres
right angles and snaps any-angle segments on routed copper, keeping every edit only where the clearance, barrier, RES_A,
spine, fill and connectivity checks hold (the tool's docstring lists them). The export must be the build of COPPER.json.
It touches every island, so it runs last, after the other lanes merge, then the chain. A second run on its own output
(rebuilt and re-exported) changes nothing. Controls: `native-21/layout/test_track_cleanup21.py`.

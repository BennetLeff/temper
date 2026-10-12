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

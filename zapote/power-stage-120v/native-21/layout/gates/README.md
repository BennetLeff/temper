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

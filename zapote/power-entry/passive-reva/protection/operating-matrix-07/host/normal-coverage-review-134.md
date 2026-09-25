# Normal coverage review 134

This review checked the accepted baseline and the parent nine-point normal checkpoint against the declared 3-by-3 matrix. The required identity is 108, 120, and 132 Vrms crossed with three declared resistive loads. LL01–LL03, LL04–LL06, and LL07–LL09 provide exactly one row for each voltage/load tier; there are nine unique cases and no missing or duplicate matrix point.

All nine individual receipts report `ACCEPTED_MODELED_NORMAL_GRID_POINT`, policy `event-aware-normal-v1`, three cycle means, zero screen counts, and retention of all original rows. The baseline receipt is also accepted under `event-aware-normal-v1` with three cycle means. The accepted resistive load powers span 359.070534–1392.349522 W; receipt input powers span 405.389658–1574.420283 W. The 15 A Irms limit remains a modeled screen. It is not a hardware rating.

The source-bound check recomputed SHA-256 for each receipt-declared small `.cir`/`.inc` file in its acceptance directory and for the baseline source set. It found zero mismatches. The parent checkpoint and margins receipt were also hashed from the current files. No raw archive was read or rehashed.

The strict legacy checker result is consistently `REJECTED_NONINCREASING_TIME` because equal timestamps are present. That rejection is retained as negative evidence; the event-aware policy evaluates equal-time groups while preserving every source row. It does not turn the strict rejection into a pass.

Margins receipt 89 confirms the declared numerical thresholds and limiting cases, including the 15 A current screen and exclusive cycle-drift bound below 0.005. These are authored-model margins only. They do not qualify component ratings, thermal or SOA behavior, fuse/protection behavior, an inverter, or a complete appliance.

The normal evidence is therefore complete for these nine discrete 650 ms modeled cold-start points plus the baseline. It does not prove interpolation between points, a continuous envelope, or the project’s 1800 W whole-appliance/hardware behavior. Parent final acceptance remains required; unfinished fault cases remain outside this review.

Evidence hashes and case identities are machine-readable in `host/normal-coverage-review-134.json`.

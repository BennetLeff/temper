# 2026-08-21 — DRC ceiling re-measurement for PR #1424 (C6/K1 footprint corrections)

## Scope

PR #1424 lands two footprint-body corrections on `pcb/temper.kicad_pcb`:
C6 from a 10 mm-pitch disc cap to the specified 22.5 mm-pitch film cap
(`C_Rect_L26.5mm_W7.0mm_P22.50mm_MKS4`, rot 90) and K1 from phantom #250
Faston tabs (zero PCB copper) to the Schrack `RT33K012`'s real THT
contacts. Per the standing contract, the DRC ceiling and every registered
measurement artifact keyed to the board hash are re-measured **in the same
PR**.

## Protocol

- `temper_placer.validation._drc_api.run_drc()` (`--all-track-errors`,
  single-thread `KICAD_CONFIG_HOME` pin), `pcb/temper.kicad_dru`
  regenerated first — the ci_check_drc.py protocol.
- kicad-cli 10.0.5 (matches the committed record's tool version).
- 120 samples per board. Measured in place; boards swapped via
  `git checkout <ref> -- pcb/temper.kicad_pcb` and verified by SHA-256
  after every swap.

### Baseline validation (before any delta was computed)

`origin/main`'s board (26981fea, the #1425 record) re-measured under the
identical protocol reproduced #1425's committed record **exactly** in
every deterministic category (clearance 179, copper_edge_clearance 11,
courtyards_overlap 1, drill_out_of_range 6, hole_clearance 33,
shorting_items 39, solder_mask_bridge 4; warnings incl. via_dangling 111)
with creepage {105: 14, 106: 106} inside the recorded band — an
independent reproduction of another session's numbers, validating this
environment before any delta was trusted.

## Results

Branch board (3ae31c44): errors 401–402 / 120 runs, warnings 405/405.
Creepage {114: 13, 115: 107} — spread 1, same KiCad pointer-dedup artifact
(issue #20048) documented since #602; ceiling 116 = max + spread, guard
116−115 = 1 ≥ 115−114 = 1 holds (checked via
`DrcRatchet.check_noise_headroom()`).

Per-type attribution, by violation-set diff at net-pair (errors) /
component-pair (warnings) granularity — measured this session, not
inherited:

| category | main → branch | cause |
|---|---|---|
| clearance | 179 → 188 (+9) | all nine: `discharge.r_snub1-p2` × {`w1_2` ×7, `power_in.ntc-no` ×2} — K1 contact nets |
| creepage (ceiling) | 107 → 116 | every new net-pair names a K1 contact net (`w1_2`/`power_in.ntc-no`/`power_in.bypass_relay-coil2`) |
| courtyards_overlap | 1 → 6 (+5) | C6 body ×{C4, C22, R26, U16}; K1 ×C7 |
| lib_footprint_mismatch | 26 → 27 (+1) | C6 (resync-stamp side effect, per the 2026-08-13 resync entry's precedent) |
| pth_inside_courtyard | 0 → 3 (+3) | all three C7 ×K1 |
| silk_over_copper | 42 → 46 (+4) | C6 ×U16 ×3; K1 ×1 |

Everything else byte-identical across all 120 samples on both boards.
error_ceiling 380 → 403; warning_ceiling 13605 → 13613.

The handoff document's "split C6 +4 / K1 +19" is confirmed at set level:
C6 contributes exactly 4 error-side courtyards; K1's contact nets account
for every other new violation.

## silk_overlap: closing the cap-saturation failure

Raw reads saturate at the 199 ERROR_LIMIT cap on both boards, which makes
`ci_check_drc.py --backend kicad-cli` exit 4 (cap-saturation guard) — the
same failure already visible on `main`'s regression workflow today. The
committed 13407 came from the 2026-08-13 inclusion–exclusion campaign;
this session re-measures it exactly.

Method — bucket-pair sweep with diagonal isolation. Run (i, j) keeps
buckets i∪j only (`measure_uncapped_drc.py:934`), so each within-bucket
violation appears in exactly n runs and each cross-bucket violation in
exactly 1:

> TRUE = raw_sum − (n−1) · Σ_i diag(i)

Steps, each measured:

1. n=16 sweep: raw 3463, Σdiag 204; every cell exact (< 199) except the
   one containing C2∪C3, which read 199 (truncated).
2. Recursive sub-partitions of that cell localized the truncation to
   C2×C3 alone; `saturating-pair` (item-level bisection) gives
   **C2×C3 = 12852** — identical to its 2026-08-13 value: the pair was
   never actually fixed; the interpenetration persists.
3. All other pairs in the hot set measured individually: REST = 0; the
   only other contribution is 2 within-C29 self-overlaps.
4. Substituting the exact cell value:
   **TRUE = 3463 − 15·204 − 199 + 12856 = 13060**.

Validation: an independent n=12 partition (raw 2647, Σdiag 204, the same
single truncated cell) reproduces **13060 exactly** through the same
algebra. Shipped as `warnings_by_type.silk_overlap = 13060`;
warning_ceiling 13613 → 13266.

Residual, flagged not fixed: `ci_check_drc.py`'s cap-saturation guard
still exits 4 after this — it fires on the *measured raw read* being at
the cap, which no ceiling value can fix while kicad-cli truncates reports
at 199. Making the gate consume uncapped totals is a follow-up.

Findings for a maintainer: C2×C3 at 12852 is ~98% of the board's entire
silk_overlap debt and predates this PR; it is recorded here because the
cap-saturation guard forced the question, not because #1424 caused it.

## Method notes

- The references provenance record
  (`temper_constraints.references.yaml`) was flagged STALE by
  `check_measurement_provenance.py` during this work — caught in the same
  PR, per contract. Sheetpath→Reference map diffed identical across all
  168 footprints before re-pinning (footprint swap changes pad geometry,
  not identity).
- One tooling incident, recorded per the measurement-instruments-that-lie
  discipline: an editor invocation with a repo-relative path wrote the
  re-pin into the MAIN checkout instead of this PR's worktree (the edit
  tool resolves paths against the session cwd, not the shell workdir).
  Caught immediately by the gate still reporting STALE; the stray edit
  was reverted before anything else touched the shared checkout. Absolute
  paths only, from here on.

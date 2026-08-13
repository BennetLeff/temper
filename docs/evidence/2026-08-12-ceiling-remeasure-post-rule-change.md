<!-- provenance: commit=900c79dd98ebcd5d37a3cf37dd599b51c7793cc0 dirty=false -->
<!-- Measured 2026-08-12 in worktree
/tmp/claude-1000/-home-bennet-Desktop-temper/c0bf43ed-bc14-4a43-9c79-57bf591cf8ab/scratchpad/worktrees/ceiling-remeasure,
branch fix/ceiling-remeasure-post-rule-change, branched from origin/main at
900c79dd98ebcd5d37a3cf37dd599b51c7793cc0. pcb/temper.kicad_pcb NOT modified:
sha256 6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64,
identical to the sha256 the CURRENTLY-COMMITTED drc_ceiling.json record
already names (measured at f70296adc). pcb/temper.kicad_dru regenerated from
scripts/generate_kicad_dru.py::generate_dru, sha256
bad860a0d199e5b4fa35d0643ba68dae1ddecc50ae5f854c27832139b60e6ae4 --
independently reproducing the DRU hash
docs/evidence/2026-08-12-clearance-floor-reland.md sec "Measured 2026-08-12"
records for the same rule state, corroborating that both documents measured
the same rules. kicad-cli 10.0.5 via the ~/.local/bin shim. DRC via
temper_placer.validation._drc_api.run_drc (--all-track-errors, single-thread
KICAD_CONFIG_HOME pin), 260 samples in two independent 130-sample rounds
against the board in place (pcb/ already carries fp-lib-table and libs/, so
no scratch-copy step was needed). -->

# Re-deriving `drc_ceiling.json` after four rule-tightening PRs, on the unchanged committed board

## Verdict up front

`pcb/temper.kicad_pcb` has not changed. Four already-merged PRs changed what
`kicad-cli`'s DRC checks (`pcb/temper.kicad_pro`'s netclass assignments and
`scripts/generate_kicad_dru.py`'s emitted rules), not the board. The
committed board now measures **1296 [1294–1296] total / clearance 402
(deterministic) / creepage 200 [198–200]** against a recorded ceiling of
**1266 / 386 / 186** — `main` has been failing its own gate since the last
of these PRs landed. This is a yardstick change, not a board regression:
every rise below is traced to a specific, named rule from a specific,
already-merged PR, corroborated by that PR's own isolated measurement. No
category rose that could not be attributed. Nothing improved, so nothing is
ratcheted down. **`pcb/temper.kicad_pcb` sha256
`6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64` is
unchanged from the currently-committed record; this PR does not touch it.**

## Measurement

260 samples total, two independent 130-sample rounds (`--all-track-errors`,
`pcb/temper.kicad_dru` regenerated from the current
`scripts/generate_kicad_dru.py` first — the `ci_check_drc.py` protocol),
against the committed board in place:

| round | samples | errors | clearance | creepage |
|---|---:|---|---:|---|
| 1 | 130 | {1295: 29, 1296: 101} | 402 (130/130) | {199: 29, 200: 101} |
| 2 | 130 | {1294: 1, 1295: 29, 1296: 100} | 402 (130/130) | {198: 1, 199: 29, 200: 100} |
| **combined** | **260** | {1294: 1, 1295: 58, 1296: 201} | **402 (260/260)** | **{198: 1, 199: 58, 200: 201}** |

Round 2 was run specifically because round 1 alone (130 samples, the file's
own minimum) found only a 2-value creepage band (199, 200 — spread 1),
which disagrees with this file's own documented history: `AGENTS.md` and
every prior `_march` entry since the #602 K3 swap record creepage as a
stable **3-value, spread-2** band on every properly-sampled (≥40) campaign.
Trusting round 1's spread of 1 would have reproduced exactly the mistake
`AGENTS.md` and the 2026-08-11-creepage-noise-headroom-guard-fix entry warn
against — a headroom computed from an under-sampled window. Round 2 found
the third value: `198`, at 1/130 (~0.8% in that round, ~0.4% combined) — rare
enough that a 59% chance existed of round 1 missing it entirely
((1 − 0.004)^130 ≈ 0.59), which is exactly what happened. The combined
260-sample band, `{198, 199, 200}`, reproduces the historical spread-2
pattern.

All 11 other error categories and all 9 warning categories are **byte-identical**
to the currently-committed record across all 260 samples in both rounds:
`annular_width` 4, `copper_edge_clearance` 10, `courtyards_overlap` 11,
`drill_out_of_range` 4, `hole_clearance` 105, `hole_to_hole` 3,
`shorting_items` 199, `solder_mask_bridge` 154, `track_width` 199,
`tracks_crossing` 1, `via_diameter` 4; warnings total 489/260,
`lib_footprint_issues` 11, `lib_footprint_mismatch` 23, `missing_courtyard` 5,
`pth_inside_courtyard` 1, `silk_edge_clearance` 1, `silk_over_copper` 172,
`silk_overlap` 199, `track_dangling` 45, `via_dangling` 32.

## Per-category before/after

| category | recorded ceiling | measured (260 samples) | new ceiling | delta | attributed to |
|---|---:|---|---:|---:|---|
| `clearance` | 386 | 402 (deterministic, 260/260) | **402** | **+16** | #1083 (+10 isolated), #1087 (`gnd`→Power, the rest of the rise), #1096 (−16, partial offset) |
| `creepage` | 186 | {198,199,200} over 260 | **202** (200 + 2 headroom) | **+16** | #1084 (new HV↔HV rule), #1083 (PWR_RTN exposed to HV↔LV + HV↔HV rules) |
| `annular_width` | 4 | 4 | 4 | 0 | — |
| `copper_edge_clearance` | 10 | 10 | 10 | 0 | — |
| `courtyards_overlap` | 11 | 11 | 11 | 0 | — |
| `drill_out_of_range` | 4 | 4 | 4 | 0 | — |
| `hole_clearance` | 105 | 105 | 105 | 0 | — |
| `hole_to_hole` | 3 | 3 | 3 | 0 | — |
| `shorting_items` | 199 | 199 | 199 | 0 | — |
| `solder_mask_bridge` | 154 | 154 | 154 | 0 | — |
| `track_width` | 199 | 199 | 199 | 0 | — |
| `tracks_crossing` | 1 | 1 | 1 | 0 | — |
| `via_diameter` | 4 | 4 | 4 | 0 | — |
| **error_ceiling** | **1266** | 1294–1296 | **1298** | **+32** | sum of the two per-type rises above |
| `warning_ceiling` | 489 | 489 | 489 | 0 | — |

No category rose that is not accounted for in this table, and no category
fell — there is nothing to ratchet down in this entry.

## Attribution, rule by rule

### `clearance` 386 → 402

- **#1083** (`42c73e21f`, `fix/unassigned-hv-domain-nets`): `PWR_RTN` (the
  doubler midpoint, an HV-domain net per `elec/domain_manifest.yaml:95`) had
  **no** entry in `pcb/temper.kicad_pro`'s `netclass_assignments`, so it fell
  to `Default` (0.2mm clearance) and was invisible to every HV↔SELV
  clearance rule. Assigned `HighVoltage` (2.0mm), matching its circuit
  siblings. The PR's own commit message measured this in isolation:
  clearance 386 → 396 (+10).
- **#1087** (`cfc8534af`, `fix/unassigned-selv-nets`): 20 previously-
  unassigned SELV-domain nets assigned real `kicad_pro` netclasses, most
  significantly `gnd` — the board's largest net, 86 pads — newly classed
  `Power` (0.5mm) instead of falling through unprotected. The PR's own
  evidence (`docs/evidence/2026-08-12-selv-net-assignment.md`) isolated that
  `gnd` alone drives the entire clearance/aggregate delta from this PR; the
  other 19 SELV nets measure zero cost on this board's current layout.
- **#1096** (`81ac8432e`, `fix/gnd-class-declaration`): declares a real
  `GND` netclass in `pcb/temper.kicad_pro` (trace_width 1.0mm, clearance
  0.3mm — mirrored unchanged from `design_rules.py`'s own long-standing
  `GND` `NetClassRules`) and repoints `gnd`'s `kicad_pro` assignment from
  `Power` (0.5mm) to `GND` (0.3mm) — a **partial improvement** against
  #1087's intermediate state (a tighter, more permissive clearance figure
  for `gnd`'s pairs), not a further rise. The PR's own commit message
  measured this in isolation: clearance 418 → 402 (−16, stable across 30
  samples).
- **#1084** explicitly does **not** touch clearance ("Clearance values are
  unchanged everywhere — `HighVoltageTank` carries the same 2.0mm as
  `HighVoltage`", its own commit message) — confirmed here: clearance is
  fully deterministic across all 260 samples, with zero contribution
  attributable to it.

Net effect on this byte-identical board: `386` (baseline — `PWR_RTN` and
`gnd` both unprotected) → `402` (`PWR_RTN` correctly `HighVoltage`-classed,
`gnd` correctly `GND`-classed). Every step is a named, already-merged PR
enforcing a rule that was previously silently absent, not a placement or
routing change.

### `creepage` 186 → 202

- **#1084** (`3231dc3db`, `feat/hv-hv-creepage-enforcement`): adds the
  **first-ever** HV↔HV functional creepage rule (new `HighVoltageTank`
  netclass, 6.3mm floor, IEC 60335-1 Table 18) for
  `tank.c_tank1-p2` (the resonant tank's cap↔coil junction, 923.7V peak /
  570.5 Vrms) against every other HV net. Previously **no** rule in the
  repo constrained any HV-to-HV creepage pair at all — all three prior
  creepage rules ("AC Mains to LV", "HV to LV", "HighVoltageIsolated to LV")
  require one side to be non-HV. The PR's own commit message measured this
  in isolation: creepage 182–184 → 185–186.
- **#1083**: `PWR_RTN` → `HighVoltage` in `kicad_pro` (see the clearance
  section above) also newly exposes `PWR_RTN` to the HV↔LV creepage rules
  (and to #1084's new HV↔HV rule) it was previously invisible to via
  `Default`, which carries no creepage protection at all. The PR's own
  commit message measured this in isolation: creepage ~183 → ~197 (+11 to
  +14).
- **#1087 and #1096 do not touch creepage.** #1096's own commit message
  states every other DRC category including creepage was "identical or
  within existing noise bands — zero measured cost anywhere" for the `gnd`
  `Power`→`GND` change. #1087's SELV-net reassignments (`Power`/`GND`/
  `FinePitch`/`Differential`/`Default`) never move a net across the HV/non-HV
  boundary any creepage rule keys on — `Default`, `Power`, and `GND` are all
  equally "LV" as far as every creepage rule's condition is concerned, so
  relabeling among them cannot add or remove a creepage pairing. Confirmed
  empirically: all 11 other error categories (including everything #1087
  could plausibly have touched via trace-width/via-template changes) are
  byte-identical to the prior record across all 260 samples.

Net effect: `182–184` (baseline — `PWR_RTN`'s HV-adjacent creepage pairs
entirely unchecked, and no HV↔HV rule existed) → `198–200` (both
`PWR_RTN`'s real HV creepage exposure **and** the new tank-node HV↔HV rule
now enforced).

## Headroom reasoning

`creepage` is declared nondeterministic (the KiCad pointer-dedup artifact,
issue #20048, present since the #602 K3 swap). `check_noise_headroom`'s
invariant is `ceiling − max(observed) ≥ max(observed) − min(observed)`.
Combined 260-sample observation: `{198, 199, 200}`, so `max=200`, `min=198`,
`spread=2`. Ceiling set to `max + spread = 202`, giving headroom `2 ≥ 2` —
satisfied with **zero** slack beyond the measured spread, per this file's
own documented convention (`max(observed) + spread`, not an arbitrary wider
buffer — see the 2026-08-11-creepage-noise-headroom-guard-fix `_march`
entry for why a wider buffer was considered and rejected).

`clearance` is **not** nondeterministic here: 402/402 across all 260
samples, zero scatter. It is not added to `nondeterministic_error_types`
and its ceiling carries no headroom beyond the observed value, matching the
convention every deterministic category in this file already follows.

Verified against the actual guard, not just by hand:

```
$ python3 -c "... DrcRatchet(...).check_noise_headroom() ..."
PASS: noise-headroom guard OK for all nondeterministic categories
```

```
$ python3 scripts/ci_check_drc.py --backend kicad-cli
PASS: temper: DRC 1296/1298 errors, 489/489 warnings within ceiling
      [2 error(s) of unratcheted slack -- lower error_ceiling to 1296 to lock this in]
PASS: noise-headroom guard (single-sample DRC is safe for every recorded category)
```

The "2 errors of unratcheted slack" note is expected, not a defect: the
aggregate ceiling is the *sum of per-type ceilings*, and the `creepage`
per-type ceiling deliberately carries 2 units of headroom above any single
observed sample — the same shape every prior aggregate figure in this file
has had whenever a nondeterministic category is present (e.g. the
2026-07-29-creepage-admitted entry's `845` vs. an observed `842`).

## Why these rises are debt, not measurement noise

Both rises are **real, previously-invisible violations that the new rules
correctly surfaced**, not an artifact of this remeasurement:

- `PWR_RTN` — a genuine mains-domain net — had zero clearance and zero
  creepage protection on the shipped board until #1083 landed. It was not
  "safe and uncounted"; it was unchecked.
- The resonant tank's cap↔coil junction (923.7V peak) had no creepage rule
  at all against any other HV net until #1084 landed — the highest working
  voltage on the entire board was, until this week, the *least* protected
  category in the ceiling file.

Recording `clearance: 402` and `creepage: 202` as the new ceiling is
admitting this debt, exactly as `docs/evidence/2026-08-11-creepage-gatedrivehv-false-positive.md`'s
precedent and this file's own `_goal` header ("every number below is debt
to pay down, not budget to spend") require — not resolving it. No category
here is a false positive being ratcheted past; #1084's own evidence
(`docs/evidence/2026-08-12-hv-hv-creepage-enforcement.md`) already
independently confirmed the rule binds on 2 real, constructed violation
pairs.

## What was not found

No category rose that could not be traced to #1083, #1084, #1087, or #1096
by name. No unattributed rise is being hidden inside this re-measurement.

## Verification before commit

```
$ sha256sum pcb/temper.kicad_pcb
6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64  pcb/temper.kicad_pcb   # unchanged
$ git status --porcelain -- pcb/
                                                                                          # empty
$ git grep -l "^<<<<<<< " -- '*.py' '*.json' '*.yaml'
                                                                                          # empty
$ python3 scripts/check_measurement_provenance.py
PASSED -- 2/2 record(s) fresh, 0 allowlisted.
$ python3 scripts/ci_check_drc.py --backend kicad-cli
PASS (see above)
```

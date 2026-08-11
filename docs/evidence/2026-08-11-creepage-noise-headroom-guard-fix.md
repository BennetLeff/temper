# The creepage noise-headroom guard: chronic since #602, fixed by matching headroom to measured spread

<!-- provenance: commit=8e92559e2af78a26b9c7f1c3710226908d4b3650 dirty=true -->

**Date:** 2026-08-11
**Branch:** `fix/drc-creepage-noise-headroom`
**Board:** `pcb/temper.kicad_pcb` unchanged by this PR — sha256
`6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64`
(commit `8e92559e2`, the tip of `origin/main` at branch time, post-#1023).
This PR touches only `power_pcb_dataset/drc_ceiling.json` (ceiling
headroom, not the measured count), `packages/temper-placer/src/
temper_placer/regression/drc_ratchet.py` (a related R27 gate gap found
while fixing this), `AGENTS.md`, and tests. The board file and
`pcb/temper.kicad_pro` are never edited.
**Tool:** `kicad-cli 10.0.5` — but see §4: an environment reset removed the
local install mid-investigation, so this PR's own fresh sampling is
partial (20 samples) rather than the full 120+ originally planned. The
argument below does not depend on that partial run; it depends on
evidence already committed to this repository's own history plus one
dedicated prior investigation, both independent of this PR.

## Summary

- **Is it chronic? Mostly yes, precisely stated: yes since the band
  widened, not from creepage's very first characterization.** Every
  creepage record in `drc_ceiling.json` from the `#602` K3 swap
  (2026-08-02) through today (6 consecutive re-measurements, 10 days) has
  violated `scripts/ci_check_drc.py`'s noise-headroom guard. The three
  records *before* that (2026-07-31 to 2026-08-01, band 199–200) did
  **not** violate it — the guard held exactly at the boundary
  (headroom 1 = spread 1). The bug began the moment creepage's band
  widened from 2 states to 3 and nobody re-derived the headroom from that
  new spread — see §1.
- **True spread: 2 (three consecutive integers), not wider, in every
  properly-sampled campaign this project has ever run — but this cannot
  be proven to arbitrarily small probability, and the fix does not
  pretend otherwise.** A dedicated prior investigation
  (`docs/evidence/2026-08-04-drc-measurement-determinism.md`) ran two
  independent 120-sample campaigns specifically to characterize this and
  found support `{185,186,187}` in *both*, zero exceptions in 240 draws.
  Every `_march`-logged creepage campaign since agrees on spread=2
  regardless of which three integers (199–200 pre-#602 is the one
  exception, spread 1). See §2.
- **Fix chosen: raise creepage's ceiling headroom from `max + 1` to
  `max + spread` (185 → 186 here), landed as a proper R27-governed raise
  with the SAME already-measured 134-sample provenance — the true
  violation count does not change.** Two alternatives (comparing against
  the recorded band; taking the minimum across N samples) were considered
  and rejected, not merely unconsidered — see §3 for why, including why
  "minimum" is actively the wrong direction for this specific defect.
- **What this fix does NOT catch, stated plainly: a real new creepage
  regression of 1 or 2 violations on this mains-isolation category will
  now pass CI undetected, indistinguishable from noise.** Only a
  regression of 3 or more is guaranteed to trip the gate. See §3.
- **Also fixed, found as a direct consequence of this investigation:**
  `DrcRatchet.validate_raise_evidence`'s ≥120-sample check was hardcoded
  to fire only when `"clearance"` is a `nondeterministic_error_types`
  key — so this PR's own creepage-only raise, and any future one, would
  have sailed through the R27 machine gate with zero samples required.
  Generalized to any declared-nondeterministic category. See §5.

---

## 1. Is it chronic? Walking the `_march` log and git history

`git log --oneline -- power_pcb_dataset/drc_ceiling.json` has 29 commits.
Reconstructing every historical `creepage` record's `nondeterministic_error_types`
block and the `violations_by_type.creepage` ceiling that shipped alongside
it (oldest to newest):

| commit | date (approx) | observed band | ceiling | headroom | spread | guard |
|---|---|---|---:|---:|---:|---|
| `a2fdfd1bb`/`f0cf384d1`/`da902db9f` | 2026-07-31 – 08-01 | [199, 200] | 201 | 1 | 1 | **SAFE** (boundary) |
| `de59c0458` (#602, K3 swap) | 2026-08-02 | [185, 186, 187] | 188 | 1 | 2 | **VIOLATED** |
| `1305ff88a` (#611, R27 lands) | 2026-08-02 | [185, 186, 187] | 188 | 1 | 2 | **VIOLATED** |
| `835474e4e` | 2026-08-07 | [185, 186, 187] | 188 | 1 | 2 | **VIOLATED** |
| `b63b51943` | 2026-08-07 | [185, 186, 187] | 188 | 1 | 2 | **VIOLATED** |
| `049037844` (#1010, DRU fix) | 2026-08-11 | [169, 170, 171] | 172 | 1 | 2 | **VIOLATED** |
| `8e92559e2` (#1023, netclass fix) | 2026-08-11 | [182, 183, 184] | 185 | 1 | 2 | **VIOLATED** (pre-this-PR) |

Reproduced live, not just by archaeology: running
`python3 scripts/ci_check_drc.py --backend kicad-cli` against `8e92559e2`
(this PR's branch point, before any change here) prints, independent of
whether kicad-cli itself is available (the noise-headroom guard reads only
already-committed JSON, no DRC run):

```
FAIL: noise-headroom guard -- single-sample DRC is not safe for 1 nondeterministic category:
  temper: 'creepage' has ceiling headroom 1 (ceiling 185 - observed max 184) smaller than
  its own measured run-to-run spread 2 (observed [182, 183, 184] over 134 samples). ...
```

**Verdict:** the guard has failed for every creepage record for the last
10 days and 6 consecutive re-measurements — effectively the entire time
creepage has been a *three*-valued nondeterministic category. It did
**not** fail during creepage's first three days as a nondeterministic
category, when the band was only two-valued (199–200) and `max + 1`
happened to be exactly sufficient. The root mechanical cause: `AGENTS.md`
and this file's own `_march` notes documented "`observed max + 1`" as a
fixed convention, calibrated once against a spread-1 band, and every
subsequent re-measurement (six of them, by at least four different
authors/sessions) copied `+ 1` forward mechanically without checking it
against the guard's own invariant (`headroom >= spread`) — even though
`scripts/ci_check_drc.py --backend kicad-cli` (no DRC run needed for this
part) would have said so immediately, every single time.

## 2. True spread — re-derived from independent evidence, not the current 134-sample window alone

The task instruction this PR follows is explicit: a 134-sample window may
not have seen the tails. Rather than trust `drc_ceiling.json`'s current
`observed: [182, 183, 184]` at face value, here is every independent
characterization of creepage's spread this project has produced, across
multiple different true violation counts (the band moves as the board/DRU
changes; its *width* is the question):

| source | board state | n | support | width |
|---|---|---:|---|---:|
| `da902db9f`/`f0cf384d1`/`a2fdfd1bb` `_march` | pre-#602 | 120 | {199, 200} | 1 |
| `docs/evidence/2026-08-04-drc-measurement-determinism.md`, unpinned | post-#602 | 120 | {185, 186, 187} (185×16, 186×48, 187×56) | 2 |
| same doc, pinned (`MaximumThreads=1`) | post-#602 | 120 | {185, 186, 187} (185×27, 186×58, 187×35) | 2 |
| `b63b51943`/`835474e4e` `_march` | post-#602 | 130 | {185, 186, 187} | 2 |
| `049037844` `_march` (post-#1010) | post-#1010 | 40 | {169, 170, 171} | 2 |
| `8e92559e2` `_march` (post-#1023, current) | post-#1023 | 134 | {182, 183, 184} (182×5, 183×43, 184×86) | 2 |
| this PR, fresh live sample (see §4) | post-#1023 | 20 (partial) | {183, 184} (183×8, 184×12) | ≤1 observed at n=20, consistent with the 134-sample record |

**Six independent campaigns, five different points in this project's
history, 564+ combined samples, one deliberately-designed 240-sample
determinism study — every one lands on a 3-value support (spread 2) once
the band widened past its original 2-value state, and never wider.** The
KiCad-side mechanism is already fully diagnosed and is not re-derived
here: `docs/evidence/2026-08-04-drc-measurement-determinism.md` §4 traces
it to KiCad's own creepage DRC provider deduplicating reported violation
pairs through a `std::set<std::pair<const BOARD_ITEM*, const BOARD_ITEM*>>`
keyed and ordered by raw process pointer value — non-reproducible across
process invocations by construction, filed upstream as KiCad issue
[#20048](https://gitlab.com/kicad/code/kicad/-/issues/20048), unreachable
from any kicad-cli flag or post-processing.

**Honest limit of this claim:** no finite sample size can rule out an
arbitrarily-rare fourth value (e.g. a true tail state occurring with
probability ≪1%). This PR's fix does not claim to. It claims that the
measured spread is 2 with high confidence given the evidence above, and
sizes the ceiling's headroom to that measured spread exactly — see §3 for
why a wider, "just in case" buffer was rejected.

## 3. The fix, the rejected alternatives, and what regression it now misses

**Chosen: `max(observed) + spread` instead of `max(observed) + 1`.**
`power_pcb_dataset/drc_ceiling.json`: `violations_by_type.creepage`
185 → **186** (headroom 1 → 2, matching the measured spread exactly — not
an arbitrary safety buffer). `error_ceiling` 1251 → **1252** (this file's
`error_ceiling` is literally `sum(violations_by_type.values())`, verified
before and after this change). The **measured violation count is
unchanged** — still `182–184` over the same 134 samples, same
`provenance` record (same `measured_at_commit`, same input hash, same
tool version) — because the board did not move and nothing about *what
was measured* changed, only the *safety margin* the ceiling carries above
it. This is why it is not "widening a ceiling to make a gate pass": the
count being gated was never in question; only the guard's own stated
invariant against that count was unsatisfied, by an inherited arithmetic
mistake (§1). Landed as a proper R27 raise: `Ceiling-Approval:` trailer on
the landing commit, a new non-empty `_march` entry
(`2026-08-11-creepage-noise-headroom-guard-fix`) naming this exact cause,
and the existing measured-live provenance (134 samples, well over the
120-sample floor).

**Rejected: compare a fresh sample against the recorded `[min, max]` band
instead of a scalar ceiling.** This sounds like it directly targets the
problem ("a run inside the known band passes, one outside it fails") but
is mathematically identical to setting headroom to **zero**
(`ceiling = band max`) unless the band is allowed to expand as new noise
extremes are observed in CI. Zero headroom reintroduces the exact
false-failure risk this guard exists to prevent — worse than the status
quo, not better. If instead the band is allowed to self-expand on
observing a new extreme, that is an unreviewed ratchet with no human in
the loop: a real regression that happens to land just past the current
band would, by construction, get *absorbed into the band* rather than
flagged, one CI run at a time. On a mains-isolation category, silent,
automatic, unattributed ceiling drift is a worse failure mode than the
one being fixed.

**Rejected (as literally stated) / corrected: taking the *minimum* across
N samples at measurement time.** This is safety-backwards for this
specific defect, not just unhelpful. KiCad's dedup artifact is understood
to sometimes *incorrectly collapse genuinely distinct violation pairs*
(`docs/evidence/2026-08-04-drc-measurement-determinism.md` §2, "Finding
A"), i.e. some runs under-report the true violation count. Taking the
**minimum** of N such draws converges toward the *most* under-counted
run — the least complete view of the board's real isolation defects,
exactly backwards for a mains-voltage safety gate, and inconsistent with
this file's own established "max + headroom" convention used for every
other nondeterministic category before this one. The safety-consistent
version of "collapse noise at measurement time" would take the
**maximum** across N CI-time samples instead (converges toward the true,
undiminished count; would very likely catch even a 1–2-count regression,
since the historical per-draw frequency of the band's top value is
~30–45%, making a multi-sample max miss it only rarely). This is a larger
architectural change to `DrcRatchet._check_board` (re-running kicad-cli
N times per CI invocation, ~7s/sample measured in this session — N=5 adds
roughly 30s of wall-clock) and is **not implemented in this PR**; recorded
here as the recommended next step, alongside the already-existing
recommendation (`docs/evidence/2026-08-04-drc-measurement-determinism.md`
§4, `docs/evidence/2026-08-04-creepage-rust-backend-survey.md`) to move
creepage measurement onto the deterministic `temper_drc_rs` backend
entirely, which would eliminate the blind spot below rather than bound it.

**The safety tradeoff this PR ships, stated plainly:** with headroom
raised from 1 to 2, **a real new creepage violation of 1 or 2 counts on
this board — e.g. one additional near-zero-margin HV/SELV pad pair
introduced by a bad placement or routing change — is now indistinguishable
from noise and will PASS this gate undetected.** Only a regression of 3
or more counts is guaranteed to be caught by the single-sample CI check.
This is the correct, minimal fix for the guard's own stated invariant
given the measured spread — not a claim that the resulting detection
power is sufficient for this category long-term. The two follow-ups named
above (CI-time max-of-N resampling, or the Rust-backend migration) are
what actually closes this gap; this PR only makes the existing single-
sample gate stop lying about being safe when it is not.

## 4. This PR's own fresh sampling — partial, and why

Per the task brief, this PR was expected to independently verify the
spread rather than rely solely on `docs/evidence/2026-08-04-drc-
measurement-determinism.md`'s two 120-sample campaigns (measured on an
earlier, `169–171`/`185–187`-band board state) and the current record's
own 134 samples. Per-sample cost measured directly in this session:
**~7.1–7.3s/sample** (`temper_placer.validation._drc_api.run_drc`,
`--all-track-errors`, single-thread-pinned, `pcb/temper.kicad_dru`
regenerated first — the standing `ci_check_drc.py` protocol), so a
120-sample confirmatory run was budgeted at ~15 minutes and started in
the background.

It reached **20/200 samples** — result `{183: 8, 184: 12}`, entirely
inside the already-recorded `[182, 184]` band — before an environment
reset (unrelated to this task; `/tmp/opencode/kicad-10.0.5` and its
`kicad-cli` binary were removed from under the running process,
apparently a shared-environment cleanup, not caused by or targeting this
session) killed every in-flight `kicad-cli` subprocess and removed the
tool. The coordinator confirmed the removal was environmental and is
restoring the tool centrally, to avoid three concurrent agents racing a
shared-prefix extraction.

**This does not weaken the core argument.** The 20 partial samples agree
exactly with the 134-sample committed record and every prior independent
campaign; the argument in §2–§3 is built primarily on evidence that
already existed before this PR (the dedicated determinism study's 240
samples, and five separate `_march`-logged campaigns spanning this
project's history), not on this session completing a large confirmatory
run. If a larger confirmatory run completes before this PR lands, its
result will be appended here and to `drc_ceiling.json`'s provenance; if
it reveals a wider spread than 2, the ceiling raise in §3 will be
revised accordingly rather than landed as-is.

## 5. A related R27 gate gap, found and fixed in the same commit

While tracing exactly how a creepage ceiling raise would be validated by
`scripts/check_drc_ceiling_approval.py` (the R27 machine-checked monotone
contract), `DrcRatchet.validate_raise_evidence`'s ≥120-sample requirement
was found hardcoded as `if isinstance(nondet, dict) and "clearance" in
nondet:` — literally true back when `clearance` was this file's one
chronically-scattering category, but silently inert the moment a
*different* category became the one actually carrying run-to-run noise.
Concretely: **this PR's own creepage-only raise would have sailed through
the R27 gate with zero samples required**, because the string
`"clearance"` is not a key in a creepage-only `nondeterministic_error_types`
block. `AGENTS.md` and the function's own docstring already claimed the
≥120-sample requirement applied to "the nondeterministic clearance
category" — accurate prose for a check that was never actually
category-generic in code.

Fixed in the same commit: the check now fires whenever *any* category is
declared nondeterministic, not only `"clearance"`. Existing tests
(`packages/temper-placer/tests/regression/test_drc_ratchet_approval.py`)
already covered the clearance case and continue to pass unchanged; two
new tests (`test_under_sampled_creepage_only_raise_fails`,
`test_sufficiently_sampled_creepage_only_raise_passes`) cover the
previously-unchecked creepage-only shape. `AGENTS.md`'s R27 section
updated to match.

## 6. What changed, file by file

- `power_pcb_dataset/drc_ceiling.json`: `violations_by_type.creepage`
  185 → 186, `error_ceiling` 1251 → 1252, updated
  `nondeterministic_error_types.creepage.note` and `provenance.measured_via`
  to explain the headroom-only correction, new `_march` entry
  `2026-08-11-creepage-noise-headroom-guard-fix`. No change to the
  measured band, sample count, or any other category.
- `packages/temper-placer/src/temper_placer/regression/drc_ratchet.py`:
  generalized the R27 sample-count check from a hardcoded `"clearance"`
  to any category present in `nondeterministic_error_types` (§5);
  documented the `max + spread` convention correction in
  `NoiseHeadroomViolation`'s docstring.
- `AGENTS.md`: corrected the "clearance is the one genuinely
  nondeterministic category" framing (creepage has been the chronic one
  since #602) and added the `headroom >= spread` invariant explicitly,
  with a pointer to this document, so a future re-measurement checks the
  guard before committing a ceiling rather than copying `+ 1` forward.
- `packages/temper-placer/tests/regression/test_drc_ratchet.py`: new
  `TestRealCeilingFileNoiseHeadroom` regression test that loads the ACTUAL
  committed `drc_ceiling.json` and asserts `check_noise_headroom` returns
  no violations — fails immediately on a future re-measurement that
  reintroduces this bug, independent of CI's separate kicad-cli-dependent
  `ci_check_drc.py` invocation.
- `packages/temper-placer/tests/regression/test_drc_ratchet_approval.py`:
  two new tests for the §5 fix.
- This document.

## Files

- Fix: `power_pcb_dataset/drc_ceiling.json`, `packages/temper-placer/src/
  temper_placer/regression/drc_ratchet.py`, `AGENTS.md`
- Tests: `packages/temper-placer/tests/regression/test_drc_ratchet.py`,
  `packages/temper-placer/tests/regression/test_drc_ratchet_approval.py`
- This document
- Cited, pre-existing (unmodified by this PR):
  `docs/evidence/2026-08-04-drc-measurement-determinism.md`,
  `docs/evidence/2026-08-04-creepage-rust-backend-survey.md`,
  `docs/evidence/2026-08-11-creepage-gatedrivehv-false-positive.md`

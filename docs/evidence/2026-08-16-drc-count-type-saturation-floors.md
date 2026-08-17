<!-- provenance: commit=bc761f6547883a25d886c7278cf9c599a1e55b55 dirty=false (HEAD at time of writing; worktree clean. This document is an engineering writeup, not a DRC measurement -- no kicad-cli run, no board touched; pcb/temper.kicad_pcb was never written by this task (`git status --porcelain` clean for pcb/** throughout). Branch feat/drc-count-type, worktree /tmp/opencode/agent-drc-count, based on origin/main 593d9ab24. The pre-existing corpus-test red documented in sec 6 was verified against a detached origin/main worktree at the same base. -->

# DrcCount — a type that makes trusting KiCad's 199/499 saturation caps as real counts unrepresentable

**Date:** 2026-08-16
**Branch:** `feat/drc-count-type` (base `origin/main` @ `593d9ab24`)
**Problem class:** instruments that under-report (handoff mechanism 4) — the
same family as the `pad_connectivity_audit.py` defects.

## 1. The problem

KiCad's DRC engine truncates the *reported* violations per category at a GUI
list-widget performance constant (`pcbnew/drc/drc_engine.cpp`, 10.0 branch):

```c
// wxListBox's performance degrades horrifically with very large datasets.  It's not clear
// they're useful to the user anyway.
#define ERROR_LIMIT 199
#define EXTENDED_ERROR_LIMIT 499
```

The headless `kicad-cli` inherits this. A count at exactly its category's
limit is therefore a **saturation floor** — "the true count is >= N" — NOT a
real count. The 2026-08-15 handoff (§2 mechanism 4) flagged the resulting
confusion directly: "a result of exactly 199 or 499 is a cap, not a count,"
and the session repeatedly had to disambiguate capped vs uncapped numbers,
with a "199" trusted as a real count when it was actually a floor.

**Where the trust was doing damage:** `power_pcb_dataset/drc_ceiling.json`
once recorded `track_width = 199` and `shorting_items = 199` as ceilings —
"Any change to the board that halves the true number of shorts will still
read 199, and any ratchet on them is measuring nothing"
(`docs/evidence/2026-08-12-dru-rule-precedence.md` sec 4). PR #1178's
de-saturation work raised those ceilings to true counts, but *nothing in the
codebase enforced* that a 199/499 could not be written (or trusted) again.
The ratchet compared raw counts with no notion of "this number is a floor."

## 2. The type

`temper-drc-rs/src/drc_count.rs` (pure Rust, unconditional module — present
in a `--no-default-features` wasm32 build, unit-testable without Python; the
pyo3 surface is `drc_count_pyo3.rs`, mirroring the `ipc`/`ipc_pyo3` split):

```rust
pub struct DrcCount { count: u32, is_capped: bool }   // fields private

pub fn from_kicad(count: u32, category: &str) -> Self  // cap detection
pub fn count(&self) -> u32                              // the raw number
pub fn is_capped(&self) -> bool
pub fn is_honest(&self) -> bool
pub fn honest_count(&self) -> Result<u32, CappedCountError>  // the only
                                                            // way to get
                                                            // truth
pub fn display(&self) -> String  // "199 (CAPPED — true count >= 199)" | "42"

pub struct CappedCountError { pub count: u32 }  // Display + Error impls
```

**The compile-time knowledge** (deliverable 4): `honest_count()` returns a
`Result`. You cannot obtain the count as *truth* without handling the cap —
calling it on a capped count returns `Err(CappedCountError)`, so a caller
that needs the true count is forced to decide what a floor means for it
(re-measure with `scripts/measure_uncapped_drc.py`, or treat the value as a
lower bound). `display()` renders the ambiguity for humans. The fields are
private, so a `DrcCount` can only be built by `from_kicad` — the capped flag
can never disagree with the count it classifies.

### 2.1 The per-category cap table (why `category` is load-bearing)

The handoff's blanket "199 or 499 is always a cap" framing is the *diagnostic
confusion* the type exists to end — taken literally it produces the **reverse
error**: `creepage` is genuinely uncapped (its provider bypasses the limit; a
20 mm creepage rule reports 3,311 — same evidence doc sec 4), and `clearance`
caps at 499, not 199. The type encodes the per-category table instead:

| category | cap | source |
|---|---|---|
| `clearance`, `unconnected_items` | 499 (`EXTENDED_ERROR_LIMIT`) | `drc_engine.cpp` `m_errorLimits` loop (`DRCE_CLEARANCE`/`DRCE_UNCONNECTED_ITEMS`) |
| `creepage` | none — uncapped | measured: 20 mm rule reports 3,311; the board's own 198–200 is real scatter |
| everything else (`track_width`, `shorting_items`, `silk_overlap`, ...) | 199 (`ERROR_LIMIT`) | `drc_engine.cpp` `else` branch |

Consequences that fall out correctly:

- `creepage = 199` → **honest** (a real count, matching the ceiling file's
  `nondeterministic_error_types` characterization).
- `clearance = 199` → **honest** (below *its* 499 cap).
- `shorting_items = 499` → **honest** (impossible as a cap — the engine stops
  at 199 for it; only 199 is the saturation signal).
- `track_width = 199` → **capped** (the exact case the session mis-trusted).

### 2.2 What it does NOT detect (near-cap overshoot) — stated honestly

`--all-track-errors` checks the limit between whole per-track batches, so a
saturated category can overshoot its nominal cap by 0–~14
(`scripts/measure_uncapped_drc.py`'s `SAFE_MARGIN = 20`). Exact-equality
detection (`from_kicad`) is the *provable* floor signal from a single raw
count; a count merely *near* a cap is **suspected** saturated and needs the
determinism re-run protocol (`_verified_count` there — repeat-exact counts
are true, cap-disturbed counts are not). `DrcCount` never guesses in the
near-cap zone: it reports exactly what is knowable from one number. The
near-cap distinction is a measurement *protocol* question, not a type
question; folding a guess into the type would make `is_capped` mean less.

## 3. Wiring

| surface | change |
|---|---|
| `temper_drc_rs` module | `drc_count_from_kicad(count, category) -> (count, is_capped, display)` and `drc_cap_for(category) -> int \| None` pyfunctions |
| `_drc_api.py` | `DrcCountInfo` dataclass + `drc_count_from_kicad` / `classify_counts` / `drc_cap_for` delegation shims (thin-pyo3 pattern) |
| `drc_ratchet.py` `_check_board` (kicad-cli backend) | every per-type error/warning count classified through `DrcCount`; saturated categories surfaced on the new `DrcRatchetResult.capped_error_categories` / `capped_warning_categories` fields (`category -> display()`). The ceiling comparison itself still runs on the raw counts (pinned kernel contract — the differential suites stay bit-identical); the flag rides alongside so a pass over a capped count is never mistaken for a verified-under-ceiling result |
| `ci_check_drc.py` | new **cap-saturation guard, exit code 4**: fails loudly whenever (a) a measured per-type count is capped, or (b) a committed ceiling value in `drc_ceiling.json` sits at its category's cap ("a ceiling pinned to a saturated value protects nothing"). Both surfaces are covered; `creepage`/`clearance`-at-199 are not flagged |
| `check_drc_determinism.py` | `analyse()` adds `at_cap` per category; `render()` prints `[at cap — floor, not a count]`, so a stable 199 reads as "reproducibly saturated" rather than "exactly 199 violations" |

**Design boundary:** the Rust ratchet kernel (`temper_drc_rs.ratchet_check`)
is untouched. It is differential-pinned against the pre-migration oracle
(`test_drc_ratchet_rust_differential.py`), and the cap signal is a property
of the *measurement*, not of the comparison — it belongs in the marshalling
layer, exactly where `_check_board` builds the counts.

## 4. Tests

- **Rust** (`drc_count.rs`, `cargo test --no-default-features`): 10 unit +
  proptest properties — `is_capped` iff `count == cap_for(category)` over the
  whole space; `honest_count` complements `is_capped`; `display` matches cap
  state; off-cap counts (below *and* above) are honest; exact-cap cases;
  `creepage`/`clearance`-199 carve-outs; `cap_for` table; error Display. Plus
  a doctest demonstrating the `honest_count()` `Result` pattern.
- **Python shims** (`tests/validation/test_drc_count_shim.py`): 12 cases over
  the delegation surface, including the carve-outs.
- **Ratchet** (`test_drc_ratchet.py::TestCapSaturationDetection`): 6 cases
  driving `_check_board` with stubbed kicad-cli results — capped flag
  populated for errors and warnings, NOT populated for `creepage` 199 /
  `clearance` 199 / above-cap values.
- **CI gate wiring** (`test_ci_check_drc.py::TestCapSaturationGuardWiring`):
  3 cases — measured capped count → exit 4; saturated ceiling value → exit 4;
  uncapped categories → exit 0.

All new suites green; the touched consumer suites green
(`tests/regression/` 487 passed, `test_drc_api_*` + `test_drc_check_vacuity_guard`
41 passed, `scripts/tests` drc/ceiling/determinism suites green, ruff clean,
`cargo clippy --no-default-features` clean, `cargo check --features python`
clean).

## 5. What this task deliberately did NOT do

- **No `drc_ceiling.json` change.** Current values are de-saturated (the
  PR #1178 correction); the type is enforcement for the *future*. Raising or
  touching any ceiling requires an owner R27 approval — out of scope.
- **No `pcb/temper.kicad_pcb` change.**
- **No `measure_uncapped_drc.py` change.** It already carries the correct
  per-category caps plus the `SAFE_MARGIN`/determinism protocol; `DrcCount`
  is the exact-cap type, complementary to it.
- **No kernel or oracle change** (the ratchet kernel and all pinned
  differential oracles are untouched — the differential suites pass
  unchanged).

## 6. Pre-existing red found while testing (not caused by this change)

`scripts/tests/test_ceiling_raise_evidence_corpus.py::test_controls_are_silent_and_injections_are_named`
(and the `test_full_corpus_covers_all_four_scenarios` variant) fail on
`origin/main` **unchanged**: the `fully-evidenced-raise-control` fixture uses
`measured_at_commit: "0" * 40`, which the (correct, 2026-08-07) commit-
resolvability enforcement in `DrcRatchet.validate_raise_evidence`
(`git cat-file --batch-check`) now flags as unresolvable — the corpus test
was written the same day and never updated to use a resolvable synthetic
commit. Verified against a detached `origin/main` worktree at the same base:
identical FAIL. Per the serial un-silencing discipline, this is reported,
not fixed in this PR.

## 7. Follow-ups worth an owner decision

1. **Update the corpus control** to a resolvable synthetic commit (e.g. a
   real SHA from the synthetic repo, or drop the control's reliance on an
   unresolvable `0000…` when it is not the class under test).
2. **Ratchet message text**: the kernel-composed message cannot carry the
   "CAPPED" marker (bit-identical contract); a future kernel revision could
   add a dedicated saturated-category line without touching the pinned
   comparison semantics.
3. **`_drc_api.run_drc` aggregate counts** (`error_count`/`warning_count`)
   remain sums over categories — a capped category inside the sum makes the
   aggregate a floor too. The per-type classification is the decisive signal;
   consumers of aggregates should route through the per-type breakdown
   (which the ratchet now labels) before treating a total as truth.

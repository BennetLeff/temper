<!-- provenance: commit=fb03b8743334f75ef95f1b64b8867db05365d56b dirty=true (only `opencode.json`, which is not a tier build input and is untouched by this document; every measurement below was taken against `origin/main` at this commit, or against PR #1473's head `28e7ccc92` where the text says so, or against the live Cloudflare account on 2026-08-24) -->

# WASM Verification Tier — Phase 5 Verdict (R24–R28)

**Date:** 2026-08-24
**Base:** `origin/main` @ `fb03b8743334f75ef95f1b64b8867db05365d56b`
**Branch:** `docs/wasm-tier-phase5-verdict`
**Plan under verdict:** `docs/plans/2026-08-10-001-feat-wasm-tier-phase5-plan.md`
(itself Phase 5 of `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md`,
R24–R28, governed by D12–D15)
**Scope:** this document only. No source, CI, plan or baseline file is touched
by this change.

Phase 5 has never had a verdict. This document records one, because the phase
as framed can no longer be completed: its own plan already found that its
headline value proposition (D12 pool relief) does not survive measurement, and
the substitutive half it retained (R24) has since run out of targets. Leaving
R24–R28 open against a goal that is not reachable the way it was written
misdescribes the tier's state to everyone who reads the plan directory.

---

## 1. The verdict table

| Req | Statement (abbreviated) | Verdict | Consequence |
|---|---|---|---|
| R24 | Each crate's `cargo test` suite leaves GitHub Actions once its R19 agreement sustains | **VACUOUS — no targets remain** | Nothing is left to remove that is not coverage. See §2.1 |
| R25 | Pool relief measured per job or step actually removed, not per crate | **SATISFIED; relief = 0** | Measured 2026-08-10, re-confirmed 2026-08-24. See §2.2 |
| R26 | Python differential/PBT suites remain on GitHub Actions permanently | **SATISFIED** | Never in question; no change proposed or made |
| R27 | Wasm-incompatible tests self-select via the R19 comparison | **PARTIAL** | The mechanism works and has produced 18 catalogued entries; it samples at a 12-night cadence. See §3 |
| R28 | The moved suites' tier verdicts become their required PR context | **BLOCKED — but not by what the workflow says** | `required-checks.json` holds zero wasm contexts. The stated blocker (R22/R23 durability) was closed on 2026-08-11 and re-verified for this document. The real blocker is R19 sustained per-crate agreement, which §3 shows is not producible at the current cadence. See §5 |

**Governing decisions:**

| Dec | Statement (abbreviated) | Standing |
|---|---|---|
| D12 | The tier is also CI tooling for the Rust suites; pool relief is the immediate efficiency win | **FALSIFIED** on the relief clause (relief = 0); the tooling clause holds and is delivered |
| D13 | Transition is suite-by-suite as R19 agreement sustains | **UNEXERCISED** — no suite ever transitioned under it |
| D14 | Wasm-sensitive tests self-select via R19 | **HOLDS**, at the cadence §3 measures |
| D15 | End-state is GitHub Actions running only CPython-bound work | **SUBSTANTIALLY TRUE, but not by transition.** See §2.3 |

### The verdict sentence

> **Phase 5 is complete by exhaustion, not by achievement.** Its additive half
> shipped and works: the deployed tier serves 30,349 executable tests across 12
> Workers, sweeps all of them nightly, and gives every PR an advisory verdict
> scoped to the tiers its diff touches. Its substitutive half (R24, D13) never
> executed and now has nothing left to execute against — the last Rust suite on
> the PR path is `temper-orchestration`'s, which is structurally native-only and
> whose removal would delete coverage rather than duplication. Its gating half
> (R28) is blocked — but not by the durability machinery every current document
> names, which has been closed since 2026-08-11. It is blocked by the same
> 12-night R19 cadence §3 measures. **R24 should be retired; R28 should be
> re-pulled as a separate phase with the correct premise.**

---

## 2. The measurements that decide it

### 2.1 R24 has no targets left

Exhaustive scan of `.github/workflows/*.yml` at this commit, excluding the
tier's own three files:

```
$ grep -rn "cargo test" .github/workflows/*.yml | grep -v wasm-tier
python-tests.yml:1205  cargo test --manifest-path packages/temper-orchestration/Cargo.toml $test_args -- --nocapture
python-tests.yml:1207  cargo test --manifest-path packages/temper-orchestration/Cargo.toml --lib "grid_hv::tests::"
python-tests.yml:1209  cargo test --manifest-path .../temper-orchestration/Cargo.toml --no-default-features --lib "host_math::tests::host_libm_symbols_actually_resolve"
python-tests.yml:1257  cargo test --doc --no-default-features --manifest-path "$manifest"    # loop over 14 manifests
```

That is **one crate's lib suite plus a doctest loop**. `temper-geometry` and
`temper-design-bundle` left in #978 (2026-08-10) — before Phase 5's plan was
written, and not claimed by it as relief under R25.

`temper-orchestration` is not a valid R24 target and never will be:

- Its registered wasm32 corpus is 1,041 tests (measured on #1473's head; 1,034
  at this commit, frozen by the parse break §5.1 describes). Its native lib
  suite is 1,086. The gap is `proptest` dev-dependency modules, `#[cfg(feature =
  "python")]` pyo3 code, and — newly identified by #1473 — `subprocess_stage`,
  whose 7 tests trap on `wasm32-unknown-unknown` with `no pids on this platform`.
- Doctests are structurally outside the registry mechanism entirely; no tier
  build can carry them.

Removing that step would not move coverage to the tier. It would delete it.
R24's mechanism (D13: "each crate leaving GitHub Actions as its R19 agreement
sustains") presumes a population of duplicated suites. That population is empty
and has been since before the phase was planned.

### 2.2 R25's relief, re-confirmed at zero

The Phase 5 plan measured this on 2026-08-10 and found the removable-job count
was 0, because `rust-checks` also runs `cargo clippy -D warnings` across 13
crates and survives the removal of any `cargo test` step in it. That holds at
this commit: the job still exists, still runs clippy, and the one `cargo test`
step left inside it is the one §2.1 shows must stay.

R25 is satisfied in the sense that matters — it demanded relief be *counted
honestly at the job level*, and counted honestly it is zero. The requirement
did its job by refusing to let the phase claim a win it did not have.

### 2.3 D15 is substantially true, and Phase 5 did not cause it

D15's end-state is "GitHub Actions running only CPython-bound work." What
GitHub Actions runs today, on the Rust side of the PR path: one crate's lib
suite (187 tests, measured live in run 31500695767 on 2026-08-11), one doctest
loop over 14 manifests, `cargo check`, and `cargo clippy --all-targets`. The
last two lint rather than execute and can never move to a Workers isolate.

So the end-state is close to reached — but by #978's removals and by the fact
that nine of the twelve tier crates never had a `cargo test` step to begin
with, not by any suite-by-suite transition under D13. **D13 was never
exercised.** Recording D15 as "achieved" without that caveat would credit the
transition mechanism for an outcome it did not produce.

---

## 3. The finding this verdict adds: native execution cadence

This has not been written down anywhere, and it bears directly on R27.

`wasm-tier-nightly.yml`'s R19 native-arm rotation (added 2026-08-11, a
well-reasoned cost fix — its header carries the full argument and the 88s-of-175s
measurement that motivated it) runs the native `cargo test` arm for **exactly one
tier per night**, selected by day-of-year modulo the tier count. There are now 12
tiers. Combined with §2.1:

> **For 11 of the 12 tier crates, native `cargo test` runs on its rotation night
> and nowhere else — at most once every 12 nights.**

`temper-orchestration` is the sole exception, because it kept its PR-path step.

Two consequences:

1. **R27's self-selection samples at a 12-night cadence.** D14's mechanism is
   sound — a test that never agrees never leaves — but "never agrees" is
   re-derived for any given crate roughly twice a month. The 18 catalogued
   expected failures (§4) are real and well-reasoned, so the mechanism is not
   vacuous; it is slow. R27 is PARTIAL for that reason, not because it fails.
2. **A native-only regression in 11 of 12 crates has a mean detection latency of
   ~6 nights and a worst case of 12.** The nightly's wasm32 build+execute step
   deliberately does *not* rotate (it feeds R5.1 staleness detection), so "does
   it pass on wasm32?" is answered nightly for everything. "Does it still pass
   natively?" is not.

Nothing here argues the rotation was wrong. It argues that the *evidence
standard R24 was conditioned on* — D13's "as its R19 agreement sustains" — is
not producible at this cadence, which is an independent reason R24 cannot be
executed as written even if it had targets.

---

## 4. What Phase 5 actually delivered

Measured 2026-08-24 by querying every deployed Worker's `/health` and by the
last nightly sweep (run 32693386339, 2026-08-24 05:23Z, conclusion success):

| tier | deployed | | tier | deployed |
|---|---:|---|---|---:|
| `temper-geometry` | 8,386 | | `temper-drc-rs` | 3,283 |
| `temper-io-types` | 6,944 | | `temper-quality-oracle` | 2,601 |
| `temper-rust-router-core` | 3,462 | | `temper-constraint-compiler` | 1,899 |
| `temper-thermal` | 2,641 | | `temper-orchestration` | 1,022 |
| `temper-design-bundle` | 60 | | `temper-constraints` | 29 |
| `temper-rust-router` | 20 | | `temper-pcl-ir` | 2 |

**Total: 30,349 executable tests. 30,331 pass. 18 expected-fail**, every one
carrying a class and a written reason in its crate's manifest (10
`wasm_expected_failures_geometry.json`, 4 `wasm_expected_failures.json`, 4
`wasm_expected_failures_thermal.json`). Zero unexpected failures, zero orphan
exclusions, zero unexpected passes.

Also delivered, and worth crediting because none of it is what the phase set out
to build:

- `wasm-tier-pr.yml` — a per-PR advisory verdict, scoped to the tiers each diff
  touches, costing zero `cargo` (it curls Workers and compares JSON). This is
  D5.2's additive win and it works.
- `wasm-tier-deploy.yml` — push-triggered, content-hash-verified deploy
  (R5.1: deployed == CI-built, sha256 per tier).
- `wasm-tier-staleness-watch.yml` — a standalone hourly watchdog, green.
- A drift-gate pair in Fast Gates (registry-vs-source, family-map-vs-registry)
  that has now caught three separate silent-drift incidents the freshness
  machinery is structurally blind to. See §6.

---

## 5. The gating question (R28) — and the stale premise everyone is reasoning from

`.github/required-checks.json` contains **zero** wasm contexts. Every current
document explains that with the same reason, and **the reason is out of date.**

`wasm-tier-pr.yml`'s header states it most directly:

> Making a tier verdict a required PR context crosses R22/R23 — the
> dead-letter, idempotency and reconciliation machinery that is unbuilt BY
> DESIGN under D10.

**R22/R23 is not unbuilt. It was closed on 2026-08-11 by #992**
(`docs/evidence/2026-08-11-wasm-tier-r22-r23-durability.md`), with dead-letter
handling, idempotent work keys, a `reconcile()` pass, and replication — each
backed by a fault-injection test rather than by inspection.

That workflow file was created **2026-08-10** in #951, one day before #992
landed. Its header was true when written and became false the next day, and
nothing updated it. Phase 5's D5.4 carries the same claim from the same
pre-#992 moment.

**Re-verified for this document at `9546f568e`**, rather than taken from the
2026-08-11 doc at face value:

```
$ node tools/wasm/test_sweep_durability.mjs
All cases passed: the sweep accounts for every dispatched test under a lost
response, a duplicate/conflicting delivery, a hung response, a transient
fault, and a partial outage
```

`sweep_multi_worker.mjs` carries `reconcile()` with its own `exit(2)`, distinct
from a test failure, and both the nightly and the PR workflow already treat any
nonzero exit as a sweep failure — so R22/R23's failure modes are loud today,
with no workflow edit required.

### What actually blocks R28

#992's own §5 named it, and this verdict's §3 measures it:

1. **R19 sustained per-crate agreement.** R19's text: *"sustained agreement is
   the bar for licensing any later gating under R15."* §3 shows any given
   crate's agreement is re-derived once every 12 nights. That is the blocker,
   and it is a measurement campaign, not an engineering gap.
2. **R10's `kicad-cli` equivalence bar**, for the DRC verdict specifically, if
   R15 is read at its literal definition. Q1 in the parent plan — *"how much
   agreement, over what corpus, sustained for how long"* — is still open and
   still has no terminal condition.

So the disposition is **not** the two-option choice an earlier draft of this
document stated. The engineering prerequisite is already paid for. What remains
is to produce the agreement evidence, per crate, at a cadence that can license
promotion — then promote contexts one crate at a time. That is a real phase with
a tractable premise, and §7 recommends pulling it.

### The pattern, noted because it is now four deep

A workflow header's prose was load-bearing for a strategic decision and had been
wrong for thirteen days. §6.2's three registry-drift incidents are the same
shape: a document or artifact that was true when written, that nothing
re-derives, and that a later reader treats as current. This document's own first
draft repeated the `wasm-tier-pr.yml` claim before checking it against
`docs/evidence/`, which is precisely how the pattern propagates.

---

## 6. Drift found while measuring

Recorded here because each was found by taking this verdict's own measurements,
and none is fixed by this document.

### 6.1 The registry drift gate has been red on `main` since 2026-08-21, and truncated

`gen_wasm_test_registry.py --check --crate temper-orchestration` exits 1 with
`unbalanced braces at line 814`. `module_body()` located a module's extent with
`line.count("{") - line.count("}")` on raw source, and
`packages/temper-orchestration/src/state_ser.rs:987` is:

```rust
let e = native_from_json("{not json").unwrap_err();
```

Four characters of deliberately-malformed JSON test data, parsed as Rust syntax.
Landed 2026-08-21 in #1434. Red on `main`'s Fast Gates in run 32688222591.

Two consequences, the second worse than the first:

- `state_ser`'s 7 tests — pure Rust, no pyo3, no proptest, fully portable — were
  never registered, so the tier verifies a corpus smaller than the commit's. This
  is precisely the failure the step's own error text describes.
- **The gate was checking 7 of 12 crates.** Both wasm steps open with
  `# No -e: exit codes are inspected here`, but `run:` defaults to `bash -e {0}`
  and no `shell:` overrides it anywhere in the workflow. The loop aborted at
  `temper-orchestration` (7th alphabetically); `temper-pcl-ir`,
  `temper-quality-oracle`, `temper-rust-router`, `temper-rust-router-core` and
  `temper-thermal` never ran. The `failed` accumulator and its `::error::` text
  naming every stale crate were unreachable code.

**PR #1473 fixed both**, plus added a `std-process-no-wasm32` exclusion predicate
for `subprocess_stage`. Independently verified for this verdict at its head
`28e7ccc92` before merge (all 12 registries green — 30,375 tests registered in
total — family-map check green, 28 new brace-parser tests passing), and
**merged 2026-08-24T17:52Z as `9546f568e`** by admin override: `Required Python
Tests` aggregated four checks independently red on `main` and unrelated to it,
and #1473 turned Fast Gates red→green while adding no new reds. Re-verified on
`main` after the merge: all 12 registries and the family map check clean.

### 6.2 The freshness machinery cannot see registry drift — third occurrence

`check_deployed_freshness.mjs` compares *deployed* against *CI-built*. Both
sides build from the **committed** registry, so a stale registry is invisible to
it: the deployed Worker is internally consistent and wrong about the source.
This has now produced three incidents:

| # | Drift | Size | Found by |
|---|---|---|---|
| 1 | `temper-design-bundle` registry stale since #1134 | 46 vs 51 | drift gate (2026-08-15 audit) |
| 2 | `test_family_map.json` unregenerated since the property campaigns | 1,719 vs 3,283 | drift gate (same audit) |
| 3 | `temper-orchestration` frozen by the §6.1 parse break | 1,034 vs 1,041 | drift gate, while red |

The drift gate is the only instrument that catches this class. That is the
argument for treating §6.1 as urgent rather than cosmetic: for three days the
repo's sole detector of the failure mode that has bitten it three times was both
red and silently checking a subset.

### 6.3 The per-family coverage report describes 11% of the corpus

`tools/wasm/gen_test_family_map.py` is `temper-drc-rs`-only by construction (its
docstring and its `ELIGIBLE` import both scope it there). So `coverage_report.py`'s
R7/R8 per-family non-vacuity report covers **3,283 of 30,349** deployed tests.
Defensible — the nine families are a DRC-rules taxonomy and do not obviously
extend to `temper-io-types` — but it means the three largest tiers (geometry
8,386; io-types 6,944; router-core 3,462) have no non-vacuity reporting at all.
Not a defect against any current requirement; a gap worth naming before anyone
cites the coverage report as tier-wide.

### 6.4 Stale prose in `wasm-tier-nightly.yml`

The R19 rotation header and the step summary at line 707 still say "nine tiers"
and "the other eight tiers". There are 12; the correct figures are twelve and
eleven, and the rotation cycle is 12 nights rather than the "under 1.5 weeks"
the header claims. Cosmetic, but it is the prose a reader uses to size §3's
cadence.

---

## 7. Recommended disposition

1. **Land #1473.** It clears a red trunk gate, restores 5 crates to that gate,
   and adds 7 portable tests to the tier's corpus.
2. **Mark `docs/plans/2026-08-10-001-feat-wasm-tier-phase5-plan.md` `status:
   completed`** with this document as its verdict, and record R24 as vacuous and
   R28 as blocked in the parent plan rather than leaving them open.
3. **Correct the stale R22/R23 prose at its three sources** — `wasm-tier-pr.yml`'s
   header, Phase 5's D5.4, and any document repeating them — so the next reader
   does not re-derive the wrong blocker. The durability machinery has been closed
   since 2026-08-11.
4. **Retire R24.** It has no targets and its licensing condition is unproducible.
   It should not be carried forward into any successor phase.
5. **Pull a new phase for R28 with the correct premise: an R19 sustained
   per-crate agreement campaign, then context promotion crate by crate.** Its
   first unit is the §3 cadence, not durability. Drafted as
   `docs/plans/2026-08-24-001-feat-wasm-tier-phase6-plan.md`.

---

## 8. Reproducing every number here

```bash
# §2.1 — the PR path's remaining cargo test invocations
grep -rn "cargo test" .github/workflows/*.yml | grep -v wasm-tier

# §4 — deployed corpus, live
for w in tier geometry thermal design-bundle router-core constraint-compiler \
         quality-oracle io-types pcl-ir orchestration constraints rust-router; do
  curl -s "https://temper-wasm-$w.bennetleff.workers.dev/health"; echo
done

# §4 — expected-failure counts
for f in tools/wasm/wasm_expected_failures*.json; do
  echo "$f $(python3 -c "import json;d=json.load(open('$f'));print(len(d.get('expected_failures',{})))")"
done

# §5 — required contexts carrying a wasm verdict
python3 -c "import json;print(json.dumps(json.load(open('.github/required-checks.json'))).lower().count('wasm'))"   # -> 0

# §6.1 — the parse break, on this commit
python3 scripts/gen_wasm_test_registry.py --check --crate temper-orchestration; echo "exit=$?"

# §6.3 — family map scope
python3 tools/wasm/gen_test_family_map.py --check    # -> 3283 tests mapped (temper-drc-rs only)
```

## 9. Sources

- `docs/plans/2026-08-10-001-feat-wasm-tier-phase5-plan.md` — the plan this verdicts.
- `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md` — R24–R28, D12–D15.
- `docs/evidence/2026-08-07-wasm-tier-phase1-verdict.md`,
  `docs/evidence/2026-08-05-wasm-tier-phase0-verdict.md` — the two prior phase
  verdicts, whose format this follows.
- `docs/evidence/2026-08-11-native-cargo-test-duplication-inventory.md` — the
  §2.1 inventory this re-measures.
- `docs/evidence/2026-08-15-wasm-tier-gap-audit.md`,
  `docs/evidence/2026-08-15-wasm-tier-redeploy-prep.md` — incidents 1 and 2 in §6.2.
- `.github/workflows/wasm-tier-{pr,nightly,deploy,staleness-watch}.yml` — the
  four workflows, whose headers carry the arguments §3 and §5 defer to.
- `docs/evidence/2026-08-11-wasm-tier-r22-r23-durability.md` — #992's durability
  work, the §5 correction's source, re-verified at `9546f568e`.
- PR #1473 — the §6.1 fix, verified at `28e7ccc92` and merged as `9546f568e`.
- `docs/plans/2026-08-24-001-feat-wasm-tier-phase6-plan.md` — the successor phase
  §7.5 recommends.

<!-- provenance: commit=66f84b8767a516f36745fc7155b1d722031c113c dirty=false -->

# WASM tier U4 closure — the coverage gap was artifact staleness, not test coverage

**Date:** 2026-08-10
**Commit:** `66f84b8767a516f36745fc7155b1d722031c113c` (`origin/main`)
**Board:** `pcb/temper.kicad_pcb` sha256 `6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64`
**Run:** GitHub Actions `31439341187` (`wasm-tier-nightly.yml`, `workflow_dispatch`)

**Supersedes, in fact:** the U4 PARTIAL verdict in
`docs/evidence/2026-08-07-wasm-tier-phase1-verdict.md`, and the "family
coverage thin" precondition that verdict places on Phase 2.

## Bottom line

The Phase 1 verdict recorded U4 as PARTIAL on a coverage-spread finding —
"`drc` has 1 registered test, `routing` has 2, and `erc` has 0 of the 95
total" — and named it "the Phase 2 precondition." That finding described the
contents of `.wasm` modules deployed on 2026-08-07, not the contents of the
test suite. Redeploying the same modules from `main` closes it:

| | 2026-08-07 deploy | 2026-08-10 redeploy |
|---|---:|---:|
| tests on the deployed tier | 147 | **1,708** |
| share of the 1,751 native tests | 8.4% | **97.5%** |
| R19 agreement rate | 1.0 | **1.0** |
| disagreements | 0 | **0** |
| native-only (no tier execution) | 1,605 | **43** |
| wasm32-only (no native counterpart) | 1 | **0** |
| sweep throughput | 387.9 tests/s | **852.3 tests/s** |

**No tests were written.** The gap was four-day-old deployed artifacts.

## Per-family

| family | deployed 2026-08-07 | deployed 2026-08-10 |
|---|---:|---:|
| drc | 1 | **1,510** |
| emc | 14 | 15 |
| erc | 0 | 12 |
| safety | 0 | **25** |
| placement | 12 | 18 |
| routing | 2 | **18** |
| infra | 109 | 110 |
| **full corpus** (`temper-wasm-tier`) | **147** | **1,708** |

The seven families sum to exactly 1,708, matching the full-corpus module: a
clean partition, no double-counting, no orphans. Counts read from each
Worker's `/health` (`test_count`) after deploy, and independently from each
staged module's `temper_test_count()` export before deploy — the two agree.

## How the staleness was established

1. `GET /accounts/{id}/workers/scripts` reported `modified_on: 2026-08-07`
   for every `temper-wasm-*` script.
2. The same nightly run publishes both arms: the local job builds the
   wasm32 module from the commit under test (1,708 registered tests), while
   the deployed job reported 147. A 1,561-test discrepancy between two arms
   of one workflow, invisible to both.
3. Rebuilding the modules from `bd85d76e` reproduced 1,708 locally before
   any deploy, confirming the suite had grown and the artifacts had not.

## The measurement that matters

Agreement did not degrade when 1,561 additional tests were exposed:

```
native : 1751 passed, 0 failed
wasm32 : 1708 total, 1704 passed, 4 expected-fail, 0 unexpected
compare: agree_pass 1704, disagree 0, expected_fail 4,
         native_only 43, wasm32_only 0, agreement_rate 1.0
sweep  : 1708 tests, 2004 ms wall, 852.3 tests/s @ concurrency 64
```

This is the load-bearing result. An agreement rate of 1.0 over 147 tests is
weak evidence — it is consistent with a tier that happens to carry only the
easy cases. The same rate over 1,708 tests, reached by adding 1,510 `drc`
tests to a family that previously carried one, is the first evidence that
wasm32 and native genuinely agree across the DRC engine.

Throughput also improved with scale (387.9 → 852.3 tests/s), which is the
expected shape: per-request isolate startup amortises over more work per
family, and the 7 families run concurrently.

## The 43 native-only tests

Down from 1,605. These have no wasm32 counterpart at all — they are not
disagreements and not failures. Under D14 this is the self-selecting
wasm-incompatible subset, and it is now small enough to enumerate and
classify, which `docs/plans/2026-08-10-001-feat-wasm-tier-phase5-plan.md`'s
U3 requires before any suite leaves GitHub Actions. The 4 expected failures
(`b7-pow-divergence-absent`, `no-dynamic-loader`, and the host-libm classes
in `tools/wasm/wasm_expected_failures.json`) are unchanged.

## What this does and does not license

**Does:** removes the coverage-spread precondition the Phase 1 verdict
places on Phase 2, and satisfies the deploy half of Phase 5 U1's
evidence-of-closure ("a nightly run reporting `wasm32.total == 1708` from
the deployed path").

**Does not:** make the tier's verdicts trustworthy without a staleness
control. This closure was produced by a manual redeploy, which is exactly
the mechanism that failed for four days. Phase 5 U1's other half — comparing
the deployed registry size against the count built from the commit under
test, and failing loudly on mismatch — is unbuilt, and until it exists this
tier can silently drift back to answering for a corpus that is not in the
repository. R5.2 (reproducible deploy) is likewise unbuilt: the redeploy
above ran from an operator shell, not from CI.

**Does not:** grant merge authority. R22/R23 durability remains deferred
under D10, and every tier verdict stays advisory.

## Reproduction

```
# stage (8 wasm32 builds)
bash scripts/stage_wasm_families.sh

# deploy (needs a token with Workers Scripts:Edit)
cd packages/temper-worker
for d in families/{drc,emc,erc,safety,placement,routing,infra} .; do
  (cd $d && npx wrangler@4 deploy)
done

# verify
for w in tier drc emc erc safety placement routing infra; do
  curl -s https://temper-wasm-$w.bennetleff.workers.dev/health
done
```

Deployed version IDs, 2026-08-10: drc `0f35d529`, emc `91f37242`, erc
`4550bd71`, safety `5f6ea4e3`, placement `d2199a6e`, routing `e796846d`,
infra `c5b65dc2`, tier `18f2ef9b`.

## Related

- `docs/plans/2026-08-10-001-feat-wasm-tier-phase5-plan.md` — U1 (redeploy +
  staleness control), U3 (the 43-test classification this enables).
- PR #929 — the wasm32 build fix, without which the nightly's local arm never
  ran and this discrepancy could not have been observed.
- PR #932 — the preflight fix, without which the deployed arm never ran.
- `docs/evidence/2026-08-07-phase1-u8-multi-worker.md` — the per-family
  layout and the 2026-08-07 counts this document measures against.

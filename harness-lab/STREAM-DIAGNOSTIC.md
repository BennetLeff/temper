# Stream diagnostic: obstacle batch 2

## Question and frozen decision rule

The first obstacle batch produced valid final boards in all three trials, but only two complete run audits. Two responses in trial 2 returned HTTP 200, emitted initial reasoning events, then hit the local relay's 60-second read timeout. The runtime immediately reissued the same input history. There was no recorded HTTP 429. Provider delay, congestion, and unreported throttling remain possible; the records do not identify their upstream cause.

The user authorized this diagnostic with “go for it” on September 9, 2026. It uses the already approved U3/C9 obstacle payload and Muse Spark 1.3 Contributor Free through OpenCode Zen, with its accepted Contributor terms. No provider/model fallback is admitted.

**Before model execution:** run the local stream tests, requalify the 10 obstacle controls and 23 routing regression cases, then freeze source and qualification hashes. Run one inspection-only preflight and three sequential fresh obstacle trials. Keep the task, hints, native validator and five-minute/ten-edit trial budget unchanged. Retain every attempt, and do not retry a failed trial.

**Batch pass:** all three runs must meet the existing complete wire/action audit and independent final-board acceptance criteria. Any incomplete response, unexpected retry/concurrency, missing evidence or exceeded budget remains indeterminate/failing for the batch. The first batch's two passes and one indeterminate result remain unchanged.

**Diagnostic interpretation:** a clean batch demonstrates operation under the revised transport policy on this fixture. A recorded read gap longer than 60 seconds followed by completion demonstrates that the old cutoff would have interrupted that response. A 429 or explicit provider limit message is evidence of throttling. Absence of those signals cannot rule throttling out. Three successful trials do not estimate provider reliability with useful precision.

## Revised transport policy

- An upstream read can wait for the remaining five-minute trial budget; each read recomputes that remaining time. The process deadline stays bounded as well.
- One upstream request at a time. An incomplete response, non-200 response, transport error or concurrent request closes admission for the rest of that trial. OpenCode may attempt a retry locally, but the relay does not forward it. This enforces the policy independently of the ineffective provider `maxRetries: 0` setting observed in batch 1; it does not claim that we changed OpenCode's internal retry implementation.
- Preserve response status and an explicit allowlist of response headers: content type, date, Retry-After, request ID and request/token rate-limit counters/reset values. Never persist request authorization headers or response cookies.
- Record request start time, attempted-upstream flag, elapsed time and maximum read gap. The first gap includes connection/header latency; later gaps measure intervals between body reads. This is relay-observed timing, not a measurement of server compute time.
- Close the active upstream socket and join handlers before auditing evidence at shutdown. Complete wire and action requirements remain unchanged.

## Local reproduction

Five real localhost-socket fault-injection tests were added to the existing runner test file. Only the upstream destination is substituted; no model is involved. All five failed against the old implementation for their intended assertions:

1. A stream silent for **61 seconds**, then complete: old relay lost the completion.
2. Incomplete EOF followed by retry: old relay sent two upstream requests.
3. HTTP 429 followed by retry: old relay sent two requests; revised test also asserts rate-limit header capture and cookie exclusion.
4. A silent stream exceeding a short trial deadline: old relay ignored that deadline.
5. Two concurrent requests: old relay forwarded both.

The ordinary transport and native qualification suites are separate from model performance. [Every PCB control is defined here](VALIDATOR-CONTROLS.md).

## Results

**All three fresh trials passed** the original strict run and board criteria. The preflight passed in 6.32 seconds with zero edits.

| Trial | Time | Edits | Run audit | Host board check | Largest read gap |
|---|---:|---:|---|---|---:|
| 1 | 68.71 s | 2 | pass | pass | 53.39 s |
| 2 | 80.43 s | 2 | pass | pass | 64.48 s |
| 3 | 93.94 s | 2 | pass | pass | 77.00 s |

The maximum read gaps in trials 2 and 3 were 64.48 and 77.00 seconds, followed by successful completion. Both are live examples that exceed the former cutoff. It supports removing the premature local timeout; it does not establish why the provider was silent in the original failed run.

[Full trial results](evidence/stream-zen-results.json), [preflight](evidence/stream-zen-preflight.json), [timing/status summary](evidence/stream-model-status.json), [complete model and native traces](evidence/stream-zen-traces.tar.gz).

Local verification: all 15 Python tests, 2 Rust tests, lint/format/compilation, 10 obstacle controls and 23 routing regression cases passed. The five new stream tests first failed on the old runner, then passed on the revised one. [Review and test record](evidence/stream-review.json), [obstacle qualification](evidence/stream-obstacle-qualification.json), [routing regression](evidence/stream-routing-regression.json), [native control traces](evidence/stream-local-traces.tar.gz).

All 15 scored upstream requests returned HTTP 200, with zero wire errors and no locally blocked retry/concurrency requests. No allowlisted rate-limit headers were returned.
The prior batch remains two clean passes and one indeterminate run. This fresh result neither overwrites nor rescores it.


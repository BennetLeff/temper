/**
 * Durability machinery for the WASM tier sweep — R22 (loss-proof result
 * delivery: dead-letter handling, idempotent keys, a reconciliation pass)
 * and R23 (replication outside the primary store), scoped to the harness in
 * tools/wasm/ per docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md.
 *
 * ## The invariant this file exists to hold
 *
 * A sweep dispatches one HTTP request per test. "Accounted-for" means every
 * dispatched (family, index) pair ends up with exactly one terminal outcome
 * — pass, fail, or explicitly-errored — never silently absent from the
 * tally. A missing result must fail the sweep loudly; it must never let the
 * sweep report green over a corpus it did not actually hear back from in
 * full. That is the same shape of bug `check_deployed_freshness.mjs` was
 * built to close for deployed-vs-built test counts (see its header, "a test
 * COUNT is a weak proxy... additive, not a replacement"); here the two
 * counts are "dispatched" and "accounted-for", and the fix is the same
 * genre: an explicit comparison that fails loudly on a gap, not an
 * assumption that the two numbers march together because the code
 * currently happens to keep them that way.
 *
 * ## What is, and is not, built here
 *
 * There is no server-side durable store for this tier (the deployed Workers
 * are stateless — `packages/temper-worker/src/worker_core.js` executes a
 * test and returns a JSON body; nothing is persisted server-side). So the
 * "primary store" R22/R23 speak of is the CLIENT's in-memory result set for
 * the run, and the failure modes worth defending against are the ones that
 * actually threaten it in this architecture:
 *
 *   - a single dropped/hung HTTP response (network fault, cold start,
 *     transient 5xx) silently thinning the tally  -> retry + dead-letter,
 *   - a retried request whose original attempt's response arrives late,
 *     double-counting or corrupting the verdict for that test -> idempotent
 *     keys (ResultLedger),
 *   - "did every dispatched test get a terminal outcome" never being
 *     checked at all -> reconcile(),
 *   - the whole run's results living only in one process's memory until a
 *     single JSON.stringify+writeFileSync at the very end, so a crash one
 *     millisecond before that write loses everything computed -> streamed,
 *     incrementally-flushed replica log + a second on-disk copy of the
 *     final summary (writeReplicatedSummary).
 *
 * What is NOT built: off-host replication (S3/R2/etc). That needs storage
 * credentials this task has no access to provision. Both replica outputs
 * this file writes land on the same host/disk as the primary — real
 * insurance against a crashed *process* or a truncated *write*, not against
 * a dead *disk*. Recorded plainly, not glossed over, in
 * docs/evidence/2026-08-11-wasm-tier-r22-r23-durability.md.
 */

import { appendFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

/** The idempotent key for one dispatched work item. Stable and unique across
 *  a single sweep: family names are unique across the topology
 *  (tier_topology.mjs's `validate()` enforces this) and index is a per-family
 *  ordinal, so the pair identifies exactly one test invocation. */
export function workKey(family, index) {
  return `${family}#${index}`;
}

/**
 * Idempotent result store. Exactly one terminal entry survives per work key
 * no matter how many times `record()` is called for it — a retried request
 * whose original response arrives late (or a genuine duplicate delivery)
 * cannot inflate the tally, and cannot silently overwrite a verdict with a
 * different one without that being visible.
 */
export class ResultLedger {
  constructor() {
    /** @type {Map<string, object>} key -> the first terminal result recorded */
    this.entries = new Map();
    /** @type {Array<{key: string, first: object, duplicate: object}>} */
    this.conflicts = [];
    this.duplicatesIgnored = 0;
  }

  /**
   * Record a terminal outcome for `key`. Returns "recorded" the first time,
   * "duplicate" when the same key resolves to an equivalent outcome again
   * (a re-delivered response for a retried request — ignored, not tallied
   * twice), or "conflict" when the same key resolves to a DIFFERENT outcome
   * (kept: the first-recorded verdict; the conflict itself is preserved in
   * `this.conflicts` for visibility rather than silently discarded).
   */
  record(key, result) {
    const existing = this.entries.get(key);
    if (existing === undefined) {
      this.entries.set(key, result);
      return "recorded";
    }
    if (existing.status === result.status && existing.name === result.name) {
      this.duplicatesIgnored += 1;
      return "duplicate";
    }
    this.conflicts.push({ key, first: existing, duplicate: result });
    return "conflict";
  }

  size() {
    return this.entries.size;
  }

  has(key) {
    return this.entries.has(key);
  }

  get(key) {
    return this.entries.get(key);
  }

  values() {
    return [...this.entries.values()];
  }
}

/**
 * The reconciliation pass (R22): every key this sweep dispatched must be
 * present in the ledger by the time the sweep finishes. Returns the keys
 * that are not — dispatched but never given ANY terminal outcome, not even
 * an error. Under this file's retry/dead-letter design that set should
 * always be empty (every code path that can fail to deliver still records a
 * synthetic "error" outcome — see `fetchJsonWithRetry` and its caller in
 * sweep_multi_worker.mjs); this function is the check that makes that a
 * proven invariant rather than an assumption a future refactor could break
 * silently. A non-empty result here is always a hard failure of the sweep.
 */
export function reconcile(dispatchedKeys, ledger) {
  const missing = [];
  for (const key of dispatchedKeys) {
    if (!ledger.has(key)) missing.push(key);
  }
  return missing;
}

function raceTimeout(ms) {
  // Deliberately NOT unref()'d: this timer is the only thing that can ever
  // unblock a `fetchImpl` that hangs forever and never settles on its own
  // (see fetchOnce below, and the F5 fault-injection case in
  // test_sweep_durability.mjs). An unref'd timer that races against a
  // Promise no other handle keeps alive can be starved by the event loop
  // deciding there is "nothing left to do" and never firing it at all —
  // exactly the hang this function exists to bound.
  return new Promise((_, reject) => {
    setTimeout(() => reject(new Error(`client-side timeout after ${ms}ms`)), ms);
  });
}

/**
 * One HTTP delivery attempt for a test, with a client-side timeout that
 * fires regardless of whether the underlying `fetch` implementation honors
 * `AbortSignal` (real Cloudflare-facing `fetch` does; a test double need
 * not, and this must still bound the wait — see the module header). Returns
 * `{ ok: true, body }` for a response that parsed as JSON and carries a
 * string `verdict`, or `{ ok: false, error }` for anything else: a thrown
 * network error, a non-2xx status, unparsable JSON, or a 2xx body with no
 * `verdict` — all of which mean "this attempt did not deliver an
 * authoritative test outcome," which is the only thing that licenses a
 * retry.
 */
async function fetchOnce(url, requestBody, { fetchImpl, timeoutMs }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await Promise.race([
      fetchImpl(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      }),
      raceTimeout(timeoutMs + 50),
    ]);
    let body;
    try {
      body = await res.json();
    } catch (e) {
      return { ok: false, error: `unparsable response body: ${e.message}` };
    }
    if (!res.ok) {
      return { ok: false, error: `HTTP ${res.status}: ${JSON.stringify(body).slice(0, 200)}` };
    }
    if (typeof body?.verdict !== "string") {
      return { ok: false, error: `response has no string "verdict": ${JSON.stringify(body).slice(0, 200)}` };
    }
    return { ok: true, body };
  } catch (e) {
    return { ok: false, error: e.message || String(e) };
  } finally {
    clearTimeout(timer);
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Deliver one test request with bounded retries. Retries ONLY a failure to
 * deliver an authoritative outcome (network error, timeout, non-2xx, a body
 * with no `verdict`) — never a legitimate `verdict: "fail"` or
 * `verdict: "error"` the Worker itself returned for a test it actually ran.
 * Retrying the latter would be retrying a deterministic test result, which
 * is a different (and not this file's) concern.
 *
 * Returns `{ ok: true, body, attempts }` on eventual success, or
 * `{ ok: false, error, attempts }` once `maxRetries` is exhausted — the
 * dead-letter case, which the caller must still record a terminal outcome
 * for (see sweep_multi_worker.mjs), never treat as simply absent.
 */
export async function fetchJsonWithRetry(
  url,
  requestBody,
  { fetchImpl = fetch, timeoutMs = 20000, maxRetries = 2, backoffMs = 200, sleepImpl = sleep } = {},
) {
  let lastError = null;
  for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
    const result = await fetchOnce(url, requestBody, { fetchImpl, timeoutMs });
    if (result.ok) return { ok: true, body: result.body, attempts: attempt + 1 };
    lastError = result.error;
    if (attempt < maxRetries) await sleepImpl(backoffMs * (attempt + 1));
  }
  return { ok: false, error: lastError, attempts: maxRetries + 1 };
}

/** Ensure the parent directory of `path` exists before writing into it. */
function ensureDir(path) {
  const dir = dirname(path);
  if (dir && dir !== ".") mkdirSync(dir, { recursive: true });
}

/**
 * Append-only NDJSON replica log — one line per terminal outcome, flushed in
 * small batches rather than once at the very end, so a process crash mid-run
 * loses at most the current batch rather than every result computed so far.
 * This is R23's replication for the run-in-progress case: the final summary
 * JSON is one file written once; this log is written continuously.
 */
export class ReplicaLog {
  constructor(path, { flushEvery = 25 } = {}) {
    this.path = path;
    this.flushEvery = flushEvery;
    this.buffer = [];
    if (path) {
      ensureDir(path);
      // Start each run with a fresh log; truncates any stale file from a
      // previous invocation at the same path.
      writeFileSync(path, "");
    }
  }

  append(record) {
    if (!this.path) return;
    this.buffer.push(JSON.stringify(record));
    if (this.buffer.length >= this.flushEvery) this.flush();
  }

  flush() {
    if (!this.path || this.buffer.length === 0) return;
    appendFileSync(this.path, this.buffer.map((l) => l + "\n").join(""));
    this.buffer = [];
  }
}

/**
 * Write the final summary to the primary path and, if given, an independent
 * replica path — two on-disk copies rather than one, so a truncated or
 * failed write to one location does not erase the run's only record. See
 * the module header for what this does and does not insure against (same
 * host, not same disk-failure-domain).
 */
export function writeReplicatedSummary(primaryPath, replicaPath, summaryObj) {
  const text = JSON.stringify(summaryObj, null, 2);
  if (primaryPath) {
    ensureDir(primaryPath);
    writeFileSync(primaryPath, text);
  }
  if (replicaPath && replicaPath !== primaryPath) {
    ensureDir(replicaPath);
    writeFileSync(replicaPath, text);
  }
}

/**
 * Write the dead-letter file (R22): every work item that never got an
 * authoritative outcome delivered even after retries, plus (belt-and-
 * suspenders) any item the reconciliation pass found truly missing from the
 * ledger, plus any conflicting-verdict anomalies. This is the "lands
 * somewhere recoverable" half of dead-letter handling — a human or a re-run
 * script can read this file and retry exactly these (family, index) pairs
 * rather than re-sweeping the whole corpus.
 */
export function writeDeadLetter(path, { deliveryFailed, missing, conflicts }) {
  if (!path) return;
  ensureDir(path);
  writeFileSync(
    path,
    JSON.stringify(
      {
        generated_at: new Date().toISOString(),
        delivery_failed: deliveryFailed,
        missing_from_ledger: missing,
        conflicting_verdicts: conflicts,
        total: deliveryFailed.length + missing.length + conflicts.length,
      },
      null,
      2,
    ),
  );
}

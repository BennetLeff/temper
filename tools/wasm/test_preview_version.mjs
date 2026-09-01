#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import test from "node:test";

import { createPreviewWorker } from "../../packages/temper-worker/src/preview_worker_core.js";

import {
  PREVIEW_LIMITS,
  WRANGLER_INTEGRITY,
  WRANGLER_VERSION,
  assertActionPins,
  classifyPendingCheck,
  comparisonContractDigest,
  makeUploadTag,
  makeScheduledUploadTag,
  parseUploadOutput,
  parseCheckExternalId,
  resolveUploadedVersion,
  validateArtifactForPublish,
  validateHealthIdentity,
  validateImmutablePreviewUrl,
  validateProductionInvariant,
  validateVersionView,
} from "./preview_version.mjs";

const SHA = "a".repeat(40);
const VERSION = "12345678-1234-1234-1234-123456789abc";
const SERVICE = "temper-wasm-io-types";
const PREVIEW_URL = `https://12345678-${SERVICE}.bennetleff.workers.dev`;

function manifest(overrides = {}) {
  return {
    schema: "temper-wasm-pr-preview-artifact-v1",
    source: {
      base_repository: "owner/temper",
      base_sha: "b".repeat(40),
      candidate: "temper-io-types",
      event_name: "pull_request_target",
      head_repository: "fork/temper",
      head_sha: SHA,
      pull_request_number: 42,
      run_attempt: 2,
      run_id: 99,
    },
    candidate: { crate: "temper-io-types", topology_sha256: "c".repeat(64) },
    census: {
      registered: 144,
      executed: 144,
      distinct_names: 144,
      wasm_sha256: "d".repeat(64),
      test_name_set_sha256: "e".repeat(64),
      imports: [],
    },
    limits: { max_wasm_bytes: 1 },
    artifact_files: ["candidate.wasm"],
    files: { "candidate.wasm": { bytes: 1, sha256: "d".repeat(64) } },
    ...overrides,
  };
}

test("the publisher dependency and runtime budgets are exact", () => {
  assert.equal(WRANGLER_VERSION, "4.128.0");
  assert.equal(
    WRANGLER_INTEGRITY,
    "sha512-jNXy9e8/pbx8iqTzXPiuflnitKJZoAfEUSUUDLW87bwyeMvJ7kb3yQMSbxEcfNdfHqJW38KRcKaLljOYV4N/4w==",
  );
  assert.deepEqual(PREVIEW_LIMITS, {
    maxTests: 10_000,
    concurrency: 64,
    requestTimeoutMs: 20_000,
    maxRetries: 2,
    workerCpuMs: 1_000,
    jobTimeoutMs: 20 * 60_000,
    capabilityTtlSeconds: 30 * 60,
  });
  const packageJson = JSON.parse(readFileSync(new URL("./wrangler-preview-runtime/package.json", import.meta.url), "utf8"));
  const packageLock = JSON.parse(readFileSync(new URL("./wrangler-preview-runtime/package-lock.json", import.meta.url), "utf8"));
  assert.equal(packageJson.dependencies.wrangler, WRANGLER_VERSION);
  assert.equal(packageLock.packages[""].dependencies.wrangler, WRANGLER_VERSION);
  assert.equal(packageLock.packages["node_modules/wrangler"].version, WRANGLER_VERSION);
  assert.equal(packageLock.packages["node_modules/wrangler"].integrity, WRANGLER_INTEGRITY);
});

test("artifact identity and the empty import allowlist fail closed", () => {
  const expected = { repository: "owner/temper", pr: 42, headSha: SHA, runId: 99, runAttempt: 2 };
  assert.equal(validateArtifactForPublish(manifest(), expected).census.registered, 144);
  assert.throws(
    () => validateArtifactForPublish(manifest({ census: { ...manifest().census, imports: ["wasi_snapshot_preview1.fd_write (function)"] } }), expected),
    /forbidden Wasm import/,
  );
  for (const mutation of [
    { head_sha: "f".repeat(40) },
    { run_id: 100 },
    { run_attempt: 3 },
    { pull_request_number: 43 },
  ]) {
    const changed = manifest();
    Object.assign(changed.source, mutation);
    assert.throws(() => validateArtifactForPublish(changed, expected), /identity mismatch/);
  }
  const tooMany = manifest();
  tooMany.census = { ...tooMany.census, registered: 10_001, executed: 10_001, distinct_names: 10_001 };
  assert.throws(() => validateArtifactForPublish(tooMany, expected), /census budget/);
});

test("upload tags distinguish attempts and version resolution is exact", () => {
  const tag = makeUploadTag({ repository: "owner/temper", pr: 42, headSha: SHA, runId: 99, runAttempt: 2 });
  assert.notEqual(tag, makeUploadTag({ repository: "owner/temper", pr: 42, headSha: SHA, runId: 99, runAttempt: 3 }));
  assert.notEqual(
    makeScheduledUploadTag({ repository: "owner/temper", headSha: SHA, runId: 99, runAttempt: 1 }),
    makeScheduledUploadTag({ repository: "owner/temper", headSha: SHA, runId: 99, runAttempt: 2 }),
  );
  const row = { id: VERSION, annotations: { "workers/tag": tag }, preview_url: PREVIEW_URL };
  assert.equal(resolveUploadedVersion([row], tag, SERVICE).id, VERSION);
  assert.equal(validateVersionView(row, VERSION, SERVICE).preview_url, PREVIEW_URL);
  assert.throws(() => validateVersionView({ ...row, id: "22345678-1234-1234-1234-123456789abc" }, VERSION, SERVICE), /identity mismatch/);
  assert.throws(() => resolveUploadedVersion([], tag, SERVICE), /exactly one/);
  assert.throws(() => resolveUploadedVersion([row, { ...row, id: "22345678-1234-1234-1234-123456789abc" }], tag, SERVICE), /exactly one/);
  const parsed = parseUploadOutput(`Uploaded\nWorker Version ID: ${VERSION}\nVersion Preview URL: ${PREVIEW_URL}\n`, SERVICE);
  assert.deepEqual(parsed, { id: VERSION, preview_url: PREVIEW_URL });
  assert.throws(() => parseUploadOutput(`Worker Version ID: ${VERSION}\n`, SERVICE), /exactly one/);
});

test("only immutable version preview URLs are accepted", () => {
  assert.equal(validateImmutablePreviewUrl(PREVIEW_URL, SERVICE).hostname, new URL(PREVIEW_URL).hostname);
  for (const bad of [
    `https://${SERVICE}.bennetleff.workers.dev`,
    `https://alias-${SERVICE}.bennetleff.workers.dev`,
    "https://example.com",
    `http://12345678-${SERVICE}.bennetleff.workers.dev`,
  ]) assert.throws(() => validateImmutablePreviewUrl(bad, SERVICE), /immutable|HTTPS|hostname/);
});

test("health binds capability expiry, source, module, contract, service and version", () => {
  const expected = {
    headSha: SHA,
    wasmSha256: "d".repeat(64),
    comparisonContractSha256: "e".repeat(64),
    service: SERVICE,
    versionId: VERSION,
    testCount: 144,
    abiVersion: 1,
  };
  const health = {
    status: "ok", head_sha: SHA, module_sha256: "d".repeat(64),
    comparison_contract_sha256: "e".repeat(64), worker_service: SERVICE,
    worker_version_id: VERSION, test_count: 144, abi_version: 1,
  };
  assert.equal(validateHealthIdentity(health, expected).status, "ok");
  for (const field of Object.keys(health).filter((key) => key !== "status")) {
    assert.throws(() => validateHealthIdentity({ ...health, [field]: "wrong" }, expected), /health identity mismatch/);
  }
});

test("comparison-contract digest is bit-identical to the U2 Python ledger", () => {
  const topology = JSON.parse(readFileSync(new URL("./wasm_tier_topology.json", import.meta.url), "utf8"));
  const census = { results: [{ name: "suite::beta" }, { name: "suite::alpha" }] };
  const expectedFailuresBytes = Buffer.from('{"expected_failures":{}}\n');
  const comparatorSha256 = "7".repeat(64);
  const js = comparisonContractDigest({
    candidate: "temper-io-types", census, expectedFailuresBytes, topology,
    comparatorSha256, abi: "immutable-worker-v1",
  });
  const tier = topology.tiers.find((item) => item.crate === "temper-io-types");
  const py = spawnSync("uv", ["run", "python", "-c", `
import hashlib, json, sys
from tools.wasm.r19_agreement_ledger import canonical_line, comparison_contract_digest
x=json.load(sys.stdin)
h=lambda b: hashlib.sha256(b).hexdigest()
components={
 "test_names_sha256": h(canonical_line(sorted(set(x["names"]))).encode()),
 "expected_failure_manifest_sha256": h(x["expected"].encode()),
 "native_args_sha256": h(canonical_line(x["tier"]["native_test_args"]).encode()),
 "abi": x["abi"],
 "topology_sha256": h(canonical_line(x["tier"]).encode()),
 "comparator_version": "r19_compare.py@" + x["comparator"],
}
print(json.dumps({"components": components, "digest": comparison_contract_digest(components)}, sort_keys=True))
`], {
    cwd: new URL("../..", import.meta.url),
    input: JSON.stringify({ names: census.results.map((row) => row.name), expected: expectedFailuresBytes.toString(), tier, abi: "immutable-worker-v1", comparator: comparatorSha256 }),
    encoding: "utf8",
  });
  assert.equal(py.status, 0, py.stderr);
  assert.deepEqual(js, JSON.parse(py.stdout));
});

test("the base-owned entrypoint gates the URL with an expiring capability", async () => {
  const inner = {
    async fetch(request) {
      return request.method === "GET"
        ? new Response(JSON.stringify({ status: "ok", test_count: 2, abi_version: 1 }), { status: 200 })
        : new Response(JSON.stringify({ verdict: "pass", index: 0, name: "alpha" }), { status: 200 });
    },
  };
  const worker = createPreviewWorker(inner, { now: () => 1_000_000 });
  const env = {
    PREVIEW_CAPABILITY: "secret-value",
    PREVIEW_EXPIRES_AT: "2000",
    PREVIEW_MAX_TESTS: "10000",
    PREVIEW_HEAD_SHA: SHA,
    PREVIEW_MODULE_SHA256: "d".repeat(64),
    PREVIEW_COMPARISON_CONTRACT_SHA256: "e".repeat(64),
    PREVIEW_SERVICE: SERVICE,
    CF_VERSION_METADATA: { id: VERSION },
  };
  const request = (path, token = null) => new Request(`https://preview.example${path}`, {
    method: path === "/run-test" ? "POST" : "GET",
    headers: token ? { "x-temper-preview-capability": token } : {},
    body: path === "/run-test" ? "{}" : undefined,
  });
  assert.equal((await worker.fetch(request("/health"), env)).status, 403);
  const healthResponse = await worker.fetch(request("/health", "secret-value"), env);
  assert.equal(healthResponse.status, 200);
  assert.equal((await healthResponse.json()).worker_version_id, VERSION);
  assert.equal((await worker.fetch(request("/manifest", "secret-value"), env)).status, 404);
  assert.equal((await worker.fetch(request("/run-test", "secret-value"), env)).status, 200);
  assert.equal((await worker.fetch(request("/health", "secret-value"), { ...env, PREVIEW_EXPIRES_AT: "999" })).status, 410);
  assert.equal((await worker.fetch(request("/health", "secret-value"), { ...env, PREVIEW_MAX_TESTS: "NaN" })).status, 500);
  assert.equal((await worker.fetch(request("/health", "secret-value"), { ...env, PREVIEW_MAX_TESTS: "10001" })).status, 500);
});

test("production and PR-head invariants reject mutation", () => {
  assert.doesNotThrow(() => validateProductionInvariant({ id: "prod-v1" }, { id: "prod-v1" }));
  assert.throws(() => validateProductionInvariant({ id: "prod-v1" }, { id: "prod-v2" }), /production deployment changed/);
});

test("orphan and deadline reconciliation preserves approval-pending", () => {
  const now = Date.parse("2026-09-01T12:00:00Z");
  assert.equal(classifyPendingCheck({ now, createdAt: now - 60_000, sourceStatus: "queued", approvalPending: true }).state, "pending-approval");
  assert.equal(classifyPendingCheck({ now, createdAt: now - 31 * 60_000, sourceStatus: "completed", published: false }).state, "failed-orphan");
  assert.equal(classifyPendingCheck({ now, createdAt: now - 61 * 60_000, sourceStatus: "queued", approvalPending: false }).state, "failed-deadline");
  assert.equal(classifyPendingCheck({ now, createdAt: now - 60_000, sourceStatus: "in_progress", published: false }).state, "pending");
  assert.deepEqual(
    parseCheckExternalId(`temper-wasm-preview-v1:99:2:42:${SHA}`),
    { runId: 99, runAttempt: 2, pr: 42, headSha: SHA },
  );
  for (const invalid of [
    `temper-wasm-preview-v1:99:2:42:extra:${SHA}`,
    `temper-wasm-preview-v1:99:2:42:short`,
    `other:99:2:42:${SHA}`,
  ]) assert.throws(() => parseCheckExternalId(invalid), /external_id/);
});

test("privileged workflows contain only immutable Action refs", () => {
  for (const path of [
    new URL("../../.github/workflows/wasm-tier-preview-verdict.yml", import.meta.url),
    new URL("../../.github/workflows/wasm-tier-preview-status.yml", import.meta.url),
    new URL("../../.github/workflows/wasm-tier-nightly.yml", import.meta.url),
  ]) assert.doesNotThrow(() => assertActionPins(readFileSync(path, "utf8")));
  assert.throws(() => assertActionPins("uses: actions/checkout@v7\n"), /mutable Action reference/);
  const publisher = readFileSync(new URL("../../.github/workflows/wasm-tier-preview-status.yml", import.meta.url), "utf8");
  assert.doesNotMatch(publisher, /^\s*PREVIEW_CAPABILITY\s*=\s*"\$\{CAPABILITY\}"/m);
  assert.match(publisher, /--secrets-file \/tmp\/preview-stage\/secrets\.json/);
  assert.match(publisher, /npm ci --prefix "\$\{WRANGLER_RUNTIME\}" --ignore-scripts/);
  assert.doesNotMatch(publisher, /npm install|npm view|--no-package-lock/);
  assert.match(publisher, /rm -f \/tmp\/preview-stage\/secrets\.json/);
  assert.match(publisher, /grep -Fq "\$\{CAPABILITY\}" \/tmp\/preview-diagnostics\/upload\.txt/);
  assert.match(publisher, /pr\.head\.sha === expectedHead/);
  assert.match(publisher, /production-invariant --before .*production-before\.json --after .*production-after\.json/);
  assert.match(publisher, /source\?\.status === "waiting"/);
  assert.match(publisher, /age > 30 \* 60_000/);
  assert.match(publisher, /age > 60 \* 60_000/);
  assert.match(publisher, /preview-source-identities/);
  assert.doesNotMatch(publisher, /parts\.length !== 6/);
  const nightly = readFileSync(new URL("../../.github/workflows/wasm-tier-nightly.yml", import.meta.url), "utf8");
  assert.match(nightly, /npm ci --prefix "\$\{WRANGLER_RUNTIME\}" --ignore-scripts/);
  assert.doesNotMatch(nightly, /npm install|npm view|--no-package-lock/);
  assert.doesNotMatch(publisher, /versions upload[^\n]*[\s\S]{0,300}\| tee/);
  for (const workflow of [publisher, nightly]) {
    const upload = workflow.indexOf('"${WRANGLER}" versions upload');
    const capture = workflow.indexOf("upload_rc=$?", upload);
    const scrub = workflow.indexOf('grep -Fq "${CAPABILITY}"', capture);
    const honorFailure = workflow.indexOf('[ "${upload_rc}" -ne 0 ]', scrub);
    assert.ok(upload >= 0 && capture > upload && scrub > capture && honorFailure > scrub,
      "upload output must be scrubbed before a failing Wrangler exit is honored");
  }
});

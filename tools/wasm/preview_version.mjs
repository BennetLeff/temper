#!/usr/bin/env node
/** Base-owned validation and identity protocol for immutable Worker previews. */

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { canonicalDeep as canonical, sha256 } from "./tier_topology.mjs";

export { sha256 };

export const WRANGLER_VERSION = "4.128.0";
export const WRANGLER_INTEGRITY =
  "sha512-jNXy9e8/pbx8iqTzXPiuflnitKJZoAfEUSUUDLW87bwyeMvJ7kb3yQMSbxEcfNdfHqJW38KRcKaLljOYV4N/4w==";
export const PREVIEW_SERVICE = "temper-wasm-io-types";
export const PREVIEW_LIMITS = Object.freeze({
  maxTests: 10_000,
  concurrency: 64,
  requestTimeoutMs: 20_000,
  maxRetries: 2,
  workerCpuMs: 1_000,
  jobTimeoutMs: 20 * 60_000,
  capabilityTtlSeconds: 30 * 60,
});

const SHA40 = /^[0-9a-f]{40}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const VERSION_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const CHECK_EXTERNAL_PREFIX = "temper-wasm-preview-v1";

export function makeUploadTag({ repository, pr, headSha, runId, runAttempt }) {
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository) || !SHA40.test(headSha)) {
    throw new Error("invalid upload source identity");
  }
  for (const value of [pr, runId, runAttempt]) {
    if (!Number.isSafeInteger(Number(value)) || Number(value) <= 0) throw new Error("invalid upload run identity");
  }
  return `temper-${repository.replace("/", "-")}-pr-${pr}-${headSha}-run-${runId}-${runAttempt}`;
}

export function makeScheduledUploadTag({ repository, headSha, runId, runAttempt }) {
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository) || !SHA40.test(headSha)) {
    throw new Error("invalid scheduled upload source identity");
  }
  for (const value of [runId, runAttempt]) {
    if (!Number.isSafeInteger(Number(value)) || Number(value) <= 0) throw new Error("invalid scheduled run identity");
  }
  return `temper-${repository.replace("/", "-")}-nightly-${headSha}-run-${runId}-${runAttempt}`;
}

export function comparisonContractDigest({ candidate, census, expectedFailuresBytes, topology, comparatorSha256, abi }) {
  if (!SHA256.test(comparatorSha256 ?? "")) throw new Error("invalid comparator sha256");
  if (typeof abi !== "string" || !abi) throw new Error("comparison ABI must be non-empty");
  const tier = topology?.tiers?.find((item) => item?.crate === candidate);
  if (!tier) throw new Error("comparison candidate is absent from topology");
  const names = [...new Set((census?.results ?? []).map((row) => row?.name))].sort();
  if (!names.length || names.some((name) => typeof name !== "string" || !name)) {
    throw new Error("comparison census has no distinct test-name set");
  }
  const components = {
    test_names_sha256: sha256(Buffer.from(canonical(names))),
    expected_failure_manifest_sha256: sha256(expectedFailuresBytes),
    native_args_sha256: sha256(Buffer.from(canonical(tier.native_test_args))),
    abi,
    topology_sha256: sha256(Buffer.from(canonical(tier))),
    comparator_version: `r19_compare.py@${comparatorSha256}`,
  };
  return { components, digest: sha256(Buffer.from(canonical(components))) };
}

export function validateArtifactForPublish(manifest, expected) {
  if (manifest?.schema !== "temper-wasm-pr-preview-artifact-v1") throw new Error("unexpected artifact schema");
  const source = manifest?.source ?? {};
  const pairs = [
    ["base_repository", expected.repository],
    ["pull_request_number", Number(expected.pr)],
    ["head_sha", expected.headSha],
    ["run_id", Number(expected.runId)],
    ["run_attempt", Number(expected.runAttempt)],
    ["candidate", "temper-io-types"],
  ];
  for (const [field, wanted] of pairs) {
    if (source[field] !== wanted) throw new Error(`artifact identity mismatch for ${field}`);
  }
  if (!SHA40.test(source.head_sha ?? "")) throw new Error("artifact identity mismatch for head_sha");
  const census = manifest?.census ?? {};
  if (
    !Number.isSafeInteger(census.registered) || census.registered <= 0 ||
    census.registered > PREVIEW_LIMITS.maxTests || census.executed !== census.registered ||
    census.distinct_names !== census.registered
  ) throw new Error("artifact census budget or completeness violation");
  if (!SHA256.test(census.wasm_sha256 ?? "") || !SHA256.test(census.test_name_set_sha256 ?? "")) {
    throw new Error("artifact digest is malformed");
  }
  if (!Array.isArray(census.imports)) throw new Error("artifact import set is malformed");
  if (census.imports.length !== 0) {
    throw new Error(`forbidden Wasm import: ${census.imports.join(", ")}`);
  }
  return manifest;
}

function versionTag(row) {
  return row?.annotations?.["workers/tag"] ?? row?.annotations?.tag ?? row?.tag ?? null;
}

function versionUrl(row) {
  return row?.preview_url ?? row?.previewUrl ?? row?.preview?.url ?? null;
}

export function validateImmutablePreviewUrl(raw, service = PREVIEW_SERVICE) {
  let url;
  try { url = new URL(raw); } catch { throw new Error("immutable preview URL is invalid"); }
  if (url.protocol !== "https:") throw new Error("immutable preview URL must use HTTPS");
  if (url.username || url.password || url.port || url.pathname !== "/" || url.search || url.hash) {
    throw new Error("immutable preview URL contains unsupported components");
  }
  const escaped = service.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`^[0-9a-f]{8}-${escaped}\\.[a-z0-9-]+\\.workers\\.dev$`);
  if (!pattern.test(url.hostname)) throw new Error("preview hostname is not an immutable version URL");
  return url;
}

export function resolveUploadedVersion(rows, tag, service = PREVIEW_SERVICE) {
  const versions = Array.isArray(rows) ? rows : rows?.versions;
  if (!Array.isArray(versions)) throw new Error("Wrangler versions output is not an array");
  const matches = versions.filter((row) => versionTag(row) === tag);
  if (matches.length !== 1) throw new Error(`expected exactly one uploaded version for tag ${tag}, got ${matches.length}`);
  const row = matches[0];
  if (!VERSION_ID.test(row?.id ?? "")) throw new Error("uploaded version has no canonical version ID");
  const previewUrl = versionUrl(row);
  if (previewUrl) validateImmutablePreviewUrl(previewUrl, service);
  return { ...row, ...(previewUrl ? { preview_url: previewUrl } : {}) };
}

export function parseUploadOutput(output, service = PREVIEW_SERVICE) {
  const ids = [...output.matchAll(/^Worker Version ID:\s*([^\s]+)\s*$/gm)].map((match) => match[1]);
  const urls = [...output.matchAll(/^Version Preview URL:\s*(https:\/\/[^\s]+)\s*$/gm)].map((match) => match[1]);
  if (ids.length !== 1 || urls.length !== 1) {
    throw new Error(`Wrangler upload output must contain exactly one version ID and preview URL (got ${ids.length}/${urls.length})`);
  }
  if (!VERSION_ID.test(ids[0])) throw new Error("Wrangler upload returned a non-canonical version ID");
  validateImmutablePreviewUrl(urls[0], service);
  if (!new URL(urls[0]).hostname.startsWith(`${ids[0].slice(0, 8)}-`)) {
    throw new Error("preview URL prefix does not match the uploaded version ID");
  }
  return { id: ids[0], preview_url: urls[0] };
}

export function validateVersionView(view, expectedId, service = PREVIEW_SERVICE) {
  const row = view?.version ?? view;
  if (row?.id !== expectedId) throw new Error("version view identity mismatch");
  const previewUrl = versionUrl(row);
  if (!previewUrl) throw new Error("uploaded version has no preview URL (preview_urls may be disabled)");
  validateImmutablePreviewUrl(previewUrl, service);
  return { ...row, preview_url: previewUrl };
}

export function validateHealthIdentity(health, expected) {
  const fields = {
    status: "ok",
    head_sha: expected.headSha,
    module_sha256: expected.wasmSha256,
    comparison_contract_sha256: expected.comparisonContractSha256,
    worker_service: expected.service,
    worker_version_id: expected.versionId,
    test_count: expected.testCount,
    abi_version: expected.abiVersion,
  };
  for (const [field, wanted] of Object.entries(fields)) {
    if (health?.[field] !== wanted) throw new Error(`health identity mismatch for ${field}`);
  }
  return health;
}

export function validateProductionInvariant(before, after) {
  if (canonical(before) !== canonical(after)) throw new Error("production deployment changed during preview upload");
}

export function classifyPendingCheck({ now, createdAt, sourceStatus, approvalPending = false, published = false }) {
  const age = Number(now) - Number(createdAt);
  if (published) return { state: "published", conclusion: null };
  if (approvalPending && age <= 24 * 60 * 60_000) {
    return { state: "pending-approval", conclusion: null, summary: "Approve the credential-free source workflow to continue." };
  }
  if (sourceStatus === "completed" && age > 30 * 60_000) {
    return { state: "failed-orphan", conclusion: "failure", summary: "Source build finished but no trusted preview verdict was published." };
  }
  if (age > 60 * 60_000) {
    return { state: "failed-deadline", conclusion: "timed_out", summary: "Exact-head preview verdict deadline expired." };
  }
  return { state: "pending", conclusion: null };
}

export function parseCheckExternalId(value) {
  const parts = typeof value === "string" ? value.split(":") : [];
  if (parts.length !== 5 || parts[0] !== CHECK_EXTERNAL_PREFIX || !SHA40.test(parts[4] ?? "")) {
    throw new Error("invalid preview check external_id");
  }
  const [runId, runAttempt, pr] = parts.slice(1, 4).map(Number);
  if (![runId, runAttempt, pr].every((item) => Number.isSafeInteger(item) && item > 0)) {
    throw new Error("invalid preview check external_id");
  }
  return { runId, runAttempt, pr, headSha: parts[4] };
}

export function assertActionPins(workflowText) {
  const refs = [...workflowText.matchAll(/^\s*uses:\s*([^\s#]+)(?:\s+#.*)?$/gm)].map((match) => match[1]);
  for (const ref of refs) {
    const at = ref.lastIndexOf("@");
    if (at === -1 || !/^[0-9a-f]{40}$/.test(ref.slice(at + 1))) {
      throw new Error(`mutable Action reference: ${ref}`);
    }
  }
  return refs;
}

function value(args, name) {
  const index = args.indexOf(name);
  if (index < 0 || args[index + 1] === undefined) throw new Error(`missing ${name}`);
  return args[index + 1];
}

async function cli(args) {
  const command = args[0];
  if (command === "validate-artifact") {
    const manifest = JSON.parse(readFileSync(value(args, "--manifest"), "utf8"));
    const checked = validateArtifactForPublish(manifest, {
      repository: value(args, "--repository"), pr: Number(value(args, "--pr")),
      headSha: value(args, "--head-sha"), runId: Number(value(args, "--run-id")),
      runAttempt: Number(value(args, "--run-attempt")),
    });
    writeFileSync(value(args, "--output"), `${canonical(checked)}\n`);
    return;
  }
  if (command === "resolve-version") {
    const rows = JSON.parse(readFileSync(value(args, "--versions"), "utf8"));
    const resolved = resolveUploadedVersion(rows, value(args, "--tag"), value(args, "--service"));
    writeFileSync(value(args, "--output"), `${canonical(resolved)}\n`);
    return;
  }
  if (command === "parse-upload") {
    const resolved = parseUploadOutput(readFileSync(value(args, "--upload-output"), "utf8"), value(args, "--service"));
    writeFileSync(value(args, "--output"), `${canonical(resolved)}\n`);
    return;
  }
  if (command === "validate-version-view") {
    const view = JSON.parse(readFileSync(value(args, "--view"), "utf8"));
    const resolved = validateVersionView(view, value(args, "--version-id"), value(args, "--service"));
    writeFileSync(value(args, "--output"), `${canonical(resolved)}\n`);
    return;
  }
  if (command === "validate-health") {
    const health = JSON.parse(readFileSync(value(args, "--health"), "utf8"));
    validateHealthIdentity(health, {
      headSha: value(args, "--head-sha"), wasmSha256: value(args, "--wasm-sha256"),
      comparisonContractSha256: value(args, "--contract-sha256"), service: value(args, "--service"),
      versionId: value(args, "--version-id"), testCount: Number(value(args, "--test-count")),
      abiVersion: Number(value(args, "--abi-version")),
    });
    return;
  }
  if (command === "production-invariant") {
    validateProductionInvariant(
      JSON.parse(readFileSync(value(args, "--before"), "utf8")),
      JSON.parse(readFileSync(value(args, "--after"), "utf8")),
    );
    return;
  }
  if (command === "contract-digest") {
    const result = comparisonContractDigest({
      candidate: value(args, "--candidate"),
      census: JSON.parse(readFileSync(value(args, "--census"), "utf8")),
      expectedFailuresBytes: readFileSync(value(args, "--expected-failures")),
      topology: JSON.parse(readFileSync(value(args, "--topology"), "utf8")),
      comparatorSha256: value(args, "--comparator-sha256"),
      abi: value(args, "--abi"),
    });
    process.stdout.write(`${result.digest}\n`);
    return;
  }
  if (command === "assert-action-pins") {
    for (const path of args.slice(1)) assertActionPins(readFileSync(path, "utf8"));
    return;
  }
  throw new Error(`unknown preview-version command ${JSON.stringify(command)}`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  cli(process.argv.slice(2)).catch((error) => { console.error(`error: ${error.message}`); process.exitCode = 1; });
}

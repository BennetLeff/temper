/**
 * Loader for tools/wasm/wasm_tier_topology.json — the WASM tier's one committed
 * description of what is built, what is deployed, what is swept, and what is
 * checked for staleness.
 *
 * See that file's `_comment` for the tier/shard model and for why the same list
 * used to live in four places. This module exists so the four consumers agree by
 * construction rather than by review.
 *
 * Deliberately dependency-free and side-effect-free so it can be imported by
 * tools that run on a bare `actions/setup-node` runner with no `npm install`.
 */

import { createHash } from "node:crypto";
import {
  lstatSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import { fileURLToPath } from "node:url";
import { basename, dirname, join, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
export const TOPOLOGY_PATH = join(HERE, "wasm_tier_topology.json");
export const MAX_PREVIEW_WASM_BYTES = 10 * 1024 * 1024;
const MAX_PREVIEW_FILE_BYTES = 16 * 1024 * 1024;
const MAX_PREVIEW_TOTAL_BYTES = 32 * 1024 * 1024;
const SHA256_RE = /^[0-9a-f]{64}$/;
const COMMIT_RE = /^[0-9a-f]{40}$/;

/** Parse the committed topology. Throws (loudly, with the path) if unreadable. */
export function loadTopology(path = TOPOLOGY_PATH) {
  let raw;
  try {
    raw = readFileSync(path, "utf8");
  } catch (e) {
    throw new Error(
      `Cannot read the WASM tier topology from ${path}: ${e.message}. ` +
        "Every consumer (staging, deploy, sweep, freshness) reads this file; " +
        "without it there is no list of Workers to act on, so callers must fail " +
        "rather than fall back to a hardcoded list that could disagree with it.",
    );
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (e) {
    throw new Error(`${path} is not valid JSON: ${e.message}`);
  }
  validate(parsed, path);
  return parsed;
}

/**
 * Structural checks that would otherwise surface as a confusing failure much
 * later — a typo'd Worker name looks exactly like an undeployed Worker.
 *
 * The disjointness check is the load-bearing one: if the same Cloudflare script
 * were listed as a shard of two different tiers, one Worker's count would be
 * counted toward two crates' built counts and each tier could pass while only
 * one module was actually fresh. A Worker may serve as both the full-corpus
 * Worker AND a shard of the SAME tier (that is exactly temper-wasm-geometry and
 * temper-wasm-thermal), but never across tiers.
 */
function validate(t, path) {
  if (!Array.isArray(t?.tiers) || t.tiers.length === 0) {
    throw new Error(`${path}: "tiers" must be a non-empty array`);
  }
  if (typeof t.base_domain !== "string" || !t.base_domain) {
    throw new Error(`${path}: "base_domain" must be a non-empty string`);
  }
  const owner = new Map(); // worker script name -> crate that claims it
  const crates = new Set();
  for (const tier of t.tiers) {
    for (const field of ["crate", "cargo_features", "staged_module", "full_corpus_worker", "wrangler_dir", "expected_failures"]) {
      if (typeof tier[field] !== "string" || !tier[field]) {
        throw new Error(`${path}: tier ${tier.crate ?? "?"} is missing string field "${field}"`);
      }
    }
    if (!Array.isArray(tier.shards) || tier.shards.length === 0) {
      throw new Error(`${path}: tier ${tier.crate} must declare at least one shard`);
    }
    if (crates.has(tier.crate)) {
      throw new Error(`${path}: duplicate tier crate ${JSON.stringify(tier.crate)}`);
    }
    crates.add(tier.crate);
    for (const script of [tier.full_corpus_worker, ...tier.shards.map((s) => s.worker)]) {
      const prev = owner.get(script);
      if (prev !== undefined && prev !== tier.crate) {
        throw new Error(
          `${path}: Cloudflare script "${script}" is claimed by both ${prev} and ${tier.crate}. ` +
            "A script may serve two roles within one tier, but never across tiers — " +
            "sharing it would let one deployed module satisfy two crates' freshness checks at once.",
        );
      }
      owner.set(script, tier.crate);
    }
  }
  // Older ad-hoc fixture topologies predate the cadence contract; absence is
  // equivalent to the explicit production spelling `[]`. A present value is
  // always validated strictly and never coerced.
  const promotionCandidates = t.promotion_candidates === undefined ? [] : t.promotion_candidates;
  if (!Array.isArray(promotionCandidates)) {
    throw new Error(`${path}: "promotion_candidates" must be an array (use [] for no candidates)`);
  }
  const candidates = new Set();
  for (const candidate of promotionCandidates) {
    if (typeof candidate !== "string" || !candidate) {
      throw new Error(`${path}: every promotion_candidates entry must be a non-empty crate-name string`);
    }
    if (candidates.has(candidate)) {
      throw new Error(`${path}: duplicate promotion candidate ${JSON.stringify(candidate)}`);
    }
    candidates.add(candidate);
    if (!crates.has(candidate)) {
      throw new Error(
        `${path}: unknown promotion candidate ${JSON.stringify(candidate)}; known tiers: ${[...crates].join(", ")}`,
      );
    }
  }
  if (candidates.size > 1) {
    throw new Error(`${path}: promotion_candidates currently supports at most one candidate`);
  }
}

/** `https://<script>.<base_domain>` */
export function workerUrl(topology, script) {
  return `https://${script}.${topology.base_domain}`;
}

/**
 * The command-line flag suffix a tier's per-crate arguments carry: the crate
 * name with the leading `temper-` dropped and any remaining `-` kept
 * (`temper-geometry` -> `geometry`, `temper-drc-rs` -> `drc-rs`).
 *
 * Exported rather than redefined per caller because it is a CONTRACT between
 * two files that never import each other: check_deployed_freshness.mjs derives
 * the flag names it accepts from it, and the deploy workflow / Makefile derive
 * the flag names they PASS from it. A private copy in each would let the two
 * drift, and the drift's symptom is the worst available one — the checker exits
 * 2 saying a tier has no built count while the caller is certain it passed one.
 */
export function tierFlagSuffix(crate) {
  return crate.replace(/^temper-/, "");
}

/**
 * Every `--built-json-<suffix> <path>` argument check_deployed_freshness.mjs
 * requires, given a function from crate name to that crate's census file. One
 * per tier, always — the checker exits 2 on a tier with no count, so a caller
 * that builds this list from the topology cannot narrow the check by forgetting
 * a crate, which is the whole reason the flags are generated rather than typed.
 */
export function freshnessArgs(topology, censusPathFor) {
  return topology.tiers.flatMap((t) => [
    `--built-json-${tierFlagSuffix(t.crate)}`,
    censusPathFor(t.crate),
  ]);
}

/** Pick one tier by crate name; throws listing the valid names. */
export function tierByCrate(topology, crate) {
  const tier = topology.tiers.find((t) => t.crate === crate);
  if (!tier) {
    throw new Error(
      `unknown tier ${JSON.stringify(crate)}; known tiers: ${topology.tiers.map((t) => t.crate).join(", ")}`,
    );
  }
  return tier;
}

/**
 * Native/R19 derivations for one scheduled slot: the ordinary rotated tier
 * followed by promotion candidates, with a rotation/candidate collision run
 * exactly once. The full all-tier wasm32 census is intentionally not based on
 * this list; callers that enforce deployed freshness must continue using
 * `topology.tiers`.
 */
export function scheduledComparisonTiers(topology, rotatedCrate) {
  const selected = [tierByCrate(topology, rotatedCrate)];
  const seen = new Set([rotatedCrate]);
  for (const candidate of topology.promotion_candidates ?? []) {
    if (seen.has(candidate)) continue;
    selected.push(tierByCrate(topology, candidate));
    seen.add(candidate);
  }
  return selected;
}

/**
 * Resolve the single Phase 6 preview candidate from the topology.
 *
 * This is deliberately stricter than `tierByCrate`: the preview artifact has
 * one Wasm slot.  Silently choosing the first of zero/two candidates or the
 * first of two build targets would let the artifact describe a different
 * module from the one the workflow actually staged.
 */
export function previewCandidateContract(topology) {
  validate(topology, "<preview topology>");
  const candidates = topology.promotion_candidates ?? [];
  if (candidates.length !== 1) {
    throw new Error(
      `<preview topology>: expected exactly one promotion candidate, got ${candidates.length}`,
    );
  }
  const crate = candidates[0];
  if (!/^temper-[a-z0-9-]+$/.test(crate)) {
    throw new Error(`<preview topology>: unsafe candidate crate name ${JSON.stringify(crate)}`);
  }
  const tier = tierByCrate(topology, crate);
  const targets = buildTargets({ ...topology, tiers: [tier] });
  if (targets.length !== 1) {
    throw new Error(
      `<preview topology>: promotion candidate ${crate} must resolve to exactly one build target, got ${targets.length}`,
    );
  }
  const target = targets[0];
  if (!/^[A-Za-z0-9_-]+$/.test(target.cargo_features)) {
    throw new Error(`<preview topology>: unsafe cargo feature ${JSON.stringify(target.cargo_features)}`);
  }
  if (basename(target.staged_module) !== target.staged_module || !/^[A-Za-z0-9][A-Za-z0-9_.-]*\.wasm$/.test(target.staged_module)) {
    throw new Error(`<preview topology>: unsafe staged module name ${JSON.stringify(target.staged_module)}`);
  }
  if (
    !tier.expected_failures.startsWith("tools/wasm/") ||
    basename(tier.expected_failures) === tier.expected_failures ||
    !/^[A-Za-z0-9_./-]+\.json$/.test(tier.expected_failures) ||
    tier.expected_failures.includes("..")
  ) {
    throw new Error(`<preview topology>: unsafe expected-failure path ${JSON.stringify(tier.expected_failures)}`);
  }
  const native = tier.native_test_args;
  const hasFeatureSelection =
    Array.isArray(native) && native[1] === "--features";
  const manifestIndex = hasFeatureSelection ? 3 : 1;
  const featureSelectionValid =
    !hasFeatureSelection ||
    (native.length >= 5 && /^[A-Za-z0-9_-]+$/.test(native[2]));
  if (
    !Array.isArray(native) ||
    ![3, 4, 5, 6].includes(native.length) ||
    native[0] !== "--no-default-features" ||
    !featureSelectionValid ||
    native[manifestIndex] !== "--manifest-path" ||
    typeof native[manifestIndex + 1] !== "string" ||
    !/^packages\/[A-Za-z0-9_./-]+\/Cargo\.toml$/.test(native[manifestIndex + 1]) ||
    native[manifestIndex + 1].includes("..") ||
    (native.length !== manifestIndex + 2 &&
      native.length !== manifestIndex + 3) ||
    (native.length === manifestIndex + 3 && native[manifestIndex + 2] !== "--lib")
  ) {
    throw new Error(
      `<preview topology>: ${crate} native_test_args must be --no-default-features [--features <safe-feature>] --manifest-path packages/.../Cargo.toml [--lib]`,
    );
  }
  return Object.freeze({
    crate,
    cargo_features: target.cargo_features,
    module_file: target.staged_module,
    digest_file: `${target.staged_module}.sha256.json`,
    expected_failures_source: tier.expected_failures,
    expected_failures_file: "expected-failures.json",
    native_test_args: [...tier.native_test_args],
    native_output_file: "native_raw.txt",
    census_file: "census.json",
    imports_file: "imports.json",
    manifest_file: "manifest.json",
    max_wasm_bytes: MAX_PREVIEW_WASM_BYTES,
  });
}

export const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
export function canonicalDeep(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalDeep).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalDeep(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function parseJsonFile(path, label) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    throw new Error(`${label} is not valid JSON: ${error.message}`);
  }
}

function assertRegularFiles(artifactDir, allowed) {
  const entries = readdirSync(artifactDir, { withFileTypes: true });
  const actual = entries.map((entry) => entry.name).sort();
  const expected = [...allowed].sort();
  if (canonicalDeep(actual) !== canonicalDeep(expected)) {
    throw new Error(
      `preview artifact has an unexpected or missing entry: expected ${expected.join(", ")}; got ${actual.join(", ")}`,
    );
  }
  for (const entry of entries) {
    const stat = lstatSync(join(artifactDir, entry.name));
    if (!entry.isFile() || stat.isSymbolicLink()) {
      throw new Error(`preview artifact entry ${entry.name} is not a regular file`);
    }
  }
}

function validateIdentity(identity, contract) {
  const required = [
    "base_repository", "base_sha", "candidate", "event_name", "head_repository",
    "head_sha", "pull_request_number", "run_attempt", "run_id",
  ];
  if (canonicalDeep(Object.keys(identity).sort()) !== canonicalDeep(required.sort())) {
    throw new Error(`preview source identity fields must be exactly ${required.join(", ")}`);
  }
  for (const field of ["base_repository", "head_repository"]) {
    if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(identity[field] ?? "")) {
      throw new Error(`invalid ${field}`);
    }
  }
  for (const field of ["base_sha", "head_sha"]) {
    if (!COMMIT_RE.test(identity[field] ?? "")) throw new Error(`invalid ${field}`);
  }
  if (identity.event_name !== "pull_request_target") throw new Error("unexpected source event");
  if (identity.candidate !== contract.crate) throw new Error("source candidate does not match topology");
  for (const field of ["pull_request_number", "run_attempt", "run_id"]) {
    if (!Number.isSafeInteger(identity[field]) || identity[field] <= 0) {
      throw new Error(`invalid ${field}`);
    }
  }
}

function inspectPreviewPayload({ artifactDir, identity, topology }) {
  const contract = previewCandidateContract(topology);
  validateIdentity(identity, contract);
  const payloadNames = [
    contract.module_file,
    contract.digest_file,
    contract.expected_failures_file,
    contract.native_output_file,
    contract.census_file,
    contract.imports_file,
  ];
  const fileRecords = {};
  let totalBytes = 0;
  for (const name of payloadNames) {
    const path = join(artifactDir, name);
    const limit = name === contract.module_file ? MAX_PREVIEW_WASM_BYTES : MAX_PREVIEW_FILE_BYTES;
    const stat = lstatSync(path);
    if (!stat.isFile() || stat.isSymbolicLink()) throw new Error(`preview artifact file ${name} is not regular`);
    if (stat.size === 0) throw new Error(`preview artifact file ${name} is empty`);
    if (stat.size > limit) throw new Error(`preview artifact file ${name} is too large (${stat.size} > ${limit})`);
    const bytes = readFileSync(path);
    totalBytes += bytes.length;
    fileRecords[name] = { bytes: bytes.length, sha256: sha256(bytes) };
  }
  if (totalBytes > MAX_PREVIEW_TOTAL_BYTES) {
    throw new Error(`preview artifact payload is too large (${totalBytes} > ${MAX_PREVIEW_TOTAL_BYTES})`);
  }

  const digest = parseJsonFile(join(artifactDir, contract.digest_file), "Wasm digest sidecar");
  if (
    canonicalDeep(Object.keys(digest)) !== canonicalDeep(["sha256"]) ||
    !SHA256_RE.test(digest.sha256 ?? "")
  ) {
    throw new Error("Wasm digest sidecar must contain exactly one lowercase sha256");
  }
  if (digest.sha256 !== fileRecords[contract.module_file].sha256) {
    throw new Error("Wasm digest sidecar does not match the staged module");
  }

  const expectedFailures = parseJsonFile(
    join(artifactDir, contract.expected_failures_file),
    "expected-failure data",
  );
  if (expectedFailures === null || typeof expectedFailures !== "object" || Array.isArray(expectedFailures)) {
    throw new Error("expected-failure data must be a JSON object");
  }
  if (
    expectedFailures.expected_failures === null ||
    typeof expectedFailures.expected_failures !== "object" ||
    Array.isArray(expectedFailures.expected_failures)
  ) {
    throw new Error("expected-failure data must contain an expected_failures object");
  }

  const native = readFileSync(join(artifactDir, contract.native_output_file), "utf8");
  if (!/^test .+ \.\.\. (?:ok|FAILED|ignored)$/m.test(native)) {
    throw new Error("native output contains no cargo test verdicts");
  }

  const census = parseJsonFile(join(artifactDir, contract.census_file), "Wasm census");
  const summary = census?.summary;
  if (!summary || !Number.isSafeInteger(summary.registered) || summary.registered <= 0) {
    throw new Error("Wasm census is empty or has no positive registered count");
  }
  if (
    summary.executed !== summary.registered ||
    summary.distinctNames !== summary.registered ||
    summary.repetitions !== 1
  ) {
    throw new Error("Wasm census counts are incomplete or non-distinct");
  }
  if (summary.sha256 !== digest.sha256) throw new Error("Wasm census digest does not match the module");
  if (!Array.isArray(census.results) || census.results.length !== summary.registered) {
    throw new Error("Wasm census result set does not match its registered count");
  }
  const names = census.results.map((row) => row?.name);
  if (names.some((name) => typeof name !== "string" || !name) || new Set(names).size !== names.length) {
    throw new Error("Wasm census test-name set is empty or non-distinct");
  }
  if (!Array.isArray(summary.imports) || summary.imports.some((entry) => typeof entry !== "string")) {
    throw new Error("Wasm census import set is malformed");
  }
  const expectedImports = { imports: [...new Set(summary.imports)].sort() };
  const imports = parseJsonFile(join(artifactDir, contract.imports_file), "Wasm import set");
  if (canonicalDeep(imports) !== canonicalDeep(expectedImports)) {
    throw new Error("Wasm import set does not match the census");
  }
  const testNameSetSha256 = sha256(Buffer.from(`${[...names].sort().join("\n")}\n`));
  if (summary.testNameSetSha256 !== testNameSetSha256) {
    throw new Error("Wasm census test-name-set digest does not match its results");
  }
  const topologySha256 = sha256(Buffer.from(canonicalDeep(topology)));
  const artifactFiles = [...payloadNames, contract.manifest_file].sort();
  return {
    schema: "temper-wasm-pr-preview-artifact-v1",
    source: { ...identity },
    candidate: {
      crate: contract.crate,
      cargo_features: contract.cargo_features,
      staged_module: contract.module_file,
      expected_failures_source: contract.expected_failures_source,
      native_test_args: contract.native_test_args,
      topology_sha256: topologySha256,
    },
    census: {
      registered: summary.registered,
      executed: summary.executed,
      distinct_names: summary.distinctNames,
      wasm_sha256: digest.sha256,
      test_name_set_sha256: testNameSetSha256,
      imports: expectedImports.imports,
    },
    limits: {
      max_wasm_bytes: MAX_PREVIEW_WASM_BYTES,
      max_file_bytes: MAX_PREVIEW_FILE_BYTES,
      max_payload_bytes: MAX_PREVIEW_TOTAL_BYTES,
    },
    artifact_files: artifactFiles,
    files: fileRecords,
  };
}

/** Derive imports, validate every payload byte, and write the canonical manifest. */
export function attestPreviewArtifact({ artifactDir, identity, topology }) {
  const contract = previewCandidateContract(topology);
  const initialNames = [
    contract.module_file,
    contract.digest_file,
    contract.expected_failures_file,
    contract.native_output_file,
    contract.census_file,
  ];
  assertRegularFiles(artifactDir, initialNames);
  const census = parseJsonFile(join(artifactDir, contract.census_file), "Wasm census");
  if (!Array.isArray(census?.summary?.imports)) throw new Error("Wasm census import set is malformed");
  writeFileSync(
    join(artifactDir, contract.imports_file),
    `${JSON.stringify({ imports: [...new Set(census.summary.imports)].sort() })}\n`,
  );
  assertRegularFiles(artifactDir, [...initialNames, contract.imports_file]);
  const manifest = inspectPreviewPayload({ artifactDir, identity, topology });
  writeFileSync(join(artifactDir, contract.manifest_file), `${canonicalDeep(manifest)}\n`);
  assertRegularFiles(artifactDir, manifest.artifact_files);
  return manifest;
}

/** Re-validate an already-attested artifact without trusting its manifest. */
export function validatePreviewArtifact({ artifactDir, topology }) {
  const contract = previewCandidateContract(topology);
  const manifest = parseJsonFile(join(artifactDir, contract.manifest_file), "preview manifest");
  assertRegularFiles(artifactDir, manifest?.artifact_files ?? []);
  const expected = inspectPreviewPayload({ artifactDir, identity: manifest.source, topology });
  if (canonicalDeep(manifest) !== canonicalDeep(expected)) {
    throw new Error("preview manifest does not match the artifact payload, identity, or topology");
  }
  return manifest;
}

function cliValue(args, name) {
  const index = args.indexOf(name);
  if (index === -1 || !args[index + 1]) throw new Error(`missing required ${name}`);
  return args[index + 1];
}

async function previewCli(args) {
  const command = args[0];
  const topologyPath = cliValue(args, "--topology");
  const topology = loadTopology(topologyPath);
  if (command === "preview-candidate") {
    process.stdout.write(`${JSON.stringify(previewCandidateContract(topology))}\n`);
    return;
  }
  const artifactDir = cliValue(args, "--artifact-dir");
  if (command === "attest-preview") {
    const identity = JSON.parse(cliValue(args, "--identity-json"));
    const manifest = attestPreviewArtifact({ artifactDir, identity, topology });
    process.stdout.write(`${JSON.stringify(manifest)}\n`);
    return;
  }
  if (command === "validate-preview") {
    const manifest = validatePreviewArtifact({ artifactDir, topology });
    process.stdout.write(`${JSON.stringify(manifest)}\n`);
    return;
  }
  throw new Error(`unknown command ${JSON.stringify(command)}`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  previewCli(process.argv.slice(2)).catch((error) => {
    console.error(`error: ${error.message}`);
    process.exitCode = 1;
  });
}

/**
 * Every distinct (cargo_features → staged_module) build the staging script must
 * perform, deduplicated: temper-geometry's (and temper-thermal's) full corpus
 * and only shard are the same module and must not be compiled twice.
 */
export function buildTargets(topology) {
  const seen = new Set();
  const out = [];
  for (const tier of topology.tiers) {
    for (const b of [tier, ...tier.shards]) {
      const key = `${b.cargo_features}|${b.staged_module}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ crate: tier.crate, cargo_features: b.cargo_features, staged_module: b.staged_module });
    }
  }
  return out;
}

/**
 * Every distinct Cloudflare script to deploy, deduplicated by wrangler
 * directory for the same reason as buildTargets.
 */
export function deployTargets(topology) {
  const seen = new Set();
  const out = [];
  for (const tier of topology.tiers) {
    for (const d of [tier, ...tier.shards]) {
      const script = d.worker ?? d.full_corpus_worker;
      if (seen.has(d.wrangler_dir)) continue;
      seen.add(d.wrangler_dir);
      out.push({ crate: tier.crate, script, wrangler_dir: d.wrangler_dir });
    }
  }
  return out;
}

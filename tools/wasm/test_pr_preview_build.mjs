#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  chmodSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  truncateSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import test from "node:test";

import {
  MAX_PREVIEW_WASM_BYTES,
  attestPreviewArtifact,
  loadTopology,
  previewCandidateContract,
  validatePreviewArtifact,
} from "./tier_topology.mjs";

const topology = loadTopology();
const sha256 = (value) => createHash("sha256").update(value).digest("hex");

function identity(overrides = {}) {
  return {
    base_repository: "temper/temper",
    base_sha: "1".repeat(40),
    candidate: "temper-io-types",
    event_name: "pull_request_target",
    head_repository: "temper/temper",
    head_sha: "2".repeat(40),
    pull_request_number: 42,
    run_attempt: 1,
    run_id: 1234,
    ...overrides,
  };
}

function fixture() {
  const dir = mkdtempSync(join(tmpdir(), "temper-preview-artifact-"));
  const contract = previewCandidateContract(topology);
  const wasm = Buffer.from("not executed by the attester");
  const wasmDigest = sha256(wasm);
  const names = ["alpha", "beta"];
  writeFileSync(join(dir, contract.module_file), wasm);
  writeFileSync(
    join(dir, contract.digest_file),
    `${JSON.stringify({ sha256: wasmDigest })}\n`,
  );
  writeFileSync(
    join(dir, contract.expected_failures_file),
    `${JSON.stringify({ expected_failures: {} })}\n`,
  );
  writeFileSync(join(dir, contract.native_output_file), "test alpha ... ok\ntest beta ... ok\n");
  writeFileSync(
    join(dir, contract.census_file),
    `${JSON.stringify({
      summary: {
        sha256: wasmDigest,
        registered: names.length,
        executed: names.length,
        distinctNames: names.length,
        repetitions: 1,
        imports: [],
        testNameSetSha256: sha256(Buffer.from(`${[...names].sort().join("\n")}\n`)),
      },
      results: names.map((name, index) => ({ index, name, status: "pass" })),
    })}\n`,
  );
  return { contract, dir };
}

function withFixture(fn) {
  const value = fixture();
  try {
    return fn(value);
  } finally {
    rmSync(value.dir, { recursive: true, force: true });
  }
}

test("the preview contract selects exactly one topology-owned candidate", () => {
  const contract = previewCandidateContract(topology);
  assert.equal(contract.crate, "temper-io-types");
  assert.equal(contract.cargo_features, "io-types-wasm-test-registry");
  assert.equal(contract.module_file, "temper_wasm_test_runner_io_types.wasm");
  assert.equal(contract.max_wasm_bytes, MAX_PREVIEW_WASM_BYTES);
  assert.equal(
    basename(contract.expected_failures_source),
    "wasm_expected_failures_io_types.json",
  );
});

test("candidate staging follows topology feature and filename changes", () => {
  const changed = structuredClone(topology);
  const tier = changed.tiers.find((entry) => entry.crate === "temper-io-types");
  tier.cargo_features = "renamed-registry-feature";
  tier.staged_module = "renamed_candidate.wasm";
  tier.shards[0].cargo_features = tier.cargo_features;
  tier.shards[0].staged_module = tier.staged_module;
  const contract = previewCandidateContract(changed);
  assert.equal(contract.cargo_features, "renamed-registry-feature");
  assert.equal(contract.module_file, "renamed_candidate.wasm");
});

test("the staging script builds only the topology-derived preview target", () => {
  const dir = mkdtempSync(join(tmpdir(), "temper-preview-stage-"));
  try {
    const repo = join(dir, "head");
    const output = join(dir, "artifact");
    const target = join(dir, "target");
    const bin = join(dir, "bin");
    mkdirSync(join(repo, "packages", "temper-wasm-test-runner"), { recursive: true });
    mkdirSync(output);
    mkdirSync(bin);
    const changed = structuredClone(topology);
    const tier = changed.tiers.find((entry) => entry.crate === "temper-io-types");
    tier.cargo_features = "renamed_registry_feature";
    tier.staged_module = "renamed_candidate.wasm";
    tier.shards[0].cargo_features = tier.cargo_features;
    tier.shards[0].staged_module = tier.staged_module;
    const topologyPath = join(dir, "topology.json");
    writeFileSync(topologyPath, JSON.stringify(changed));
    const cargo = join(bin, "cargo");
    writeFileSync(
      cargo,
      "#!/bin/bash\nset -euo pipefail\nmkdir -p \"${CARGO_TARGET_DIR}/wasm32-unknown-unknown/release\"\nprintf fake-wasm > \"${CARGO_TARGET_DIR}/wasm32-unknown-unknown/release/temper_wasm_test_runner.wasm\"\nprintf '%s\\n' \"$*\" > \"${FAKE_CARGO_ARGS}\"\n",
    );
    chmodSync(cargo, 0o755);
    const result = spawnSync(
      "bash",
      [
        fileURLToPath(new URL("../../scripts/stage_wasm_families.sh", import.meta.url)),
        "--preview-candidate",
        "--repo-root", repo,
        "--topology", topologyPath,
        "--output-dir", output,
        "--target-dir", target,
      ],
      {
        encoding: "utf8",
        env: {
          ...process.env,
          FAKE_CARGO_ARGS: join(dir, "cargo-args.txt"),
          PATH: `${bin}:${process.env.PATH}`,
        },
      },
    );
    assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
    assert.deepEqual(readdirSync(output).sort(), [
      "renamed_candidate.wasm",
      "renamed_candidate.wasm.sha256.json",
    ]);
    assert.match(readFileSync(join(dir, "cargo-args.txt"), "utf8"), /--features renamed_registry_feature/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("zero candidates and a candidate with two build modules fail closed", () => {
  const empty = structuredClone(topology);
  empty.promotion_candidates = [];
  assert.throws(() => previewCandidateContract(empty), /exactly one promotion candidate/);

  const multiple = structuredClone(topology);
  const tier = multiple.tiers.find((entry) => entry.crate === "temper-io-types");
  tier.shards.push({
    ...tier.shards[0],
    family: "other",
    cargo_features: "other-feature",
    staged_module: "other.wasm",
  });
  assert.throws(() => previewCandidateContract(multiple), /exactly one build target/);
});

test("untrusted topology cannot inject shell fields or paths", () => {
  const mutations = [
    (tier) => {
      tier.cargo_features = "valid\tsecond-row";
      tier.shards[0].cargo_features = tier.cargo_features;
    },
    (tier) => {
      tier.staged_module = "../escaped.wasm";
      tier.shards[0].staged_module = tier.staged_module;
    },
    (tier) => tier.native_test_args.push("--config=build.rustc-wrapper=evil"),
    (tier) => tier.expected_failures = "../../other.json",
  ];
  for (const mutate of mutations) {
    const changed = structuredClone(topology);
    mutate(changed.tiers.find((entry) => entry.crate === "temper-io-types"));
    assert.throws(() => previewCandidateContract(changed), /unsafe|native_test_args/);
  }
});

test("a valid artifact is complete, self-describing, and supports a fork source", () => {
  withFixture(({ contract, dir }) => {
    const manifest = attestPreviewArtifact({
      artifactDir: dir,
      identity: identity({ head_repository: "contributor/temper" }),
      topology,
    });
    assert.equal(manifest.source.head_repository, "contributor/temper");
    assert.equal(manifest.source.head_sha, "2".repeat(40));
    assert.equal(manifest.candidate.crate, "temper-io-types");
    assert.equal(manifest.census.registered, 2);
    assert.equal(manifest.files[contract.module_file].sha256, manifest.census.wasm_sha256);
    assert.deepEqual(manifest.artifact_files.sort(), [
      contract.census_file,
      contract.digest_file,
      contract.expected_failures_file,
      contract.imports_file,
      contract.manifest_file,
      contract.module_file,
      contract.native_output_file,
    ].sort());
    assert.deepEqual(validatePreviewArtifact({ artifactDir: dir, topology }), manifest);
  });
});

test("empty census, digest mismatch, a second module, oversize Wasm, and missing native fail", () => {
  const mutations = [
    ({ contract, dir }) => {
      const census = JSON.parse(readFileSync(join(dir, contract.census_file), "utf8"));
      census.summary.registered = 0;
      census.summary.executed = 0;
      census.summary.distinctNames = 0;
      census.results = [];
      writeFileSync(join(dir, contract.census_file), JSON.stringify(census));
    },
    ({ contract, dir }) => {
      writeFileSync(join(dir, contract.digest_file), `${JSON.stringify({ sha256: "0".repeat(64) })}\n`);
    },
    ({ dir }) => writeFileSync(join(dir, "unexpected_second.wasm"), "wasm"),
    ({ contract, dir }) => truncateSync(join(dir, contract.module_file), MAX_PREVIEW_WASM_BYTES + 1),
    ({ contract, dir }) => rmSync(join(dir, contract.native_output_file)),
  ];
  const messages = [/empty/i, /digest/i, /unexpected/i, /too large/i, /native/i];
  mutations.forEach((mutate, index) => {
    withFixture((value) => {
      mutate(value);
      assert.throws(
        () => attestPreviewArtifact({ artifactDir: value.dir, identity: identity(), topology }),
        messages[index],
      );
    });
  });
});

test("manifest validation detects payload rewrites", () => {
  withFixture(({ contract, dir }) => {
    attestPreviewArtifact({ artifactDir: dir, identity: identity(), topology });
    writeFileSync(join(dir, contract.native_output_file), "test rewritten ... ok\n");
    assert.throws(() => validatePreviewArtifact({ artifactDir: dir, topology }), /digest|size|payload/i);
  });
});

test("the base-owned workflow checks out and attests an exact credential-free head", () => {
  const workflow = readFileSync(
    new URL("../../.github/workflows/wasm-tier-preview-verdict.yml", import.meta.url),
    "utf8",
  );
  assert.match(workflow, /pull_request_target:/);
  assert.match(workflow, /permissions:\s*\n\s*contents: read/);
  assert.match(workflow, /ref: \$\{\{ github\.event\.pull_request\.head\.sha \}\}/);
  assert.match(workflow, /repository: \$\{\{ github\.event\.pull_request\.head\.repo\.full_name \}\}/);
  assert.ok((workflow.match(/persist-credentials: false/g) ?? []).length >= 2);
  assert.match(workflow, /git -C .* rev-parse HEAD/);
  assert.match(workflow, /refs\/pull\/.*\/merge/);
  assert.match(workflow, /\/control\/scripts\/stage_wasm_families\.sh/);
  assert.match(workflow, /\/control\/tools\/wasm\/run_wasm_tests\.mjs/);
  assert.match(workflow, /\/control\/tools\/wasm\/tier_topology\.mjs/);
  assert.match(workflow, /head\.crate !== base\.crate/);
  assert.match(workflow, /HEAD_SHA}:tools\/wasm\/wasm_tier_topology\.json/);
  assert.match(workflow, /github\.run_id.*github\.run_attempt/);
  assert.doesNotMatch(workflow, /actions\/cache|save-cache/);
  assert.doesNotMatch(workflow, /secrets\./);
  assert.doesNotMatch(workflow, /uses:\s*[^\n]+@(v\d+|main|master)\b/);
});

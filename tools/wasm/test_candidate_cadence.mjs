#!/usr/bin/env node

import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  loadTopology,
  scheduledComparisonTiers,
  tierFlagSuffix,
} from "./tier_topology.mjs";

const committed = loadTopology();

function withCandidates(candidates, fn) {
  const dir = mkdtempSync(join(tmpdir(), "wasm-candidate-cadence-"));
  const path = join(dir, "topology.json");
  const topology = structuredClone(committed);
  topology.promotion_candidates = candidates;
  writeFileSync(path, `${JSON.stringify(topology)}\n`);
  try {
    return fn(path);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test("empty promotion candidate list preserves the single rotated tier", () => {
  withCandidates([], (path) => {
    const topology = loadTopology(path);
    assert.deepEqual(
      scheduledComparisonTiers(topology, "temper-geometry").map((tier) => tier.crate),
      ["temper-geometry"],
    );
  });
});

test("a non-rotated candidate is added after the rotated tier", () => {
  withCandidates(["temper-io-types"], (path) => {
    const topology = loadTopology(path);
    assert.deepEqual(
      scheduledComparisonTiers(topology, "temper-geometry").map((tier) => tier.crate),
      ["temper-geometry", "temper-io-types"],
    );
  });
});

test("a candidate rotation night derives the candidate exactly once", () => {
  withCandidates(["temper-io-types"], (path) => {
    const topology = loadTopology(path);
    assert.deepEqual(
      scheduledComparisonTiers(topology, "temper-io-types").map((tier) => tier.crate),
      ["temper-io-types"],
    );
  });
});

test("unknown candidates fail topology validation", () => {
  withCandidates(["temper-not-a-tier"], (path) => {
    assert.throws(() => loadTopology(path), /unknown promotion candidate.*temper-not-a-tier/);
  });
});

test("duplicate candidates fail topology validation", () => {
  withCandidates(["temper-io-types", "temper-io-types"], (path) => {
    assert.throws(() => loadTopology(path), /duplicate promotion candidate.*temper-io-types/);
  });
});

test("the promotion contract currently admits at most one distinct candidate", () => {
  withCandidates(["temper-io-types", "temper-geometry"], (path) => {
    assert.throws(() => loadTopology(path), /supports at most one candidate/);
  });
});

test("malformed candidate contracts fail closed", () => {
  for (const malformed of [null, "temper-io-types", [""], [42]]) {
    withCandidates(malformed, (path) => {
      assert.throws(() => loadTopology(path), /promotion_candidates/);
    });
  }
});

test("two selected tiers have collision-safe artifact suffixes", () => {
  withCandidates(["temper-io-types"], (path) => {
    const topology = loadTopology(path);
    const suffixes = scheduledComparisonTiers(topology, "temper-geometry").map((tier) =>
      tierFlagSuffix(tier.crate),
    );
    assert.deepEqual(suffixes, ["geometry", "io-types"]);
    assert.equal(new Set(suffixes).size, suffixes.length);
    assert.deepEqual(
      suffixes.map((suffix) => `/tmp/r19_local_${suffix}_commit_board.json`),
      [
        "/tmp/r19_local_geometry_commit_board.json",
        "/tmp/r19_local_io-types_commit_board.json",
      ],
    );
  });
});

test("nightly narrows native/R19 work to the selected set but keeps the all-tier census", () => {
  const workflow = readFileSync(
    new URL("../../.github/workflows/wasm-tier-nightly.yml", import.meta.url),
    "utf8",
  );
  assert.ok(
    workflow.split("scheduledComparisonTiers").length - 1 >= 3,
    "selection, native, and local R19 steps must share the cadence helper",
  );
  const census = workflow.slice(
    workflow.indexOf("- name: Build + run every tier's wasm32 registry"),
    workflow.indexOf("- name: Anti-vacuity"),
  );
  assert.match(census, /for \(const t of loadTopology\(\)\.tiers\)/);
  assert.match(workflow, /--runtime-arm local-node/);
  assert.match(workflow, /diagnostic\/non-qualifying/);
});

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

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
export const TOPOLOGY_PATH = join(HERE, "wasm_tier_topology.json");

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
 * Worker AND a shard of the SAME tier (that is exactly temper-wasm-geometry),
 * but never across tiers.
 */
function validate(t, path) {
  if (!Array.isArray(t?.tiers) || t.tiers.length === 0) {
    throw new Error(`${path}: "tiers" must be a non-empty array`);
  }
  if (typeof t.base_domain !== "string" || !t.base_domain) {
    throw new Error(`${path}: "base_domain" must be a non-empty string`);
  }
  const owner = new Map(); // worker script name -> crate that claims it
  for (const tier of t.tiers) {
    for (const field of ["crate", "cargo_features", "staged_module", "full_corpus_worker", "wrangler_dir", "expected_failures"]) {
      if (typeof tier[field] !== "string" || !tier[field]) {
        throw new Error(`${path}: tier ${tier.crate ?? "?"} is missing string field "${field}"`);
      }
    }
    if (!Array.isArray(tier.shards) || tier.shards.length === 0) {
      throw new Error(`${path}: tier ${tier.crate} must declare at least one shard`);
    }
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
}

/** `https://<script>.<base_domain>` */
export function workerUrl(topology, script) {
  return `https://${script}.${topology.base_domain}`;
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
 * Every distinct (cargo_features → staged_module) build the staging script must
 * perform, deduplicated: temper-geometry's full corpus and its only shard are
 * the same module and must not be compiled twice.
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

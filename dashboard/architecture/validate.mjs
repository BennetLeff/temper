#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const architectureDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(architectureDir, "../..");

function parseArgs(argv) {
  const options = { writeBuildInfo: null, commit: null, ref: null };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    const value = argv[index + 1];
    if (argument === "--write-build-info") options.writeBuildInfo = value;
    else if (argument === "--commit") options.commit = value;
    else if (argument === "--ref") options.ref = value;
    else throw new Error(`Unknown argument: ${argument}`);
    if (!value) throw new Error(`Missing value for ${argument}`);
    index += 1;
  }
  return options;
}

function uniqueById(items, label, errors) {
  const seen = new Set();
  for (const item of items) {
    if (!item.id) errors.push(`${label} has an entry without an id`);
    else if (seen.has(item.id)) errors.push(`${label} has duplicate id: ${item.id}`);
    seen.add(item.id);
  }
  return seen;
}

function validate(data) {
  const errors = [];
  const { districts, nodes, edges, palette, flowColors } = data;
  const districtIds = uniqueById(districts, "districts", errors);
  const nodeIds = uniqueById(nodes, "nodes", errors);
  uniqueById(edges, "edges", errors);

  for (const node of nodes) {
    if (!districtIds.has(node.district)) errors.push(`${node.id}: unknown district ${node.district}`);
    if (!palette[node.kind]) errors.push(`${node.id}: unknown palette kind ${node.kind}`);
    if (!Array.isArray(node.sources) || node.sources.length === 0) errors.push(`${node.id}: no source citations`);
    for (const [sourcePath, description] of node.sources ?? []) {
      const resolved = path.resolve(repoRoot, sourcePath);
      const insideRepo = resolved === repoRoot || resolved.startsWith(`${repoRoot}${path.sep}`);
      if (!insideRepo) errors.push(`${node.id}: source escapes repository: ${sourcePath}`);
      else if (!fs.existsSync(resolved)) errors.push(`${node.id}: cited source does not exist: ${sourcePath}`);
      if (!description?.trim()) errors.push(`${node.id}: source lacks a description: ${sourcePath}`);
    }
  }

  for (const edge of edges) {
    if (!nodeIds.has(edge.from)) errors.push(`${edge.id}: unknown sender ${edge.from}`);
    if (!nodeIds.has(edge.to)) errors.push(`${edge.id}: unknown receiver ${edge.to}`);
    if (!flowColors[edge.flow]) errors.push(`${edge.id}: unknown flow ${edge.flow}`);
    if (!edge.payload?.trim()) errors.push(`${edge.id}: missing payload`);
  }

  return errors;
}

function writeBuildInfo(outputPath, { commit, ref }) {
  if (!commit || !ref) throw new Error("--write-build-info requires --commit and --ref");
  const resolvedOutput = path.resolve(process.cwd(), outputPath);
  const info = {
    commit,
    ref
  };
  const contents = `globalThis.TEMPER_ATLAS_BUILD = Object.freeze(${JSON.stringify(info, null, 2)});\n`;
  fs.writeFileSync(resolvedOutput, contents, "utf8");
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  globalThis.TEMPER_ATLAS_VALIDATE_ONLY = true;
  await import(pathToFileURL(path.join(architectureDir, "app.js")).href);
  const data = globalThis.TEMPER_ATLAS_DATA;
  if (!data) throw new Error("app.js did not expose TEMPER_ATLAS_DATA in validation mode");

  const errors = validate(data);
  if (errors.length) {
    console.error(`Architecture atlas validation failed (${errors.length} errors):`);
    for (const error of errors) console.error(`  - ${error}`);
    process.exitCode = 1;
    return;
  }

  if (options.writeBuildInfo) writeBuildInfo(options.writeBuildInfo, options);
  const sourceCount = data.nodes.reduce((total, node) => total + node.sources.length, 0);
  console.log(`Architecture atlas valid: ${data.nodes.length} structures, ${data.edges.length} paths, ${sourceCount} citations.`);
}

main().catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});

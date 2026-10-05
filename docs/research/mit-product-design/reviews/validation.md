# Corpus, skill and application validation

Validated 2026-10-03. Ten Sol agents were used across source collection, skill authorship, independent review and product application; the parent integrated and checked their work. This document records the bounds of those checks.

| Check | Result | What it establishes |
|---|---|---|
| Source-cache integrity | PASS: 60 manifest-listed cached source files; no missing file/hash/PDF-signature errors | Bytes agree with manifests. 55 PDF copies represent 47 unique hashes; 11 are lecture transcripts. This does not establish complete content review. |
| Product input identity | PASS: 21 live selected files and local snapshots match manifest hashes | The reviewed working-source bytes are pinned. The source checkout is dirty; Git HEAD alone is insufficient. |
| Four skill schemas | PASS: skill-creator `quick_validate.py` | Names, frontmatter and required skill structure. This is not a behavioral test. |
| Independent skill behavior/source review | PASS with targeted corrections applied | Reviewers sampled primary-source claims and ran realistic scenarios. See the three review reports below. |
| Installed skills | PASS: every installed file matches the versioned skill copy | Four skills installed under `/Users/bennet/.codex/skills/`; [installation receipt](skill-installation.json) pins entry hashes. |
| Full-bridge audit | PASS: 91 components, 67 nets; 17/17 tests | Existing constrained connectivity/identity checks and deliberate miswire tests reproduce. No layout, electrical-stress or physical qualification claim. [Commands and output](../application/electrical-evidence/receipt.md). |
| Capacitor source review | Exact 942C12P1K-F and 942C12P22K-F rows visually confirmed on PDF p. 3 | Manufacturer table groups these at 1200 Vdc/430 Vac; p. 1 defines the AC catalog rating at 60 Hz. The actual operating-frequency/waveform envelope remains open. |
| `make regen` and `make regen-check` | PASS; no derived-file diff | Repo state, seven WASM registries, oracle hashes, hash-order, manifest, kernel and wire-format checks consistent. No pin drift was accepted. |
| Import-boundary gate | UNAVAILABLE: exit 5, missing `lint-imports` executable | Tool failure, not a clean report and not an observed contract violation. No application import code changed. |
| Whitespace/local links | PASS after correcting a mechanical evidence line locator and local links | Added documentation has no missing local Markdown targets in the retained worktree. External URL availability varies; download hashes preserve source identity. |

## What independent review changed

- [PCB review](pcb-skill-review.md): explicitly bound the full sensing-to-current-extinction chain; retained tank/bus energy, failed-short interruption, MOV/fuse coordination, deterministic corners, and the missing-layout case. The hypothetical scenario was not a product finding.
- [Mechanical review](mechanical-skill-review.md): added two-sided actuator travel/force inequalities and seal compression/cycle/reassembly analysis. Applied separately to the actual package records afterward.
- [Product/manufacturing review](product-manufacturing-skill-review.md): clarified process/volume transitions, stage decisions and responsible roles, and cosmetic seam versus cleaning/service tradeoffs. The hypothetical 20/20,000 volumes are not Temper production commitments.

Parent integration corrected the electrical finding to an **unsupported model acceptance criterion**, not a proven physical overvoltage. It also preserved the distinction between the capacitor's 60 Hz nameplate, its frequency-dependent envelope, and the sinusoidal assumption behind peak-to-RMS conversion. The mechanical sampled-travel citation was corrected to R2 validation JSON line 352.

## Reproduction

Run the skill-creator validator against each `skills/temper-*` directory. The working interpreter for this session was `/Users/bennet/Miniforge3/bin/python3`, which already contains PyYAML. The default interpreter in the isolated worktree and the bundled runtime lacked it; no dependency was installed into the shared project environment.

Repository regeneration used `UV_PROJECT_ENVIRONMENT=/Users/bennet/Desktop/temper/.venv`, `UV_CACHE_DIR=/private/tmp/temper-mit-uv-cache`, `PYTHONPATH=packages/temper-placer/src`, and the Makefile's `--no-sync` commands. No package synchronization, shared Cargo build, Rust extension rebuild, DRC run, or new physical experiment was performed. The independent electrical audit used standalone `rustc` with outputs in temporary storage, as recorded in its receipt.

Raw MIT/manufacturer sources and snapshots of another task's untracked product files remain local and Git-excluded. The repository contains original skills, summaries, manifests, reviews and hashes; cloning it alone does not restore those excluded caches. Source rights and third-party exceptions remain item-specific.

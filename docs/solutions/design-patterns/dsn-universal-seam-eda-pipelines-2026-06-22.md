---
title: "Pattern: SPECCTRA DSN/SES as Universal Seam for EDA Pipelines"
date: 2026-06-22
category: design-patterns
module: temper_placer
problem_type: design_pattern
component: development_workflow
severity: high
applies_when:
  - Multiple pipeline stages produce or consume PCB layout data
  - Parity tests between different tools or formats are needed
  - External tool interop (FreeRouting, KiCad, Altium) is a requirement
  - Intermediate data must be human-readable and diffable for code review
tags:
  - dsn
  - ses
  - specctra
  - intermediate-format
  - pipeline-seam
  - eda
  - deterministic-serialization
  - git-diff
  - content-hash
  - freerouting
  - schema-versioning
  - json-sidecar
  - normalizer
---

# Pattern: SPECCTRA DSN/SES as Universal Seam for EDA Pipelines

## Context

Temper's PCB design automation has three pipeline systems (placement, routing,
validation, and output generation), each producing or consuming PCB layout data.
Before adopting SPECCTRA DSN/SES as the canonical intermediate format at every
pipeline stage boundary, each system used its own incompatible internal Python
state representation. A `PlacementResult` from the placer could not be fed into
the router without bespoke conversion code. Parity tests between pipelines were
impossible because there was no shared representation against which to compute a
diff.

The problem grew with each new pipeline stage: every boundary needed a
point-to-point converter, every converter had drift risks, and changes in one
system's internal format silently invalidated downstream consumers. External tool
interop (FreeRouting) required yet another bespoke export path.

The solution selected SPECCTRA DSN/SES — a human-readable, diffable, industry
standard format supported natively by KiCad, FreeRouting, and Altium — as the
single canonical interchange format. Every pipeline stage serializes to and
deserializes from DSN at its boundaries. The format is not used as the internal
working representation (that remains optimized Python objects); it is the seam.

## Guidance

### Core principles

1. **Byte-identical serialization with deterministic ordering.** DSN output must
   be byte-for-byte identical for the same semantic input. This means:
   - No timestamps, tool versions, or non-semantic metadata in the output.
   - Collection iteration order must be deterministic (sorted keys for
     hashmap-based structures, explicit `sort()` on sequences).
   - Floating-point values must use a fixed precision and format (e.g.,
     `f"{value:.6f}"`) and never use `repr()` which varies by Python version.
   - Line endings must be normalized (`\n` only, no `\r\n`).

2. **Content-hash schema versioning in DSN comment headers.** Every DSN file
   starts with a header comment block containing a content-hash of the schema
   definition used to produce it. Consumers check this hash before parsing and
   fail with a clear message if the hash does not match any supported schema
   version. This allows consumers to detect format changes without a central
   registry or version negotiation protocol.

   ```
   (temper_schema_hash abc123def456)
   (temper_schema_version 3)
   ```

3. **DSN is lossy for non-geometric data — use JSON sidecars.** DSN carries
   geometric and connectivity data (components, nets, layers, tracks, vias).
   It does not carry internal analysis artifacts such as occupancy grids,
   channel capacity maps, routing congestion heat maps, or placer cost matrices.
   These are written alongside the DSN file as `.json` sidecars with matching
   basenames. The sidecar is not part of the DSN seam contract; it is an
   optional enrichment that downstream stages may consume if available.

   ```
   output/placement.dsn          ← canonical seam file
   output/placement.cost.json    ← optional sidecar (occupancy grid)
   output/placement.channels.json ← optional sidecar (channel capacity)
   ```

4. **Semantic normalizer strips non-semantic noise.** A dedicated normalizer
   pass strips timestamps, tool version strings, generator provenance comments,
   and other non-semantic content from DSN files before they are committed or
   diffed. The normalizer runs as part of the serialization step and produces
   `*.normalized.dsn` files that are safe for `git diff`.

5. **Incremental boundary registration.** Not all pipeline stage boundaries
   are registered in one pass. Start with the highest-value boundaries — those
   that enable the most interop or the most parity testing — and register
   additional boundaries as confidence in the format grows. The first five
   boundaries registered were: placer output (`placement.dsn`), router input
   (same file), router output (`routing.ses`), validation input (same file),
   and output generation input (`routing.ses`). The remaining 34 internal
   boundaries remain unconverted and use the legacy internal format until
   registration is justified.

### Pipeline topology

```
Placer ──→ placement.dsn ──→ Router ──→ routing.ses ──→ Validator ──→ routing.ses ──→ Output Gen
              │                                │                      │
              ├── placement.cost.json          ├── routing.cost.json   ├── validation.report.json
              └── placement.channels.json      └── routing.grid.json   └── validation.errors.json
```

### Normalizer contract

The normalizer must be idempotent: `normalize(normalize(x)) == normalize(x)`.
It must also be semantic-preserving: the normalized file parses to the same
geometric and connectivity data as the original. The normalizer is the sole
authority on what constitutes a semantic change vs. a cosmetic change for `git
diff` purposes.

### FreeRouting interop verification

Temper-produced DSN feeds to FreeRouting without any preprocessing or
postprocessing:

```bash
freerouting -de placement.dsn -do routing.ses
```

The round-trip was verified by routing a temper-placed board through FreeRouting
and loading the resulting `.ses` back into the temper validation pipeline. No
format adaptation or field remapping was needed.

## Why This Matters

Before DSN as universal seam, three pipelines used three incompatible internal
state formats. A change to the placer's internal `PlacementResult` class broke
the router silently until a human noticed the routing output was wrong. Parity
tests required writing a full adapter for every pair of formats — an M×N problem
that no one attempted at scale.

The DSN seam reduces this to an N problem: every stage speaks one format at its
boundaries. Parity testing becomes `git diff placement_v1.dsn placement_v2.dsn`
— a single command, not a bespoke test harness. Code review of pipeline changes
becomes reading a diff of a human-readable text file, not inspecting Python
object dumps.

The deterministic serialization requirement is load-bearing: without it, two
runs of the same placer on the same input produce different DSN files (iterator
order, timestamp, tool version), and `git diff` is useless. Byte-identical
output for the same semantic input is the property that makes `git diff` usable
as a parity checker.

The content-hash schema versioning removes the coordination problem of format
evolution. A consumer that sees an unrecognized schema hash fails immediately
with a clear message, rather than silently misinterpreting a field. No central
registry, no version negotiation, no runtime format detection by heuristic.

## When to Apply

Apply this pattern when:

- Multiple pipeline stages produce or consume the same domain of data and need
  interop or parity testing.
- The domain data has a well-defined, stable industry standard format that is
  human-readable and diffable (DSN for PCB, GLTF for 3D, SVG for vector
  graphics, etc.).
- The format is supported natively by at least one external tool you depend on
  (free rider: you get interop without writing a converter).
- The internal working representation benefits from properties the interchange
  format does not provide (performance, rich object graphs, analysis data), and
  the internal↔interchange conversion cost is acceptable.

Do NOT apply when:

- The domain has no stable industry standard format and inventing one adds more
  maintenance cost than the M×N converter problem it solves.
- All pipeline stages are tightly coupled in the same process and can share a
  single internal representation without overhead.
- The interchange format is binary, non-diffable, or requires a heavy parser
  that dominates runtime (DSN is text and parses in milliseconds for realistic
  board sizes).
- The format is lossy for data that downstream stages genuinely need and the
  sidecar pattern cannot compensate (e.g., the format cannot represent the
  topology at all).

### Decision flow

```
Multiple pipeline stages share PCB data
    │
    ├─ Does an industry standard interchange format exist? ── No ──→ Define internal schema; evaluate later
    │
    ├─ Is the format human-readable and diffable? ── No ──→ Binary format: only if performance dominates
    │
    ├─ Is deterministic byte-identical output achievable? ── No ──→ DSN seam not viable; use schema-aware comparator
    │
    ├─ Are there analysis artifacts the format cannot carry? ── Yes ──→ Add JSON sidecar pattern
    │
    └─ Yes → Register highest-value boundaries first; expand incrementally
```

## Examples

### DSN header with content-hash schema versioning

```
(temper_schema_hash a1b2c3d4e5f6)
(temper_schema_version 7)
(pcb temper_induction_v2
  (parser
    (string_quote \"))
  (resolution um 1000)
  (unit um)
  ...
)
```

Consumers check the hash at parse time:

```python
SUPPORTED_HASHES = {"a1b2c3d4e5f600000000000000000000", ...}

def parse_dsn(path: Path) -> Board:
    raw = path.read_text()
    header_hash = extract_schema_hash(raw)
    if header_hash not in SUPPORTED_HASHES:
        raise UnsupportedSchemaError(
            f"DSN file {path} uses schema hash {header_hash}, "
            f"not in supported set: {sorted(SUPPORTED_HASHES)}"
        )
    return _parse_dsn_body(raw)
```

### Deterministic serialization

```python
def serialize_placement(board: Board, path: Path) -> None:
    lines = []
    lines.append(f"(temper_schema_hash {SCHEMA_HASH})")
    lines.append(f"(temper_schema_version {SCHEMA_VERSION})")
    lines.append(f"(pcb {board.name}")
    lines.append(f"  (resolution um {board.resolution})")
    lines.append(f"  (unit um)")

    # Deterministic ordering: sort components by name
    for comp in sorted(board.components, key=lambda c: c.name):
        lines.append(f"  (component {comp.name}")
        # Fixed-precision float formatting
        lines.append(f"    (place {comp.x:.6f} {comp.y:.6f})")
        lines.append(f"    (layer {comp.layer})")
        lines.append(f"  )")

    lines.append(")")
    path.write_text("\n".join(lines) + "\n")
```

### Normalizer stripping non-semantic noise

```python
def normalize_dsn(raw: str) -> str:
    """Strip timestamps, tool versions, and generator provenance from DSN."""
    lines = raw.splitlines()
    out = []
    for line in lines:
        # Strip timestamp comments
        if re.match(r'^\s*;\s*Generated\s+at\s+', line):
            continue
        # Strip tool version strings
        if re.match(r'^\s*;\s*tool_version\s+', line):
            continue
        # Strip generator provenance
        if re.match(r'^\s*\(generator\s+', line):
            continue
        out.append(line)
    return "\n".join(out) + "\n"
```

### Parity test via git diff

```bash
# Compare two placer runs — are they semantically equivalent?
python -m temper_placer --input board.kicad_pcb --output /tmp/v1.dsn
python -m temper_placer --input board.kicad_pcb --output /tmp/v2.dsn
normalize-dsn /tmp/v1.dsn
normalize-dsn /tmp/v2.dsn
diff /tmp/v1.normalized.dsn /tmp/v2.normalized.dsn
# Empty diff → byte-identical → semantically equivalent
```

### JSON sidecar for non-geometric data

```python
def serialize_placement_with_sidecars(board: Board, output_dir: Path) -> None:
    dsn_path = output_dir / "placement.dsn"
    cost_path = output_dir / "placement.cost.json"
    channels_path = output_dir / "placement.channels.json"

    # Canonical seam file
    serialize_placement(board, dsn_path)

    # Optional sidecars (non-geometric analysis data)
    cost_path.write_text(json.dumps({
        "grid_resolution_um": board.occupancy_grid.resolution,
        "cells": board.occupancy_grid.serialize_sparse(),
    }, indent=2))

    channels_path.write_text(json.dumps({
        "channels": board.channel_capacity_map.serialize(),
    }, indent=2))
```

### FreeRouting round-trip

```bash
# Temper placer produces DSN
python -m temper_placer --input board.kicad_pcb --output placement.dsn

# Feed directly to FreeRouting — no preprocessing needed
freerouting -de placement.dsn -do routing.ses

# Temper validator reads FreeRouting output directly
python -m temper_drc validate --dsn placement.dsn --ses routing.ses
```

## Related

- `packages/temper-placer/src/temper_placer/serialization/dsn_writer.py` — DSN serialization
- `packages/temper-placer/src/temper_placer/serialization/dsn_reader.py` — DSN deserialization
- `packages/temper-placer/src/temper_placer/serialization/ses_reader.py` — SES deserialization
- `packages/temper-placer/src/temper_placer/serialization/normalizer.py` — Semantic normalizer
- `packages/temper-placer/src/temper_placer/serialization/schema_hash.py` — Content-hash schema versioning
- `docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md` — Baseline + monotonic shrink meta-pattern
- SPECCTRA DSN format specification: <https://www.artwork.com/specctra/specctra_dsn.htm>
- FreeRouting: <https://github.com/freerouting/freerouting>

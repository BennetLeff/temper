---
date: 2026-06-22
type: feat
origin: docs/brainstorms/2026-06-22-dsn-universal-seam-requirements.md
status: active
---

# Plan: DSN/SES Universal Seam for Pipeline Stage Boundaries

## Summary

Formalize SPECCTRA DSN as the canonical intermediate format at every pipeline stage boundary. Introduce deterministic byte-identical serialization, content-hash schema versioning embedded in DSN comment headers, and a lightweight boundary registry so any stage can dump or consume DSN. v1 registers the 5 highest-value boundaries: after SEMANTIC, after TOPOLOGICAL, after placement (GEOMETRIC), after routing, and after validation (OUTPUT).

## Problem Frame

Temper has three overlapping pipeline systems (PipelineOrchestrator 8-phase, RouterV6Pipeline 5-stage, DeterministicPipeline 26-stage) that speak different internal data structures. The active strangler-fig decomposition effort needs to test that extracted stages produce results identical to their monolith counterparts, but without a common interchange format these parity tests require ad-hoc wrappers that serialize to temporary KiCad PCB files. 118 ad-hoc scripts each invent their own data-passing convention. A canonical DSN/SES seam makes every pipeline stage boundary speak the same language -- parity tests, stage composition, and external validation all inherit a single contract for free.

## Requirements Trace

| Requirement | Source | Acceptance |
|-------------|--------|------------|
| R1 — Every stage boundary serializes to DSN | Requirements doc | `temper dsn export --boundary <name>` produces valid DSN |
| R2 — Deterministic byte-identical serialization | Requirements doc | Same input → diff-identical output across machines with same floating-point rounding |
| R3 — Non-semantic noise stripped | Requirements doc | DSN contains no timestamps, tool versions, JAX PRNG state, or path fragments |
| R4 — Content-hash schema versioning in DSN header | Requirements doc | Header contains `;schema-version: sha256:<hex>`; hash changes if schema changes |
| R5 — Schema version validated on consumption | Requirements doc | Unknown version → fail early with diagnostic naming expected/received |
| R6 — FreeRouting import compatibility | Requirements doc | `freerouting -de <file>.dsn` produces valid SES without preprocessing |
| R7 — KiCad SES import compatibility | Requirements doc | SES output importable by KiCad's SPECCTRA session importer |
| R8 — Golden DSN committed per boundary | Requirements doc | `power_pcb_dataset/goldens/temper/<boundary>.dsn` tracked in git |
| R9 — Standalone stage vs monolith parity | Requirements doc | Byte-identical DSN output from standalone stage consuming upstream golden |
| SC1 — `git diff` on golden DSN detects regressions | Requirements doc | Zero false positives in CI |
| SC2 — FreeRouting consumes placement DSN | Requirements doc | Successfully autoroutes the Temper board from DSN |
| SC3 — Stage extraction proven without monolith startup | Requirements doc | Standalone stage passes CI gate on golden input |
| SC4 — CI regenerates golden DSN on golden-input path changes | Requirements doc | Golden check fails if monolith output diverges |

## Implementation Units

### U1. Deterministic DSN Serialization

**Goal:** Modify the existing DSN exporter to produce byte-identical output for identical semantic inputs, and add a normalization pass that strips non-semantic noise.

**Requirements:** R2, R3

**Dependencies:** None (self-contained in io layer)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/io/dsn.py` — Add `DSNExpression.with_comment(line: str)` for comment-line insertion; ensure float formatting is pinned to `{:.6f}` consistently
- Modify: `packages/temper-placer/src/temper_placer/io/dsn_exporter.py` — Add `deterministic: bool = True` constructor parameter; when True: sort nets alphabetically by sanitized name (not by fanout/span), sort components by ref, sort padstack definitions by name, sort pin lists by pin number, sort keepouts by name, sort layers by index consistently
- Create: `packages/temper-placer/src/temper_placer/io/dsn_normalizer.py` — `DSNNormalizer` class with:
  - `normalize(dsn_text: str) -> str`: strips comment lines matching non-semantic patterns (`;exported-at:`, `;tool-version:`, `;machine:`, `;path:`), normalizes trailing whitespace, ensures single trailing newline
  - `is_normalized(dsn_text: str) -> bool`: asserts no non-semantic noise remains
- Create: `packages/temper-placer/tests/io/test_dsn_normalizer.py`
- Modify: `packages/temper-placer/tests/io/test_dsn_exporter.py` — Add test cases for deterministic output (two calls with same inputs → identical strings)

**Approach:**
1. In `dsn.py`, add a `comment` field to `DSNExpression.__str__()` that emits `;comment text\n` before the S-expression when set. Format floats with `f"{v:.6f}"` with trailing-zero stripping (already done) but ensure no platform-specific formatting leaks.
2. In `dsn_exporter.py`, add a `deterministic` flag. When True:
   - `export_network`: sort nets by `clean_name.lower()` instead of `(len(pins), span)`. Keep net-class assignments (power/signal) but emit nets in sorted order within each class.
   - `export_library`: sort images by `fp_id`, sort pins within each image by pin number (natural sort), sort padstack keys alphabetically.
   - `export_placement`: sort components by `fp_id` then ref.
   - `export_structure`: sort layers by index; sort keepouts by name.
3. In `dsn_normalizer.py`, the normalizer is a post-processing pass. It uses regex to strip lines matching known non-semantic patterns. It also verifies that the DSN text contains no control characters and ends with exactly one newline.
4. The normalizer is applied automatically when `DSNExporter` is constructed with `deterministic=True`.

**Test scenarios:**
- Two `DSNExporter(board, netlist).export_pcb()` calls with deterministic=True produce identical `str()` output
- Same inputs on different Python processes produce identical output (verified via subprocess test)
- Normalizer strips `;exported-at: 2026-06-22T10:00:00` and `;tool-version: temper-placer 1.2.3` lines
- Normalizer preserves `;schema-version: sha256:...` lines (semantic)
- Float `12.3` formats as `12.3`, float `12.300001` formats as `12.300001`

**Verification:** `git diff` on the same input twice produces empty output. CI golden check has zero false positives.

---

### U2. Content-Hash Schema Versioning

**Goal:** Compute a content hash of the DSN structural skeleton (layers, nets, component footprints -- not coordinates) and embed it as a comment header in every DSN file so downstream consumers detect schema changes.

**Requirements:** R4

**Dependencies:** U1 (needs deterministic serialization to compute stable hashes)

**Files:**
- Create: `packages/temper-placer/src/temper_placer/io/dsn_schema.py` — `DSNSchemaHasher` with:
  - `compute_schema_hash(board, netlist) -> str`: Hashes the schema skeleton (layer names + types, net names sorted, component footprint names + pin counts sorted, design rules) using SHA-256, returns hex string
  - `embed_header(dsn_text: str, schema_hash: str) -> str`: Inserts `;schema-version: sha256:<hash>` as the first line
  - `extract_hash(dsn_text: str) -> str | None`: Parses the header to extract the hash, or None if missing
- Create: `packages/temper-placer/tests/io/test_dsn_schema.py`
- Modify: `packages/temper-placer/src/temper_placer/io/dsn_exporter.py` — In `export_pcb()`, when deterministic=True, compute schema hash and embed it

**Approach:**
1. The schema hash covers: layer count, layer names (sorted), layer types per layer, component footprint names (sorted), pin count per footprint, net names (sorted), and rule values (trace width, clearance). It does NOT cover: component positions, rotations, pin coordinates, net pin assignments, wiring traces.
2. The hash is computed by serializing the schema fields into a canonical key-sorted JSON string then running SHA-256.
3. The header is embedded as a DSN comment line: `;schema-version: sha256:<64-char-hex>` before the `(pcb ...)` expression.
4. `DSNExporter.export_pcb()` calls `DSNSchemaHasher` when `deterministic=True` and prepends the header to the output string.

**Test scenarios:**
- Same board + netlist → same hash across invocations
- Adding a net → hash changes
- Changing a footprint (different pin count) → hash changes
- Moving a component (position only) → hash unchanged
- Changing trace width rule → hash changes
- `extract_hash()` parses `;schema-version: sha256:abc123...` correctly
- `extract_hash()` returns None for DSN without schema-version header

**Verification:** `git diff` on a DSN file shows a changed schema-version only when the schema actually changed, not when only positions changed.

---

### U3. DSN Schema Version Validator

**Goal:** Provide a validator that stages call on DSN input to fail early when the schema version is unknown or incompatible.

**Requirements:** R5

**Dependencies:** U2 (uses schema hash extraction)

**Files:**
- Create: `packages/temper-placer/src/temper_placer/io/dsn_validator.py` — `DSNVersionValidator` with:
  - `validate(dsn_text: str, expected_hash: str) -> None`: Extracts the embedded hash, compares to expected; raises `DSNVersionMismatchError(expected, received)` on mismatch
  - `validate_or_warn(dsn_text: str, expected_hash: str) -> bool`: Like validate but returns False instead of raising; logs warning
  - `DSNVersionMismatchError` exception with `expected: str`, `received: str | None` fields
- Create: `packages/temper-placer/tests/io/test_dsn_validator.py`

**Approach:**
1. `DSNVersionValidator` is a stateless utility (all methods are static/class methods).
2. `validate()` calls `DSNSchemaHasher.extract_hash()` from U2, compares to `expected_hash`. If missing or mismatched, raises `DSNVersionMismatchError` with a message like: `DSN schema version mismatch: expected sha256:abc123, got sha256:def456. The upstream stage may have changed its output format.`
3. The validator is designed to be called at stage initialization -- before any processing -- to fail fast.

**Test scenarios:**
- `validate()` passes when hash matches
- `validate()` raises `DSNVersionMismatchError` when hash differs
- `validate()` raises `DSNVersionMismatchError` when header is missing (received=None)
- Error message contains both expected and received hashes
- `validate_or_warn()` returns True on match, False on mismatch (no exception)

**Verification:** A stage consuming DSN with unknown version fails immediately with a clear diagnostic, rather than producing corrupted downstream output (AE4).

---

### U4. Stage Boundary Registry and DSN Integration

**Goal:** Register the 5 v1 stage boundaries with the pipeline systems so DSN can be exported at any registered boundary. Provide a uniform API for extracting DSN output at a boundary.

**Requirements:** R1, v1 5-boundary scope

**Dependencies:** U1, U2 (deterministic serialization + schema hashing)

**Files:**
- Create: `packages/temper-placer/src/temper_placer/io/boundary_registry.py` — `BoundaryRegistry`:
  - `BOUNDARIES` dict mapping boundary name → `BoundaryDef(pipeline_class, phase_name, output_format, serialization_fn)`
  - 5 v1 entries: `semantic`, `topological`, `placement`, `routing`, `validation`
  - `get_boundary(name) -> BoundaryDef`
  - `list_boundaries() -> list[str]`
- Create: `packages/temper-placer/src/temper_placer/io/dsn_boundary.py` — `DSNBoundaryExporter`:
  - `export_at_boundary(boundary_name: str, input_pcb: Path, config: Path | None = None) -> str`: Runs the monolith pipeline to the named boundary on the given PCB, serializes and returns DSN text
  - `export_all_boundaries(input_pcb: Path, config: Path | None = None) -> dict[str, str]`: Runs the pipeline once, snapshots DSN at each registered boundary
- Modify: `packages/temper-placer/src/temper_placer/pipeline/orchestrator.py` — Add optional `dsn_callbacks: dict[str, Callable]` parameter to `PipelineOrchestrator` that fires after each phase completes; used by `DSNBoundaryExporter` to capture state at boundaries
- Create: `packages/temper-placer/tests/io/test_dsn_boundary.py`

**Approach:**
1. `BoundaryDef` is a dataclass: `(pipeline_class: type, phase_name: str, output_format: Literal["dsn", "ses", "json"], serialization_fn: str)`.
2. The 5 v1 boundaries map to `PipelineOrchestrator` phases:
   - `semantic` → `PipelinePhase.SEMANTIC`, DSN with netlist + structure
   - `topological` → `PipelinePhase.TOPOLOGICAL`, DSN with topology-annotated netlist
   - `placement` → after `PipelinePhase.GEOMETRIC`, DSN with placement + structure + library
   - `routing` → after `PipelinePhase.ROUTING`, DSN/SES with wiring
   - `validation` → after `PipelinePhase.OUTPUT`, DSN with final state
3. `DSNBoundaryExporter` instantiates a `PipelineOrchestrator` with DSN callbacks registered at each of the 5 boundaries. The callbacks receive the pipeline state at that phase, construct a `DSNExporter` from the current board/netlist/positions state, and serialize.
4. The orchestrator gains a `_dsn_callbacks` dict. After each `PipelinePhase` completes, it calls the corresponding callback with the current `PipelineState`. The callback is a `Callable[[PipelineState], None]`.
5. For boundaries that produce data not mappable to DSN (e.g., topology analysis artifacts), the `output_format` field in `BoundaryDef` captures that. v1 boundaries all have DSN-mappable geometry.

**Test scenarios:**
- `list_boundaries()` returns `["semantic", "topological", "placement", "routing", "validation"]`
- `export_at_boundary("placement", temper.kicad_pcb)` returns valid DSN with structure, library, placement, network sections
- Same input → same DSN output (deterministic via U1)
- `export_all_boundaries()` returns a dict with 5 keys, each value is valid DSN
- Boundary registry rejects unknown boundary name with clear error
- Callbacks fire only for registered boundaries, not for intermediate phases

**Verification:** `temper dsn export --boundary placement --input temper.kicad_pcb --config constraints.yaml` (from U5) produces valid DSN with all required sections. The output is byte-identical when run twice.

---

### U5. CLI `temper dsn` Command Group

**Goal:** Provide CLI commands for DSN export, golden comparison, and boundary listing so developers and CI can operate at the DSN seam.

**Requirements:** R1, R2, R6, R7, R8, R9

**Dependencies:** U1-U4

**Files:**
- Create: `packages/temper-placer/src/temper_placer/cli/dsn_commands.py` — Click command group `dsn` with subcommands:
  - `dsn export`: Export DSN at a stage boundary
  - `dsn check`: Compare current DSN output against committed golden
  - `dsn boundaries`: List registered stage boundaries
  - `dsn validate`: Validate a DSN file's schema version against an expected hash
- Modify: `packages/temper-placer/src/temper_placer/cli/__init__.py` — Register `dsn` command group; add `from .dsn_commands import dsn; main.add_command(dsn)`

**Approach:**
1. **`dsn export`**: `--boundary <name> --input <pcb> --config <yaml> --output <file> [--no-deterministic]`
   - Calls `DSNBoundaryExporter.export_at_boundary()`, writes to file or stdout.
2. **`dsn check`**: `--boundary <name> --input <pcb> --config <yaml> [--golden-dir <dir>]`
   - Reads golden DSN from `power_pcb_dataset/goldens/temper/<boundary>.dsn`
   - Exports current DSN, normalizes both with `DSNNormalizer`, diffs
   - Reports PASS (byte-identical), WITHIN_TOLERANCE (geometry-only differences within 1e-3mm), or FAIL
   - Exit code 0 on pass/within-tolerance, non-zero on fail
3. **`dsn boundaries`**: Lists registered boundaries with pipeline, phase, and format from `BoundaryRegistry`
4. **`dsn validate`**: `--dsn <file> --expected-hash <sha256:...>` — Calls `DSNVersionValidator.validate()`

**CLI Design (click):**
```python
@click.group()
def dsn():
    """DSN/SES universal seam operations."""

@dsn.command()
@click.option("--boundary", "-b", required=True, help="Stage boundary name")
@click.option("--input", "-i", required=True, type=click.Path(exists=True), help="Input KiCad PCB")
@click.option("--config", "-c", type=click.Path(exists=True), help="Constraints YAML")
@click.option("--output", "-o", type=click.Path(), help="Output DSN file (default: stdout)")
@click.option("--no-deterministic", is_flag=True, help="Disable deterministic mode")
def export(boundary, input, config, output, no_deterministic): ...

@dsn.command()
@click.option("--boundary", "-b", required=True)
@click.option("--input", "-i", required=True, type=click.Path(exists=True))
@click.option("--config", "-c", type=click.Path(exists=True))
@click.option("--golden-dir", type=click.Path(), default="power_pcb_dataset/goldens/temper")
def check(boundary, input, config, golden_dir): ...

@dsn.command()
def boundaries(): ...

@dsn.command()
@click.option("--dsn", "dsn_file", required=True, type=click.Path(exists=True))
@click.option("--expected-hash", required=True)
def validate(dsn_file, expected_hash): ...
```

**Test scenarios:**
- `temper dsn export --boundary placement` writes valid DSN to stdout
- `temper dsn check --boundary placement` passes when golden matches
- `temper dsn check --boundary placement` fails when output diverged
- `temper dsn boundaries` lists 5 boundaries with pipeline/phase info
- `temper dsn validate --dsn golden.dsn --expected-hash sha256:abc` exits 0 on match, 1 on mismatch

**Verification:** Manual acceptance run: `temper dsn export --boundary placement --input pcb/temper.kicad_pcb -o /tmp/test.dsn && freerouting -de /tmp/test.dsn` succeeds (AE2). `temper dsn check --boundary placement` passes when nothing changed.

---

### U6. Golden Fixture Infrastructure

**Goal:** Establish the golden fixture directory, initial golden DSN files, and CI check workflow so every PR gates on DSN boundary parity.

**Requirements:** R8, R9, SC1, SC4

**Dependencies:** U5 (uses `temper dsn check` and `temper dsn export`)

**Files:**
- Create: `power_pcb_dataset/goldens/temper/semantic.dsn` — Golden DSN after SEMANTIC phase
- Create: `power_pcb_dataset/goldens/temper/topological.dsn` — Golden DSN after TOPOLOGICAL phase
- Create: `power_pcb_dataset/goldens/temper/placement.dsn` — Golden DSN after GEOMETRIC/placement
- Create: `power_pcb_dataset/goldens/temper/routing.dsn` — Golden DSN after ROUTING phase
- Create: `power_pcb_dataset/goldens/temper/validation.dsn` — Golden DSN after OUTPUT/validation
- Create: `power_pcb_dataset/goldens/temper/manifest.yaml` — Records board, stage, pipeline, git commit hash, format version
- Create: `.github/workflows/golden-check.yml` — CI workflow that runs `temper dsn check` on all 5 boundaries
- Modify: `packages/temper-placer/src/temper_placer/cli/dsn_commands.py` — Add `dsn generate` subcommand (golden regeneration)
- Create: `packages/temper-placer/tests/io/test_dsn_integration.py` — End-to-end golden flow test

**Approach:**
1. **Initial golden generation**: Run `temper dsn export --boundary <name> --input pcb/temper.kicad_pcb --config pcb/temper_config.yaml -o power_pcb_dataset/goldens/temper/<name>.dsn` for each of the 5 boundaries. This produces the committed golden files.
2. **Manifest**: `manifest.yaml` is hand-written initially and validated by the golden check. Format:
   ```yaml
   format_version: 1
   board: temper
   fixtures:
     - stage: semantic
       pipeline: PipelineOrchestrator
       format: dsn
       generated_at_commit: <sha>
     - stage: topological
       ...
   ```
3. **`dsn generate`**: Wraps `dsn export` with manifest update. `temper dsn generate --boundary <name> [--all]` exports DSN to the golden directory and updates the manifest's `generated_at_commit`.
4. **CI workflow**: `.github/workflows/golden-check.yml`:
   - Checkout repo with submodules
   - Setup Python with temper-placer installed
   - Run `temper dsn check --boundary semantic --input pcb/temper.kicad_pcb`
   - Repeat for topological, placement, routing, validation
   - Fail if any check fails
   - The job is **required** in branch protection
5. **Existing `temper_testing.golden` module**: The golden fixture system in this plan is independent of `temper_testing.golden` (which operates on JSON snapshots). They coexist: `temper_testing.golden` for unit-level JSON snapshots, `temper dsn check` for pipeline-level DSN parity.

**Test scenarios:**
- `temper dsn generate --boundary placement` creates/updates `power_pcb_dataset/goldens/temper/placement.dsn`
- `temper dsn check --boundary placement` passes when monolith is unchanged
- `temper dsn check --boundary placement` fails when placement algorithm is modified (detected as DSN coordinate changes)
- CI workflow passes on PRs that don't change pipeline behavior
- CI workflow fails when PR changes placement output unintentionally
- Manifest `generated_at_commit` is updated on golden regeneration
- Schema version hash in DSN header matches the current monolith's schema hash (per U2)

**Verification:** CI golden check runs on every PR. Manual test: modify a placement heuristic, run `temper dsn check --boundary placement`, confirm it fails. Then run `temper dsn generate --boundary placement` to regenerate, confirm check passes.

---

### U7. FreeRouting and KiCad Interoperability Verification

**Goal:** Confirm the existing DSN exporter and the new deterministic-mode output satisfy FreeRouting and KiCad import requirements. This is a verification-only unit (no new code beyond what U1-U6 provide).

**Requirements:** R6, R7, SC2

**Dependencies:** U1, U5 (deterministic DSN output and CLI)

**Files:**
- Create: `packages/temper-placer/tests/io/test_dsn_freerouting.py` — Integration test that:
  - Exports DSN from the Temper board via `temper dsn export --boundary placement`
  - Invokes `freerouting -de <dsn> -do <ses>` (if FreeRouting is installed)
  - Asserts SES is produced and contains at least one routed wire
  - Asserts SES can be parsed (contains `(session ...)` structure)
- Create: `packages/temper-placer/tests/io/test_dsn_kicad.py` — Integration test that:
  - Takes a known-good SES file
  - Invokes `kicad-cli pcb import` or validates the SES file is structurally valid

**Approach:**
1. Tests are skipped (not failed) if `freerouting` or `kicad-cli` are not installed. They are marked with `@pytest.mark.skipif(not shutil.which("freerouting"), reason="FreeRouting not installed")`.
2. The DSN export uses the deterministic mode from U1 to ensure reproducibility.
3. These tests primarily validate that U1's deterministic changes (sorting, normalization) didn't break FreeRouting compatibility -- the exporter already works for FreeRouting (verified by existing `.dsn` files in `pcb/`).

**Test scenarios:**
- `freerouting -de temper_placement.dsn` exits 0 and produces `.ses` file
- Produced SES contains `(session` and at least one `(wire` or `(net` element
- Deterministic DSN (alphabetically sorted nets) is accepted by FreeRouting same as fanout-sorted DSN

**Verification:** CI test suite includes these integration tests. AE2 is formally verified.

---

## Key Technical Decisions

1. **Normalization lives in a post-processing pass (`DSNNormalizer`), not in the serializer.** The serializer already produces deterministic output when `deterministic=True`. The normalizer strips remaining non-semantic noise (timestamps, tool versions) that could leak from higher-level orchestrator code. This separation keeps the serializer focused on format correctness and the normalizer focused on diff-purity. The normalizer is always applied in deterministic mode.

2. **Deterministic mode sorts alphabetically, not by fanout/span.** The current exporter sorts nets by fanout (low first) then HPWL span (short first) for routing quality. Deterministic mode overrides this with pure alphabetical sorting by sanitized net name. This is necessary for byte-identical output because fanout and span depend on floating-point positions which can vary across machines. The non-deterministic mode (for FreeRouting consumption) keeps the fanout/span sort.

3. **Schema hash embedded as DSN comment header (`;schema-version: sha256:<hex>`).** This is the most self-contained mechanism -- the version travels with the file, requires no filename conventions or sidecar files, and is naturally ignored by tools that don't understand it. The hash covers the structural skeleton (layers, nets, footprints), not coordinates, so position-only changes don't invalidate downstream consumers.

4. **Version validation is a standalone utility callable by any stage.** It is not a decorator or base-class method because the three pipeline systems have different programming models (PipelineOrchestrator is phase-based, DeterministicPipeline is `Stage.run(state)`, RouterV6 is function-chained). A stateless `DSNVersionValidator.validate()` function works uniformly across all three.

5. **v1 boundaries are PipelineOrchestrator-only.** The 5 highest-value boundaries (semantic, topological, placement, routing, validation) all map to PipelineOrchestrator phases. RouterV6 and DeterministicPipeline boundaries are deferred to v2 (after the golden fixture ladder matures). The boundary registry is designed to accept additional pipelines without schema changes.

6. **Golden files live under `power_pcb_dataset/goldens/<board_id>/`.** This co-locates golden fixtures with the dataset they validate, rather than scattering them across the repo. The board ID is `temper` for the induction cooker PCB.

## Risks & Dependencies

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Deterministic sort breaks FreeRouting compatibility | Low | Medium | U7 integration test validates FreeRouting acceptance of deterministic DSN; if FreeRouting misbehaves with alphabetically-sorted nets, we keep fanout-sort for the FreeRouting path and only use alphabetical-sort for golden files |
| Floating-point reproducibility across platforms | Medium | High | Python's `float` has cross-platform format consistency with 6 decimal places (U1). JAX floating-point variance between CPU/GPU is a known issue; golden files are generated on CPU (CI standard). Cross-machine float variance up to 1e-6mm is handled at diff time (geometric tolerance in U5 check command per golden-fixture-ladder R8) |
| PipelineOrchestrator callbacks change phase timing | Low | Low | Callbacks are `Callable[[PipelineState], None]` -- they don't modify state. They fire after the phase's main logic completes. Performance impact is one DSN serialization per boundary (O(n) in component count, already fast) |
| Breaking change to DSNExporter constructor | Low | Low | `deterministic` defaults to `True` for the new behavior. Existing callers that pass no flag get deterministic output. Callers that need the old fanout-sort behavior pass `deterministic=False`. The `scripts/export_dsn.py` script is updated to pass `deterministic=False` explicitly to preserve routing-quality net ordering |
| Schema hash false positives (hash changes on non-schema changes) | Medium | Medium | The hash input is strictly filtered to schema fields only (layers, nets, footprints, rules). Extensive unit tests in U2 verify hash stability when only positions change. If false positives occur in practice, the hash algorithm is isolated in `DSNSchemaHasher` for easy adjustment |

### Dependencies

- **U1 → U2**: U2 needs deterministic serialization to compute stable schema hashes
- **U1, U2 → U4**: DSN boundary integration needs both deterministic output and schema hashing
- **U1-U4 → U5**: CLI commands use all underlying modules
- **U5 → U6**: Golden infrastructure uses CLI commands
- **U1, U5 → U7**: Interop tests use deterministic DSN output
- **Existing**: `temper_placer.io.dsn_exporter.DSNExporter` — the plan extends this class, does not replace it
- **Existing**: `temper_placer.io.dsn` — `DSNExpression` gains a `comment` attribute
- **External**: FreeRouting CLI for U7 tests (optional, tests skip if not installed)
- **External**: KiCad CLI for U7 tests (optional, tests skip if not installed)

## System-Wide Impact

### New Packages / Modules

| Module | Purpose |
|--------|---------|
| `temper_placer.io.dsn_normalizer` | Post-processing pass to strip non-semantic noise |
| `temper_placer.io.dsn_schema` | Content-hash computation and header embedding |
| `temper_placer.io.dsn_validator` | Schema version validation for DSN consumers |
| `temper_placer.io.boundary_registry` | Stage boundary manifest and lookup |
| `temper_placer.io.dsn_boundary` | DSN export at pipeline stage boundaries |
| `temper_placer.cli.dsn_commands` | `temper dsn` CLI command group |

### Modified Modules

| Module | Change |
|--------|--------|
| `temper_placer.io.dsn` | Add `DSNExpression.comment` field for header comments; pin float formatting |
| `temper_placer.io.dsn_exporter` | Add `deterministic` flag; alphabetically-sorted output mode; integrate schema hashing |
| `temper_placer.pipeline.orchestrator` | Add optional `dsn_callbacks` dict; fire callbacks after each phase |
| `temper_placer.cli.__init__` | Register `dsn` command group |
| `temper_placer.io.__init__` | Export new modules' public API |
| `scripts/export_dsn.py` | Set `deterministic=False` explicitly to preserve routing-quality net ordering |

### Data Directories

| Directory | Purpose |
|-----------|---------|
| `power_pcb_dataset/goldens/temper/` | Golden DSN fixtures for the Temper board (5 files + manifest) |
| `.github/workflows/` | New `golden-check.yml` CI workflow |

### Test Files

| File | Tests |
|------|-------|
| `tests/io/test_dsn_normalizer.py` | U1: Normalization correctness, noise stripping |
| `tests/io/test_dsn_exporter.py` (modified) | U1: Deterministic output assertions |
| `tests/io/test_dsn_schema.py` | U2: Schema hash computation, header embedding |
| `tests/io/test_dsn_validator.py` | U3: Version validation, error messages |
| `tests/io/test_dsn_boundary.py` | U4: Boundary registry, boundary export |
| `tests/io/test_dsn_freerouting.py` | U7: FreeRouting import acceptance |
| `tests/io/test_dsn_kicad.py` | U7: KiCad SES import acceptance |
| `tests/io/test_dsn_integration.py` | U6: End-to-end golden generate/check flow |

### Backward Compatibility

- `DSNExporter` constructor gains an optional `deterministic: bool = True` parameter. Existing callers get deterministic output by default.
- `DSNExpression.__str__()` emits an optional comment line before the S-expression. Existing serialization is unchanged unless `comment` is set.
- `PipelineOrchestrator` gains an optional `dsn_callbacks` parameter that defaults to `{}` -- no callbacks fire by default.
- The `scripts/export_dsn.py` script explicitly passes `deterministic=False` to preserve the current fanout-sorted behavior for FreeRouting consumption.

### Performance

- Deterministic sorting is O(n log n) on net/component count, same as current fanout-sort. No performance regression.
- DSN boundary callbacks run one serialization per registered boundary per pipeline run. Each serialization is O(components + nets + pins). For the Temper board (~60 components, ~80 nets), this is negligible (<50ms per boundary on a modern CPU).
- Schema hashing is O(n) on the schema skeleton size and runs once per DSN export. Negligible.

---

## Implementation Order

1. **U1** — Deterministic Serialization (foundation for everything)
2. **U2** — Schema Versioning (depends on U1)
3. **U3** — Version Validator (depends on U2)
4. **U4** — Boundary Registry + Integration (depends on U1, U2)
5. **U5** — CLI Commands (depends on U1-U4)
6. **U6** — Golden Fixtures + CI (depends on U5)
7. **U7** — Interop Verification (depends on U1, U5)

U1-U3 can be implemented and tested entirely within the `io` package without touching the pipeline systems. U4 is the first unit that touches `PipelineOrchestrator`. U5-U6 are integration units that wire everything together. U7 is a verification gate run last.

# Instructions for AI Agents

## Project Context

**This is the Temper induction cooker project:**
- **Firmware**: ESP32-S3 with 8-state machine
- **PCB**: KiCad design with temper-placer optimizer
- **Language**: C (firmware), Python/JAX (placer)

**Key areas:**
- `firmware/` - ESP32-S3 control code
- `packages/temper-placer/` - JAX-based PCB placement optimizer
- `pcb/` - KiCad schematics
- `docs/solutions/` - documented fixes for past problems (bugs, patterns, tooling decisions), organized by category with YAML frontmatter — search before implementing or debugging in a known area
- `docs/solutions/` - documented solutions to past bugs, best practices, and architecture patterns (YAML frontmatter, organized by category)

## Firmware Config Codegen

`firmware/config.h` is generated from `firmware/config.yaml` by
`firmware/tools/gen_config.py`. After editing the manifest:

```bash
python3 firmware/tools/gen_config.py
git add firmware/config.h && git commit -m "chore: regenerate config.h"
```

CI regenerates and `git diff --exit-code`s against the committed copy.

## Transition Table Regeneration

`firmware/main/transition_table.h` is generated from `firmware/transition_table.yaml`
by `firmware/tools/gen_transition_table.py`. After editing the manifest:

    python3 firmware/tools/gen_transition_table.py
    git add firmware/main/transition_table.h && git commit -m "chore: regenerate transition table"

CI regenerates and `git diff --exit-code`s against the committed copy.

`firmware/test/test_transition_table_generated.c` is also regenerated from the
same manifest via `firmware/test/gen_transition_table.py`. After manifest edits:

    python3 firmware/test/gen_transition_table.py --generate
    git add firmware/test/test_transition_table_generated.c
    git commit -m "test: regenerate transition table tests"

## Import Boundary Check

Before pushing, verify your changes don't violate import boundaries:

```bash
uv run python scripts/import_linter_gate.py
```

If violations are reported:
1. Check `.importlinter` for the boundary contract violated
2. Option A: Move the import to a permitted module (use public `__init__.py` exports)
3. Option B: Add an allowlist entry to `import-linter-allowlist.yaml` with justification + ticket reference

The same check runs in CI. After the soft-launch period (until 2026-07-06), violations block PR merge.
See `docs/plans/2026-06-22-014-feat-import-linter-boundary-enforcement-plan.md`.

## Script Manifest Convention

Every `scripts/*.py` file must have an entry in `scripts/manifest.yaml`. The
CI `check_manifest_gate` rejects new scripts without a manifest entry.

**Adding a new script:**

1. Add an entry to `scripts/manifest.yaml`:
   ```yaml
   - path: your_script.py
     purpose: "What the script does"
     owner: your-name
     last_run: "2026-06-22"
     category: keep          # or ticket / delete
     disposition: utility    # or ci-gate / shell-invoked / temper-scripts-sunset
     imports: []             # populated by `scripts/trace_invocations.py`
   ```
2. Run `uv run python scripts/trace_invocations.py` to refresh the invocation graph
3. CI will fail on missing entries (`check_manifest_gate`); sunset warnings
   fire on stale `last_run` dates after 30/60 days (`check_script_sunset`)

**Sunset clock (per plan 2026-06-22-021):**
- 30 days no invocation → WARNING (keep/ticket)
- 60 days no invocation → ESCALATE (ticket auto-promotes to delete priority)
- Sunset never auto-deletes; deletion is always a `git rm` by a human

See `docs/plans/2026-06-22-021-feat-script-triage-sunset-plan.md`.

## Building and Running Firmware Tests

```bash
cmake -B firmware/test/build firmware/test
cmake --build firmware/test/build
./firmware/test/build/test_state_machine_only
```

## Documentation & Context Maintenance

**Critical Rules for AI Agents:**

1.  **Context Awareness**: Before editing or using a script, check for a corresponding `*_INSTRUCTIONS.md` or `*_DESIGN.md` file in the same directory or project root (e.g., `AUTOMATED_PCB_DESIGN_INSTRUCTIONS.md`). Read it to understand the "Why" and "How" of the tool.
2.  **Documentation Sync**: If you modify the logic of a script (e.g., `add_power_planes_v2.py`), you **MUST** update the corresponding instructions file to reflect the change. Code and documentation must never drift apart.
3.  **Decision Logging**: Major architectural decisions must be recorded in `docs/` or the relevant `*_INSTRUCTIONS.md` file. Do not rely on git history alone.

### Traceability Convention

Inline `# @req(<plan-id>, <req-id>): <note>` comments link code to plan
requirements. Two CI gates enforce consistency: every claimed @req tag must
correspond to a live requirement in a plan document, and every plan's
non-deferred requirement must have at least one code annotation — but only
in directories that have opted in via a `TRACEABILITY` sentinel file.

See `docs/TRACEABILITY.md` for the full specification.

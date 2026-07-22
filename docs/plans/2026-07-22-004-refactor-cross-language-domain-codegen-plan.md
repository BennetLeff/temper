---
title: "feat: Cross-Language Domain Codegen — NetClassRules SSOT Manifest"
type: feat
status: active
date: 2026-07-22
origin: docs/brainstorms/2026-06-21-net-class-rules-fields-requirements.md
---

# feat: Cross-Language Domain Codegen — NetClassRules SSOT Manifest

## Summary

Complete the cross-language SSOT codegen pipeline for `NetClassRules`: a YAML
manifest declaring every field once, Jinja2 templates generating both a Python
Pydantic model and a Rust struct block, a codegen script with CI enforcement
(`git diff --exit-code`), and updates to the bridge + DRC call sites to read
`safety_category` from the model instead of keyword substrings.

The pipeline builds on the firmware `config.h` codegen precedent
(`firmware/tools/gen_config.py`) and completes the remaining work from the
N4 plan (`docs/plans/2026-06-22-004-feat-net-class-rules-fields-plan.md`).

## Problem Frame

Today `board.rs:174-198` carries a hand-maintained `NetClassRules` Rust struct
whose fields duplicate the YAML manifest at
`packages/temper-placer/configs/netclass_rules_manifest.yaml`. The codegen
script (`scripts/gen_domain_models.py`) already generates the Python side but
fails on the Rust side because `board.rs` lacks the `// BEGIN GENERATED
NetClassRules` / `// END GENERATED NetClassRules` delimiters. The bridge
(`board_py_bridge.rs:294-305`) hand-extracts each field with Python dict key
strings that must match the manifest; a rename in the manifest that is
reflected in the generated struct but not in the bridge creates a silent field
swap. The safety checks (`hv_lv_separation.rs`, `isolation.rs`) use keyword
substring matching instead of reading `safety_category` from the resolved
`NetClassRules`, duplicating the classification logic that the manifest
already declares.

## Scope Boundaries

### In scope

- U1: Validate the YAML manifest (`netclass_rules_manifest.yaml`) is the SSOT
- U2: Validate Jinja2 Python template produces the committed `netclass_rules_gen.py`
- U3: Validate Jinja2 Rust template matches the generated struct block
- U4: Validate the codegen script (`gen_domain_models.py`) is correct
- U5: Validate CI enforcement step in `python-tests.yml`
- U6: Regenerate all artifacts and confirm idempotency
- U7: Verify `design_rules.py` already imports from `netclass_rules_gen`
- U8: Add `BEGIN/END GENERATED` markers to `board.rs`, replace the hand-maintained `NetClassRules` struct with generated block
- U9: Update `board_py_bridge.rs` to use `safety_category` from model; update safety checks to prefer `NetClassRules.safety_category` over keyword fallback
- U10: Run full test suite, verify CI readiness

### Out of scope

- Adding new fields to the manifest
- Changing field names in existing consumers
- The `temper-drc` Python package (superseded by `temper-drc-rs`)

## Implementation Units

### U1. Validate the YAML manifest
Manifest at `packages/temper-placer/configs/netclass_rules_manifest.yaml` is the SSOT. All 18 fields + 1 doc_only field are declared with language-neutral types.

### U2. Validate Python Jinja2 template
Template at `scripts/templates/netclass_rules.py.j2` generates `netclass_rules_gen.py`. Verify the generated file matches the committed copy byte-for-byte.

### U3. Validate Rust Jinja2 template
Template at `scripts/templates/netclass_rules.rs.j2` generates the Rust `NetClassRules` struct + `Default` impl block delimited by `BEGIN/END GENERATED` markers.

### U4. Validate codegen script
Script at `scripts/gen_domain_models.py` renders both templates, writes Python output atomically, and replaces the delimited block in `board.rs`.

### U5. Validate CI enforcement
CI step `gen_domain_models.py --check` in `.github/workflows/python-tests.yml` fails on drift. Path filters include all relevant files.

### U6. Regenerate artifacts and confirm idempotency
Run `python3 scripts/gen_domain_models.py` — Python side already in sync. Rust side blocked until U8 adds markers.

### U7. Verify import-path switch in design_rules.py
`design_rules.py:19` imports `NetClassRules` from `netclass_rules_gen`. No change needed.

### U8. Add markers to board.rs and replace NetClassRules struct
Add `// BEGIN GENERATED NetClassRules` / `// END GENERATED NetClassRules` markers, replace the hand-maintained struct with the generated block. Run codegen to populate.

### U9. Update bridge and DRC call sites
- `board_py_bridge.rs`: verify `extract_net_class_rules` field keys match manifest `rust_name` values
- `hv_lv_separation.rs`: prefer `NetClassRules.safety_category` over keyword fallback
- `isolation.rs`: prefer `NetClassRules.safety_category` over keyword fallback

### U10. Run tests and verify CI readiness
Run `python3 scripts/gen_domain_models.py --check`, pytest, cargo test. Commit each unit.

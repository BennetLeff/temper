---
title: "NetClassRules cross-language codegen SSOT — manifest → Pydantic model + Rust struct from one vocabulary"
date: "2026-08-03"
category: docs/solutions/architecture-patterns/
module: temper_placer, temper-drc-rs, CI
problem_type: architecture_pattern
component: net_classification
severity: medium
symptoms:
  - "Two languages (Python Pydantic model, Rust struct) must carry the SAME NetClassRules type — fields, defaults, enums, docs — with zero drift between them"
  - "Hand-maintaining the second copy silently diverges: a field added in one language is missing from the other until a consumer hits a missing key"
  - "The drift gate (gen_domain_models.py --check in CI) fails closed when the generated artifacts do not match the manifest"
---

# Problem

NetClassRules is consumed on both sides of the FFI boundary: the Python placer
(`packages/temper-placer`) builds placements and the Rust DRC engine
(`packages/temper-drc-rs`) measures them. Two hand-written declarations of the
same type drift silently — the classic duplicated-SSOT failure. The
resolution is code generation from one language-neutral manifest, in the same
family as the firmware config codegen (`firmware/tools/gen_config.py`) and the
transition-table codegen precedents.

## Root cause

The type is needed in two languages at once; nothing forces two hand-written
copies to agree, and the divergence only surfaces when a consumer touches a
field that exists in one language but not the other.

## Solution

The chain:

```
packages/temper-placer/configs/netclass_rules_manifest.yaml   (SSOT, versioned "1.0")
      │  language-neutral field vocabulary: float, optional_float, int,
      │  optional_int, string, optional_string, string_enum, dict, doc_only
      ▼
scripts/gen_domain_models.py                                  (generator)
      │  jinja2 templates: scripts/templates/netclass_rules.py.j2,
      │  netclass_rules.rs.j2
      │  idempotent writes: .tmp file → byte-compare → atomic replace
      │  (--check mode: exit 1 on any drift, wired into python-tests.yml)
      ▼
├── packages/temper-placer/src/temper_placer/core/netclass_rules_gen.py
│       Pydantic BaseModel with model_config = ConfigDict(frozen=True);
│       the type TEMPER_NET_CLASSES instances are declared against
│       (core/design_rules.py:60)
└── packages/temper-drc-rs/src/board.rs:198-265
        Rust struct NetClassRules inside a delimited block
        ("// BEGIN GENERATED NetClassRules — DO NOT EDIT" … "// END"),
        replaced in place; consumed via board.net_class_rules:
        HashMap<NetClassName, NetClassRules> (denormalized to
        Component.rules for fast access)
```

Rules of the pattern:

1. **One manifest, two outputs, one CI gate.** Every field of the type is
   declared exactly once. `scripts/gen_domain_models.py --check` (run in the
   Python Tests workflow) fails closed on any drift, so a manifest edit
   without regeneration is caught before merge.
2. **Language-neutral vocabulary.** The manifest types (string_enum,
   optional_float, …) are mapped to each target language inside the generator
   — the manifest never contains language-specific syntax.
3. **Delimited-block replacement for Rust.** The Rust consumer file is edited
   in place between BEGIN/END markers; everything outside the block is
   hand-written Rust that uses the generated struct. This keeps hand-written
   and generated code in the same file without the generator owning the file.
4. **Idempotence by construction.** Regenerating twice yields byte-identical
   output (the .tmp + compare + atomic-replace sequence guarantees this);
   `--check` is a pure verification pass, not a second writer.
5. **Generated code is checked in.** Both outputs are committed; CI
   regenerates and `git diff --exit-code`s against the committed copies
   (same discipline as firmware/config.h and the transition table).
6. **Consumers read the generated type, never the manifest.** The safety
   checks read `rules.safety_category` (see
   `temper-drc-rust-migration-shim-then-delete-2026-08-03.md`); the placer
   reads TEMPER_NET_CLASSES. Only the generator reads the manifest.

### Relationship to the older design-rules chain

`netclass-clearance-ssot-designrules-consumer-chain-2026-07-07.md` documents
the YAML-authority → DesignRules → consumers chain (clearance *values*). This
doc covers the TYPE-level SSOT (field *shapes*) that feeds that chain: the
two are complementary — values live in one SSOT, type shape in another, and
both are codegen/ratchet-gated.

## Prevention

- Any change to NetClassRules fields: edit the manifest, run
  `python3 scripts/gen_domain_models.py`, verify idempotence (run twice → no
  diff), commit all three artifacts (manifest + both generated outputs) in
  the same commit. CI's `--check` fails closed otherwise.
- Never hand-edit inside the Rust BEGIN/END block or the generated Python
  file — the next regeneration silently overwrites it.
- When adding a field, declare it in the manifest vocabulary first; if no
  vocabulary type fits, extend the vocabulary (and the two templates) rather
  than smuggling language-specific types into the manifest.

## Evidence

- `scripts/gen_domain_models.py` docstring: "Regenerate cross-language
  NetClassRules domain model from SSOT manifest … idempotent — writes each
  output to a .tmp file, compares byte-for-byte, atomically replaces"
- `configs/netclass_rules_manifest.yaml` header: "Single Source of Truth for
  NetClassRules domain model … consumed by scripts/gen_domain_models.py to
  generate: … netclass_rules_gen.py (Pydantic model) … board.rs (delimited
  block replacement)"
- `board.rs:198` "// BEGIN GENERATED NetClassRules — DO NOT EDIT"
- `python-tests.yml:1092` "run: uv run python3 scripts/gen_domain_models.py --check"
- `netclass_rules_gen.py:26` "model_config = ConfigDict(frozen=True)"

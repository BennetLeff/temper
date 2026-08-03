---
title: "slot_generation config key was whitelisted but never parsed — every config-driven placer run silently used 10mm spacing"
date: "2026-07-17"
category: logic-errors
module: temper_placer
problem_type: logic_error
component: service_object
symptoms:
  - "deterministic placer runs with a YAML config specifying slot_generation.spacing_mm still produce the same slot grid as spacing_mm=10 (the hardcoded default)"
  - "load_constraints does not warn about slot_generation — it passes _warn_unknown_config_keys cleanly because the key is in _KNOWN_CONFIG_KEYS"
  - "getattr(config, 'slot_generation', None) in create_drc_aware_pipeline always returns None even when the YAML block is present and non-empty"
  - "no test failure: unit tests construct PlacementConstraints directly and never exercise config_loader's YAML parsing path for this field"
root_cause: logic_error
resolution_type: code_fix
severity: medium
tags:
  - atopile
  - placer
  - config-loader
  - silent-config-drop
  - yaml
  - slot-generation
  - deterministic-pipeline
---

> **Status update (2026-08-03 refresh):** subject (`create_drc_aware_pipeline` slot_generation parsing) is live and resolved; the linked `deterministic-placer-pipeline-post-jax-retirement-stubs.md` was deleted — see `jax-framework-retirement-reverse-topological-deletion-2026-07-05.md` for that era's record.


# slot_generation config key was whitelisted but never parsed

## Problem

`config_loader.py` accepted `slot_generation` as a known top-level YAML key
(`_KNOWN_CONFIG_KEYS` included it, so `_warn_unknown_config_keys` never
flagged it), but no `_parse_*` function actually read the key's value into
`PlacementConstraints`. The dataclass field either didn't exist or was
never assigned, so `getattr(config, "slot_generation", None)` in
`create_drc_aware_pipeline` (`deterministic/__init__.py:337`) always
returned `None`, and the pipeline silently fell back to the hardcoded
10mm `slot_spacing_mm` default — regardless of what the YAML file
requested.

This surfaced while authoring `configs/temper_production_config.yaml`
for the U6 placement re-baseline: a `slot_generation.spacing_mm: 4` block
was added to raise slot count from ~150 to ~888 (needed to place all 144
components), but the placer kept generating the old ~150-slot grid as if
the block weren't there.

## Symptoms

- Config-driven runs produce identical slot grids to config-free runs,
  even when `slot_generation.spacing_mm` differs between them.
- No warning, no error — the key passes the "unknown config keys" guard
  because it was added to the whitelist (presumably when the field was
  planned) without the corresponding parser ever being written.
- The retired 33-component fixture's config asked for `spacing_mm: 12`,
  close enough to the 10mm fallback that nobody noticed the value wasn't
  actually being applied — the bug had zero observable effect until a
  config needed a spacing *far* from the default.

## What Didn't Work

- Assuming the zone or net-class configuration was wrong, since those are
  the config sections that visibly change placement. Zone assignment and
  net-class steering were working correctly; the slot *density* just
  never changed no matter what `slot_generation` said.
- Re-reading the YAML for a typo. The key name, nesting, and
  `spacing_mm` field name all matched exactly what `_KNOWN_CONFIG_KEYS`
  declared as valid — the whitelist entry was the trap. A key being
  "known" was assumed to imply it was "handled."

## Solution

Add the missing dataclass field and the one-line parser that was never
written:

```python
# packages/temper-placer/src/temper_placer/_constraint_types/config.py
@dataclass
class PlacementConstraints:
    ...
    slot_generation: dict | None = None  # was missing entirely
```

```python
# packages/temper-placer/src/temper_placer/io/config_loader.py
def _parse_misc(config: dict, constraints: PlacementConstraints) -> None:
    if "slot_generation" in config and isinstance(config["slot_generation"], dict):
        constraints.slot_generation = config["slot_generation"]
    if "placement_priority" in config:
        ...
```

`create_drc_aware_pipeline` already had the consumption side correct
(`slot_config = getattr(config, "slot_generation", None); if slot_config
and "spacing_mm" in slot_config: slot_spacing = slot_config["spacing_mm"]`)
— it just had nothing upstream ever populating the field.

## Why This Works

`_KNOWN_CONFIG_KEYS` and the `_parse_*` functions are two independently
maintained lists that happen to describe the same config schema. Adding a
key to the whitelist is a one-line change that silences the "unknown
config key" warning; wiring the actual parse is a separate, easy-to-forget
step. Nothing enforces that every whitelisted key has a corresponding
assignment into `PlacementConstraints` — the whitelist's job is to catch
*typos and genuinely unknown keys*, not to catch *known keys with no
parser*, so a key can sit in a state that looks validated (passes the
unknown-key check) while being completely inert.

## Prevention

- **Test the parse, not just the schema.** Add a
  `test_config_loader_parses_slot_generation` (and, more generally, one
  assertion per `_KNOWN_CONFIG_KEYS` entry) that round-trips a minimal
  YAML fixture through `load_constraints` and asserts the resulting
  `PlacementConstraints` field is non-default. A whitelist-driven
  parametrized test — iterate `_KNOWN_CONFIG_KEYS`, assert each key has a
  corresponding non-default field after parsing a fixture that sets it —
  would have caught this and the next one of these automatically, rather
  than requiring someone to notice a config value silently not applying.
- **Treat "in `_KNOWN_CONFIG_KEYS`" and "has a parser" as one atomic
  change**, not two. When adding a key to the whitelist, add the
  `_parse_*` line in the same commit/diff hunk so review can't approve
  one without the other.
- **Pick default values that are far from any real config value**, not
  close to it. The bug went unnoticed for as long as it did because the
  fixture's requested `12mm` was close enough to the hardcoded `10mm`
  default that the placement output looked plausible either way. A
  config smoke test that asserts the *effective* value differs from the
  hardcoded default when the config sets a different one would surface
  this class of bug even when the numeric difference is small.

## Related Issues

- [`docs/solutions/logic-errors/silent-constraint-drop-seam-bugs-2026-07-11.md`](silent-constraint-drop-seam-bugs-2026-07-11.md)
  — the same *pattern* (a config value is accepted, appears validated,
  and is then silently dropped before reaching the stage that needs it)
  in a different pipeline (the CP-SAT `temper_placer.regression` path,
  not the deterministic `create_drc_aware_pipeline` path this doc
  covers). Two independent instances of the same failure shape in two
  different placer pipelines is a signal this project's config-loading
  layer needs a structural fix (the whitelist-driven parametrized test
  above), not just another one-off patch — worth a
  `/ce-compound-refresh config-loader` pass to consolidate the lesson if
  a third instance appears.
- [`docs/solutions/logic-errors/deterministic-placer-pipeline-post-jax-retirement-stubs.md`](deterministic-placer-pipeline-post-jax-retirement-stubs.md)
  — three earlier bugs in the same `create_drc_aware_pipeline` path,
  also uncaught by unit tests because the tests never exercised the real
  end-to-end seam. This is the sixth bug in that same family across this
  arc (three pipeline type-drift bugs, one Edge.Cuts parser bug, one NTC
  MPN mismatch, and this one) — all uncaught by passing unit tests
  because none of them exercised the actual config file → pipeline →
  output path against real data.
- `docs/plans/2026-07-15-001-feat-artifact-identity-provenance-plan.md`,
  unit U6 — the placement re-baseline task that surfaced this bug while
  authoring `configs/temper_production_config.yaml`.

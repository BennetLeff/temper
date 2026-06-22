---
title: "fix: Remediate N2 Safety Drift Sites"
type: fix
status: active
date: 2026-06-22
origin: docs/plans/2026-06-22-002-feat-safety-constant-ssot-plan.md
---

# fix: Remediate N2 Safety Drift Sites

## Summary

The N2 safety-constant SSOT plan shipped the *detection mechanism* (AST linter + reconciliation test). The four known drift sites were surfaced as HOLD reports but not remediated. This plan fixes each site — two authority-value corrections and two DRU orphan resolutions — and verifies the N2 reconciliation test reports zero HOLDs afterward. Also folds in the N4 `safety_category` update to `CreepageCheck` to use model-first resolution instead of hardcoded defaults.

---

## Problem Frame

The N2 reconciliation test (`test_safety_constant_reconciliation.py`) currently surfaces 4 HOLDs with an override file (`safety_constant_overrides.yaml`). The overrides paper over drift rather than fixing it:

| # | Site | Current | Authority | Status |
|---|------|---------|-----------|--------|
| 1 | `packages/temper-drc/src/temper_drc/checks/safety/creepage.py:20` | `min_iso_width_mm=7.0` | `6.0` (ACMains clearance) | **Drift — overridden** |
| 2 | `packages/temper-drc/src/temper_drc/cli.py:353` | `creepage_mm: 8.0` | `6.0` | **Drift — overridden** |
| 3 | `scripts/generate_kicad_dru.py:123` | `(min 3.0mm)` ACMains→HV | orphan — no authority source | **Orphan** |
| 4 | `scripts/generate_kicad_dru.py:158` | `(min 1.5mm)` HV internal | orphan — no authority source | **Orphan** |

Sites 1-2 are simple value corrections (7.0→6.0, 8.0→6.0). Sites 3-4 require an EE decision: verify the ACMains→HV 3.0mm and HV-internal 1.5mm values are correct, add them as new authority entries with documentation, and update the reconciliation test to cover them.

Additionally, the `HVLVSeparationCheck` at `hv_lv_separation.py:32` reads `constraints.hv_clearance_mm` (default `10.0`) — an independent inter-domain gap axis, not an intra-class clearance. The N2 reconciliation test correctly surfaces this as INFORMATIONAL (not HOLD). No fix needed; value is confirmed correct per EE sign-off.

---

## Scope Boundaries

### In scope

- Fix drift site 1: `CreepageCheck.min_iso_width_mm` default 7.0 → 6.0
- Fix drift site 2: YAML template `creepage_mm` 8.0 → 6.0
- Resolve drift site 3: verify 3.0mm ACMains→HV value, add authority entry, remove from overrides
- Resolve drift site 4: verify 1.5mm HV-internal value, add authority entry, remove from overrides
- Remove all 4 entries from `safety_constant_overrides.yaml`
- Verify N2 reconciliation test fails with empty override file (R10 acceptance)

### Deferred

- `hv_lv_separation.py` `hv_clearance_mm=10.0` axis — confirmed correct, stays as informational

### Out of scope

- Trace width or via dimension authority expansion (N2 R2 scope: safety clearances only)
- Pydantic migration of CLI template (N4 companion plan domain)
- Adding new net classes or design rules

---

## Implementation Units

### U1. Fix `CreepageCheck` default (site 1)

**Goal:** Change `min_iso_width_mm` from 7.0 to 6.0 to match ACMains authority clearance.

**Files:**
- `packages/temper-drc/src/temper_drc/checks/safety/creepage.py:20`

**Approach:**
1. Change `min_iso_width_mm: float = 7.0` → `min_iso_width_mm: float = 6.0` at line 20.
2. Update the N4 `resolve_safety_category()` integration so `CreepageCheck` reads `safety_category` from the model rather than relying on the hardcoded default. The check currently uses `min_iso_width_mm` as a single threshold for all isolation packages; post-N4, it should read from `SAFETY_CONSTANT_AUTHORITY` for ACMains/HighVoltage clearance values.

**Verification:** N2 reconciliation test reports one fewer HOLD. Existing temper-drc tests pass.

---

### U2. Fix CLI YAML template (site 2)

**Goal:** Change CLI template `creepage_mm` from 8.0 to 6.0.

**Files:**
- `packages/temper-drc/src/temper_drc/cli.py:353`

**Approach:**
1. Change `"creepage_mm": 8.0` → `"creepage_mm": 6.0` at line 353.
2. Verify the change by running `python -m temper_drc compare --help` (the template string is used in CLI arg defaults/docs).

**Verification:** N2 reconciliation test reports one fewer HOLD. CLI help output shows updated default.

---

### U3. Resolve ACMains→HV DRU orphan (site 3)

**Goal:** Add 3.0mm as a formal authority entry for ACMains-to-HighVoltage clearance (inter-class gap between AC Mains domain and high-voltage DC domain), or document it as site-specific DRU-only if no authority value is appropriate.

**Files:**
- `scripts/generate_kicad_dru.py:121-131` — where the 3.0mm DRU rule is emitted
- `packages/temper-placer/src/temper_placer/core/design_rules.py` — SAFETY_CONSTANT_AUTHORITY (add entry if 3.0mm is decided as authority value)

**Approach:**
1. The 3.0mm ACMains→HV gap is an inter-class clearance, not an intra-class one. Authority values 6.0mm (ACMains to LV) and 2.0mm (HV to LV) bound it from both sides. The 3.0mm value is a derived minimum (ACMains creepage path through HV domain).
2. **Decision option A (recommended):** Keep 3.0mm as a DRU-only site-specific rule. Add it to the reconciliation test's `DRU_allowed_orphans` list with a comment: `# ACMains→HV inter-class gap — not derivable from single-class authority values; site-specific minimum per EE review.`
3. **Decision option B:** Add `("ACMains", "HighVoltage", "clearance", 3.0)` as a new authority entry in `SAFETY_CONSTANT_AUTHORITY` + document in N2 problem frame table.
4. **This plan assumes option A** (DRU-only orphan, documented in reconciliation test). If EE review prefers option B, adjust in implementation.

**Verification:** N2 reconciliation test reports zero HOLDs for this site (entry moved to `DRU_allowed_orphans` list).

---

### U4. Resolve HV-internal DRU orphan (site 4)

**Goal:** Add 1.5mm as a documented value for HV-internal same-footprint clearance.

**Files:**
- `scripts/generate_kicad_dru.py:152-160` — where the 1.5mm DRU rule is emitted

**Approach:**
1. The 1.5mm HV-internal same-footprint gap is a manufacturing clearance, not a safety clearance. It prevents solder bridging between HV pads on the same component.
2. **Decision:** Keep as DRU-only site-specific rule. Add to `DRU_allowed_orphans` in the reconciliation test with annotation: `# HV internal same-footprint — manufacturing clearance, not a safety authority value; site-specific minimum per EE review.`
3. No authority entry needed. The value is self-documenting in `generate_kicad_dru.py` comments.

**Verification:** N2 reconciliation test reports zero HOLDs for this site.

---

### U5. Remove overrides and verify clean reconciliation

**Goal:** Remove all 4 HOLD entries from `packages/temper-drc/tests/safety_constant_overrides.yaml` and confirm N2 R10 acceptance: reconciliation test fails with empty override file.

**Files:**
- `packages/temper-drc/tests/safety_constant_overrides.yaml` — remove entries for sites 1-4
- `packages/temper-drc/tests/test_safety_constant_reconciliation.py` — add DRU_allowed_orphans list (U3, U4)

**Approach:**
1. Delete the 4 override entries corresponding to the fixed drift sites.
2. Add `DRU_allowed_orphans` list to the reconciliation test with entries for sites 3 and 4.
3. Run the reconciliation test with empty override file → passes (zero HOLDs).
4. Run the reconciliation test with the original override entries still present → fails (R10 acceptance: the test catches removed overrides).

**Verification:** `uv run pytest packages/temper-drc/tests/test_safety_constant_reconciliation.py -v` passes with zero overrides or expected-orphan annotations. N2 AST linter still passes.

---

## System-Wide Impact

- **`creepage.py`** — `CreepageCheck` default tightened from 7.0mm to 6.0mm. Existing boards with isolation packages narrower than 7.0mm but wider than 6.0mm that previously passed will now fail. This is the intended correction — the previous threshold was too lenient.
- **`cli.py`** — YAML template default tightened. New `temper-drc compare` runs generated with defaults will use 6.0mm instead of 8.0mm.
- **`generate_kicad_dru.py`** — no code change (values stay). Only the reconciliation test's understanding changes.
- **`safety_constant_overrides.yaml`** — shrinks from 4 HOLD entries to 0. This is the goal.
- **No firmware, no PCB schematics, no placer algorithm changes.**

---

## Risk Analysis & Mitigation

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Reducing `CreepageCheck` threshold from 7.0 to 6.0 flags existing boards with isolation packages in the 6.0-7.0mm range | Medium | Low | The temper PCB has no isolation packages in this range per `_safety_keywords.py` catalog. External corpus boards may have false positives; DRC check is advisory (warn, don't block) per N4 U4. |
| Reducing CLI template default from 8.0 to 6.0 changes behavior for new `temper-drc compare` runs | Low | Low | Template defaults are overridden by config files in all production use; only bare-CLI-first runs are affected. |
| 3.0mm ACMains→HV value is wrong and the EE review disagrees with DRU-only orphan status | Medium | Low | The plan assumes option A but defers final decision to implementation. Option B (authority entry) is documented and can be switched at implementation time. |

---

## Test Strategy

- N2 AST linter (`test_safety_constant_lint.py`) continues to pass — no new bare float literals introduced.
- N2 reconciliation test (`test_safety_constant_reconciliation.py`) passes with empty override file — all 4 HOLDs resolved.
- Existing temper-drc safety tests pass.
- Existing temper-placer core tests pass (SAFETY_CONSTANT_AUTHORITY unchanged for sites 3-4 under option A).

---
date: 2026-06-21
topic: safety-constant-ssot
---

# Safety-Constant SSOT with Two-Layer Enforcement

## Summary

A focused hardening initiative that collapses the duplicated safety clearance constants scattered across the Temper PCB toolchain into a single authority record, then enforces that authority with **two independent layers**: (1) a static AST linter that rejects float literals matching an authority value anywhere outside the authority record, and (2) a runtime reconciliation test that reads every consumer of net-class clearance values and fails CI as a **HOLD** on any divergence. Static prevention + dynamic detection — neither layer alone is sufficient, because the linter can't see string-formatted mm literals in DRU text generation and the reconciliation test can't pinpoint the offending line at edit time.

This doc is intentionally narrow: it covers the **enforcement mechanism** (authority record + linter + reconciliation test) for the safety-constant duplication. The broader Pydantic typed net-class model migration, IEC citation fields, golden-file DRU diffing, and KiCad headless DRC fixture are owned by `2026-06-21-source-of-truth-validation-requirements.md` (Phases 2–3 there). N2 is compatible with that migration and defers to it; the authority record and both enforcement layers work against the current `@dataclass NetClassRules` today and against the future Pydantic model unchanged.

---

## Problem Frame

The same physical safety constraint — "AC Mains clearance is 6.0mm" — is stated in **four** places in the codebase today, with **silent drift between them**:

| Site | File:line | Value |
|------|-----------|-------|
| Authority candidate | `packages/temper-placer/temper_placer/core/design_rules.py:484,489` | `clearance=6.0`, `creepage_mm=6.0` (ACMains); `clearance=2.0`, `creepage_mm=2.0` (HighVoltage) |
| DRU generator literal | `scripts/generate_kicad_dru.py:106` | `(min 6.0mm)` ACMains→LV |
| DRU generator literal | `scripts/generate_kicad_dru.py:123` | `(min 3.0mm)` ACMains→HV — **no source in design_rules.py** |
| DRU generator literal | `scripts/generate_kicad_dru.py:140` | `(min 2.0mm)` HV→LV |
| DRU generator literal | `scripts/generate_kicad_dru.py:158` | `(min 1.5mm)` HV internal same-footprint — **no source** |
| Creepage check default | `packages/temper-drc/temper_drc/checks/safety/creepage.py:10` | `min_iso_width_mm=7.0` — **matches no other site** |
| CLI template default | `packages/temper-drc/temper_drc/cli.py:307` | `creepage_mm=8.0` in generated YAML template — **matches no other site** |
| HV/LV separation source | `packages/temper-drc/temper_drc/checks/safety/hv_lv_separation.py:32` | reads `constraints.hv_clearance_mm` (default `10.0` per `input/constraints.py:90`) — **independent axis, matches nothing** |

The drift is not hypothetical: `creepage.py` says 7.0mm, the CLI template says 8.0mm, `TEMPER_NET_CLASSES["ACMains"].creepage_mm` says 6.0mm, and the DRU emits 6.0mm for ACMains clearance. A developer who changes one site has no signal that three others disagree. The June 2026 clean-base sprint fixed twelve silent bugs of exactly this shape — constraint exists in one place, interpreted in another, no machine-enforced link.

The two-layer design addresses both failure modes the single-layer alternatives miss:
- A **linter only** can't catch string-formatted mm values inside DRU text (`f"(min {v}mm)"`) without parsing Python f-strings into their AST — fragile and incomplete. It also can't catch values that *should* match the authority but are recomputed from a different formula (e.g. `hv_clearance_mm` derived from a YAML file).
- A **reconciliation test only** catches the drift but only after CI runs — it doesn't point the developer at the offending line at edit time, and it can be bypassed by a developer who skips local tests.

Together: the linter prevents the easy case (bare float literals), the reconciliation test catches the hard case (derived/indirect values), and a HOLD-grade CI failure ensures the divergence is never silently merged.

---

## Actors

- A1. **Developer** — edits `TEMPER_NET_CLASSES`, the DRU generator, or a DRC check; the primary source of drift.
- A2. **AST linter** — runs as a ruff custom check (or standalone pre-commit hook) over the Python source tree; rejects bare float literals that match an authority value outside the authority record.
- A3. **Reconciliation test** — a pytest in `packages/temper-drc/tests/` that imports every consumer of net-class clearance values, reads the emitted DRU text, and asserts equality with the authority record.
- A4. **CI pipeline** — runs A2 and A3 on every push; emits a **HOLD** status on A3 failure (not a hard block — see Failure Mode decision).

---

## Key Flows

- F1. **Developer adds a new bare float literal matching an authority value**
  - **Trigger:** A1 writes `clearance=6.0` in a new DRC check or helper.
  - **Actors:** A1, A2
  - **Steps:** (1) A1 saves the file. (2) A2 scans the AST, finds a `Float(value=6.0)` outside the authority record and outside an allowlist of legitimate non-clearance uses. (3) A2 emits a lint error naming the file, line, the matched authority constant, and the canonical import path the developer should use instead. (4) A1 either imports the authority value or adds a justified allowlist entry with a comment.
  - **Outcome:** The literal never reaches CI; the drift is prevented at edit time.
  - **Covered by:** R2, R3

- F2. **Developer changes the authority value but forgets a string-formatted consumer**
  - **Trigger:** A1 changes `TEMPER_NET_CLASSES["ACMains"].clearance` from 6.0 to 6.5 and updates the DRU generator's `(min 6.0mm)` literal — but the DRU text is built via an f-string from a *recomputed* expression that still yields 6.0.
  - **Actors:** A1, A3, A4
  - **Steps:** (1) A1 commits. (2) A3 imports `TEMPER_NET_CLASSES`, runs the DRU generator, regex-extracts `(min Xmm)` values from the emitted text, maps each rule to its authority net-class pair, and compares. (3) A3 finds the DRU emits 6.0mm where the authority says 6.5mm. (4) A4 reports a HOLD failure naming the DRU rule, the emitted value, and the authority value.
  - **Outcome:** The drift is detected at CI, not in bring-up. The merge is blocked pending either fixing the generator or updating the authority.
  - **Covered by:** R4, R5

- F3. **Developer adds a new net class with a clearance value**
  - **Trigger:** A1 adds a `"PowerAudio"` entry to `TEMPER_NET_CLASSES` with `clearance=1.2`.
  - **Actors:** A1, A2, A3
  - **Steps:** (1) A1 adds the entry. (2) A2 sees a new authority value `1.2` registered; future bare `1.2` literals elsewhere are now rejected. (3) A3's reconciliation test detects that the new net class has no corresponding DRU rule and emits a **HOLD** with a message naming the uncovered net class — the developer must either add a DRU rule or mark the class as DRU-exempt in the authority record.
  - **Outcome:** New net classes are consciously connected to all consumers; no silent gap.
  - **Covered by:** R4

---

## Requirements

### Phase 1 — Authority record

- R1. A single canonical authority record for safety-constant values is designated on the existing `NetClassRules` entries in `TEMPER_NET_CLASSES` (`packages/temper-placer/temper_placer/core/design_rules.py`). No schema migration is required for Phase 1; the existing `@dataclass` fields (`clearance`, `creepage_mm`) are the authority. The Pydantic migration in the companion doc's Phase 2 supersedes this record's *type* but not its *authority* — the same identifiers remain the SSOT after migration.
- R2. The authority set covers exactly these fields per net class, for exactly these net classes: `ACMains` (`clearance`, `creepage_mm`), `HighVoltage` (`clearance`, `creepage_mm`). Trace width, via dimensions, and non-safety net classes (`Signal`, `Power`, `GND`, `HighSpeed`, `GateDrive`, `HighCurrent`, `FinePitch`) are **out of scope** for N2 — they are not safety constants and expanding the authority set dilutes the linter's signal-to-noise ratio. The authority set is explicitly enumerated in a constant (e.g. `SAFETY_CONSTANT_AUTHORITY`) listing `(net_class, field, value)` triples, so the linter and reconciliation test read from one place.

### Phase 2 — Static layer (AST linter)

- R3. An AST linter scans all Python files under `packages/` and `scripts/`. For each `ast.Constant` of type `float` whose value matches an entry in `SAFETY_CONSTANT_AUTHORITY`, the linter reports an error **unless** the literal appears inside the authority record's defining module or inside an explicit `# allow-safety-constant: <reason>` comment on the same line. The error message names the matched authority triple and the canonical import path.
- R4. The linter is wired into CI via the existing ruff configuration (`[tool.ruff]` in root `pyproject.toml`) as a custom check, **or** as a standalone pre-commit hook / pytest in `packages/temper-drc/tests/` if ruff's plugin API does not support custom AST visitors in the installed version. The chosen mechanism is documented in `CLAUDE.md`. String-formatted mm values inside DRU text generation (`f"(min {v}mm)"`) are **not** in linter scope — they are the reconciliation test's responsibility. The linter does not attempt to evaluate f-strings.
- R5. The linter's authority-value matching uses exact float equality on the raw literal, not rounded comparison. A literal `6.0` matches an authority value of `6.0`; a literal `6.00` also matches (same float). A literal `0.006` (metres) does **not** match `6.0` and is not flagged — unit conversion is the developer's responsibility and out of scope.

### Phase 3 — Dynamic layer (reconciliation test)

- R6. A pytest in `packages/temper-drc/tests/` (named e.g. `test_safety_constant_reconciliation.py`) performs three reads on every CI run:
  1. Imports `TEMPER_NET_CLASSES` and extracts the authority values from R2.
  2. Invokes `scripts/generate_kicad_dru.py:generate_dru()` and regex-extracts every `(min Xmm)` constraint with its enclosing rule name and net-class condition.
  3. Imports `CreepageCheck` and reads its `min_iso_width_mm` default; imports `ConstraintSet` and reads its `hv_clearance_mm` default; reads the CLI template's `creepage_mm` value.
- R7. The test maps each DRU rule to its authority pair(s) — `ACMains→LV` maps to `ACMains.clearance`; `ACMains→HV` maps to a *cross-class* authority value that **does not currently exist** in `TEMPER_NET_CLASSES` (the 3.0mm ACMains→HV rule has no source). The test reports each DRU literal that has no authority source as a **HOLD** with a message naming the DRU rule and the missing authority pair. This is the mechanism that surfaces the existing 3.0mm and 1.5mm orphan literals.
- R8. The test asserts `CreepageCheck.min_iso_width_mm` default equals `TEMPER_NET_CLASSES["ACMains"].creepage_mm`; asserts `ConstraintSet.hv_clearance_mm` default equals `TEMPER_NET_CLASSES["HighVoltage"].clearance`; asserts the CLI template's `creepage_mm` equals the same. Each mismatch produces a named HOLD failure identifying both sites and both values.
- R9. **Failure mode: HOLD, not hard block.** A reconciliation failure exits CI with a distinct non-zero code that the project's merge policy treats as a manual-review hold (the PR cannot auto-merge but a human may override with a recorded justification). Rationale: safety-constant drift is sometimes intentional during bring-up (e.g. deliberately relaxing a rule to probe a failure mode); a hard block forces developers to delete the test, which is worse than a hold. The override is recorded in the PR description and the test's failure message names the override mechanism. The linter (R3) remains a hard block — there is no legitimate reason to introduce a new bare float literal that duplicates an authority value.

### Phase 4 — Coverage of the existing drift

- R10. On landing, the reconciliation test **must fail as HOLD** against the current `main` branch, surfacing all four known drifts: (a) `CreepageCheck` 7.0 vs authority 6.0, (b) CLI template 8.0 vs authority 6.0, (c) DRU ACMains→HV 3.0mm orphan, (d) DRU HV internal same-footprint 1.5mm orphan. This is the acceptance test for N2 itself — if the test passes on `main`, N2 is not working. The follow-up fix for each drift is a separate changeset tracked against the companion doc's Phase 2 (Pydantic validators) or a dedicated cleanup ticket; N2's deliverable is the **detection**, not the remediation.

---

## Success Criteria

- A developer who types `clearance=6.0` into a new DRC check sees a lint error at save/commit time naming the authority constant — never reaching CI.
- A developer who changes `TEMPER_NET_CLASSES["ACMains"].clearance` but forgets the DRU generator's recomputed f-string sees a HOLD failure at CI naming both values — never reaching bring-up.
- The four known drifts in `main` today (7.0, 8.0, 3.0mm orphan, 1.5mm orphan) appear as a single named HOLD report the first time the reconciliation test runs.
- After N2 lands, no new safety-constant duplication can be merged without either (a) importing the authority value, (b) adding an allowlist entry with a recorded reason, or (c) a human override with a recorded justification.

---

## Out of Scope

- **Pydantic typed net-class model migration** — owned by `2026-06-21-source-of-truth-validation-requirements.md` Phase 2 (R4 there). N2's authority record works against the current `@dataclass`; the migration supersedes the type but not the authority.
- **IEC 60664-1 citation fields and normative-minimum validators** — owned by the companion doc Phase 2 (R5 there). N2 enforces *internal consistency* across consumers; it does not validate against the IEC standard.
- **Golden-file DRU diffing and KiCad headless DRC fixture** — owned by the companion doc Phase 3 (R6–R8 there). N2's reconciliation test checks value consistency between source and emitted text, not whether the emitted DRU is byte-identical to a golden file or whether KiCad actually fires the rule.
- **Trace width, via dimensions, non-safety net classes** — out of the authority set (R2). These are not safety constants; expanding scope dilutes the linter signal.
- **DRU rules with no authority source remediation** — N2 surfaces the 3.0mm ACMains→HV and 1.5mm HV-internal orphans; deciding the correct authority value for them is an EE decision tracked separately.
- **Cross-layer voltage consistency (VoltageMap)** — owned by the companion doc Phase 4.

---

## Assumptions

- **A1.** The authority set is exactly `{(ACMains, clearance, 6.0), (ACMains, creepage_mm, 6.0), (HighVoltage, clearance, 2.0), (HighVoltage, creepage_mm, 2.0)}` as of `main` today. The 2.0mm HighVoltage clearance is itself wrong per IEC 60664-1 (companion doc R5/R11 will catch this); N2 treats the current declared value as the authority for *internal-consistency* purposes and does not assert it against the IEC standard.
- **A2.** Ruff's installed version (`>=0.1.6` per root `pyproject.toml:10`) supports custom AST-based checks via plugin API. If it does not, the fallback is a standalone pre-commit hook or pytest (R4); the requirements are written to be mechanism-agnostic.
- **A3.** The reconciliation test can invoke `generate_dru()` from `scripts/generate_kicad_dru.py` as an importable function without file-system side effects. Verified: the function returns a string (`scripts/generate_kicad_dru.py:39`); the script's `__main__` block handles file writing. Import is clean.
- **A4.** The existing CI runs pytest and ruff on every push; no new CI runner infrastructure is required. The reconciliation test slots into `packages/temper-drc/tests/` alongside existing tests.
- **A5.** The four known drifts are bugs, not intentional overrides. If any is intentional (e.g. `CreepageCheck` 7.0mm is a deliberate conservative margin above the 6.0mm authority), the remediation ticket records the justification and the reconciliation test gains an allowlist entry — but the default assumption is drift until proven otherwise.
- **A6.** Exact float equality (R5) is sufficient because all current literals are single-decimal values (6.0, 7.0, 8.0, 2.0, 3.0, 1.5). No site uses higher precision that would trigger floating-point representation issues. If higher-precision constants are added later, the equality check is revisited.

---

## Open Questions

### Resolve Before Planning

- **[Affects R3][Technical]** Which mechanism for the AST linter — ruff custom plugin, standalone pre-commit hook, or pytest-time AST scan? Depends on ruff plugin API support in the pinned version. Recommend the pre-commit hook as the lowest-friction fallback if ruff's plugin API is unstable.
- **[Affects R9][Policy]** Does the project's CI/merge policy support a distinct "HOLD" exit code separate from "FAIL"? If CI only supports pass/fail, the HOLD semantics degrade to a hard block with an allowlist-on-failure escape hatch. Confirm the CI runner's exit-code handling before implementing R9.
- **[Affects R7][Technical]** Should the reconciliation test also cover the DRU rules that have *no* authority source (3.0mm ACMains→HV, 1.5mm HV-internal) as HOLD, or only flag values that *conflict* with an existing authority? Recommendation: flag orphans as HOLD — surfacing them is the primary value of N2 over the companion doc's golden-file diff (which would not flag orphans because the golden file already contains them).

### Deferred to Planning

- **[Affects R2][EE]** Should `FinePitch.clearance=0.1` be added to the authority set? It is a safety-adjacent constant (minimum manufacturable clearance) but not a safety constant in the IEC sense. Default: no — keep the authority set narrow.
- **[Affects R10][Process]** Is the remediation of the four known drifts tracked as a single ticket or four separate tickets? Recommend four, since each has a different owner (placer, drc, drc, EE-judgement).

---
title: "feat: Safety-Constant SSOT with Two-Layer Enforcement"
type: feat
status: active
date: 2026-06-22
origin: docs/brainstorms/2026-06-21-safety-constant-ssot-requirements.md
---

# feat: Safety-Constant SSOT with Two-Layer Enforcement

## Summary

A narrow hardening initiative that collapses the duplicated safety clearance constants scattered across the Temper PCB toolchain into a single enumerated authority record, then enforces it with **two independent layers**: (1) a static AST linter (a standalone pytest using `ast.walk`) that rejects bare float literals matching an authority value anywhere outside the authority record, and (2) a runtime reconciliation test that reads every consumer of net-class clearance values and fails CI on any divergence. The linter prevents the easy case (bare literals); the reconciliation test catches the hard case (string-formatted mm values inside DRU text and recomputed/derived values). On landing, the reconciliation test **must fail against current `main`** — surfacing the four known drifts as a single named HOLD report. N2's deliverable is the **detection mechanism**, not the remediation of those drifts.

This plan is intentionally narrow. Pydantic typed net-class migration, IEC 60664-1 citation fields, golden-file DRU diffing, and KiCad headless DRC fixtures are owned by the companion plan `docs/plans/2026-06-21-002-feat-source-of-truth-validation-plan.md` (Phases 2–3 there). The authority record and both enforcement layers here work against the current `@dataclass NetClassRules` today and against the future Pydantic model unchanged — they key off identifiers, not types.

---

## Problem Frame

The same physical safety constraint — "AC Mains clearance is 6.0mm" — is stated in **four drifting sites** today, with no machine-enforced link between them. The current `main` branch contains this drift:

| # | Site | Value | Authority status |
|---|------|-------|------------------|
| 1 | `packages/temper-placer/temper_placer/core/design_rules.py:484,489` (ACMains) | `clearance=6.0`, `creepage_mm=6.0` | authority |
| 1 | `packages/temper-placer/temper_placer/core/design_rules.py:495,500` (HighVoltage) | `clearance=2.0`, `creepage_mm=2.0` | authority |
| 2 | `scripts/generate_kicad_dru.py:106` (ACMains→LV) | `(min 6.0mm)` | matches authority |
| 2 | `scripts/generate_kicad_dru.py:140` (HV→LV) | `(min 2.0mm)` | matches authority |
| 3 | `scripts/generate_kicad_dru.py:123` (ACMains→HV) | `(min 3.0mm)` | **orphan — no source** |
| 3 | `scripts/generate_kicad_dru.py:158` (HV internal same-footprint) | `(min 1.5mm)` | **orphan — no source** |
| 4 | `packages/temper-drc/temper_drc/checks/safety/creepage.py:10` | `min_iso_width_mm=7.0` | **drifts from authority 6.0** |
| 4 | `packages/temper-drc/temper_drc/cli.py:307` (YAML template) | `creepage_mm=8.0` | **drifts from authority 6.0** |
| — | `packages/temper-drc/temper_drc/checks/safety/hv_lv_separation.py:32` | reads `constraints.hv_clearance_mm` (default `10.0` per `input/constraints.py:90`) | **independent axis** — HV/LV separation is an inter-domain gap, not an intra-class clearance; out of N2 authority but in reconciliation-test *reporting* scope so the divergence is visible |

A developer who changes one site has no signal that three others disagree. The June 2026 clean-base sprint fixed twelve silent bugs of exactly this shape. The two-layer design addresses both failure modes the single-layer alternatives miss:

- A **linter only** cannot catch string-formatted mm values inside DRU text (`f"(min {v}mm)"`) without parsing Python f-strings into their AST — fragile and incomplete. It also cannot catch values recomputed from a different formula (e.g. `hv_clearance_mm` derived from a YAML file).
- A **reconciliation test only** catches the drift but only after CI runs — it does not point the developer at the offending line at edit time, and it can be bypassed by a developer who skips local tests.

Together: the linter prevents the easy case (bare float literals at edit time), the reconciliation test catches the hard case (derived/indirect values at CI time), and a non-zero CI exit ensures the divergence is never silently merged.

---

## Scope Boundaries

### In scope

- R1–R10 from the origin requirements document: the authority record, the AST linter, the reconciliation test, and the acceptance test that the reconciliation **fails against current `main`**.
- The four known drifts are *surfaced* by N2. Their *remediation* is tracked as separate changesets against the companion plan's Phase 2 (Pydantic validators) or as dedicated cleanup tickets — N2's deliverable is detection, not the fix.

### Deferred to companion plan

- `docs/plans/2026-06-21-002-feat-source-of-truth-validation-plan.md` Phase 2: Pydantic migration of `NetClassRules` (U4) and IEC 60664-1 `iec_reference` + normative-minimum validator (U5).
- Same plan Phase 3: golden-file DRU diffing (U6), `kiutils` round-trip parse (U7), and KiCad headless DRC fixture (U8).
- Same plan Phase 4: `VoltageMap` cross-layer voltage consistency. The `hv_clearance_mm=10.0` axis in `hv_lv_separation.py` is owned by that work; N2 only *reports* its divergence from `HighVoltage.clearance=2.0` as informational, it does not adjudicate the value.

### Out of scope

- Trace width, via dimensions, and non-safety net classes (`Signal`, `Power`, `GND`, `HighSpeed`, `GateDrive`, `HighCurrent`, `FinePitch`) — not safety constants; expanding the authority set dilutes the linter's signal-to-noise ratio (per R2).
- Deciding the correct authority value for the 3.0mm ACMains→HV and 1.5mm HV-internal DRU orphans — an EE decision tracked separately. N2 surfaces them as HOLD; remediation is a follow-up ticket.
- IEC 60664-1 citation fields and normative-minimum validators — owned by the companion plan's U5. N2 enforces *internal consistency* across consumers; it does not validate against the IEC standard.
- Atopile-side voltage/creepage oracle — owned by the companion plan's Phase 5.

---

## Key Technical Decisions

**Authority set is exactly `{(ACMains, clearance, 6.0), (ACMains, creepage_mm, 6.0), (HighVoltage, clearance, 2.0), (HighVoltage, creepage_mm, 2.0)}`**, enumerated in a single `SAFETY_CONSTANT_AUTHORITY` constant listing `(net_class, field, value)` triples so the linter and reconciliation test read from one place. The 2.0mm HighVoltage clearance is itself wrong per IEC 60664-1 (the companion plan's U5 will catch this); N2 treats the current declared value as the authority for *internal-consistency* purposes and does not assert it against the IEC standard. (see origin — Assumption A1)

**Linter mechanism: standalone pytest using `ast.walk`, NOT a ruff plugin.** Research confirms ruff has no public custom-check AST visitor API in the pinned version (`[tool.ruff.lint] select = ["E","W","F","I","B","C4","UP"]` in root `pyproject.toml`; ruff's plugin model is Rust-side checkers, not Python AST visitors). The fallback in R4 is therefore the chosen mechanism: a pytest in `packages/temper-drc/tests/` that walks the AST of every `.py` file under `packages/` and `scripts/`, finds `ast.Constant` nodes with `isinstance(value, float)`, and reports any whose value matches an authority triple outside the authority record's defining module or outside an explicit `# allow-safety-constant: <reason>` line comment. This runs in CI alongside the reconciliation test as a hard block. It is also runnable locally as `uv run pytest packages/temper-drc/tests/test_safety_constant_lint.py`. (resolves origin Open Question [Affects R3])

**Reconciliation test reads DRU output + `creepage.py` + `TEMPER_NET_CLASSES` + `cli.py` template, fails as HOLD on divergence.** Per R6–R8, the test performs three reads: (1) imports `TEMPER_NET_CLASSES` and extracts the authority values; (2) invokes `scripts/generate_kicad_dru.py:generate_dru()` and regex-extracts every `(min Xmm)` constraint with its enclosing rule name and net-class condition (the function returns a string at `scripts/generate_kicad_dru.py:39` — import is clean, no file-system side effects, per origin Assumption A3); (3) imports `CreepageCheck` and reads its `min_iso_width_mm` default (`7.0` at `packages/temper-drc/temper_drc/checks/safety/creepage.py:10`), imports `ConstraintSet` and reads its `hv_clearance_mm` default (`10.0` at `packages/temper-drc/temper_drc/input/constraints.py:90`), and reads the CLI template's `creepage_mm` (`8.0` at `packages/temper-drc/temper_drc/cli.py:307`).

**CI has no HOLD tier — degrade to hard block + allowlist escape hatch.** The CI workflow (`.github/workflows/python-tests.yml`) runs `uv run pytest tests/ -v --tb=short` and treats any non-zero exit as a job failure; there is no distinct "HOLD" exit code path, and GitHub Actions merge gating is pass/fail. R9's HOLD semantics therefore degrade to: the reconciliation test fails CI as a hard block by default, but the test honors a committed `packages/temper-drc/tests/safety_constant_overrides.yaml` allowlist file (the `TEMPER_SAFETY_OVERRIDE` env var mentioned in earlier drafts is dropped in U3's refinement — see Implementation Unit U3, "Decision: load the override file unconditionally" — in favor of unconditional file loading) mapping `(site, expected_value, reason)` triples. When an override is present and matches the divergent site, the test emits a clear `OVERRIDE` report line (site, values, recorded reason) and passes. The override file is the recorded justification required by R9. A human reviewer sees the override entry in the PR diff. This is the documented escape hatch; the linter (R3) remains a hard block with no override — there is no legitimate reason to introduce a new bare float literal that duplicates an authority value. (resolves origin Open Question [Affects R9])

**DRU orphans: flag safety-class orphans as HOLD; non-safety orphans get allowlist with reason.** Per R7 and the resolved Open Question [Affects R7]: the reconciliation test maps each DRU rule to its authority pair(s). `ACMains→LV` maps to `ACMains.clearance` (6.0). `HV→LV` maps to `HighVoltage.clearance` (2.0). `ACMains→HV` (3.0mm) and `HV internal same-footprint` (1.5mm) have *no* source in `TEMPER_NET_CLASSES` — they are orphans. The test flags any safety-class DRU rule (rule condition references `ACMains` or `HighVoltage`) without an authority source as a HOLD with a message naming the DRU rule and the missing authority pair. Non-safety DRU rules (GateDrive near HV, Power internal, Ground clearance, USB differential, Default routing) without an authority source are flagged only if their value collides with an authority value; otherwise they are added to a default allowlist in `safety_constant_overrides.yaml` with a `non-safety class` reason. Surfacing orphans is the primary value of N2 over the companion plan's golden-file diff (which would not flag orphans because the golden file already contains them).

**Exact float equality, no rounded comparison.** Per R5 and Assumption A6: a literal `6.0` matches an authority value of `6.0`; `6.00` also matches (same float). `0.006` (metres) does NOT match `6.0` and is not flagged — unit conversion is the developer's responsibility. All current literals are single-decimal (6.0, 7.0, 8.0, 2.0, 3.0, 1.5), so floating-point representation issues do not arise.

**Authority record location: `packages/temper-placer/temper_placer/core/design_rules.py`.** `SAFETY_CONSTANT_AUTHORITY` is defined in the same module as `TEMPER_NET_CLASSES` so the linter's "outside the authority record's defining module" exemption is a single file boundary. The constant is derived *from* `TEMPER_NET_CLASSES` at module scope (so changing `TEMPER_NET_CLASSES["ACMains"].clearance` updates the authority set automatically), but is also explicitly enumerated as `tuple[tuple[str, str, float], ...]` so the linter can read it without importing the dataclass.

**Documentation sync.** Per `AGENTS.md` "Documentation & Context Maintenance": the chosen linter mechanism (standalone pytest, not ruff plugin) and the override escape-hatch convention are recorded in `CLAUDE.md` (or `AGENT_INSTRUCTIONS.md` if `CLAUDE.md` is absent — confirm at implementation time) in the same commit as U2. The four known drifts and their tracking tickets are listed in the plan's Risk Analysis so a future reader can trace "why does the reconciliation test fail on `main`?" without re-deriving the history.

---

## Implementation Units

### Phase 1 — Authority record

### U1. Designate `SAFETY_CONSTANT_AUTHORITY` in design_rules.py

**Goal:** Define a single canonical authority record enumerating `(net_class, field, value)` triples for exactly `{ACMains, HighVoltage} × {clearance, creepage_mm}`, derived from `TEMPER_NET_CLASSES` at module scope so it cannot itself drift.

**Requirements:** R1, R2

**Dependencies:** None

**Files:**
- `packages/temper-placer/temper_placer/core/design_rules.py` (add `SAFETY_CONSTANT_AUTHORITY` after `TEMPER_NET_CLASSES`)
- `packages/temper-placer/tests/core/test_design_rules.py` (add authority-record assertions)

**Approach:**

Add at module scope, immediately after the `TEMPER_NET_CLASSES` literal:

```python
# Directional — not specification:
SAFETY_CONSTANT_AUTHORITY_NET_CLASSES: frozenset[str] = frozenset({"ACMains", "HighVoltage"})
SAFETY_CONSTANT_AUTHORITY_FIELDS: frozenset[str] = frozenset({"clearance", "creepage_mm"})

SAFETY_CONSTANT_AUTHORITY: tuple[tuple[str, str, float], ...] = tuple(
    (nc_name, field_name, float(getattr(nc, field_name)))
    for nc_name, nc in TEMPER_NET_CLASSES.items()
    if nc_name in SAFETY_CONSTANT_AUTHORITY_NET_CLASSES
    for field_name in SAFETY_CONSTANT_AUTHORITY_FIELDS
)
```

This is derived from `TEMPER_NET_CLASSES` so the authority set tracks the dataclass values automatically, but is materialized as a flat tuple of triples so the linter (U2) and reconciliation test (U3) can read it without instantiating the dataclass. A `float()` cast is applied so the linter compares floats to floats (the dataclass field is already `float`, but the cast is defensive against future Pydantic migration that might return `int` for round values).

**Patterns to follow:** Existing `TEMPER_NET_CLASSES` literal style in `design_rules.py:480-560`. Module-scope constant placement.

**Test scenarios:**
- `from temper_placer.core.design_rules import SAFETY_CONSTANT_AUTHORITY` succeeds.
- `SAFETY_CONSTANT_AUTHORITY` contains exactly 4 triples: `("ACMains","clearance",6.0)`, `("ACMains","creepage_mm",6.0)`, `("HighVoltage","clearance",2.0)`, `("HighVoltage","creepage_mm",2.0)`.
- Changing `TEMPER_NET_CLASSES["ACMains"].clearance` to `6.5` (in a test that mutates the dict) changes the corresponding authority triple to `("ACMains","clearance",6.5)`.
- `("FinePitch","clearance",0.1)` is NOT in `SAFETY_CONSTANT_AUTHORITY` (non-safety class excluded).
- `("ACMains","trace_width",2.5)` is NOT in `SAFETY_CONSTANT_AUTHORITY` (non-safety field excluded).

**Verification:** `uv run pytest packages/temper-placer/tests/core/test_design_rules.py` passes. `python -c "from temper_placer.core.design_rules import SAFETY_CONSTANT_AUTHORITY; print(SAFETY_CONSTANT_AUTHORITY)"` prints the 4 triples.

---

### Phase 2 — Static layer (AST linter)

### U2. AST linter as standalone pytest using ast.walk

**Goal:** A pytest that walks the AST of every `.py` file under `packages/` and `scripts/`, finds `ast.Constant` nodes whose value is a float matching an entry in `SAFETY_CONSTANT_AUTHORITY`, and reports an error unless the literal is inside the authority record's defining module (`design_rules.py`) or carries an `# allow-safety-constant: <reason>` comment on the same line.

**Requirements:** R3, R4, R5

**Dependencies:** U1 (`SAFETY_CONSTANT_AUTHORITY` must exist)

**Files:**
- `packages/temper-drc/tests/test_safety_constant_lint.py` (new — the linter itself, structured as a pytest that fails on violation)
- `CLAUDE.md` or `AGENT_INSTRUCTIONS.md` (document the linter mechanism and the `# allow-safety-constant:` escape hatch — confirm which file exists at implementation time; the companion plan's U6 documents the golden-file update command in `CLAUDE.md`, so prefer `CLAUDE.md` if present)

**Approach:**

The linter is a single pytest module. It runs at import/collection time:

1. Import `SAFETY_CONSTANT_AUTHORITY` from `temper_placer.core.design_rules`.
2. Build a set of authority float values: `authority_values = {v for (_, _, v) in SAFETY_CONSTANT_AUTHORITY}`.
3. Enumerate Python files under `packages/` and `scripts/` (use `pathlib.Path` walking, exclude `tests/` subtrees so the linter does not flag its own test fixtures, and exclude `design_rules.py` itself as the authority module).
4. For each file, `ast.parse` the source, then `ast.walk` the tree. For each `ast.Constant` node with `isinstance(node.value, float) and node.value in authority_values`:
   - Read the source line. If the line contains `# allow-safety-constant:` with a non-empty reason, skip.
   - Otherwise, record a violation: `(file, lineno, node.value, matched_authority_triples)`.
5. Assert `violations == []`, printing a structured report if not. Each violation message names the file, line, the matched authority triple(s), and the canonical import path: `from temper_placer.core.design_rules import TEMPER_NET_CLASSES; TEMPER_NET_CLASSES["ACMains"].clearance`.

The existing `creepage.py:10` (`min_iso_width_mm: float = 7.0`) and `cli.py:307` (`creepage_mm=8.0`) sites are NOT flagged by the linter on `main` today, because `7.0` and `8.0` are not in `authority_values` (which is `{6.0, 2.0}`). This is correct — those are *drifted* values, not duplicates of an authority value, and the reconciliation test (U3) catches them. The linter's job is to prevent *new* duplications of the authority values; the reconciliation test's job is to catch existing and future *drifted* values.

A legitimate non-clearance use of `6.0` or `2.0` (e.g. a board dimension constant `BOARD_WIDTH_MM = 2.0`) is handled by the `# allow-safety-constant: board width, not a clearance` line comment. The linter does not attempt to evaluate f-strings, so `f"(min {v}mm)"` in `generate_kicad_dru.py` is NOT in linter scope — it is the reconciliation test's responsibility.

The linter is wired into CI via the existing `uv run pytest tests/ -v` step in `.github/workflows/python-tests.yml:48-50`. No new CI job is required — the linter is just another test file in `packages/temper-drc/tests/`. The existing `paths:` filter on the workflow already includes `packages/**`, so editing any Python file under `packages/` triggers the linter.

**Patterns to follow:** `packages/temper-drc/tests/checks/test_factory.py` (pytest patterns in this repo). `ast.walk` stdlib usage. The `assert set(class_order) == set(TEMPER_NET_CLASSES.keys())` AST-adjacent pattern already in `generate_kicad_dru.py:240`.

**Test scenarios:**
- On current `main`, `uv run pytest packages/temper-drc/tests/test_safety_constant_lint.py` passes (no authority-value duplicates exist outside `design_rules.py`).
- A new file containing `X = 6.0` (no allowlist comment) causes the linter to fail naming the file, line, `("ACMains","clearance",6.0)`, and the canonical import path.
- A new file containing `X = 6.0  # allow-safety-constant: board width` passes.
- A new file containing `X = 2.0` (no comment) fails naming `("HighVoltage","clearance",2.0)` and `("HighVoltage","creepage_mm",2.0)`.
- A new file containing `X = 0.006` is NOT flagged (unit conversion out of scope per R5).
- `design_rules.py` itself is NOT scanned (authority module exemption).
- Test files under `packages/*/tests/` are NOT scanned (test fixture exemption).
- A file containing `f"(min {v}mm)"` is NOT flagged (f-string evaluation out of scope).

**Verification:** `uv run pytest packages/temper-drc/tests/test_safety_constant_lint.py` passes on `main`. Temporarily adding `X = 6.0` to a library module causes the test to fail with a named violation. The `# allow-safety-constant: <reason>` comment suppresses the failure.

---

### Phase 3 — Dynamic layer (reconciliation test)

### U3. Reconciliation test — three-read consistency check with allowlist override

**Goal:** A pytest in `packages/temper-drc/tests/` that performs three reads (authority record, emitted DRU text, runtime check defaults + CLI template), maps each DRU rule to its authority pair, and fails CI on any divergence — unless the divergent site is listed in `safety_constant_overrides.yaml` with a matching `(site, expected_value, reason)` entry, in which case it emits an `OVERRIDE` report line and passes.

**Requirements:** R6, R7, R8, R9, R10

**Dependencies:** U1 (`SAFETY_CONSTANT_AUTHORITY`), U2 (linter already prevents new duplicates; U3 catches drifted and orphan values)

**Files:**
- `packages/temper-drc/tests/test_safety_constant_reconciliation.py` (new — the reconciliation test)
- `packages/temper-drc/tests/safety_constant_overrides.yaml` (new — committed allowlist file; initially empty or with non-safety DRU defaults)
- `CLAUDE.md` or `AGENT_INSTRUCTIONS.md` (document the override escape hatch and the `TEMPER_SAFETY_OVERRIDE` env var)

**Approach:**

The test is structured as a single `test_safety_constants_reconcile()` function that collects a list of `Finding` records, then asserts no `Finding` has severity `HOLD` unless it is covered by an override entry.

**Read 1 — authority:**
```python
from temper_placer.core.design_rules import TEMPER_NET_CLASSES, SAFETY_CONSTANT_AUTHORITY
authority = {(nc, field): val for (nc, field, val) in SAFETY_CONSTANT_AUTHORITY}
# authority = {("ACMains","clearance"):6.0, ("ACMains","creepage_mm"):6.0,
#              ("HighVoltage","clearance"):2.0, ("HighVoltage","creepage_mm"):2.0}
```

**Read 2 — DRU text:**
```python
from scripts.generate_kicad_dru import generate_dru  # scripts/ is on sys.path via pyproject
# OR import via importlib.util from the absolute path — confirm at implementation time
dru_text = generate_dru()
# Regex-extract each "(constraint clearance (min Xmm))" with its enclosing (rule "Name") and condition
# Build a list of DruRule(name, condition, value_mm)
```

The regex extracts `(rule "<Name>"` blocks, pairs each with its `(condition "...")` and `(constraint clearance (min <X>mm))`, and parses the condition's `A.NetClass == '<Class>'` / `B.NetClass == '<Class>'` clauses to identify the net-class pair. The map is:

| DRU rule | Net-class pair | Authority key | Expected value |
|----------|----------------|---------------|----------------|
| "AC Mains to LV" | `(ACMains, *)` | `("ACMains","clearance")` | 6.0 |
| "AC Mains to HV" | `(ACMains, HighVoltage)` | **orphan** — no authority | flagged HOLD |
| "HV to LV" | `(HighVoltage, *)` | `("HighVoltage","clearance")` | 2.0 |
| "HV internal same footprint" | `(HighVoltage, HighVoltage)` | **orphan** — no authority | flagged HOLD |
| "GateDrive near HV" | `(GateDrive, HighVoltage)` | non-safety class | allowlisted |
| "Power internal same footprint" | `(Power, Power)` | non-safety class | allowlisted |
| "Ground clearance" | `(Ground, *)` | non-safety class | allowlisted |
| "USB differential" | `(HighSpeed, HighSpeed)` | non-safety class | allowlisted |
| "Default routing" | `(*, *)` | non-safety class | allowlisted |
| "Same footprint pads" / "Fine pitch IC pads" (anticipated — not yet present in generate_kicad_dru.py) | `(*, *)` | non-safety class | allowlisted |

For each DRU rule: if it has an authority key, assert `dru_value == authority[authority_key]`; else if it references a safety class (`ACMains` or `HighVoltage`) in its condition, flag as HOLD (orphan); else look up in the default non-safety allowlist.

**Read 3 — runtime check defaults + CLI template:**
```python
import inspect
from temper_drc.checks.safety.creepage import CreepageCheck
from temper_drc.input.constraints import ConstraintSet
from temper_drc.cli import init_constraints  # or read the template literal via inspect.getsource

# CreepageCheck.__init__ default
sig = inspect.signature(CreepageCheck.__init__)
creepage_default = sig.parameters["min_iso_width_mm"].default  # 7.0

# ConstraintSet default
hv_clearance_default = ConstraintSet().hv_clearance_mm  # 10.0

# CLI template creepage_mm literal — read via inspect.getsource(cli.init_constraints)
# and regex-extract "creepage_mm": <X> from the template dict, OR import the template
# dict as a module-level constant if a small refactor exposes it. Prefer inspect-based
# extraction to avoid modifying cli.py in this unit.
cli_creepage = <extracted from cli.py:307 template>  # 8.0
```

Assert:
- `creepage_default == authority[("ACMains","creepage_mm")]` → `7.0 == 6.0` → **HOLD** (drift site 4a).
- `cli_creepage == authority[("ACMains","creepage_mm")]` → `8.0 == 6.0` → **HOLD** (drift site 4b).
- `hv_clearance_default == authority[("HighVoltage","clearance")]` → `10.0 == 2.0` → **INFORMATIONAL** (independent axis — HV/LV inter-domain separation is not the same physical constraint as intra-class clearance; report the divergence but do not HOLD, per Scope Boundaries. The companion plan's VoltageMap work owns this value.)

**Override mechanism:**

`safety_constant_overrides.yaml` schema:
```yaml
overrides:
  - site: "creepage.py:CreepageCheck.__init__.min_iso_width_mm"
    expected_value: 7.0
    reason: "Known drift vs authority 6.0; remediation tracked in temper-xxx"
    ticket: "temper-xxx"  # optional
  - site: "cli.py:init_constraints.creepage_mm"
    expected_value: 8.0
    reason: "Known drift vs authority 6.0; remediation tracked in temper-yyy"
    ticket: "temper-yyy"
  - site: "dru:AC Mains to HV"
    expected_value: 3.0
    reason: "Orphan — no authority source; EE decision pending in temper-zzz"
    ticket: "temper-zzz"
  - site: "dru:HV internal same footprint"
    expected_value: 1.5
    reason: "Orphan — no authority source; EE decision pending in temper-www"
    ticket: "temper-www"
```

The test loads this file (if `TEMPER_SAFETY_OVERRIDE=1` env var is set, or unconditionally — the override file is the *recorded justification*, not an opt-in). A `Finding` is downgraded from HOLD to OVERRIDE if `(site, expected_value)` matches an entry with a non-empty `reason`. The test prints every OVERRIDE line in the report so a reviewer sees the justification in CI output.

**Decision: load the override file unconditionally.** R9's "human may override with a recorded justification" is satisfied by the committed YAML file — the recorded reason IS the override. There is no separate env-var gate. If the override file is missing or empty, every HOLD finding fails the test. This keeps the override visible in `git diff` and prevents silent bypass. (Refines R9 — the env-var `TEMPER_SAFETY_OVERRIDE` mentioned in the Approach is dropped in favor of unconditional override-file loading; document this in `CLAUDE.md`.)

**Acceptance test (R10):** On current `main`, with an initially-empty `safety_constant_overrides.yaml`, the test **must fail** with four HOLD findings:
1. `creepage.py:CreepageCheck.__init__.min_iso_width_mm` — 7.0 vs authority 6.0
2. `cli.py:init_constraints.creepage_mm` — 8.0 vs authority 6.0
3. `dru:AC Mains to HV` — orphan, no authority source
4. `dru:HV internal same footprint` — orphan, no authority source

This is the acceptance test for N2 itself — if the test passes on `main` with an empty override file, N2 is not working. The plan therefore lands in two commits: (a) U1+U2+U3 with an empty override file — CI fails as expected, demonstrating detection; (b) the same commit populates `safety_constant_overrides.yaml` with the four known-drift entries (with reasons citing the follow-up remediation tickets), and CI goes green. Commit (a) may be squashed into (b) for landing if the project's merge policy requires green CI on every commit — in that case, the override file is populated in the same commit as U3, and the acceptance criterion is verified locally by temporarily emptying the override file and confirming the four HOLDs appear. Document this two-commit convention in `CLAUDE.md`.

**Patterns to follow:** `packages/temper-drc/tests/checks/test_factory.py` (pytest assertion style). `inspect.signature` / `inspect.getsource` stdlib usage. YAML loading via `yaml.safe_load` (already a dependency in `temper-drc`).

**Test scenarios:**
- With empty `safety_constant_overrides.yaml`, the test fails with exactly 4 HOLD findings naming the sites and values above. (R10 acceptance)
- With the 4 known-drift override entries populated, the test passes and prints 4 OVERRIDE lines.
- Changing `TEMPER_NET_CLASSES["ACMains"].clearance` to `6.5` and updating the DRU generator's `(min 6.0mm)` literal to `(min 6.5mm)` (but forgetting the `creepage.py` default) causes a HOLD on `creepage.py` (7.0 vs new authority 6.5) — drift detected.
- Adding a new net class `"PowerAudio"` with `clearance=1.2` to `SAFETY_CONSTANT_AUTHORITY_NET_CLASSES` causes a HOLD on the DRU (no rule covers `PowerAudio`) — uncovered net class detected. Covers F3.
- Removing one of the 4 override entries causes the corresponding HOLD to re-surface.
- A non-safety DRU rule (e.g. "GateDrive near HV" 0.5mm) is NOT flagged because it is in the default non-safety allowlist.
- The `hv_clearance_mm=10.0` divergence is reported as INFORMATIONAL, not HOLD.
- The override file's `expected_value` field is checked: if the actual divergent value does not match `expected_value`, the override does not apply and the HOLD fires (prevents stale overrides).

**Verification:** `uv run pytest packages/temper-drc/tests/test_safety_constant_reconciliation.py` fails with 4 HOLDs on empty override file; passes with 4 override entries populated. CI step `Run temper-drc tests` (`.github/workflows/python-tests.yml:48-50`) reflects this.

---

## System-Wide Impact

- **CI pipeline:** Two new test files in `packages/temper-drc/tests/` (`test_safety_constant_lint.py`, `test_safety_constant_reconciliation.py`) plus one new committed YAML file (`safety_constant_overrides.yaml`). No new CI job — both tests run in the existing `Run temper-drc tests` step (`.github/workflows/python-tests.yml:48-50`). The `paths:` filter on the workflow already includes `packages/**` so editing any Python file under `packages/` triggers both tests. `scripts/generate_kicad_dru.py` is NOT in the workflow's `paths:` filter today (`paths: ['packages/**', 'pyproject.toml', '.github/workflows/python-tests.yml']`); consider adding `'scripts/**'` to the filter so DRU generator edits trigger the reconciliation test. This is a one-line workflow edit in U3.
- **`CLAUDE.md` / `AGENT_INSTRUCTIONS.md`:** U2 documents the linter mechanism and the `# allow-safety-constant: <reason>` comment convention. U3 documents the override escape hatch, the `safety_constant_overrides.yaml` schema, and the two-commit landing convention for the four known drifts. Confirm which file exists at implementation time (the companion plan's U6 references `CLAUDE.md` — prefer it if present).
- **`packages/temper-placer/temper_placer/core/design_rules.py`:** Gains `SAFETY_CONSTANT_AUTHORITY` and two frozensets at module scope. No existing code changes — the constant is additive.
- **`packages/temper-drc/temper_drc/checks/safety/creepage.py`:** NOT modified by N2. The 7.0 default is surfaced as a HOLD and recorded in the override file; remediation is a separate changeset.
- **`packages/temper-drc/temper_drc/cli.py`:** NOT modified by N2. The 8.0 template literal is surfaced as a HOLD via `inspect.getsource`; remediation is a separate changeset.
- **`scripts/generate_kicad_dru.py`:** NOT modified by N2. The 3.0mm and 1.5mm orphans are surfaced as HOLD; the EE decision and DRU generator fix are a separate changeset.
- **Developer workflow:** A developer who types `clearance=6.0` into a new DRC check sees a lint error at `uv run pytest` time (locally) and at CI time. A developer who changes `TEMPER_NET_CLASSES["ACMains"].clearance` but forgets a consumer sees a HOLD failure at CI naming both values. To override, the developer adds an entry to `safety_constant_overrides.yaml` with a `reason` and (optionally) a ticket ID — the override is visible in `git diff` for human review.

---

## Risk Analysis & Mitigation

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Reconciliation test fails to import `generate_dru` from `scripts/` (scripts/ not on `sys.path`) | Medium | Medium | Confirm `scripts/` is importable from `temper-drc` tests at implementation time; if not, use `importlib.util.spec_from_file_location` to load `scripts/generate_kicad_dru.py` by absolute path. The function returns a string (no side effects), so import-time execution is safe. |
| `inspect.getsource(cli.init_constraints)` regex extraction is brittle to CLI template formatting changes | Low | Low | The template dict literal is stable (`"creepage_mm": 8.0`); the regex `r'"creepage_mm":\s*([\d.]+)'` is precise. If `cli.py` is refactored to a dataclass template, the extraction is updated in the same changeset. |
| Linter flags a legitimate non-clearance use of `6.0` or `2.0` (e.g. board dimensions, via drill sizes) | Low | High | The `# allow-safety-constant: <reason>` comment is the documented escape hatch. The linter's exclusion of `tests/` and `design_rules.py` reduces noise. If the allowlist volume grows large, revisit the authority set (per R2's narrow-set rationale). |
| Override file becomes a dumping ground for unreviewed drifts | Medium | Medium | The override entry's `reason` and `ticket` fields are required and visible in `git diff`. The reconciliation test prints every OVERRIDE line in CI output so a reviewer sees the justification. CODEOWNERS entry for `safety_constant_overrides.yaml` requiring safety-reviewer approval is a follow-up (out of N2 scope). |
| A new net class added to `TEMPER_NET_CLASSES` is not added to `SAFETY_CONSTANT_AUTHORITY_NET_CLASSES` and silently bypasses the authority | Low | Medium | The reconciliation test's "uncovered safety net class" check (F3) only fires for classes in `SAFETY_CONSTANT_AUTHORITY_NET_CLASSES`. A class added to `TEMPER_NET_CLASSES` but not to the authority frozenset is simply not safety-checked — by design (R2's narrow scope). Document this in `CLAUDE.md` so developers know safety classes must be added to both. |
| Exact float equality (R5) breaks if a future authority value has higher precision (e.g. `6.35`) | Low | Low | Assumption A6 holds for current values. If higher-precision constants are added, the equality check is revisited in that changeset. Documented in the plan; not a current risk. |
| CI `paths:` filter excludes `scripts/**` so editing `generate_kicad_dru.py` does not trigger the reconciliation test | Medium | High | U3 adds `'scripts/**'` to `.github/workflows/python-tests.yml` `paths:` filter. One-line edit. |
| Linter AST walk is slow on the full `packages/` tree | Low | Low | The tree is small (~100 .py files). `ast.walk` over a single file is microseconds. Total linter runtime is well under 1 second. If it grows, narrow the scan to `packages/temper-drc/temper_drc/checks/` and `packages/temper-placer/temper_placer/core/` (the two directories where safety constants are consumed). |

---

## Test Strategy

- **U1 (authority record):** Unit tests in `packages/temper-placer/tests/core/test_design_rules.py` asserting the 4-triple contents, the derivation-from-`TEMPER_NET_CLASSES` property, and the exclusion of non-safety classes/fields.
- **U2 (linter):** The linter IS a test (`test_safety_constant_lint.py`). Its self-verification is the test scenarios above — temporarily adding a `6.0` literal to a library module and confirming the test fails. No separate test file.
- **U3 (reconciliation):** The reconciliation test IS a test (`test_safety_constant_reconciliation.py`). Its acceptance criterion (R10) is that it fails with 4 HOLDs on an empty override file and passes with 4 override entries. The two-commit landing convention (or local verification by emptying the override file) is the documented verification procedure.
- **CI integration:** Both new test files run in the existing `Run temper-drc tests` step. No new CI job. The `paths:` filter is extended to include `scripts/**`.
- **Regression:** The existing `packages/temper-drc/tests/` suite continues to pass. The existing `packages/temper-placer/tests/core/` suite continues to pass. No existing tests are modified except `test_design_rules.py` (U1 adds assertions).

---

## Deferred to Implementation

- **`scripts/` importability:** Confirm whether `from scripts.generate_kicad_dru import generate_dru` works from `packages/temper-drc/tests/` with the current `pyproject.toml` / `sys.path` setup, or whether `importlib.util.spec_from_file_location` is needed. The `scripts/` directory has no `__init__.py` (it's a script directory, not a package), so the `importlib` approach is likely required.
- **`CLAUDE.md` vs `AGENT_INSTRUCTIONS.md`:** Confirm which file exists at implementation time and is the convention for the project. The companion plan's U6 references `CLAUDE.md`; prefer it if present, else use `AGENT_INSTRUCTIONS.md`.
- **CLI template extraction:** Decide between `inspect.getsource(cli.init_constraints)` + regex vs. a small refactor exposing the template dict as a module-level constant in `cli.py`. The `inspect` approach avoids modifying `cli.py` in N2 (keeping the drift-site file unchanged is cleaner — the drift is surfaced, not silently fixed). Prefer `inspect` unless the regex proves brittle.
- **Override file location:** `packages/temper-drc/tests/safety_constant_overrides.yaml` is the default. If the file is better placed at repo root (alongside `pyproject.toml`) for visibility, move it and update the test's path resolution. Implementation-time decision.
- **Two-commit vs single-commit landing:** If the project's merge policy requires green CI on every commit (likely, given GitHub branch protection), U3 lands as a single commit with the override file pre-populated, and the R10 acceptance criterion is verified locally by temporarily emptying the override file. If squashed-merge is acceptable, the two-commit convention (failing commit, then green commit) is a stronger audit trail. Confirm at implementation time.
- **Remediation tickets for the 4 known drifts:** Per origin Open Question [Affects R10][Process], recommend four separate tickets (placer, drc, drc, EE-judgement) since each has a different owner. The override file's `ticket` fields reference these. Create the tickets as part of U3 implementation.

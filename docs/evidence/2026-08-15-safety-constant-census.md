<!-- provenance: commit=de06e7ab102a99b7aaf3ad13dec7cd09959cb39f dirty=UNKNOWN -->
---
module: repo-wide
tags: [safety, constants, census, clearance, creepage, ampacity, thermal, ocp, pd, material-group, voltage-class]
problem_type: untraceable-constants
---

# Safety-Constant Census — 2026-08-15

**Branch:** `census/safety-constant-sites-2026-08-15` (base `origin/main` @ `8f21d2725`)
**Method:** read-only grep/read sweep of the entire tree; no source files modified.
**Purpose:** prep work for a migration to typed `SafetyValue` with provenance. Every
site below is a bare `f64`/`int`/named constant that asserts or enforces a
clearance, creepage, ampacity, thermal, OCP/OVP, PD, material-group, or
voltage-class value.

## Classification vocabulary

| Class | Meaning |
|---|---|
| **FABRICATED** | No source exists anywhere (repo or recovered standard); created by the same commit that created its consumer, or contradicts a recovered table. |
| **CITED** | Carries a standards citation at/near the site. **May be MISCITED** — citation verified only where the recovered tables make it checkable. |
| **UNCITED** | No citation attached; may or may not be correct. |
| **DERIVED** | Traces to a recovered standards table or a documented measured value (e.g. ngspice 570.5 Vrms). |

Recovered ground truth used for cross-checks (all in-tree):
- **IEC 60335-1 Table 17** (basic-insulation creepage, PD1/PD2/PD3 × group I/II/IIIa-IIIb), recovered verbatim at
  `docs/evidence/2026-07-28-creepage-determination-brainstorm.md:286-294`. Max value **12.5**; value set contains **no 14.0 and no 6.0**.
- **IEC 60335-1 Table 18** (functional-insulation creepage), recovered at
  `docs/evidence/2026-08-12-hv-hv-creepage-determination.md:194-201`. Row vi (>500–800 V): **6.3 PD2 / 10.0 PD3**.
- **IEC 60335-1 Table 16** clearance value set (per handoff): {0.5, 1.5, 3.0, 5.5, 8.0, 11.0} — **no 6.0, no 2.0**.
- **Clause 29.2 material groups** (recovered): I = CTI ≥ 600; II = 400–600; **IIIa = 175–400; IIIb = 100–175**.
  IEC 60335-1 merges IIIa/IIIb into one column. So "IIIb, CTI 175–249" is a **self-contradiction** (175–249 is IIIa).

---

## 1. Creepage

### 1a. The `14.0` mm family — the fabricated base (5 production/test homes + 2 test pins)

Every site below descends from one unsourced `14.0` base. The repo's own recovered
Table 17 contains no 14.0 at any row (max 12.5). The value and its first citation
were written in the same commits as the implementations (`1f85f4ad1b`,
`1e99a151be`). PR #1198's `19.6 = 14.0 × 1.4` inherits the untraceability.

| file:line | constant/expression | value | context | prod/test | citation? | class |
|---|---|---|---|---|---|---|
| `packages/temper-design-bundle/src/net_types.rs:245` | `VoltageClass::HIGH_VOLTAGE => 14.0` (in `get_creepage_mm`) | 14.0 mm | Production creepage kernel (base × {0.8, 1.0, 1.4} by material group) | **PROD** | docstring "per IEC 60335" (no table) | **FABRICATED** |
| `packages/temper-drc-rs/src/router_clearance.rs:433` | `VoltageClass::HighVoltage => 14.0` (in `voltage_class_creepage_mm`) | 14.0 mm | Live router clearance gate's creepage arm ("IEC 60335-1 Table 17, material group 2") | **PROD** | "IEC 60335-1 Table 17" — 14.0 not in recovered Table 17 | **FABRICATED** (MISCITED) |
| `packages/temper-placer/tests/core/test_net_types_pbt.py:78` | `_CREEPAGE_BASE["HIGH_VOLTAGE"] = 14.0` | 14.0 mm | Property test "Independent IEC 60335 reference tables" — byte-identical to impl, same commit | test | "Independent IEC 60335 reference tables" | **FABRICATED** (not independent) |
| `packages/temper-placer/tests/core/_net_types_py_oracle.py:113` | `VoltageClass.HIGH_VOLTAGE: 14.0` | 14.0 mm | Pinned differential oracle (verbatim pre-migration Python) | test | none | FABRICATED (inherits impl) |
| `packages/temper-placer/tests/router_v6/test_clearance_boundary.py:607-611` | `required_clearance == approx(14.0)` | 14.0 mm | "most-conservative across all standards (IEC 60950-1, 60335-1, 60664-1, 62368-1, IPC-2221)" | test | five standards named; matches none | **FABRICATED** (MISCITED) |
| `packages/temper-placer/tests/router_v6/test_clearance_check.py:294` | `required == 14.0mm` | 14.0 mm | clearance_check regression pin | test | none | UNCITED (SNAPSHOT) |
| `packages/temper-drc-rs/src/router_clearance.rs:1521,1544` | `400V -> required clearance 14.0mm (HIGH_VOLTAGE creepage table)` | 14.0 mm | differential-test comment + assertion | test | "(HIGH_VOLTAGE creepage table)" | UNCITED (SNAPSHOT) |

**Also in this family:** `19.6` (14.0 × 1.4) exists only on branch `fix/router-nlayer-routing`
(PR #1198), not on `main` — an untraceable base × an untraceable multiplier (handoff §3).

### 1b. PD2/PD3 reinforced & functional creepage — the *traceable* family

These trace to the recovered Table 17/18 and are the model of what the rest should be.

| file:line | constant | value | context | prod/test | citation? | class |
|---|---|---|---|---|---|---|
| `scripts/generate_kicad_dru.py:81` | `HV_CREEPAGE_PD2_MM = 8.0` | 8.0 mm | DRU emission, reinforced mains<->PELV barrier | **PROD** | cl. 29.2.3 × Table 17 row iv (4.0 × 2) ✓ recovered | **DERIVED** |
| `scripts/generate_kicad_dru.py:82` | `HV_CREEPAGE_PD3_MM = 12.6` | 12.6 mm | DRU fallback | **PROD** | Table 17 row iv PD3 (6.3 × 2) ✓ recovered | **DERIVED** |
| `scripts/generate_kicad_dru.py:110` | `HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD2_MM` | 8.0 mm | selection alias | **PROD** | — | DERIVED |
| `scripts/generate_kicad_dru.py:199` | `HV_TANK_CREEPAGE_PD2_MM = 6.3` | 6.3 mm | tank↔bus functional creepage | **PROD** | Table 18 row vi PD2 ✓ recovered | **DERIVED** |
| `scripts/generate_kicad_dru.py:200` | `HV_TANK_CREEPAGE_PD3_MM = 10.0` | 10.0 mm | tank fallback | **PROD** | Table 18 row vi PD3 ✓ recovered | **DERIVED** |
| `scripts/generate_kicad_dru.py:231-234` | `HV_TANK_CREEPAGE_ENFORCED_MM = {PD2:…, PD3:…}[_TANK_POLLUTION_DEGREE]` | 6.3 mm | dict-select (drift-gate-safe alias) | **PROD** | — | DERIVED |
| `packages/temper-placer/src/temper_placer/core/isolation_constants.py:31` | `MIN_BARRIER_WIDTH_MM = 8.0` | 8.0 mm | isolation-barrier SSOT (keepout + CP-SAT corridor) | **PROD** | keepout docstring cites "approximately 6.4mm CLEARANCE and 8.0mm CREEPAGE" — 6.4 is the IPC-2221 251–300 V bracket, not an IEC clearance; 8.0 itself ✓ Table 17 row iv × 2 | **DERIVED** (docstring conflates sources) |
| `packages/temper-placer/src/temper_placer/placer/cp_sat/tank_creepage.py:173` | `HV_TANK_CREEPAGE_PD2_MM = 6.3` | 6.3 mm | CP-SAT tank constraint | **PROD** | Table 18 row vi ✓ | **DERIVED** |
| `packages/temper-placer/src/temper_placer/placer/cp_sat/tank_creepage.py:178` | `HV_TANK_CREEPAGE_PD3_MM = 10.0` | 10.0 mm | CP-SAT tank constraint | **PROD** | Table 18 row vi ✓ | **DERIVED** |
| `packages/temper-placer/src/temper_placer/placer/cp_sat/tank_creepage.py:183` | `DEFAULT_TANK_CREEPAGE_MM = HV_TANK_CREEPAGE_PD3_MM` | 10.0 mm | designs against PD3 by default (as-built governs) | **PROD** | — | DERIVED |
| `elec/src/constraints.ato:36` | `creepage = 8.0mm` | 8.0 mm | HighVoltage module constraint | **PROD** | "IEC 60335-1 reinforced insulation" ✓ row iv × 2 | CITED (correct) |
| `elec/src/constraints.ato:84,96` | `min_creepage = 8.0mm` | 8.0 mm | HV_to_LV / HV_to_ISO inter-domain | **PROD** | "IEC 60335-1 reinforced insulation" | CITED |
| `elec/src/constraints.ato:46,91` | `creepage = 5.0mm` / `min_creepage = 5.0mm` | 5.0 mm | ACMains module / AC_to_LV | **PROD** | none | UNCITED (5.0 exists in recovered Table 17 only at row iv PD3-I or row v PD2-IIIa/IIIb — no stated basis) |
| `packages/temper-placer/tests/placer/cp_sat/test_tank_creepage.py:51,54` | `== 10.0`, `== 6.3` | 10.0 / 6.3 | pins module constants | test | — | DERIVED |
| `packages/temper-drc-rs/src/req_safe_01.rs:1096-1099` | `("MAINS","LV_CONTROL","reinforced", 6.0, 8.0, 10.0)` etc. | 8.0 creepage | REQ-SAFE-01 matrix (port of Python SSOT) | **PROD** | matrix header cites Table 17 row iv ✓ (creepage 4.0/8.0 correct; see clearance section for the 6.0 column) | CITED (creepage column correct) |
| `packages/temper-placer/src/temper_placer/requirements/validators/clearance.py:259-288` | `IEC60335_REQUIREMENTS` rows: `min_creepage_mm` 4.0 / 8.0 / 4.0 / 8.0 / 8.0 / **1.0** | 4.0/8.0/1.0 | REQ-SAFE-01 SSOT matrix | **PROD** | header cites Table 17 row iv (4.0 ✓, 8.0 ✓); FUNCTIONAL row 1.0 pinned while the module's own comment concedes Table 18 gives **1.1 (PD2) / 1.8 (PD3)** — known-low pin | CITED — **FUNCTIONAL 1.0 is a known-low MISCITE** |
| `packages/temper-placer/tests/requirements/safety/test_clearance.py:186-225` | matrix (4.0/8.0/1.0) | 4.0/8.0/1.0 | regression pin of the matrix | test | same header claims Table 17 | CITED (SNAPSHOT of above; inherits the 1.0 pin) |

### 1c. The `6.0` legacy creepage drift family (one fact, many homes, no recovered value)

`6.0` appears in **no recovered table row** for any voltage this board carries.
It is the historical placer-feasibility figure, repeatedly re-cited to Table 17/16
which do not contain it.

| file:line | constant | value | context | prod/test | citation? | class |
|---|---|---|---|---|---|---|
| `packages/temper-placer/configs/netclass_rules.yaml:17` | `ACMains.creepage_mm: 6.0` | 6.0 | placer netclass SSOT | **PROD** | `because:` cites "IEC 60335-1 Table 16 working isolation at 400V" — Table 16 is *clearance*, and 6.0 is in neither table | **MISCITED** |
| `packages/temper-placer/configs/netclass_rules.yaml:46` | `HighVoltage.creepage_mm: 6.0` | 6.0 | placer netclass SSOT | **PROD** | `because:` points at the *clearance* derivation (HV_INTERNAL_CLEARANCE_MM) | **MISCITED** |
| `packages/temper-placer/configs/netclass_rules.yaml:108` | `HighVoltageSignal.creepage_mm: 6.0` | 6.0 | carve-out class | **PROD** | "carried over unchanged" | UNCITED |
| `packages/temper-placer/configs/netclass_rules.yaml:141` | `HighVoltageIsolated.creepage_mm: 6.0` | 6.0 | gate-drive bootstrap class | **PROD** | "legacy, not primary-cited" (self-labeled) | UNCITED |
| `packages/temper-placer/configs/netclass_rules.yaml:76` | `HighVoltageTank.creepage_mm: 6.3` | 6.3 | tank class | **PROD** | Table 18 row vi PD2 ✓ | **DERIVED** |
| `packages/temper-placer/src/temper_placer/core/design_rules.py:81` | `ACMains.creepage_mm = 6.0` | 6.0 | Python TEMPER_NET_CLASSES | **PROD** | none at site | UNCITED |
| `packages/temper-placer/src/temper_placer/core/design_rules.py:140,381,394` | `HighVoltage/HighVoltageSignal/HighVoltageIsolated creepage_mm = 6.0` | 6.0 | Python TEMPER_NET_CLASSES | **PROD** | HighVoltageTank:343 = 6.3 (DERIVED) | UNCITED |
| `configs/temper_deterministic_config.yaml:167` | `creepage_mm: 6.0` | 6.0 | deterministic config netclass | **PROD** | "IEC 60335-1 Table 17 (basic insulation)" — 6.0 not in Table 17 | **MISCITED** |
| `configs/temper_production_config.yaml:180` | `creepage_mm: 6.0` | 6.0 | orphan config (not loaded) | prod-orphan | none | UNCITED |
| `docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md:83` | `min_creepage_mm: 8.0` vs `design_value_mm: 10.0` | 8.0 / 10.0 | documents that the gate enforces **10.0**, not the 8.0 IEC requirement | doc | — | DERIVED (context note) |

### 1d. IEC 60950-1 creepage tables (two copies, internally consistent)

| file:line | constant | value set | context | prod/test | citation? | class |
|---|---|---|---|---|---|---|
| `packages/temper-geometry/src/via_clearance.rs:130-137` | `CREEPAGE_TABLE` | {0.4, 2.0, 2.5, 3.0, 5.0, 8.0} at {50,150,300,600,1000,∞} V | IEC 60950-1 arm of `safety_distances` | **PROD** | "IEC 60950-1 clearance/creepage tables" (module header) | CITED (not verified) |
| `packages/temper-drc-rs/src/router_clearance.rs:449-456` | `creepage_table` | same | IEC 60950-1 arm of router gate | **PROD** | "IEC 60950-1 Table 2K/2N, pollution degree 2 / overvoltage category 2" | CITED (not verified) |
| `packages/temper-geometry/src/via_clearance.rs:152-158` | ×1.25 (OVC≥3), ×2.0 (PD≥3) | — | 60950-1 multipliers | **PROD** | standard 60950-1 factors | CITED |

### 1e. IPC-2221 "simplified" bracket table — four synchronized copies, hedged, no recovered source

| file:line | constant | value set | context | prod/test | citation? | class |
|---|---|---|---|---|---|---|
| `packages/temper-geometry/src/creepage_check.rs:230-250` | `required_creepage_bracket` | {0.13,0.25,0.5,0.8,1.25,1.6,3.2,6.4,8.0,12.0} @ {15,30,50,100,150,170,250,300,600,∞} V | production creepage kernel (Rust) | **PROD** | "IPC-2221 (simplified)" | **UNCITED** (hedged "(simplified)"; no recovered IPC-2221 table anywhere in `docs/`) |
| `packages/temper-placer/src/temper_placer/router_v6/creepage_check.py:446-479` | `_calculate_required_creepage` | same | Python twin (one-line delegation) | **PROD** | docstring table, "IPC-2221 (simplified)" | UNCITED |
| `packages/temper-quality-oracle/src/ipc2221.rs:21-32` | `IPC2221_BRACKETS` | same | differential oracle | prod-oracle | "Boundaries sourced from `router_v6/creepage_check.py`" — circular self-reference | UNCITED |
| `packages/temper-placer/tests/router_v6/test_clearance_boundary.py:190-213` | bracket cases | same | boundary tests | test | "IPC-2221 table from creepage_check" | UNCITED (SNAPSHOT) |
| `packages/temper-placer/tests/router_v6/test_creepage_boundary.py:440-475` | `_BRACKET_CASES` | same | boundary tests | test | "IPC-2221 voltage bracket" | UNCITED (SNAPSHOT) |
| `packages/temper-geometry/src/creepage_check.rs:522-535` | bracket asserts | same | Rust tests | test | — | UNCITED (SNAPSHOT) |

### 1f. Creepage multipliers (material group / pollution / internal layer)

| file:line | constant | value | context | prod/test | citation? | class |
|---|---|---|---|---|---|---|
| `packages/temper-design-bundle/src/net_types.rs:248-249` | material group 3 → ×1.4, group 1 → ×0.8 | 1.4 / 0.8 | creepage base scaling | **PROD** | none; recovered Table 17 column ratios are not uniform (e.g. row iv PD2: 2.0/2.8/4.0 → ratios 1.4/1.43) — ×1.4 is a rough fit at best | **FABRICATED-ish** (matches row iv PD2 group II↔III only by coincidence) |
| `packages/temper-design-bundle/src/net_types.rs:229-230` | PD3 → ×1.5, PD1 → ×0.8 | 1.5 / 0.8 | clearance base scaling | **PROD** | none; Table 16 has no PD dimensioning (see clearance.py's own admission) | **FABRICATED-ish** |
| `packages/temper-geometry/src/via_clearance.rs:153,157` | OVC≥3 ×1.25; PD≥3 creepage ×2.0 | 1.25 / 2.0 | 60950-1 | **PROD** | 60950-1 factors | CITED |
| `packages/temper-drc-rs/src/router_clearance.rs:499` | `INTERNAL_LAYER_CREEPAGE_FACTOR = 0.30` | 0.30 | IEC 60664-1 internal-layer reduction | **PROD** | none at site | UNCITED |
| `packages/temper-geometry/src/grid_raster.rs:287` | `base_creepage_mm * 0.30` | 0.30 | grid raster | **PROD** | none | UNCITED |
| `packages/temper-placer/src/temper_placer/router_v6/clearance_engine.py:98` | `INTERNAL_LAYER_CREEPAGE_FACTOR: float = 0.30` | 0.30 | clearance engine | **PROD** | none | UNCITED |
| `packages/temper-placer/src/temper_placer/router_v6/constraints_drc_oracle.py:105` | `INTERNAL_LAYER_CREEPAGE_FACTOR = 0.30` | 0.30 | DRC oracle | prod-oracle | none | UNCITED |
| `packages/temper-placer/src/temper_placer/deterministic/stages/_grid_hv.py:15` | `INTERNAL_LAYER_CREEPAGE_FACTOR: float = 0.30` | 0.30 | stage grid | **PROD** | none | UNCITED |
| `packages/temper-orchestration/src/clearance.rs:490` | `result *= 0.30` (internal, >0.5) | 0.30 | live gate max-then-reduce | **PROD** | none | UNCITED |

> The `0.30` internal-layer factor exists in **5 production copies** (handoff §2 mechanism 1: one fact, many homes). The `> 0.5` threshold it applies under exists in 4 of them.

---

## 2. Clearance

### 2a. IEC 60335 Table 16 / VoltageClass clearance bases

| file:line | constant | value | context | prod/test | citation? | class |
|---|---|---|---|---|---|---|
| `packages/temper-design-bundle/src/net_types.rs:222-227` | SELV 0.5 / LV 1.0 / 120V 1.5 / 240V 3.0 / HV 8.0 | set | `get_clearance_mm` base | **PROD** | docstring "per IEC 60335" (no table) | UNCITED (8.0/3.0/1.5/0.5 are in Table 16's recovered set; 1.0 is not — may be row-based) |
| `packages/temper-drc-rs/src/router_clearance.rs:416-424` | same 5 values | set | router gate clearance arm | **PROD** | "IEC 60335-1 Table 16, pollution degree 2" | CITED (not verified) |
| `packages/temper-design-bundle/src/net_types.rs:230` | `3 => base * 1.5` | 1.5 | PD3 clearance multiplier | **PROD** | none | FABRICATED-ish (Table 16 has a single PD3 footnote, not a column ratio) |

### 2b. HV barrier clearances — 2.0 (derived) vs 6.0 (miscited legacy)

| file:line | constant | value | context | prod/test | citation? | class |
|---|---|---|---|---|---|---|
| `scripts/generate_kicad_dru.py:67` | `HV_INTERNAL_CLEARANCE_MM = 2.0` | 2.0 | DRU same-domain HV floor | **PROD** | full cl. 29.1 chain (1500 V OVC II → Table 16 0.5 → cl. 29.1.3 next-step 1.5 + soldered 0.5 = 2.0) | **DERIVED** |
| `packages/temper-placer/configs/netclass_rules.yaml:42,72,104` | `HighVoltage/HighVoltageTank/HighVoltageSignal clearance: 2.0` | 2.0 | placer classes | **PROD** | `because:` = the DRU chain | DERIVED |
| `packages/temper-placer/src/temper_placer/core/design_rules.py:76,135` | `ACMains clearance=6.0`, `HighVoltage clearance=2.0` | 6.0 / 2.0 | Python classes | **PROD** | ACMains 6.0: none (MISCITED legacy); HV 2.0: comment chain | 6.0 **MISCITED**, 2.0 DERIVED |
| `packages/temper-placer/configs/netclass_rules.yaml:13` | `ACMains.clearance: 6.0` | 6.0 | placer class | **PROD** | `because:` "Table 16 working isolation at 400V" — 6.0 not in Table 16 | **MISCITED** |
| `packages/temper-placer/configs/netclass_rules.yaml:137` | `HighVoltageIsolated.clearance: 6.0` | 6.0 | bootstrap class | **PROD** | "reinforced separation to LV/SELV" — 6.0 not in Table 16 | MISCITED (self-labeled legacy) |
| `packages/temper-placer/configs/netclass_rules.yaml:234-280` | `class_pairs` — **18 rows of `{clearance: 6.0}`** | 6.0 | cross-class separation pairs | **PROD** | `because:` "IEC 60335-1 Table 16 working isolation at 400V — 6.0mm" | **MISCITED** (18 identical homes) |
| `scripts/generate_kicad_dru.py:897` | `(constraint clearance (min 6.0mm))` (RULE 2) | 6.0 | mains<->everything barrier | **PROD** | comment block names Table 16/60664 | UNCITED (6.0 not in Table 16) |
| `scripts/generate_kicad_dru.py:917` | `(min 3.0mm)` (RULE 4) | 3.0 | mains-to-LV basic | **PROD** | — | UNCITED (3.0 in Table 16 set ✓) |
| `scripts/generate_kicad_dru.py:1009,1053,1089` | `(min 2.0mm)` (RULES 4b/4c/5a) | 2.0 | same-domain HV reductions | **PROD** | references HV_INTERNAL_CLEARANCE_MM's derivation | DERIVED |
| `scripts/generate_kicad_dru.py:1163,1179,1192` | `_HV_ISOLATED_CLEARANCE_MM = 2.0` | 2.0 | isolated same-side | **PROD** | none at site | UNCITED (matches 2.0 family) |
| `scripts/generate_kicad_dru.py:126,1519` | `DEFAULT_ROUTING_CLEARANCE_MM = 0.2` | 0.2 | RULE 10 floor | **PROD** | = netclass_rules.yaml `default_clearance_mm` = kicad_pro Default (gate-enforced equality) | DERIVED (config SSOT) |
| `scripts/generate_kicad_dru.py:1492,1501,1509` | 0.2 / 0.15 / 0.1 | LV defaults | GND/Signal/FinePitch rules | **PROD** | none | UNCITED (LV, non-safety) |
| `packages/temper-drc-rs/src/router_clearance.rs:14-19` | `default_clearance` "0.127mm" | 0.127 | comment documenting the floor (5 mil) | **PROD** | none | UNCITED |
| `packages/temper-placer/src/temper_placer/router_v6/_pipeline_core.py:79-103` | (removed) 0.15 | 0.15 | historical A* floor — replaced by 0.2 | prod-history | — | (fixed; documented in comment) |
| `packages/temper-placer/src/temper_placer/router_v6/clearance_check.py:72,131,262` | `min_clearance: float = 0.127` | 0.127 | verify_clearance default | **PROD** | "5mil standard" | UNCITED |

### 2c. Requirements-matrix clearance columns (3.0 / 6.0)

| file:line | constant | value | context | prod/test | citation? | class |
|---|---|---|---|---|---|---|
| `packages/temper-placer/src/temper_placer/requirements/validators/clearance.py:261-288` | `min_clearance_mm`: 3.0 / 6.0 / 3.0 / 6.0 / 6.0 / 0.5 | 3.0/6.0/0.5 | REQ-SAFE-01 matrix | **PROD** | module header cites **Table 17 — a creepage table — for the clearance column**; its own text concedes Table 16 "is keyed to rated impulse voltage… not to pollution degree"; 6.0 not in Table 16's set | **MISCITED** (self-aware) |
| `packages/temper-drc-rs/src/req_safe_01.rs:1096-1099` | matrix rows (6.0, 8.0, 10.0) | 6.0 clearance | Rust port of same matrix | **PROD** | same header | MISCITED (port) |
| `packages/temper-placer/tests/requirements/safety/test_clearance.py:186-225` | `expected_clearance` 3.0 / 6.0 / 0.5 | 3.0/6.0/0.5 | matrix regression pin | test | header: "IEC 60335-1 Table 17 400V row" — Table 17 is creepage | **MISCITED** (SNAPSHOT) |
| `docs/evidence/2026-07-30-creepage-requirement-reconciliation.md` | 3.0 basic / 6.0 reinforced | 3.0/6.0 | reconciliation doc | doc | — | DERIVED (documented basis) |

---

## 3. Ampacity / trace width

### 3a. IPC current-capacity kernels — the 0.048/0.024 vs 0.065 conflict

| file:line | constant | value | context | prod/test | citation? | class |
|---|---|---|---|---|---|---|
| `packages/temper-drc-rs/src/ipc.rs:26,49` | `k = 0.024 / 0.048` | 0.048 ext / 0.024 int | **authoritative** IPC current-capacity kernel (`estimate_trace_current` / `calculate_min_trace_width`) | **PROD** | "IPC-2221/2152" docstring; formula is IPC-2221B's | CITED (IPC-2221B) |
| `packages/temper-drc-rs/src/types/fuse.rs:22,24` | `K_EXTERNAL = 0.048`, `K_INTERNAL = 0.024` | same | fuse sizing | **PROD** | "IPC-2221" | CITED |
| `packages/temper-placer/temper-constraints/src/ipc.rs:117` | `k_ext = 0.065` | **0.065** | CP-SAT ampacity gate (`_ipc2152_forward`) | **PROD** | **none** — handoff §10: "unsourced `k_ext = 0.065`" | **FABRICATED** |
| `packages/temper-placer/temper-constraints/src/ipc.rs:120` | internal → × 0.65 | 0.65 | internal derating in same kernel | **PROD** | none | UNCITED (handoff: neither "IPC-2152" thing is genuinely IPC-2152) |
| `packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py:572` | "derated by a factor of 0.55 per IPC-2152 Section 3" | 0.55 | docstring for the gate's wrapper | **PROD** | cites IPC-2152 Sec 3 | **MISCITED** (no recovered IPC-2152 text) |
| `packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py:583-599` | `_min_width_ipc2152` / `_ipc2152_forward` | — | thin delegation to temper-constraints | **PROD** | — | UNCITED (inherits 0.065) |
| `packages/temper-placer/tests/placer/cp_sat/test_ipc2152_rust_differential.py:24-25` | `k_ext = 0.065` oracle | 0.065 | pinned differential oracle | test | none | FABRICATED (pins the fabricated value) |
| `packages/temper-placer/src/temper_placer/core/ipc2152.py:16,24,34,80` | `temp_rise_c=10.0` defaults | 10.0 °C | IPC-2152 wrappers | **PROD** | none | UNCITED (ΔT default; handoff notes 20/40 chosen figures are *less* conservative than this uncited 10 °C) |
| `docs/hardware/TRACE_WIDTH_CALCULATIONS.md:28` | k = 0.048 / 0.024, ΔT 20 °C traces / 40 °C pours | — | design-basis doc (REQ-ELEC-02) | doc | "IPC-2221B recommendation" (20 °C is commonly cited; 40 °C pour is project choice) | CITED |
| `packages/temper-placer/src/temper_placer/core/ipc2221.py:21-32` | `TRACE_CURRENT_TABLE_1OZ` {0.15→0.7 … 10.0→42.0} | — | **no production caller found** (dead lookup table) | prod-dead | none | UNCITED |

### 3b. Net-current table + defaults

| file:line | constant | value | context | prod/test | citation? | class |
|---|---|---|---|---|---|---|
| `packages/temper-drc-rs/src/ipc.rs:59-74` | `net_currents()` | DC_BUS+ 16, AC_L 10, AC_N 10, SW_NODE 16, GATE 2×, +3V3 0.5, +5V 0.5, +15V 0.2 (A) | W2 expected currents | **PROD** | "W2 R3 requirements" | UNCITED (requirement ref, not standard) |
| `packages/temper-drc-rs/src/ipc.rs:77` | `DEFAULT_SIGNAL_CURRENT = 0.1` | 0.1 A | fallback | **PROD** | none | UNCITED |
| `elec/src/constraints.ato:7-15` | `i_max = 25A` / `15A` / `4A` | 25/15/4 | HighVoltage/ACMains/GateDrive module constraints | **PROD** | none | UNCITED |
| `elec/src/modules.ato:585-593` | 22.5 A RMS design current | 22.5 | tank/bus current basis | **PROD** | "1800 W … derived, not a value read from any part" | DERIVED (documented calc) |

### 3c. Trace widths derived from ampacity

| file:line | constant | value | context | prod/test | citation? | class |
|---|---|---|---|---|---|---|
| `packages/temper-placer/configs/netclass_rules.yaml:43,73` | `HighVoltage/HighVoltageTank trace_width: 5.0` | 5.0 mm | bus/tank width | **PROD** | `because:` IPC-2221B math: 22.5 A RMS, 2 oz ext, 40 °C pour → 4.77 mm required; 15 A/20 °C trace → 4.16 mm | **DERIVED** |
| `packages/temper-placer/src/temper_placer/core/design_rules.py:134,337` | `trace_width=5.0` | 5.0 mm | Python classes | **PROD** | same | DERIVED |
| `packages/temper-placer/configs/netclass_rules.yaml:105` | `HighVoltageSignal trace_width: 0.5` | 0.5 mm | mA-tier manufacturability floor | **PROD** | "TRACE_WIDTH_CALCULATIONS.md S3.8 … 0.5 mm (20 mils) manufacturability" | DERIVED (manufacturability, not ampacity) |

---

## 4. Thermal

### 4a. Firmware interlocks (production) — the uncited OCP/OVP/thermal thresholds

| file:line | constant/expression | value | context | prod/test | citation? | class |
|---|---|---|---|---|---|---|
| `firmware/main/state_machine.c:391` | `read_heatsink_temperature() > 100.0f` | **100.0 °C** | heatsink over-temp → FAULT_OVER_TEMP | **PROD** | none | **UNCITED** (handoff-flagged "100.0 (uncited over-temp threshold)") |
| `firmware/main/state_machine.c:397` | `read_dc_bus_current() > 50.0f` | **50.0 A** | IGBT-short discriminator | **PROD** | comment "IGBT short (>50A)" — no part/standard ref | **UNCITED** |
| `firmware/main/state_machine.c:401` | `read_dc_bus_current() > 35.0f` | **35.0 A** | OCP → FAULT_OVER_CURRENT | **PROD** | none | **UNCITED** (handoff-flagged "35 (uncited OCP threshold)") |
| `firmware/main/state_machine.c:518` | `read_heatsink_temperature() < 70.0f` | 70.0 °C | cooldown exit | **PROD** | none | UNCITED |
| `firmware/config.yaml:17` | `SAFE_IDLE_TEMP = 50.0` | 50.0 °C | IDLE return | **PROD** | none | UNCITED |
| `firmware/config.yaml:25,33` | `MIN_TEMP = 30.0`, `MAX_TEMP = 250.0` | 30 / 250 °C | setpoint bounds | **PROD** | none | UNCITED |
| `firmware/config.yaml:214,222` | `RUNAWAY_MAX_ABSOLUTE_TEMP_C = 300.0`, `RUNAWAY_MAX_TEMP_RISE_RATE_C_PER_S = 15.0` | 300 °C / 15 °C/s | runaway interlock | **PROD** | none | UNCITED |
| `firmware/config.yaml:196` | `fan_max_temp_rise_rate_c_per_s = 5.0` | 5 °C/s | fan guard | **PROD** | none | UNCITED |
| `firmware/config.yaml:107,115,123` | `RTD_SHORT_FAULT_OHM = 10.0`, `RTD_OPEN_FAULT_OHM = 300.0`, `RTD_GROSS_OPEN_DIAGNOSTIC_OHM = 10000.0` | 10/300/10000 Ω | PT100 probe bounds | **PROD** | PT100 characteristics (10 Ω short / 300 Ω open) | CITED (sensor physics; plausible) |

### 4b. Firmware interlock tests (SNAPSHOT pins of the uncited values)

| file:line | value | context | prod/test | citation? | class |
|---|---|---|---|---|---|
| `firmware/test/test_state_machine.c:506,511` | heatsink 105 °C → FAULT_OVER_TEMP | interlock test | test | none | UNCITED (SNAPSHOT) |
| `firmware/test/test_state_machine.c:539-544` | 40 A → FAULT_OVER_CURRENT | interlock test | test | none | UNCITED (SNAPSHOT) |
| `firmware/test/test_state_machine.c:576,580-608` | >50 A → IGBT_SHORT; 35 A does **not** | boundary test | test | none | UNCITED (SNAPSHOT) |

### 4c. Placer/thermal-model values

| file:line | constant | value | context | prod/test | citation? | class |
|---|---|---|---|---|---|---|
| `packages/temper-placer/src/temper_placer/metrics/physics.py:325` | `thermal_margin_c = 150.0 - max_tj` | 150.0 °C | junction margin | **PROD** | "# 150C is typical shutdown" — no part/standard | **UNCITED** |
| `packages/temper-placer/src/temper_placer/metrics/physics.py:282` | `ambient_temp_c: float = 40.0` | 40 °C | thermal scorer ambient | **PROD** | none | UNCITED |
| `packages/temper-thermal/src/junction_temp.rs` (tests 136-154) | Rjc 0.6 / Rch 0.25 / Rha 1.0 | — | TO-247 thermal-chain test params | test | none | UNCITED (typical values, uncited) |
| `docs/hardware/TRACE_WIDTH_CALCULATIONS.md:13` | Ambient 60 °C | 60 °C | "worst-case kitchen environment" | doc | none | UNCITED |
| `elec/src/constraints.ato:105-115` | `igbt_max_temp = 423.15K` (150 °C), `igbt_derate_temp = 398.15K` (125 °C), `inductor_max_temp = 398.15K`, `mcu_max_temp = 358.15K` (85 °C), `cap_max_temp = 378.15K` (105 °C) | 150/125/125/85/105 °C | schematic thermal constraints | **PROD** | none | UNCITED (typical component class limits, plausible) |

> Cross-check: `150.0 - max_tj` in the placer and `423.15 K = 150 °C` in the .ato
> agree with the firmware's *heatsink* 100 °C being a different (heatsink, not
> junction) quantity — but none of the three sites cites a part datasheet.

---

## 5. OCP / OVP

| file:line | constant | value | context | prod/test | citation? | class |
|---|---|---|---|---|---|---|
| `firmware/main/state_machine.c:401` | `read_dc_bus_current() > 35.0f` | **35.0 A** | software OCP trip | **PROD** | none | **UNCITED** |
| `firmware/main/state_machine.c:397` | `read_dc_bus_current() > 50.0f` | 50.0 A | IGBT-short trip | **PROD** | none | **UNCITED** |
| `firmware/test/test_state_machine.c:539-608` | 40/35/50 A pins | — | interlock boundary tests | test | none | UNCITED (SNAPSHOT) |
| `elec/src/modules.ato:88-90` | `assert q_high.current_rating >= constraints.i_max` (25 A) | 25 A | IGBT selection assert | **PROD** | constraint SSOT (constraints.ato) | CITED (internal chain) |
| `elec/src/constraints.ato:7-8` | `v_max = 400V`, `i_max = 25A` | 400 V / 25 A | HighVoltageConstraints | **PROD** | none | UNCITED |

> **No hardware comparator OCP threshold constant found in `elec/`.** The 35 A /
> 50 A software thresholds in `state_machine.c` are the only OCP values; the
> CT-based comparator path is wired as a ZCD timing input (handoff §2), not as a
> numeric threshold. The 35/50 A values have no citation in the repo.

---

## 6. Pollution degree / material group / CTI

| file:line | constant | value | context | prod/test | citation? | class |
|---|---|---|---|---|---|---|
| `packages/temper-placer/src/temper_placer/router_v6/clearance_engine.py:152-154` | `pollution_degree: int = 2`, `material_group: str = "IIIa"`, `overvoltage_category: int = 2` | 2 / IIIa / 2 | multi-standard engine defaults | **PROD** | none at site (engine header cites the five standards) | UNCITED |
| `packages/temper-orchestration/src/clearance.rs:395-397` | same defaults (2, "IIIa", 2) | same | Rust port | **PROD** | — | UNCITED |
| `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:87` | **Material Group IIIb, FR4 CTI 175-249V** | IIIb/175–249 | spec sheet | doc | "cl. 29.2" implied — contradicts recovered cl. 29.2 (IIIb = 100 < CTI < 175; **175–249 is IIIa**; IEC 60335 merges the two) | **MISCITED** (internal contradiction) |
| `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:86` | **Overvoltage Category III** | OVC III | spec sheet | doc | "Equipment connected to mains distribution" — IEC 60335-1 cl. 29.1 puts appliances in **OVC II** (handoff §9; corrected on `cert-lab-package`) | **MISCITED** (wrong category) |
| `packages/temper-design-bundle/src/net_types.rs:237-251` | material_group 1/2/3, ×0.8/1.0/1.4 | — | creepage kernel | **PROD** | docstring "1=best, 2=typical FR4, 3=worst CTI" | UNCITED |
| `packages/temper-placer/src/temper_placer/requirements/validators/clearance.py:216-228` | Material Group IIIa/IIIb column, PD2 | — | matrix derivation | **PROD** | recovered Table 17 | DERIVED |
| `docs/evidence/2026-08-11-pd2-decision-record.md` | PD2 selected | — | owner decision | doc | IEC 60335-2-6 cl. 29.2 Addition + enclosure prerequisite | DERIVED |
| `scripts/check_pd2_compartment_evidence.py` | PD2 vs PD3 constants read from DRU | 8.0/12.6 | compartment-evidence gate (currently exit 3 — evidence file missing) | **PROD** (gate) | — | DERIVED |

---

## 7. Voltage class / mains voltage

| file:line | constant | value | context | prod/test | citation? | class |
|---|---|---|---|---|---|---|
| `packages/temper-design-bundle/src/net_types.rs:138-139` | `MAINS_120V = 3`, `MAINS_240V = 4` | 120/240 | voltage-class enum | **PROD** | none | UNCITED |
| `packages/temper-placer/src/temper_placer/router_v6/clearance_check.py:732-736` | `voltage_ratings.get(net, 230.0)` | **230.0 V** | HV-net default governing voltage | **PROD** | none | UNCITED (a fourth mains value — 120/120-240/240/230 per handoff §2.1) |
| `packages/temper-placer/configs/netclass_rules.yaml:18` | `ACMains.voltage_v: 325.0` | 325.0 V | = 230 Vrms × √2 | **PROD** | none | DERIVED (peak of 230 Vrms) |
| `elec/src/constraints.ato:11,44` | `ACMains v_max = 135V` | 135 V | 120 V + margin | **PROD** | "120V + margin" | DERIVED |
| `packages/temper-placer/src/temper_placer/core/design_rules.py:139,342,380,393` | `voltage_v = 400.0 / 923.7 / 400.0 / 20.0` | — | class voltages | **PROD** | Tank 923.7 measured (ngspice) | DERIVED (Tank), UNCITED (others) |
| `packages/temper-orchestration/src/derivation_stage.rs:169-173` | code 1 → MAINS_120V, 2 → MAINS_240V | — | config-code mapping | **PROD** | — | UNCITED |

---

## 8. Summary

### Totals (counted mechanically from the tables above — 124 site rows)

| Metric | Count |
|---|---|
| **Total sites catalogued** | **124** |
| — production (incl. gates/oracle/aliases/schematics) | 98 |
| — test | 14 |
| — doc/oracle/other (incl. 1 documented-fixed historical site) | 12 |
| **FABRICATED** (no source anywhere; incl. pinned oracles of fabricated values) | **10** |
| **MISCITED** (carries a citation that does not support the number) | **12** |
| **CITED** (citation present, not checked for correctness) | 15 |
| **UNCITED** (no citation, may be correct) | 57 |
| **DERIVED** (traces to a recovered table or a documented measured value) | 29 |
| documented-fixed (historical, resolved) | 1 |
| **Untraceable-or-worse combined (FABRICATED + MISCITED)** | **22** |
| Unique numeric values catalogued (0.13…14.0, 0.024…0.065, 5.0…300.0, K/Kelvin thresholds) | ~45 |
| **One fact, many homes** clusters | 9 (14.0×7, 6.0-creepage×9, 6.0-clearance×22, 0.30×5, 8.0-barrier×7, IPC-2221 bracket×6, 60950 tables×2, 0.048/0.024 vs 0.065×2, 35/50 A OCP×3) |

Roughly **1 in 5 safety-constant sites (22/124) is untraceable or mis-cited**, and
**57/124 carry no citation at all**. Only 29/124 trace to a recovered standard
table or a measured value.

### Most concerning findings

1. **`14.0` mm creepage base — FABRICATED, 7 homes, and it feeds the live router clearance gate.**
   `router_clearance.rs:433` (production) returns 14.0 mm for the `HighVoltage`
   class with the label "IEC 60335-1 Table 17" — the recovered Table 17 tops out
   at 12.5 and has no 14.0. The differential oracle, the PBT "independent"
   tables, and two further test pins all replicate it. PR #1198's 19.6 = 14.0 × 1.4
   inherits this as its base. **This is the single highest-value fix target.**
2. **`0.065` k-value in `temper-constraints/src/ipc.rs:117` — FABRICATED, live in the CP-SAT ampacity gate.**
   The authoritative kernel (`temper-drc-rs/src/ipc.rs`) uses IPC-2221B's
   0.048/0.024; the CP-SAT gate's `_ipc2152_forward` uses an unsourced 0.065 with
   a ×0.65 internal derating and a "0.55 per IPC-2152 Sec 3" claim in its docstring.
   Two calculators, two answers, one of them authoritative-cited.
3. **Firmware interlocks: 100 °C heatsink / 35 A OCP / 50 A IGBT-short — all UNCITED,**
   and the firmware tests pin them (SNAPSHOT). For a mains appliance these are
   safety-critical; none has a part-datasheet or standards citation anywhere in
   `firmware/`.
4. **OVC III (spec) vs OVC II (governing).** `HIGH_VOLTAGE_CLEARANCE_SPEC.md:86`
   claims OVC III; IEC 60335-1 cl. 29.1 makes appliances OVC II (handoff §9).
   The same spec's "IIIb, CTI 175–249" contradicts recovered cl. 29.2 (175–249 is
   IIIa). Both corrected on `cert-lab-package` but not on `main`.
5. **`6.0` mm clearance/creepage: 22 clearance + 9 creepage homes, zero recovered-table support.**
   The 18-row `class_pairs` block all cite "Table 16 working isolation at 400V"
   for a 6.0 mm figure in no recovered table; the requirements matrix's own header
   cites Table 17 (creepage) for its clearance column and its own body concedes the
   mismatch. The 6.3/12.6/8.0/10.0 PD2/PD3 family by contrast is fully
   traceable — the model to copy.
6. **IPC-2221 bracket table: 6 synchronized copies, hedged "(simplified)", no recovered
   IPC-2221 source in `docs/`.** Even the oracle's comment is circular
   ("sourced from creepage_check.py").
7. **The `1.0` FUNCTIONAL creepage pin** (`validators/clearance.py:287`, mirrored in
   `test_clearance.py:223`) is pinned below the table's own 1.1 (PD2) / 1.8 (PD3)
   with the concession in the same file — a known-low SNAPSHOT of a safety value.

### Recommended migration shape (for the typed `SafetyValue` work)

- Start from the **DERIVED** family (Table 17/18 rows, DRU constants, measured
  570.5 Vrms/923.7 V, IPC-2221B 0.048/0.024) as the provenance-carrying skeleton.
- The **14.0** family needs either a real source (IEC 60664-1 Annex L / 60335
  full text — both unobtainable per handoff) or an explicit
  `SafetyValue(provenance=UNKNOWN, conservative=True)` type rather than a bare f64.
- Deduplicate the 8 one-fact-many-homes clusters into single typed constants with
  a drift gate — the existing `scripts/check_creepage_clearance_drift.py`
  (written, tested, CI-invocation commented out) is the natural enforcement point.

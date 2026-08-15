# Safety Assertion Audit — Resumed (2026-08-15)

**Branch:** `audit/safety-assertions-2026-08-15` (off `origin/main` @ `8f21d2725`)
**Base for all line numbers:** `origin/main` @ `8f21d2725` (`fix(drc): word-boundary net classification in router_clearance (resolves #1175)`)
**Continuation of:** the safety-assertion audit begun 2026-08-14 (handoff §3; ~40 sites / 12 files, 6 MISCITED / 9 SNAPSHOT / 3 DERIVED, forks killed by spend limit before chunk A was finished).

This document (a) verifies the prior audit's headline findings in-tree so they have
file:line evidence, (b) resumes the audit on the four surfaces the handoff names as
untouched — HV/LV separation, ampacity/PD/material group, thermal, firmware safety
contract — and (c) answers work-queue item 3: does `test_tank_creepage.py` catch the
tank↔bus 3.2×–5.0× creepage shortfall, or mask it?

## Classification conventions (unchanged from the prior audit)

- **MISCITED** — carries a standards citation that does not support its number. Worst
  category: manufactures confidence and resists correction.
- **SNAPSHOT** — expected value exists only in test/code (or an uncited doc); detects
  regression, not correctness.
- **DERIVED** — traces to a recovered standards table or spec requirement (repo's
  recovered tables: IEC 60335-1 Table 15, Table 16, Table 17, Table 18 in
  `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §3 and
  `docs/evidence/2026-08-12-hv-hv-creepage-determination.md` §3.1; nothing from
  IPC-2221/2152 or IEC 60664-1 is recovered in-repo).

---

## Part 0 — Work-queue item 3: `test_tank_creepage.py` vs the tank↔bus shortfall

**Finding under test:** `docs/evidence/2026-08-12-hv-hv-creepage-determination.md:431-433`
— `tank.c_tank1-p2` ↔ bus rails: **2.0 mm provided vs 6.3 mm (PD2) / 10.0 mm (PD3)
required**, a 3.2×–5.0× shortfall, PD3 governing as built.

**Verdict: the test does not catch the shortfall, and structurally cannot. It is an
honest, documented-limitation SNAPSHOT that gives no signal on the specific pair the
evidence doc found short.**

Reasoning, in four independent layers:

1. **The pair is not enumerable by the test.** The bus rails (`+170V_BUS`,
   `DC_BUS_RTN`) are *nets*, not components. `tank_creepage_pairs()` enumerates
   (tank-ref × other-HV-*component*-ref) pairs only
   (`tank_creepage.py:256-273`); a net with no refdes can never appear in `pairs`,
   so `check_tank_creepage_separation()` can never be asked to measure the tank↔bus
   gap. The test's own pair-count pin (`test_tank_creepage.py:83`,
   `len(pairs) == 4 * 42`) would pass unchanged with the tank↔bus gap at 2.0 mm.

2. **The metric is component bounding-box, not copper.** `check_tank_creepage_separation`
   computes Chebyshev box-to-box gaps (`tank_creepage.py:453-456`). The finding is a
   copper-to-copper (pad-to-track/pour) distance. The module's own docstring says
   exactly this: it "is silent — correctly, not by omission — on pad-to-routed-copper
   creepage, which is a routing-stage property" (`tank_creepage.py:66-72`), and the
   production caller's comment repeats it
   (`cli/__init__.py:810-815`: "this is a COMPONENT-BOX bound … it says nothing about
   pad-to-routed-track creepage"). The DRC headline pair (C25 pad 2 vs a
   `discharge.k_dis1-nc` track, 2.2656 mm) is itself a pad-to-track pair the test
   explicitly asserts it does *not* reject at component granularity
   (`test_c25_k2_pair_is_NOT_rejected_at_component_granularity`,
   `test_tank_creepage.py:122-148`).

3. **The pass signal the test does emit is about a different shortfall.** 
   `test_rejects_the_committed_placement_at_pd3` asserts ≥1 violation with worst
   `< 1.0 mm` (`test_tank_creepage.py:107-120`) — that fires on component-body pairs
   (C25↔RV1, C27↔U5 at 0.4 mm box gap, per the module docstring `tank_creepage.py:74-80`).
   The tank↔bus 2.0 mm gap is invisible to it. The test would be green on a board whose
   only defect was the tank↔bus shortfall.

4. **Liveness is weak.** The suite runs in the `extended-cpsat` job's
   "Run cp-sat suite (fast remainder)" step, which is (a) `continue-on-error: true`,
   (b) in a job the workflow's own comment describes as "Masked test step … cannot
   fail any build — not in required-checks.json's required_contexts"
   (`python-tests.yml:3047-3055`), and (c) `if: schedule || workflow_dispatch` —
   nightly only, **never on PRs** (`python-tests.yml:3057-3059`). Confirmed
   `extended-cpsat` is absent from `.github/required-checks.json` `required_contexts`.

**What the test does do right (for the record):** its two constants are the
repo's only DERIVED creepage figures found in this audit so far:
`HV_TANK_CREEPAGE_PD2_MM = 6.3` / `PD3 = 10.0` (`test_tank_creepage.py:51-54`;
`tank_creepage.py:173-178`) match the recovered Table 18 row >500–≤800 V, material
group IIIa/IIIb cells exactly (6.3 / 10.0), with a two-way OCR cross-check recorded in
the evidence doc (`2026-08-12-hv-hv-creepage-determination.md:226-246`). `570.5 Vrms`
is a carried-forward measured quantity (`2026-08-12-hv-clearance-adequacy.md` Sec 3.2,
ngspice worst OCP-01-passing corner), not an invented one. The module and its test are
honest about what they cannot see — the gap is that the *only* live test touching the
tank node never checks the pair that matters.

**Related finding N1 (genesis of the "2.0 mm provided"):** the 2.0 mm is not a
measurement artifact; it is the enforced same-class `HighVoltage` clearance in the
DRU rules and netclass SSOT, whose derivation lives at
`scripts/generate_kicad_dru.py:63-67` (`HV_INTERNAL_CLEARANCE_MM = 2.0`). The
derivation's arithmetic chain is **DERIVED** from recovered primary text — Table 15
(120 V, OVC II → 1 500 V impulse), Table 16 (1 500 V → 0.5 mm basic), clause 29.1.3
(reinforced = next higher step 2 500 V → 1.5 mm), clause 29.1 (+0.5 mm soldering
adder) — but **it is a reinforced mains↔PELV clearance**, derived and documented as
"Fail-closed reinforced clearance for the mains<->PELV barrier", then applied as the
same-domain HighVoltage↔HighVoltage internal figure the tank↔bus pair falls under.
Two application errors:

- **Insulation-class mismatch.** A reinforced mains↔PELV barrier figure is not a
  same-domain HV↔HV functional figure. For the tank↔bus boundary the governing
  requirement is Table 18/17 functional/basic creepage at >500–800 V: 6.3 / 10.0 mm —
  the 2026-08-12 evidence doc's exact finding.
- **Voltage basis is 120 V only.** The chain starts from `v_ac_nominal = 120V`
  (`elec/src/main.ato:52`, asserted 100–130 V). Table 15's rated-voltage row shifts at
  150 V; at 240 V nominal (OVC II) the chain gives 2 500 V impulse → 1.5 mm basic →
  4 000 V reinforced → 3.0 mm + 0.5 = 3.5 mm. The 2.0 mm figure is valid only for a
  ≤150 V-rated appliance. (Handoff mechanism 1: mains voltage lives at four values
  across the repo — 120 / 120-240 / 240 / 230.)

The SSOT itself flags the same-class question as open — `design_rules.py:104-106`:
"Whether 2.0 is itself IEC-adequate for the same-domain, no-creepage-backstop
HighVoltage-to-HighVoltage case is NOT resolved by this fix — see the evidence doc's
open-question section." The 2026-08-12 evidence answers it (short by 3.2×–5.0×); the
SSOT and the DRU rules still enforce the short value.

---

## Part 1 — Verified headline findings from the prior audit (file:line evidence)

| # | Site | Asserted value | Claimed citation | Class | Evidence |
|---|------|---------------|------------------|-------|----------|
| V1 | `packages/temper-placer/tests/core/test_net_types_pbt.py:62-80` | HIGH_VOLTAGE creepage base **14.0** | "Independent IEC 60335 reference tables" | **MISCITED** | `_CREEPAGE_BASE["HIGH_VOLTAGE"] = 14.0` is byte-identical to the implementation `temper-design-bundle/src/net_types.rs:240-251` (same factors 0.8/1.0/1.4). Both created in the **same commit** `1f85f4ad1b` (2026-08-01, "migrate net_types to temper-design-bundle (#560)" — stat shows `net_types.rs` +907 and `test_net_types_pbt.py` +490 together). Recovered Table 17 (`2026-07-28-creepage-determination-brainstorm.md:286-294`, CITED-PRIMARY) contains **no 14.0 at any row**; maximum 12.5. |
| V2 | `packages/temper-placer/tests/router_v6/test_clearance_boundary.py:607-611` | required_clearance **14.0** at 400 V | "most-conservative across all standards (IEC 60950-1, 60335-1, 60664-1, 62368-1, IPC-2221)" | **MISCITED** | Value and citation written in the **same commit** `1e99a151be` (2026-06-25, "unified multi-standard clearance engine (#25)"): the engine `clearance_engine.py` takes `max()` over candidates whose 60335-1 term is the very `VoltageClass` creepage 14.0 from V1 — the five-standard citation is attached to one untraceable number. The other named standards contribute no 14.0 (IPC-2221 bracket max is 12.0 at 601–1000 V in this repo's own copies). |
| V3 | `packages/temper-placer/tests/requirements/safety/test_clearance.py:160-172` (matrix rows 3.0/4.0/6.0 and 6.0/8.0/10.0) | clearance **3.0 basic / 6.0 reinforced** | Comment cites "IEC 60335-1 Table 17 … 400V row" | **MISCITED** (clearance column) | Table 17 is the *creepage* table. Table 16's recovered value set is {0.5, 1.5, 3.0, 5.5, 8.0, 11.0} — 6.0 is not in it. The *creepage* column (4.0 / 8.0) is correctly DERIVED (Table 17 row iv, >250–≤400 V, IIIa/IIIb, PD2 basic 4.0; reinforced 2× = 8.0 per clause 29.2.3). |
| V4 | `test_clearance.py:224-228` (FUNCTIONAL row 0.5/1.0/2.0) | `min_creepage_mm == 1.0` (LV↔LV functional) | presented as "IEC 60335-2-6 requirements matrix" | **MISCITED / pins a known-low value** | The SSOT itself concedes in-tree: `validators/clearance.py:245-249` — "Table 18 row i, ≤50V, Material Group IIIa/IIIb reads 1.1mm PD2 / 1.8mm PD3, vs this row's current 1.0mm, already slightly under even the PD2 figure" (flagged, not corrected). `HIGH_VOLTAGE_CLEARANCE_SPEC.md:207-214` repeats the flag. The test pins the known-short value. |
| V5 | IPC-2221 bracket table, four synchronized copies: `test_creepage_boundary.py:440-475` (values 0.13/0.25/0.5/0.8/1.25/1.6/3.2/6.4/8.0/12.0), `temper-geometry/src/creepage_check.rs:230-250` (+ test `:522-535`), `router_v6/creepage_check.py:446-479` | brackets 0.13→12.0 mm | "IPC-2221 (simplified)" | **SNAPSHOT/MISCITED** | Hedged in-source as "(simplified)" (`creepage_check.py:447`; `creepage_check.rs:226-227` "simplified IPC-2221 voltage→creepage table"). **No recovered IPC-2221 text exists anywhere in `docs/`** — grep of `docs/` finds no IPC-2221 table. Four copies synchronized by differential tests; nothing external anchors the values. |
| V6 | `validators/clearance.py:230-236` (comment) + matrix rows `:260-285` | clearance 3.0/6.0, design 6.0/10.0 | "already meet or exceed Table 16's 400V-row minimum" | **MISCITED** | 6.0 is not in Table 16's recovered value set. The same comment admits Table 16 "is keyed to rated impulse voltage (via Table 15's overvoltage-category lookup), not to pollution degree or material group" — yet the PD2/PD3 discussion is what moves creepage, and the "Design Value" column the comment declares "not used as a basis for anything in this table" is still present with those very numbers in `design_value_mm`. |

*(The prior audit's counts — 6 MISCITED / 9 SNAPSHOT / 3 DERIVED across ~40 sites —
are consistent with the above; V1–V6 are the headline members re-verified here.)*

---

## Part 2 — NEW: HV/LV separation surface

| # | Site | Asserted value | Claimed citation | Class | Evidence / reasoning |
|---|------|---------------|------------------|-------|---------------------|
| S1 | `temper-drc-rs/src/constraints.rs:289` (`default_hv_clearance() = 10.0`); mirrored `_constraint_types/config.py:226` (`Field(default=10.0)`), `validation/drc_types.py:147` | **10.0 mm** HV↔LV separation | Rust: none. Python ancestor (`8b73368ab`, original check): "Safety requirements (IEC 60335) often demand large clearances (e.g. 10mm)" | **MISCITED** | The original docstring's "IEC 60335 … e.g. 10mm" is a vague hedged citation, no clause/table/row. The repo's own spec for the governing boundaries says 8.0 mm PD2 / 12.6 mm PD3 reinforced (`HIGH_VOLTAGE_CLEARANCE_SPEC.md:174,201-204`) — 10.0 sits between PD2 and PD3 with no derivation. The rule is live: registered in `create_default_registry` (`rules/mod.rs:256`), runs via `temper_drc_rs.run_drc` (`lib.rs:216-248`), invoked from `validation/drc_oracle.py:251`. Net classes declare `safety_category` (`design_rules.py:85,144,155,179,202,213,237,249`), so the check is non-vacuous when the engine runs. |
| S2 | `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:86` (REQ-ELEC-04 §3.2) | **OVC III** | "Equipment connected to mains distribution" | **MISCITED (stale ground truth)** | Handoff §9 records the correction: IEC 60335-1 cl. 29.1 (CITED-PRIMARY, `2026-07-28-creepage-determination-brainstorm.md:219-220`) — "Appliances are in overvoltage category II." Under OVC III essentially the whole `HighVoltage` netclass fails. Spec corrected only on `cert-lab-package`; main still carries III. |
| S3 | `HIGH_VOLTAGE_CLEARANCE_SPEC.md:87` | Material Group **IIIb**, "FR4 CTI 175-249V" | (same table) | **MISCITED** | Internally inconsistent with the recovered clause 29.2 material-group definitions (`2026-07-28-...brainstorm.md:296-298`, CITED-PRIMARY): IIIa = 175<CTI<400, IIIb = 100<CTI<175. CTI 175–249 is **IIIa**, not IIIb. (And IEC 60335-1 merges IIIa+IIIb into one column, so the label error is value-neutral *here* — but the same error is load-bearing in PR #1198's `REQ-ELEC-04 §3.2` citation, handoff §3.) |
| S4 | `HIGH_VOLTAGE_CLEARANCE_SPEC.md:129-139` (§4.1) | clearance table incl. design values 1.5/2.0/2.5/3.0/5.0/6.0/10.0 | "Based on IEC 60664-1 Table F.2 for Overvoltage Category III, Pollution Degree 2" | **MISCITED** | Basis table is for the wrong OVC (see S2); the "Design Value" column (10.0 at 600 V etc.) is an uncited invented round-number column — the same column the validators' comment disclaims. No recovered IEC 60664-1 text exists in-repo to check Table F.2 against. |
| S5 | `temper-drc-rs/src/rules/safety/hv_lv_separation.rs:204-334` (tests) | fixture threshold 3.0 mm | none (self-consistency) | **SNAPSHOT** | Ten tests pin the rule's own geometry/classification behavior (edge-gap math, keyword fallback, declared categories). They detect regression in the *mechanism*, not correctness of the *threshold* — the threshold's only source is S1's untraceable 10.0 default. |
| S5b | `docs/specs/NET_CLASS_SPECIFICATION.md:128` (HighVoltageIsolated) | "Clearance: 6.0mm (240 mil) to low-voltage domains" | none | **SNAPSHOT (stale)** | A fifth netclass-value source that disagrees with the current SSOT (`design_rules.py` HighVoltage clearance=2.0) — drift example of handoff mechanism 1/5. |

---

## Part 3 — NEW: ampacity / PD / material-group surface

| # | Site | Asserted value | Claimed citation | Class | Evidence / reasoning |
|---|------|---------------|------------------|-------|---------------------|
| S6 | `temper-drc-rs/src/ipc.rs:36-51` (`calculate_min_trace_width`) | docstring: "using **IPC-2152**" | IPC-2152 | **MISCITED** | The function is the *inverted IPC-2221 formula* (`k·ΔT^0.44·A^0.725`, k=0.048/0.024) — the same kernel as `estimate_trace_current` beside it. IPC-2152 is a chart-based standard with no such closed form. Handoff §10: "neither thing named 'IPC-2152' is genuinely IPC-2152" — this file's own docstring is the second instance. The forward k constants (0.048/0.024) are the published IPC-2221B values; no recovered IPC-2221 text is in-repo to pin them to (V5's caveat applies), but the *formula* is at least the standard's. |
| S7 | `placer/cp_sat/gates.py:372` (`StackupGate._DEFAULT_TEMP_RISE_C = 10.0`) | ΔT **10 °C** | none (uncited) | **SNAPSHOT** | The live routing ampacity gate's rise is uncited and *more conservative* than `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` §1's "Max Temp Rise (traces) **20°C** … (pours) **40°C**" whose claimed citation is "IPC-2221B recommendation" — no recovered IPC-2221 text supports a specific recommended rise (the IPC-2221 ampacity charts are commonly read at 10 °C; 20 °C as "the recommendation" is unverifiable in-repo). Three rise figures in one repo for the same physics. Handoff §10 flags the 20/40 choice as *less* conservative than the 10 °C it replaced — worth an owner sanity check for an enclosed forced-air appliance. |
| S8 | `docs/hardware/TRACE_WIDTH_CALCULATIONS.md:41-57` (§3.1/3.2) | DC bus / switch node **22 A peak** | none | **SNAPSHOT + rms/peak confusion** | Conflicts with R3's 16 A (`ipc.rs:61-68`, `gates.py:359-369`) and with `elec/src/modules.ato:585-593`'s 22.5 A rms (first-harmonic solve; ngspice cross-check 20.7 A rms). The repo's own sim gives **22.66 A rms / 32.22 A peak** tank current at nominal (`docs/evidence/2026-08-07-zvs-margin-sweep.md:318`) — i.e. "22 A peak" in the doc matches the sim's *rms* value, consistent with an rms/peak mislabel. Four current figures for the same nets: 16 A (R3), 22 A peak (doc), 22.5 A rms (ato), 15 A (fuse/trace tier). Handoff mechanism 1, live. |
| S9 | `ipc.rs:55-79` `net_currents()`; `gates.py:359-371` `_DEFAULT_NET_CURRENTS` | DC_BUS+/SW_NODE 16.0, AC_L/N 10.0, GATE 2.0, +3V3/+5V 0.5, +15V 0.2, default 0.1 | "W2 R3 requirements" | **DERIVED (to internal requirement — caveat)** | Traces to R3 in `docs/brainstorms/2026-07-08-4-layer-functional-stackup-requirements.md:49-57`, which is itself *uncited design intent* (no external basis given for any current). So: traceable to a spec requirement (DERIVED per convention), but the requirement's own numbers have no external anchor — the caveat belongs in the same row. |
| S10 | `design_rules.py:139` (`HighVoltage.creepage_mm = 6.0`) | **6.0 mm** netclass creepage | none | **SNAPSHOT (dormant)** | Below even the PD2 minimum (6.3 mm) for the >500–800 V band the tank node sits in (recovered Table 17/18). Not consumed by `scripts/generate_kicad_dru.py` (no `creepage_mm` reference) or the placer — a dormant field, but it is the netclass SSOT's declared creepage and nothing flags that it contradicts the 6.3/10.0 analysis. |
| S11 | `scripts/generate_kicad_dru.py:63-67` `HV_INTERNAL_CLEARANCE_MM = 2.0` | **2.0 mm** | Table 15/16 + cl. 29.1/29.1.3 chain | **DERIVED arithmetic, MISCITED application** | See Part 0, finding N1. Chain itself is fully cited to recovered primary text; the application (reinforced mains↔PELV figure reused as same-domain HV↔HV internal clearance, 120 V-only basis) is not supported. This is the *source* of the "2.0 mm provided" in the tank↔bus finding, and it is also the figure `HighVoltage.clearance` (`design_rules.py:135`) and DRU RULE 4/4c (`generate_kicad_dru.py:1009,1053,1089`) enforce. |
| S12 | `packages/temper-placer/temper-constraints/src/ipc.rs:111-121` (`ipc2152_forward`, k_ext = **0.065**, internal ×0.65) | k_ext 0.065 / 65% internal | "IPC-2152 forward … internal layers derated to 65%" | **MISCITED (live, under-conservative)** | **This is the kernel the LIVE ampacity gate calls.** `gates.py:488-491` → `_min_width_ipc2152` → `temper_constraints.min_width_ipc2152_py` (`gates.py:580`) → `temper-constraints/src/ipc.rs` k_ext=0.065. The authoritative kernel (`temper-drc-rs/src/ipc.rs:20`, IPC-2221B k=0.048/0.024) gives **+35% less current capacity** at the same geometry — the live gate is *less conservative* than the repo's own authoritative calculator. 0.065 is unsourced (handoff §10). The wrapper's own docstrings contradict each other on the internal derate: `gates.py:568` says "derated by a factor of 0.55 per IPC-2152 Section 3" while `gates.py:591-592` and the kernel say 65% — two "IPC-2152 Section 3" claims, two numbers, no recovered IPC-2152 text. Third mislabeled "IPC-2152" in the repo. |
| S13 | `gates.py:489` (`copper_oz=1.0` hardcoded) | **1 oz** assumed for every layer | none | **SNAPSHOT (over-provisioned internals)** | The 4-layer stackup SSOT is outer 1 oz / inner **0.5 oz** (`2026-07-08-004` plan: "Outer copper 1oz (35µm), inner copper 0.5oz (17µm)"); `TRACE_WIDTH_CALCULATIONS.md:27-28` claims outer 2 oz / inner 1 oz — a third stackup claim. Assuming 1 oz for 0.5 oz inner layers doubles the ampacity the gate credits internal traces — an under-conservative bias in the same direction as S12. |
| S14 | `temper-drc-rs/src/rules/mod.rs:257` (`CreepageCheck::new(6.0)`) | **6.0 mm** "minimum isolation width" | none | **SNAPSHOT (dead code)** | The check measures component *package width* against 6.0 — not creepage — and is dead as documented (handoff §9): no netclass declares `safety_category: "iso"` (verified: `design_rules.py` declares only AC/HV/LV). The 6.0 exists only in the registration; no citation, no consumer. `IsolationCheck` (`isolation.rs`) is zone-structural with no numeric constants of its own. |

---

## Part 4 — NEW: thermal surface

| # | Site | Asserted value | Claimed citation | Class | Evidence / reasoning |
|---|------|---------------|------------------|-------|---------------------|
| T1 | `temper-thermal/src/thermal_edges.rs:201` | **Rjc=0.6, Rch=0.25, Rha=1.0 K/W, copper_area=0.0** for every component | none | **SNAPSHOT** | Every component on the board gets the same 1.85 K/W total and zero copper benefit (so the `copper_benefit` term in `junction_temp.rs:94` is never exercised in the live path). No per-device datasheet values; an IGBT's real Rjc (~0.35 K/W) and a µC's (~10s of K/W) are both flattened to the same number. The model is a heuristic with no citation and no datasheet trace. |
| T2 | `metrics/physics.py:325` | `thermal_margin_c = 150.0 - max_tj` | "150C is typical shutdown" | **SNAPSHOT** | "Typical" is not a citation. Three conflicting thermal limits exist in-repo: 150 °C (this margin), 100 °C (firmware `OVER_TEMP_THRESHOLD`, below), 85/120 °C (heatsink/coil, `FUNCTIONAL_TEST_CRITERIA.md:69-70`). Handoff mechanism 1: one quantity, three homes, no shared source. |
| T3 | `metrics/physics.py:282` | `ambient_temp_c: float = 40.0` | none | **SNAPSHOT** | `TRACE_WIDTH_CALCULATIONS.md:23` asserts "Ambient Temperature **60 °C** Worst-case kitchen environment". A margin computed at 40 °C ambient is up to 20 °C optimistic vs the repo's own worst-case claim. |
| T4 | `_constraint_types/thermal.py:69-84` `_RJC_PACKAGE_LOOKUP` (TO-247: 0.6, TO-220: 1.0, DPAK: 2.0, …) | per-package Rjc | none | **SNAPSHOT** | "Typical" package values in **three synchronized copies** (`thermal.py`, `io/config_loader.py`, `temper-design-bundle/src/config_loader.rs` — the file's own comment). No datasheet anchor for any entry; TO-247 0.6 K/W is not the value of the actual IGBT part in the BOM. | 

---

## Part 5 — NEW: firmware safety contract surface

| # | Site | Asserted value | Claimed citation | Class | Evidence / reasoning |
|---|------|---------------|------------------|-------|---------------------|
| F1 | `firmware/components/safety/safety.c:42` | `OVER_TEMP_THRESHOLD 100.0f /* °C */` | none | **SNAPSHOT** | Introduced in the initial sync commit `04fe05232` (2025-12-14); blame confirms no later edit. No standard citation anywhere in firmware (only IEC mention in the whole tree: `test_common.h:267`, an IEC 60751 RTD linearization note). Conflicts with `docs/FUNCTIONAL_TEST_CRITERIA.md:69-70` (heatsink NTC 85 °C / coil NTC 120 °C): the firmware's single 100 °C matches neither documented trip point. |
| F2 | `safety.c:43` | `OVER_CURRENT_THRESHOLD 35.0f /* Amps */` | none | **SNAPSHOT + internal contradiction** | Same origin (04fe05232). `docs/FUNCTIONAL_TEST_CRITERIA.md:48-49` documents primary OCP trip at **45–55 A** (setting 50 A peak) and secondary at 55–65 A; `elec/src/modules.ato:1618-1619` dimensions OCP-01 to **49.9 A**. 35 A matches neither the hardware comparator (~50 A) nor any acceptance band. The firmware software guard trips 15 A early vs the documented OCP — either the guard is redundant noise or the docs are wrong; nothing reconciles them. |
| F3 | `firmware/test/test_safety.c:33-58,105-121,315-324` | 101 °C→trip, exactly 100 °C→no trip; 36 A→trip, exactly 35 A→no trip | none (self) | **SNAPSHOT** | Tests pin the firmware's own `#define`s — they detect regression, not correctness. A change of 100→105 °C in both places stays green. |
| F4 | `docs/FUNCTIONAL_TEST_CRITERIA.md:48-70` | OCP 45–55 A / 55–65 A; OVP 390–410 V; thermal 85/120 °C; UVLO 12.0/2.9 V | none | **SNAPSHOT (uncited acceptance criteria)** | No standards citation for any band; the "Basis" note (lines 52-55) clarifies *peak vs RMS* semantics only, not the origin of the numbers. 12.0 V gate-drive UVLO and 2.9 V logic UVLO are plausible datasheet-derived values but are not linked to any datasheet in-repo. |
| F5 | `firmware/test/test_fault_list_generated.c:44-47` | `FAULT_COUNT == 14` | generated manifest | **SNAPSHOT (self-referential)** | Pins the count of the generated fault enum — internal consistency between generator and test, no external requirement anchor. (Not a numeric safety distance; included for completeness.) |

---

## Part 6 — Cross-cutting new findings

- **N1** — `generate_kicad_dru.py:63-67` / `design_rules.py:135`: the enforced 2.0 mm same-class HV clearance is a reinforced mains↔PELV figure derived on a 120 V-only basis, applied to the wrong boundary and the wrong voltage class (Part 0).
- **N2** — The netclass SSOT's own comment (`design_rules.py:104-106`) declares the same-class HV↔HV adequacy question *unresolved*, while the 2026-08-12 evidence answers it (3.2×–5.0× short) and the SSOT + DRU rules still enforce the short figure. SSOT and evidence are not reconciled.
- **N3** — Four current figures for the bus/tank nets (16 A R3 / 22 A peak doc / 22.5 A rms ato / 15 A fuse-trace), one of which ("22 A peak") is internally inconsistent with the repo's own sim (22.66 A *rms* at nominal). No reconciliation exists.
- **N4** — Mains-voltage basis drift (120 V asserted in `main.ato:52`; 120–240/230 in other docs). Safety-relevant because Table 15's rated-voltage row shifts at 150 V: the 2.0 mm clearance chain collapses at 240 V (would be 3.5 mm).
- **N5** — `TRACE_WIDTH_CALCULATIONS.md:62` skin-depth analysis at **38 kHz**; the tank's legal PLL range is **44–50 kHz** (handoff §9; `zvs-margin-sweep`). Stale-frequency analysis feeding a width recommendation.
- **N6 (positive)** — The genuinely DERIVED sites found in this pass: tank constants 6.3/10.0 (recovered Table 18), matrix creepage 4.0/8.0 (recovered Table 17 row iv + cl. 29.2.3 doubling), the 2.0 mm arithmetic chain itself (Table 15/16 + cl. 29.1/29.1.3 — misapplied, not mis-derived), and per-net currents (R3 requirement). Three of the four prior DERIVED classifications plus these — still roughly one in seven, consistent with the handoff's headline.
- **N7 (live-path amplification of S12)** — The ampacity gate's three stacked biases are all in the *under-conservative* direction vs the authoritative kernel: k_ext 0.065 vs 0.048 (+35% capacity), copper 1 oz assumed for 0.5 oz inner layers (×2 capacity for internals), and ΔT 10 °C being the only conservative choice. Any trace that passes the live gate at these settings would fail the repo's own authoritative IPC-2221B kernel. This is the "live path is not where it looks" mechanism (handoff §2 item 2) applied to ampacity: the authoritative calculator in `temper-drc-rs` is *not* what the routing gate calls — the nested `temper-constraints` crate is.

## Coverage status

Files covered in this pass (40 files + 4 more examined via git history): `test_tank_creepage.py`, `tank_creepage.py`,
`_encoder_solve.py`, `cli/__init__.py`, `hv_lv_separation.rs`, `constraints.rs`,
`rules/mod.rs`, `config.py`, `drc_types.py`, `ipc.rs` (+`ipc_pyo3.rs`), `gates.py`,
`physics.py`, `thermal_edges.rs`, `junction_temp.rs`, `_constraint_types/thermal.py`,
`safety.c`, `test_safety.c`, `test_fault_list_generated.c`, `design_rules.py`,
`generate_kicad_dru.py`, `clearance.py` (validator), `test_clearance.py`,
`test_clearance_boundary.py`, `test_creepage_boundary.py`, `creepage_check.rs`,
`creepage_check.py`, `check_isolation_keepout.py`, `isolation_constants.py`,
`net_types.rs`, `test_net_types_pbt.py`, `TRACE_WIDTH_CALCULATIONS.md`,
`FUNCTIONAL_TEST_CRITERIA.md`, `NET_CLASS_SPECIFICATION.md`,
`HIGH_VOLTAGE_CLEARANCE_SPEC.md`, `isolation.py` (test), `drc_oracle.py`, `lib.rs`,
`temper-constraints/src/ipc.rs`, `rules/safety/creepage.rs`, `rules/safety/isolation.rs`.
Examined via `git show` for archaeology:
`hv_lv_separation.py` (deleted Python ancestor), `clearance_engine.py` (#25),
`net_types.py` oracle side of `1f85f4ad1b`, `safety.c` at `04fe05232`.

Still uncovered (known): the remainder of the original chunk A (files never enumerated
in a surviving artifact — the prior audit's report did not land), plus:
`temper-design-bundle/src/hv_lv_partition.rs` and its five test files,
`_constraint_types/safety.py`, `validators/isolation.py`,
`test_clearance_copper.py`, `test_creepage_spec_row_form.py`,
`core/ipc2152.py` (no production caller — latent, per handoff §9), and the
`drc_ratchet`/`ci_check_drc` ceiling machinery (R27 territory, out of scope here).
*(The nested `packages/temper-placer/temper-constraints/src/ipc.rs` flagged in handoff
§10 was covered in this pass — S12/S13; `rules/safety/creepage.rs` & `isolation.rs`
were covered in this pass — S14, no numeric sites in `isolation.rs`.)*

## Bottom line

1. **Item 3 (tank test):** the test is honest about its box-granularity blind spot but
   structurally incapable of catching the tank↔bus shortfall, runs nightly in a masked,
   non-required job, and its one real signal (≥1 box violation < 1.0 mm) fires on a
   *different* shortfall. The gap it cannot see is enforced by a clearance value
   (2.0 mm) whose derivation is a misapplied reinforced-barrier figure on a 120 V-only
   basis.
2. **Item 1 (audit):** 24 new sites classified across the four surfaces (Parts 2–5):
   **6 MISCITED** (S1, S2, S3, S4, S6, S12), **16 SNAPSHOT** (S5, S5b, S7, S8, S10, S13,
   S14, T1–T4, F1–F5), **1 DERIVED** (S9), plus one dual-classified site (S11/N1:
   arithmetic chain DERIVED from recovered primary text, *application* MISCITED).
   The four surfaces are
   materially *worse* than the already-audited clearance/creepage tests: no recovered
   primary text anchors the HV/LV 10.0 default, the OVC/CTI spec rows are wrong on
   main, the thermal model's constants are flat heuristics, and the firmware safety
   thresholds (100 °C / 35 A) contradict the repo's own acceptance criteria
   (85/120 °C, 45–55 A) with no reconciliation and no external anchor.
3. Nothing in this audit was fixed — per the operating rules, the audit reports; the
   fixes (re-derived values, spec corrections, reconciliation of the current tables)
   are owner decisions. The two values that *would* fix the tank↔bus pair — 6.3/10.0 mm
   — are already DERIVED and in-tree; the remaining question is whether to enforce them
   at the DRU/SSOT level for same-class HV pairs.

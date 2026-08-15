<!-- provenance: commit=8f21d2725 dirty=false -->

# Verification of the `14.0` mm HIGH_VOLTAGE creepage base — not obtainable from any recovered standards text

Date: 2026-08-15. Worktree `/tmp/opencode/agent-creepage-base`, branch
`investigate/creepage-base-14-verification`, checked out at `origin/main`
(`8f21d2725`). Follow-up to handoff §3 item 2 ("Verify the `14.0` base or
establish it is not obtainable") and to PR #1198's `19.6 = 14.0 × 1.4`.

**Verdict up front.** `14.0` mm is **not traceable to any recovered standards
table at any row, pollution degree, or material group applicable to this
board**, and it is **not derivable** from the recovered tables by any
documented arithmetic. It is a fabricated constant wearing a "Table 17"
citation. Strictly, `14.0` IS a genuine cell of IEC 60335-1's creepage tables
— but only at working voltages **>1 000 V** with **material group II**, rows
this board's HIGH_VOLTAGE nets (120–570.5 Vrms, generic FR-4 group IIIa/IIIb)
cannot occupy. **PR #1198's `19.6` is therefore not supportable**: an
untraceable base times an unsourced multiplier that the governing standard
does not define, applied to classes whose bases are already group-IIIa/IIIb
values. The repo already carries the correct numbers (8.0 mm PD2 / 12.6 mm
PD3 reinforced for the ≤400 V barrier; 6.3 mm PD2 / 10.0 mm PD3 functional
for the >500–800 V tank band).

---

## 1. What was verified

| Claim (handoff §3) | Result |
|---|---|
| `test_net_types_pbt.py:62-80` presents `14.0` under "Independent IEC 60335 reference tables" | **Confirmed fabricated label.** The test's `_CREEPAGE_BASE`/`_CREEPAGE_FACTOR` are byte-identical to the implementation, created in the same commit `1f85f4ad1` (the Wave-4 migration). The "reference" and the code are the same text. |
| Recovered Table 17 contains no 14.0; max 12.5 | **Confirmed for the transcribed rows (≤1 000 V).** The full Table 17 continues past 1 000 V identical to Table 18 (§3), where 14.0 exists at inapplicable rows. |
| `test_clearance_boundary.py:607-611` asserts 14.0 citing five standards | **Confirmed.** Value and citation written in the same commit `1e99a151b` (2026-06-25, "unified multi-standard clearance engine"). At 400 V, none of the five standards' recovered tables gives 14.0 — only the engine's own untraceable 60335-1 base does. |
| PR #1198: 19.6 = 14.0 × 1.4, authority REQ-ELEC-04 §3.2 | **Confirmed mechanism** (branch `fix/drc-router-clearance-material-group` @ `5228dbce7`): `base * creepage_multiplier()` where `IiiaOrB → 1.4`, base `HIGH_VOLTAGE = 14.0`. The cited spec's own creepage table (§5.1) gives 8.0/12.6 — **never 19.6 or 14.0**. |
| REQ-ELEC-04 §3.2 "IIIb, CTI 175-249V" internally inconsistent | **Confirmed.** Clause 29.2: IIIa 175<CTI<400, IIIb 100<CTI<175. "CTI 175-249" is **IIIa**, and Table 17 **merges** IIIa/IIIb into one column — the escalation the fix rests on is not a distinction the standard makes. |

---

## 2. Git archaeology — where 14.0 came from

`git log --all -S "14.0"` across the whole repo, all refs:

1. **`418fab757` (2026-01-07) — the origin.** The very first commit of
   `temper_placer/core/net_types.py` introduced, with **no derivation, no
   clause, no row, no source**:

   ```python
   # IEC 60335-1 Table 17 (basic insulation, material group II)
   creepages = {
       VoltageClass.SELV: 0.5,
       VoltageClass.LOW_VOLTAGE: 1.6,
       VoltageClass.MAINS_120V: 2.5,
       VoltageClass.MAINS_240V: 5.0,  # 6.3mm for reinforced
       VoltageClass.HIGH_VOLTAGE: 14.0,
   }
   ```

   The commit message ("Encodes IEC 60335 clearance/creepage requirements
   into types") cites no table row. No earlier commit anywhere in the repo
   carries a 14.0 creepage value (checked the pre-existing router
   creepage lineage: `fff8bab76`, `8dfcc9451`, `25fe7f408`, `4fe6f3ce0`,
   `b0c6b61e7` — their 14.0s are IPC-2221 ampacity for 3.0 mm traces, ~14 A,
   and test coordinates, unrelated).

2. **`1e99a151b` (2026-06-25)** — the unified clearance engine consumes the
   60335-1 `VoltageClass` values as one candidate among five and takes the
   max; at 400 V the max is the engine's own 14.0. `test_clearance_boundary.py`
   updated to expect 14.0, with a five-standard citation added in the same
   commit.

3. **`278662e80` (2026-07-26)** — the Rust port (`router_clearance.rs`, the
   always-on Stage-5.7 gate) embeds the table as literals, `14.0` included.
   Its own docstring confirms the live magnitudes: "only 3 distinct
   required-clearance values occur in practice (0.127mm default, 4.2mm
   internal-HV, 14.0mm external-HV)".

4. **`1f85f4ad1` (Wave-4)** — migration copies the table into
   `temper-design-bundle/src/net_types.rs`, the pinned oracle
   `_net_types_py_oracle.py`, and the "independent reference" pbt test —
   three copies of the same unsourced constant, one of them mislabelled
   "Independent".

So the entire 14.0 lineage (test, oracle, Rust, router gate, clearance
engine) descends from one unsourced constant written on 2026-01-07.

---

## 3. Every recovered standards table, checked for 14.0

| Table | Source / provenance | 14.0 present? | Applicable row for this board? |
|---|---|---|---|
| IEC 60335-1 **Table 17** (basic creepage), rows i–vii transcribed | `docs/evidence/2026-07-28-creepage-determination-brainstorm.md:286-294`, CITED-PRIMARY (IS 302-1:2008), cross-checked cell-for-cell against Broadcom's IEC 60664-1 reproduction | **No** — value set {0.2 … 12.5} | — |
| IEC 60335-1 **Table 17**, rows viii–xviii (implied by §3.2 of the 2026-08-12 doc: identical to Table 18 from >500 V to the bottom) | `docs/evidence/2026-08-12-hv-hv-creepage-determination.md:195-207` | **Yes, two cells** — see below | **No** |
| IEC 60335-1 **Table 18** (functional creepage), transcribed in full | `docs/evidence/2026-08-12-hv-hv-creepage-determination.md:188-207`, CITED-PRIMARY | **Yes, two cells** — see below | **No** |
| IEC 60664-1 (via Broadcom §4.5 reproduction) | `2026-07-28-creepage-determination-brainstorm.md:308-324`, CITED-SECONDARY | No — max 10.0 reinforced at 500 V | — |
| IEC 60950-1 (repo's tables, Table 2K/2N) | `packages/temper-geometry/src/via_clearance.rs:122-136`, `router_clearance.rs:441-456` | No — max creepage 8.0 at >1 000 V | — |
| IPC-2221 (simplified) | `router_v6/creepage_check.py:446-479` / `creepage_check.rs` | No — max 12.0 at 601–1 000 V | — |
| IEC 62368-1 | Only via `design_rule_creepage` = config `creepage_mm` (6.0 for HighVoltage) | No | — |

**The two genuine 14.0 cells, and why neither can apply:**

Table 18 (hence Table 17 above 500 V), Material Group II column:

| Working voltage (V) | PD1 | PD2 II | PD3 II |
|---|---|---|---|
| >1 000 and ≤1 250 | 3.2 | 7.1 | **14.0** |
| >2 000 and ≤2 500 | 7.5 | **14.0** | 28.0 |

Both 14.0 cells require **working voltage > 1 000 V** AND **material group II
(400 < CTI < 600)**. This board's HIGH_VOLTAGE nets run at 120 V mains, 170–
400 V bus, and 570.5 Vrms (923.7 V peak) resonant tank
(`docs/evidence/2026-08-12-hv-clearance-adequacy.md`, carried forward) —
nothing above 1 000 V. The substrate is generic FR-4 with CTI unstated
(repo-wide assumption: group IIIa/IIIb;
`2026-07-28-creepage-determination-brainstorm.md:585-622`). A 14.0 mm figure
for this board would require a 1 kV+ working voltage and a CTI ≥ 400 laminate
to be named at the same time — neither exists.

**Conclusion (a): `14.0` is not traceable to any standard at any row
applicable to this board.** It is either lifted from a row/group combination
that cannot apply here, or fabricated; either way it is unsupportable. This is
a "not obtainable" verdict for the *value as used*: the repo's recovered
materials do not produce 14.0 for this board's HIGH_VOLTAGE class.

---

## 4. Could 14.0 be derived? — no documented derivation exists

Candidate derivations, all rejected:

- **2 × 7.0 (reinforced from a 7.0 basic):** no 7.0 exists in any recovered
  table cell.
- **10.0 × 1.4:** 10.0 is a real Table 18/17 cell (>500–800 V, PD3,
  IIIa/IIIb) and ×1.4 = 14.0 exactly. But **no document anywhere derives
  14.0 this way**, and the 1.4 multiplier itself has no recovered-standards
  basis (below).
- **Any Table 16 (clearance) relationship:** Table 16's value set is
  {0.5, 1.5, 3.0, 5.5, 8.0, 11.0} — no 14.0.

**The base table is internally incoherent even as a "Table 17" reading.** The
comment claims "material group II", but the bases are a grab-bag:

| Base | Claimed | Recovered-table cell it actually matches |
|---|---|---|
| SELV 0.5 | Table 17 II | **No Table 17/18 cell** — it is a Table 16 *clearance* value |
| LOW_VOLTAGE 1.6 | Table 17 II | **Table 18** >250–400 V, PD2, group **I** (1.6) |
| MAINS_120V 2.5 | Table 17 II | **Table 17** >125–250 V, PD2, group **IIIa/IIIb** (2.5) — a IIIa/IIIb value, not II |
| MAINS_240V 5.0 | Table 17 II | **Table 17** >400–500 V, PD2, group **IIIa/IIIb** (5.0) — a IIIa/IIIb value, not II |
| HIGH_VOLTAGE 14.0 | Table 17 II | **No cell at any row/group this board can occupy** |

So the "group II base" comment is false for two of five entries, and the
table mixes basic-creepage cells, a functional-creepage cell, a clearance
cell, and an unsourced number. The `base × {0.8, 1.0, 1.4}` structure itself
is not how Table 17 works: material group selects a **column**, and the
column ratios vary by row. Measured from the recovered table:

- II → IIIa/IIIb ratio at PD2: 1.39 (>125–250), 1.43 (>250–400), 1.39
  (>400–500), **1.40** (>500–800), 1.43 (>800–1 000) — "1.4" matches exactly
  only the >500–800 row.
- II → IIIa/IIIb ratio at **PD3**: 1.13 (>250–400), **1.11** (>500–800) —
  applying 1.4 at PD3 over-escalates by ~25 %.
- I → II ratio at PD2: 0.71–0.72 — "0.8" matches no row.

---

## 5. What the correct figure is (if 14.0 is replaced)

The governing inputs are established in-repo: working voltages 120–570.5
Vrms (§3), material group IIIa/IIIb (generic FR-4, and Table 17 merges the
two), pollution degree PD2 as the owner-selected production target with **PD3
as the as-built fallback** (`docs/evidence/2026-08-11-pd2-decision-record.md`).
From the recovered tables, per actual net voltage:

| Working voltage | Table | Row | PD2 basic | PD2 reinforced (cl. 29.2.3: ×2) | PD3 basic | PD3 reinforced |
|---|---|---|---:|---:|---:|---:|
| 120 V mains | T17 | >50–125 | 1.5 | 3.0 | 2.4 | 4.8 |
| ≤400 V bus | T17 | >250–400 | 4.0 | **8.0** | 6.3 | **12.6** |
| 570.5 V tank | T18 = T17 | >500–800 | 6.3 | 12.6 | 10.0 | 20.0 |

For the HIGH_VOLTAGE netclass as a reinforced barrier at ≤400 V, PD2, group
IIIa/IIIb: **8.0 mm** — which the repo already carries in three independent
places, all derived from the recovered table:

- `temper_placer/core/isolation_constants.py:45` — `MIN_BARRIER_WIDTH_MM =
  8.0` ("REINFORCED creepage, pollution degree 2, material group IIIb, ≤400V
  working voltage");
- `requirements/validators/clearance.py:265-269` — `IEC60335_REQUIREMENTS`
  REINFORCED min_creepage 8.0 (basic 4.0);
- `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:174` — §5.1's own Table 17
  transcription: 8.0 (PD2) / 12.6 (PD3).

And the placer-feasibility config (`netclass_rules.yaml`) already keys creepage
by voltage: `HighVoltage` 6.0 @ 400 V and `HighVoltageTank` 6.3 @ >500–800 V
PD2, the latter citing Table 18 directly. **The structurally correct answer is
not a single replacement number**: the `VoltageClass.get_creepage_mm` model
(a single base per class, scaled by a material-group multiplier) is a
fabricated abstraction over a table indexed by (working voltage × PD ×
material group). The class spans three Table 17 rows; no single base can be
right. The fix direction the repo already proves out is per-class, voltage-
keyed config plus the DRU emission, and the `VoltageClass` creepage path
should be keyed like the real table (or retired from the live path). Note the
PD2-vs-PD3 question remains open (handoff §7.C); under PD3-as-built the
correct figures are 12.6 mm (bus reinforced) / 10.0 mm (tank functional) —
every prior PD2-based number in this document is the best case, not the
current case.

---

## 6. PR #1198's 19.6 — status

`19.6 = 14.0 × 1.4` fails on four independent grounds:

1. **Untraceable base.** 14.0 is not a recovered-table value for this board
   (§3). Escalating an unsourced number does not make it sourced; it makes
   the gate enforce a larger unsourced number.
2. **The multiplier is not the standard's structure.** The standard selects
   a material-group *column*; it defines no 1.4 multiplier anywhere. 1.4 is
   net_types.rs's own unsourced factor, matching exactly one Table 17 row
   (>500–800 PD2) and over-escalating at PD3 by ~25 % (§4).
3. **Double-counting for two of the five classes.** `Mains120V` (2.5) and
   `Mains240V` (5.0) bases are already Table 17 **IIIa/IIIb** cells. PR
   #1198 multiplies *every* class by the IIIa/IIIb factor on the premise
   that the base table was "material group 2 (typical FR4)" — for those two
   classes the group penalty is applied twice, and the "group II" comment
   the premise rests on is false for them.
4. **The cited authority contradicts itself and the standard.** REQ-ELEC-04
   §3.2's "Material Group IIIb, FR4 CTI 175-249V": clause 29.2 defines IIIb
   as 100 < CTI < 175, so CTI 175–249 is **IIIa**; and Table 17 **merges**
   IIIa and IIIb into one column, so the IIIa-vs-IIIb distinction the fix's
   rationale leans on changes no number. REQ-ELEC-04's own creepage table
   (§5.1) — the same spec — gives 8.0 (PD2) / 12.6 (PD3), **nowhere 19.6**.

Fair caveat: 19.6 is *conservative* — larger than any recovered requirement.
An over-conservative gate does not endanger safety; it manufactures false
violations, blocks routability (the exact problem Stage 5.7 exists to catch),
and entrenches an unsourced number as "the design's declared requirement".
Neither "accept 19.6" nor "revert to 14.0" is the right move: the right move
is to replace the `VoltageClass` creepage path with the recovered-table
lookup keyed on (working voltage, PD, material group) — values the repo
already computes correctly elsewhere (§5). PR #1198's *method* (exhaustive
sweep, conservative-only divergence proof, separate re-pin commit) remains
exemplary; its *input* was never verified, exactly as the handoff suspected.

---

## 7. Sources

- Recovered Table 17: `docs/evidence/2026-07-28-creepage-determination-brainstorm.md:281-324`
  (CITED-PRIMARY, IS 302-1:2008 = IEC 60335-1 Ed. 4.2-era, OCR'd; cell-for-cell
  cross-checked against Broadcom's IEC 60664-1 reproduction).
- Recovered Table 18 + clause 29.2.4: `docs/evidence/2026-08-12-hv-hv-creepage-determination.md`
  (CITED-PRIMARY, same IS 302-1:2008 artifact, sha256 recorded in its header).
- Material groups, cl. 29.2: `2026-07-28-creepage-determination-brainstorm.md:299-306`.
- The 14.0 lineage: commits `418fab757`, `1e99a151b`, `278662e80`, `1f85f4ad1`
  (verified by `git log --all -S "14.0"` / `git show`).
- PR #1198: branch `fix/drc-router-clearance-material-group` @ `5228dbce7`
  (`router_clearance.rs` diff: `base * BOARD_MATERIAL_GROUP.creepage_multiplier()`).
- REQ-ELEC-04: `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:81-90` (§3.2),
  `:169-183` (§5.1).
- Board working voltages: `docs/evidence/2026-08-12-hv-clearance-adequacy.md`
  (570.5 Vrms tank, carried forward, not re-measured).

## 8. Compliance with the task's hard rules

- Nothing in `pcb/temper.kicad_pcb` was opened for writing.
- No `git stash` used. No other worktree touched.
- No standards value was invented or reconstructed: every number above is
  quoted from a recovered table or computed as an explicit ratio of two
  recovered cells, and where the answer is "not obtainable", that is the
  answer.
- Commit lineage for this document: see git log on
  `investigate/creepage-base-14-verification`.

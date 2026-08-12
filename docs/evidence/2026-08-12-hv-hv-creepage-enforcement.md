<!-- provenance: commit=80a1df053bdc04e68127edd746722b890ba300c9 dirty=false (branch feat/hv-hv-creepage-enforcement, based on origin/main @ 1a7365587). pcb/temper.kicad_pcb sha256=6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64 -- UNCHANGED by this work and identical to the hash recorded in power_pcb_dataset/drc_ceiling.json's provenance and in docs/evidence/2026-08-12-hv-clearance-adequacy.md; the board file was never written. kicad-cli 10.0.5 (/home/bennet/.local/opt/kicad-10.0.5/root/usr/bin/kicad-cli, `kicad-cli version` = 10.0.5), measured live, MaximumThreads=1 pinned via a scratch KICAD_CONFIG_HOME per temper_placer.validation._drc_api._single_threaded_kicad_env. Every DRC number below was measured on a scratch copy of pcb/temper.kicad_pcb + .kicad_pro + the regenerated .kicad_dru outside the repo. Sample counts stated per table. Working voltages are NOT re-derived here: they are carried forward unchanged from docs/evidence/2026-08-12-hv-clearance-adequacy.md (PR #1080, branch commit de7d3a113), and the Table 18 determination from docs/evidence/2026-08-12-hv-hv-creepage-determination.md (PR #1081, branch commit fb61b01f3). Both are read first-hand this session; neither is on main. -->

# The HV↔HV creepage requirement is now enforced. It rejects two real pairs on the committed board — including the tank node at 2.27mm against a 6.3mm requirement, 2.8× short. It does **not** breach the DRC ceiling, but it consumes 100% of the remaining headroom, and that is the thing that needs a decision.

**Verdict, up front.**

1. **The gap was structural, not a missing value.** `NetClassRules.creepage_mm` already
   existed and `HighVoltage` already carried `6.0`
   (`packages/temper-placer/src/temper_placer/core/design_rules.py:104`). It was dead
   weight: **no rule anywhere consumed it**, and all three creepage constraints the DRU
   generator emits require one side to be non-HV. So the fix is a new *rule*, not a new
   *value*. Section 2.

2. **Scoped to one net: `tank.c_tank1-p2`.** It is the only net on this board measured
   above 500 Vrms against any other net (570.5 Vrms vs the bus rails). Every other
   `HighVoltage` net is at most 400 V and sits two Table 18 rows lower. A new
   `HighVoltageTank` class carries it. Section 1.

3. **6.3mm, from IEC 60335-1 Table 18** (functional insulation, cl. 29.2.4), band
   >500 and ≤800 V, material group IIIa/IIIb, PD2. Carried forward from PR #1081, not
   re-derived.

4. **It reaches exactly one enforcement path: kicad-cli.** The new
   `(rule "HighVoltageTank functional creepage")` in `pcb/temper.kicad_dru` is the whole
   of the enforcement. **No Rust safety kernel enforces this figure, and this document
   does not claim one does** — `creepage_mm` is marshalled into `BoardState` and then
   read by nothing. Section 3 shows the code.

5. **It binds, proven three ways.** On the real board it rejects 2 pairs and the count
   tracks the constraint value monotonically (0 → 2 → 4 as the figure goes
   0.001 → 6.3 → 20mm). On a constructed fixture it rejects 5.0mm and accepts 7.0mm.
   Section 5.

6. **Ceiling: not breached, but saturated.** creepage 182–184 → **185–186** against a
   ceiling of 186; errors 1262–1264 → **1265–1266** against `error_ceiling` 1266. The
   gate compares with `>`, so both pass — at exactly zero margin. **The ceiling was not
   raised and no figure was weakened to fit under it.** But the repo's own
   single-sample-safety invariant now fails on the measured band, which is a real
   problem with a real fix. Sections 6 and 7.

---

## 1. Scope: which nets, and why only one

### 1.1 The measured per-net picture

`docs/evidence/2026-08-12-hv-clearance-adequacy.md` §1 enumerates the **14 `HighVoltage`
nets** on the committed board and §2.3/§3.2 measures the working voltage of each pair
against the repo's own committed ngspice deck
(`simulation/harness/nets/zvs_margin_sweep.cir`), at the worst OCP-01-passing corner
(L −10%, C −10%, 48 kHz). Carried forward unchanged:

| Pair | Worst OCP-passing working voltage | Table 18 band | PD2 functional creepage |
|---|---:|---|---:|
| `tank.c_tank1-p2` ↔ `+170V_BUS` / `DC_BUS_RTN` | **570.5 Vrms** | **vi** (>500–800) | **6.3mm** |
| `tank.c_tank1-p2` ↔ `PWR_RTN` | 544.6 Vrms | vi | 6.3mm |
| `tank.c_tank1-p2` ↔ `SW_NODE` | 411.5 Vrms | v (>400–500) | 4.0mm |
| `SW_NODE` ↔ rails | 240.2 Vrms | iii | 2.0mm |
| `+170V_BUS` ↔ `DC_BUS_RTN` | 400 V | iv (>250–400) | 3.2mm |
| `w1_1`, `w1_2`, `a`, `zcd`, `power_in.ntc-no`, `discharge.k_dis*-nc`, `+15V_LS`, `hb.power_loop.q_high-g`, `tank-out` | ≤400 V | iv or lower | ≤3.2mm |

**One net crosses 500 Vrms: `tank.c_tank1-p2`.** It is the resonant tank's cap↔coil
junction, the only node in the power stage that is not rail-clamped — it carries the
inductive drop `I·ωL_loaded` on top of a rail offset. `SW_NODE` measures ±173 V at every
operating point because the half-bridge clamps it; `tank-out` sits a current-transformer
primary away from `PWR_RTN`.

### 1.2 Why a class split and not a raise of `HighVoltage`

This is the decision PR #1080 §5.1 recommended, and the reason is arithmetic, not
preference: **`HighVoltage` spans two Table 18 rows.** Row iv (3.2mm) for the bus, relay
contacts and rectifier-side nets; row vi (6.3mm) for the tank node. One class cannot
carry one correct creepage figure for both, and applying 6.3mm to all 14 nets would
impose a 2× over-requirement on the 13 nets that are packed tightest.

That is not hypothetical on this board. PR #1080 §5 measured the alternative directly:
raising the `HighVoltage` netclass wholesale costs **+5 clearance violations at the
smallest step (3.0mm)** and breaches the ceiling immediately, because it is the bus and
relay nets — not the tank node — that are tight. And
`docs/evidence/2026-08-11-pd2-decision-record.md:19-30` records what happens when this
project applies an unnecessarily strict global figure: PD3/12.6mm was measured **not
established feasible** — 196 violating pad-pairs, at least one isolator UNSAT even after
part substitution.

**This is scoping to the measurement, not scoping to reduce the count.** The count is a
consequence; §5's threshold sweep shows the rule would report 4 violations at 8.3mm and
13 at the PD3 figure of 10.0mm if the pollution-degree decision moved.

### 1.3 What was NOT changed

- **`pcb/temper.kicad_pcb` was not modified.** Verified: sha256 unchanged at
  `6928b7c8…`, identical to `drc_ceiling.json`'s recorded input hash.
- **No clearance value moved.** `HighVoltageTank.clearance = 2.0`, identical to
  `HighVoltage`'s. PR #1080 settled that 2.0mm is adequate for every `HighVoltage` pair
  including this one; PR #1061 / `2026-08-12-netclass-param-reconciliation.md` settled
  the netclass parameters. Measured confirmation: **clearance 386/386 in every one of
  the 30 baseline + 39 post-change samples**, unchanged.
- **`power_pcb_dataset/drc_ceiling.json` was not touched.** No ceiling raised, no
  `Ceiling-Approval:` trailer, no re-measurement committed. §7 proposes what should
  happen instead.

---

## 2. What was actually missing: a rule, not a value

The task's second question — is HV↔HV creepage unenforced because no rule *exists*, or
because a rule exists and no netclass *carries* a value? — has a specific answer, and
they need different fixes.

**The value existed and was inert.** `NetClassRules` has had a `creepage_mm` field since
the model was generated (`packages/temper-placer/src/temper_placer/core/netclass_rules_gen.py:49`),
and `HighVoltage` carried `creepage_mm=6.0` at `design_rules.py:104`, mirrored in
`packages/temper-placer/configs/netclass_rules.yaml:35`. That 6.0 has a debunked
citation (`netclass_rules.yaml`'s own note: *"IEC 60335-1 Table 16 working isolation at
400V"* — Table 16 has no 400 V row and no 6.0mm value) and, more to the point, **nothing
reads it to enforce a distance**. §3 traces that.

**The rule did not exist.** `scripts/generate_kicad_dru.py` emits `creepage` constraints
in exactly three rules, and every one requires one side to be non-HV:

| Rule | Condition (from the generated `pcb/temper.kicad_dru`, pre-change) | creepage |
|---|---|---:|
| `AC Mains to LV` | `A=='ACMains' && B!='ACMains' && B!='HighVoltage' && B!='GateDriveHV'` | 8.0mm |
| `HV to LV` | `A=='HighVoltage' && B!='HighVoltage' && B!='ACMains' && B!='GateDriveHV' && B!='HighVoltageIsolated'` | 8.0mm |
| `HighVoltageIsolated to LV` | `A=='HighVoltageIsolated' && B!='HighVoltageIsolated' && B!='HighVoltage' && B!='ACMains' && B!='GateDriveHV'` | 8.0mm |

The only HV-internal rule, `HV internal same footprint`, declares **clearance only** and
is further gated on `A.Reference == B.Reference`.

**Independently confirmed empirically.** The 0.001mm probe in §5.2 is the direct test: a
rule scoped to exactly the HV↔HV tank pairs, set to a distance nothing can violate,
reports 0 — and the same rule at 20mm reports 4. Before this change there was no such
rule to set.

**KiCad netclasses cannot express creepage at all.** `pcb/temper.kicad_pro`'s
`net_settings.classes[]` entries carry `clearance`, `track_width`, via and diff-pair
fields — there is no creepage key in the schema. Creepage on the kicad-cli path is
expressible **only** as a custom `.kicad_dru` rule. So a creepage figure that never
reaches the `.kicad_dru` is not enforced regardless of what `design_rules.py` says, and
before this change none did for an HV↔HV pair.

---

## 3. Which enforcement path the rule reaches — and which it does not

### 3.1 kicad-cli: reached, and this is the whole of the enforcement

`scripts/generate_kicad_dru.py` now emits, into `pcb/temper.kicad_dru`:

```
(rule "HighVoltageTank functional creepage"
   (condition "A.NetClass == 'HighVoltageTank' && (B.NetClass == 'HighVoltage' || B.NetClass == 'HighVoltageTank')")
   (constraint creepage (min 6.3mm))
)
```

kicad-cli resolves `A.NetClass`/`B.NetClass` from `pcb/temper.kicad_pro`'s
`net_settings.netclass_assignments`, where `"tank.c_tank1-p2": "HighVoltageTank"` is now
recorded, against a `net_settings.classes[]` entry of the same name. Both were added.
No `netclass_patterns` glob re-captures the net (the eight patterns are `+*V`, `VCC*`,
`VDD*`, `DC_BUS*`, `GATE_*`, `PWM_*`, `VBOOT_*`, `AC_*`; tested against the net name,
zero match), and KiCad's explicit assignments take precedence over patterns regardless.

KiCad 10.0.5's creepage constraint is a real surface-path graph solver, not a relabelled
clearance check — established in `docs/evidence/2026-07-28-drc-creepage-constraint.md`
and visible here in the measured `actual` distances (§5).

### 3.2 The Rust safety kernels: NOT reached. Stated plainly.

**No Rust kernel enforces 6.3mm, or any per-netclass creepage figure.** The value
travels into Rust and is consumed by nothing:

- **It arrives.** `packages/temper-drc-rs/src/drc_marshal.rs:1373-1375` reads
  `creepage_mm` off the net-class definitions; `board_py_bridge.rs:399` extracts it into
  `board::NetClassRules.creepage_mm` (`board.rs:229`). `HighVoltageTank` flows through
  automatically — `regression/drc_ratchet.py` iterates `TEMPER_NET_CLASSES` generically,
  with no hardcoded class list.
- **Nothing reads it.** The only other references to `.creepage_mm` in `temper-drc-rs`
  are the marshalling round-trip itself (`drc_marshal.rs:1018`, `:1479`, `:1589-1591`).
  There is no rule keyed on it.
- **The creepage kernels are keyed on net NAMES, not netclasses.**
  `packages/temper-geometry/src/creepage_check.rs` contains no `net_class` reference at
  all; it selects nets with `is_high_voltage_net(net_name)` (`:325`), a keyword scan, and
  dimensions from an IPC-2221 table. `packages/temper-drc-rs/src/router_clearance.rs`'s
  `voltage_class_creepage_mm` (`:359`) is a hardcoded IEC table indexed by a
  `VoltageClass` derived from `classify_net_class(net_name)` (`:246`) — a substring match
  on the **net name**, OR'd with `elec/domain_manifest.yaml`'s HV net-name set. The
  project's netclass names never enter either function.
- **`Component.net_class` cannot even carry the name.**
  `packages/temper-placer/src/temper_placer/io/_parse_nets.py:42-79` collapses component
  class to a severity literal: every HV- or AC-category component arrives in Rust
  labelled literally `"HighVoltage"`. A component on `tank.c_tank1-p2` therefore resolves
  to **`HighVoltage`'s** rules, not `HighVoltageTank`'s. (`Net.class`, unlike
  `Component.net_class`, does carry the real name.)

What the Rust side *does* gain from the new class, stated for completeness and not as
creepage coverage: `safety_category="HV"` puts it in scope for
`rules/safety/hv_lv_separation.rs`, which enforces a single global
`constraints.hv_clearance_mm` (default 10.0), and `voltage_v=923.7 ≥ 60` puts it in scope
for `rules/routing/partial_discharge.rs`'s fixed 1.5× inner-layer multiplier. Neither is
6.3mm and neither is a creepage check.

**Consequence to be honest about:** the tank node also *loses* membership in three
hardcoded `== "HighVoltage"` string tests —
`packages/temper-design-bundle/src/deterministic_stages.rs:336` (zone inference),
`packages/temper-drc-rs/src/clearance_matrix.rs:230` (HV zone override), and
`packages/temper-drc-rs/src/validation.rs:284-285` (HV↔LV pair criticality). On this
board the practical effect is nil, because C25/C26/C27 and R30 all carry `SW_NODE` or
`tank-out` on their other pad and remain `HighVoltage` members by that route — but a
future component wired only to the tank node would not. That is a latent consequence of
this change and it is recorded rather than fixed here.

---

## 4. Coverage preservation: the carve-out does not drop what the tank node already had

Moving a net out of `HighVoltage` silently strips it from every rule condition naming
that class. Left unhandled that is a **safety regression** wearing the costume of a
safety improvement. Seven rule conditions were updated:

| Rule | Change | Why |
|---|---|---|
| `HV to LV` | added `&& B.NetClass != 'HighVoltageTank'` | **The critical one.** Without it the swapped ordering (A=bus `HighVoltage`, B=tank) matches, charging a same-domain functional pair the 8.0mm *reinforced* cross-barrier figure — the exact false-positive shape `docs/evidence/2026-08-11-creepage-gatedrivehv-false-positive.md` documents for GateDriveHV/HighVoltageIsolated. |
| **`HighVoltageTank to LV`** (new) | exact clone of `HV to LV`: clearance 2.0mm, creepage 8.0mm | Preserves the reinforced HV↔LV boundary the tank node had as a `HighVoltage` member. Figures carried over unchanged — this rule preserves a requirement, it does not introduce one. |
| `AC Mains to LV` | added `&& B.NetClass != 'HighVoltageTank'` | Same false-positive shape, ACMains side. |
| `AC Mains to HV` | B-side widened to `(HighVoltage \|\| HighVoltageTank)` | Keeps the 3.0mm same-side figure the pair had. |
| `HighVoltageIsolated to LV` | added exclusion | Same shape. |
| `HighVoltageIsolated same side` | B-side widened | Keeps the 2.0mm same-side figure. |
| `HV internal same footprint`, `GateDriveHV/SELV near HV` | both sides widened | C25/C26/C27 have pad 1 on `SW_NODE` and pad 2 on the tank net; after the carve-out neither this rule nor the generic `Same footprint pads` rule (which requires `A.NetClass == B.NetClass`) matched that intra-package pair. |
| trace-width `class_order` list | added `HighVoltageTank` | This list is hand-maintained and silently drops any class missing from it. Without the entry the tank node's tracks lose the 3.0mm minimum width they had, and nothing says so. |

**Measured proof that coverage was preserved, not just intended.** The creepage
violations involving `tank.c_tank1-p2`, before and after:

```
BASELINE   HV to LV:                            7   actuals=[0.3281, 1.9341, 4.475, 4.895, 6.1707, 7.875, 7.985]
BRANCH     HighVoltageTank to LV:               7   actuals=[0.3281, 1.9341, 4.475, 4.895, 6.1707, 7.875, 7.985]
BRANCH     HighVoltageTank functional creepage: 2   actuals=[2.2656, 5.0]
```

Same seven pairs, same seven measured distances, same 8.0mm requirement — only the rule
name changes. The delta is exactly the two new HV↔HV violations. `track_width` measured
199 before and after, so the restored trace-width rule reports nothing new either.

---

## 5. Proof the rule binds

A creepage rule never seen to reject anything is not a rule. Three independent
demonstrations.

### 5.1 It rejects two real pairs on the committed board

Deterministic — **2 of 2 in all 10 final samples**, identical pairs and distances:

```
Creepage violation (rule 'HighVoltageTank functional creepage' creepage 6.3000 mm; actual 2.2656 mm)
    PTH pad 2 [tank.c_tank1-p2] of C25      at (160.00, 112.70)
    Track [discharge.k_dis1-nc] on B.Cu     at (156.25, 112.15)

Creepage violation (rule 'HighVoltageTank functional creepage' creepage 6.3000 mm; actual 5.0000 mm)
    PTH pad 1 [tank.c_tank1-p2] of R30      at ( 49.10, 124.48)
    PTH pad 2 [tank-out]        of R30      at ( 36.10, 124.48)
```

Both are genuine, and both are the pairs the physics predicted:

- **C25 pad 2 ↔ `discharge.k_dis1-nc`: 2.2656mm provided against 6.3mm required — 2.8×
  short.** `discharge.k_dis1-nc` is an HV-bus net (`design_rules.py:329`). This is
  precisely the tank-node-to-bus pair measured at 570.5 Vrms. It is the headline
  violation: the highest-voltage insulation interface on the board, at a third of the
  distance the standard asks for, on a rule that did not exist until now.
- **R30 pad 1 ↔ pad 2: 5.0000mm against 6.3mm.** These are the two litz-pad terminals of
  the coil connection — the tank node against `tank-out`. `tank-out` returns to `PWR_RTN`
  through the CT primary, so this pair carries essentially the tank↔`PWR_RTN` voltage,
  544.6 Vrms, also Table 18 row vi. Correctly flagged.

Neither is a same-package artefact of the kind that would make the rule noise: R30's is a
same-footprint pair but a *real* 5.0mm surface gap between two terminals 544.6 Vrms
apart, not a package-internal geometry the rule has no business measuring.

### 5.2 The count tracks the constraint value monotonically

Sweeping only the rule's `min` on the same board, one sample each:

| `(constraint creepage (min …))` | tank-rule violations | total creepage | total errors |
|---:|---:|---:|---:|
| 0.001mm *(floor probe)* | **0** | 183 | 1263 |
| 2.0mm | 0 | 184 | 1264 |
| 5.0mm | 1 | 185 | 1265 |
| 5.5mm | 2 | 185 | 1265 |
| **6.3mm (enforced)** | **2** | 185 | 1265 |
| 6.4mm | 3 | 186 | 1266 |
| 8.3mm | 4 | 187 | 1267 |
| 10.0mm *(PD3 figure)* | 4 | 188 | 1268 |
| 20.0mm *(ceiling probe)* | 4 | 187 | 1267 |

This is the step function of the four real measured distances in the tank↔HV pair space:
**2.2656, 5.0000, 6.3992, 8.2547mm**. The 0.001mm floor proves the rule is not firing on
everything it matches; the 20mm ceiling proves it is not silently matching nothing. Both
failure modes a rule can have are excluded.

The 6.3992mm pair is worth naming, because it is a **real on-board pair that the rule
accepts**: C25 pad 2 against a via on `discharge.k_dis1-nc`, 0.0992mm above the bar. The
rule discriminates at 6.3mm on real geometry, in both directions.

### 5.3 A constructed case that satisfies 6.3mm passes

Two 1.0mm THT pads on F.Cu, one on `tank.c_tank1-p2` (`HighVoltageTank`), one on
`+170V_BUS` (`HighVoltage`), on a synthetic board carrying only the new rule:

| Edge-to-edge gap | Result |
|---|---|
| **5.0mm** | `Creepage violation (rule 'HighVoltageTank functional creepage' creepage 6.3000 mm; actual 5.0000 mm)` — **1 violation** |
| **7.0mm** | **0 violations** |

Reproducer in §9.

---

## 6. Ceiling impact — measured, not estimated

kicad-cli 10.0.5, `--all-track-errors --format json`, `MaximumThreads=1`, scratch copy of
the committed board.

| | clearance | creepage | total errors |
|---|---|---|---|
| **Baseline** (origin/main, 20 samples) | 386 (20/20) | **182–184** `{184:12, 183:6, 182:2}` | 1262–1264 |
| **This branch** (29 samples: 19 + 10 post-`class_order`) | 386 (29/29) | **185–186** `{186:24, 185:5}` | 1265–1266 |
| `drc_ceiling.json` | 386 | **186** | **1266** |

Baseline reproduces the committed record exactly (`violations_by_type.clearance = 386`,
`creepage` inside its recorded 182–184 band), which is the check that this harness agrees
with the one the ceiling was measured with.

**Delta: +2 creepage, +2 total errors, +0 clearance.** Both new violations are the §5.1
pairs.

### 6.1 It does not breach — and that is not the good news it sounds like

The ratchet compares with strict inequality: `if error_delta > 0` in
`packages/temper-drc-rs/src/drc_ratchet.rs:176`, and the per-category check is the same
shape. creepage 186 == ceiling 186 passes; errors 1266 == `error_ceiling` 1266 passes.

Confirmed by running the real gate, `scripts/ci_check_drc.py`, on this branch: it reports
**no error-side failure**, and the same output as on pristine main. (Both runs fail on
`lib_footprint_issues 166 > 11`, a warning-side artefact of the local kicad-cli's
footprint-library environment — identical on main, unrelated to this change, and not
introduced by it.)

**So the ceiling was not breached, was not raised, and no figure was weakened to stay
under it.** 6.3mm is the Table 18 number; §5.2 shows what the honest alternatives would
have cost.

### 6.2 But the headroom is now zero, and the repo has a guard that says why that matters

`power_pcb_dataset/drc_ceiling.json` records creepage as nondeterministic with
`observed: [182, 183, 184]`, `samples: 130`, against ceiling 186 — headroom 2, spread 2.
`packages/temper-placer/src/temper_placer/regression/drc_ratchet.py:372`
(`check_noise_headroom`) enforces `headroom >= spread`, because CI runs DRC **once** and
compares that single sample directly against the ceiling.

Run against the committed record, the guard passes. Run against **this branch's measured
band**, using the repo's own function:

```
observed=[185, 186] ceiling=186
FAIL headroom=0 spread=1
temper: 'creepage' has ceiling headroom 0 (ceiling 186 - observed max 186) smaller than
its own measured run-to-run spread 1 (observed [185, 186] over 29 samples). A single-sample
CI run can land above the ceiling from noise alone, with no board regression -- widen the
headroom (or move this category to a deterministic engine) before trusting a single sample.
```

The guard currently reports PASS **only because the committed `observed` record is now
stale.** Nothing in this change updated it, deliberately — refreshing it is a
re-measurement, and per `drc_ceiling.json`'s own `_goal` a re-measurement that raises a
ceiling needs a `Ceiling-Approval:` trailer and a ≥120-sample record.

**This is the honest state: the rule lands green today, on 29 samples, with zero margin
and a stale noise record.** 29 samples never produced 187. But
`docs/evidence/2026-08-04-drc-measurement-determinism.md` characterised creepage on an
earlier board state across two independent 120-sample campaigns and found a **3-value
band with spread 2** both times. If this band is also 3 values wide, its third value is
187 and CI goes red intermittently from noise alone.

---

## 7. Staging proposal

The violation count is **not** unmanageable — it is 2, both real, both actionable. This
does not need staging as advisory. What needs a decision is the **zero headroom**, and
the choice is between three options that must be made deliberately rather than absorbed:

**Recommended — (A) fix the two violations, do not touch the ceiling.** The rule found a
real defect; the fix is the board, not the bar. Both pairs are spacing problems on a
board that is already re-solved routinely. Resolving them returns creepage to 183–184 and
restores the headroom automatically, with the rule left permanently in place and the
ceiling untouched. This is the only option that ends with the requirement enforced *and*
satisfied.

**(B) If the board cannot move first: re-measure the creepage record properly, and
ratchet the ceiling *down* where the same run allows it.** A ≥120-sample campaign
establishes whether the post-change band is 2 or 3 values. If it is `[185, 186]`, the
invariant needs `ceiling = 186 + 1 = 187` — a **raise**, requiring a `Ceiling-Approval:`
trailer, an attributed cause (this rule), and a fresh measured-live record, all
machine-checked by `scripts/check_drc_ceiling_approval.py`. That approval should be
requested explicitly and granted by a human, not taken. **I have not taken it, and this
PR does not include it.**

**(C) Only if (A) and (B) are both blocked: land the rule behind an advisory step with a
dated deadline.** The repo already has this pattern —
`docs/evidence/2026-08-11-pd2-decision-record.md` §5.3 wires a real, red gate into
`consistency-gates` with `continue-on-error: true` and a written path to blocking. The
same shape would work here. It is listed third because it is the weakest: it enforces
nothing until someone removes the flag, and this repo already carries several gates in
that state.

**What should not happen, listed so it is on the record:** raising the ceiling silently,
choosing a figure below 6.3mm to stay under it, or narrowing the class to one that
reports fewer violations. Each was available and each was rejected.

---

## 8. Findings adjacent to the change

### 8.1 A gate that could not run, caught and fixed

Adding the constants in the obvious shape —
`HV_TANK_CREEPAGE_ENFORCED_MM = HV_TANK_CREEPAGE_PD2_MM`, mirroring the existing
`HV_CREEPAGE_ENFORCED_MM` — made `scripts/check_creepage_clearance_drift.py` exit **5
(GATE ERROR — "could not run a trustworthy check")**, where on main it exits 3 (a real
violation report). A gate that cannot run is strictly worse than a gate that reports
findings, so this was fixed rather than accepted.

**Cause.** That gate classifies each declaration into a `(metric, tier)` family with
`tier ∈ {reinforced, basic, working, unspecified}`, read by keyword-scanning the attached
comment. It treats a bare `NAME2 = NAME1` as a "selection alias" and self-checks that the
selected constant sits in a comparable family. **6.3mm is functional insulation — a tier
that gate does not model** — so it has no family and the self-check fails.

**Fix, and one rejected alternative.** The enforced constant is now a dict lookup keyed
by an explicit `_TANK_POLLUTION_DEGREE`, which keeps the one-line PD2/PD3 switch,
duplicates no literal, and reads to the gate as a non-literal expression (its existing
UNRESOLVED bucket). Adding `functional` to the gate's tier vocabulary was tried and
**rejected on measurement**: against the pristine tree it also re-tags
`netclass_rules.yaml`'s `HighVoltageIsolated` entries — whose `because` reads *"reinforced
separation to LV/SELV, functional-only to its own HV/ACMains neighbours"* — out of the
reinforced families, shrinking `[clearance/reinforced]` 4→3 and `[creepage/reinforced]`
10→9 and turning two real MISMATCH reports into OK ones. That is a loss of gate
sensitivity dressed as a fix. Teaching that gate to distinguish *"this value is
functional"* from *"this text mentions functional"* is real work and belongs in its own
change.

**Verified outcome:** the gate now exits 3 on this branch with **family membership and
mismatch counts identical to pristine main** (4 mismatched families, same members, same
values); the six new declarations land in the FLAGGED bucket (94 → 100), which is the
same treatment every `TEMPER_NET_CLASSES` entry already gets. The two load-bearing
comment placements are documented in-place so a future tidy-up does not silently undo
them.

### 8.2 The pinned differential oracle is stale on `main`, and it is a safety constant

`packages/temper-placer/tests/core/_design_rules_py_oracle.py` still carries
`HighVoltage.clearance = 6.0` while the live table has `2.0` — the value
`docs/evidence/2026-08-12-netclass-param-reconciliation.md` corrected. Three tests in
`test_design_rules_rust_differential.py` fail on pristine `origin/main` for exactly this
reason. **They fail identically on this branch, with the same message naming the same
constant** — this change neither caused nor fixed them, and the `HighVoltageTank` entry
was mirrored into the oracle so it contributes no new difference. Reported because a
stale pinned oracle on a *clearance* value is the same defect class this whole line of
work exists to close; re-pinning it is a separate change.

### 8.3 `PWR_RTN` still has no netclass

Carried forward from PR #1080 §6.3. `tank.c_tank1-p2` ↔ `PWR_RTN` measures 544.6 Vrms and
genuinely needs 6.3mm functional. Because `PWR_RTN` falls through to `Default`, the pair
is charged **8.0mm** by `HighVoltageTank to LV` — reading an HV-domain return as LV. That
is numerically conservative and is the same treatment the pair already received before
this change, so nothing regressed; but it is a mislabelled pair, and the right fix is to
class `PWR_RTN`, which `sync_kicad_netclass_assignments.py` currently protects
(`PROTECTED_NETS`) precisely because doing so would drag 85 grounded pins into HV.

### 8.4 One pair is over-constrained by one table row, deliberately

`tank.c_tank1-p2` ↔ `SW_NODE` is the voltage across the tank capacitors: 411.5 Vrms,
Table 18 band v = **4.0mm** at PD2, not 6.3mm. The rule applies 6.3mm to it because
`SW_NODE` is a `HighVoltage` net. Splitting it out needs a `NetName`-keyed override whose
rule-precedence behaviour this repo has not established. **Measured cost of not
splitting it: zero** — the only components carrying both nets are C25/C26/C27, a 40mm-pitch
axial package (`temper:C_Axial_L34.0mm_D22.5mm_P40.00mm_Horizontal`) whose pads sit 40mm
apart. Recorded so the conservatism is visible rather than silently baked in.

### 8.5 PD3, restated because 6.3mm will be read out of context

`docs/evidence/2026-08-11-pd2-decision-record.md` §2 records that the sealed compartment
PD2 is conditional on **does not exist**, and that *"PD3/12.6mm governs the as-built
construction today"*. 6.3mm is therefore a **floor against the selected target**, not a
claim that the as-built board complies. The as-built functional figure is **10.0mm**,
which §5.2 measures at **4 violations** rather than 2. Both constants are in the source
(`HV_TANK_CREEPAGE_PD2_MM` / `HV_TANK_CREEPAGE_PD3_MM`) so a mechanical reclassification
moves one line.

And the clause-19 route remains open but unrun: per
`docs/evidence/2026-08-12-hv-hv-creepage-determination.md` §4-5, cl. 29.2.4's exemption is
conditional on passing clause 19 **with this creepage distance short-circuited** — a dead
short from the tank node to a bus rail across a running 1.8 kW resonant converter — and
cl. 19.11.2(a) makes that short-circuit a *mandatory* fault condition precisely because
creepage is below the clause-29 values. Nobody has run it.

---

## 9. Reproduction

```bash
# 1. Regenerate the DRU from the SSOT and inspect the new rule
uv run python scripts/generate_kicad_dru.py
grep -A3 'HighVoltageTank functional creepage' pcb/temper.kicad_dru

# 2. Measure. Scratch copy only -- pcb/temper.kicad_pcb is never written.
D=$(mktemp -d); cp pcb/temper.kicad_pcb pcb/temper.kicad_pro pcb/temper.kicad_dru "$D"/
CFG=$(mktemp -d); mkdir -p "$CFG/10.0"; echo MaximumThreads=1 > "$CFG/10.0/kicad_advanced"
KICAD_CONFIG_HOME="$CFG" kicad-cli pcb drc --all-track-errors --format json \
    --output "$D/drc.json" "$D/temper.kicad_pcb"
jq '[.violations[] | select(.severity=="error" and .type=="creepage")] | length' "$D/drc.json"
jq -r '.violations[] | select(.description | test("HighVoltageTank functional")) | .description' "$D/drc.json"

# 3. Binding probes: edit the (min 6.3mm) in the copied .kicad_dru to 0.001mm and 20.0mm
#    and re-run step 2. Expect 0 and 4 tank-rule violations respectively.

# 4. The constructed accept/reject fixture is two 1.0mm THT pads on F.Cu at a chosen
#    edge-to-edge gap, one net assigned HighVoltageTank and one HighVoltage in the
#    fixture's own .kicad_pro, with only the new rule in its .kicad_dru.
#    5.0mm -> 1 violation (actual 5.0000mm); 7.0mm -> 0 violations.

# 5. Gates
uv run python scripts/check_hv_netclass_coverage.py                # PASS
uv run python scripts/check_netclass_class_param_correspondence.py # PASS
uv run python scripts/check_netclass_map_board_correspondence.py   # PASS
uv run python scripts/sync_kicad_netclass_assignments.py --check   # PASS
uv run python scripts/check_creepage_clearance_drift.py            # exit 3, same 4 families as main
uv run python scripts/ci_check_drc.py                              # no error-side failure
```

---

## Files

- This document: `docs/evidence/2026-08-12-hv-hv-creepage-enforcement.md`
- Rule + constants: `scripts/generate_kicad_dru.py`
  (`HV_TANK_CREEPAGE_PD2_MM`/`PD3_MM`/`ENFORCED_MM`, `HV_TANK_CLASS`, rule
  `"HighVoltageTank functional creepage"`, rule `"HighVoltageTank to LV"`, seven amended
  conditions, `class_order`)
- Class + assignment: `packages/temper-placer/src/temper_placer/core/design_rules.py`
  (`TEMPER_NET_CLASSES["HighVoltageTank"]`, `TEMPER_NET_ASSIGNMENTS["tank.c_tank1-p2"]`),
  `packages/temper-placer/configs/netclass_rules.yaml`,
  `pcb/temper.kicad_pro` (`net_settings.classes[]`, `netclass_assignments`),
  `configs/temper_production_config.yaml`
- Mirrored oracle / expectations: `packages/temper-placer/tests/core/_design_rules_py_oracle.py`,
  `packages/temper-placer/tests/core/test_design_rules.py`,
  `packages/temper-placer/tests/io/test_netclass_loader.py`
- Carried forward, not re-derived: `docs/evidence/2026-08-12-hv-clearance-adequacy.md`
  (PR #1080, working voltages and the no-constraint finding),
  `docs/evidence/2026-08-12-hv-hv-creepage-determination.md` (PR #1081, Table 18 and the
  clause-29.2.4 analysis), `docs/evidence/2026-08-11-pd2-decision-record.md` (PD2
  selection and the unmet compartment prerequisite)
- **Not modified:** `pcb/temper.kicad_pcb`, `power_pcb_dataset/drc_ceiling.json`,
  `elec/**`, any clearance value.

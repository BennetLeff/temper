# Creepage violation triage: how many of 205 are genuine, how many are rule artifacts

<!-- provenance: commit=bb4941d9ccc2ec9f67c00883c529ca4a334f4fd7 dirty=true (branch docs/creepage-205-triage, tracking origin/fix/kicad-pro-netclass-consolidation / PR #474; base confirmed via `git rev-parse HEAD` before any measurement; dirty=true for the one in-scope code change this doc reports, scripts/generate_kicad_dru.py, plus this doc itself) -->

**Date:** 2026-07-30
**Scope:** `scripts/generate_kicad_dru.py` (rule-generation fix only). `pcb/temper.kicad_pcb`,
`pcb/temper.kicad_pro`, and `power_pcb_dataset/drc_ceiling.json` are **not modified** and are treated as
read-only throughout. No `Ceiling-Approval:` trailer is authored.

## Verdict, up front

**205 is not the honest genuine-defect count, and it was partly a rule-generation bug.** Of the 205 raw
`creepage` violations `kicad-cli pcb drc` reports on PR #474's tree:

| Bucket | Before fix (205) | After fix (186) | What it means |
|---|---:|---:|---|
| **Genuine HV/mains↔SELV crossings** (different components) | 135 | 135 | Real. A human must fix these (routing/placement). |
| **Genuine, same-package isolation-barrier gap** (intra-component) | 5 | 5 | Real, but **not layout-fixable** — package geometry (matches the TO-247 precedent, Sec 4). |
| **Same-domain (HV↔HV) pairs, different components** — rule artifact | 38 | 24 | Not a genuine crossing. Both nets are electrically the same HV/mains domain. |
| **Same-domain (HV↔HV) pairs, same component** — rule artifact | 18 | 13 | Same as above, coincidentally on one ref. |
| **Protective-impedance divider interior nodes** | 9 | 9 | Neither HV nor SELV by the manifest's own explicit judgment — flagged, not resolved either way (Sec 5). |

A genuine rule-generation defect (Sec 3) inflated the artifact buckets by 19 violations (38→24, 18→13).
It is fixed in this pass, in `scripts/generate_kicad_dru.py` only. **Bottom line: of the 205 originally
reported, 140 are genuine board defects (135 board-routable + 5 fixed by package geometry, not layout),
37 are rule artifacts (now reduced to 19 after the fix landed here — the remaining 19 are a *second*,
separate defect this pass could not fix because it lives in `pcb/temper.kicad_pro`, out of scope per this
task's constraints), and 9 are a flagged, unresolved policy question, not yet bucketed either way.**

---

## 1. Reproducing the number

The `.kicad_dru` file is generated, not tracked (`.gitignore:58`, `/pcb/*.kicad_dru`) — it must be
regenerated before DRC sees any custom rule at all:

```
PYTHONPATH=$PWD/packages/temper-placer/src .venv/bin/python scripts/generate_kicad_dru.py
kicad-cli pcb drc --all-track-errors --format json --output /tmp/drc.json pcb/temper.kicad_pcb
```

Without this step, `kicad-cli` reports **0** `creepage`-type violations (confirmed: ran DRC against the
board with no `.kicad_dru` present first, got 32 `clearance` violations total and zero mentions of
`creepage` anywhere in the JSON). With the DRU file regenerated from this branch's
`packages/temper-placer/src/temper_placer/core/design_rules.py`, `creepage` count is **exactly 205** —
matches the task brief's figure, confirming this is the tree and generation path the 205 was measured on.

## 2. Method: real net data, not netclass-name guessing

Every one of the 205 violations was classified by resolving **both nets' true electrical domain**
against `elec/domain_manifest.yaml` (HV domain: `ac_l`, `+170V_BUS`, `SW_NODE`, `GATE_HS`/`GATE_LS`,
`PWR_RTN`, the isolated gate-driver bootstrap nets, etc.; SELV domain: `gnd`, `+15V`, `+3V3`, the RTD/UI/
MCU nets, etc.) — **not** by trusting `pcb/temper.kicad_pro`'s own per-net KiCad netclass assignment,
because Sec 6 below shows that assignment is itself incomplete for several of these exact nets.

36 of the 205 violations' nets were not literal entries in the manifest's net lists (mid-chain divider
nodes, auto-named internal nets of ICs/regulators, unused MCU GPIOs, logic-glue outputs). Rather than
guess from spelling (the manifest's own ground rule, `elec/domain_manifest.yaml:9-15`), every one was
traced through the **freshly-built compiled netlist** (`make netlist` → `elec/build/default.net`,
2129 lines, 168 components) to its actual neighbor components and, transitively, to a declared HV or
SELV net. Three examples (full trace for every net is in the `classify.py`/`dump_tables.py` working
scripts, summarized here):

- `power_in.r_zcd_top1-p2`: netlist net 23 = `{R7 pin1, R6 pin2}`; `R6 pin1` = `ac_l` (net 12, HV); `R7
  pin2` = `zcd` (net 14, HV, already declared). Both ends of this resistor are HV → the node between them
  is HV.
- `discharge.q_dis_drv-g`: netlist net 35 = `{Q2 pin2, R17 pin2, R18 pin1}`; `R17 pin1` = `DISCHARGE_CTRL`
  (net 25, from `U27`/MCU, SELV); `R18 pin2` = `gnd` (net 1, SELV). Both ends SELV → this is the SELV-side
  gate-drive signal for the discharge relay's driver transistor.
- `hb.gate_hs.driver-p1` (U7 pin 6, `DT`): not independently re-traced — `elec/domain_manifest.yaml`
  itself already states the answer in its own commentary (search "primary-side, GNDI-referenced,
  correctly left off this list"), just never added to the SELV net list. Treated as SELV per the
  manifest's own stated reasoning, not re-derived.

The three OVP-01 divider interior nodes (`safety.ovp.r_div_top1-p2`, `r_div_top2-p2`, `r_adc_top2-p2`)
were **not** forced into either domain — traced, they sit between +170V_BUS and a declared-SELV endpoint
through nothing but resistors, and the manifest itself already says why that is not a HV/SELV call:
*"the divider chains' own purely-interior nodes... sit at genuinely intermediate voltage... neither HV
nor SELV by voltage"* (`elec/domain_manifest.yaml`, "Deliberately NOT closed" paragraph). This doc keeps
that judgment rather than overriding it (Sec 5).

## 3. The rule-generation defect (found and fixed)

`scripts/generate_kicad_dru.py`'s RULE 2 (`AC Mains to LV`), RULE 4 (`HV to LV`), and the
`HighVoltageIsolated to LV` rule each apply the reinforced HV↔SELV creepage figure using a **blacklist**
condition — "match everything except these specific other classes":

```
RULE 4 before (line ~525 pre-fix):
   (condition "A.NetClass == 'HighVoltage' && B.NetClass != 'HighVoltage' && B.NetClass != 'ACMains'")
```

`GateDriveHV` (`GATE_HS`/`GATE_LS`, floats on `SW_NODE`) and `HighVoltageIsolated` (the gate-driver
floating bootstrap supply) are **the same physical HV domain** as `HighVoltage`/`ACMains` per
`elec/domain_manifest.yaml` — `packages/temper-placer/src/temper_placer/core/design_rules.py`'s own
`TEMPER_NET_CLASSES` table tags all four (`ACMains`, `HighVoltage`, `GateDriveHV`,
`HighVoltageIsolated`) `safety_category="HV"`. The blacklist named only `HighVoltage`/`ACMains`, so any
pair where the "other side" carried the `GateDriveHV` or `HighVoltageIsolated` KiCad netclass looked
like a genuine mains↔SELV crossing and got the full reinforced 8.0mm creepage requirement, when both
sides are the same domain.

**Measured, before fixing:** of the 205, 37 non-intra-footprint violations were true `HV↔HV` pairs
(Sec 2's domain resolution). Splitting those 37 by mechanism (checked against each net's actual
KiCad-computed netclass, `pcb/temper.kicad_pro`'s `net_settings.netclass_assignments` /
`netclass_patterns`, reproduced with a small Python harness matching `fnmatch` case-sensitively — the
same semantics `kicad-cli` uses on this platform, confirmed empirically in Sec 6):

| Root cause | Count | Example |
|---|---:|---|
| Blacklist gap (both nets carry a *correctly-assigned* HV-domain KiCad netclass, just not the one named in the condition) | 14 | `HighVoltage` (`DC_BUS_RTN`) vs `HighVoltageIsolated` (`hb.gate_hs.driver-p1-1`) |
| `pcb/temper.kicad_pro`'s own netclass-assignment gap (one net is truly HV but resolves to `Default` in the live project file) | 23 | `HighVoltage` (`DC_BUS_RTN`) vs `Default` (`+170V_BUS`) |

Only the first row (14) is a defect in `scripts/generate_kicad_dru.py` — the file this task authorizes
fixing. The second row (23) is a defect in `pcb/temper.kicad_pro` itself (Sec 6) — a file this task's
constraints forbid modifying, so it is reported, not fixed, here.

**Fix applied** (`scripts/generate_kicad_dru.py`, RULE 2/RULE 4/`HighVoltageIsolated to LV`): added
`&& B.NetClass != 'GateDriveHV' && B.NetClass != 'HighVoltageIsolated' && B.NetClass != 'HighCurrent'`
(the latter for model consistency with `design_rules.py`'s `safety_category` table, even though no live
`pcb/temper.kicad_pro` netclass currently uses that name). Symmetrically extended `"HighVoltageIsolated
same side"`'s clearance-only condition to also match `GateDriveHV`, so that pair still gets an explicit
same-side clearance figure (2.0mm) instead of silently falling back to an implicit, inconsistent
per-netclass baseline. Full diff: `scripts/generate_kicad_dru.py`, the three `(rule ...)` blocks named
`"AC Mains to LV"`, `"HV to LV"`, `"HighVoltageIsolated same side"`, `"HighVoltageIsolated to LV"`.

**Before/after, re-measured on the same board, same command:**

```
PYTHONPATH=$PWD/packages/temper-placer/src .venv/bin/python scripts/generate_kicad_dru.py
kicad-cli pcb drc --all-track-errors --format json --output /tmp/drc_after.json pcb/temper.kicad_pcb
```

| | Before | After |
|---|---:|---:|
| Total `creepage` violations | **205** | **186** |
| `HV to LV` rule | 157 | 140 |
| `HighVoltageIsolated to LV` rule | 48 | 46 |

Only the "same-domain-HV" buckets shrank (38→24 non-intra, 18→13 intra-footprint, per the table in the
verdict). `genuine-cross-domain` (135), `intra-component-genuine-barrier` (5), and
`protective-impedance-interior-node` (9) are **byte-identical before and after** — this change removed
false positives only, it added or changed nothing else. Verified: `scripts/tests/test_generate_kicad_dru.py`
(26 tests) still passes unmodified; the 8 unrelated `test_pipeline_metrics.py` failures were reproduced
on an unmodified `bb4941d9` worktree first (`git worktree add --detach`) to confirm they pre-exist this
change (a stale `pipeline_metrics.cmd_slo`/`cmd_spc` API mismatch, unrelated to creepage/DRU rules).

## 4. Intra-component violations: two different things, not one bucket

23→18 intra-footprint creepage violations (same reference designator on both sides) split into two
categories that must not be conflated:

**5 genuine same-package isolation-barrier gaps** (unaffected by the fix, real, and — like the repo's
existing TO-247/IGBT precedent — **not fixable by layout**, only by a different package/BOM choice):

| Component | Pins (nets) | Rule | Measured | Required |
|---|---|---|---:|---:|
| U7 (UCC21550BDWKR, `SOIC16W_Isolat...`) | `input` (primary, pin 10) ↔ `+15V_LS` (secondary, pin 11) | HV to LV | 0.670mm | 8.0mm |
| U7 | `input` ↔ `hb.gate_hs.driver-p1-1` (VDDA, pin 16) | HighVoltageIsolated to LV | 7.020mm | 8.0mm |
| U7 | `input` ↔ `hb.gate_hs.driver-p2` (VSSA, pin 14) | HighVoltageIsolated to LV | 4.480mm | 8.0mm |
| K3 (discharge relay, Omron G5LE-1) | `discharge.k_dis1-coil2` (SELV coil) ↔ `DC_BUS_RTN` (HV contact) | HV to LV | 5.025mm | 8.0mm |
| K3 | `discharge.k_dis2-coil1` (SELV coil) ↔ `DC_BUS_RTN` | HV to LV | 5.025mm | 8.0mm |

U7 and K3 are two of the seven components `docs/evidence/2026-07-30-creepage-requirement-reconciliation.md`
Sec 4 already names as the project's "known intra-footprint blockers" set
(`{C6, K1, K2, K3, T1, U3, U7}`) — this doc's independent measurement corroborates that set rather than
re-deriving it. `scripts/generate_kicad_dru.py`'s own RULE 5 comment records the underlying physical
fact for the TO-247 case this project already investigated: *"TO-247 IGBTs have 5.45mm pin pitch (1.95mm
edge-to-edge)"* — below the 2.0mm reinforced-clearance requirement and unfixable by any placement
change, per `docs/evidence/2026-07-28-conformal-coating-pd1.md` Sec 4. U7's/K3's own package/relay-body
geometry is the analogous limiting factor here: reinforced HV↔SELV creepage requires physical distance
the package itself does not provide across its own internal barrier.

**13 same-domain (HV↔HV) violations that happen to share a ref** — rule artifacts, same root cause as
Sec 3's board-pair bucket, just coincidentally on one component (e.g. `U5`: `hb.power_loop.q_high-g`
(gate) ↔ `+170V_BUS` (collector) — both HV, same IGBT). Full list in the "Data" section below.

## 5. Protective-impedance divider interior nodes: flagged, not resolved

9 violations involve `safety.ovp.r_div_top1-p2`, `safety.ovp.r_div_top2-p2`, or `safety.ovp.r_adc_top2-p2`
— interior nodes of the two OVP-01 protective-impedance chains `elec/domain_manifest.yaml`'s
`protective_impedance_chains:` section declares (`ovp01_comparator_divider`,
`ovp01_adc_sense_divider`). The manifest **explicitly and deliberately** does not assign these interior
nodes to either domain: *"the divider chains' own purely-interior nodes... sit at genuinely intermediate
voltage (per the manifest's own arithmetic, ~57-166V for the comparator divider's interior nodes) —
neither HV nor SELV by voltage, and forcing either label would be exactly the naming-convention guess
the manifest's ground rule forbids."*

This doc keeps that judgment rather than overriding it in either direction — these 9 are **not** counted
as "genuine" (the manifest itself declines to call them a domain crossing) and **not** counted as a
"rule artifact" (unlike Sec 3's defect, the rule condition genuinely matched a declared-HV net against
an undeclared one; there is no netclass-blacklist bug here). The correct disposition is an open question
this repo has already named once and not settled:
`docs/evidence/2026-07-27-domain-classification-coverage.md` Sec 7: *"Whether IEC 60335-1 requires a
full pairwise clearance/creepage check between the two ENDS of an already-declared protective-impedance
divider chain... in addition to the chain's own current-limiting/redundancy construction requirement, or
whether the construction requirement alone suffices — not resolved here."* This doc does not resolve it
either. A human must decide the policy question before these 9 can be moved into "genuine" or
"acceptable-as-is."

## 6. Is the required distance correct? Two separate findings, neither fixed here

**Finding A — `pcb/temper.kicad_pro`'s own netclass assignment is missing several live HV nets.**
Checked directly (Sec 3's 23-count row): `ac_l`, `ac_n`, `+170V_BUS`, `PWR_RTN`, and `SW_NODE` — the
literal AC-mains and DC-bus nets — all resolve to KiCad's generic `Default` netclass in the current
`pcb/temper.kicad_pro`, **not** `ACMains`/`HighVoltage`. Confirmed two ways:

1. `net_settings.netclass_assignments` in `pcb/temper.kicad_pro` has keys `"AC_L"`/`"AC_N"`/`"DC_BUS+"`/
   `"DC_BUS-"` — stale, wrong-case/wrong-name aliases that do not match the compiled netlist's actual
   lowercase names (`ac_l`, `ac_n`, `+170V_BUS`). `net_settings.netclass_patterns`' `'+*V'` pattern
   (intended for `+15V`/`+3V3`-style names) requires the net name to **end** in `V` — `+170V_BUS` ends in
   `S`, so it does not match either. No assignment or pattern claims these nets; they fall through to
   `Default`.
2. Empirically, in the DRC's own **`clearance`** (not creepage) violations: `ac_n` vs
   `hb.gate_hs.driver-p2` is reported as `"Clearance violation (rule 'Default routing' clearance
   0.2000 mm; actual 0.0376 mm)"` and `+170V_BUS` vs `RTD_SDI` similarly cites `'Default routing'`
   0.2mm — not `"netclass 'ACMains'"` (6.0mm) or `"netclass 'HighVoltage'"` (2.0mm/6.0mm), which would be
   the worst (most restrictive) applicable requirement and would be what's reported if either net
   carried its intended class. The string `"ACMains"` and the rule names `"AC Mains to LV"`/`"AC Mains to
   HV"` appear **zero times** anywhere in the 1900-violation DRC output — on a board with live AC-mains
   copper, that is strong independent confirmation the class is unused, not merely under-triggered.

This is a genuinely serious, live gap — **the literal mains input nets carry no DRC protection from the
ACMains netclass's rules at all today.** It is a defect in `pcb/temper.kicad_pro`, a file this task's
constraints explicitly forbid modifying, so it is reported here, not fixed. It is also the direct cause
of 23 of Sec 3's 37 same-domain mismeasurements (an HV net silently masquerading as `Default`, which
auto-satisfies every rule's "not-A-class" exclusion).

**Finding B — the enforced creepage figure itself (8.0mm) is stale relative to this project's own
already-settled pollution-degree correction.** `scripts/generate_kicad_dru.py:80-127` defines both
`HV_CREEPAGE_PD2_MM = 8.0` and `HV_CREEPAGE_PD3_MM = 12.6`, and pins `HV_CREEPAGE_ENFORCED_MM =
HV_CREEPAGE_PD2_MM` (line 127) — 8.0mm, PD2 — with a comment calling the PD2-vs-PD3 choice
"UNRESOLVED... a human must settle." But commit `96726eac` (already an ancestor of this branch's HEAD,
title *"fix(safety): correct pollution degree PD2 -> PD3, reinforced creepage 10.0mm -> 12.6mm"*)
already settled this: `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` Sec 3.2.1 now states *"Pollution
Degree: 3 (corrected 2026-07-30, was 2)"* with a full IEC 60335-2-6 cl. 29.2 Addition citation (PD3 is
the appliance-class default; PD2 must be earned by an enclosure argument this board's own
`CHASSIS_AIRFLOW_DESIGN.md`/`COIL_BRACKET_DESIGN.md`/IP20 rating do not support), and
`packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`'s
`IEC60335_REQUIREMENTS` matrix was updated to 12.6mm reinforced creepage for the equivalent boundary.
That commit's own message states *"scripts/generate_kicad_dru.py already encoded this fail-closed and is
unchanged"* — true only of the conformal-coating fail-closed behavior (`COATING_QUALIFIED = False`), not
of the PD2/PD3 creepage figure, which was left at 8.0mm. **Compounding this,
`packages/temper-placer/configs/netclass_rules.yaml` (line ~53) already contains a comment claiming the
fab-authoritative figure is "12.6mm, PD3-pinned, cited"** — that claim is false against the actual
generator output measured in this pass (confirmed: the regenerated `.kicad_dru` from Sec 1 contains
`(constraint creepage (min 8.0mm))`, not 12.6mm) — a documentation-vs-code drift on top of the
figure-currency gap itself.

**Not fixed here, deliberately.** `scripts/generate_kicad_dru.py`'s own comment (unchanged by this pass)
explains why a solo re-pin is unsafe: re-targeting `HV_CREEPAGE_ENFORCED_MM` to PD3 "touches this
constant, [`check_isolation_keepout.py`'s] `MIN_BARRIER_WIDTH_MM`, and the physical U3/U7 creepage-slot
geometry on the board simultaneously" — three things this task's constraints (no board changes, one
targeted rule-generation fix) do not authorize touching together. Re-measuring at 12.6mm would also
**raise**, not lower, the genuine-violation count (Finding B moves the wrong direction for a task about
inflation) — a separate, larger, already-flagged piece of work for a human to pick up, not folded into
this pass's fix.

## 7. Data: the full 186, by bucket

**Same-domain (HV↔HV), different components — rule artifact, 24 remaining after the fix:**

`DC_BUS_RTN↔+170V_BUS` (C8/R4, 5.895mm) · `PWR_RTN↔DC_BUS_RTN` (C3, 5.785mm) · `a↔<no net>` (U3, 0.946mm)
· `a↔PWR_RTN` (L1, 0.065mm) · `a↔SW_NODE` (R24, 5.416mm) · `ac_l↔a` (R6, 3.530mm) ·
`discharge.k_dis1-nc↔PWR_RTN` (6.574mm) · `discharge.k_dis2-nc↔PWR_RTN` (R14/R5, 4.830mm) ·
`discharge.r_dis1a-p2↔discharge.k_dis1-nc` (R12, 4.215mm) · `discharge.r_snub1-p2↔DC_BUS_RTN` (R28,
0.390mm) · `discharge.r_snub1-p2↔discharge.k_dis1-nc` (R19, 2.371mm) ·
`hb.gate_hs.driver-p2↔+170V_BUS` (C24, 1.708mm) · `hb.gate_hs.driver-p2↔ac_n` (L1, 0.038mm) ·
`hb.gate_hs.driver-p2↔discharge.k_dis2-no` (K3, 1.248mm) ·
`hb.gate_hs.driver-p2↔discharge.r_dis1a-p2` (R11, 7.089mm) · `hb.power_loop.q_high-g↔ac_l` (R24/R6,
0.954mm) · `power_in.ntc-no↔+170V_BUS` (R11, 0.557mm) · `power_in.ntc-no↔PWR_RTN` (C6, 0.882mm) ·
`power_in.ntc-no↔ac_n` (RT1/RV1, 7.131mm) · `power_in.r_zcd_top1-p2↔a` (R6, 3.160mm) ·
`power_in.r_zcd_top1-p2↔hb.gate_hs.driver-p2` (0.194mm) ·
`power_in.r_zcd_top1-p2↔hb.power_loop.q_high-g` (R6/R24, 3.849mm) · `w1_1↔PWR_RTN` (F1/D2, 1.600mm) ·
`zcd↔ac_n` (R7/C1, 0.505mm).

**Same-domain (HV↔HV), same component — rule artifact, 13 remaining:** `PWR_RTN↔DC_BUS_RTN` (R5,
4.700mm) · `SW_NODE↔DC_BUS_RTN` (U6, 3.950mm) · `a↔<no net>` (U3, 4.280mm) · `a↔PWR_RTN` (U3, 1.740mm) ·
`discharge.r_snub2-p2↔discharge.k_dis2-nc` (R20, 4.700mm) · `hb.gate_hs.driver-p2↔SW_NODE` (D5, 2.400mm)
· `hb.power_loop.q_high-g↔+170V_BUS` (U5, 3.450mm) · `hb.power_loop.q_high-g↔SW_NODE` (R24, 0.850mm) ·
`power_in.ntc-no↔+170V_BUS` (U1, 3.980mm) · `tank-out↔PWR_RTN` (T1, 6.360mm) · `w1_1↔ac_n` (RV1,
7.045mm) · `zcd↔PWR_RTN` (R8, 0.850mm) · `zcd↔power_in.r_zcd_top1-p2` (R7, 1.800mm).

**Intra-component, genuine isolation-barrier gap — unfixable by layout, 5:** see Sec 4 table (U7 ×3,
K3 ×2).

**Protective-impedance divider interior nodes — flagged, unresolved, 9:** see Sec 5 (`safety.ovp.r_div_top1-p2`,
`r_div_top2-p2`, `r_adc_top2-p2` against `DC_BUS_RTN`/`hb.power_loop.q_high-g`/`power_in.ntc-no`/`a`/
`hb.gate_hs.driver-p1-1`/`w1_1`/`zcd`).

**Genuine, board-routable cross-domain, 135 (58 unique component pairs)** — unchanged before/after,
byte-identical to the pre-fix set; e.g. `power_in.ntc-no↔+15V` (R79, 7.853mm vs 8.0mm required),
`tank-out↔+15V` (R30/R1, 5.516mm), `SHUTDOWN↔+15V_LS` (U7, 1.520mm), `discharge.k_dis1-coil2↔+15V_LS`
(U8, 5.268mm) — these are real HV/mains-to-SELV proximity findings on the board today and must be
reported as real.

## 8. Gates and verification

| Check | Result |
|---|---|
| `git rev-parse HEAD` / `git branch --show-current` at start | `bb4941d9`, matches PR #474's branch (`origin/fix/kicad-pro-netclass-consolidation`) |
| `scripts/tests/test_generate_kicad_dru.py` | 26 passed (unchanged) |
| `scripts/tests/` (full suite) | 704 passed, 8 failed — the 8 failures reproduced identically on an unmodified `bb4941d9` detached worktree (`test_pipeline_metrics.py`, `cmd_slo`/`cmd_spc` API mismatch), confirmed pre-existing and unrelated |
| `kicad-cli pcb drc` creepage count, before fix | 205 |
| `kicad-cli pcb drc` creepage count, after fix | **186** |
| `pcb/temper.kicad_pcb` | unmodified (`git status` shows only `scripts/generate_kicad_dru.py` changed) |
| `pcb/temper.kicad_pro` | unmodified |
| `power_pcb_dataset/drc_ceiling.json` | unmodified, not touched, no `Ceiling-Approval:` trailer authored |

## 9. UNVERIFIED / follow-ups for a human

- **Finding A** (Sec 6): `pcb/temper.kicad_pro`'s missing netclass assignment for `ac_l`/`ac_n`/
  `+170V_BUS`/`PWR_RTN`/`SW_NODE` needs a `pcb/temper.kicad_pro` edit — out of this task's scope (file is
  explicitly protected) but should be treated as the highest-priority follow-up: the literal mains nets
  currently get zero ACMains-netclass DRC protection.
- **Finding B** (Sec 6): whether to re-pin `HV_CREEPAGE_ENFORCED_MM` to `HV_CREEPAGE_PD3_MM` (12.6mm) —
  and, if so, `scripts/check_isolation_keepout.py`'s `MIN_BARRIER_WIDTH_MM` and the physical U3/U7
  creepage-slot geometry must move together, not independently. Not attempted here.
- **Sec 5's protective-impedance interior-node question** — whether IEC 60335-1 requires a standalone
  pairwise creepage check between a divider chain's own interior nodes and a nearby HV net, in addition
  to the chain's construction/redundancy requirement, remains open (also flagged, not resolved, by
  `docs/evidence/2026-07-27-domain-classification-coverage.md` Sec 7).
- The 135 genuine board-routable violations and the 5 genuine intra-footprint ones are **not** re-solved
  or fixed here — this task's constraints are triage only ("do not fix the board").

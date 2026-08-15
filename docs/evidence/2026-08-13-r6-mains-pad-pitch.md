<!-- provenance: commit=03a7415c8f08e6e8128a9ff90d8bc724ed8ddb58 dirty=false (origin/main tip at task start). Worktree /home/bennet/Desktop/temper-r6-mains-pad-pitch, branch fix/r6-mains-pad-pitch. pcb/temper.kicad_pcb was NEVER opened for writing in this task -- `git status --porcelain` is clean for pcb/** throughout; the only file this change adds is this document. R6's pad geometry (1.7999999999999998mm, reported as 1.80mm) was independently recomputed from pcb/temper.kicad_pcb's own `(pad ...)` S-expressions (pad 1 at x=-1.4625, pad 2 at x=+1.4625, both 1.125mm wide, roundrect) -- not merely copied from the cited CSV -- and matches it exactly. R7/R8/R9's pad gaps (1.80mm, 0.85mm, 0.85mm) were recomputed the same way and also match. The violations dataset relied on for the sweep is docs/evidence/2026-08-12-dru-rule-precedence-violations.csv (PR #1110, on main, itself measured with the same uncapped-partition methodology scripts/measure_uncapped_drc.py/PR #1111 implements) -- 1291 data rows, re-read directly this session, not re-run, because no board content changed for this task and there is therefore nothing new for a fresh DRC pass to find. `git log --all` was used to establish ancestry of two candidate fixes (5842767c2, 70b843428) against HEAD. No subagents were dispatched. -->

# R6 is not a footprint that needs widening. It is a dead component: the mains zero-crossing-detection divider it belongs to was deleted from `elec/src/` on 2026-08-XX (commit `5842767c2`), but `pcb/temper.kicad_pcb` on `main` was never resynced to remove it — and a resync that does exactly that already exists, unmerged, on `origin/codex/handoff-actionables`.

**Verdict up front.**

1. **R6 is `power_in.r_zcd_top1`, a 220kΩ SMD 1206 resistor** (Yageo
   `RC1206FR-07220KL`, `docs/hardware/BOM.md:60`) — the top element of a
   three-resistor divider (`R6`=top1 220k, `R7`=top2 220k, `R8`=bot 10k) that
   stepped AC mains down through a 3.3V zener clamp (`D2`) into an H11L1TVM
   optocoupler (`U3`, LED resistor `R9`, SELV-side pull-up `R10`) to deliver an
   isolated mains zero-crossing signal to the MCU. **Pad 1 sits on `ac_l`
   (ACMains netclass, live mains). Pad 2 sits on the divider's internal tap
   net, `power_in.r_zcd_top1-p2`.** Confirmed net-class asymmetry is real, and
   the `AC Mains to LV` rule (6.0mm clearance, 8.0mm PD2 creepage) is the
   correct rule *family* to be checking this pair against, in principle
   (Sec 1).
2. **The whole ZCD divider-and-optocoupler circuit — R6, R7, R8, R9, R10, D2,
   U3, seven components — was deleted from `elec/src/modules.ato`,
   `main.ato`, `components.ato`, and `elec/domain_manifest.yaml` on `main`**
   (commit `5842767c2`, "delete U3 (H11L1 mains-ZCD optocoupler) and its
   dedicated circuitry", documented in
   `docs/evidence/2026-07-30-zcd-optocoupler-removal.md`): no firmware
   consumer, no architectural role in this design (soft-start is
   time-delayed, not zero-cross-synchronised), no safety-chain wiring, and
   its own isolator U3 had an **unfixable** 8.560mm HV↔SELV intra-footprint
   pad separation against the (then) 12.6mm PD3 creepage target. Confirmed
   directly against the current worktree: `grep -rn "zcd" elec/src/*.ato`
   returns **zero** matches. R6 does not exist in the circuit this repo is
   currently building. Sec 2.
3. **`pcb/temper.kicad_pcb` on `main` still physically carries all seven dead
   components**, each with a `Sheetpath` property pointing straight at the
   deleted instance path (`R6`→`power_in.r_zcd_top1`, `R7`→`…top2`,
   `R8`→`…bot`, `R9`→`…r_zcd_opto`, `R10`→`…r_zcd_pullup`,
   `D2`→`…d_zcd_clamp`, `U3`→`…zcd_opto`) — confirmed by reading the board
   file directly, this session, not inferred. **The resync that removes them
   already exists**: commit `70b843428` ("fix: reconcile board after ZCD
   removal") rewrites `pcb/temper.kicad_pcb` to drop exactly these
   footprints and re-measures the DRC ceiling — but it lives only on
   `origin/codex/handoff-actionables`, is **not an ancestor of `main`'s
   HEAD**, and was never merged. Sec 3.
4. **R6's 1.80mm clearance violation is therefore stale-board noise, not a
   live safety defect.** There is no circuit left for a wider footprint to
   protect. Widening R6's package would fix a divider that no longer exists,
   while leaving the real problem (seven un-deleted footprints and their
   still-un-deleted copper) untouched. The honest fix is completing the
   pending resync — deleting R6 (and R7/R8/R9/R10/D2/U3) from
   `pcb/temper.kicad_pcb` — which this task's own brief places out of scope
   ("Do not modify `pcb/temper.kicad_pcb`"). **No footprint change is made in
   this PR.** Sec 4.
5. **Separately, and regardless of R6 being dead: the `AC Mains to LV` rule's
   6.0mm clearance figure in `scripts/generate_kicad_dru.py` does not carry a
   sound citation, and this repo's own already-computed numbers suggest the
   correctly-derived reinforced clearance for this exact crossing (mains
   ↔ PELV/LV) is 2.0mm, not 6.0mm.** This is a determination only — no value
   is changed here, consistent with how every prior citation-recovery
   document in this repo (`2026-08-12-hv-hv-creepage-determination.md`,
   `2026-08-12-hv-clearance-adequacy.md`) has landed its finding before any
   number moves. Sec 5.
6. **The sweep found 12 intra-component pad-pair violations across 10
   distinct components under the current, corrected (strictest-wins) DRU.
   Four of them — R6, R7, R8, R9 — are the same dead ZCD circuit.** The
   other six (`C23`, `R24`, `U7`×3, `U8`, `R51`, `R56`) are live components;
   `U7` is a previously-tracked, known intra-footprint isolator gap, and
   `R51`/`R56` are the first links of the OVP/ADC divider chains, each
   falling exactly 0.2mm short of the same-domain 2.0mm `HV internal same
   footprint` rule by nothing more than standard-1206-package geometry. This
   is a large enough class (R30, and now four more instances via one root
   cause) to be worth a gate. Sec 6.

**Nothing is changed by this PR except this document.** `pcb/temper.kicad_pcb`,
`scripts/generate_kicad_dru.py`, `packages/temper-placer/configs/netclass_rules.yaml`,
and `docs/hardware/BOM.md` are all untouched.

---

## 1. What R6 is, and the nets on its two pads

`pcb/temper.kicad_pcb:5680-5706`, footprint `Resistor_SMD:R_1206_3216Metric`
(standard IPC-7351-nominal SMD 1206, **not** through-hole — see Sec 4.1 for why
this matters), reference `R6`, `Sheetpath` property `power_in.r_zcd_top1`,
placed at `(142.35, 59.73)`, rotation 180°:

```
(pad "1" smd roundrect (at -1.4625 0 180) (size 1.125 1.75) ...
  (net 29 "ac_l"))
(pad "2" smd roundrect (at 1.4625 0 180) (size 1.125 1.75) ...
  (net 90 "power_in.r_zcd_top1-p2"))
```

Pad-edge-to-pad-edge gap, recomputed directly from these coordinates (not
copied from the CSV): `(1.4625 − 1.125/2) − (−1.4625 + 1.125/2) = 0.9 −
(−0.9) = 1.8mm` — exact match to the cited CSV's `actual_mm=1.8` and to
`docs/evidence/2026-08-12-dru-rule-precedence-violations.csv`'s row for `R6`
at `(143.8125, 59.73)` (the CSV's x is a pad-relative offset, not the
footprint origin; y matches exactly).

Pad 1 is on `ac_l` — live AC mains line, `ACMains` netclass, confirmed by
`elec/src/modules.ato:857` (`ac_l ~ fuse.p1`) and the fact that this is the
exact net the board's fuse F1 and MOV sit on. Pad 2 is on
`power_in.r_zcd_top1-p2`, an auto-named internal divider-tap net, `Default`
netclass in `pcb/temper.kicad_pro`. This is a genuine cross-domain pad pair —
the `AC Mains to LV` rule (6.0mm clearance / 8.0mm creepage) is the correct
rule to be checking it against, *if* the circuit behind it still existed.

**What R6 does, historically:** the top element of a 220k/220k/10k divider
(`R6`/`R7`/`R8`) stepping AC mains down through a 3.3V zener clamp (`D2`) to
drive an H11L1TVM optocoupler (`U3`) via a 430Ω LED resistor (`R9`), whose
SELV-side open-collector output was pulled up by `R10` (10k) and fed to the
MCU as a mains zero-crossing signal. Full BOM entries at
`docs/hardware/BOM.md:60-65`.

---

## 2. R6's circuit was deleted from the design three weeks before this task

`grep -rn "zcd" elec/src/*.ato` on this worktree's `main` tip returns
**nothing** — no `r_zcd_top1`, no `r_zcd_top2`, no `r_zcd_bot`, no
`zcd_opto`, no `d_zcd_clamp`. This is not an oversight in my search: it is
the documented, deliberate result of commit `5842767c2` ("fix(elec): delete
U3 (H11L1 mains-ZCD optocoupler) and its dedicated circuitry"), which **is**
an ancestor of the current `main` HEAD (`git merge-base --is-ancestor
5842767c2 HEAD` → true). `docs/evidence/2026-07-30-zcd-optocoupler-removal.md`
records the reasoning and the full component/net diff:

| Ref (pre-deletion) | Instance path | Part | Role |
|---|---|---|---|
| R6 | `power_in.r_zcd_top1` | 220k 1206 | HV divider top 1 |
| R7 | `power_in.r_zcd_top2` | 220k 1206 | HV divider top 2 |
| R8 | `power_in.r_zcd_bot` | 10k 0603 | HV divider bottom |
| D2 | `power_in.d_zcd_clamp` | BZT52C3V3 | 3.3V zener clamp |
| R9 | `power_in.r_zcd_opto` | 430R 0603 | Opto LED series resistor |
| U3 | `power_in.zcd_opto` | H11L1TVM | Optocoupler (the isolator) |
| R10 | `power_in.r_zcd_pullup` | 10k 0603, 1% | SELV pull-up |

The stated reasons (independently verifiable, not taken on the prior
session's authority alone): no firmware consumer of `PIN_ZCD_INPUT`, no
architectural role in a DC-bus resonant converter with time-delayed
soft-start, no wiring into `SafetyInterlock`/OCP/OVP/WDT, and — the reason
most relevant to *this* task — **U3's own isolation barrier was already an
unfixable violation**: 8.560mm HV↔SELV intra-footprint pad separation on a
DIP-6_W10.16mm package against a 12.6mm PD3 creepage target, with no
optocoupler family able to close that gap. The ZCD sensing scheme was
abandoned, not narrowed or re-packaged, and R6/R7/R8 went with it as the
divider that fed the now-deleted opto.

`elec/domain_manifest.yaml` confirms the same: `zcd`, `a`, and
`ZCD_ISO` are gone from every domain declaration; only historical comments
pointing at the removal doc remain (lines 104, 465-472, 628).

---

## 3. The board was never resynced on `main` — but the resync already exists elsewhere

`pcb/temper.kicad_pcb` (read-only throughout this task) still carries all
seven dead footprints, each labeled with the exact deleted instance path:

| Ref | `Sheetpath` property (read from `pcb/temper.kicad_pcb`) |
|---|---|
| R6 | `power_in.r_zcd_top1` |
| R7 | `power_in.r_zcd_top2` |
| R8 | `power_in.r_zcd_bot` |
| R9 | `power_in.r_zcd_opto` |
| R10 | `power_in.r_zcd_pullup` |
| D2 | `power_in.d_zcd_clamp` |
| U3 | `power_in.zcd_opto` |

This is the exact situation `2026-07-30-zcd-optocoupler-removal.md` itself
flagged as outstanding: *"`pcb/temper.kicad_pcb` still carries U3's DIP-6
footprint, R6/R7/R8/R9/R10, D2, and their copper... per the task's explicit
instruction to leave it alone."* That document lists the pending resync steps
verbatim: remove the seven footprints and their copper, re-run
`scripts/resync_pcb_netlist.py`, confirm `check_copper_net_consistency.py`
returns to 0, and re-measure `power_pcb_dataset/drc_ceiling.json` in the same
change per `AGENTS.md`'s codegen-adjacent-change convention.

**That work already happened, just not on `main`.** `git log --oneline --all
| grep -i zcd` surfaces a second commit, `70b843428` ("fix: reconcile board
after ZCD removal", 2026-07-30, same author), whose diffstat is exactly this:

```
pcb/temper.kicad_pcb                               | 5710 +++++++++-----------
power_pcb_dataset/drc_ceiling.json                 |   35 +-
.../requirements/safety/test_clearance_copper.py   |   12 +-
.../2026-07-30-zcd-optocoupler-removal.md          |   14 +-
.../2026-07-30-iec-60335-1-current-status.md       |   25 +
```

`git merge-base --is-ancestor 70b843428 HEAD` returns **false** — this
commit is reachable only from `origin/codex/handoff-actionables`, not from
`main`. Whatever integration step should have carried it across never ran.

---

## 4. Why this task does not widen R6's footprint

### 4.1 The task brief's premise needs a correction, made honestly

The task frames this as PR #1109's `R30` pattern: "a through-hole resistor...
1.80mm pad pitch... package choice." **R6 is not through-hole.** Its
footprint is `Resistor_SMD:R_1206_3216Metric` — the same generic,
IPC-7351-nominal 1206 land pattern used elsewhere on this board for `R51`
(`safety.ovp.r_div_top1`) and `R58`/`R56` (`safety.ovp.r_adc_top2`/`top1`).
1.80mm is simply the standard pad-to-pad gap of a 1206 chip resistor, not a
custom geometry someone chose and could "widen" the way `LitzPad_15A`'s
13.0mm→18.0mm pitch was widened in #1109. There is no single-part fix here
in the R30 sense: you cannot make a 1206 resistor's own two pads 6.0mm apart
and still call it a 1206 resistor. Any footprint fix would necessarily mean
a different, larger package (2512, or a leaded/axial part) or splitting the
divider into a chain — the same menu the task brief anticipated.

### 4.2 But the part behind that footprint doesn't need any of those options

All of Sec 4.1's menu (bigger package, different part, series chain like the
OVP divider's `r_div_top1/top2/top3`) is aimed at making a **live** mains
divider meet a clearance/creepage bar. R6 is not a live divider. Its
downstream circuit — R7, R8, D2, R9, U3, R10 — is deleted from
`elec/src/`, and the isolator it fed (U3) was independently confirmed
un-fixable at any footprint (Sec 2). Re-engineering R6's package to protect
a circuit that no longer exists would be exactly the "invented footprint"
the task's own rules warn against — solving a problem the design no longer
has, while leaving the actual defect (seven pieces of dead copper on a
committed board) unaddressed.

### 4.3 The honest fix, and why it isn't done here

The honest fix is the resync: delete R6, R7, R8, R9, R10, D2, and U3 (and
their copper/zones) from `pcb/temper.kicad_pcb`, matching what `70b843428`
already did on the unmerged branch, and re-measure
`power_pcb_dataset/drc_ceiling.json` in the same change per `AGENTS.md`.
That is a `pcb/temper.kicad_pcb` edit, which this task's brief explicitly
prohibits ("**Do not modify `pcb/temper.kicad_pcb`.**"). **No footprint
change is made in this PR.** The recommended follow-up is narrow and
already scoped by prior work: port (or cherry-pick, after review — the two
branches have diverged for two weeks) `70b843428`'s board edit onto `main`,
or re-run the resync tooling fresh against the current board.

---

## 5. Is 6.0mm the right clearance requirement for this pair? (Determination only — no value changed)

Independent of R6 being dead, the task asks whether `AC Mains to LV`'s
6.0mm clearance figure (`scripts/generate_kicad_dru.py:876-886`) is
correctly derived. It is worth answering because the same rule governs
every other `ACMains`↔LV pair on the board, and because the task flagged
that several 6.0mm figures in this repo trace to a citation
(`"IEC 60335-1 Table 16 working isolation at 400V"`) that
`docs/evidence/2026-08-12-hv-hv-creepage-determination.md` and three earlier
documents establish **does not exist** — Table 16 is indexed by rated
impulse voltage, not working voltage; 400V is not one of its rows; and
6.0mm is not one of its values (`docs/evidence/2026-07-28-creepage-determination-brainstorm.md:79-84`,
Table 16's full value set is `{0.5, 1.5, 3.0, 5.5, 8.0, 11.0}`).

**`AC Mains to LV`'s own comment does not use that exact debunked string** —
it cites `"IEC 60335-1 basic insulation for 240V AC"` — but this is a
different, equally unsupported citation for three independent reasons:

1. **Wrong insulation tier.** `docs/evidence/2026-07-28-creepage-determination-brainstorm.md`
   §2.2-2.3 (CITED-PRIMARY, clause 3.4.4) determines directly: the LV/SELV
   domain here is earthed (`elec/src/main.ato:475`, `gnd ~ pe`), making it a
   PELV circuit, and *"reinforced insulation... [is] required for every
   lateral mains↔PELV crossing."* `AC Mains to LV`'s comment says "basic,"
   not reinforced.
2. **Wrong voltage.** 240V is not this board's mains voltage. `v_ac_nominal
   = 120V` with `assert v_ac_nominal within 100V to 130V` (NEMA 5-15
   tolerance) at `elec/src/main.ato:52,56` — this is a single-market,
   120V-nominal design, not a 240V one.
3. **A correctly-derived number for exactly this crossing already exists
   in the same file, wired to the wrong rule.** `HV_INTERNAL_CLEARANCE_MM`
   (`scripts/generate_kicad_dru.py:59-67`) is computed as: rated voltage
   120V → Table 15 row ii, OVC II (cl. 29.1, CITED-PRIMARY: *"Appliances are
   in overvoltage category II"*) → rated impulse voltage 1500V → Table 16
   basic clearance at 1500V = 0.5mm → clause 29.1.3's reinforced "next
   higher step" (CITED-PRIMARY: *"using the next higher step for rated
   impulse voltage as a reference"*) → 2500V row = 1.5mm → clause 29.1's
   +0.5mm soldered-construction adder (this is a soldered PCB, one of the
   clause's own named examples) → **2.0mm**. Its own comment self-describes
   this exact figure as *"Fail-closed reinforced clearance for the
   mains↔PELV barrier, uncoated"* — i.e., this constant already **is** the
   AC-Mains-to-LV reinforced clearance requirement, correctly derived and
   cited — but it is plugged into the `HV internal same footprint` rule
   (same-HV-domain pairs only) rather than `AC Mains to LV`.

Under this repo's own cited derivation, the reinforced clearance
requirement for R6's pair (had R6 still been live) would be **2.0mm, not
6.0mm** — a finding of the same shape as the fix `netclass_rules.yaml`
already applied to `HighVoltage` on 2026-08-12 (clearance corrected from a
debunked 6.0 to a cited 2.0), but **not yet applied** to `ACMains`: its
`class:` entry (`netclass_rules.yaml:12-21`) and all nine `ACMains-*`/
`HighVoltage-*` `class_pairs` entries (lines 204-212) still carry the exact
debunked `"IEC 60335-1 Table 16 working isolation at 400V"` citation,
unfixed.

**This does not mean 6.0mm is simply wrong and should become 2.0mm.**
Creepage is the historically dominant constraint in every prior
determination in this repo (clearance ~2mm, creepage 6.3-12.6mm for
comparable HV↔LV crossings), and `AC Mains to LV`'s own creepage figure
(`HV_CREEPAGE_ENFORCED_MM = 8.0mm`, PD2) is derived from Table 17 **row iv
(>250-400V)** — the DC-bus/`HighVoltage` voltage band, not the ~120-130V
`ACMains` band, which would land in row ii or iii (1.5-5.0mm reinforced
depending on which side of the 125V boundary the 130V worst case falls).
Re-deriving the *correct* row for `ACMains` specifically, and reconciling
the clearance and creepage figures together, is exactly the kind of
board-wide, safety-critical change this repo's convention (see
`2026-08-12-hv-clearance-adequacy.md`, `2026-08-12-hv-hv-creepage-determination.md`
— both land a determination and change zero values) says should get its
own dedicated review rather than being folded into an R6-shaped task. **No
value in `scripts/generate_kicad_dru.py` or `netclass_rules.yaml` is
changed by this PR.** Flagged as a determination for a follow-up PR.

---

## 6. Sweep: intra-component pad pairs on different domains, across the whole board

Method: `docs/evidence/2026-08-12-dru-rule-precedence-violations.csv` (1291
data rows, the uncapped, corrected-precedence violation set measured for PR
#1110/#1111) filtered to `kind_a == "Pad" and kind_b == "Pad"` and
`components` containing exactly one reference (no comma) — i.e., both
violating pads belong to the same footprint, the R30/R6 shape. Not
re-measured fresh: no board content changed in this task, so there is
nothing for a new DRC pass to find that this dataset doesn't already show,
and re-running the full uncapped sweep (which is itself a multi-minute,
many-`kicad-cli`-invocation process) would reproduce the same numbers.

**12 rows, 10 distinct components:**

| Component | Sheetpath | Rule | Required | Actual | Deficit | Status |
|---|---|---:|---:|---:|---:|---|
| R6 | `power_in.r_zcd_top1` | AC Mains to LV | 6.0mm | 1.8mm | 4.2mm | **dead** (Sec 2-3) |
| R7 | `power_in.r_zcd_top2` | HV to LV | 2.0mm | 1.8mm | 0.2mm | **dead** |
| R8 | `power_in.r_zcd_bot` | HV internal same footprint | 2.0mm | 0.85mm | 1.15mm | **dead** |
| R9 | `power_in.r_zcd_opto` | HV internal same footprint | 2.0mm | 0.85mm | 1.15mm | **dead** |
| C23 | `hb.c_vddb` | HV internal same footprint | 2.0mm | 0.65mm | 1.35mm | live |
| R24 | `hb.gate_hs.rgs` | HV internal same footprint | 2.0mm | 0.85mm | 1.15mm | live |
| U7 (×3) | `hb.gate_hs.driver` | HV to LV | 2.0mm | 0.67mm | 1.33mm | live, previously tracked |
| U8 | `hb.gate_hs.boot_diode` | HighVoltageIsolated same side | 2.0mm | 1.5mm | 0.5mm | live |
| R51 | `safety.ovp.r_div_top1` | HV to LV | 2.0mm | 1.8mm | 0.2mm | live |
| R56 | `safety.ovp.r_adc_top1` | HV to LV | 2.0mm | 1.8mm | 0.2mm | live |

Cross-checked directly against `pcb/temper.kicad_pcb`'s own pad coordinates
for R6, R7 (both 1206, gap = `(1.4625−0.5625)−(−1.4625+0.5625) = 1.8mm`
exactly) and R8, R9 (both 0603, gap = `(0.825−0.4)−(−0.825+0.4) = 0.85mm`
exactly) — all four match the CSV to the reported precision.

**Four of ten (R6, R7, R8, R9) are the same dead ZCD circuit** (Sec 2-3) —
not four independent design defects, one root cause counted four times. This
matters for "is this a class worth a gate": it is not "R30 plus one," it is
"R30 plus a stale-board detector that would have caught R6/R7/R8/R9 for
free" — a `check_copper_net_consistency.py`-style gate (already exists,
already flags this exact desync as `FAILED — exit 3, 402 violations` per
`2026-07-30-zcd-optocoupler-removal.md`) is arguably the more
leveraged fix than any per-footprint one.

**Six of ten (C23, R24, U7, U8, R51, R56) are live and worth naming
precisely, but out of this task's scope (none is R6, none is mains-crossing —
`U7` and `U8` are `HighVoltage`↔`HighVoltage`/`HighVoltageIsolated`
same-domain functional pairs, `R51`/`R56` are same-domain OVP/ADC divider
links, `C23`/`R24` are gate-drive same-domain pairs):**

- **`U7`** (the UCC21550 isolated gate driver, `SOIC16W_Isolated`) is a
  **previously tracked** intra-footprint gap —
  `packages/temper-placer/tests/requirements/safety/test_clearance_copper.py::test_the_seven_known_intra_footprint_blockers_are_now_visible`
  already carries U7 in its historical `{"C6","K1","K2","K3","T1","U3","U7"}`
  set (now empirically cleared to `intra == set()` as of the 2026-08-02 K3
  swap, per that test's own docstring) — not a new finding, but the CSV's
  `HV to LV` **clearance** rows (0.67mm, ×3) are a different constraint
  dimension than the **creepage** figure (8.100mm, cleared) that test
  checks, so U7 may still be worth a fresh look at clearance specifically.
  Not investigated further here — out of scope for an R6 task.
- **`R51`/`R56`** (`safety.ovp.r_div_top1`/`r_adc_top1`, both 1206) miss the
  same-domain 2.0mm `HV internal same footprint` bar by exactly 0.2mm —
  identical shape to R6/R7's *own* same-domain shortfall, and a reminder
  that PR #1106's series-chain fix for the OVP divider addressed the
  mains-to-LV reinforced crossing but did not close the smaller, same-domain
  functional-insulation gap each individual 1206 link still carries. Given
  Sec 5's finding that the *interpolated* (not step-rounded) reading of the
  same clause gives 1.75mm for a comparable pair
  (`2026-08-12-hv-clearance-adequacy.md` §3.1), this 0.2mm gap sits close to
  the boundary between "genuine shortfall" and "rounding convention" and
  deserves its own determination, not a reflexive footprint swap.
- **`C23`/`R24`** (`hb.c_vddb`, `hb.gate_hs.rgs`) are new-to-this-sweep,
  unflagged elsewhere as far as could be found in this session — worth a
  dedicated look, not fixed here.

---

## 7. Measurement summary

- **R6 gap, before:** 1.80mm (measured from `pcb/temper.kicad_pcb` pad
  geometry directly; matches the cited CSV exactly).
- **R6 gap, after:** **1.80mm — unchanged.** No footprint was widened, no
  part was swapped, `pcb/temper.kicad_pcb` was not opened for writing.
  Sec 4 explains why: R6 is dead, and the fix that applies to a dead
  component is deletion (a board edit this task is scoped not to make), not
  a wider package.
- **`scripts/verify_pumpkin_engine.py`**: not run. It gates a *solve*
  (placement/routing re-optimization); this task performs no solve and
  writes no board, so there is nothing for it to verify.
- **Placement / isolation-barrier feasibility (PD2/8.0mm, all 8 isolators,
  #1082 heatsink co-location):** not re-checked, because nothing that could
  perturb placement changed. These remain exactly as they were on `main`
  before this task.
- **Sweep:** 12 intra-component pad-pair violations, 10 distinct components,
  4 attributable to one root cause (the unresynced dead ZCD divider), 6
  live and out of scope. Full table in Sec 6.

---

## 8. What remains

1. **Land the board resync.** Either cherry-pick/rebase `70b843428`'s
   `pcb/temper.kicad_pcb` + `power_pcb_dataset/drc_ceiling.json` edit onto
   `main` (after review — two weeks of drift on both branches), or re-run
   the resync fresh: delete R6/R7/R8/R9/R10/D2/U3 and their copper, run
   `scripts/resync_pcb_netlist.py`, confirm `check_copper_net_consistency.py`
   returns to 0, re-measure `power_pcb_dataset/drc_ceiling.json` in the same
   change per `AGENTS.md`. This clears R6, R7, R8, R9 from the sweep in
   Sec 6 as a side effect, for free.
2. **Prune `docs/hardware/BOM.md`.** Lines 60-65 still list `R_ZCD_TOP1/TOP2`,
   `R_ZCD_BOT`, `D_ZCD_CLAMP`, `U_ZCD_OPTO`, `R_ZCD_OPTO`, `R_ZCD_PULLUP` as
   active BOM entries; line 89's own note anticipates this ("if/when that
   lands, this BOM subsection... must be pruned in the same change"). The
   source-side deletion already landed (`5842767c2`); the BOM note is now
   stale in the other direction.
3. **Re-derive `AC Mains to LV`'s clearance and creepage figures for the
   actual ~120-130V mains band**, not the 250-400V DC-bus band the current
   8.0mm creepage figure borrows, and reconcile `netclass_rules.yaml`'s
   `ACMains` class + its nine `class_pairs` entries off the debunked "Table
   16 at 400V" citation the same way `HighVoltage` was already corrected on
   2026-08-12. Sec 5 is a determination, not a fix; this is real,
   board-wide-impact work that deserves its own dedicated PR and review.
4. **Consider a gate for the class this sweep surfaced**: any footprint
   whose `Sheetpath` no longer resolves to a live `elec/src/` instance path
   is exactly the condition that produced four of Sec 6's ten findings.
   `check_copper_net_consistency.py` already detects this category of
   desync (it failed with 402 violations the moment R6-R10/U3/D2 were
   deleted from source); the gap is that its failure did not block this
   specific board from staying on `main` un-resynced for two weeks.

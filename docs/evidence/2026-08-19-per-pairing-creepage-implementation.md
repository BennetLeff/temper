<!-- provenance: branch worktree-agent-aa75e0e19860271a2, based on origin/main tip eb5022510.
     pcb/temper.kicad_pcb sha256 = 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b,
     verified identical before and after this session -- never opened for write.
     elec/**/*.ato read only. power_pcb_dataset/drc_ceiling.json untouched. No pinned
     `_*_py_oracle.py` oracle was deleted, consolidated or re-pinned.
     Environment: `make venv-isolate` under `env -u CONDA_PREFIX` before any measurement;
     temper-design-bundle's pyo3 extension rebuilt (`maturin develop --release`) after the
     Rust change, so no measurement here ran against a stale .so.
     Standards basis: docs/evidence/2026-08-19-table-17-row-determination-hv-selv.md
     (commit 0cbc04248). No standards value is reconstructed here; where a requirement is
     not obtainable, that is what is recorded. -->

# Per-pairing creepage: replacing `MIN_BARRIER_WIDTH_MM = 12.6` with a derived requirement — four figures went DOWN, two went UP, and nine pairings have no requirement at all

## Verdict up front

`MIN_BARRIER_WIDTH_MM = 12.6` is gone. Every creepage requirement on this board is now
**derived per pairing** from a declared, dated, digest-anchored working voltage, through the
recovered IEC 60335-1 Table 17/18 in `packages/temper-design-bundle/src/safety_value.rs`.

**Both directions landed.** The DC-bus and mains crossings came down; the resonant-tank
crossing went up, and the single geometric barrier went up with it:

| enforcement point | before | after | direction |
|---|---|---|---|
| `isolation_constants.MIN_BARRIER_WIDTH_MM` | 12.6 mm | **20.0 mm** | **UP** |
| `isolation_barrier.DEFAULT_CORRIDOR_WIDTH_MM` | 13.1 mm | **20.5 mm** | **UP** |
| DRU `"AC Mains to LV"` creepage | 12.6 mm | **4.8 mm** | down |
| DRU `"HV to LV"` creepage | 12.6 mm | **20.0 mm** | **UP** |
| DRU `"HighVoltageTank to LV"` creepage | 12.6 mm | **20.0 mm** | **UP** |
| DRU `"HighVoltageSignal to LV"` creepage | 12.6 mm | **8.0 mm** | down |
| DRU `"HighVoltageIsolated to LV"` creepage | 12.6 mm | **8.0 mm** | down |
| `gates.py` `HV_LV_CREEPAGE_MM` | 12.6 mm (one scalar) | **removed** — per net pair | both |

**And nine of the fifteen pairings have no requirement at all.** They run at 47 kHz, above
IEC 60664-1 cl. 1.1.1's 30 kHz scope ceiling; cl. 2.3 routes dimensioning above it to
IEC 60664-4, which is paywalled and was not obtained. They are represented as explicitly
indeterminate, carry a `NaN` requirement and a *proven lower bound*, and **cannot produce a
PASS from any consumer at any measured distance**. `scripts/check_insulation_pairings.py`
exits 6 for them and will do so on every CI run until that standard is obtained or the
design changes.

---

## 1. The per-pairing table as implemented

Read directly out of `elec/insulation_manifest.yaml` through the Rust rule
(`docs/evidence/2026-08-19-per-pairing-creepage-measure.py` §1). PD3, material group
IIIa/IIIb throughout.

| pairing | class | V r.m.s. | f (Hz) | table | row | required | floor |
|---|---|---|---|---|---|---|---|
| `MAINS<->SELV` | reinforced | 120.0 | 60 | 17 | `>50-125` (ii) | **4.8 mm** | 4.8 |
| `DC_BUS<->SELV` | reinforced | 170.0 | 0 | 17 | `>125-250` (iii) | **8.0 mm** | 8.0 |
| `SELV<->SWITCHING` | reinforced | 170.0 | **47 000** | 17 | `>125-250` | **NOT DETERMINABLE** | 8.0 |
| `SELV<->TANK` | reinforced | 570.5 | **47 000** | 17 | `>500-800` (vi) | **NOT DETERMINABLE** | **20.0** |
| `DC_BUS<->DC_BUS` | functional | 340.0 | 0 | 18 | `>250-400` (iii) | **5.0 mm** | 5.0 |
| `DC_BUS<->MAINS` | functional | 340.0 | 60 | 18 | `>250-400` | 5.0 mm | 5.0 |
| `MAINS<->MAINS` | functional | 120.0 | 60 | 18 | `>50-125` | 2.2 mm | 2.2 |
| `SELV<->SELV` | functional | 15.0 | 0 | 18 | `<=50` | 1.8 mm | 1.8 |
| `DC_BUS<->SWITCHING` | functional | 340.0 | **47 000** | 18 | `>250-400` | **NOT DETERMINABLE** | 5.0 |
| `MAINS<->SWITCHING` | functional | 340.0 | **47 000** | 18 | `>250-400` | **NOT DETERMINABLE** | 5.0 |
| `SWITCHING<->SWITCHING` | functional | 340.0 | **47 000** | 18 | `>250-400` | **NOT DETERMINABLE** | 5.0 |
| `DC_BUS<->TANK` | functional | 570.5 | **47 000** | 18 | `>500-800` (v) | **NOT DETERMINABLE** | 10.0 |
| `MAINS<->TANK` | functional | 570.5 | **47 000** | 18 | `>500-800` | **NOT DETERMINABLE** | 10.0 |
| `SWITCHING<->TANK` | functional | 570.5 | **47 000** | 18 | `>500-800` | **NOT DETERMINABLE** | 10.0 |
| `TANK<->TANK` | functional | 570.5 | **47 000** | 18 | `>500-800` | **NOT DETERMINABLE** | 10.0 |

Barrier floor = **20.0 mm**, set by `SELV<->TANK`. Barrier determinable = **False**.

### 1.1 What is declared and what is derived

**Declared** (`elec/insulation_manifest.yaml`, each with a cited basis): five net groups
(`MAINS` 6 nets, `DC_BUS` 11, `SWITCHING` 8, `TANK` 2, `SELV` 35 — 62 nets, exactly the HV
+ SELV domains of `elec/domain_manifest.yaml`), each group's rated frequency, and each
**pairing's** long-term r.m.s. working voltage.

**Derived** (`packages/temper-design-bundle/src/insulation.rs`): the insulation class
(cross-domain → reinforced, same-domain → functional, cl. 3.3.5), the table row (IEC 60664-1
cl. 3.2.1.1 — the r.m.s. value selects the row), the ×2 for reinforced (cl. 29.2.3), and
whether the result is a requirement or only a bound.

Working voltage is declared **per pairing, not per net**, because cl. 3.1.3 defines it as
the voltage *"to which the part under consideration is subjected"* — a property of a pair.
`+170V_BUS` is 170 V against SELV and 340 V against `DC_BUS_RTN`; `max(170, 170)` gets the
rail-to-rail case wrong by a factor of two.

Insulation class is **derived, never declared**: a declaration that could name the class
could downgrade a barrier crossing to functional — halving its requirement — without
changing any physical claim.

### 1.2 One deliberate deviation from the determination's own table — in the strict direction

`docs/evidence/2026-08-19-table-17-row-determination-hv-selv.md` §6.1 records pairing 8
(tank ↔ bus rails) as *"Table 18, row v, 10.0 mm"*, determinate. **This implementation marks
it NOT DETERMINABLE with a 10.0 mm floor**, because the same document's §6.2 says *"every
net that floats on the switch node or the tank"* is above the 30 kHz ceiling, and the tank
is the tank. The two statements are inconsistent; the self-consistent reading is the
stricter one, and this is the only place this implementation departs from that document.
It **never lowers** anything relative to it. Flagged here rather than absorbed.

Similarly, §6.1's pairing 6 (`SELV<->SWITCHING`) is recorded as not determinable with **no
floor named**. This implementation derives an 8.0 mm floor for it by applying the *same*
method that document applies to its pairing 7. The floor is labelled a bound everywhere it
appears and is never presented as a requirement.

### 1.3 What was NOT implemented, and why that is safe

Annex L's clearance-comparison step (*"compared with the corresponding clearance of Table 16
and enlarged if necessary"*) is deliberately not implemented. Table 16 is keyed to **rated
impulse voltage**, and the working-voltage → rated-impulse mapping (Table 15) is not
recovered in this repository for every pairing, so computing the step would mean inventing
an input. It is non-binding regardless: at 120 V nominal / 1500 V rated impulse, the
recovered Table 16 basic clearance is 0.5 mm and even the reinforced step plus the
soldered-construction adder is 2.0 mm (`HV_INTERNAL_CLEARANCE_MM`), below every creepage
figure derived here (smallest: 1.8 mm; smallest cross-barrier: 4.8 mm). Stated rather than
silently skipped.

---

## 2. The mechanism

Follows `feat/enclosure-declaration-derives-pd`'s pattern exactly — declare facts, derive
consequences, fail closed on missing evidence — and reuses its shapes rather than inventing
new ones (same `verification:` block, same content-digest staleness rule, same "no pyo3 in
the core" split, same "the honest limitation is one call away from the number" discipline).

```text
elec/insulation_manifest.yaml          declared groups, frequencies, per-pairing
                                        working voltages, each with a cited basis;
                                        verification.declared_state_sha256 covers all
                                        of it including every `basis` string
  -> packages/temper-design-bundle/src/insulation.rs      THE RULE (Rust, no pyo3 in core)
       insulation_class_for(a, b)        cl. 3.3.5
       voltage_range_for(v_rms)          IEC 60664-1 cl. 3.2.1.1
       table_17_lookup / table_18_lookup recovered tables (safety_value.rs)
       creepage_reinforced()             cl. 29.2.3
       frequency_in_scope(f)             IEC 60664-1 cl. 1.1.1 (30 kHz)
    -> Requirement::Determined | Requirement::IndeterminateWithFloor
  -> temper_placer.core.insulation_coordination           the thin loader
  -> every consumer
```

**Fail-closed, in Rust, with no fallback anywhere**: empty, unparseable, unknown-key
(including a hand-written requirement), unsupported schema version, placeholder verification
field, malformed commit anchor, **stale** (a working voltage or a group membership edited
after the digest that backs it), empty group, missing `basis`, a net in two groups, a
working voltage above the highest transcribed row, and — the one that matters most — **any
unordered pair of groups, including self-pairs, with no declared pairing**. There is no
default pairing. 22 unit tests, all also registered in the wasm test registry.

### 2.1 Why `Requirement` has two shapes

```rust
pub enum Requirement {
    Determined(SafetyValue),
    IndeterminateWithFloor { requirement: SafetyValue, floor: SafetyValue },
}
```

* `requirement_mm()` on an indeterminate pairing returns **`NaN`**, not a number. Every
  `measured >= NaN` is `false`, which is the fail-closed direction.
* `enforceable_floor_mm()` is a *proven lower bound* — the `<=30 kHz` table figure, i.e.
  what the requirement would be if the pairing were in scope. It is what a geometric
  constraint should be built from, and clearing it is **not** compliance.
* `grade(measured)` is three-valued and **there is no input for which an indeterminate
  pairing returns `Pass`** — pinned by
  `insulation::tests::indeterminate_never_passes_at_any_distance`, which asserts it over
  measurements from 0 mm to 10⁹ mm.
* `Verdict::is_pass()` returns `false` for `Indeterminate`, so no consumer has to remember
  the rule.

### 2.2 The one literal, and why it is a seam

`insulation_coordination.ENFORCED_POLLUTION_DEGREE = 3` is the only new literal. Pollution
degree belongs to the **enclosure**, not the netlist, so `insulation.rs` takes it as an
*input* and does not read it — which keeps this module composable with
`feat/enclosure-declaration-derives-pd` instead of holding a second copy of that branch's
answer. `scripts/check_insulation_pairings.py` cross-checks it against
`generate_kicad_dru.py`'s own PD selector line on every run. When that branch lands, the
constant is deleted and replaced by `resolve_declaration().pollution_degree`.

---

## 3. Each consumer, before and after

| consumer | before | after | measured how |
|---|---|---|---|
| `packages/temper-placer/src/temper_placer/core/isolation_constants.py` | `MIN_BARRIER_WIDTH_MM = 12.6` (literal) | `= _barrier_floor_mm()` → **20.0**, plus new `MIN_BARRIER_WIDTH_IS_DETERMINATE = False` | gate §"Enforcement points" |
| `scripts/check_isolation_keepout.py` | required width 12.6 mm; `clean` → prints `PASSED`, exits 0 | required width 20.0 mm; prints the four barrier-crossing pairings and their rows; **`clean` + indeterminate → prints `INDETERMINATE`, exits new `EXIT_INDETERMINATE = 6`, never `PASSED`** | run on the real board |
| `packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py` | `DEFAULT_CORRIDOR_WIDTH_MM = 13.1` | **20.5** (derived, no line changed — the "computed, not restated" note did its job) | gate §"Enforcement points" |
| `packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py` | `HV_LV_CREEPAGE_MM = 12.6`, one scalar for every violation; `_is_hv_net` a hardcoded 7-name frozenset | constant **removed**; each violation graded against its own net pair's pairing, with `context["pairing"]` and `context["determinable"]`; `_is_hv_net` reads the net-exact declaration; **zero violations + indeterminate → `UNMEASURED`, never `CLEAN`** | 8 new tests |
| `scripts/generate_kicad_dru.py` | five rules all at `HV_CREEPAGE_ENFORCED_MM` = 12.6 | five per-class figures (4.8 / 20.0 / 20.0 / 8.0 / 8.0), each emitted with its governing pairing and, where applicable, a "PROVEN LOWER BOUND ONLY" note | regenerated DRU + projections |
| `packages/temper-placer/configs/pair_creepage.generated.yaml` | every HV↔LV class pair 12.6 | `ACMains|*` 4.8; `*|HighVoltage` and `*|HighVoltageTank` 20.0; `*|HighVoltageSignal` and `*|HighVoltageIsolated` 8.0 | regenerated |
| `packages/temper-placer/configs/zone_pour_creepage.generated.yaml` | same | same, follows automatically | regenerated |

### 3.1 The net-class reduction, and the one place it blunts the improvement

KiCad's DRU language has no notion of safety domain, so a `"<HV class> to LV"` rule must
take the **worst member pairing** of its class — `max` over floors, `all` over
determinability. Conservative by construction: no pairing ends up below its own figure.

**`HighVoltage` is the casualty.** `TEMPER_NET_ASSIGNMENTS` puts `PWR_RTN` (120 V),
`+170V_BUS`/`DC_BUS_RTN`/`hb-gnd` (170 V d.c.), `SW_NODE` (47 kHz) **and `tank-out`
(570.5 V r.m.s.)** all in that one class, so its rule must carry 20.0 mm — it goes **up**,
not down, even though its DC-bus members earn 8.0 mm. The per-pairing reduction is real
everywhere nets are visible (the keepout gate, `gates.py`, the pad-pair census); it is
blunted only where the consumer can see nothing finer than a net class.

**Not fixed here, and flagged rather than done:** moving `tank-out` into the
`HighVoltageTank` net class would let `HighVoltage` fall to 8.0 mm. That is a net-class
re-partition — it changes `pcb/temper.kicad_pro`'s `netclass_assignments` and interacts
directly with `fix/netclass-tables-reconcile`, which is already reconciling those two
tables. It is a one-line change with a routing blast radius, and it belongs to whoever owns
that branch.

### 3.2 A fifth enforcement point exists and was deliberately NOT touched

`packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`'s
`IEC60335_REQUIREMENTS[(DC_BUS, LV_CONTROL, REINFORCED)]` carries `min_creepage_mm = 12.6`,
mirrored in `packages/temper-drc-rs/src/req_safe_01.rs` and **copied into the pinned oracle
`packages/temper-placer/tests/requirements/clearance_oracle/clearance.py:244`**.

Changing it would alter a pinned `_*_py_oracle`-family output. Per the standing rule, that
is a **STOP-and-report**, not a change to make in passing. It is the natural next step and
it is the last place `12.6` still lives as a safety figure on this branch.

---

## 4. The five blocking components, graded against their real pairings

Gap = exact, rotation-invariant, copper-to-copper package maximum (`pad_pair_distance`, the
same kernel the REQ-SAFE-01 validator and `check_isolation_keepout.py` use): the most
separation the part can offer at **any** placement and **any** rotation. Method reproduced
from `docs/evidence/2026-08-19-isolator-package-maxima.py`.

| ref | binding HV net | SELV net | pairing | gap | old (12.6) | new required | new |
|---|---|---|---|---|---|---|---|
| C6 | `PWR_RTN` | `gnd` | `MAINS<->SELV` | 8.000 | FAIL | 4.8 mm | **PASS** |
| K1 | `power_in.ntc-no` | `power_in.bypass_relay-coil1` | `MAINS<->SELV` | 8.000 | FAIL | 4.8 mm | **PASS** |
| U6 | `hb-gnd` | `+3V3` | `DC_BUS<->SELV` | 8.100 | FAIL | 8.0 mm | **PASS** |
| T2 | `hb-gnd` | `gnd` | `DC_BUS<->SELV` | 9.100 | FAIL | 8.0 mm | **PASS** |
| **T1** | **`tank-out`** | **`gnd`** | **`SELV<->TANK`** | **9.100** | FAIL | **≥20.0 mm, NOT DETERMINABLE** | **FAIL** |
| K2 | `discharge.k_dis1-nc` | `discharge.k_dis1-coil2` | `DC_BUS<->SELV` | 12.760 | PASS | 8.0 mm | PASS |
| K3 | `discharge.k_dis2-nc` | `discharge.k_dis1-coil2` | `DC_BUS<->SELV` | 12.760 | PASS | 8.0 mm | PASS |
| PS1 | `PWR_RTN` | `+15V` | `MAINS<->SELV` | 35.500 | PASS | 4.8 mm | PASS |

**Four pass and only T1 fails.** The task brief's hypothesis is confirmed on every row —
binding pair, measured gap and required figure.

**T1 got worse, not better.** Under the scalar it was short by 3.5 mm and looked like the
same class of problem as C6/K1/U6/T2. It is not: it is short by **at least 10.9 mm**, and
its true requirement is not obtainable at all. It is the only structurally impossible one,
and the other four were never real.

Two corrections to the brief's framing, both confirmed by direct reading rather than
assumption:

* **U6 is the UCC21550 gate driver**, not a bus part. Its `hb-gnd` pin is pin 9 (VSSB),
  which `elec/domain_manifest.yaml` calls *"low-side secondary ground, floats on
  `DC_BUS_RTN`"* — hence `DC_BUS<->SELV` at 8.0 mm, and its 8.100 mm gap passes by 0.100 mm.
  A gap of 0.1 mm against a derived figure is a pass, but it is not margin.
* **K1's SELV-side pin is the bypass relay's coil**, and its HV-side net
  `power_in.ntc-no` is the rectified mains node feeding the doubler
  (`elec/src/modules.ato:700-704`) — mains-referenced, so `MAINS<->SELV` at 4.8 mm, not the
  bus figure.

---

## 5. Board-wide effect

### 5.1 The 187 pad pairs

**Reproduced exactly, then re-measured.** `docs/evidence/2026-08-19-per-pairing-pad-census-before-after.py`
runs section 7 of `docs/evidence/2026-08-19-mechanism-a-analyze.py` (commit `6a6718a21`)
against both projections on one identical placement, and reproduces its **187 pairs over 74
nets** on the before table before reporting the after.

| | pad pairs below required creepage | nets involved |
|---|---|---|
| before (12.6 mm everywhere) | **187** | 74 |
| after (per-pairing) | **503** | 107 |
| delta | **+316** | +33 |

Attribution, per class pair — **every raise traces to the tank**:

| class pair | before | after | |
|---|---|---|---|
| `Default <-> HighVoltage` | 71 | 223 | **RAISED** (class contains `tank-out`) |
| `HighVoltage <-> Power` | 52 | 208 | **RAISED** (same) |
| `FinePitch <-> HighVoltage` | 15 | 37 | **RAISED** (same) |
| `GateDriveSELV <-> HighVoltage` | 0 | 0 | — |
| `Default <-> HighVoltageTank` | 2 | 12 | **RAISED** |
| `HighVoltageTank <-> Power` | 3 | 10 | **RAISED** |
| `FinePitch <-> HighVoltageTank` | 0 | 1 | **RAISED** |
| `Default <-> HighVoltageSignal` | 18 | 4 | lowered |
| `Default <-> HighVoltageIsolated` | 16 | 6 | lowered |
| `HighVoltageIsolated <-> Power` | 7 | 2 | lowered |
| `HighVoltageSignal <-> Power` | 3 | 0 | lowered |
| `ACMains <-> *` | 0 | 0 | lowered thresholds, no pairs either way |

**No threshold, ceiling, allowlist or expectation was adjusted to absorb this.**
`power_pcb_dataset/drc_ceiling.json` was not touched.

Centre-to-centre is an upper bound on the real copper-to-copper gap, so both counts are
lower bounds on the real violation count — the same caveat the original measurement states.

### 5.2 The exact HV↔SELV copper-to-copper census

Different measurement, different (larger) universe: all 109 HV pads × 237 SELV pads = 25 833
pairs, at exact copper-to-copper distance rather than centre-to-centre
(`2026-08-19-per-pairing-creepage-measure.py` §3).

| pairing | floor | determinable | pairs | below 12.6 (before) | below floor (after) | clears floor but INDETERMINATE |
|---|---|---|---|---|---|---|
| `DC_BUS<->SELV` | 8.0 | yes | 10 665 | 30 | **1** | 0 |
| `MAINS<->SELV` | 4.8 | yes | 7 110 | 42 | **3** | 0 |
| `SELV<->SWITCHING` | 8.0 | **no** | 6 636 | 39 | **4** | 6 632 |
| `SELV<->TANK` | 20.0 | **no** | 1 422 | 9 | **28** | 1 394 |
| **total** | | | 25 833 | **120** | **36** | 8 026 |

Read this carefully, because the two headline numbers point in opposite directions and both
are true:

* **Pairs failing a figure that is actually required fell 120 → 36 (−84).** The bus and
  mains crossings were over-charged; correcting them removed 68 of those.
* **Pairs failing on the tank crossing rose 9 → 28**, and the switch-node crossing rose
  0 → 4 against its own floor. That is the tank tightening, landing.
* **8 026 pairs clear their floor but can never be certified**, because their requirement
  does not exist. That count is dominated by pairs that are simply far apart; the number is
  formally correct and practically uninformative. The informative version is the 32 pairs
  (4 + 28) that fail a floor they cannot even be certified against.

### 5.3 The halo, and the "50" figure

`MIN_BARRIER_WIDTH_MM` 12.6 → 20.0 grows the HV halo:

| | halo area | SELV pads inside |
|---|---|---|
| 12.6 mm | 25 523 mm² | 26 / 237 |
| 20.0 mm | 39 111 mm² | **149 / 237** |

**A correction to the task brief.** There is no "50 unroutable nets" figure in this
repository (`git log --all -S"50 unroutable"` and `--grep` are both empty). The **50** is
from `docs/evidence/2026-08-19-mechanism-a-zero-copper-63-nets.md`: *"for 50 of the 63, at
least one of the net's own pads is unreachable on the pad's own layer because it sits inside
a foreign net's required creepage."* The denominator is 63 zero-copper nets, not 50
unroutable ones, and the current honest routing gap is **79 of 139** nets
(`eb5022510`/`d63219450`), not 50 or 70.

The halo those 50 nets are blocked by is the **router's** per-class halo
(`_astar_nlayer._stamp_foreign_creepage_halos`, radius = family static inflation +
`pair_creepage(searching class, obstacle class)`), which reads the projection this change
regenerates. Its stamped radius was 12.9–17.1 mm; with `HighVoltage`/`HighVoltageTank` at
20.0 mm it grows for exactly the classes that contain the tank, and shrinks for
`HighVoltageSignal`/`HighVoltageIsolated`. **Re-running that instrumented route was not
attempted here** — it needs three full production routes and is a separate measurement, not
a claim this change is entitled to make. The direction is knowable, the magnitude is not.

---

## 6. Interactions with the three pushed branches

* **`fix/netclass-tables-reconcile`** — no conflict; complementary, and it owns the fix for
  §3.1. It adds 7 HV-domain nets (`input`, `discharge.k_dis1-no`/`-no`, the `r_dis*`/
  `r_snub*` taps) to `TEMPER_NET_ASSIGNMENTS` as `HighVoltageSignal`. Every one of those is
  already declared in `elec/insulation_manifest.yaml`, so when that branch lands the
  per-class reduction picks them up automatically: `input` is `SWITCHING` (indeterminate,
  8.0 mm floor) and the rest are `DC_BUS` (8.0 mm), which is what `HighVoltageSignal`
  already resolves to. **No figure moves.** Its `--check` drift tripwire and the gate added
  here are the same pattern.
* **`fix/zone-pour-obstacle-set`** — no conflict; it consumes
  `zone_pour_creepage.generated.yaml`, which this change regenerates. Its per-pair zone
  carve will widen for tank-bearing classes and narrow for the signal/isolated classes,
  automatically. Its `CARVE_SNAP_COMPENSATION_MM = 0.001` remains correct at 20.0 mm.
* **`fix/wire-placer-constraints`** — no file conflict, one material interaction. It
  measured the isolation-barrier constraint as **INFEASIBLE at 12.6 mm and at 13.1 mm** on
  the committed floorplan, and concluded *"`MIN_BARRIER_WIDTH_MM` must not move"*. It is
  not less infeasible at 20.0/20.5 mm. **That conclusion is inverted by this determination:**
  the corridor was never the cause of the infeasibility — five isolation-bridging packages
  offer 8.0–12.8 mm of copper-to-copper separation at any placement, and T1 needs ≥20.0 mm
  from a 9.1 mm package. Narrowing the corridor cannot fix that and would only hide it. Its
  `dru_resolved_pairs=True` path takes `max(pair_clearance, pair_creepage)` from the same
  projections this change regenerates, so it inherits the new figures with no edit.

---

## 7. Gate results, all baselined against pristine `origin/main`

Every failure below was reproduced on a clean `origin/main` worktree at `eb5022510` with the
same interpreter before being attributed.

| gate / suite | pristine main | this branch | attribution |
|---|---|---|---|
| `scripts/tests/test_check_isolation_keepout.py` | 27 pass | **28 pass** | fixture derived from the SSOT instead of a `14.0` literal; one new guard test |
| `scripts/tests/test_generate_kicad_dru.py` | 35 pass | **35 pass** | 6 tests re-pointed from the removed scalar to the per-class figure |
| `scripts/tests/test_check_fact_registry_drift.py` | 1 fail (`hb_gnd` kicad_pro, KNOWN RED) | **same 1 fail** | 2 facts retargeted; no new failure |
| `scripts/check_fact_registry_drift.py` | exit 3, 4 TOOL ERRORs | **exit 3, 4 TOOL ERRORs** | identical |
| `scripts/check_creepage_clearance_drift.py` | exit 3 (`clearance/reinforced` family) | **exit 3, same family** | identical; the `creepage/reinforced` family lost its `MIN_BARRIER_WIDTH_MM` member because that literal is gone |
| `scripts/tests/test_check_pd2_compartment_evidence.py` | 2 fail | **same 2 fail** | pre-existing: its `_PD2_CONST_RE` expects a numeric literal, but `HV_CREEPAGE_PD2_MM` has been a `creepage_table_lookup` call since before this change |
| `packages/temper-placer/tests/.../test_physics_gate.py` | 6 fail (`No resolvable KiCad project`, sidecar), 15 pass | **same 6 fail, 24 pass** | pre-existing environment defect; 8 new tests added that stub `run_drc` one level in, so the per-pairing grading is genuinely covered |
| `scripts/check_manifest_gate.py` | pass | **pass** | new gate registered |
| **`scripts/check_insulation_pairings.py`** (new) | n/a | **exit 6, INDETERMINATE** | the finding itself |
| `scripts/check_isolation_keepout.py` | exit 3 (barrier zone absent) | **exit 3 (barrier zone absent)** | unchanged; the board still has no barrier keepout at all |

**No test was skipped, `xfail`ed, deleted or weakened. No assertion was relaxed. No ratchet
ceiling was raised. No allowlist was broadened. No `continue-on-error`, `|| true`,
`# type: ignore` or `# noqa` was added.** Where a test's *expectation* changed, it changed
because the derivation changed, and every such test now reads the figure from the derivation
rather than restating it — so the next re-derivation moves them for free.

---

## 8. What this does not close

1. **The 47 kHz requirement is unknown, not satisfied.** No amount of copper clears a
   requirement nobody has read. Closing it needs **IEC 60664-4**, or the **UL/CSA 6th
   Edition** text that the Intertek SUN records as having *"added requirements for minimum
   basic, supplementary, reinforced and functional insulation creepage distances for
   circuits operating at greater than 30 kHz"* into these same clauses. Both must be bought.
   This is the single highest-value purchase this project can make.
2. **The tank↔SELV working voltage has never been measured in this repository.** 570.5 V
   r.m.s. is a tank-to-**bus** figure carried forward from
   `docs/evidence/2026-08-12-hv-clearance-adequacy.md`. The determination's own inferred
   bound against earth is √(570.5² + 170²) ≈ 595.3 V r.m.s. — the same row, so the number
   does not move — but it is inferred, and the measurement is cheap.
3. **T1 is structurally impossible in its current package.** 9.1 mm of copper-to-copper
   separation against ≥20.0 mm. No placement, rotation or slot fixes it; it needs a
   different part or a different topology.
4. **The REQ-SAFE-01 matrix still carries 12.6** (§3.2), behind a pinned oracle.
5. **The PELV question from the determination's §7 remains open.** `gnd ~ pe` makes the LV
   domain PELV per cl. 3.4.4, which permits three separations of which reinforced is only
   one. This implementation derives reinforced for every cross-domain pairing, i.e. it takes
   the strictest of the three. Nothing here suggests dropping it.
6. **This mechanism cannot make a working voltage true.** It operates on a claim. It can
   ensure the claim is explicit, complete, internally consistent, digest-anchored and
   unchanged since it was verified. It cannot measure a circuit.

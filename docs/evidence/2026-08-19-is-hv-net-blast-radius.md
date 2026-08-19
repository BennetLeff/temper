# `is_hv_net()` blast radius: which consumer applies which separation to the five highest-energy nets

Date: 2026-08-19
Branch: `fix/hv-net-classification-blast-radius`, cut from `origin/main` @ `eb5022510`
Board measured: `pcb/temper.kicad_pcb`, sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`
— verified identical before and after every measurement below. The board
file was never written.
Toolchain: `kicad-cli` 10.0.5; worktree-private `.venv` provisioned by
`make worktree NAME=... VENV=1` (`make extensions-check` → 10/10 fresh).

---

## 0. Lead finding

**No live consumer of `is_hv_net()` decides a copper separation on this
board, and all five nets in the brief are classified correctly on every
path that does.**

The fab-authoritative DRU generator, the placer's `SEPARATED` constraint
generator, the router's decision-stage pair-clearance table, the router's
clearance verdict, the zone-pour carve tables and the tank-creepage
constraint all classify by **net class** — `TEMPER_NET_ASSIGNMENTS`,
`pcb/temper.kicad_pro`, `elec/domain_manifest.yaml` — not by
`is_hv_net()`. All five nets carry correct `HighVoltage` /
`HighVoltageTank` assignments in both tables, and `ac_l`/`ac_n` carry
correct `ACMains`. Section 1 is the table.

**Answering the question as asked — has a mains-adjacent conductor been
held to a functional or SELV separation rather than a reinforced one?**

* **Not through `is_hv_net()`, and not for these five nets.** The three
  `is_hv_net()`-family consumers that classify wrongly are (a) a gate that
  *detects* violations rather than setting separation, (b) a branch that is
  dead in production, and (c) an oracle whose pair table returns `0.2` for
  every pair regardless of class. Sections 3 and 4.
* **Yes, elsewhere, and it is pre-existing and already CI-red.** Seven
  HV-domain nets have **no netclass assignment at all** and fall to KiCad's
  `Default` class — 0.2 mm clearance, no creepage rule — on the
  fab-authoritative path. `scripts/check_hv_netclass_coverage.py` exits 3
  on pristine `origin/main` naming all seven. **Section 5.** None of them
  is one of the five in the brief.

---

## 1. Blast-radius table

"today" = what the consumer applies on `origin/main`. "correct" = what the
authoritative classifier gives. Clearances in mm.

| # | Consumer | Classifier it uses | `+170V_BUS` | `DC_BUS_RTN` | `hb-gnd` | `tank-out` | `tank.c_tank1-p2` | `ac_l` / `ac_n` | Correct today? | Live? |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `scripts/generate_kicad_dru.py` → `pcb/temper.kicad_dru` → `kicad-cli` DRC (**fab-authoritative**) | `kicad_pro.netclass_assignments` | HighVoltage | HighVoltage | HighVoltage | HighVoltage | HighVoltageTank | ACMains 6.0 | **yes** | yes |
| 2 | `placer/cp_sat/netclass_constraints.py` (placer `SEPARATED` constraints) | `get_rules_for_net()` (PR #1323) | 2.0 | 2.0 | 2.0 | 2.0 | 2.0 | 6.0 | **yes** | yes |
| 3 | `router_v6/pair_clearance.py` + `profile_grids` (router **decision** stage) | `configs/pair_clearance.generated.yaml`, keyed by net class | class-correct | ″ | ″ | ″ | ″ | ″ | **yes** | yes |
| 4 | `router_v6/clearance_check._get_required_clearance` (router verdict) | `elec/domain_manifest.yaml` HV domain ∨ `_is_hv_keyword_match` | HV | HV | HV | HV | HV | HV | **yes** | yes |
| 5 | `router_v6/_zone_pour_stitch._zone_layers_for_net` (zone-pour carve) | `TEMPER_NET_ASSIGNMENTS` / `TEMPER_NET_CLASSES` | eligible | eligible | eligible | eligible | eligible | eligible | **yes** | yes |
| 6 | `placer/cp_sat/tank_creepage.py` | `TEMPER_NET_ASSIGNMENTS` | — | — | — | — | HighVoltageTank 6.3 creepage | — | **yes** | yes |
| 7 | `placer/cp_sat/feedback._handle_clearance_violation` | `classify_net_type()` — net-name keywords | **Signal** | **Signal** | **GND** | **Signal** | **Signal** | **HighVoltage**, not ACMains | **NO** → fixed | **no — dead branch, see 3.2** |
| 8 | `placer/cp_sat/gates.IECCreepageGate._is_hv_net` | local 7-name frozenset | **not HV** | **not HV** | **not HV** | **not HV** | **not HV** | **not HV** | **NO** → fixed | yes (via `PhysicsGate`, `--all-gates`) |
| 9 | `router_v6/constraints_design_rules._classify_net` → `ClearanceMatrix` → `constraints_drc_oracle` | net-name keywords | Signal | Signal | GND | Signal | Signal | Signal | NO — but **inert**, see 4.1 | oracle only |
| 10 | `router_v6/_net_policy._should_route` (routing **eligibility**, not separation) | `router_v6` power/ground/hv predicates | recognised (power) | recognised (power) | recognised (ground) | **unrecognised** | **unrecognised** | recognised (hv) | see 4.2 | yes |
| 11 | `_astar_nlayer` / `_astar_reconstruct` `domain=` field, `bundle_analyzer`, `quality/via_count` | `classify_net_type` / `is_signal_net` | reporting + heuristics only; no separation | | | | | | n/a | yes |

Reproduce rows 7–11 and the raw predicate output:

```
cd <this worktree>
env -u CONDA_PREFIX ./.venv/bin/python \
    docs/evidence/2026-08-19-is-hv-net-blast-radius.py
```

Raw classifier output, freshly built `temper_io_types`:

```
net                      ground  power   hv  core_type  v6_type
+170V_BUS                     0      0    0     signal    power
DC_BUS_RTN                    0      0    0     signal    power
hb-gnd                        1      0    0     ground   ground
tank-out                      0      0    0     signal   signal
tank.c_tank1-p2               0      0    0     signal   signal
ac_l                          0      0    1         hv       hv
ac_n                          0      0    1         hv       hv
```

Authoritative net class for the same nets:

```
net                  TEMPER_NET_ASSIGNMENTS   get_rules_for_net().name   clr   creepage  cat
+170V_BUS            HighVoltage              HighVoltage                2.0   6.0       HV
DC_BUS_RTN           HighVoltage              HighVoltage                2.0   6.0       HV
hb-gnd               HighVoltage              HighVoltage                2.0   6.0       HV
tank-out             HighVoltage              HighVoltage                2.0   6.0       HV
tank.c_tank1-p2      HighVoltageTank          HighVoltageTank            2.0   6.3       HV
ac_l / ac_n          ACMains                  ACMains                    6.0   6.0       AC
```

---

## 2. Corrections to the premise — three of the brief's claims did not survive measurement

### 2.1 `hb-gnd` **is** recognised. The brief's reading came from a stale extension.

The brief states that inside `_should_route()`, `hb-gnd`, `tank-out` and
`tank.c_tank1-p2` "are not recognized as power, ground, OR high-voltage at
all". For `hb-gnd` that is **false on a correctly built extension**:

```
is_ground_net("hb-gnd") -> True
```

It reads `False` only against a **stale** `temper_io_types` `.so` built
before the 2026-08-13 hyphen-boundary fix. The shared `.venv` in the main
checkout still had exactly that stale build at the start of this session —
the failure mode `AGENTS.md` warns about, reproduced live:

| venv | `is_ground_net("hb-gnd")` |
|---|---|
| `/home/bennet/Desktop/temper/.venv` (shared, stale) | `False` |
| this worktree's own `.venv` after `make venv-isolate` | `True` |

Consequence for the brief's finding #2: of the three nets named, only
**`tank-out` and `tank.c_tank1-p2`** are genuinely unrecognised.
`hb-gnd` is recognised as ground, and — separately — `+170V_BUS` and
`DC_BUS_RTN` are recognised as **power** by `is_power_net_v6`, which is
the predicate `_net_policy` actually imports. So for four of the five nets
the zone-eligibility branch **is** consulted and `_should_route` returns
`False`; they do not fall through to A*. Measured:

```
+170V_BUS        recognised=1  zone_layers=[F.Cu,In3.Cu,In4.Cu,B.Cu]  should_route=False
DC_BUS_RTN       recognised=1  zone_layers=[...]                      should_route=False
hb-gnd           recognised=1  zone_layers=[...]                      should_route=False
tank-out         recognised=0  zone_layers=[...]                      should_route=True
tank.c_tank1-p2  recognised=0  zone_layers=[...]                      should_route=True
```

### 2.2 The case-sensitivity finding has a compensating mechanism — confirmed, two of them

The brief asked me to look for a compensating mechanism before concluding
`ac_l`/`ac_n` are unclassified. There is one, in both tables:

`pcb/temper.kicad_pro`'s `netclass_patterns` *are* uppercase (`AC_*`,
`DC_BUS*`) and do not match `ac_l`/`ac_n`. **They do not need to.** The
same file's `netclass_assignments` — which KiCad resolves *ahead of*
patterns — carries explicit lowercase entries, and so does
`core/design_rules.py`'s `TEMPER_NET_ASSIGNMENTS`:

```
"ac_l": "ACMains",
"ac_n": "ACMains",
```

Measured end-to-end: `ac_l`/`ac_n` → `ACMains`, clearance 6.0 mm, in
`get_rules_for_net()`, in `kicad_pro`, and therefore in the generated
`.kicad_dru` that `kicad-cli` enforces. **Nothing to add; no change made.**

A third, independent reason the premise does not bite: `is_hv_net` calls
`.upper()` on its input, so `is_hv_net("ac_l")` was already `True`. The
predicate was never case-sensitive.

The uppercase `AC_L` / `AC_N` / `DC_BUS+` / `DC_BUS-` keys that *do* appear
in those tables are ghosts —
`scripts/check_hv_netclass_coverage.py` PROPERTY 5 lists all 39 such keys
as "has a kicad_pro netclass assignment but no real board net".

### 2.3 Consumer #7 was not applying a loose figure — it was raising

My own first-pass write-up said `feedback.py` "injected 0.15 mm" for the DC
bus. That is wrong and is corrected in 3.2: it *computed* 0.15 mm and then
raised `ValueError` before injecting anything, and the branch is dead in
production anyway.

---

## 3. What was fixed, with before/after numbers

### 3.1 `IECCreepageGate._is_hv_net` — recognised 1 of 27 HV nets

Was `return name in _HV_NET_PATTERNS`, a local 7-name frozenset. Measured
against the board's 162 real net names:

* **6 of the 7 names do not exist on this board at all** — `DC_BUS+`,
  `DC_BUS-`, `SW_NODE_DC+`, `SW_NODE_DC-`, `AC_L`, `AC_N`. Only `SW_NODE`
  does.
* The mains conductors are spelled `ac_l`/`ac_n`; the DC bus is
  `+170V_BUS`/`DC_BUS_RTN`.
* So the predicate recognised **1 of the 27 nets
  `elec/domain_manifest.yaml` declares HV-domain** — all 27 of which are
  present on the board.

**Fix.** Check the 7-name set first (never narrow), then
`elec/domain_manifest.yaml` + `_is_hv_keyword_match` — the identical
string-only classifier `router_v6/clearance_check._get_required_clearance`
already uses, needing no `DesignRules` instance. This takes the repo from
four independently maintained HV classifiers to three, and introduces no
net list and no safety figure of its own.

> The 2026-08-17 evidence doc
> (`2026-08-17-netclass-classifier-manifest-and-ieccreepagegate-liveness.md`
> §2) flagged this and left it unfixed on the stated ground that
> reconciling it "requires threading a `DesignRules` instance into a
> function that currently has none available". **That premise was wrong** —
> `clearance_check` answers this exact question from a bare string.

Applying the gate's own filter to the real DRC report (776 violations: 179
`clearance`, 106 `creepage`, …):

| | HV↔LV `clearance` pairs the gate reports |
|---|---|
| before | **1** — `SW_NODE` vs `hb.power_loop.q_high-g`, and this is a **false positive**: both are declared HV-domain, i.e. a same-domain pair |
| after | **2** — `+170V_BUS` vs `safety.ovp.r_div_top1-p2`, `+170V_BUS` vs `safety.ovp.r_adc_top1-p2` |

Honest reading of the two new ones: those OVP-divider mid-chain nodes are
**deliberately unclassified** by the manifest, whose own single-fault
analysis records that they "reach the FULL +170V_BUS potential (170.0 V
exactly)" under the IEC 60335-1 cl. 8.1.4 fault. They are not SELV. So this
is not "two new mains-to-touchable crossings"; it is the gate surfacing two
pairs it could not previously see, in place of one it should never have
raised. Direction is strictly toward the truth.

### 3.2 `feedback._handle_clearance_violation` — misclassifying *and* crashing *and* dead

Three separate facts, measured, in order of importance:

**(a) The branch is dead in production.** The only DRC-violation type the
router produces — `router_v6/_adapter_types.py::DrcViolation` — has fields
`net_name`, `message`, `location`, `comp_a`, `comp_b`, `required_mm`,
`components`, `count`, `type`. It has **no `net_a`/`net_b`**. The whole
net-classification branch is guarded by
`if net_a and net_b:` with `getattr(violation, "net_a", None)`, so on the
production path it is never entered. It is reachable from tests and from
any future violation object that carries net names.

**(b) On `origin/main` it raises rather than injecting anything.** Both
`because` assignments in the branch could yield the empty string
(`.get("because", "")`, and a bare `else: because_text = ""` for every
class pair absent from `class_pairs`), and `SeparatedConstraint` rejects a
rationale under 10 characters. `FeedbackClassifier.classify()` **propagates**
the exception — it does not drop the delta. Measured, `<net> vs SPI_CLK`:

```
--- BEFORE (origin/main) / design_rules = netclass_rules.yaml ---
   +170V_BUS        -> ValueError: Rationale 'because' must be >=10 chars
   DC_BUS_RTN       -> ValueError
   hb-gnd           -> ValueError
   tank-out         -> ValueError
   tank.c_tank1-p2  -> ValueError
   ac_l / ac_n      -> 6.0 mm
--- BEFORE (origin/main) / design_rules = create_temper_design_rules() ---
   all eight nets   -> ValueError
--- AFTER (this change) / design_rules = netclass_rules.yaml ---
   all eight nets   -> 6.0 mm
--- AFTER (this change) / design_rules = create_temper_design_rules() ---
   +170V_BUS, DC_BUS_RTN, hb-gnd, tank-out, tank.c_tank1-p2 -> 2.0 mm
   ac_l, ac_n, AC_L                                          -> 6.0 mm
```

So the correct statement of the defect is **not** "the DC bus was held to
0.15 mm". It is: *the classifier resolved the DC bus to a class that does
not exist ("Signal"), whose per-class figure is the 0.15 mm LV default, and
the method then raised before injecting a constraint at all.* The 0.15 mm
is what the misclassification computed, not a separation any solve ever
saw.

**(c) The classification itself.** `classify_net_type()` is a word-boundary
match over `HV_NET_PATTERNS = {"AC_L","AC_N","PE","DC_BUS+","DC_BUS-",
"SW_NODE"}`, none of which is how this board spells its HV nets:

| net | old: `classify_net_type` → class → per-class clr | authoritative class → clr |
|---|---|---|
| `+170V_BUS` | signal → **"Signal"** → 0.15 | HighVoltage → 2.0 |
| `DC_BUS_RTN` | signal → **"Signal"** → 0.15 | HighVoltage → 2.0 |
| `tank-out` | signal → **"Signal"** → 0.15 | HighVoltage → 2.0 |
| `tank.c_tank1-p2` | signal → **"Signal"** → 0.15 | HighVoltageTank → 2.0 |
| `hb-gnd` | ground → **"GND"** → 0.30 | HighVoltage → 2.0 |
| `ac_l` / `ac_n` | hv → **"HighVoltage"** → 2.0 | **ACMains → 6.0** |

`"Signal"` is not a declared class in `TEMPER_NET_CLASSES` at all; it falls
through `get_rules_for_net`'s cascade to the LV default.

**Fix.** `design_rules.get_rules_for_net(net_a/net_b)` and take the
resolved class name — exactly the change PR #1323 made in
`netclass_constraints.py` for the identical defect. The empty-`because`
crash is fixed by keeping the informative default rationale instead of
blanking it. No new mechanism, no new figure.

### 3.3 A loosening I introduced and then caught — the `"Default"` → `"Signal"` normalization

Worth recording because it is the trap in this fix. `netclass_rules.yaml`'s
`class_pairs` table spells the generic-LV bucket **`"Signal"`**
(`HighVoltage-Signal: 6.0`, `ACMains-Signal: 6.0`, …), while
`get_rules_for_net` returns **`"Default"`** for a net with no assignment.
My first version passed the raw resolved names through, which made every
HV↔LV `class_pairs` row **miss**:

```
AC_L vs SPI_CLK:  6.0 mm  ->  2.0 mm     # max(ACMains 6.0? no: max(2.0, 0.2))
```

That is a loosening, in a fix whose whole point is that the old classifier
was too loose. `netclass_constraints._pin_class_infos` already solved this
in PR #1323 with `net_class = "Signal" if rules.name == "Default" else
rules.name`, and its docstring names the exact hazard. The same
normalization is now applied here, and
`test_hv_to_unassigned_lv_never_loosens_below_the_class_pairs_row`
(8 parametrized cases) is the ratchet against it regressing.

---

## 4. Consumers examined and deliberately NOT changed

### 4.1 `ClearanceMatrix` — misclassifies, but the misclassification is inert

`constraints_design_rules._classify_net` has no HV branch at all and puts
`+170V_BUS`, `ac_l`, `tank-out` and `tank.c_tank1-p2` in `"Signal"`. But it
does not matter, because `ClearanceMatrix.get_clearance` returns `0.2` for
*every* pair — measured:

```
Signal      x Signal       -> 0.2
Signal      x HighVoltage  -> 0.2
HighVoltage x HighVoltage  -> 0.2
ACMains     x Signal       -> 0.2
```

The per-class `clearance` values the matrix is loaded with are never
consulted for pair lookups. That is a separate and larger defect in a
post-route verification oracle (`ClearanceMatrix`'s only non-test importer
is `constraints_drc_oracle.py`, as `pair_clearance.py`'s own docstring
already records). Fixing it means deciding what a pair table should return,
i.e. **authoring separation figures**, which this task must not do.
**Flagged, not fixed.**

### 4.2 `_should_route` and the two tank nets — not changed, deliberately

`tank-out` and `tank.c_tank1-p2` are unrecognised by all three `router_v6`
predicates, so `_should_route` returns `True` and A* attempts them even
though `_zone_layers_for_net` reports both zone-pour-eligible.
"Correcting" the classification here would flip them to
`should_route=False`, i.e. would **reduce** the measured routing gap by
declaring them pour-covered — the exact direction `origin/main`'s own
`eb5022510` / `d63219450` concluded against ("the 9 zone-dependent nets are
genuinely open — routing gap is 79, not 70"). **Not changed:** this is a
routing-completeness question already adjudicated, not a separation
question, and changing it would improve a metric with no physical change.

### 4.3 `IECCreepageGate` never inspects the `creepage` category — scoped, not fixed

`check()` filters `if err.rule != "clearance": continue`, so it never looks
at `kicad-cli`'s own `creepage`-category violations — despite
`HV_LV_CREEPAGE_MM` (12.6 mm, PD3) being a creepage figure. Measured on
this board, `creepage` category:

| classifier | HV↔LV pairs |
|---|---|
| old 7-name frozenset | 4 |
| manifest-backed (this change) | **77** |

and **35** of those pair a manifest-declared **HV** net directly against a
manifest-declared **SELV** net — including `ac_l`↔`gnd` and `ac_n`↔`gnd`.
The gate reports none of them, before or after this change.

Those 35 **are** caught by the fab-authoritative
`generate_kicad_dru.py` → `kicad-cli` path — that is how they were measured,
and they are already inside the board's existing DRC totals. What is broken
is this gate's redundant in-placer check of them. Widening the rule filter
changes *what the gate measures* rather than *how it classifies*, so it is
scoped as separate follow-up rather than folded into a classification fix
where it would look like the same change.

---

## 5. The real inadequate-separation finding — pre-existing, already CI-red

`scripts/check_hv_netclass_coverage.py` **FAILS on `origin/main`** (exit
3), PROPERTY 1 and PROPERTY 3, naming **seven HV-domain nets with no
netclass assignment in either `TEMPER_NET_ASSIGNMENTS` or
`pcb/temper.kicad_pro`**:

```
discharge.k_dis1-no    discharge.k_dis2-no
discharge.r_dis1a-p2   discharge.r_dis2a-p2
discharge.r_snub1-p2   discharge.r_snub2-p2
input
```

All seven are on the board. They are bus-bleed-string and relay-contact
snubber mid-nodes on the DC bus, plus `input` — the UCC21550's raw
low-side driver output, on the HV side of the isolator barrier. With no
assignment they resolve to KiCad's `Default` class — **0.2 mm clearance and
no creepage rule** — on the fab-authoritative `kicad-cli` path. The gate's
own wording: *"falls to Default (0.2mm), invisible to every HV↔SELV
clearance/creepage rule."*

Bounding the exposure, measured: **30** violations in the current DRC
report already name one of the seven (27 `creepage`, 3 `clearance`),
because the DRU's HV rules are written as
`A.NetClass == 'HighVoltage' && B.NetClass != <HV family>`, which fires
when B is `Default`. **0** of those pair one of the seven directly against
a declared-SELV net.

**But absence of a violation there is absence of a check, not evidence of
adequate separation:** a `Default`-vs-`Default` or `Default`-vs-SELV pair
among these seven has **no rule written for it at all**.

Not fixed here. Per the `hb-gnd` precedent recorded in
`core/design_rules.py`, syncing a net into `pcb/temper.kicad_pro` for real
surfaces new genuine violations and requires routing/placement remediation
— a separate, human-gated step. Two SELV-domain nets (`s1`,
`safety.ocp2-line`) are unassigned by the same gate's PROPERTY 4.

---

## 6. Violation counts, before and after

**Board DRC totals are unchanged, and that is expected**: nothing in this
change touches the board, the DRU generator, or any netclass table.

```
kicad-cli pcb drc --all-track-errors --severity-all --format json \
    -o drc.json pcb/temper.kicad_pcb
-> 776 violations, 339 unconnected items      (before and after)
```

`power_pcb_dataset/drc_ceiling.json` is untouched. `MIN_BARRIER_WIDTH_MM`
is untouched.

What changed is what the two fixed consumers *see*:

| measurement | before | after | attribution |
|---|---|---|---|
| `IECCreepageGate` HV↔LV `clearance` pairs | 1 (a false positive) | 2 (both real, both `+170V_BUS`) | classification widened from a 7-name set to the domain manifest |
| `feedback.py`, `+170V_BUS` vs an LV net | `ValueError` (nothing injected) | 6.0 mm (yaml rules) / 2.0 mm (temper rules) | `get_rules_for_net` + the empty-`because` crash fix |
| `feedback.py`, `ac_l`/`ac_n` vs an LV net | 6.0 mm (yaml) / `ValueError` (temper) | 6.0 mm both | same |
| `feedback.py`, any pair outside `class_pairs` | `ValueError`, propagated out of `classify()` | constraint injected | crash fix |

**Nothing was suppressed.** No threshold, ceiling, allowlist, oracle pin or
test expectation was changed to absorb any increase. The one increase this
change does produce — the `IECCreepageGate` count going 1 → 2 — is reported
above with both pairs named.

---

## 7. Oracle safety

Neither fix alters a pinned `_*_py_oracle.py` or its differential:

* `_gates_py_oracle.py` contains no `_is_hv_net` / `IECCreepageGate` code.
* `_feedback_py_oracle.py` **does** carry a frozen copy of
  `_handle_clearance_violation`, **but** its differential's
  `MockDrcViolation` has no `net_a`/`net_b` attributes, so the branch this
  change edits is never entered on either arm. Confirmed by running
  `test_feedback_rust_differential.py` after the change: green.
* `scripts/oracle_hashes.json` is untouched; no hash was re-pinned.
* **`HV_NET_PATTERNS` was deliberately NOT widened.** Adding board net
  names to it would invent a keyword mechanism where a net-class/manifest
  mechanism already exists — and
  `tests/wave4_phase2/test_core_contracts_differential.py` builds its
  `NAME_CORPUS` *from* those constants while comparing production against a
  frozen oracle copy, so a new pattern would diverge production from a
  pinned oracle. That is the documented STOP condition, and it was not
  crossed.

---

## 8. Test results

All runs in this worktree's own `.venv`, `-p no:randomly`.

**Pristine `origin/main` baseline** (sources reverted with
`git checkout --`, tests present):

```
8 failed, 2730 passed
  6x test_physics_gate.py::test_creepage_*        -- scaffolding: `_write_pcb`
      writes a bare .kicad_pcb with no .kicad_pro sidecar, so `run_drc`
      returns UNMEASURED ("No resolvable project"). Pre-existing.
  1x test_netclass_feedback.py::test_yaml_loaded_carries_because_text
  1x test_e2e_netclass_ssot.py::test_class_pairs_contain_safety_critical_entries
      -- both assert "IEC 60335" appears in an ACMains-Signal `because`
      string that was rewritten to "UNSOURCED legacy 6.0mm ...". Pre-existing.
```

**After this change**, same command, same file set:

```
8 failed, 2730 passed   -- the identical eight. Zero new failures.
```

Command:

```
env -u CONDA_PREFIX ./.venv/bin/python -m pytest -q -p no:randomly \
  packages/temper-placer/tests/placer/cp_sat/test_physics_gate.py \
  packages/temper-placer/tests/placer/cp_sat/test_feedback.py \
  packages/temper-placer/tests/placer/cp_sat/test_feedback_rust_differential.py \
  packages/temper-placer/tests/placer/cp_sat/test_gates_rust_differential.py \
  packages/temper-placer/tests/placer/cp_sat/test_gates_pbt.py \
  packages/temper-placer/tests/placer/cp_sat/test_gate.py \
  packages/temper-placer/tests/placer/cp_sat/test_gate_contract.py \
  packages/temper-placer/tests/placer/cp_sat/test_delta_mapper.py \
  packages/temper-placer/tests/placer/cp_sat/test_net_currents_rust_differential.py \
  packages/temper-placer/tests/pcl/ \
  packages/temper-placer/tests/core/test_coverage_paydown_v22.py \
  packages/temper-placer/tests/core/test_coverage_paydown_v17.py \
  packages/temper-placer/tests/router_v6/test_net_classification_rust_differential.py \
  packages/temper-placer/tests/wave4_phase2/test_core_contracts_differential.py
```

### Tests added, and that they fail without the fix

Demonstrated by restoring each pre-fix function body in place, running, and
restoring the fix (no `git stash` was used anywhere).

`test_physics_gate.py` — with `_is_hv_net` reverted to
`return name in _HV_NET_PATTERNS`, **4 of 6 new tests fail**:

```
FAILED test_is_hv_net_recognises_every_manifest_hv_net
FAILED test_is_hv_net_recognises_the_five_highest_energy_nets
FAILED test_is_hv_net_recognises_lowercase_mains_conductors
FAILED test_creepage_gate_reports_hv_to_lv_for_a_real_board_net_pair
```

The other two pass both before and after **by design** — they are the
anti-vacuity guards: `test_is_hv_net_does_not_flag_declared_selv_nets`
(no declared-SELV net may become HV) and
`test_is_hv_net_never_narrows_the_legacy_set` (every name the old frozenset
recognised must still be recognised).

`test_feedback.py` — with the classifier reverted to `classify_net_type`
and the crash fix retained, **all 7 parametrized cases fail**:

```
FAILED test_clearance_feedback_uses_authoritative_netclass_for_hv_nets
       [+170V_BUS] [DC_BUS_RTN] [hb-gnd] [tank-out] [tank.c_tank1-p2] [ac_l] [ac_n]
   e.g. "ac_n (mains neutral -- netclass ACMains) remediated at 2.0mm,
         below its own net class's 6.0mm"
```

`test_clearance_feedback_still_uses_the_lv_figure_for_two_lv_nets` passes
both ways — the anti-vacuity guard that the fix does not simply raise every
separation.

`test_netclass_feedback.py` — with **only** the `"Default"` → `"Signal"`
normalization removed and everything else in the fix retained, **6 of the 8
ratchet cases fail**, and so does one **pre-existing repo test** that passes
both on `origin/main` and with the full fix:

```
FAILED test_yaml_loaded_hv_signal_violation_uses_yaml_value   <-- pre-existing test
FAILED test_hv_to_unassigned_lv_never_loosens_below_the_class_pairs_row
       [DC_BUS+] [+170V_BUS] [DC_BUS_RTN] [hb-gnd] [tank-out] [tank.c_tank1-p2]
   e.g. min_distance_mm == 2.0, below the class_pairs HighVoltage-Signal 6.0
```

The two `ACMains` cases (`AC_L`, `ac_l`) still pass without the
normalization only by coincidence: `max(ACMains 6.0, Default 0.2)` happens
to equal that table's `ACMains-Signal` figure of 6.0. That coincidence is
exactly why the HV cases are the load-bearing ones.

### Gates run

```
scripts/check_hv_netclass_coverage.py   -> exit 3, FAILED (pre-existing, Section 5)
make extensions-check                   -> PASSED, 10/10 fresh
ruff check / ruff format --check        -> clean on all five changed files
```

---

## 9. Files changed

```
packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py       (+/-)
packages/temper-placer/src/temper_placer/placer/cp_sat/feedback.py    (+/-)
packages/temper-placer/tests/placer/cp_sat/test_physics_gate.py       (+6 tests)
packages/temper-placer/tests/placer/cp_sat/test_feedback.py           (+8 tests)
packages/temper-placer/tests/pcl/test_netclass_feedback.py            (+8 cases)
docs/evidence/2026-08-19-is-hv-net-blast-radius.md                    (new)
docs/evidence/2026-08-19-is-hv-net-blast-radius.py                    (new)
```

`pcb/temper.kicad_pcb` — **not modified**, sha256 verified identical before
and after: `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`.
`pcb/temper.kicad_dru` is generated and gitignored; it was regenerated to
run DRC and is not part of this change.

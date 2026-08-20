# Open-findings register — 2026-08-20

**What this is.** Every finding from the 2026-08-19/20 verification session — and
the pre-existing findings it touched — that is **still open**, with what decision
it needs and who can make it. `docs/solutions/` records what was *fixed*. This
records what is *not*.

**What this is not.** Not a narrative of the session. It recommends no change to
any safety threshold, and it changes nothing: no code, config, threshold,
`.ato`, oracle, DRU or board file was modified. `pcb/temper.kicad_pcb` sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`, verified
before the first command of this task and after the last.

## How to read it

**Severity** — ranked by consequence, not subsystem.
**S1** could injure a person or destroy hardware · **S2** blocks fabrication ·
**S3** costs time, or is latent.

**Confidence** — `measured` (a tool or instrument run against the real artifact) ·
`simulated` (ngspice or a model) · `inferred` (arithmetic over declared values) ·
`unverified` (asserted in prose; no reproducible support found).

**Status** — `OPEN` · `FIXED-UNMERGED` (a branch closes it; merging is the whole
action) · `DEFERRED` (diagnosed, cost known, deliberately not shipped).

> **Every branch from this session is unmerged.** All 39 were checked with
> `git merge-base --is-ancestor`; none is an ancestor of `origin/main`. The only
> session work on main is the cleanup series (#1396–#1400, #1408, #1409), which
> contains no finding in this register.

---

# 1. Decide these first

| # | Finding | Why it leads | Needs | Conf. |
|---|---|---|---|---|
| **F1** | **Two hardware overcurrent trips dispatch on a sensor function that has no hardware implementation.** `state_machine.c:400,404` call `read_dc_bus_current()` for `IGBT_SHORT_CURRENT_THRESHOLD` and `OVER_CURRENT_THRESHOLD`. The only definitions in the whole tree are a simulation stub and a test stub | The IGBT short-circuit trip is the last line of defence on a 1200 V half-bridge | Firmware owner | measured |
| **F2** | **The mains↔SELV isolation barrier does not exist on the board.** `grep -c MAINS_SELV_ISOLATION_BARRIER pcb/temper.kicad_pcb` → **0** | Every creepage figure here — 12.6, 8.0, 20.0 mm — describes a constraint with no physical realisation | Board owner | measured |
| **F3** | **83 HV↔SELV net pairs sit below 12.6 mm on the production board; minimum 0.0331 mm** | This is the live board, surfaced only as the *baseline* column of a rejected experiment. Nobody owns it | Placement + EE | measured |
| **F4** | **No OVP senses the lower half-bus — and none senses the full bus either** | A midpoint imbalance overvolts one 250 V capacitor while the total stays legal, and nothing can see it | Safety owner | measured |
| **F5** | **Dead time clears the shoot-through guard by 7.5 ns / 2.5 %** on `dt_res`'s ±1 % corner alone; the IC/temperature spread has never been scope-verified | Shoot-through on a 1200 V half-bridge | Power-stage owner + bench | inferred |
| **F6** | **Bus capacitors run at 4.2–5.8× rated ripple current**, live since 2026-07-26 — and their CI gate entry is `backlog: true`, so it cannot fail | Electrolytic vent/rupture on the HV bus | EE decision | simulated |
| **F7** | **D1/D2 (MUR1560) repetitive peak never checked: I_FRM = 30 A vs a simulated 60–83 A recharge peak (2.0–2.8×)** | Recorded as *"large margin on both axes"* in the stress audit, which compared average current only — and it has **no gate entry at all** | EE decision | simulated |
| **F8** | **At the +10 % L / +10 % C tank corner the 1800 W point sits at 42.7 kHz — below the 44 kHz ZVS floor.** Below loaded resonance the bridge hard-switches at full bus | This is the *destruction mechanism* behind "1800 W unreachable", not just an unmet spec | PLL/ZVS owner | simulated |
| **F9** | **Zone fill is nondeterministic on the HV bus and breaches the mains barrier.** B.Cu `+170V_BUS` lands on **either 471.9 or 923.8 mm²**; the filled `ac_n` pour drives mains-to-LV creepage to **6.0005 mm** | The committed artifact does not say which board you get | Board owner | measured |
| **F10** | **`V(tank-out)` has not been bench-measured.** Simulated 41–53 mV against a 1.0 V threshold; the declaration file is deliberately all-`null` and its gate exits 6 | T1 — the last blocking isolation part — turns entirely on this one reading | Bench | simulated |
| **F11** | **IEC 60664-4 is not owned: 9 of 15 insulation pairings are indeterminate** | The tank↔SELV ≥20.0 mm is a *proven floor*, not the requirement. No analysis can close it | Purchase | inferred |
| **F12** | **`pcb_spec.yaml` still declares a 230 V mains and pollution degree 2** on a 120 V, PD3 design | 230 V×√2 = 325 V lands in Table 17 **row iv**; 120 V×√2 = 170 V is **row iii**. This fossil is the probable origin of the row-iv selection that produced 12.6 mm — and the placer reads this file | Owner | measured |

---

# 2. Needs an electrical-engineering decision

### F1 — Two safety trips call a sensor with no hardware implementation · S1 · measured · OPEN

`firmware/components/safety/safety.c:112-130` splits on a simulation `#ifdef`:

```c
/* Simulated sensor reads */
static float read_dc_bus_current(void) { return sim_state.dc_bus_current; }   /* :114 */
#else
/* External function declarations (implemented in peripherals) */
extern float read_dc_bus_current(void);                                        /* :126 */
```

**There is no `peripherals` component and no implementation.** Every definition
in the tree:

```
firmware/components/safety/safety.c:114     static, simulation-only
firmware/test/state_machine_stubs.c:365     test stub
```

Callers: `safety.c:261`, `safety.c:353`, and — the ones that matter —

```c
firmware/main/state_machine.c:400   if (read_dc_bus_current() > IGBT_SHORT_CURRENT_THRESHOLD) {
firmware/main/state_machine.c:404   if (read_dc_bus_current() > OVER_CURRENT_THRESHOLD) {
```

`read_heatsink_temperature` has the identical shape.

**Consequence.** On a non-simulation build these symbols are undefined. Either
the firmware does not link for hardware, or the trips resolve to something
nobody has identified. Both hardware overcurrent paths — including IGBT
short-circuit detection — currently have no implemented sensor behind them.

**Related, same cluster:** there is **no DC-bus undervoltage path at all** — no
undervoltage fault code (`firmware/main/fault_list_generated.h:21-35`, 14
entries), no event, no transition in `firmware/transition_table.yaml`. And the
hardware watchdog (1.6 s) and shutdown budgets (100–200 ms) are all far longer
than one 60 Hz line cycle (16.7 ms); nobody has done that arithmetic.

**Decision.** Firmware owner. This is the highest-consequence single item in the
register.

### F2 — The isolation barrier keepout is absent from the board · S1 · measured · OPEN

`scripts/check_isolation_keepout.py:172` defines
`BARRIER_ZONE_NAME = "MAINS_SELV_ISOLATION_BARRIER"`, and the docstring (`:81`)
requires a zone *"named exactly `BARRIER_ZONE_NAME` (a documented convention, not
any keepout)"* — deliberately narrow so an unrelated keepout is never mistaken
for it. The board contains no such zone:

```
grep -c "MAINS_SELV_ISOLATION_BARRIER" pcb/temper.kicad_pcb      # -> 0
```

Corroborated on **both** arms of PR #1385's experiment and independently listed
as a pre-existing red in PR #1380 §7.

**Consequence.** `MIN_BARRIER_WIDTH_MM = 12.6` is enforced as a CP-SAT corridor
constraint and a DRU rule, but nothing in the router's configuration space
forbids crossing the boundary. What has kept production traces from crossing is
*emergent* — grid A\* emits staircases averaging 0.99 mm. That is not a safety
property, and F53 shows exactly what happens when it is removed.

**Decision.** Board owner: does the barrier become a real all-layer keepout
(which then also constrains the router), or is the architecture restated? Note
the copper-free-on-every-layer property is load-bearing elsewhere — it is why
IEC 60335-1 cl. 3.4.4 branch (i) (basic insulation + earthed protective screen)
was foreclosed in the reinforced-insulation determination.

### F3 — 83 HV↔SELV pairs below 12.6 mm, minimum 0.0331 mm · S1 · measured · OPEN

`origin/review/anyangle-drc-creepage`, evidence doc lines 133–141:

| | **production** | any-angle |
|---|---|---|
| distinct HV↔SELV pairs < 12.6 mm | **83** | 129 |
| item-level offending pairs | **486** | 728 |
| global minimum HV↔SELV separation | **0.0331 mm** | 0.0000 mm |

Worst case named: `hb.gate_hs.driver-p1-1` pad C22.1 ↔ `gnd` pad C6.2. The doc
scopes it out of its own review — *"a **pad-to-pad placement** defect that both
arms share — it is not caused by routing and is out of scope here"* — and it has
not been picked up anywhere since.

**Caveat.** These counts are graded against 12.6 mm and move in **both**
directions under per-pairing (F35). The 0.0331 mm minimum does not move.

### F4 — No lower-half OVP sense, and no full-bus sense · S1 · measured · OPEN

One `OVPComparator` (`elec/src/modules.ato:2118`, instantiated `:3205`),
monitoring one node: `:2303` (trip divider) and `:2433` (ADC monitor) are the
**same** node, wired at `elec/src/main.ato:864` and `elec/src/modules.ato:3239`.
`dc_bus_plus` is the +170 V **upper half-bus** referenced to the doubler
midpoint — proved independently of naming at `elec/src/modules.ato:877`, where
`assert c_bus1.voltage_rating >= v_bus_half * 1.25` passes at 250 ≥ 212.5 and
would not at 250 ≥ 425.

Stated in-source at `elec/src/modules.ato:2184-2190` (*"KNOWN LIMITATION [...]
BLIND to bus IMBALANCE"*) and sharpened, but explicitly not fixed, on
`origin/fix/ato-assertion-vacuity-paydown-2` at `elec/src/main.ato:991-994`:
*"a midpoint imbalance overvolts ONE bus capacitor while the total stays inside
`v_cap_max`, and no OVP on this board can see that — there is no lower-half
sense at all. That is a protection-coverage gap for the safety owner."*

> **Correction to the seeding index.** The claim was "no OVP senses the lower
> half". The verified position is stronger: there is **no total-bus sense
> either**. Coverage is upper-half only.

**Decision.** Safety owner. `docs/hardware/SELV_ISOLATION_REDESIGN.md:241`
proposes an isolated differential amplifier (Option B) — a proposal, not an
implementation. Read together with F19: the parts being protected have 4.75 %
real margin, not the 17.65 % they appear to have.

### F5 — Dead time clears the guard by 7.5 ns / 2.5 % · S1 · inferred; unverified at the IC · OPEN

| | value | source |
|---|---|---|
| `dt_res` | 34 kΩ **±1 %** | `elec/src/modules.ato:271-278` |
| dead-time law (TI UCC21550) | `t_DT(ns) ≈ 8.6 × R_DT(kΩ) + 13` | `elec/src/modules.ato:280-281` |
| declared dead time | `305.4 ns` — **a dead literal on main** | `elec/src/modules.ato:283` |
| IGBT turn-off | `245 ns` | `elec/src/modules.ato:359`; `elec/src/main.ato:668` |
| the only interlock on main | `assert t_dt_sw > t_igbt_off + 50ns` — 300 > 295, **both literals** | `elec/src/main.ato:670` |

Derived interval over ±1 % alone: **[302.5, 308.3] ns**
(`paydown-2:elec/src/modules.ato:373-379`). Worst corner
`8.6 × 33.66 + 13 = 302.476 ns`; `302.476 − 295 = 7.476 ns` = **2.47 %**.

> **Precision note.** The 2.5 % is margin over `t_igbt_off + 50 ns` = 295 ns, not
> over the 245 ns turn-off itself (that margin is 57.5 ns).

**The larger gap.** `elec/src/modules.ato:268-270` already warns that
*"IC/temperature variation can fall below 300 ns [...] **scope verification
remains required**."* **No scope measurement exists in this repository.** The
±1 % resistor corner is the *smallest* contributing spread and it alone consumes
97.5 % of the budget.

**Decision.** Raise `dt_res`, or bench-verify across temperature. This register
does not propose lowering the 50 ns guard.

### F6 — Bus capacitor ripple 4.2–5.8× rated, gate suppressed · S1 · simulated · OPEN

`C2/C3/C4/C5` = `EKMQ251VSN182MA50S`, rated **2.70 A rms** (105 °C/120 Hz),
applied **11.39–15.57 A per cap** (central 13.02 A). Unchanged on main at
`elec/src/modules.ato:825`.

`docs/hardware/PART_STRESS_AUDIT.md` §0 (2026-08-07): *"The known ~5×
bus-capacitor ripple-current failure [...] is **still live**. No board, netlist,
or BOM change has touched this bank."* Gate entry `bus_cap_ripple_current` is
`backlog: true` — see **F40**.

**Costed options, all on unmerged branches:**

| option | ceiling | cost |
|---|---|---|
| 12 × Nichicon `LGW2E471MELB25` (6/half) | bank no longer binding | **+41 % of board area** (14 700 mm² vs 6 400), full placement/creepage rework |
| 6 × `LGW2E102MELC35` (3/half) | 683–965 W | 27 % of board |
| **MPN swap only** → `LGW2E182MELC50` | 513–771 W | **zero board change** — identical 1800 µF/250 V/D35×50 |

The 12-can route has an unresolved dependency: the D30 KiCad footprint's
existence in the committed library was **not verified**, and its snap-in lead
pitch is *"`[UNOBTAINABLE from what I extracted]` — not assumed to be 10.0 mm."*

### F7 — D1/D2 repetitive peak, 2.0–2.8× absolute maximum, ungated · S1 · simulated · OPEN

`MUR1560G` (`elec/src/components.ato:283-296`). Fairchild
MUR1540/MUR1560 Rev. B, Absolute Maximum Ratings: **I_FRM = 30 A**. Simulated
recharge pulse peaks at **60–83 A** at 1800 W. The source's own words:
*"**Row 4 is new.** No document in this repository has checked the rectifier
diodes against their repetitive peak rating."* The 15 A `I_F(AV)` at
`components.ato:291` is not binding — average current is 6.4–7.8 A.

**Two things make it worse than a bare over-rating:**

1. **It is recorded as safe.** `docs/hardware/PART_STRESS_AUDIT.md:269` lists
   these diodes with margin *"large on both axes"* — true on the average-current
   axis, silent on the repetitive-peak axis.
2. **It is ungated.** `scripts/part_stress_limits.yaml` has 13 entries and **no
   D1/D2 entry**. The vacuity gate explicitly does not catch this class either.

Independently reproduced to within 1 % on a second branch, which shows the
diodes become binding at **396–704 W (central 609 W)** once the bank is resized.

```
python3 docs/evidence/2026-08-19-input-stage-power-ceiling.py   # on that branch
```

### F8 — The tank tolerance corner hard-switches the bridge · S1 · simulated · OPEN

`elec/src/modules.ato:498-506` carries the declaration verbatim:

> `# TOLERANCE REGRESSION, DELIBERATELY NOT PAPERED OVER: the catalogue`
> `#   942C tolerance is K = +/-10%, against the WIMA part's J = +/-5%.`
> `#   Worst-case bank is 270-330nF instead of 285-315nF, i.e. resonant`
> `#   frequency spread widens from +2.6/-2.4% to +5.4/-4.7%. [...] no J part`
> `#   number appears in any CDE catalogue table, so acquiring one is a`
> `#   procurement conversation with CDE -- NOT an MPN to be constructed`
> `#   by swapping the K. Flagged here for the PLL/ZVS-window owner.`

Declarations `:514`, `:521`, `:528` are bare `100nF` — not file style
(`:349` is `470nF +/- 10%`, `:293` is `100nF +/- 10%`).

> **Nuance.** The ±10 % is not absent from the design, it is **decoupled from the
> part** — a free scalar at `elec/src/main.ato:487`
> (`c_tank_tolerance = 0.10`) whose assertion the vacuity detector classifies
> `NO_CIRCUIT_COUPLING`. Nothing ties the number to the three capacitors it
> describes.

**The consequence is a hard infeasibility, not a spread.** At `+10 % L / +10 % C`
the 1800 W point moves to **42.7 kHz, below the 44 kHz floor** — recorded as
**infeasible** in the "three claimants on G" table. `f_pll_tracking_min = 44 kHz`
is derived at `main.ato:171-186` as 1.05 × worst-case loaded resonance and
mirrored at `firmware/components/control/pll_control.h:104`. **Below loaded
resonance the tank is capacitive and the bridge hard-switches a 1200 V
half-bridge at full bus.**

Separately, low line (100 V) alone demands `G ≥ 1.440` against an available
1.427–1.630, leaving a **0–8.5 %** residual ripple budget.

**Decision.** PLL/ZVS-window owner: open the CDE procurement conversation for a J
part, widen the PLL window, or re-derive the 44 kHz floor. Three decisions; none
is an edit to a line.

### F9 — Zone fill nondeterministic and barrier-breaching · S1/S2 · measured · OPEN (PR #1388)

Six fills of a **byte-identical** input produced six distinct coppers; only
**57 of 144 filled rings (39.6 %)** identical across all six; area spread
**186.50 mm² (0.84 %)**. Survives `_single_threaded_kicad_env()` pinning.

**Root cause isolated:** `+170V_BUS` and `hb-gnd` zones both at **priority 70**
with overlapping outlines on B.Cu/In3.Cu, filled areas exactly anti-correlated.
B.Cu `+170V_BUS` lands on **either 471.9 or 923.8 mm²** — *"A coin flip on the
HV DC bus."*

**Barrier breach:** all 23 new creepage violations involve zone copper; the
filled `ac_n` pour drives worst-case `AC Mains to LV` creepage
**11.5078 → 6.0005 mm**, reproducibly in all six. Clean negative control: the
10.0 mm HV↔HV tank pair is unchanged.

**Residual hazard, no mechanism proposed.** `kicad-cli` does not auto-fill; a
human plotting from the GUI would. *"The committed artifact does not say which
board you get: one workflow yields a 6.0 mm mains-to-SELV gap, the other yields 9
unconnected power nets."*

Three board defects, **explicitly none actioned**: the priority-70 collision, the
`ac_n` outline encroachment, and nine copper-less nets.

**Caveat.** 6.0005 mm is graded against 12.6 mm. Under per-pairing, `MAINS↔SELV`
is 4.8 mm and it would **pass**. This finding's severity flips depending on which
unmerged branch you believe — which is itself the argument for deciding F35.

### F13 — `v_ovp_trip` declared 390 V; the divider trips at 399.90 V · S1 · simulated + inferred · FIXED-UNMERGED

| | value | source |
|---|---|---|
| declared | `v_ovp_trip: voltage = 390V` | `elec/src/main.ato:636` |
| its assertions | `< v_cap_max` (:638), `> v_bus_max` (:639) | both literal-vs-literal |
| hand-derived | `2.5 × (77.331 + 1290000/487000) = 199.95 V` half → **399.90 V** | `elec/src/modules.ato:2321-2325` |
| ngspice | 200.0292 V half → 400.06 V; agreement 0.079 V | `docs/evidence/2026-07-28-ovp01-trip-point-sim.json` (`"calibrated": false`) |
| tolerance corner | **395.5616 – 404.2494 V** (+4.348 / −4.340) | ±1 % top, ±0.1 % bottom/hyst |
| with tempco ΔT=60 | **392.22 – 407.62 V**, ≈ ±7.7 V | `elec/src/modules.ato:2335-2337` |

> **Corrections to the index.** The figure is **399.90 V**, not 399.91 (the fixing
> branch writes "That is 399.9 V"). The **±4.34 V is asymmetric and
> tolerance-only** — it excludes REF2025's ±0.05 % Vref tolerance and all tempco.

**Also violated:** the OVP bus-ADC divider reaches **3.360 V — 60 mV over the
3.3 V rail** at ±1 %, at the *nominal* half-bus. It can back-drive the ADC input.

`paydown-2` makes the assertion falsifiable (`elec/src/main.ato:1001-1006`); it
does not decide the intended trip or rescale the divider.

### F14 — Fuse, choke and relay below the design's own computed draw · S1 · simulated · OPEN

| device | rating | demand |
|---|---|---|
| F1 fuse (Schurter FST 5×20 time-lag) | 16 A | **28.81 A rms** |
| L1 CMC (`B82726S2163N030`) | 16 A @ 50 Hz | 28.81 A |
| K1 contact, IEC | 20 A | 28.81 A |

**Both citations are correct.** 28.81 A is the simulated stiffest-line figure;
**28.83 A** is what the landed assertion itself computes
(`16.6667 × 1.73`, `elec/src/modules.ato:734`). They agree to 0.1 % because
`k_line_rms = 1.73` was taken from the simulation's own ratio. Neither appears as
a written literal.

**The independent, arguably worse finding:** at the low end of the device's *own
declared input tolerance* the draw is **18.1–19.6 A at 108 V** and
**19.6–21.2 A at 100 V** (`main.ato:56` asserts `within 100V to 130V`).
`PART_STRESS_AUDIT.md` §1.2: *"a **normal, in-tolerance operating condition**,
not a fault"*, and *"no line-voltage-based power derating was found in
`firmware/`"*. Gate entry `ac_line_current_low_line` is `backlog: true`.

### F15 — UCC21550: 4 A rated source vs 6.8–9.1 A demand · S1 · inferred · OPEN

`GateDriveHS` in `elec/src/modules.ato` carried the diagnosis in prose before any
assertion existed — *"Rg = 2.2 Ω: 15 V/2.2 Ω ≈ 6.8 A peak demand, UCC21550 limits
to 4 A source"*, and *"the first-instant demand is 20.1 V/2.2 Ω = 9.1 A"*. Nothing
asserted it until the paydown; it now VIOLATES.

> **Do not cite 6.5–7.2 A.** That range appears only in a commit message, is
> uncorroborated in the diff, and reads as a drafting slip. Use **6.8–9.1 A**.

**Decision.** Raise `rg_on` — which costs switching loss and moves F5's dead-time
budget. Decide the two together.

### F16 — IGBT 40 A is `I_C` continuous, compared against a peak · S1 · datasheet value unqualified in-source · PARTLY FIXED-UNMERGED

`elec/src/components.ato:9-20` declares `IKW40N120H3` with `current_rating = 40A`
and `i_c_max = 40A` — **no condition qualifier**. The comparisons:

- `elec/src/main.ato:580-582` — `# IGBT Current Margin (>= 1.5x peak current)`
  then `assert ... >= i_peak_max * 1.5`, i.e. 40 A continuous ≥ 25 A peak × 1.5.
- `elec/src/modules.ato:88`/`:90` — 40 A vs `HighVoltageConstraints.i_max = 25A`
  (`constraints.ato:8`), which the design treats as a peak.

**The basis error is already known in this same file.** `main.ato:611-628` carries
an explicit correction for the OCP path (*"comparing a peak trip against a
continuous rating was the wrong comparison regardless"*), splitting into
`i_ocp_trip_peak = 50.1A` vs `i_igbt_soa_limit = 60A`. The correction was made two
dozen lines below a line that still has the defect.

`paydown-2` makes the check derived and expects it to fail (44.9 A vs 40 A) while
stating outright that it does **not** settle the basis. Note also `main.ato:60`'s
`i_peak_max <= i_max` is a **25 ≤ 25 tie — zero derating** (and `modules.ato:176`
is a 4 A ≥ 4 A tie).

**Decision.** Settle the basis — peak vs continuous vs SOA — then the margin.
Close F30 (junction temperature) at the same time.

### F17 — `Q1`/`Q2` are mapped to the IGBT thermal stackup but are SOT-23 parts · S1 · measured · OPEN

`Q1`/`Q2` are `AO3400A` SOT-23 signal MOSFETs credited with an IGBT's thermal
path (`packages/*/thermal_constants.rs`). Same non-conservative class as the `U6`
defect PR #1379 *did* fix (U6 mapped at 0.96 K/W when the correct placeholder is
1.85 K/W — an 11-minute-stale snapshot from the ZCD renumber). #1379 explicitly
left this one: *"documented as an intentional legacy-analysis alias [...] Worth a
follow-up."* The error direction hides overheating.

### F18 — cl. 27.6 / 27.5 earthing continuity has never been assessed · S1 · primary-text + inferred · OPEN

`elec/src/main.ato:753` hard-bonds SELV ground to PE. IEC 60335-1 cl. 27.6
(page-verified) permits PCB copper to carry earthing continuity in a non-hand-held
appliance **only if** (a) at least two tracks with independent soldering points,
each passing cl. 27.5, and (b) the laminate complies with IS 5921 Part 6 or 7.
cl. 27.5 requires 1.5× rated current or 25 A (whichever is higher) from a ≤12 V
source, with calculated resistance **≤ 0.1 Ω**.

Flagged as a side finding and never picked up: *"the same clause governs the
existing `gnd ~ pe` bond wherever that continuity is carried on PCB copper rather
than to a stud. Not assessed here."*

**Consequence.** This is the Class-I protective-earth path for the whole
appliance. If it runs on PCB copper without two independent qualifying tracks,
the protective earth is not a protective earth. Nobody has traced where the bond
is carried.

### F19 — `v_bus_half = 170 V` is nominal-line: 4.75 % real vs 17.65 % apparent · S1 · inferred · OPEN

`elec/src/modules.ato:862` declares `v_bus_half = 170V`, used at `:866`, `:869-870`
and `:877-878`. **A second independent copy sits at `elec/src/modules.ato:1348`**
in `BusDischarge`. `elec/src/constraints.ato:10-11` declares `v_max = 135V`:

```
high line:  135 × √2       = 190.919 V   (not 169.7 V)
required:   190.919 × 1.25 = 238.65 V    (not 212.5 V)
real:       250 / 238.65   = 4.75 %  margin
apparent:   250 / 212.5    = 17.65 % margin
```

Recorded on `paydown-2` at `elec/src/modules.ato:1141-1148` and explicitly not
fixed: *"Changing `v_bus_half` is an electrical decision that also moves
`p_bleed_actual` and `BusDischarge`'s copy of the same constant, so it is reported
to the power-stage owner rather than made here."*

**This is the margin F4's missing lower-half OVP would have been protecting.**

### F20 — Control loop aliases the bus ripple · S2 · measured · OPEN

`firmware/main/main.c:45` — `#define CONTROL_LOOP_PERIOD_MS 10 /* 100 Hz */`, used
at `:61`. The bus disturbance is 60 Hz (each half-bus bank recharges once per
mains cycle). Nyquist is 50 Hz. *"**The firmware cannot track the ripple
cycle-by-cycle and will alias it.** [...] (Flagged, not fixed — a firmware
finding outside this task.)"* Aliased ripple appears as a low-frequency beat in
commanded power.

### F21 — `v_bus_ripple_max = 20 V` is violated today · S2 · simulated · OPEN

`elec/src/main.ato:68-69`. Simulated at 1800 W: stiffest-line **22.7 V**, central
**22.2 V**, softest-line **22.9 V** — all VIOLATED. Separately, that analysis gives
the 20 V figure a derivation for the first time (it had none) and it lands
*inside* the derived band, so it is ratified, not challenged.

### F22 — No hold-up / ride-through requirement exists anywhere · S2 · measured · OPEN

*"Searched exhaustively across `docs/`, `elec/`, `firmware/`, all `*.md`, `*.ato`,
`*.yaml`. **This is a finding, not an absence of effort.**"* No hold-up,
ride-through, brownout-ride-through or line-dropout requirement in ms or cycles.
IEC 61000-4-11 (voltage dips / short interruptions): **zero hits repo-wide**.

Re-run independently here: `grep -rEi "hold-?up|ride-?through|brownout"
elec/ firmware/` returns only RTD_AVDD brownout — a different rail, an analog
fault case, not a mains requirement.

**Decision.** Product owner: declare one or formally declare its absence. It is a
direct input to F6's bank sizing.

### F23 — Thin margins and unflagged parts · S3 · inferred · OPEN

From `docs/hardware/PART_STRESS_AUDIT.md` (2026-08-07), all still live:

| item | rated | applied | margin |
|---|---|---|---|
| Coil NTC `NTCALUG01A104GA` (R65) | +125 °C | trips at **120.3 °C** | **3.8 %** |
| Bus bleeders R4/R5 | 2 W | 1.31 W continuous | 34.5 % — **below the repo's own 50 % guideline** |
| `C14` `GRM55DR72E106KW01L` | 250 V | 170 V | **68 % DC bias, not flagged in source** — and the MPN was **not found at Mouser or DigiKey** |

The C14 line is the one to act on: an unconfirmed MPN carrying the worst DC-bias
ratio in the audit, in a project with a documented history of fabricated MPNs.

### F24 — A resistor-power safety assertion is written backwards · S3 · measured · OPEN

`elec/src/modules.ato:851-853`:

```
assert r_bleed1.power_rating >= p_bleed_actual * 0.5   # 50% derating
```

Labelled "50 % derating", but it requires `rated ≥ 0.5 × actual` — so it fails
only above **2× rated**. At committed values it reads `2 ≥ 0.657`, and would still
read true at `p_bleed_actual = 3.9 W`. The structurally identical check for the
same function 250 lines later (`elec/src/modules.ato:1386-1390`) is correct.

### F25 — F1 / RT1 / K1 I²t coordination has never been analysed · S2 · measured (absence) · OPEN

`elec/src/modules.ato:665-673`: a 16 A time-lag fuse on a 15 A continuous branch
= ~7 % headroom, and *"No I2t coordination analysis between this fuse,
NTC_Inrush, and bypass_relay's switch-in timing has been found anywhere in this
repo."* The bus-capacitance analysis moves the energy term 22 % favourably
(103.7 J → 81.2 J against RT1's 150 J) and explicitly does not resolve it.
Consequence: nuisance trips at legitimate load, or a fuse that does not clear.

---

# 3. Needs a measurement

Most of these are cheap. F10 gates the last blocking isolation component.

| # | What | Why | Conf. |
|---|---|---|---|
| **F10** | `V(tank-out)` r.m.s. vs `PWR_RTN` and vs earth | ≤1.0 V → requirement drops to 4.8 mm and **every isolation part on the board becomes compliant**. >35.0 V → T1 is short by 10.900 mm | simulated |
| **F26** | Tank↔SELV working voltage against earth | Never measured — the declared 570.5 V is the **wrong net pair** | inferred |
| **F27** | Dead time on a scope, across temperature | `modules.ato:268-270` demands it; see F5 | — |
| **F28** | Feed inductance `L_feed` | The input the HF-bypass answer is most sensitive to — swings the benefit from 24 % to 87 % | — |
| **F29** | `R_eff`, the reflected pan resistance | *"R_eff is NOT computable from the repo; it must be measured"* — a 3.55–5.31 Ω bracket that propagates into every power figure here | — |
| **F30** | IGBT junction temperature at 47 kHz / 28.7–31.9 A | The only in-repo derivation is 2025-12-14, predates the coil correction, uses Rth(j-c) = 0.50 K/W against the datasheet's **0.31 K/W**. Heatsink Rth-sa has no datasheet at all | — |
| **F31** | CT burden resistor pulse rating at the OCP-01 trip | 1.25 W vs 0.25 W continuous (5×). `modules.ato:1727-1730`: *"Confirm the part's pulse rating on the bench"* | — |
| **F32** | 47 kHz ripple on `hb-gnd` | Load-bearing for U6's *determinability* — *"order 1 V [...] but this repository has never measured it"* | — |

### F10 in full · S1/S2 · simulated · OPEN

`origin/analysis/tank-out-winding-voltage-simulation`:

- `docs/hardware/BENCH-tank-out-winding-voltage.md` line 3: **"Status: NOT YET PERFORMED."**
- `elec/tank_out_working_voltage.yaml` — every field `null`, deliberately:
  *"THIS FILE IS DELIBERATELY EMPTY, AND THAT IS THE MECHANISM WORKING."*
- `scripts/check_tank_out_declaration.py:118` `EXIT_NO_MEASUREMENT = 6`;
  `:142` `PROJECT_FALSIFICATION_THRESHOLD_VRMS = 1.0`.

| measured r.m.s. | verdict | consequence |
|---|---|---|
| ≤ 1.0 V | `SUPPORTS_MAINS` | requirement 4.8 mm vs T1's 9.100 mm — **T1 passes, and so does every other isolation part** |
| 1.0 – 35.0 V | `CONTESTED` | row unchanged; the project's own published prediction is falsified |
| > 35.0 V | `CONFIRMS_TANK` | T1 is a real blocker: 9.100 mm vs ≥20.0 mm |

The 35.0 V is arithmetic from the Table 17 row boundary (`√(125² − 120²)`,
line 136), not a reconstructed standards value.

**Four caveats the index does not carry:**

1. **41–53 mV is the geometrically-anchored sub-range, not the answer.** The
   sweep's full bracket reaches **1.38 V**, and the harness's own conclusion is
   *"ANSWER TO THE POSED QUESTION: NO, the whole bracket does not stay under
   1 V."* Quoting 41–53 mV alone is misleading.
2. **Prose-only.** The figure is computed at runtime and printed, never stored —
   and the branch records that **ngspice is not installed on the machine that
   produced it**.
3. **The 1 V crossing is quoted three ways:** ~144 nH at the 1800 W operating
   point, ~94 nH scaled to the OCP-01 trip, and "~94 nH ≈ 13× the geometric
   estimate" in the YAML header, which drops the "scaled to trip" qualifier.
4. **The instrument can produce a confident, meaningless number.** The bench
   procedure documents an electrocution/equipment-destruction hazard (an
   earth-referenced probe on `PWR_RTN` shorts the mains through the probe ground
   lead) and a hard requirement of **≥80 dB CMRR at 47 kHz** — a typical HV
   differential probe at 60 dB gives **170 mV of common-mode feedthrough, larger
   than the signal**, biased toward the expensive conclusion.

**And the gate is not wired to CI:** `check_tank_out_declaration.py` is **not
registered in `scripts/manifest.yaml`** on its own branch.

### F26 in full — the 570.5 V figure is measured on the wrong net · S1 · inferred · OPEN

The `SELV↔TANK` working voltage is declared **570.5 V r.m.s. / 923.7 V peak**.
That figure is measured **tank-to-BUS**, and on `tank.c_tank1-p2` — the *other*
net in the TANK group. *"Every one of the 20 places the 570.5 V figure appears
[...] measures `tank.c_tank1-p2` [...] `tank-out` appears there four times, and
never once carrying a voltage."*

Stated as a gap in four independent places, including
`elec/insulation_manifest.yaml`'s own basis line: *"**MEASUREMENT GAP**, stated
because it is load-bearing: that figure is measured tank-to-**BUS**, and the
tank↔SELV working voltage has **NEVER** been measured in this repository."*

**Deeper than "not measured":** the deck the figure came from *cannot* produce a
`tank-out` voltage — `simulation/harness/nets/zvs_margin_sweep.cir:330` returns
the coil directly to node 0, *"so no `tank-out` node has ever existed in this
project's decks."* The manifest declares 570.5 V for **both** TANK nets on a basis
line reading *"The resonant tank's two measured nets."* One of the two was
measured.

The against-earth figure in use, `√(570.5² + 170²) ≈ 595.3 V`, is inferred. It
lands in the same Table 17 row, so the row does not move — a coincidence of the
row boundaries, not a verification.

---

# 4. Needs a purchase

### F11 — IEC 60664-4 · S1 · inferred · OPEN

**The arithmetic is exact.** `elec/insulation_manifest.yaml` declares 5 groups —
`MAINS` (6), `DC_BUS` (11), `SWITCHING` (8), `TANK` (2), `SELV` (35) = 62 nets,
exactly `elec/domain_manifest.yaml`'s HV 27 + SELV 35 (independently recomputed
here). Every unordered pair **including self-pairs** = **15**. Every pairing
touching `SWITCHING` or `TANK` (both `frequency_hz: 47000.0`) = **9**:
`SELV↔SWITCHING`, `SELV↔TANK`, `MAINS↔SWITCHING`, `DC_BUS↔SWITCHING`,
`SWITCHING↔SWITCHING`, `MAINS↔TANK`, `DC_BUS↔TANK`, `SWITCHING↔TANK`, `TANK↔TANK`.

IEC 60664-1 cl. 1.1.1 scopes the document to *"rated frequencies up to 30 kHz"*;
cl. 2.3 routes above that to IEC 60664-4. This board switches at 47 kHz.

**"Indeterminate" is a type, not a caveat** —
`packages/temper-design-bundle/src/insulation.rs`:

```rust
pub enum Requirement {
    Determined(SafetyValue),
    IndeterminateWithFloor { requirement: SafetyValue, floor: SafetyValue },
}
```

`requirement_mm()` returns **NaN**, so every `measured >= NaN` is false;
`enforceable_floor_mm()` returns the ≤30 kHz figure — *"a proven lower bound
[...] clearing it is **not** compliance"*; `Verdict::is_pass()` returns false,
pinned by a test asserted from 0 mm to 10⁹ mm.

**Two acquisition routes, both purchases:** IEC 60664-4 itself, or the UL/CSA
6th-Edition text, which Intertek's SUN records as having *"added requirements for
minimum basic, supplementary, reinforced and functional insulation creepage
distances for circuits operating at greater than 30 kHz."* The evidence's own
assessment: *"Both must be bought. This is the single highest-value purchase this
project can make."*

**Two caveats to carry:**

1. **The repo never states a price.** Searched across all branches — zero hits.
   What it says is that unlike IEC 60335-1 (recovered free via IS 302-1:2008, the
   BIS adoption), 60664-4 *"has no equivalent national-adoption or full-text
   public-archive route found."*
2. **The "unobtainable" label has already been wrong once.** Annex L was recorded
   as paywalled for weeks and then found free in the BIS adoption on 2026-08-19.
   And the cert package concedes *"that specific vendor-by-vendor search is not
   itself recorded in a committed evidence document this package can cite by
   exact location."* **Confidence on "unobtainable" is `unverified`.** A vendor
   sweep is cheap and has not been done.

**Also unobtained: IEC 60335-1 Ed. 6.** Every quotation is from IS 302-1:2008,
which adopts the 2004-based edition. Whether **cl. 22.27** — the clause that makes
reinforced insulation unconditional — survives verbatim into Ed. 6 is **not
verified**, and a CSA/UL bulletin confirms Table 17 is not frozen across editions.

### F33 — C6's specified part has zero stock until 2027-01-20 · S2 · measured · OPEN

TDK `B81123C1562M000` (5.6 nF Y1, 22.50 mm pitch) is the only geometry that
clears with margin. Digi-Key: **0 stock, lead time 2027-01-20**, $1.88/1. The
stocked 2.2 nF / 15.00 mm alternatives clear only with a deliberately shrunk land
pattern, at **0.0–0.4 mm margin** — and the repo already recorded that same part
as a *"false solve"* at stock pad size.

The 2.2 → 5.6 nF change needs sign-off against touch current:
**1153.7–1241.7 µA vs the 1.35 mA IEC 60335-2-6 limit — 8–15 % headroom.**

> *"Do not let the second option be chosen implicitly by someone shrinking a pad
> to make the DRC go green."*

**And nobody has asked whether the swap is needed at all** now the requirement is
4.8 mm rather than 12.6 (F35).

### F34 — C6's certificate numbers were verified for the wrong MPN · S2 · unverified · OPEN

ENEC-05495 / UL E97863 are recorded for `B81123C1222M000` — the **2.2 nF
sibling** — not for the specified `B81123C1562M000`. The doc labels series-wide
coverage *"an inference, not a document I read."* An open agency question on a Y1
safety capacitor. Check the B81123 approvals table against the exact ordering code
before purchase.

---

# 5. Needs an owner call on repo policy

### F35 — Does `MIN_BARRIER_WIDTH_MM` move to the per-pairing table? · S1 · inferred from page-verified primary text · OPEN

`MIN_BARRIER_WIDTH_MM = 12.6` is live on main
(`packages/temper-placer/src/temper_placer/core/isolation_constants.py:47`).

| pairing | per-pairing | basis |
|---|---|---|
| `MAINS↔SELV` | **4.8 mm** | Table 17 row ii, 2.4 × 2 |
| `DC_BUS↔SELV` | **8.0 mm** | Table 17 row iii, 4.0 × 2 |
| `+170V_BUS ↔ DC_BUS_RTN` | 5.0 mm | Table 18 row iii, functional |
| `SELV↔TANK` | **≥20.0 mm, NOT DETERMINABLE** | Table 17 row vi, floor only |
| the 9 of F11 | NaN | above 30 kHz |

12.6 mm is Table 17 row **iv** (>250–400 V) — a row that fits a 230 V design.
So the single scalar is **~1.6× too generous** for the crossing that prompted it
and **at least ~1.6× too small** for the crossing that is actually the worst case.

**But it is not a simple win — on the board it makes things worse.** Because
`tank-out` (570.5 V) shares the `HighVoltage` netclass with `PWR_RTN` (120 V) and
`+170V_BUS`/`DC_BUS_RTN`/`hb-gnd` (170 V), KiCad's netclass-granular DRU must take
the **worst member pairing**, so `HighVoltage → LV` goes **up** to 20.0 mm:

| class pair | at flat 12.6 | per-pairing |
|---|---|---|
| `Default ↔ HighVoltage` | 71 | **223** |
| `HighVoltage ↔ Power` | 52 | **208** |
| `FinePitch ↔ HighVoltage` | 15 | **37** |
| **total pad pairs below required** | **187** (74 nets) | **503** (107 nets) |

And on the exact copper-to-copper census (109 HV × 237 SELV = 25 833 pairs),
**8026 pairs clear their floor but are INDETERMINATE** — they can never return
PASS at any distance.

**The highest-leverage unclaimed action in the whole isolation stack** is a
one-line change: move `tank-out` into `HighVoltageTank`, which lets `HighVoltage`
fall to 8.0 mm. It edits `pcb/temper.kicad_pro`'s `netclass_assignments` and
collides directly with PR #1391. The implementation doc declines it explicitly:
*"a one-line change with a routing blast radius [...] it belongs to whoever owns
that branch."*

**And at 20.0 mm the committed placement is very nearly unroutable:** free
routable area falls 12 622.9 → **4553.4 mm²** (67.1 % → **88.1 %** keepout, a 64 %
loss); the route collapses from 4907 segments to **758**; **10 of 112 nets
connect**. The per-pairing derivation and the model-E placement must land
together, and neither has.

**This decision is upstream of F3 and F9.** Both are graded against 12.6 mm and
both move materially — in opposite directions — under per-pairing.

**Two disclosed inconsistencies inside the per-pairing work itself:**

- The determination (§6.1) records pairing 8 (tank↔bus) as *determinate* at
  Table 18 row v, 10.0 mm; the implementation marks it NOT DETERMINABLE with a
  10.0 mm floor. It flags the disagreement and takes the stricter reading. **Two
  committed docs disagree; the stricter one is unmerged.**
- `SELV↔SWITCHING`'s 8.0 mm floor is **invented by the implementation** by analogy
  to its own pairing 7. §6.1 names no floor. Labelled as a bound, but not present
  in the determination.

### F36 — `scripts/check_insulation_pairings.py` will exit 6 on every CI run · S3 · measured · OPEN

Nine pairings carry `NaN` requirements and can never produce PASS. Whoever lands
`feat/per-pairing-creepage-derivation` must decide whether CI tolerates a
structurally unresolvable red, and what that red means to a reviewer.

### F12 — `pcb_spec.yaml` declares 230 V / PD2 on a 120 V, PD3 design · S1 · measured · OPEN

`packages/temper-placer/configs/pcb_spec.yaml:41-42` — `mains_voltage_v: 230.0`,
`pollution_degree: 2`. `scripts/check_fact_registry_drift.py:280-305` registers
the authoritative PD as `3.0` and records this as *"PARTIALLY FIXED 2026-08-17
[...] `pcb_spec.yaml` remains KNOWN RED."*

**Consequence.** 230 V × √2 = 325 V lands in Table 17 **row iv**; 120 V × √2 =
170 V is **row iii**. The 230 V fossil is the probable origin of the row-iv
selection that produced 12.6 mm — and it is still sitting in a live config the
placer reads. The board is unambiguously 120 V: `RV1` is a `V150LA10AP` (150 Vrms
MCOV) which would self-destruct on 230 V.

### F37 — The oracle re-pin item is **CONTRADICTED — close it** · S3 · measured

The index records "the pinned-oracle re-pin (`clearance_oracle/clearance.py:244`)".

- **Line 244 is prose inside a comment block.** Read directly, lines 238–250 are a
  paragraph about moving *"the third of three enforcement points to the PD3
  figure"*. Line 244 is the phrase ``and ``scripts/check_isolation_keepout.py``'s
  ``MIN_BARRIER_WIDTH_MM```. It is not a hash.
- **`clearance.py` is not hash-pinned at all.** `scripts/check_oracle_hashes.py`
  registers only `_*_py_oracle.py`. The one registry entry touching this
  directory (`scripts/oracle_hashes.json:130`) pins the *sibling*
  `_iec60335_requirements_py_oracle.py`.
- **That pin is currently correct.** Its sha256 was recomputed from disk:
  `bbe66509c2c5140c0f8cb4a03276f2aa7d16aa0b5e5d1c679e9005003dd7526a` —
  byte-identical to the registry. Nothing needs re-pinning.
- The nearest 2026-08-17 doc documents a re-pin of a *different* oracle and states
  the clearance oracles were *"created, not re-pinned — zero existed for either
  file"*.

**Why it got conflated:** "pin" is overloaded here. The comment block *containing*
line 244 is about the 12.6 mm PD3 enforcement point — a **numeric** pin, a
hand-typed constant. `clearance.py:301` uses the word the same way:
*"**CORRECTED 2026-08-15** from the legacy 1.0mm pin to **1.8mm**"*.

**What is real, and is a policy question:** `_astar_nlayer_py_oracle.py` is under
a bit-exact f64 parity contract and **re-pinning it is forbidden**. That is why
F55's Tier-3 fix was not shipped. Six agents correctly refused to touch it — the
mechanism working — but it is also a permanent block on a class of kernel
changes. Owner: may that contract ever be re-pinned, by whom, on what evidence?

### F38 — 0.2 mm via drill below the board's own 0.3 mm minimum, and the 0.3 has no derivation · S2 · measured · PARTLY FIXED-UNMERGED

| | value | source |
|---|---|---|
| net-class declaration | `via_drill=0.2` (`FinePitch`) | `core/design_rules.py:191`; mirrored `configs/netclass_rules.yaml:206` |
| board's own minimum | `"min_through_hole_diameter": 0.3` | `pcb/temper.kicad_pro:30` |
| on the board today | `(size 0.8000) (drill 0.2000)` | `pcb/temper.kicad_pcb:9038-9039`, `:9157-9158`, `:9903-9904` |

It **is** a drill. (Distinct 0.2 values exist nearby and must not be conflated:
`kicad_pcb:12689` zone `connect_pads (clearance 0.2000)`,
`temper.kicad_pro:24 min_microvia_diameter`, `:31 min_track_width`, and KiCad
`Default`'s 0.2 mm clearance in F51.)

**Neither number is sourced.** `git log -S'"min_through_hole_diameter"'` returns a
single commit — `651927a8e` ("syncing dec 15", a ~4000-line bulk sync) — with **no
derivation in-tree**, and JLCPCB's published multilayer floor is *looser* at
0.15 mm. And no gate checks hole size at all: `check_fab_capability_floor.py`'s
P1/P2/P3 all compute `(size − drill)/2` and never look at the hole.

`origin/fix/via-hole-size-floor` clamps at the **Rust `Via::new` constructor**
(`drill_out_of_range` 6→0 and 4→0) and says so: *"The guard sits at the
constructor, not in the net-class table."* `via_drill=0.2` is still at
`design_rules.py:191` on that branch.

**Owner: which number is the real floor?**

### F39 — No hole-to-hole or hole-to-edge figure is fab-sourced · S2 · measured · OPEN

`generate_kicad_dru.py`'s PTH hole-to-hole 0.5 mm and `min_copper_edge_clearance`
0.5 mm are this repo's own design values. `FAB_CAPABILITY.md` sources only annular
ring (0.254 mm), min drill (0.15 mm), hole-to-**copper** and edge-to-**copper** —
none of them hole-to-hole or hole-to-edge. `HoleRequirements.hole_to_hole_fab_sourced`
and `.hole_to_edge_fab_sourced` are both `False` by design. Note also that
`pcb/temper.kicad_pro`'s `min_hole_to_hole: 0.3` is **looser** than the DRU's 0.5 —
the two disagree.

### F40 — Three real over-rating findings cannot fail CI, and the worst one has no entry · S1 · measured · OPEN

`scripts/part_stress_limits.yaml` carries 13 entries; three are `backlog: true`
and so do not fail the gate:

| id | designators | rated | applied |
|---|---|---|---|
| `bus_cap_ripple_current` | C2–C5 | 2.7 A | **13.02 A** |
| `ac_line_current_low_line` | F1, L1 | 16.0 A | **18.52 A** |
| `tank_coil_peak_current` | R30 | **15.0 A** *(stale — F41)* | 31.9 A |

All seeded 2026-08-07. The gate runs in CI
(`.github/workflows/python-tests.yml:2792`) and exits 3 on a `FAIL`; the workflow
comment is honest — *"3 real over-rating findings are a dated backlog [...] board
redesign decisions for a hardware maintainer"*. Thirteen days on they are still
unowned. **And D1/D2's repetitive-peak finding (F7) is not an entry at all**, so
the highest-ratio over-rating in this register is entirely ungated.

**Owner: a `backlog` flag with no expiry is indistinguishable from a
suppression.** Give the three a date, or accept them formally.

### F41 — Four sources still declare a superseded 15 A pad rating, one of them the gate's own data · S3 · measured · PARTLY FIXED ON MAIN

> **Correction to the index.** The claim was "Litz pads rated 15 A carrying
> 28.7–31.9 A". The rating was corrected on **main** on 2026-08-13:
> `elec/src/footprints.ato:22-26` declares `pad.current_rating = 25A`, with the
> docstring recording *"current_rating corrected 2026-08-13 from 15A [...] to
> 25A"*. The module **name** `LitzPad_15A` is retained deliberately as historical,
> to avoid desyncing the `fp-lib-table` reference on the placed board.

**And the comparison mixes bases.** 28.7–31.9 A is a **peak**; the pad rating is
**continuous**. `pcb/libs/lib.pretty/LitzPad_15A.kicad_mod:4` says so: *"a
28.7-31.9A peak-vs-15A-continuous comparison, as `PART_STRESS_AUDIT.md` Sec 1.3
makes, mixes bases."* Like-for-like continuous is **20.7 A rms** (ngspice) to
**22.5 A rms** (first-harmonic) against 25 A ≈ 1.11×.

**Still open:** four sources say 15 A, one load-bearing —
`scripts/part_stress_limits.yaml:106-120` (`rated: 15.0`) **gates CI against a
rating that no longer exists**; `elec/src/modules.ato:590-592` cites
*"`LitzPad_15A`'s declared 15A pad rating (footprints.ato)"* against a file that
now says 25 A; plus `PART_STRESS_AUDIT.md:128` and `BOM.md:155`.

**And the 25 A is `inferred`, not a datasheet figure** — IPC-2221B applied to a
PTH annulus by engineering judgment. The footprint's own descr: *"still not a
part-specific datasheet number [...] **Flagged for human visual cross-check before
fabrication**."* That cross-check is pre-fab work.

Separately: the same 28.7–31.9 A peak also exceeds `main.ato:60`'s
`i_peak_max = 25 A`, which passes only because it is a 25 ≤ 25 tie.

### F42 — The DRC ceiling is pinned to a board three commits stale · S2 · measured · OPEN

`power_pcb_dataset/drc_ceiling.json` declares `error_ceiling: 2201` with
provenance `inputs[0].sha256 = 9c1f4a37b03c6433...`, measured 2026-08-16 (#1279).
The live board is `26981fea2dbc...`:

```
git log -3 --pretty='%h %ad %s' --date=short -- pcb/temper.kicad_pcb
11a7e7c52 2026-08-17 fix(router): revert M6c, land the Tier 3 span-scaled budget (#1334)
342e1bd08 2026-08-17 fix(pcb): re-route lands both stitch fixes — track_width 120→0, net ~-185 DRC (#1333)
968d1a33d 2026-08-17 fix(router): enforce the 0.254mm annular floor in Via::new (#1316)

git log -1 --pretty='%h %ad %s' --date=short -- power_pcb_dataset/drc_ceiling.json
1188c726d 2026-08-20 cleanup: DRC ceiling machinery (#1398)      # machinery only, not a re-measure
```

The ceilings have never been re-ratcheted against the current board, and #1333
claims a ~185-count net improvement — so they carry unratcheted slack. The file's
own `_goal` names the hazard (*"debt to pay down, not budget to spend"*) and the
2026-07-27 `_march` entry describes exactly this mode: *"nobody ratcheted, leaving
68 errors of slack for a regression to hide in."* Independently noted by PR #1388
(as #1370), which says only deltas are reportable as a result.

### F43 — `_is_hv_net` recognises 1 of 27 HV nets, and is **still on main** · S1 · measured · OPEN

`packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py:746-756` — a
7-entry hardcoded frozenset:

```
"DC_BUS+", "DC_BUS-", "SW_NODE", "SW_NODE_DC+", "SW_NODE_DC-", "AC_L", "AC_N"
```

Against the 27-net HV domain in `elec/domain_manifest.yaml`, **six of the seven do
not exist on this board** — only `SW_NODE` does. Used at `gates.py:837-838` to
split HV/LV for `IECCreepageGate`, so a DRC clearance violation naming any of the
other 26 HV nets is **not recognised as an HV↔LV crossing**. The docstring calls
it a `KNOWN GAP, flagged not fixed`.

> **Correction to `docs/solutions/`.** The catalogue
> (`checks-that-cannot-fail-catalogue-2026-08-20.md`, row 8) states the fix commit
> `d59fb0caf` is *"(merged to main)"*. **It is not.**
> `git merge-base --is-ancestor d59fb0caf origin/main` fails, and
> `git branch -r --contains d59fb0caf` returns only
> `origin/fix/hv-net-classification-blast-radius` — unmerged, no PR. The defect is
> live on main today. This is the only figure in the six solutions documents that
> did not hold up.

### F44 — Trunk is red on `main` in at least five independent places · S3 · measured · OPEN

Reproduced on a pristine `origin/main` worktree:

1. `check_manifest_gate.py` fails on `check_placement_pair_creepage.py`, which has
   **no manifest entry on origin/main** (introduced by `d5882072d`). **It blocks
   the manifest gate for everyone.**
2. `test_design_rules_rust_differential.py::test_module_constants_identical` —
   Rust `design_rules.rs` carries `hb-gnd: HighVoltage`, the pinned Python oracle
   does not. *A netclass disagreement between two safety tables, on an HV net.*
3. Five `cli/` failures (`test_optimize_no_loop.py` ×4, `test_repair_unplaced.py` ×1).
4. `pad_geometry::tests::pow2_is_exact_where_powi_is_not` (1 of 8468 Rust tests).
5. `test_adapter_convert_marshal_rust_differential.py` asserts `(0.6, 0.3)` that
   `Via::new`'s annular clamp corrects to `(0.9, 0.3)`; plus
   `test_ci_test_file_registration.py` ×3 on 12 unregistered test files.

(5) is targeted by PR #1389; (1)–(4) are open.

**Related:** `check_board_containment.py` is CI-wired, blocking, and **red on the
real board** (8 violations — the staged-off-board OCP-02 DNF parts) while three of
its own tests assert the board is clean. Its docstring's claim *"On today's
committed board it reports zero violations"* is stale. PR #1387 fixed four false
positives in the same script and deliberately left the real-board red.

### F45 — `_PASSING_LOCALLY` tests run in no CI job · S3 · measured · OPEN

`test_strip_copper` rotted for weeks and accumulated three stale assertions (a
96-zone expectation, `isolated_copper` 109→0, `track_width` 120→0) because the
file is marked `_PASSING_LOCALLY` and is in no CI job. PR #1379 fixed that file;
**the pattern itself is unaudited.** Worth an inventory — this one instance hid
three stale expectations about the board's own copper.

### F46 — T2's DNF status rests on a premise that is now void · S3 · measured · OPEN

T2 is marked DNF — do-not-fit — and parked at (100.0, 300.0), 46 mm off the
outline (`pcb/temper.kicad_pcb:6412`; `docs/hardware/BOM.md:283`). Its stated
technical premise, in `docs/STRATEGY.md:233` and `firmware/config.yaml:254`, is
that *"its CST3015 cannot reach the 12.6mm PD3 reinforced"* bar. T2's actual
pairing is `DC_BUS↔SELV` = **8.0 mm**, which its settled 9.100 mm span clears by
1.1 mm. *"**The de-scope's sole technical premise is void.**"*

It does **not** auto-reinstate — the timing ground (up to 10.64 µs latency vs
OCP-01's <1 µs), the core-reset/flux-walking ground (no simulation of the gated
waveform exists), and the "not clause-mandated" ground are untouched. But the DNF
text is unchanged on every branch including main, and nobody has re-decided it.

---

# 6. Fixed but unmerged — the "just merge it" list

**This is the most useful distinction in the document.** Everything below is
diagnosed *and* remediated on a branch. The action is a merge decision, not an
engineering decision.

## 6.1 Open PRs

| PR | Branch | What it closes |
|---|---|---|
| **#1390** | `fix/drc-parser-unconnected-items` | `_parse_drc_json` read **1 of kicad-cli's 10** top-level keys — **339 `unconnected_items` invisible**; true error count 718 vs the reported 379 |
| **#1391** | `fix/netclass-tables-reconcile` | Two net→netclass tables drifted for **34–35 days**, leaving **7 HV-domain nets at KiCad `Default`** (0.2 mm clearance, no creepage rule) on the fab-authoritative path. Revives the drift gate. DRC 776 → 883 (+107); creepage 106 → 150 (+44) |
| **#1392** | `gate/ato-assertion-vacuity` | The detector that found **74 of 86** assertions unfalsifiable. Detector only — see F47 |
| **#1393** | `fix/completion-pct-metric-chain` | Four defects in one chain: a fraction rendered as a percent (a 90 %-routed board printed **"0.9 %"**); a blocking SLO whose join key matched **zero of 135 records** for its entire history; a CI step calling a subcommand that never existed, swallowed by `\|\| SLO_EXIT=$?`; `drc_errors: 0` across all 135 runs |
| **#1394** | `agent/clearance-floor-and-copper-audit` | `topology_copper_audit` **ran zero times** on the default recipe |
| **#1395** | `docs/agents-instrument-notes` | A stale-extension gate checking timestamps not symbols; `cargo test` poisoning the shared target dir for every worktree |
| **#1389** | `fix/via-floor-stale-tests` | 8 stale annular-ring expectations; fixtures now derive from the crate constant |
| **#1387** | `agent/three-red-gates` | Three unowned red gates, and a documented coverage number off by **310×** |
| **#1376 / #1380** | pad-rotation convention | **F52 — 34 real HV↔SELV violations below 12.6 mm that were never counted** |
| **#1360 / #1363** | `input` / `discharge.*` netclass | **F51** |
| **#1385** | `review/anyangle-drc-creepage` | **A REJECT, not a fix** — merging records the decision. See F53 |
| **#1386** | `investigate/open-slot-creepage` | Open slots do not escape the closed-end credit — but its Annex-L premise is stale. See F54 |
| **#1388** | `measure/zone-fill-consequences` | Measures F9. Recommends keeping the unfilled ceiling |

#1385, #1386 and #1388 all have **zero comments and zero reviews**.

## 6.2 Branches with no PR at all

Invisible to anyone reading the PR queue.

| Branch | What it closes | Measured effect |
|---|---|---|
| `fix/gnd-plane-backbone-on-in1cu` | `BACKBONE_LAYER = "F.Cu"`, stale 3 days after the bug it worked around was fixed | In1.Cu 0 → 294 segments; `unconnected_items` **339 → 304** |
| `fix/power-islands-backbone-on-in2cu` | same, power islands | In2.Cu 0 → 227; F.Cu 652 → 485; **304 → 282** |
| `agent/per-pairing-placement-route` | routes the per-pairing-compliant placement | **282 → 251** |
| `fix/via-hole-size-floor` | enforces `min_through_hole_diameter` at `Via::new` | `drill_out_of_range` **6→0** and **4→0** |
| `fix/multi-pad-landing-vias` | `_attempt_pad_layer_landing` inspected only `segments[0]`/`[-1]` | +1 pad, +1 net, **0 nets lost** — see F49 |
| `fix/net-current-table-fail-closed` | ampacity table keyed on `DC_BUS+`, a net that never existed; `+170V_BUS` and `DC_BUS_RTN` rated **0.1 A instead of 16 A** | pins the single-SSOT home count |
| `fix/hv-net-classification-blast-radius` | **F43** | wrongly reported as merged in `docs/solutions/` |
| `fix/ato-assertion-vacuity-paydown` + `-2` | 74 → 60 → **53** unfalsifiable; makes F13/F5/F16 falsifiable | 5 now VIOLATE — F47 |
| `fix/stub-aware-via-drop` | makes the gnd drop-via search stub-aware | and measures why that is not enough |
| `analysis/*`, `research/*`, `evidence/*` (12 branches) | all the standards work, the power ceiling, the CST3015 settlement | evidence only; nothing enforced |

**Merge-order note.** `fix/gnd-plane-backbone-on-in1cu` →
`fix/power-islands-backbone-on-in2cu` → `agent/per-pairing-placement-route` is a
measured chain and must land in that order; 339→304→282→251 is only meaningful
sequentially. **Merge #1390 first** or the chain's own metric is unreadable. And
per F35, the per-pairing derivation must land *with* the model-E placement or the
board becomes unroutable.

---

# 7. Latent and deferred, with the reason

### F47 — The electrical assertion ledger · S1 · measured · OPEN

Counted directly from `.ato-assertion-vacuity-inventory` at each ref:

| | gate `ae3a9c028` | paydown-1 | paydown-2 |
|---|---|---|---|
| assertions total | 86 | 88 | **94** |
| circuit-coupled | 12 | 27 | **40** |
| `NO_CIRCUIT_COUPLING` | **74** | **60** | **53** |
| `TIE_MARGIN` | 3 | 0 | 0 |
| `TAUTOLOGY` | 0 | 1 | **1** |
| `VIOLATED` | 0 | 5 | **5** |
| `INDETERMINATE` | 0 | 4 | **4** |
| open ledger entries | 77 | 70 | **63** |

**"53" is right for `NO_CIRCUIT_COUPLING` specifically, and it undercounts three
ways:**

1. **Strict "cannot fail" is 54** — `TAUTOLOGY` is by the gate's own definition
   also cannot-fail.
2. **The open ledger is 63** — add 4 `INDETERMINATE` (undecidable; a different
   defect class, and their identities are **not itemised anywhere**).
3. **Five assertions evaluate FALSE right now** — the opposite of vacuous, and the
   highest-severity items in the ledger: F14 (×3), F15, F13, plus F57
   (`p_output_max`). Burying them inside "53 vacuous" hides them.

`main.ato` contains **no derived quantities at all** — which is the structural
reason `p_output_max = 1800W` was never caught. The paydown is honest about its
limits: *"NOTHING NEW FAILS, AND THAT IS THE HONEST RESULT [...] `ato build` fails
on the same nine assertions before and after."* `.ato-assertion-vacuity-inventory`
does not exist on `origin/main`.

### F48 — Eight "fake completions": the router reports safety nets as routed · S2 · measured · OPEN

Eight nets have **exactly `pads_connected == 2`** regardless of having 3, 4 or 5
pads, and the router reports every one as `routed`:

`GATE_LS`, `RTD_HW_FAULT`, `V_BUS_SENSE`, `bias`, `power_in.bypass_relay-coil1`,
`refin_n`, `safety.ovp.comp-inp`, `vbias`

In every case the channel path's waypoints *do* cover all the net's pads; the
router emitted 513–5541 path points per net and reported success. **`GATE_LS`,
`V_BUS_SENSE` and `safety.ovp.comp-inp` are gate-drive and OVP-sense nets** — a
board fabricated on this report would have them incompletely connected.

### F49 — The landing-via fix is correct, and the board has nowhere to put the vias · S2 · measured · OPEN

Of **23** candidate interior landing vias, three fabricability gates leave **one**:

| gate | survivors | blocked |
|---|---|---|
| raw interior scan | 23 | — |
| 1 — skip pads the route already lands elsewhere | 6 | 17 (`drop_redundant_vias` deleted them downstream anyway) |
| 2 — via **footprint** free on **every** layer | 4 | **2 — `V_BUS_SENSE`, `power_in.bypass_relay-coil1`** |
| 3 — the hole must be drillable | **1** | **3 — `vbias`, `bias`, `RTD_HW_FAULT`** |

Unconstrained, the pass emitted 6 vias and kicad-cli attributed **15 violations to
4 of them by name**; the fully unconstrained version would have shipped
**+17/−11 pads and +52 DRC violations**.

**A board-density finding, not a router bug.** Three become recoverable the moment
`fix/via-hole-size-floor` lands (F38); two are genuinely dirty; the rest is a
routing gap. Gate 2's occupancy-grid heuristic *"will sometimes trust a cell it
should not, and sometimes refuse one it could take"* — a real geometric via-drop
validator is the correct answer and was not built.

### F50 — Two via-emission paths bypass the fabricability floor · S2/S3 · measured · OPEN

**F50a — `_zone_pour_stitch.py` writes vias as raw f-strings.**
`router_v6/_zone_pour_stitch.py:834-838` appends an s-expression by string
concatenation — no `Via::new`, no clamp:

```python
f"  (via (at {px:.4f} {py:.4f})"
f" (size {via_size:.4f}) (drill {via_drill:.4f})"
```

with fallbacks at `:726-727` (`else 0.8` / `else 0.4`). Ring = **0.20 mm** against
a declared **0.254 mm** floor (`pcb/temper.kicad_pro:32`,
`docs/hardware/FAB_CAPABILITY.md:146`,
`packages/temper-orchestration/src/pipeline_route.rs:149`).

> **Severity caveat worth recording.** The fallback fires only on a netclass
> lookup miss. `:108` restricts the loop to
> `_CONTINUITY_EXEMPT_NETS = frozenset({"power_in.ntc-no"})`, and
> `design_rules.py:631` maps that net to `HighVoltage` (1.2/0.6 = a 0.30 mm ring).
> **On today's board the 0.20 mm path is latent, not live.** It becomes live the
> moment a continuity-exempt net is added without a netclass assignment — exactly
> the drift class that went unnoticed for 34–35 days in #1391.

Survives `fix/zone-pour-obstacle-set`'s 321-line rewrite of the same file
(f-string now `:898-899`, constants `:790-791`, both unchanged).

**F50b — `_find_via_drop_point` uses zero edge margin.**
`router_v6/_ground_plane.py:519` — `if not board_polygon.contains(footprint):` —
where `footprint` is the bare copper disc; no `.buffer(-margin)` on this path.
Declared elsewhere: `min_copper_edge_clearance: 0.5` (`temper.kicad_pro:21`) and
`COPPER_EDGE_CLEARANCE_MM = 0.5` (`_encoder_solve.py:391`).

> **Sharper than the index states:** the *same file* declares
> `BOARD_EDGE_MARGIN_MM = 1.0` at `:113` and applies it at `:817` — **to the plane
> pour only**. The pour is held 1.0 mm off the edge while vias dropped by the same
> module are held 0.0 mm off it. The inconsistency is intra-file.

Not fixed anywhere; `fix/multi-pad-landing-vias` touches only `_astar_nlayer.py`.

### F51 — `input` is netclass `Default` but is the UCC21550's secondary-side output · S2 · measured · FIXED-UNMERGED (#1360/#1363)

This charges `R22.1` a 12.6 mm reinforced barrier against
`hb-gnd`/`SW_NODE`/`+170V_BUS`, forcing R22 **36 mm** from its driver, and produces
a false `U6.10 ↔ U6.11 at 0.670 mm` violation between adjacent pins **on the same
isolated side**. Fixing it would put both gate-drive legs under ~10 mm. PR #1360
classifies `input` as `HighVoltageSignal` on both enforced surfaces; #1363 does the
same for the 6 `discharge.*` nets. **This is a different defect from the "7 HV
nets at Default clearance" item — that one is the tables-drift defect, PR #1391.**

### F52 — The pad-rotation fix reveals 34 real HV↔SELV violations never counted · S1 · measured · FIXED-UNMERGED (#1376/#1380)

Over all 25 833 HV×SELV pairs: pre-fix `R(+θ)` reported 155 pairs below 12.6 mm;
corrected `R(−θ)` reports **122** — of which **34 were missed entirely** and 67
were phantoms. At 8.0 mm: 26 → 12, with **3 real ones missed**. The arithmetic
closes exactly: `(122 − 34) + 67 = 155`. Ground truth from pcbnew 10.0.5 via
`scripts/kicad_pad_polygon_oracle.py`.

**The safety census was wrong in both directions and could never self-correct** —
the pre-fix code computed the correct column only for pairs the wrong column had
already flagged. It is invisible today only because all 527 pads sit at multiples
of 90° (0°:58, 90°:202, 180°:175, 270°:92): **correct by coincidence of placement,
not by construction.** Any future part at a non-90° angle makes it wrong. On main
the 34 remain uncounted.

### F53 — Any-angle search: rejected, with two latent items and reopen criteria written against a superseded number · S3 · measured · DEFERRED

PR #1385 correctly REJECTs Theta\*: 8 direct HV↔SELV metallic contacts at
**0.0000 mm** (including `tank-out` track ↔ `I_SENSE` pad T1.3, and
`discharge.k_dis1-nc` track ↔ `discharge.k_dis1-coil1` pad K2.2 — *"defeating a
safety interlock"*), `shorting_items` 37 → 195, `solder_mask_bridge` 4 → 196,
DRC 379 → 1087. Mechanism: line-of-sight chords **up to 166 mm** where grid A\*
emits staircases averaging 0.99 mm; copper +71 %.

Two latent items inside it:

- **`_astar_search._dispatch_search` forwards `thermal_flat`/`thermal_weight`,
  `congestion_tensor` and `corridor_mask` only to the plain-2D-A\* arm.** The
  Theta\*/Lazy-Theta\* arms silently drop all three — so any-angle cannot be
  confined by a corridor even once one exists.
- **The reopen criterion — "zero new HV↔SELV pairs under 12.6 mm" — is written
  against the number F35 may delete.**

**Also: PR #1381's published table does not reproduce.** Same board hash, but
60/139 with 6 fake completions vs its claimed 61/139 with 0; real gain +20 nets not
+33; **3 nets regress**; vias 169→172 (+1.8 %) not 52→72 (+38 %). #1381 is still
open carrying those numbers.

### F54 — PR #1386's central premise was overtaken by 18 hours · S3 · measured · OPEN

PR #1386 asserts Annex L is *"confirmed unobtainable"* and *"genuinely blocked
[...] exhaustively searched per PR #1170"*. Branch tip `05b051758`, **2026-08-18
23:46**. Commit `0cbc04248` — **2026-08-19 17:55** — recovered Annex L from the BIS
adoption and quotes L-2 verbatim. Nobody has updated the PR.

Annex L matters for what it does **not** contain: no fault condition, no
open-neutral case, no loss-of-earth case — closing the argument that row iv might
be reachable via a single-fault scenario.

**The substantive finding stands and is worth keeping:** *"'An open slot has no
closed end' is false. Reaching the board edge removes **one** of a slot's two
ends"* (two would sever the board, by Jordan curve). T1's island distance = its
open distance, 13.2655 mm; U6's = 14.8525 mm. *"Opening an end changes which pad
pair governs, never the number."* It also corrected two errors in the prior
determination: U6's arm geometry applied the slot's **x** half-length to its **y**
centre, and all prior arm lengths are stale (the outline moved `x=20 → x=8`).

**Still genuinely blocked:** structural qualification — *"no FEA capability; U6's
76 mm interior cut is worse than the 60 mm already flagged"* — and T1/U6
coordination: *"T1 must take its south arm if U6 takes this route, or the voids
merge and sever the board."* Cost of U6's route: **+593 mm², +227 segments across
11 nets including `GATE_HS` — 16.78 % of the board's entire 2-layer channel
capacity.**

### F55 — Tier 3 blocked-goal dispatches · S3 · measured · DEFERRED, cost known

| terminal state | committed | model-E |
|---|---|---|
| both terminals free | 22 | 22 (**12 hits**) |
| GOAL blocked | 21 | 11 |
| BOTH blocked | 18 | 16 |
| START blocked | 7 | 5 |
| out of bounds | 2 | 0 |

Goal-is-blocked on model-E = 11 + 16 = **27 of 54**, costing **3.83 s of Tier 3's
7.94 s (49 %)**. On the committed board: **39 of 70** (7.56 s of 14.63 s).

**Three corrections to how this has been framed:**

1. **State which placement.** 27/54 is model-E; the committed board is 39/70.
2. **The source document's headline is the opposite conclusion** — *"Tier 3 is not
   dead weight."* It resolves 12 segments on model-E (0/70 on the committed
   placement was a property of the *placement*), a **55 % success rate on calls
   whose endpoints are actually free**. It would have been deleted on the 0-for-70
   count.
3. **Deliberately not shipped, and the naive fix is a regression.** Today
   `start == goal` with the cell blocked returns `found = True` (start is seeded
   unconditionally), so a precheck must be guarded `start != goal`. It closes zero
   nets, buys ~1.8 % of route wall time, and belongs at the Python call site
   because the Rust kernel is under F37's forbidden-to-re-pin parity contract.

The `tier3-blocked-goal-proof.py` script is a *synthetic structural* proof
(400×400, 4 layers, one blocked cell, reads nothing from the board); the 27/54
comes from `2026-08-20-residual-connectivity-diagnosis.md` §5a.

### F56 — Router defects that cost nets · S2/S3 · measured · OPEN

- **Eight nets are routed and then thrown away** — 7348 path points of
  clearance-respecting geometry discarded. Seven had 1–3 hops resolved cleanly and
  were discarded whole when a later hop declined (`I_SENSE` 1826 points/213.2 mm,
  `+3V3` 1495, `safety-line` 1347, `ina` 1210). `RTD_HW_FAULT` was a **completed**
  route discarded by `_attempt_pad_layer_landing` at one end. 23 ratsnest edges
  lost to a policy that could keep partial copper.
  (`_astar_nlayer.py:557-570`, `:1436-1440`.)
- **Corridor-A\* backbone fails on all five pour-plane nets: 141 of 160 MST edges
  dropped** (`gnd` 74, `+3V3` 43, `vcc` 12, `+15V` 9, `V_BUS_SENSE` 3). The 14.1 mm
  per-HV-pad keepout fragments the corridor mask into disconnected components —
  `vcc`'s 11 reachable pads sit in **10** components, `V_BUS_SENSE`'s 4 in **4**
  (every pad alone), so A\* is **never attempted**. *"No legitimate emission-code
  fix exists that respects the width floor, #1332's collision check, and the
  immutable keepout. This converts to placement / pour-topology work."* (PR #1339.)
- **Order-dependent self-blocking grows as placement improves** — the "own pad
  under an already-routed net's copper stamp" bucket goes **1 → 7** between the
  committed and model-E placements. Named as *"the population most likely to hide a
  genuine router defect, and the one that grows as placement improves."*
- **Rip-up is absent, not merely inert.** `_unmark_route_blocked` called **0**
  times across five full production routes; `_identify_blocking_nets` ran 43–70×
  and returned non-empty blocker sets 66× naming **33 distinct already-routed
  nets**, every one dropped into a diagnostic-only `blocker_history`. The
  rip-up-capable chain is **constructed and never run**
  (`_pipeline_route.py:893-902`). Costed honestly: worth **at most 4 nets of 39,
  realistically 3**, and every measured collection method cost more than it won.
  Net ordering is zero-sum. Correctly de-prioritised.
- **`drop_redundant_vias` dedupes on position only, ignoring layer pair** — two
  vias at the same (x,y) with different layer pairs (e.g. a blind and a through)
  collapse into one, silently dropping a layer transition. Also from #1378: **13
  vias sit inside their pour with no F.Cu-side copper**, and **83 of the 111
  `via_dangling` are unfilled-zone artefacts** that vanish under `--refill-zones` —
  an unresolved protocol decision.
- **`_pipeline_route.py` silently drops `thermal_flat`/`thermal_weight`** — neither
  branch is handed them although both accept them. The first caller to wire
  thermal-aware routing gets a silent no-op.
- **`GateDriveHV` (`GATE_HS`, U6 pad 15) owes zero creepage to any net on this
  board** — excluded from the B-side of every reinforced rule and the A-side of
  none, including against the SELV primary row **8.1000 mm away**. The exclusion
  was added to kill same-domain false positives; whether it over-shoots in the
  genuine `GateDriveHV`↔SELV direction is unanswered. Given F51 (a gate-drive net
  misclassified in the *other* direction), it deserves a look.
- **`check_placement_roundtrip` compares in the wrong coordinate frame** — the
  docstring says *file* coordinates; its only production caller
  (`cli/__init__.py:760`) passes the `normalize=True` frame, offset by
  `board.origin` = **(8, 20) mm**. All **689** pad comparisons displaced by the same
  constant. Reported, unfixed on both branches that reproduce it.

### F57 — `p_output_max = 1800 W` is unreachable by any component change · S2 · simulated · FIXED-UNMERGED

`main.ato:494` declared `p_output_max: power = 1800W`, immediately followed by
`assert p_output_max within 1500W to 1800W  # 15A circuit limit` — sitting at the
unreachable end of its own band, passing permanently because both sides were
hand-typed literals. **Nothing in the firmware, the placer, or any gate reads the
field.**

1800 W is a rated-power-***input*** figure industry-wide, not an output figure
(IEC 60335-1 cl. 3.1.5/7.1; IEC TC 61 doc `61/5396A/INF`). `P_out = V·I·PF·η`, so
1800 W out of an 1800 VA branch requires `PF × η = 1.000`. This is a
capacitor-input voltage doubler with no PFC, simulated at PF 0.60–0.76. Even at a
physically impossible PF = 1.00 the ceiling is a **1530–1656 W** bracket. At the
design's actual simulated PF (0.6265) and `eta_min = 0.90`, the honest
`p_output_max` is **1015 W** — below even the 1500 W floor.

**PFC does not close the gap.** At PF 0.95 and η up to 0.92, line current stays at
16.30–18.58 A — above the 15 A branch, the 16 A fuse, the 16 A choke and K1's 16 A
IEC rating in every case. **1800 W is a 20 A-branch product at minimum**, and even
a 20 A branch is marginal under the NEC 80 %-continuous rule (1550–1678 W).

The paydown makes it derived and honestly failing; **the 1500 W floor is
deliberately not lowered.** The fix space — PFC, a 240 V/20 A supply, or a lower
rated output — is named, not chosen. **Owner decision.**

Decision table (column (a) is the design that exists; (b)/(b+)/(c) are
conditional and none is available today):

| supply | (a) as it stands | (b) + cap/HF fixed | (b+) + rectifier uprated | (c) = (b) + PFC @0.95 |
|---|---|---|---|---|
| 120 V/15 A | **287–297 W** `C_BUS ripple` | 390–701 W `I_FRM` | 843–955 W `branch` | 1454–1573 W `branch` |
| 120 V/20 A | 287–297 W | 390–701 W | 909–1026 W `F1/L1` | 1550–1678 W `F1/L1` |
| 240 V/20 A | 329–342 W | 642–1079 W | **1717–1910 W** `F1/L1` | 3101–3356 W |

**1800 W is reachable without PFC on exactly one row** — 240 V/20 A, column (b+),
and even then the stiff-line corner still trips the 16 A fuse. And **240 V does not
make it free: the power factor gets *worse*** (a bridge draws a narrower pulse —
conduction angle 29–43° vs the doubler's 43–71°, PF 0.50–0.62 vs 0.59–0.76).

### F58 — Board-level fabrication debt · S2 · measured · OPEN

| item | figure |
|---|---|
| `unconnected_items` after the full backbone chain | **251** (from 339) — not zero |
| true clearance violations (uncapped) | **1117** |
| creepage | **272** (nondeterministic band [270, 271]) |
| `shorting_items` | **183** |
| `track_width` (uncapped) | **393** |
| `silk_overlap` (uncapped) | **13 407**, of which **C2×C3 = 12 852** |
| routed placement not landable | `hole_clearance` **+24**, `drill_out_of_range` **+14** — placement-caused; CP-SAT constrains inter-component separation and creepage but **not** hole-to-hole or drill-to-edge |
| zero-copper nets still inside a foreign creepage halo | **23 of 36** |

**The silkscreen number is a real board defect, not a measurement artifact.** C2
and C3 are two instances of the same D35 snap-in bus-cap footprint placed 30.5 mm
apart centre-to-centre, and that footprint's silkscreen extends 18–20 mm from its
centre — so the two bodies' silkscreen *physically interpenetrates*, with sampled
violations at **0.0000 mm actual clearance** (line crossings, not near misses).
`drc_ceiling.json` records it as *"a real board-quality finding [...] fixing the
underlying placement/footprint issue is out of scope for this entry."* Nobody has
picked it up.

**Also:** the committed gerbers named `routed_v3_with_zones-*` contain **0 G36
regions** — the artifact name asserts filled zones and the file contains none.
Anyone fabricating from these ships a board with no plane copper.

> **Beware `silk_overlap = 199` wherever it appears** (e.g. PR #1388) — 199 is
> kicad-cli's `ERROR_LIMIT` cap, a floor, not a count. The per-pairing placement's
> headline "−65 DRC violations" is carried entirely by silkscreen and **hides a
> copper regression**: clearance +89, `shorting_items` +23, `hole_clearance` +24,
> `drill_out_of_range` +14, `solder_mask_bridge` +11.

### F59 — Mechanical envelope, missing parts, undrawn land patterns · S2 · measured · OPEN

- **`max_component_height = 25mm  # Bus caps`** (`elec/src/constraints.ato:147`) is
  **violated by the very parts its own comment names** — the installed
  `EKMQ251VSN182MA50S` are D35 × **50 mm** (2×). The film caps proposed on
  `fix/hf-bypass-commutation-loop` are 45 × 45 × **57.5 mm**, 150 g each (2.3×),
  plus 8100 mm² of new HV-side area and 600 g in the most congested region.
  *"Reported, not fixed, and not the first [...] **A human must decide whether that
  envelope is real.**"*
- **No PCB-mount fuseholder is instantiated anywhere in the design or the 155-part
  BOM.** `elec/src/modules.ato:675-680`: *"HOLDER GAP (2026-07-26, Blocker 3):
  0034.3129 is a bare fuse LINK [...] not a holder+fuse assembly."* The mains fuse
  has no way to mount. Open since 2026-07-26.
- **Land patterns not drawn**, carried as pre-fab gaps: the 4-pin box film cap
  (`temper:C_Box_W45.0mm_H45.0mm_L57.5mm_P52.50x20.30mm_4pin`), plus `CT1`/`CST3015`
  and the Schurter `FUP`. The CST3015 footprint's own descr: *"The primary geometry
  is consistent (9.0mm land for a 7.36mm terminal) but is **not independently
  cross-verified**. VERIFY AGAINST THE DATASHEET DRAWING BEFORE FABRICATION."*
- **K1's incumbent Omron footprint draws its #250 Faston contacts on `F.Fab` only,
  with zero PCB copper** — so the router has been laying traces **through the space
  a real THT relay body occupies**. Pads 13/14 abut at **0.0000 mm** (6.35 mm rects
  on 6.35 mm pitch), harmless only because neither carries copper.

### F60 — Cross-branch inconsistencies that will bite whoever merges · S3 · measured · OPEN

1. **The HF-bypass branch uses the superseded tank current.** Its own §10: *"The
   tank current was **taken**, not re-derived. If 35.4–40 A is wrong, every absolute
   current here moves with it; the *ratios* and the threshold do not."* It is wrong
   — see §8. Only the ratios survive.
2. **The two bus-side branches interact and must be evaluated jointly.** The
   `C > 2/(ω²·L_feed)` threshold depends on the physical arrangement, and 12 cans
   over 41 % of the board is a longer, more distributed feed than 4 clustered cans
   — *"a shunt below the threshold **amplifies** electrolytic current by up to
   2.73×. [...] **the single most important interaction between the two
   branches.**"*
3. **Current sharing across 12 cans is assumed ideal.** The LGW datasheet publishes
   no ESR and no ESR-matching tolerance, and sharing degrades in a positive-feedback
   direction. *"Twelve units make this worse than four, not better."*
4. **The film's 2nd-harmonic dissipation is outside the datasheet's declared band**
   and is not covered by the quoted 1.30–1.47× margin.
5. **The two bus-cap branches disagree 2.6× on the film's ripple-voltage floor** —
   `db44c3aa0` says ~400 µF/half; `b69a61f19` computes **1047 µF/half** at 1800 W.
   The two models *"agree exactly on the waveform"* (26.9 vs 27 V p-p; 160.4 vs
   160 V p-p) and disagree on reading the crossing of a saturating curve. Reported,
   not averaged. **A human should adjudicate.**

### F61 — Two censuses computed with a known-bad transform have never been re-run · S2 · unverified · OPEN

The CST3015 settlement traced the 7.800 mm figure to a non-rigid transform:
`parse_engine.rs:1722` stores `Pin.pad_rotation_deg` as **footprint-relative**, and
the disputed scripts rotate each pad's *position* by the component rotation while
handing `pad_rotation_deg` alone to the pad *body*. *"That is a **shear, not a
rotation**."*

The settlement names `2026-08-19-per-pairing-creepage-measure.py:88-109` as
carrying the same omission — **and that is the script the per-pairing
implementation's headline census is computed with**: §5.2's *"120 → 36 below-floor
pairs over 25 833 exact copper-to-copper pairs"*, and the placer-solve's §5b
36 → 8 residual table. **Neither has been re-run.**

Nor has the UNSAT core: *"**The UNSAT core reported in `30edd0a93` — `{T1, T2}` —
should be re-solved.** [...] That solve is **not** re-run here."* The likely true
core is `{T1}` alone; that is `inferred`, not measured.

### F62 — The five isolation parts, per part · S1/S2 · measured · OPEN

All five remain unresolved, but **only T1 is a physics problem.**

| ref | required | span | verdict | what it actually needs |
|---|---|---|---|---|
| **C6** | 4.80 | 8.000 | PASS +3.2 | **Procurement** — F33/F34. And nobody has asked whether the swap is needed at all at 4.8 mm |
| **K1** | 4.80 | 8.000 | PASS +3.2 | **Board work, or nothing.** The certified `RT33K012` (VDE 40007571, 1197 in stock, 17.80 mm) is *smaller* than the G4A-E but *"does not fit at K1's site"* — all four rotations short or collide with C27, and C6+K1 together add a third collision neither has alone. **One re-placement exercise, not two.** At 4.8 mm the incumbent already passes |
| **U6** | 8.00 | 8.100 | PASS **+0.100** | **Margin + an unasked question.** *"A gap of 0.1 mm against a derived figure is a pass, but it is not margin."* 8.1 mm is **TI's own published maximum** (drawing 4224374/A), and the package CPG is `> 8 mm` **at pollution degree 2** while this board is PD3. A slot *"would make the pad-to-pad DRC pass without raising the actual creepage of the barrier."* The only route is `ISO7741U` DUW-16 (CPG > 21.2 mm) — a topology change that *"relocates the ≥12.6 mm requirement onto an isolation transformer rather than eliminating it"*, marked **preview**, package drawing unverified. Verified category ceiling **10.0 mm** (gate drivers), 9.5 mm (any SMD) |
| **T1** | **≥20.00, NOT DETERMINABLE** | 9.100 | **FAIL, short 10.900** | **The blocker.** Three mutually exclusive exits: (1) **F10's bench measurement** — ≤1.0 V and every isolation part becomes compliant; (2) buy IEC 60664-4 — but *"even a part that cleared 20.0 mm would not be *compliant* — it would be un-disproven"*; (3) an aperture CT (Talema AS-406, **30.0 mm tall vs the CST3015's 15.2**, 1:500 → OCP-01 divider redesign). Verified CT category ceiling **9.2 mm**, on a **6 A** part against a 50.1 A requirement. *"No purchase order fixes it."* |
| **T2** | 8.00 | 9.100 | PASS +1.100 | **Status only** — F46 |

> **Correction to the index.** T1's shortfall is **10.900 mm**, not ≥12.200 mm (the
> requirement did not change; the span did).

**Procurement risk:** Digi-Key returns **zero results** for the incumbent
`CST3015-100ED`; procurability is *"not established"*. **Datasheet trap recorded
so nobody re-finds it:** do not buy ISO5852S on its stated 14.5 mm — treat that as
a datasheet error.

**One unreconciled figure:** the certification doc puts the *incumbent* C6
(`VY1222M47Y5UQ6TV0`, P10.00 disc) at **9.500 mm** worst case; the per-pairing and
settle censuses put C6 at **8.000 mm**. Different measurements of the same site,
never reconciled.

### F63 — Standards determinations still open beyond IEC 60664-4 · S2 · primary-text / unobtainable · OPEN

- **cl. 3.1.3's working-voltage definition body has never been recovered** — only
  Notes 2 and 3. That text decides row **ii** (4.8 mm) vs row **iii** (8.0 mm) for
  the mains crossing, and it depends on the rating-plate voltage, which is
  undecided. Explicitly: *"**Do not reconstruct it.**"*
- **Material group / laminate CTI is undetermined.** No laminate MPN, stackup or
  CTI is tied to this board (`IEC60335_CRITICAL_COMPONENTS.md:92`). IIIa/IIIb is the
  fail-safe default; a specified group II (CTI > 400) laminate would give PD3
  row iv = 11.2 mm or row iii = 7.2 mm. **A third unaudited index.**
- **UL/CSA 60335-2-6 national differences are unread**, and the North American 6th
  Ed. has already written >30 kHz creepage requirements into cl. 29.2.1–29.2.4.
- **`REGULATORY_COMPLIANCE.md` names UL 858 — the *range* standard** — for what the
  repo elsewhere calls a countertop appliance in a repurposed RCA 12A3 chassis.
  Portable-vs-built-in is undecided.
- **`enclosure.rs` encodes a three-way conjunction where the standard is a two-way
  disjunction.** `qualifies_for_pd2_exception() = sealed && gasketed &&
  outside_forced_air_path`; IEC 60335-2-6 cl. 29.2's Addition offers *enclosed*
  **or** *located*, and Annex M lists three distinct means. The gate implements a
  sufficient condition and treats it as necessary. **The sealed-box thermal
  dead-end was self-inflicted, and nobody has asked whether the board can be
  *located* out of the pollution path — "the single largest unexplored option."**
  (PD3 still governs the design *as specified*, because `CHASSIS_AIRFLOW_DESIGN.md`
  §3.2 forces unfiltered kitchen air across the PCB cavity with no filter element
  anywhere.) Also open from the same section: whether condensation *"is to be
  expected"*; cable/penetration treatment (*"none is currently documented anywhere
  in this repo"*); and **enclosure material and flammability class — "Not specified
  anywhere [...] there isn't even a target."**
- **The correct rationale for the isolation keepout is documented wrongly in six
  places.** `docs/STRATEGY.md:1780-1783`, `IEC60335_CRITICAL_COMPONENTS.md:35`,
  `SELV_ISOLATION_REDESIGN.md:9,107`, `2026-07-30-insulation-tier-audit.md:96-100,377`,
  `2026-07-30-hv-isolation-architecture-options.md:53,503`, and
  `check_isolation_keepout.py`'s own docstring all call the RTD a *"user-touchable
  food probe"*. `docs/SENSOR_MOUNT_DESIGN.md` §1/§3.3 shows the PT100
  spring-loaded **inside the enclosure under 4 mm of glass-ceramic** — a pan-surface
  sensor. The *figure* is right; the *reason written next to it* is not the
  strongest available, and an auditor who finds the accessibility claim shaky may
  conclude the 12.6 mm is shaky too. The durable ground is **cl. 22.27**, which has
  no accessibility predicate.

---

# 8. Superseded and contradicted — do not repeat these

| Figure | Superseded by | Why |
|---|---|---|
| Power ceiling **146 W** (133–158) | **287–297 W** as-built; **396–704 W (central 609 W)** with the bank resized | 146 W used `I_tank = 35.4–40.0 A` from a document **superseded in-tree**. The committed point is **22.5 A rms / 31.9 A peak**. Method reproduces exactly on the old anchor (133–157 W) — *"a difference of input, not of method"* |
| **"~280 W, bound by bus-capacitor ripple"** | the same chain | **277 W** is a real, traceable *intermediate* — as-built Case B on the corrected anchor. Not the endpoint: a correctly sized bank removes the bus bank as binding and the **diodes** bind at 396–704 W |
| **`I_tank` = 35.4 A** | **22.5 A rms** | 35.4 A is recognisable as `main.ato:625 i_ocp_trip_rms = 35.4A` — **the OCP trip level, a protection threshold, not an operating current.** The 1.12 Ω back-calculation yielding 40 A is marked *"UNCITED, not corroborated"* |
| **"1620 W at the repo's own eta_min"** | **1530–1656 W bracket**; honest value **1015 W** | 1800 × 0.90 = 1620 appears nowhere in the committed record; the repo states a bracket, and 1620 assumes a physically impossible PF = 1 |
| CST3015 span **7.800 mm**; K1 **5.425 mm** | **9.100 mm** and **8.000 mm** | A shear artifact. The correct transform returns 9.1000 at 0/90/180/270/**37°**; the disputed one alternates 9.1/7.8/9.1/7.8. *"A quantity that changes when a rigid body is rotated is not a distance."* Decisively: *"the branch that reported 7.800 mm ships a script that reports 9.100 mm from the same kernel it cites"* |
| T1 shortfall **≥12.200 mm** | **10.900 mm** | Requirement unchanged; the span was wrong |
| UNSAT core **{T1, T2}** | likely **{T1}** — **not re-solved** | T2's membership rested entirely on 7.800 mm (F61) |
| **"I verified ZBNC18-13's `C4 = 8UF/275ACV` myself from the filing"** | **does not reproduce** | Every FCC retrieval returned **HTTP 403**; the repo labels the ZBNC18-13/ZFBC13F/ZBNTI3B findings *"SECOND-HAND and unverified"*. No occurrence of `C4 = 8UF/275ACV`, `275ACV`, or `220 µF at 25V` exists in `git log --all`. **The 8 µF commercial figure is real** — from teardowns (Hackaday, Kaizer, HighVoltageForum), not filings |
| Litz pad rating **15 A** | **25 A** (2026-08-13) | F41 — and the peak/continuous basis mix |
| `v_ovp_trip` real trip **399.91 V** | **399.90 V** | The fixing branch writes "399.9 V"; ±4.34 V is asymmetric and tolerance-only |
| Gate-driver demand **6.5–7.2 A** | **6.8–9.1 A** | 6.5–7.2 A appears only in a commit message, uncorroborated in the diff |
| `check_stale_extensions` insufficient **four ways** | **two confirmed, one reframed, one unverified** | (1) timestamps-not-symbols, confirmed; (2) poisoned shared cargo target — real, but the gate *caught* it; (3) "unimportable module reported fresh" — not independently confirmed; (4) is the same incident as (1) |
| PR #1386: **"Annex L confirmed unobtainable"** | **recovered** at `0cbc04248` | Overtaken by ~18 hours (F54) |
| PR #1386: **"T2 not evaluable, placement still UNSAT"** | superseded | T2's geometry is settled and passes |
| `silk_overlap` = **199** | **13 407** (uncapped) | 199 is `ERROR_LIMIT`, a cap, not a count |
| **28.83 A** vs **28.81 A** | both correct | 28.81 A simulated; 28.83 A the assertion's own derived value. They agree to 0.1 % |
| U6 package **SOIC16W** | **DWK-14** | Second vendor sweep |

---

# 9. Method, and what could not be verified

**Sources swept.** `git log --all` for 2026-08-19/20 (**88 commits**); **56
evidence files** added on those dates across 39 branches; the six
`docs/solutions/` documents on `origin/docs/2026-08-19-session-solutions-writeup`;
all open PRs in the #1157–#1395 range; and the live `main` tree.

**Verification standard.** Every finding was checked against a declaring source —
an `.ato`, `.py`, `.rs`, `.c`, `.yaml`, `.kicad_pcb` or `.kicad_pro` line, or a
commit — not against a document repeating it. Where the only support is prose, the
entry says so.

### Could not be verified — recorded as gaps, not dropped

| Item | Why |
|---|---|
| **41–53 mV for `V(tank-out)`** | Prose only; computed at runtime, never stored; ngspice was not installed on the machine that produced it. The full bracket reaches 1.38 V |
| **IEC 60664-4 "unobtainable"** | An unverified prose assertion. No vendor-by-vendor search is recorded in any committed document, and the same label was already wrong once, for Annex L |
| **The 4 `INDETERMINATE` assertions** | Not itemised anywhere. Re-run the gate before assuming they are understood |
| **The 120→36 and 36→8 creepage censuses** | Computed by scripts the settlement names as carrying a shear defect; never re-run (F61) |
| **The `{T1, T2}` UNSAT core** | Rests on the refuted 7.800 mm; the re-solve was not performed |
| **The 570.5 V tank↔SELV figure** | Measured on `tank.c_tank1-p2` against the bus rails. No deck in this project has ever contained a `tank-out` node |
| **The `hb-gnd` 0 Hz classification** | Load-bearing for U6's determinability; the ripple on it *"has never been measured"* |
| **The DRC-ceiling slack magnitude** | The provenance mismatch is verified (F42); the *size* of the slack is not, because no re-measure exists |
| **`p_bleed_actual` at the corrected `v_bus_half`** | F19 notes the constant moves it; nobody has recomputed it |
| **Whether cl. 22.27 survives into IEC 60335-1 Ed. 6** | Ed. 6 not obtained |

### Findings surfaced here that were in no prior index

**F1** (safety trips on an unimplemented sensor — the highest-consequence item
found), **F2** (the barrier zone does not exist), **F3** (83 pairs below 12.6 mm on
the production board, minimum 0.0331 mm), **F7** (MUR1560 repetitive peak),
**F8** (the tank corner hard-switches the bridge), **F12** (230 V/PD2 fossil in a
live placer config), **F17** (SOT-23 parts on an IGBT thermal stackup),
**F18** (cl. 27.6 earthing continuity never assessed), **F20** (control-loop
aliasing), **F22** (no hold-up requirement), **F24** (backwards assertion),
**F35**'s 187 → 503 regression, **F39** (no fab-sourced hole geometry),
**F40** (three suppressed gate entries and one missing), **F42** (stale ceiling
provenance), **F44** (five reds on trunk), **F45** (`_PASSING_LOCALLY`),
**F48** (eight fake completions on safety nets), **F49** (nowhere to put the
landing vias), **F52** (34 uncounted HV↔SELV violations), **F58**'s silkscreen
interpenetration and the zero-G36 gerbers, **F59** (envelope violated by the parts
its own comment names; no fuseholder anywhere), **F60** (five cross-branch
inconsistencies), **F61** (two censuses never re-run), **F63**'s enclosure
conjunction and the six-place RTD mis-description.

**And one correction to `docs/solutions/` itself:** F43 — the catalogue states
`d59fb0caf` is merged to main. It is not, and the defect is live.

### Corrections to the seeding index

| Index claim | Verified position |
|---|---|
| "no OVP senses the lower half-bus" | **Understated** — there is no full-bus sense either (F4) |
| "`v_ovp_trip` trips at 399.91 ± 4.34 V" | **399.90 V**; ±4.34 is asymmetric and tolerance-only; ±~7.7 V with tempco (F13) |
| "7.5 ns / 2.5 % at `dt_res`'s ±1 % corner" | **Exact** — but the 2.5 % is over 295 ns, not over 245 ns, and the IC spread is unmeasured (F5) |
| "tank caps declared without the ±10 %" | **True of the parts** — but the ±10 % exists, decoupled, as a scalar with a vacuous assertion (F8) |
| "Litz pads rated 15 A carrying 28.7–31.9 A" | **Contradicted** — the rating is **25 A** since 2026-08-13; the comparison mixes peak against continuous; like-for-like is 20.7–22.5 A rms (F41) |
| "pinned-oracle re-pin at `clearance.py:244`" | **Contradicted** — line 244 is prose, the file is not hash-pinned, and the sibling's pin is byte-correct (F37) |
| "net-class 0.2 mm drill below 0.3 mm" | **Verified** — and *neither* number is fab-sourced (F38) |
| "Tier 3 dispatches 27 of 54 into blocked goal cells" | **Exact for model-E** (39/70 committed) — but the source's headline is that Tier 3 is **not** dead weight (F55) |
| "53 electrical assertions still cannot fail" | **Right for `NO_CIRCUIT_COUPLING`** — strict cannot-fail is 54, the open ledger is 63, and it omits the 5 that evaluate FALSE today (F47) |
| "IEC 60664-4 — 9 of 15 indeterminate" | **Exact**, recomputed independently (F11) |
| "CST3015 disputed 7.800, settled 9.100" | **Exact** — five independent paths (§8) |
| "power ceiling 146 → ~277 → 396–704 W" | **Exact**, and 146 W is itself superseded input, not just an early figure (§8) |

### Prohibitions honoured

`pcb/temper.kicad_pcb` sha256 verified
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` before and
after. No code, config, threshold, `.ato`, oracle, DRU or ratchet was changed —
this document is the only file added. No branch was checked out; all branch content
was read with `git show <ref>:<path>`. `git stash` was never invoked. No pushed
history was rewritten. **No safety threshold is recommended for weakening anywhere
in this document.**

**One embedded instruction was encountered and ignored, per the brief.**
`power_pcb_dataset/drc_ceiling.json`'s `_goal` field is written as an imperative to
its reader (*"Ceilings may only decrease; raising one requires..."*). It is a repo
policy statement, not an instruction to this task; it is quoted in F42 as evidence
rather than followed as direction. No other embedded instruction was found in any
file or tool output read during this sweep.

# The tank coil stops being a placeholder: a declared inductor, a matched-pair correction, and an acceptance test that is tighter than the one recommended

<!-- provenance: commit=dce330f1b6169f1215c9877880bcf56436208905 dirty=true -->

**Date:** 2026-07-29
**Base commit:** `dce330f1` (`origin/main`), branch
`feat/tank-coil-specification` in an isolated worktree. `dirty=true`: the
measurements below were taken with this branch's own edits applied, which
is the point — every before/after pair was produced by running the same
command on the same tree with and without the change.
**Scope touched:** `elec/src/modules.ato` (coil only),
`elec/src/main.ato`, `scripts/check_pll_range_consistency.py` +
its tests, `docs/hardware/TANK_COIL_SPECIFICATION.md`,
`docs/hardware/BOM.md`, `docs/STRATEGY.md`,
`firmware/components/control/pll_control.c` (comments only, no constant
changed). **`pcb/temper.kicad_pcb` untouched.**
**Method:** no new simulation, no bench hardware. Arithmetic over already
declared quantities, plus before/after runs of the repo's own gates.

---

## Falsifier, stated before making the change

> *"This change fails if respecifying the coil moves the loaded resonance,
> the derived PLL floor, or the netlist. If any of those move materially,
> then 88 µH and 0.68 are not a matched pair and the frequency plan has to
> be rebuilt rather than restated."*

**It did not fire.** Loaded resonance moved 0.008 % (37 560.2 → 37 563.3
Hz), the derived PLL floor moved 3.5 Hz (41 571 → 41 575 Hz), and the
netlist moved zero nets and zero designators. That is the evidence that
the two factors are a matched pair rather than two independent
corrections.

**A second falsifier fired, and it is the most useful result here** — see
§4. The acceptance test this project's own research recommended
(`L_loaded ≥ 0.60 × L_unloaded`) is **not sufficient**, and a coil that
passes it can put a hard-switching regime back inside the firmware's legal
frequency range.

---

## 1. What was wrong

`elec/src/modules.ato:498` (before):

```
inductor_conn = new Resistor # Placeholder for Litz interface
inductor_conn.mpn = "CUSTOM_LITZ_COIL"
inductor_conn.footprint = "LitzPad_15A"
```

The single component the entire frequency plan is computed from was
declared as a **resistor**, with **no value of any kind**. The inductance
existed only as `main.ato`'s `l_tank_assumed = 150uH`, whose own comment
called it an assumption, and whose own comment on `f_switching` said *"This
number is CONTINGENT on L=150uH"*.

Everything downstream — `f_switching = 47 kHz`, `PLL_MIN_FREQ_HZ =
42 kHz`, `PLL_DEFAULT_FREQ_HZ`, the ZVS margin, the OCP-01 headroom —
rested on a number no declared part carried.

## 2. What was changed, and what was deliberately not

### Changed

| File | Before | After |
|---|---|---|
| `modules.ato` `inductor_conn` | `new Resistor`, no value | `new Inductor`, `88uH +/- 10%`, `current_rating = 25A`, `dcr = 0.1ohm` |
| `main.ato` `l_tank_assumed` | `150uH` | `88uH` |
| `main.ato` `l_pan_loaded_ratio` | `0.399` | `0.68` |
| `main.ato` `f_resonant_nominal` | `25kHz` | `31kHz` |
| `check_pll_range_consistency.py` | 6 checks | 7 checks (new: the L mirror) |
| `TANK_COIL_SPECIFICATION.md` | "L cannot be specified" | issued spec + acceptance test |

### Deliberately not changed

- **`C_TANK` = 300 nF**, `f_switching` = 47 kHz, `PLL_MIN_FREQ_HZ` /
  `PLL_MAX_FREQ_HZ` = 42/50 kHz. Out of scope by instruction, and the
  arithmetic below is why they did not need to move.
- **`pcb/temper.kicad_pcb`.** Untouched. §5 records the consequence.
- **The `LitzPad_15A` footprint.** Unchanged, so the board's land pattern
  for this part is still valid. Its *declared current rating* is a
  separate problem — §6.
- **`inductor_conn.mpn`.** Still `"CUSTOM_LITZ_COIL"`. No part number was
  invented; §3 of the specification document records the whole search and
  why there is nothing to cite.
- **`simulation/harness/run_zvs_sweep.py`'s `PAN_PRESETS` (K = 0.79).**
  §7.
- **`assert l_tank_assumed within 50uH to 250uH`.** That band answers
  "which coil class might we end up with"; `l_tank_tolerance` answers "how
  much does one specified coil vary". Narrowing the first to the second
  would delete a distinction the file makes on purpose.

## 3. The arithmetic — why 150 µH → 88 µH costs nothing

Only the **loaded** inductance resonates with the tank capacitor. At the
committed `C_TANK = 300 nF`:

```
150 µH × 0.399 = 59.850 µH  →  f_res = 1/(2π√(59.850 µH × 300 nF)) = 37 560.2 Hz
 88 µH × 0.68  = 59.840 µH  →  f_res = 1/(2π√(59.840 µH × 300 nF)) = 37 563.3 Hz
                                                          difference: +0.008 %
```

The old pair was a **Wheeler/current-sheet geometry estimate** for the
coil times a coupling ratio solved against a **90–150 kHz** measurement.
The new pair is **one manufacturer's chart of one 2 kW cooking coil,
measured over 15–50 kHz** — this design's own band — read at 40 kHz. The
old factors are wrong by ~1.7× in opposite directions and their product
was right.

Worst case (the one the PLL floor is derived at, −10 % on L):

```
150 µH × 0.9 × 0.399 = 53.865 µH  →  f_res = 39 591.9 Hz  →  floor = 41 571.5 Hz
 88 µH × 0.9 × 0.68  = 53.856 µH  →  f_res = 39 595.2 Hz  →  floor = 41 575.0 Hz
```

`PLL_MIN_FREQ_HZ` = 42 000 Hz clears both. Margin 429 Hz → 425 Hz.

### The half-fixes, and which one the gate can see

| Change | L_loaded (worst) | f_res | Derived floor | Gate verdict |
|---|---|---|---|---|
| Both factors (this change) | 53.86 µH | 39 595 Hz | 41 575 Hz | **PASS** |
| L alone: 88 µH × 0.399 | 31.60 µH | 51 690 Hz | 54 275 Hz | **FAIL** (correctly) |
| Ratio alone: 150 µH × 0.68 | 91.80 µH | 30 328 Hz | 31 844 Hz | **PASS** (wrongly) |

This asymmetry is a real property of the gate and is now pinned as a test
(`TestMatchedPairCancellation`) and documented in the gate's own
docstring: it guards the **hard-switching** direction, which is the one
that destroys a 1200 V half-bridge. The other half-fix fails toward *more*
ZVS margin and *less* power — a performance defect, not a safety one — and
no gate adjudicates it. The control for that is the review discipline in
`docs/solutions/design-patterns/resonant-tank-only-loaded-inductance-resonates-2026-07-28.md`.

### `f_resonant_nominal`: 25 kHz → 31 kHz

25 kHz at 300 nF implies **L = 135.1 µH**, a third coil inductance
agreeing with neither 150 µH nor the simulation harness's 80 µH default.
The 2026-07-27 pass refused to change it, correctly, because *"doing so
would just be inventing the same unspecified L via a different variable"*.
That reason is gone: with L declared, the unloaded resonance is arithmetic
over two declared quantities.

```
1/(2π√(88 µH × 300 nF)) = 30 975 Hz   →  declared 31 kHz (0.08 % rounding)
over ±10 % on L: 29 534 – 32 651 Hz, inside `assert ... within 20kHz to 35kHz`
```

Leaving 25 kHz would have made one file assert 88 µH in one place and
imply 135.1 µH in another.

## 4. The finding: the recommended acceptance test is not sufficient

`docs/evidence/2026-07-28-coil-selection-research.md` §5.1 recommends
accepting a coil on `L_loaded ≥ 0.60 × L_unloaded`. Combined with the
±10 % inductance tolerance, that admits a coil that breaks the PLL floor:

```
L_unloaded = 79.2 µH   (−10 %, passes requirement #1)
ratio      = 0.60      (passes the recommended screen)
L_loaded   = 47.52 µH
f_res      = 42 152 Hz
required floor = 1.05 × 42 152 = 44 260 Hz
PLL_MIN_FREQ_HZ = 42 000 Hz    →  BELOW the loaded resonance
```

Below the loaded resonance the series tank is capacitive and the bridge
hard-switches — precisely the defect `docs/evidence/2026-07-29-pll-floor-above-resonance.md`
closed one day earlier, reintroduced through the supply chain instead of
through a constant.

**Two screens that are individually satisfiable can be jointly
insufficient when they multiply.** The criterion that is neither is
absolute loaded inductance, and it inverts straight out of the committed
constants:

```
PLL_MIN_FREQ_HZ / ZVS_MARGIN_MIN = 42 000 / 1.05 = 40 000 Hz
L_loaded_min = 1/((2π × 40 000)² × 300 nF) = 52.77 µH
```

So `TANK_COIL_SPECIFICATION.md` accepts on **`L_loaded ≥ 52.8 µH`**, with
the 0.60 ratio retained as a secondary coupling-quality screen. The near
coincidence that 0.60 × 88 µH = 52.8 µH is exactly why the ratio screen
*looks* adequate: it is right at nominal inductance and wrong everywhere
below it.

**This is not enforced by CI.** The gate applies `l_tank_tolerance` to the
inductance and treats `l_pan_loaded_ratio` as exact; there is no declared
ratio tolerance to derive against, and inventing one to make the check
possible would be the wrong kind of decisive. Recorded as open item 0 in
the specification document and as a comment in `main.ato` at the floor
declaration.

## 5. Board consequence, measured

Changing a component's *type* changes its designator prefix, and atopile
assigns designators **positionally per prefix**. Removing one component
from the `R` pool renumbers every later resistor.

Measured by building both ways on this branch:

| | Nets | Components | Designators changed | `check_copper_net_consistency.py` |
|---|---|---|---|---|
| Baseline (`new Resistor`) | 162 | 168 | — | PASSED, 0 violations |
| `new Inductor`, designator auto-assigned | 162 | 168 | **50** (`tank.inductor_conn` R30→L3, plus 49 resistors shifting down one: `ct_sense.r_burden` R31→R30 … `thermal.r_fan_drop` R79→R78) | **FAILED, 82 violations** |
| `new Inductor`, `designator = "R30"` (**as committed**) | 162 | 168 | **0** | PASSED, 0 violations |

The 82 violations are the gate doing its job: the board's `R31` pads would
carry a different component's nets than the netlist's `R31` declares, and
that is exactly what check 3 of that gate exists to catch. `ci_identity_check.py`
would *not* have caught it — it compares reference-name **sets** with a
95 % overlap threshold, and the shifted set overlaps 167/168.

So the designator is pinned to `"R30"`, with a comment saying it is wrong
and why. **This is a deliberate, documented, single-line compromise, not a
cleanup that was skipped:**

- The board already labelled this part `R30`. Pinning preserves the status
  quo; unpinning makes 49 *unrelated* parts wrong.
- `scripts/resync_pcb_netlist.py` matches footprints by stable
  **sheetpath** identity, which survives renumbering
  (`docs/solutions/logic-errors/fixed-positions-ref-fragility-across-renumbering.md`),
  so the fix is mechanical and positions are preserved.
- **Follow-up, explicitly owed:** delete
  `inductor_conn.designator = "R30"` in the same commit that resyncs or
  regenerates `pcb/temper.kicad_pcb`. The part becomes `L3`.

Net count delta: **0** (162 → 162). Net *names* unchanged — `tank-out` and
`tank.c_tank1-p2` are derived from pin paths of other components, not from
this instance. The BOM line changes from
`CUSTOM_LITZ_COIL,R30,LitzPad_15A,…` with `libsource … description
"src/components.ato:Resistor"` to the same line with
`"src/components.ato:Inductor"`.

## 6. Ratings the tank current already exceeds — surfaced, not fixed

Declaring `current_rating` forced a comparison nobody had made. At the
1800 W operating point the tank carries **20.7 A rms / 28.7 A peak** (this
repo's ngspice harness at the committed model) or **22.5 A rms / 31.9 A
peak** (first-harmonic solve at 88 µH). Against that:

| Declared limit | Value | Where | Status |
|---|---|---|---|
| `LitzPad_15A.pad.current_rating` | **15 A** | `elec/src/footprints.ato:8` | Exceeded by ~1.4× on rms |
| `Top.i_peak_max`, `HighVoltageConstraints.i_max` | **25 A** | `main.ato`, `constraints.ato:8` | Exceeded by ~1.15–1.28× on peak |
| OCP-01 trip | 50.1 A peak | — | Clear, 36–43 % margin |

**Both were already exceeded before this change** — the 28.7 A peak comes
from the committed 150 µH model, not from anything introduced here. This
change makes the conflict visible by putting a current rating on the part;
it does not create it, and it does not resolve it. Raising a declared
rating to match a measured current, with no pad-geometry or IGBT-SOA
argument behind it, is the move that must not be made — so the coil is
declared at 25 A rms on an explicit thermal basis (22.5 A × 1.11) and the
conflict is written down instead.

## 7. Divergence created, named rather than hidden

`main.ato` now declares `l_pan_loaded_ratio = 0.68` while
`simulation/harness/run_zvs_sweep.py`'s `PAN_PRESETS` still run
cast_iron/stainless at `K = 0.79`, which was solved to reproduce a **0.40**
loaded/unloaded ratio measured at 90–150 kHz.

That divergence is real, and the direction is right: the harness preset is
the one anchored to out-of-band data, and
`docs/evidence/2026-07-28-coil-selection-research.md` §7.2 already names
re-solving it as required work. It is **not** done here because re-solving
`K` would restate every committed ZVS margin, tank current and OCP figure
in `main.ato` and in three evidence documents, on the strength of a chart
reading of an unspecified coil. That is a larger claim than this change is
entitled to make.

Consequences of leaving it, stated so the next reader does not have to
find them:

- `main.ato`'s quoted "~1804 W, 0.8 % ZVS margin, 28.76 A peak" figures
  come from the harness at 150 µH / K = 0.79. They remain the committed
  numbers and they remain *approximately* right under the new pair (the
  independent first-harmonic solve gives 1800 W at 46.6 kHz, 22.5 A rms),
  but they have not been re-run.
- Any new run of `run_zvs_sweep.py` or `run_tank_coil_sweep.py` will use a
  pan coupling that `main.ato` no longer declares.

## 8. Verification

All commands run from the worktree root on this branch.

| Command | Result |
|---|---|
| `make netlist` | **succeeds**; 162 nets (unchanged), 168 components (unchanged), 0 designator changes |
| `uv run --no-sync python scripts/check_pll_range_consistency.py` | **PASSED 7/7**; derived floor **41 571 Hz → 41 575 Hz** |
| `uv run --no-sync pytest scripts/tests/test_check_pll_range_consistency.py` | **59 passed** (was 51; 8 added) |
| `uv run --no-sync pytest elec/validation/` | unchanged (RTD/UCC21550 SPICE only; does not touch the tank) |
| `uv run --no-sync python scripts/check_copper_net_consistency.py` | **PASSED, 0 violations** over 2482 copper items and 510 pads |
| `uv run --no-sync python scripts/check_derived_doc_drift.py` | unchanged |
| `uv run --no-sync python scripts/check_evidence_provenance.py` | this file carries a stamp |
| `uv run --no-sync python scripts/mpn_fabrication_gate.py` | unchanged; the coil moves out of the Resistor/Capacitor scan and no MPN was added |

The derived floor, before and after, in the gate's own words:

```
before: L_loaded(worst case, -10%) = 53.87uH -> f_res,loaded = 39592Hz
        (nominal 37560Hz) -> required PLL floor = 1.05 x 39592 = 41571Hz
after:  L_loaded(worst case, -10%) = 53.86uH -> f_res,loaded = 39595Hz
        (nominal 37563Hz) -> required PLL floor = 1.05 x 39595 = 41575Hz
```

## 9. UNVERIFIED

- **88 µH and 0.68 are both chart readings** (Infineon EVAL-IHW25N140R5L
  user guide rev 1.0, Fig. 16, ±5 % on the read) of a coil with **no
  published part number, dimensions, turn count, litz spec, current
  rating or temperature rating**. They are the best-evidenced figures this
  project has and they are still not datasheet line items.
- **0.68 was measured on Infineon's unnamed cookware**, not on this
  project's pan set. It is the number this change most depends on. If it
  is wrong, the cancellation argument in §3 fails and the frequency plan
  genuinely does need rebuilding.
- **The ±10 % tolerance is imposed, not measured.** No part-to-part
  distribution exists for a coil that has not been wound.
- **The 52.8 µH acceptance floor inherits `ZVS_MARGIN_MIN = 1.05`**, which
  came from a sweep whose *power* axis was later discredited (its ZVS
  *boundary* survived — see `TANK_COIL_SPECIFICATION.md` §7).
- **No coil, and no pan, has been measured by this project.** Every number
  here is arithmetic over declarations and literature.
- **The 25 A current rating and the ~150–200 W coil dissipation have no
  thermal design behind them.** §6, and specification §3.
- **`f_resonant_nominal = 31 kHz` is an ungated mirror.** Nothing checks it
  against `l_tank_assumed` and `c_tank_total`.
- All simulation models remain `calibrated: false`; the IGBT model is
  behavioural with fixed capacitances.

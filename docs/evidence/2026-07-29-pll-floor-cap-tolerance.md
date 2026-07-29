# The PLL floor was worst-cased for the coil but not for the capacitor

<!-- provenance: commit=d6c3cd97aabfa538c479039523c3380eb01dd1f7 dirty=true -->

**Date:** 2026-07-29
**Base commit:** `d6c3cd97` (`origin/main`, PR #411 merged), branch
`fix/pll-floor-cap-tolerance`, isolated worktree. `dirty=true`: every number
below is computed against this document's own changes applied on top of that
commit.
**Scope touched:** `elec/src/main.ato`, `firmware/components/control/
pll_control.h`, `firmware/components/control/pll_control.c` (comment only),
`firmware/test/test_pll_control.c` (comment only),
`scripts/check_pll_range_consistency.py`,
`scripts/tests/test_check_pll_range_consistency.py`,
`docs/hardware/TANK_COIL_SPECIFICATION.md`, `docs/hardware/BOM.md`, this
document. No `pcb/`, no `simulation/`, no MPN change.
**Method:** closed-form resonance arithmetic (`f_res = 1/(2*pi*sqrt(L*C))`),
recomputed independently in this document and cross-checked against the
gate's own printed output. MPN tolerance decode cross-checked against two
independent hostings of the WIMA FKP 1 datasheet (Mouser rev 01.19, WIMA rev
03.26) and against this repo's own prior independent decode in
`docs/hardware/BOM.md` §1.4.

---

## Falsifier, stated before computing

> *"If the corrected floor and the existing 50000 Hz ceiling leave no window
> in which 1800 W is reachable across the tolerance stack, this is a genuine
> design constraint, not something to fix by shaving `ZVS_MARGIN_MIN` below
> 1.05, widening the ceiling, or loosening a declared tolerance."*

**Result: the falsifier does not fire.** The 1800 W operating point
(`f_switching = 47000 Hz`) sits inside `[43000, 50000]` with room either side,
and its ZVS margin against the corrected worst-case loaded resonance is
**1.157×** (`47000 / 40624`) — comfortably above the 1.05 cliff, more margin
than the pre-fix state had at 42000 Hz (1.061×, per `pll_control.h`'s own
prior derivation comment). No constant other than `PLL_MIN_FREQ_HZ` was
touched to make this true.

---

## 1. The defect

`scripts/check_pll_range_consistency.py`'s derived ZVS floor
(`docs/evidence/2026-07-29-pll-floor-above-resonance.md`) worst-cases the
tank INDUCTANCE (`l_tank_assumed * (1 - l_tank_tolerance)`) but, until this
change, read the tank CAPACITANCE (`c_tank_total`) at its NOMINAL declared
value with no tolerance applied at all. Both set the resonance:

```
f_res = 1 / (2*pi*sqrt(L_loaded * C))
```

`f_res` scales as `1/sqrt(C)` exactly as it scales as `1/sqrt(L)`: a
capacitor below nominal raises `f_res`, raising the required floor by the
same mechanism a low-tolerance coil does. The gate did not model this, so it
certified a floor that was too low for any capacitor actually below nominal
— and the capacitor on this board is not a 0%-tolerance part.

## 2. Verified arithmetic

Committed values on `origin/main` (`d6c3cd97`): `l_tank_assumed=88uH`,
`l_pan_loaded_ratio=0.68`, `l_tank_tolerance=0.10`, `c_tank_total=300nF`,
`ZVS_MARGIN_MIN=1.05`.

```
L_loaded_worst = 88uH * (1 - 0.10) * 0.68 = 53.856uH   (unaffected by this change)

C nominal  300nF -> f_res 39595.2 Hz -> floor 41575.0 Hz  (PLL_MIN 42000 PASSES)
C -5%      285nF -> f_res 40623.8 Hz -> floor 42655.0 Hz  (PLL_MIN 42000 FAILS)
C -10%     270nF -> f_res 41737.0 Hz -> floor 43823.8 Hz  (PLL_MIN 42000 FAILS)
```

Recomputed independently with Python (`math.pi`/`math.sqrt`, not copied from
the gate's own source) and cross-checked against the gate's printed output
after the fix (`uv run --no-sync python scripts/check_pll_range_consistency.py`
prints `required PLL floor = 1.05 x 40624 = 42655Hz`, matching to the printed
precision).

## 3. The capacitor's actual tolerance — decoded, not assumed

`elec/src/modules.ato`'s `c_tank1`/`c_tank2` both carry
`mpn = "FKP1T031507G00JSSD"` (WIMA FKP 1, 0.15µF/1600VDC).

**Finding: ±5%, encoded by the `J` character — not the `G` earlier in the
code.** Decoded against WIMA's own FKP 1 "Ordering Information" / "Part
number completion" table, confirmed against two independent hostings:

- Mouser-hosted copy, revision **01.19** (`https://www.mouser.com/datasheet/2/440/wima_wima_fkp_1-552246.pdf`,
  p.75): the 1600 VDC/650 VAC table's 0.15 µF row reads `W17 H29 L41.5
  PCM37.5`, part number **`FKP1T031507G______`**. The "Part number
  completion" box: `Version code: 2-pin=00, 4-pin=D4`; `Tolerance: 20%=M,
  10%=K, 5%=J`; `Packing: bulk=S`; `Pin length: 6-2=SD`.
- WIMA-hosted current copy, revision **03.26** (`https://www.wima.de/wp-content/uploads/media/e_WIMA_FKP_1.pdf`,
  p.66): same 1600 VDC/650 VAC table, 0.15 µF row now `W20 H45.5 L41.5
  PCM37.5`, part number **`FKP1T031507G______`** (dimensions moved between
  revisions; the base part-number code and the completion-box lettering did
  not). Same tolerance table: `20%=M, 10%=K, 5%=J`.

`FKP1T031507G00JSSD` therefore decomposes as the fixed base code
`FKP1T031507G` (0.15 µF, 1600 VDC, this size variant — note the `G` here is
part of that FIXED base code, not the tolerance letter) followed by the
completion suffix `00` (2-pin) + **`J` (5% tolerance)** + `S` (bulk) + `SD`
(6-2mm pin length). Reading the earlier `G` as the tolerance character would
have been a plausible-looking mistake (the task brief that motivated this
change explicitly flagged both `G` and `J` as candidates) but is wrong: `G`
never appears in either datasheet's tolerance-letter table at all.

This independently reproduces `docs/hardware/BOM.md` §1.4's own prior decode
of the same MPN's completion suffix ("`00` 2-pin, `J` ±5 %, `S` bulk, `SD`
6-2 pin length"), written when that document corrected this MPN's
voltage/value fields on 2026-07-28 — two independent passes over the same
part number agree.

**`c_tank_tolerance = 0.05`.**

## 4. The fix

1. `c_tank_tolerance: dimensionless = 0.05` declared in `elec/src/main.ato`
   alongside `l_tank_tolerance`, sanity-bounded `[0.01, 0.30)`.
2. `scripts/check_pll_range_consistency.py`'s `derive_zvs_floor()` now
   worst-cases `C_worst = c_tank_total * (1 - c_tank_tolerance)` together
   with the already-correct `L_loaded_worst`. All seven pre-existing checks
   (including PR #411's check 7, the coil-inductance mirror) are unchanged
   and unrenumbered; the capacitor worst-casing is folded into check 5
   itself, since it derives the same single floor.
3. `PLL_MIN_FREQ_HZ` raised `42000 -> 43000` (smallest round kHz at or above
   the corrected 42655 Hz floor). `firmware/components/control/pll_control.h`
   and `elec/src/main.ato`'s `f_pll_tracking_min` both updated; the existing
   cross-check (checks 1-2) keeps them tied together.
   `PLL_DEFAULT_FREQ_HZ = 47000` still sits inside `[43000, 50000]` with the
   1800 W point unaffected — see the falsifier result above.
4. **Check 8 added**: the gate now computes the coil incoming-acceptance
   threshold by inverting its own floor formula —
   `L_loaded_min = 1 / ((2*pi*(PLL_MIN_FREQ_HZ/ZVS_MARGIN_MIN))**2 * C_worst)`
   — and fails the build if the number written in
   `docs/hardware/TANK_COIL_SPECIFICATION.md` (its own
   `` `L_loaded ≥ <value> µH` is requirement #3`` sentence, parsed by that
   exact anchor) disagrees by more than a 0.01 µH rounding allowance. At the
   corrected values: `43000/1.05 = 40952.4 Hz`, `L_loaded_min = 1/((2π ×
   40952.4)² × 285nF) = 52.995 µH`, stated in the spec as **53.00 µH**
   (previously 52.77 µH, derived only from the L-worst-case / nominal-C
   floor). `docs/hardware/BOM.md` §1.4's cross-reference to the same
   threshold updated to match.
5. Tests added to `scripts/tests/test_check_pll_range_consistency.py`
   (`TestCapacitorToleranceWorstCase`, `TestCoilAcceptanceThresholdMirror`):
   most notably `test_regression_to_nominal_c_is_caught_by_the_floor_check`,
   which asserts that `PLL_MIN_FREQ_HZ=42000` — sufficient under the OLD,
   L-only derivation — is now correctly a VIOLATION once
   `c_tank_tolerance=0.05` is honored. This is the regression the task
   required the test suite to catch: any future edit that silently stopped
   worst-casing the capacitor (reverting to nominal `c_tank_total` in the
   derivation) would make this exact test start failing.

## 5. Verification run

```
$ uv run --no-sync python scripts/check_pll_range_consistency.py
...
  [derived] L_loaded(worst case, -10%) = 53.86uH, C(worst case, -5%) = 285.0nF -> f_res,loaded = 40624Hz (nominal 37563Hz) -> required PLL floor = 1.05 x 40624 = 42655Hz
  [derived] coil acceptance threshold L_loaded_min = 53.00uH (inverted from PLL_MIN_FREQ_HZ and worst-case C; must match docs/hardware/TANK_COIL_SPECIFICATION.md)
  [OK] declared tracking min matches firmware PLL_MIN_FREQ_HZ: ...
  [OK] PLL_MIN_FREQ_HZ above the derived ZVS floor: pll_control.h PLL_MIN_FREQ_HZ=43000Hz vs required 42655Hz ...
  [OK] TANK_COIL_SPECIFICATION.md's L_loaded acceptance threshold matches the gate-derived value: ...

PASSED -- 8/8 check(s) agree.
```

`uv run --no-sync python -m pytest scripts/tests/test_check_pll_range_consistency.py`:
**74 passed** (was 59 before this change; 15 new tests added, 2 pre-existing
denominator assertions updated from four/seven to five/eight).

`firmware/test/build/test_pll_only` (CMake, native build, not ESP-IDF):
**24 Tests 0 Failures 0 Ignored** — the compile-time `_Static_assert`-style
ZVS floor guard in `pll_control.c` (a separate, WEAKER, nominal-resonance
compile-time check, `PLL_MIN_FREQ_HZ*100 >= DEFAULT_RESONANT_FREQ_HZ_INT*105`)
still compiles and passes at `PLL_MIN_FREQ_HZ=43000`, unaffected by this
change (it was never the tight bound; `scripts/check_pll_range_consistency.py`
is the authority per its own comment).

## 6. Heads-up for HELD PR #410

PR #410 (re-source `c_tank1`/`c_tank2` to 3× CDE `942C16P1K-F`, ±10%
tolerance — because the current WIMA part is ~2× over its permissible AC
current) will, when merged, change `c_tank_tolerance` from `0.05` to `0.10`.
At that point:

```
C_worst(10%) = 270nF -> f_res 41737 Hz -> floor 43824 Hz  (PLL_MIN 43000 FAILS)
```

`scripts/check_pll_range_consistency.py`'s check 5 (and, downstream, check 8)
**will fail** until `PLL_MIN_FREQ_HZ` is raised again, to roughly **44000 Hz**
(smallest round kHz at or above 43824 Hz — re-derive at merge time rather
than trusting this number, since `l_tank_assumed`/`l_pan_loaded_ratio` could
also have moved by then). **This is correct, intended behavior, not a bug in
this PR** — do not pre-emptively raise the floor for ±10% now, and do not
change the gate to tolerate the wider tolerance silently when #410 lands.

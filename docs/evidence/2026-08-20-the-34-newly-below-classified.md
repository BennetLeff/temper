# The 34 newly-below-12.6 mm pairs, classified against the figures that apply

**Date:** 2026-08-20
**Board:** `pcb/temper.kicad_pcb`, sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`,
**verified identical before and after every measurement; never opened for
write.**
**Harness:** `docs/evidence/2026-08-20-the-34-newly-below-classified.py`
(add-only; no threshold, ceiling, ratchet, allowlist, oracle or test touched).

## 0. Headline

Of the 34 pad pairs the R(-theta) pad-world correction pushed below the legacy
12.6 mm scalar:

| | count |
|---|---|
| **genuine violations against their own applicable figure** | **2** |
| compliant against their own applicable figure | 24 |
| NOT DETERMINABLE (47 kHz, no requirement exists) -- all clear the proven floor | 8 |
| cross the HV<->SELV barrier | **34 of 34** (that is what the instrument enumerates) |
| of those, *mains*<->SELV specifically | 10 |
| **intra-package** (rotation-invariant, no placement helps) | **0** |
| still below their figure under the model-E placement | **0 of 34** |

**The flat 12.6 mm was over-reporting.** 24 of 34 are outright compliant and 8
more clear their proven floor. Only two are real, and both are inter-component
and both are resolved by the compliant model-E placement.

**Correction to the brief this task was issued under: `U1` is not the MCU.**
`U1` is `power_in.d1`, a `TO-220-2_Vertical` mains-input doubler diode
(`(property "Sheetpath" "power_in.d1")`, board line 6519). `C6` is
`power_in.y_cap_pe`, the Y-capacitor that is itself a *declared isolator*
straddling the barrier. The MCU (`U27`, ESP32-S3) appears nowhere in the 34.

## 1. Which figure applies

12.6 mm is Table 17 row **iv** (>250-400 V) -- a 230 V figure on a 120 V
design. The applicable figures come from `elec/insulation_manifest.yaml` via
`packages/temper-design-bundle/src/insulation.rs` (branch
`feat/per-pairing-creepage-derivation`). They were **not copied from prose**:
`barrier_setbacks()` was executed in-process off that branch, against a wheel
built from its own `temper-design-bundle` source, and printed:

```
DC_BUS        8.00 mm  (DC_BUS<->SELV)
MAINS         4.80 mm  (MAINS<->SELV)
SWITCHING     8.00 mm  (SELV<->SWITCHING)  [PROVEN FLOOR ONLY]
TANK         20.00 mm  (SELV<->TANK)  [PROVEN FLOOR ONLY]
all_determinable = False
```

`SELV<->SWITCHING` and `SELV<->TANK` run at 47 kHz, above IEC 60664-1
cl. 1.1.1's 30 kHz scope ceiling; cl. 2.3 routes dimensioning to IEC 60664-4,
which is paywalled and was not obtained. **Clearing a floor is not
compliance**, and the 8 indeterminate pairs below are reported as non-passes
however wide their gap.

## 2. Re-derivation, not inheritance

The 34 were re-derived from the board's own bytes with the pad-world
composition re-implemented from the convention statement (not imported from
the corrected script), computing both conventions side by side:

```
HV pads 109 x SELV pads 237 = 25833 pairs
figures that MOVED under the correction : 19640
below 12.6 mm, superseded R(+theta)     :   155
below 12.6 mm, canonical  R(-theta)     :   122
NEWLY below (the unsafe direction)      :    34
```

Every published count reproduces exactly. The three worst movers reproduce to
four decimals: `U1.2<->C6.2` 4.7652, `U1.1<->C6.2` 7.1253, `C7.2<->R56.1`
7.4543.

**The lead figure was additionally checked by hand from the board bytes**, so
it does not rest on the harness either. `C6` is at `(at 66.99 201.51 270)`
with pad 2 at local `(at 10 0 270)`, net `gnd`; `U1` is at `(at 60 218 0)`
with pad 2 at local `(at 5.08 0 180)`, net `power_in.ntc-no`. Under
R(-270 deg) the C6 pad-2 centre is `(66.99, 211.51)`; U1 pad 2 is
`(65.08, 218)`. Centre distance `hypot(1.91, 6.49) = 6.76522`; both pads are
2 mm circles, so edge-to-edge is `6.76522 - 1 - 1 = 4.76522`. Under R(+270)
the same arithmetic gives 24.5588 -- the superseded figure.

## 3. The two genuine violations

| pair | nets | pairing | figure | measured | short by |
|---|---|---|---|---|---|
| `U1.2 <-> C6.2` | `power_in.ntc-no` <-> `gnd` | MAINS<->SELV, **reinforced** | 4.8 mm | **4.7652 mm** | 0.0348 mm |
| `U1.1 <-> C6.2` | `+170V_BUS` <-> `gnd` | DC_BUS<->SELV, **reinforced** | 8.0 mm | **7.1253 mm** | 0.8747 mm |

Both are the mains-input doubler diode `U1` against the SELV-side terminal of
the Y-cap `C6`. `gnd ~ pe` (`elec/src/main.ato:753`), so both are physically
HV-to-earth reinforced crossings.

The first is **0.0348 mm short** -- knife-edge, well inside fabrication
tolerance, and it should be read as "not demonstrably compliant" rather than
as a large shortfall. The second is unambiguous.

Neither is intra-package. `C6`'s own terminal-to-terminal span is 8.0 mm
against a 4.8 mm MAINS<->SELV requirement, i.e. the declared isolator itself
is compliant; the failure is that `U1` is placed too near it.

## 4. The 8 indeterminate pairs

`U5.1/U5.2` (`GATE_LS`/`SW_NODE`) and `U6.10/U6.11` (`input`/`+15V_LS`) against
SELV pads of `U6`, `U25`, `J2`, ranging 9.7380 to 12.4445 mm. All clear the
8.0 mm proven floor; none can be certified, because no requirement for them
exists. They are **not** passes.

## 5. Zero of the 34 are intra-package -- and that is structural

An intra-package pad-to-pad distance is a rigid-body invariant, so it cannot
change under a change of rotation convention. Every one of the 34 is, by
definition, a pair whose figure moved. **No pair that moved can be
intra-package.** All 34 are therefore inter-component and are the placer's
problem, not a T1-style structural blocker.

For contrast, of the 122 pairs below 12.6 mm under the canonical convention,
37 *are* intra-package -- including `T1.1<->T1.4` at 9.1000 mm against the
20.0 mm SELV<->TANK floor. None of those 37 is among the 34.

## 6. Measured against the model-E placement, not assumed

Row E of `analysis/per-pairing-placer-solve` (`30edd0a93`) was **re-solved**,
not inherited: `optimal`, 168/168 placed, 38.0 s, seed 42, same encoded
setbacks. Applied to a scratch board with the production write contract
(168 updated / 0 skipped, round-trip PASS over 168 components / 521 pads,
containment PASS). The template board's sha256 was verified unchanged across
the write.

**All 34 clear their applicable figure under model E**, by wide margins
(35.8 mm to 194.5 mm). `U1.2<->C6.2` goes 4.7652 -> 59.1069;
`U1.1<->C6.2` goes 7.1253 -> 54.8819.

Grading *every* HV<->SELV pad pair against its own per-pairing figure under
the canonical convention (which had not been done -- the published census used
the superseded composition):

```
COMMITTED board : 35 pairs below their own figure
    MAINS      3   min  4.0500 / 4.8
    DC_BUS     1   min  7.1253 / 8.0
    SWITCHING  4   min  3.5781 / 8.0   [FLOOR ONLY]
    TANK      27   min  8.8500 / 20.0  [FLOOR ONLY]  (2 intra-package)

MODEL-E place   :  5 pairs below their own figure
    DC_BUS     1   T2.2<->T1.4  4.7643 / 8.0
    TANK       4   min  1.9778 / 20.0  [FLOOR ONLY]  (2 intra-package)
```

35 -> 5 independently reproduces the count
`docs/evidence/2026-08-20-ovp-pads-under-model-e-placement.md` (`cbdf42bee`)
arrived at by a different route ("Census 2 becomes 35 -> 5 rather than
36 -> 8"). The published 36 -> 8 was computed on the superseded composition.

**Two committed-board violations sit outside the 34** and are noted because
they are worse than either of the two above: `K1.14<->J1.1` at 4.0500 mm and
`K1.14<->J1.2` at 4.1831 mm, both MAINS<->SELV against 4.8 mm. They were
already below 12.6 mm before the correction, so they are not "newly" below --
but they are the mains barrier's worst determinate shortfalls on this board.

## 7. Undeclared nets -- bounded, and the bound is good news

None of the 34 involves an undeclared net.

Sweeping the whole board rather than only the 34: **77 of the 139 nets that
carry copper pads (177 pads) are classified by NEITHER domain in
`elec/domain_manifest.yaml`**, and the measurement instrument skips them
silently (`if domain is None: continue`), so they contribute nothing to the
25,833-pair denominator. That is the structurally interesting number.

Cross-referencing every one of those 77 against this repo's own
`TEMPER_NET_ASSIGNMENTS` netclass table bounds the hazard:

```
HighVoltage                4 nets /   8 pads   <-- graded by nothing
<no explicit assignment>  65 nets / 137 pads
FinePitch                  7 nets /  19 pads
Power                      1 nets /  13 pads
```

The four `HighVoltage` ones are exactly the OVP divider mid-chain taps already
identified in `cbdf42bee`: `safety.ovp.r_div_top1-p2` (R46.2, R47.1),
`safety.ovp.r_div_top2-p2` (R47.2, R48.1), `safety.ovp.r_adc_top1-p2`
(R51.2, R52.1), `safety.ovp.r_adc_top2-p2` (R52.2, R53.1). **There are no
others.** Nothing further is in that state -- the count is 4, not "4 so far".

Their nearest declared-SELV copper on the committed board, canonical
convention: 1.6423 mm (`R53.1` -> `R67.2`/`gnd`), 1.8000 mm, 2.2320 mm,
2.6004 mm, 2.8112 mm, 4.1277 mm, 14.9651 mm, 21.9553 mm. No per-pairing
figure grades any of them. The 1.6423 mm and the 1.8000 mm intra-package pair
both persist in some form under model E (1.8000 mm), consistent with
`cbdf42bee`'s 1.64 -> 1.80 range.

The root cause is at the **domain** level, not the insulation level: the
insulation manifest's groups cover exactly the domain manifest's 62 nets
(proved: zero nets in one and not the other), so a net the domain manifest
never declares can never acquire an insulation group.

## 8. Proved vs inferred

**Proved by measurement in this session:** every distance in every table
above; the 25833 / 19640 / 155 / 122 / 34 counts; the four per-pairing figures
(executed, not quoted); the model-E re-solve and its write contract; the 35
-> 5 census; the 77-undeclared-net sweep and its 4-net `HighVoltage` subset;
the board sha256 before and after every step.

**Inferred, and load-bearing:**
* The per-pairing *requirements* themselves rest on
  `elec/insulation_manifest.yaml`'s declared working voltages and on the
  Table 17/18 rows recovered in `0cbc04248`. This session verified the
  derivation *executes* to 4.8/8.0/8.0/20.0; it did not re-audit the standards
  determination behind them.
* Whether `U1.2<->C6.2` at 0.0348 mm short is a defect or a tolerance artifact
  is a judgement, not a measurement.
* Model E is a *candidate* placement solved against these figures. It clears
  all 34, but it is not the committed board and it introduces its own
  residuals (section 6), including three HV<->HV functional-clearance
  regressions already reported in `cbdf42bee`.

**Not verified here:** the branch carrying the pad-world correction
(`worktree-agent-a88f1f2907eb88fcc`, `41c8d5272`/`c67e41b5e`) has an
unverified test status -- its `router_v6` run finished 20 failed / 6242 passed
and those 20 are not yet proven pre-existing. That does not affect any
measurement above, because the convention proof and every figure here are
independent of it, but the branch must not be treated as landable on that
basis.

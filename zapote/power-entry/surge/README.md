# Loaded differential surge screen on V150LA10AP

**Status: conditional screen, not a surge-protection pass.** Current design
choices and the finite qualification work are in [CLOSEOUT.md](../CLOSEOUT.md).
Keep the MOV as the candidate L–N clamp; qualify it with the real source and
assembly before crediting protection.

## Retained calculation

The script solves a 1 kV open-circuit voltage source behind a fixed 2 Ω resistor
against the extracted V–I curve. It reports:

| Quantity | Typical curve | Curve scaled to match maximum at 50 A |
| --- | ---: | ---: |
| Peak operating point | 278.7 A / 442.6 V | 273.0 A / 454.0 V |
| Fraction of 500 A prospective short-circuit current | 56% | 55% |
| Calculated MOV energy in this source model | 3.55 J | 3.49 J |

500 A is the generator's prospective short-circuit current, not the MOV current.
395 V is a **maximum at 50 A, 8/20 µs only**. It is neither an upper nor a lower
bound at other currents. Multiplying the extracted curve by 395/383.1 is an
**assumed shape sensitivity**, not a maximum curve or a worst-case bracket.

The 454 V scenario is numerically above TEA2209T's 440 V operating rating and
below its 700 V mains-transient rating and the proposed MOSFET's 600 V rating.
The ratios are 1.032, 0.649 and 600/454 = 1.32 respectively. They are scalar
comparisons, not qualified margins. Each pin's reference, transient conditions
and actual overshoot must be evaluated; the controller and MOSFET limits cannot
be substituted for one another. See the [NXP TEA2209T datasheet](https://www.nxp.com/docs/en/data-sheet/TEA2209T.pdf).

## Model boundary that prevents acceptance

A fixed resistance makes the source's short-circuit current proportional to its
open-circuit voltage. Fitting that voltage to 1.2/50 µs therefore does **not**
produce the required 8/20 µs short-circuit current. Dropping that cross-check did
not make the source a validated combination-wave model. The retained calculation
is useful as a load-line sensitivity, but cannot close the adopted surge test.

Consequently, neither approximately 3.5 J nor the ratio to the MOV's 4500 A
8/20 rating demonstrates energy/current survival. The event waveform, mains
superposition/phase, component variation and installed wiring must be included.
The former statements "passes", "worst case" and "energy margin done" are
withdrawn as qualification claims. No numerical model was changed in this
closeout; the script output now states these limits too.

## Extraction and reproduction

The retained LA-series PDF's Figure 10 uses vector paths. The extraction script
chains those paths and calibrates log-log axes. Its three 50 A cross-checks are:

| Curve | Extracted voltage | Tabulated maximum |
| --- | ---: | ---: |
| V130LA10A(P) | 333.7 V | 340 V |
| V140LA10A(P) | 346.8 V | 360 V |
| V150LA10A(P) | 383.1 V | 395 V |

These comparisons support the extraction; falling below a maximum does not by
itself prove the identity, typical status or entire shape of a curve.

```sh
python3 zapote/power-entry/surge/extract_la_vi_curve.py
python3 zapote/power-entry/surge/loaded_surge.py
```

The extractor requires PyMuPDF; the load-line script uses the standard library.
Inputs are `data/v150la10a_vi_curve.json` and the captured LA-series PDF under
`../loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-MOV/attempt-001/raw/`.
The fitted voltage markers are checked before reporting energy. That numerical
check verifies the selected voltage waveform, not its physical applicability as
an IEC combination-wave source.

## Common mode: use this board's circuit

The adopted target is 2 kV at 12 Ω, approximately 167 A prospective. The L–N MOV
provides no common-mode clamp. The chosen development path is insulation and
return-path withstand, with physical qualification still open.

On the saved shunt-repair board, **U41 is VY1102M31Y5UQ63V0, authored as 1 nF Y1,
from PFC_BUS_MINUS to PE_CHASSIS**. Its exact pad nets and board hash are recorded
in [the closeout](../CLOSEOUT.md#2-exact-baseline-and-circuit-boundaries). The
previous paragraph about 2.2 nF Y2 capacitors and a 5.6 nF doubler-midpoint
capacitor was transferred from another design and is withdrawn here.

The current [Vishay VY1 family datasheet](https://www.vishay.com/docs/28537/vy1series.pdf)
identifies Y1/500 VAC classification and component AC proof tests. This is useful
family evidence; exact retained order-code approvals and impulse applicability
must be established for U41. It is not evidence of a completed assembly test.

The connected HOT bias supply, permit/control wiring, PE, enclosure and all
isolation barriers determine the actual common-mode path. A 3000 VAC hipot
requirement is not a test receipt and cannot be compared numerically with 2 kV
surge to establish withstand. Q4 in the closeout specifies the required assembly
assessment and test. No extra PE clamp is selected merely from its absence.

## Disposition

The extraction and numerical screen are retained. The MOV choice is provisional;
differential and common-mode qualification remain open. The
[adopted contract](../../../docs/specs/SURGE_CONTRACT.md) defines the target,
not a compliance certification. There has been no powered test. The internal
capacitor-discharge fault is separate and receives no protection credit from
this L–N clamp.

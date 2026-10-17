# 03 Loss and thermal budget — round 3 result

- Board: `native-15/section.kicad_pcb`, SHA-256
  `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`.
- Source revision: PR #1615 source `44417ae1489fd00e2d652fd3b2c1582b76d17630`;
  2026-09-27; Codex GPT-6. KiCad 10.0.4, Miniforge Python 3,
  ngspice 45.2 for imported A1/A5 work.
- Evidence class: **exact structural** for part/position extraction;
  **model-based and conditional calculation** for losses and thermal screens.
- Verdict: **PARTIAL / BLOCKED for D2 and B3**. An unconstrained grid case
  exceeds the shunt's 1 W rating if sustained. Pad and fan selection require
  physical contact and complete loss inputs.

## Summary

The [loss table](outputs/losses.csv) and [machine-readable heat map](outputs/board_heat_sources.json)
retain each component, location, formula, heat partition and unknown item.
The illustrative 120 V, 1,710 W cast-iron/high tank case has 21.47 A RMS,
41.28 A peak, 32.77 kHz and **0.461 W in R5**. The modeled MOS conduction
is **6.78 W/device** at a *typical* interpolated 125 °C RDS(on); A1's covered
27 °C-model turn-off events add **0.26 W/high-side and 0.33 W/low-side**.
An assumed 15 A RMS
sinusoidal mains current and the GBJ single-point VF give **28.36 W BR1**.
Those five sink parts total **56.63 W, with known omissions**.

The 108 V low-R/full-power grid extreme has 44.70 A tank RMS and 89.79 A
peak. R5 dissipates **2.00 W at nominal resistance**, or **2.04 W** with
the +1% resistance and assumed +50 °C TCR corner, versus [Vishay's 1 W
P70 °C rating](sources/wsk2512.pdf). [Twelve of 45 modeled full-power
cases](outputs/grid_rating_screen.json) exceed 1 W at 1 mΩ if maintained.
All 12 have tank peaks above 67 A, exceeding even [A3's highest static CT
threshold](inputs/a3-thresholds.json) of 60.01 A, and **must not be used as
continuous cooling design points**. The actual trip timing, thermal pulse
duty and protection integrity still need physical confirmation.

## Method and inputs

The exact board has 135 footprints. [read_board.py](scripts/read_board.py)
re-extracted their references, values, footprint anchors and pad nets under KiCad
Python. Its [output](inputs/board-parts.json) is byte-identical to the
previous independent extraction (`6e4c324c…`). `losses.py` checks the live
board hash and exact hot-part identities before computing. KiCad's footprint
anchor is often at pin 1 and is **not** the body centre; the heat JSON's
`x_mm/y_mm` are the midpoint of each reference's pad-centre bounding box,
with the original anchor retained separately. This is a placement proxy,
not a verified thermal centroid. The [provenance
record](outputs/provenance.json) hashes every copied CSV and PDF.

| Input | Published condition and use |
| --- | --- |
| [Infineon IPW65R018CFD7](sources/ipw65r018cfd7.pdf), Rev 2.0 p. 3, 5, 6, 12 | RθJC max 0.28 °C/W; RDS(on) 15/18 mΩ typ/max at 25 °C, 33 mΩ **typ** at 150 °C, VGS=10 V; 234 nC Qg only for 0–10 V; TO-247 dimensions. No hot max is specified. |
| [Diodes GBJ2510](sources/gbj2510.pdf), DS21221 Rev 11 p. 2, 4 | VF max 1.05 V at IF=12.5 A/Tj=25 °C only; RθJC **typical 1 °C/W per element**; package outline. A constant 1.05 V over the actual current and hot junction is a screen. |
| [Vishay WSK2512](sources/wsk2512.pdf), Rev 2023-12-11 p. 1–2 | 1 W at 70 °C; 1 mΩ code; ±250 ppm/°C TCR for 1–2.9 mΩ; 1% tolerance. Real board temperature and pulse-duty rating still needed. |
| [CDE 942C](sources/942C.pdf), printed p. 3 | C21/C22 typical 6 mΩ and C23 5 mΩ ESR at listed 100 kHz condition. At the actual 30.7–57.6 kHz and hot case, loss and current rating are unresolved by A5. |
| [TDK B82726S22x3 source record](inputs/tdk-source.json), May 2026 p. 4 | L1 two 4.5 mΩ typical windings. Source PDF's redistribution notice prevents embedding it; URL and SHA-256 retained. |
| [onsemi MC78L00A](sources/mc78l00a.pdf), SOT-89 thermal and MC78L05 table | 55 °C/W junction-to-ambient under datasheet PCB conditions; input bias 3.8 mA typ/6 mA max at 25 °C. HOT5 load is unknown. |
| [Mean Well IRM-20](sources/irm20.pdf), 2025-11-21 p. 2 and [IRM-05](sources/irm05.pdf), 2025-08-08 p. 2 | 84% and 75% typical at **rated load, 230 Vac, 25 °C**. Their actual 120 V partial-load efficiencies and outputs are unknown. |
| [Henkel thermal guide](sources/henkel-tim-guide.pdf), printed p. 63, 75 | SIL PAD 400 0.229 mm: 1.45 °C·in²/W at 50 psi; SIL PAD K-10 0.152 mm: 0.41. Typical fixture values include interface resistance. |
| [Aavid 63730](sources/aavid-63730.pdf), Nov. 2016 p. 1–2 | 76.2 × 57.15 mm extrusion profile, 1.88 °C/W natural and graph over about 1–5 m/s for **one 10 W heat source**. This is a comparison, not an installed fan rating. |
| [A1 turn-off table](inputs/turnoff_energy.csv) and [A5 grid](inputs/cases.csv), [shunt](inputs/shunt-grid.csv), [events](inputs/switching-events.csv) | Frozen sibling-agent data snapshots; A1 deadtime 348 ns, L=1, 0.2 ns, both directions of vendor dissipative heat at 27 °C; A5 ideal full bridge/no dead time over one 60 Hz rectified half-cycle. Full 135-case grid. |

The input files are locally pinned under this task. No value is transferred
from historical `LOSS-REFACTOR.md` as a device model: its 22.5 W rectifier
and 25.4 W switches are a different waveform/thermal assumption. Here the
bridge's 28.36 W single-point screen is 26% above 22.5 W, mainly the 15 A
sinusoidal assumption and 1.05 V point value. The nominal four-MOS
conduction-plus-covered-turn-off screen is 28.27 W, 11% above 25.4 W,
because this actual tank example has 21.47 rather than 18.7 A RMS and
turn-off is included. Neither comparison validates the old or new total.

## Per-part power and heat partition

The [CSV](outputs/losses.csv) states formulas and references for every
line. These are selected figures in watts; `?` means the true total includes
an unquantified term. `sink`/`board` are assumed destinations, not measured
thermal paths. The JSON lists derived pad-bounds `(x,y)` in mm for 42 parts;
unknown-only heat is `null`, never a claim of zero. Additional bus,
snubber, EMI and bleed parts are included as explicit unresolved rows.

| Part(s) | 120 V example | High-current stress | Main limitation |
| --- | ---: | ---: | --- |
| Q2/Q5 high side, **each**, sink | 7.03? | 29.43? | Typical 125 °C conduction + A1 direction-1 covered events only; dead time, ZVS and out-of-grid currents missing. |
| Q3/Q6 low side, **each**, sink | 7.10? | 29.44? | Same with A1 direction-0 events. |
| BR1, sink | 28.36? | 28.36? | 15 A input sine + single-point 25 °C VF; no actual bridge-current waveform. |
| R5, board | 0.461 | 2.043 | Actual shunt RMS from A5; stress includes tolerance and assumed +50 °C TCR. |
| C21/C22, **each**, board | 0.459 | 1.989 | 100 kHz typical ESR used outside condition. |
| C23, board | 0.079 | 0.343 | Same ESR limitation. |
| L1, board | 2.025? | 2.025? | 15 A input, typical DC DCR; AC and temperature missing. |
| R22–R25, **each**, board | 0.00494 | 0.02263 | A5 ideal tank waveform average. |
| R39, board | 0.069? | 0.300? | Ideal 100:1 CT; T1 winding/core unknown. |
| U3, board | ≥0.057? | ≥0.057? | Typical 3.8 mA input bias alone; add `10 V × Ihot5`. |
| PS1/PS2, board | ? | ? | Actual output load and 120 V partial-load efficiency missing. |
| R10/R12/R18/R20, U1/U2, T1 | ? | ? | Gate charge at 15 V, dissipation split, CT core/winding loss missing. |

The MOS assumption `Idevice,rms = Itank,rms/√2` applies only to the
idealized 50% conduction bridge. `RDS(on)(125 °C)=29.4 mΩ` is a linear
interpolation of two **typical** temperature points; the datasheet gives
no guaranteed hot maximum. A1's *vendor dissipative channel + epi + diode*
energy is used, because external-pin `VDS×ID` also charges output and
snubber capacitances. Direction 0 maps to low-side turn-off and direction 1
to high-side; the two energies differ, so they are never merged as an
identical device. It is a 27 °C, board-L placeholder model: 11 of 546
nominal and 387 of 532 stress switching events are outside its 1–37 A
current range. Below 120 V, the 120 V curve is only a proxy. No complete
device power bound or temperature iteration is claimed. Co(er)=396 pF and
Co(tr)=4144 pF are both effective **0–400 V** values; neither is used as
constant C at 170/198 V. A future lost-ZVS calculation needs Eoss(V) or
`∫V·Coss(V)dV` plus Qrr at the actual commutation conditions.

For R5, A5 saved `i_R5=s(t)·i_tank`, so `s²=1` makes its ideal RMS equal
to tank RMS. The saved shunt waveform confirms that result separately.
During real dead time the low-side body-diode return also passes R5;
without those switching intervals the correction cannot be quantified.

At 32.77 kHz, Infineon's 234 nC over a **0–10 V, 400 V test** corresponds
to `Qg×10V×f = 0.0767 W` from a hypothetical 10 V gate source **per
device**. The board drives about 15 V; neither its full gate charge nor
the split across R10/R12/R18/R20, U1/U2 and internal gate resistance is
established. That reference value is kept in `losses.json` but is not
assigned as device or board heat. At rated output and 230 Vac, the typical
IRM-20/IRM-05 efficiencies imply 4.0/1.65 W internal heat; these do not
describe their actual unknown 120 V, partial-load operating points.

For U3, the **6 mA maximum input bias is specified at the 25 °C table
condition**, so `15 V×6 mA = 0.09 W` is a test-point reference, not a
guaranteed hot upper bound. With the quoted 55 °C/W SOT-89 datasheet PCB
condition and a 125 °C design junction, conditional algebra using 0.09 W
would leave `(125−Tamb)/55 − 0.09` for output-load heat, equivalent to
**127 mA at 50 °C** and **100 mA at 65 °C** after dividing by the 10 V
drop. The first figure exceeds the regulator's **100 mA electrical rating**;
neither is an approved current limit at those ambients. The native-15 HOT5
load, hot bias and actual copper heat path must be measured before a
regulator verdict.

## Heatsink sensitivity and status

[heatsink_requirement.md](heatsink_requirement.md) details both exact
Henkel options, TO-247 tab-to-PE capacitance (roughly 32–52 pF using 1 kHz
εᵣ), the per-element bridge thermal equation, 50/65 °C air, and the Aavid
airflow comparison. For the nominal example, SIL PAD 400 requires
≤0.399/0.134 °C/W at 50/65 °C; K-10 requires ≤0.973/0.708 °C/W.
These are **optimistic conditional screens**. Natural convection on the
illustrative Aavid profile (1.88 °C/W) misses both. Its forced-air curve
is for a 10 W centered source; no numerical 1/2/3 m/s requirement is
transferred to the actual 57 W, sink length and enclosure.

The 108 V low-R stress case puts the 0.229 mm SIL PAD 400 beyond 125 °C
even with an ideal sink under the model. K-10 at 65 °C has only
~0.002 °C/W remaining for the sink before missing losses, so it is also
not a plausible continuous corner. Since protection intervenes, this does
not set the steady fan requirement.

**Remaining dependencies, cheapest resolution:** A1 needs a thermal/board
switching sweep through the actual event-current range and a lost-ZVS map;
A5 needs an exact-part CDE hot-frequency rating; the hardware owner needs
HOT5, PS1/PS2 loads and actual mains bridge-current waveforms; D2 needs a
selected interface/sink and contact pressure. B3 can ingest the JSON's
*known board heat* for a sensitivity run but must preserve its
`has_unquantified_loss` flags; it cannot call the result a qualified board
temperature. The physical confirmation is the enclosed full-power
thermocouple/current test described in the heatsink note.

**Master-plan status line:** 03 — partial, D2/B3 blocked: conditional losses
and pad/sink screens delivered; R5 1 W stress failure found; switching,
bridge, auxiliary loads and installed cooling remain unqualified.

## Reproduce

From the repository root in the assigned checkout:

```sh
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 zapote/power-stage-120v/validation-results/03-loss-thermal-budget/round3/scripts/read_board.py
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-results/03-loss-thermal-budget/round3/scripts/losses.py
```

The KiCad Python tool prints a harmless wxApp assertion on this host before
the successful 135-footprint save. The script validates the exact board
SHA-256. All source URLs, revisions and full hashes are in
[`sources/intake.md`](sources/intake.md) and
[`outputs/provenance.json`](outputs/provenance.json).

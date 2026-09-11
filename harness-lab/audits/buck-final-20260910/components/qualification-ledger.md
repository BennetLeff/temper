# Buck component qualification ledger — 2026-09-10

This ledger is an engineering review aid in the component audit. It is not an
approved registry entry, a simulation result, or a manufacturer guarantee.
The actual circuit gate in `harness-lab/src/circuit_validation.rs` requires
positive reviewed `effective_min_uf >= required_min_uf` for each capacitor and
`inductor_saturation_a >= required_peak_a`; the current requirements file
leaves both required values unresolved. The ledger therefore supplies bounded
calculation inputs without manufacturing a pass.

## Operating envelope and derived screens

The follow-up [margin review](../margin-resolution/README.md) supersedes the
nominal-frequency screens below for tolerance-corner decisions. With 450 kHz,
4.48 uH and VOUT up to 3.465 V, the ideal 1 A operating peak reaches 1.679 A.
The earlier 10 mV ESR allocation is a sensitivity assumption, not a bounding
switching-edge calculation. Source impedance cannot be added as inductor
peak current times resistance; the input network determines that transfer.
Neither review supplies a guaranteed capacitance floor or changes the hot
fault-current criterion.

The adopted electrical envelope is VIN 13.5–16.5 V, VOUT 3.3 V, 500 kHz,
0.05–0.5 A continuous load-step endpoint, and a 0.05–1.0 A pulse endpoint.
The thermal target is ambient up to 70 °C in the derated region, U3 junction
≤125 °C, and L2 hotspot ≤105 °C. These are design targets and bench/simulation
conditions, not component ratings.

For a first-order input-capacitor screen, `D=3.3/VIN` and
`Creq=Iout*D*(1-D)/(fsw*DeltaVIN)`. At 1 A and 500 kHz:

| VIN | D | Creq at 50 mV | Creq at 100 mV |
|---:|---:|---:|---:|
| 13.5 V | 0.2444 | 7.39 uF | 3.69 uF |
| 15.0 V | 0.2200 | 6.86 uF | 3.43 uF |
| 16.5 V | 0.2000 | 6.40 uF | 3.20 uF |

No board requirement currently declares `DeltaVIN`; 50 and 100 mV are
sensitivity points only. With a 10 mOhm ESR assumption and 10 mV reserved for
the ESR step, the 13.5 V/1 A/50 mV screen becomes about 9.24 uF. This is a
conservative calculation assumption, not a TI limit.

At 0.5 A, the listed capacitances halve. The 1 A pulse is the dominant charge
screen, but its duration and source impedance must be included in the final
waveform model.

For L2, the ideal inductor ripple is
`dI=VOUT*(1-D)/(L*fsw)`. With L=5.6 uH:

| VIN | dI p-p | Peak at 0.5 A | Peak at 1.0 A |
|---:|---:|---:|---:|
| 13.5 V | 0.889 A | 0.944 A | 1.444 A |
| 15.0 V | 0.917 A | 0.958 A | 1.458 A |
| 16.5 V | 0.943 A | 0.971 A | 1.471 A |

These operating peaks are far below Bourns' 23 A, 25 °C, 20%-drop Isat
specification. The separate 6.68 A value is the converter high-side peak
current ceiling used by the fault analysis; it is not a normal 1 A output
requirement. The existing 8.35 A condition is 1.25 × 6.68 A, so it is
defensible as a deliberate hot-saturation stress screen, but it is not
derived from the 0.5/1 A operating envelope. It must remain labeled as such
unless the adopted fault procedure removes it; it must not be silently
replaced by the much smaller normal operating peak. This screen is not a
fault-survival or recovery claim.

Using the Bourns 10 mOhm maximum DCR as a deliberately conservative room-
temperature calculation input, the approximate copper loss is 3.2 mW at the
0.5 A endpoint, 10.7 mW at the 1 A endpoint, 0.45 W at 6.68 A, and 0.70 W at
8.35 A (including the small switching ripple in RMS current). These numbers
are sensitivity estimates only: hot DCR, core loss, PCB spreading, airflow
and pulse duration determine the actual hotspot.

## Evidence ledger

| Item | Manufacturer evidence | Engineering use | Status |
|---|---|---|---|
| C9 Samsung `CL32B106KBJZW6E` | Exact product/ADS identity: 10 uF ±10%, 50 V, X7R, 1210, soft termination. Typical graph is approximately 7 uF around 16.5 V, 1 kHz/1 Vrms. | A typical-data sensitivity point. Applying an explicit 10% initial-tolerance factor gives about 6.3 uF before temperature, aging, AC amplitude, and model uncertainty. | Does not establish the required minimum; use the written VIN budget and a bias/temperature/aging model or measurement. |
| C10/C13 KEMET `C0603C104K5RACTU` | Exact selected MPN is 100 nF ±10%, 50 V X7R, 0603. | Correct source metadata; no 100 nF retained floor is assumed. | Electrical effective value remains a circuit qualification input if the gate requires it. |
| C11/C12 Murata `GRM32ER71E226KE15L` | Exact MPN is 22 uF ±10%, 25 V X7R. Retained 25 °C/10 mVrms DC-bias data show about 17.1 uF near 3.3 V; retained 3.465 V temperature data have a minimum of 15.288456 uF and rise to about 19.6 uF near 70 °C. | Two parts provide a typical-data starting point for output transient analysis; no lower combined floor is asserted. | Must account for tolerance, aging, AC bias, ESL/ESR and actual waveform before passing the gate. |
| L2 Bourns `SRP1265A-5R6M` | Exact PDF: 5.6 uH ±20%, 10 mOhm max DCR, 12.5 A Irms at 40 °C rise, 23 A Isat at 20% drop, specified at 25 °C. | Normal envelope peaks 0.94–1.47 A. 8.35 A remains a distinct fault screen, not a normal-load estimate. | No manufacturer combined 105 °C-hotspot L(I,T) floor retained. |

### Explicit screening sensitivity (not guaranteed derating)

The following factors are a review sensitivity range, chosen to expose the
consequence of unknown effects. They are not claimed Samsung, KEMET or Murata
limits: temperature factor 0.90–1.00 where no part-specific temperature trace
exists, aging factor 0.80–1.00, and initial tolerance factor 0.90 for ±10%
parts (0.80 for the historical ±20% model). The Samsung graph is read only as
approximately 7 uF at 16.5 V, not as a 6.94 uF precision measurement. The
Murata temperature minimum below already includes its temperature effect, so
it is not multiplied by another temperature factor:

| Part/screen point | Typical/bias point | Temperature minimum used | Temperature minimum × 0.90 tolerance × 0.80 aging |
|---|---:|---:|---:|
| C9 at 16.5 V bias | ~7.00 uF | 6.30 uF (assumed 0.90 temperature factor) | 4.54 uF |
| C11 or C12 near 3.3 V bias | 17.06 uF | 15.288456 uF (retained JSON minimum) | 11.01 uF |
| C11 + C12, same sensitivity | 34.12 uF | 30.576912 uF (two retained minima) | 22.01 uF |

The C11/C12 temperature JSON is measured-characterization data at 3.465 V,
10 mVrms, not a combined tolerance/aging guarantee; its retained minimum is
15.288456 uF and it rises to about 19.6 uF near 70 °C. The range above
must therefore be treated as a transparent placeholder until the exact
qualification conditions are defined.

## Defensible assumptions and smallest gap

Defensible review assumptions are the stated VIN/load/frequency envelope,
the ideal ripple equations, and explicitly parameterized sensitivity factors
(10% initial tolerance, 10 mV ESR allocation, and separately chosen aging or
temperature factors). They are useful for sizing and sensitivity, but none is
a manufacturer guarantee. TI's LMR51430 guidance recommends X5R/X7R input
ceramics, a rating approximately twice maximum VIN, and a typical 4.7 uF-or-
higher high-frequency input decoupler; it does not declare this board's VIN
ripple limit.

The smallest real external evidence gap is two-part: (1) write the board's
numeric VIN ripple budget and evaluate C9 with a combined-condition model or
measurement at 13.5/15/16.5 V and both load endpoints; and (2) obtain an exact
SRP1265A hot L(I,T) curve or measure L2 in a standalone DC-bias inductance
fixture at the proposed 8.35 A stress screen and 105 °C hotspot. Do not use
the regulated buck output to impose that current. A substitute with stronger 25 °C figures does not close
that exact-part hot condition without package, thermal, and waveform review.

Primary references are the TI LMR51430 datasheet, Samsung exact C9 page, and
the retained Bourns PDF and Murata JSON files listed in `README.md` beside this
ledger.

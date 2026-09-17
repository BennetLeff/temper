# Conventional silicon boost comparison: 65, 90, and 129 kHz

This is a decision screen for the maintained single-phase CCM boost PFC. It
compares the current `IPW65R045C7 + UCC27624DR`, 12 V driver bias, 4.7 ohm
gate resistor, 129.107 kHz, 180 uH baseline with lower-frequency conventional
silicon variants. It does not predict whole-board efficiency, delivered pan
power, temperature, BOM cost, or a production-safe magnetic design.

The source identity is commit `07a066e86251c13b0aec95b3d6f4ce958459db39`.
The maintained experiment-02 result is the numerical authority for the
conditional MOSFET subtotal. The exact arithmetic and provenance are in
`comparison.json`.

## Decision

Use 90 kHz as the next low-frequency comparison point if the goal is to trade
switching loss against a physically buildable choke without committing to the
large magnetic jump at 65 kHz. Hold the matched-ripple condition by moving
from 180 uH to about 258 uH effective. A 65 kHz option is credible only as a
new magnetic design: it needs about 358 uH effective (about 441 uH nominal if
10% tolerance and 10% DC-bias headroom are budgeted), and stores roughly twice
the baseline magnetic energy at the 120 V current peak.

The arithmetic says a 65 kHz matched-ripple case reduces the conditional C7
no-assist switch subtotal from 45.50 W to 26.13 W; 90 kHz gives 33.68 W. Those
are partial model sensitivities. They omit or leave unresolved the boost
diode, bridge, inductor core and AC winding loss, bulk-capacitor ESR, PCB,
auxiliary supply, thermal path, and gate-loop commutation. They cannot select
a winner by total efficiency.

At 108 Vrms the 15 Arms ceiling permits at most 1620 W ideal-PF input. The
requested 1796.310 W input anchor would require 16.633 Arms, so every
frequency case must fold back at low line. The retained nominal case is 1796.310 W input at 120 Vrms and 15 A true RMS.
The ratios P/V (14.969 A at 120 V and 13.608 A at 132 V) are ideal-PF lower
bounds, not true RMS including ripple. The 132 V matched-power current must
be solved in the maintained model. These are input-power comparisons, not
delivered DC or pan power.

## Reference points and sources

* TI's [UCC28180 datasheet](https://www.ti.com/lit/ds/symlink/ucc28180.pdf)
  specifies programmable CCM operation from 18 kHz to 250 kHz. It therefore
  covers 65, 90, and 129 kHz. Its integrated gate output is specified as a
  1.5 A source / 2 A sink peak capability, not an output impedance guarantee.
* TI's [SLUP348 2 kW design review](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/234/07_5F00_2kWcharger_5F00_slup348.pdf)
  uses UCC28180 at 130 kHz and gives a 168 uH choke calculation at a 30%
  ripple design point. This is a topology reference, not proof that its
  high-line/current conditions transfer to this 120 Vrms, 15 Arms appliance.
* TI's [UCC28180EVM guide](https://www.ti.com/lit/ug/sluuat3b/sluuat3b.pdf)
  demonstrates a 390 V, 120 kHz, 360 W PFC module. It validates controller
  frequency use, not a 1.8 kW magnetic or thermal solution.
* TI's [choke design article](https://www.ti.com/lit/ta/sszta19/sszta19.pdf)
  explicitly separates bridge, inductor, diode, and switching losses. Its
  45 kHz sendust example shows why a lower frequency can be a magnetic/core
  choice rather than a free MOSFET-loss reduction.
* TI's [TIDA-00779 design guide](https://www.ti.com/lit/ug/tidube1d/tidube1d.pdf)
  uses UCC28180 at 45 kHz with an actual 180 uH choke, but its 190--270 Vac,
  high-line 3.5 kW envelope is not a magnetic drop-in for this 120 Vac,
  15 Arms case. It is useful evidence that 45 kHz is a real controller/magnetic
  design point, not evidence that 180 uH remains sufficient here.
* The exact 180 uH candidate is Wurth [760800301](https://www.we-online.com/components/products/datasheet/760800301.pdf):
  24.5 A at 40 K natural-convection rating, 48 A at 4 m/s, 43 A typical
  saturation current, and 20 mOhm maximum DCR. Its local retained PDF hash
  is `4b01fecaf517331dbc40cc291b2b0841904d8a221228b43541c72416c91217f8`.

## Matched-ripple calculation

For a boost CCM worst-case duty point of `D = 0.5`, use

`delta_I = Vbus * D * (1-D) / (L * fSW)`.

The switch-loss comparison uses the experiment-02 `Vbus = 400 V`, rather than
the older 389.615 V control-calculation value. With `L = 180 uH` and
`fSW = 129107.392 Hz`, the baseline ripple is 4.30305 A peak-to-peak.
Keeping `L*fSW` constant gives:

| Case | Effective L for 4.303 A pp | Nominal L with 10% tolerance + 10% DC-bias allowance | Stored energy at 120 V, 15 Arms* | Conditional C7 no-assist subtotal |
| --- | ---: | ---: | ---: | ---: |
| 65 kHz | 357.53 uH | 441.39 uH | 97.6 mJ | 26.13 W |
| 90 kHz | 258.21 uH | 318.78 uH | 70.5 mJ | 33.68 W |
| 129.107 kHz | 180.00 uH | 222.22 uH | 49.1 mJ | 45.50 W |

`*` Energy uses the ideal-CCM conservative bound
`Ipk = sqrt(2)*15 + delta_I/2 = 23.365 A`; the retained 120 V operating
point has 15 A true RMS. The bound combines maxima that need not occur
at the same line phase and is not an exact simulated peak. The
maintained model's inductor RMS is already the 15.0 A true-RMS input current;
do not add triangular ripple RMS again. Compare the 23.365 A peak with the
choke's saturation curve, while its 24.5 A natural-convection rating is a
thermal RMS rating. Saturation, hot bias, airflow, and core temperature remain
unverified. The 108 V full-power 25.68 A peak is infeasible because it would
require 16.633 Arms and is therefore not an operating point.

The nominal-L column is a design envelope, not a part recommendation. The
existing 180 uH part is published at +/-20% inductance; its low-inductance
144 uH corner is why the maintained switching report also evaluates 144 uH.
No retained source supplies the new choke's bias curve, core loss, AC copper
loss, hot DCR, airflow, or saturation margin.

Do not keep 180 uH while lowering frequency and claim unchanged currents. At
65 kHz the ripple would be 8.55 A pp; at 90 kHz it would be 6.17 A pp. The
larger ripple changes current-sense peak, RMS losses, bridge/diode stress,
and the energy that the choke must absorb.

## What the switch subtotal means

The retained experiment-02 C7 no-assist point is 120 V, 400 V bus, 12 V
UCC27624, 4.7 ohm external gate resistance, Qgd multiplier 1, transfer charge
10 nC, and RDS multiplier 1. Its terms are:

* overlap: 37.36824 W;
* output-capacitance energy: 1.51056 W;
* conduction: 6.47946 W;
* gate-network charge energy: 0.14408 W;
* subtotal: 45.50234 W.

For the table, only overlap, Eoss, and gate charge are multiplied by
`fSW / 129107.392`; conduction is held constant because the ripple is held
constant. This is a transparent sensitivity, not a new simulation and not a
claim that transition energy scales linearly in the assembled loop. Driver
resistance, common-source inductance, diode commutation, ringing, dead time,
and measured Eon/Eoff can all break that scaling.

The 65 kHz figure is therefore useful for deciding whether to spend effort on
a magnetic prototype. It is not permission to remove a heatsink or to add
the nominal wattage to the remaining assembly terms.

## Conventional silicon candidates

`IPW65R045C7` remains the best-supported baseline: 650 V, 45 mOhm maximum at
25 C, 93 nC typical Qg, 30 nC Qgd, and 11.7 uJ Eoss at a 400 V test point.
Its 150 C typical RDS curve point is 96 mOhm, and actual Eon/Eoff at this PFC
current is unknown.

`IPW65R041CFD7` is a plausible silicon screening candidate (41 mOhm maximum,
76 mOhm typical at 150 C), but its 102 nC Qg and 14.0 uJ 400 V Eoss are higher
than C7. Its fast-body-diode marketing does not supply a matched CCM PFC
Eon/Eoff result. The lower hot-RDS direction can be defeated by higher
switching and gate loss.

`STW65N65DM2AG` is retained as a control, not a recommendation. Its 50 mOhm
maximum RDS, 120 nC Qg, and 58 nC Qgd make the experiment-02 no-assist point
substantially worse under the same assumptions. A silicon-only boost still
needs a separately qualified diode: the maintained model's C3D20065D is a
SiC Schottky with zero reverse-recovery charge in the model. A conventional
ultrafast silicon diode would add an exact `Qrr * Vbus * fSW` term plus
forward-drop loss; without a named device and test conditions that term stays
unknown. Lowering frequency helps that term, but does not establish a diode
winner.

## Magnetic, bridge, and capacitor consequences

The Wurth 180 uH candidate's 24.5 A natural-convection rating is a thermal
RMS rating, and the maintained model's inductor RMS is 15.0 A at the input
ceiling. The 23.365 A ideal-CCM peak bound is instead compared with its 43 A
typical saturation-current screen. A forced-air rating is available, but
installed airflow, hot-bias inductance, and core temperature are not part of
the current evidence. This remains a magnetic qualification gap, not a reason
to ratchet the input ceiling.

At 120 V and 15 A the 20 mOhm DCR alone is about 4.50 W using the maintained
true-RMS current. A new 258/358 uH winding will not retain this
DCR by arithmetic. More turns can increase copper length and AC proximity
loss; a larger core can reduce flux density but increase size and cost. Core
loss needs manufacturer Steinmetz/B-H data or a measured bias/ripple sweep.

Bridge loss remains a large term in the retained screen: about 28.28 W from a
constant 1.05 V two-diode estimate at nominal current. That is an estimate,
not a temperature-qualified value. The boost diode's forward curve,
capacitance, and commutation are unclosed. Bulk capacitor ESR/current sharing,
PCB and connector resistance, relay/NTC behavior, and auxiliary supply loss
are likewise unknown. A total-efficiency ranking with those fields null would
be misleading.

## Cheap 15 V control question

Using the actual AUX_15V rail to supply UCC27624 is conditionally attractive:
the driver recommends 4.5--26 V and the C7's +/-20 V VGS absolute maximum must not be exceeded. It could avoid
a dedicated nominal 12 V regulator. It is not established that 15 V improves
the system. `Qg * Vdrive * f` is 0.144 W at 12 V and 0.180 W at 15 V for the
93 nC C7 charge point held fixed. Qg itself depends on bias, so the 15 V
number is only a charge-scale estimate, not a matched gate-drive prediction.
These figures are supply charge energy, not die switching loss.
At 15 V, gate overshoot and negative undershoot must remain inside the C7
absolute maximum, with practical margin, and the controller-to-driver input waveform must be valid during
UVLO, startup, OVP, and faults.

The decisive measurement is the actual AUX_15V at the UCC27624 pins while the
C7 crosses its Miller plateau, with VGS, VDS, driver output current, ringing,
and temperature captured. If that passes, rerun the experiment-02 cases at
15 V. Do not add a 12 V rail solely because the model used 12 V, and do not
reuse the 12 V result as evidence for 15 V.

## Most discriminating next inputs

1. Measure the candidate choke's inductance and temperature rise versus DC
   bias at the 108 Vrms/15 Arms current envelope, then measure core and winding
   loss at 65, 90, and 129 kHz with the matched ripple amplitudes. This
   resolves the main frequency tradeoff.
2. On a 400 V double-pulse fixture, capture C7 (and any silicon candidate)
   Eon/Eoff, Eoss commutation, VGS plateau, VDS overshoot, and current at the
   actual line-phase switching-current range. Use hot 25/100/125 C fixture
   points and preserve the waveforms.
3. Characterize an exact conventional silicon boost diode's Qrr and Vf over
   current and temperature. Add its reverse-recovery and capacitive terms
   without double-counting Eon/Eoff.
4. Validate AUX_15V regulation and UCC27624 input/enable sequencing at the
   board pins. The driver EN pull-up is not a fail-off mechanism.
5. Measure bridge Vf, HCSM2818FT10L0 shunt assembly temperature, bulk-cap ESR/ripple, and
   installed heatsink/airflow before making a whole-assembly efficiency or
   cost decision.

Until those measurements exist, the decision is to retain the C7/SiC baseline
for the controlled experiment, prototype 90 kHz with a real 258 uH-class
choke as the first lower-frequency branch, and treat 65 kHz as a magnetic
redesign with explicit size/thermal risk.

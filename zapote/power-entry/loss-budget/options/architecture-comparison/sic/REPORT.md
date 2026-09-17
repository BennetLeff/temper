# Conventional boost candidate: Kelvin-source SiC

Research snapshot: 2026-09-17. Source revision checked in the canonical input
worktree: `07a066e86251c13b0aec95b3d6f4ce958459db39`. This is an architecture
comparison and measurement contract. It does not edit the PCB, select a BOM,
claim qualification, or rank total assembly efficiency.

## Recommendation

Carry **onsemi NTH4L060N065SC1 + TI UCC27624DR** as the conventional single
diode-bridge CCM boost coupon candidate. Use one driver channel, disable the
unused channel, and propose a regulated **0/+15 V unipolar** gate bias at the
driver pins. The 15 V value is the NTH data-sheet RDS(on) test point; it is not
a manufacturer-recommended turn-on voltage. Keep the existing controller
GATE-to-driver input damping concept, add a short driver-output-to-gate loop,
and return the driver to the MOSFET's separate Kelvin-source pin.

This candidate is evidence-strong because the exact onsemi primary PDF is
retained and hashed, and it reports EON and EOFF at a fully stated switching
test point. That evidence is a calibration anchor, not a PFC switching-loss
prediction: the source test uses a **-5/+18 V bipolar gate swing, 400 V, 20 A,
25 °C, inductive load and RG=2.2 Ω**. The proposed assembled circuit is 0/+15 V
and its instantaneous PFC current varies with line phase and inductor ripple.
Do not import 45 µJ + 18 µJ into the PFC loss total until a matched
double-pulse measurement exists.

UCC27624 is a dual 5 A/5 A low-side driver with 4.5–26 V recommended VDD with UVLO and input tolerance
appropriate to a measured UCC28180 GATE signal. Its second channel is not a
reason to build an interleaved design now. The driver choice keeps headroom for
the 15 V proposal and provides a future channel option, while the present
architecture remains one switch, one boost diode, one inductor and one bridge.

TI's [PFC topology note](https://www.ti.com/lit/an/sluaau2/sluaau2.pdf) describes
the conventional boost as a low-side MOSFET, inductor and diode after a diode
bridge, and calls out gate-drive current, transition speed, UVLO and noise
handling. It also describes interleaved and bridgeless alternatives as more
complex topologies with additional current paths or line-commutation concerns.

## Source-bound device facts

The retained [onsemi NTH4L060N065SC1 PDF](sources/NTH4L060N065SC1-Rev3-2023-01.pdf)
(SHA-256 `e1063468f3c85e75c1830382be534ad8d7647d7f69ba8d4fe4c4dc31b004f8c4`)
specifies 650 V, a TO-247-4LD with a separate Kelvin source, and recommended
VGS operation from -5 V to +18 V. Its typical RDS(on) is 60 mΩ at 15 V/20 A/25 °C,
44 mΩ typical and 70 mΩ maximum at 18 V/20 A/25 °C, and 50 mΩ typical at 18 V,
20 A and 175 °C. No guaranteed 100 °C or 125 °C point was used.

The same PDF gives QG=74 nC and QGD=23 nC at VDS=520 V, ID=20 A and -5/+18 V.
Its switching table gives td(on)=11 ns, tr=14 ns, td(off)=24 ns, tf=11 ns,
EON=45 µJ, EOFF=18 µJ and 63 µJ total at VDS=400 V, ID=20 A, RG=2.2 Ω,
25 °C and an inductive load. Those are typical source test values. They do not
specify the assembled PFC commutation, temperature, gate loop or event-current
distribution.

The retained [TI UCC27624 PDF](sources/UCC27624-RevE.pdf) (SHA-256
`b42590ddafb28a608aae30f5a2c333851cf11ded63daa03fbdef6df93ecb8a51`) gives
4.5–26 V VDD, typical 5 Ω pull-up and 0.6 Ω pull-down, 5 A peak source/sink
tests, 4.1 V rising and 3.8 V falling UVLO, and typical 2.0/1.0 V input
thresholds. The 5 A numbers are peak capacitive-load tests, not a plateau
current guarantee. EN has an internal pull-up; an external fail-off interlock
is required.

The retained [TI UCC28180 PDF](sources/TI-UCC28180.pdf) (SHA-256
`e1e1588c6854b43742a667c76df26f06d9ac51231f0176c43b2a46b63c1b00be`) remains
the controller reference. Its GATE output, UVLO and over-voltage behavior must
be measured at the new driver's input. A nominal controller clamp or a typical
high-level value is not a startup or fault waveform guarantee.

## Comparable arithmetic and its boundary

The retained experiment-02 CCM report is pinned by SHA-256
`3805a41c953ae04dec3f65084de51a153e048d9ac4abfd204a8c52abde26749c`.
It uses a 400 V modeled bus and 129,107.39198577 Hz, with duty-weighted
switch RMS moments of 12.3323 A, 11.9995 A and 11.6573 A at 108/120/132 Vrms
when input current is 15 A. These are model moments, not measured waveforms.

At the proposed 0/+15 V drive, conduction can be screened at the stated
25 °C RDS test point. The gate term below is only a charge-scale estimate: its
74 nC input was measured at -5/+18 V, so it is not a matched 0/+15 V result.

| line | switch RMS from retained model | Pcond, 60 mΩ at 25 °C | QG·V·f gate-network term |
| ---: | ---: | ---: | ---: |
| 108 Vrms, 15 A limit | 12.332 A | 9.125 W | 0.143 W |
| 120 Vrms, 15 A nominal | 11.999 A | 8.639 W | 0.143 W |
| 132 Vrms, 15 A sensitivity | 11.657 A | 8.153 W | 0.143 W |

The equation is `Pcond = Iswitch_rms² × RDS(on)` and `Pgate = QG × Vdrive × fSW`.
The 132 Vrms/15 A point is **1,975.605 W input**, so it is not a same-power
comparison with the nominal approximately 1,796.310 W. The real-power PF=1
current target for 132 Vrms is `1,796.310 / 132 = 13.6084 A`; true RMS including
inductor ripple remains null until the model is rerun. At 108 Vrms, the 15 A
limit provides only approximately 1,617.010 W, so it is a deliberate low-line
derating point.

The 18 V/44 mΩ and 18 V/70 mΩ values are useful source-condition references but
are not terms in the proposed 15 V screen. The source EON/EOFF point is shown separately and is not
added to the table. EOSS is also absent: adding a 400 V EOSS value to a measured
EON/EOFF capture can double count capacitive energy. A future measurement must
state whether EOSS is already included.

## Terms still missing from a whole-assembly result

The partial table covers only switch conduction and the gate-charge energy rate.
It cannot represent a complete 1.8 kW PFC assembly. The bridge's two-conduction-
diode loss and reverse recovery, boost diode forward/recovery loss, inductor
DCR/core loss and saturation margin, current shunt I²R and body temperature,
bulk/output capacitor ESR and ripple current, controller loss, driver static
bias, AUX_15V conversion loss, gate-loop copper, EMI filter loss, and cooling
through the actual TO-247-4/heatsink/air path all remain unmeasured or
unbound. None may be silently filled with the C7's conditional 38–53 W result.

The mechanical cost is real: the existing TO-247-3 footprint cannot preserve
the NTH Kelvin return. Add a TO-247-4 land pattern, route power-source copper
separately from the short driver-source return, place the SOIC-8 driver and its
100 nF plus at least 1 µF local bypass, and keep the gate resistor in the
driver-to-Kelvin loop. The extra driver, bypass parts, gate resistor and copper
area are assembly terms; availability and price observations are cached and
must be rechecked before a BOM decision. The indexed 2026-09-17 observations
were 447 NTH parts at $12.83 quantity one and 1,038 UCC27624DR parts at $1.46
cut-tape quantity one; these are not live allocation guarantees.

## Required evidence before ranking

1. Verify an AUX_15V producer at the UCC27624 pins through line/load transients,
   startup, shutdown and controller UVLO. Hold EN low until both rails are
   valid and PWM is low; prove that loss of either rail disables the output.
2. Capture controller GATE, driver IN/OUT and MOSFET VGS measured at the Kelvin
   source. Use 0/+15 V as the proposal and log any peak above a provisional
   16 V review flag; then reconcile overshoot, ringing and the NTH
   operating/absolute limits. The 16 V flag is a measurement prompt, not a
   qualification limit. Confirm the unused channel is disabled.
3. Run double-pulse tests at approximately 400 V over the instantaneous
   drain-current range present at switching instants, not the duty-weighted RMS
   values. Sweep gate resistance from the 2.2 Ω source anchor upward and capture
   EON/EOFF, VDS overshoot, VGS ringing and EMI at controlled 25/100/125 °C
   fixture states.
4. Run CCM PFC at 108 Vrms/15 A derated, 120 Vrms/15 A nominal and 132 Vrms at
   the true-RMS current solved for the same 1796.310 W input power. P/V is
   only an ideal-PF lower bound; the true-RMS setpoint remains unknown. Measure bridge, diode, magnetics, shunt,
   capacitor, auxiliary and cooling terms before comparing assemblies.

## Escalation trigger

Do not design interleaved or bridgeless variants yet. Escalate to **interleaved
boost** only if the measured single-boost assembly misses the system's written
loss or thermal budget, or fails inductor-current/EMI limits after the gate and
cooling evidence above. Interleaving adds a second MOSFET, diode,
inductor/current path and control phase; the UCC27624 second channel does not
by itself establish the benefit.

Consider **bridgeless boost** only when measured bridge-diode conduction and
line-commutation loss is the dominant remaining shortfall and the required
line-referenced EMI/control evidence is available. Removing the bridge adds
line-commutation and common-mode constraints, so it is not a free subtraction.
These are escalation criteria, not designs or claims of savings.

## Verification

The candidate arithmetic in `candidate.json` was independently recomputed from
the pinned switch-RMS values and the equations above. Primary PDFs were copied
without modification and their SHA-256 values were checked after copying. Web
research was limited to the official onsemi NTH data sheet, TI UCC27624 product
data sheet and TI SLUAAU2 PFC topology note; no distributor observation is
treated as measured electrical evidence. No CAD, Rust harness, source or shared
build was changed.

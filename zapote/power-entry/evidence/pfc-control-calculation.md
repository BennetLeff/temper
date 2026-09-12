# Conditional UCC28180 control calculation

Date: 2026-09-11.  This calculation uses the current prototype at
`/private/tmp/temper-power-entry-20260912/elec/src/power_entry_unit.ato` and
is intended to replace its placeholder control values. It is a design
starting point, not a stability or production qualification result.

**Superseded correction:** the earlier revision omitted the `fSW` factor in
TI equation 78 and reported the wrong loop phase. The values below replace
those earlier intermediate values.

## Assumptions

The target is 1,800 W measured at the 120 Vrms, 60 Hz input, PF = 1.00 as a
current-limit design point. I used 94% PFC efficiency only to estimate the
regulated output power (`Pout = 1,692 W`); changing that efficiency changes
the loop-plant calculation. The bus target is 390 V. The boost inductor is
150 uH nominal, 121.5 uH at the combined -10% tolerance and -10% DC-bias
corner, and the
shunt is 10 mOhm. Four 560 uF capacitors are treated as a 2,240 uF parallel
bank. Startup and inrush are excluded.

TI's procedure and equations are in the [UCC28180 datasheet, sections
9.2.2.1–9.2.2.12, pp. 23–35](https://www.ti.com/lit/ds/symlink/ucc28180.pdf).
The TI 2 kW design seminar uses the same controller and shows the CCM
inductor/current and four-capacitor calculations on [SLUP348, pp. 11–14](https://www.ti.com/seclit/ml/slup348/slup348.pdf).

## Calculated operating quantities

* `IIN_RMS = Pin/Vin = 1800/120 = 15.00 A` (the requested input target).
* Sinusoidal current peak is `sqrt(2) * 15 = 21.21 A`; average rectified
  current is `2*sqrt(2)/pi * 15 = 13.50 A`.
* At the worst 50% boost duty point, switching ripple is
  `dI = Vout*D*(1-D)/(L*fSW) = 390*0.25/(121.5 uH*130 kHz) = 6.18 A pp`.
  A conservative current-sense peak is therefore `21.21 + 6.18/2 =
  24.30 A`.
* TI sizes the shunt for soft overcurrent at 10% above maximum peak using
  `VSOC(min)=0.265 V` (datasheet p. 27):
  `Rsense = 0.265/(1.1*24.30) = 9.91 mOhm`. The existing 10 mOhm part
  reaches that threshold at 26.5 A and is a conservative lower-resistance
  choice; its 3 W rating still needs a temperature/ripple check. Its nominal
  full-load dissipation is approximately `IIN_RMS^2*R = 2.25 W` before
  switching/ripple contributions.

## Proposed component starting values

These values are the output of the TI procedure where the datasheet gives a
closed-form rule. Values marked “initial” require a measured or simulated
loop iteration before claiming stability.

| Function | Calculation / constraint | Proposed start |
|---|---|---|
| Switching frequency | TI FREQ curve/equation with `fSW=130 kHz`, `fTYP=65 kHz`, `RTYP=32.7 kOhm`, `RINT=1 Mohm` | `RFREQ ≈ 16.2 kOhm`, 1%; verify actual frequency on the assembled controller |
| Feedback bottom | `RFB2 = VREF*RFB1/(VOUT-VREF)`, `VREF=5 V` | `RFB2 = 13.0 kOhm`, 1% |
| Feedback top | TI recommends about 1 Mohm total and series parts for voltage rating (p. 28) | `5 x 200 kOhm` in series, each with an explicit working-voltage rating; total 1 Mohm |
| VSENSE filter | TI limits `RFB2*C` to about 10 us (p. 29) | `CVSENSE = 680 pF` gives 8.84 us with 13 kOhm |
| ISENSE filter | TI specifies 220 ohm series resistor plus 1,000 pF local capacitor (p. 27) | Keep `RISENSE=220 ohm`; add `CISENSE=1 nF` directly at ISENSE to quiet ground |
| Current averaging | TI selects `fIAVG ≈ 5 kHz`, and warns that too large/small CICOMP affects THD/stability (p. 31) | `CICOMP ≈ 2.7 nF` initial, directly from ICOMP to quiet ground; see calculation below |
| Voltage loop | TI equations 109–119: zero at the PWM-to-stage pole, 20 Hz pole, 10 Hz target | `CVCOMP≈5.6 uF` series, `RVCOMP≈33.2–34.0 kOhm`, `CVCOMP_P≈240 nF` parallel |
| VCOMP rating | TI requires VCOMP capacitor rating above the 7 V pin absolute maximum (p. 33) | Use a specified >=10 V capacitor; the current unresolved 10 nF cannot be accepted |

The current source's `ICOMP -> 10 kOhm -> 4.7 nF -> GND` is not the TI
current-averaging topology: the datasheet describes a capacitor from ICOMP to
ground. The proposed 2.7 nF is therefore conditional on changing that
connection to a direct capacitor. The current source also has only one
series VCOMP R/C and no parallel compensation capacitor, so its `10 kOhm +
10 nF` pair is not an implementation of the TI example network.

## Nominal loop calculation (reduced model)

For a reproducible nominal iteration, TI equation 78 is evaluated directly:
`M1M2 = Pin*Vout*2.5*Rsense*K1*fSW/(Vin_rms^2*10^6)` in V/us. With
`Pin=1800 W`, `Vout=390 V`, `Rsense=10 mOhm`, `K1=7`, `fSW=130 kHz`, and
`Vin=120 V`, this gives **1.1090625 V/us**. The TI example's corresponding
calculation is 0.7625 V/us with its printed 0.92 efficiency convention (close
to its rounded 0.751 figure).

Bisection of the exact TI piecewise equations 81–88 over the required
2–4.5 V range gives `VCOMP=3.227878 V`, `M1=0.609326`, `M2=1.820147`, and
`M3=1.382273`; `M1*M2=1.1090625 V/us`. The selected nominal constants are
`gmi=0.95 mS` and `gmv=56 uS` (magnitude; TI lists the voltage gm as a
negative error-amplifier transconductance) from the datasheet typical
electrical characteristics (p. 5).

For the 5 kHz current-averaging target, the TI example relation is
`CICOMP = gmi*M1/(2*pi*K1*fIAVG)`, with `K1=7`. Substitution gives
`0.95mS*0.609326/(2*pi*7*5kHz) = 2.63 nF`; the proposed standard value is
`2.7 nF`, giving a nominal pole near 4.9 kHz. This calculation requires the
direct ICOMP capacitor topology described above.

The reduced output-plant pole is estimated from the twice-line energy model
as `fPWM_PS = 1/(2*pi*[K1*2.5*Rsense*Vout^3*Cout]/[KFQ*M1M2*1e6*Vin^2])`
(equation 106), which evaluates to **0.840844 Hz**. Equation 107 gives
`GFB=13k/(1M+13k)=0.012833` and the reduced open-loop magnitude at 10 Hz as
`GVL=-5.636 dB`. Equation 113 then gives `Cseries=5.540 uF`; choose 5.6 uF
with a >=10 V rating. Equation 116 with the actual 5.6 uF gives
`RVCOMP=33.8 kOhm`; choose 33.2 kOhm or 34.0 kOhm. Equation 118 with 34.0
kOhm and 5.6 uF gives `CVCOMP_P=~247 nF`; choose 240 nF. These are the
nominal equation outputs for this plant, subject to the specified standard
part values.

For the common-part selection now used by the calculator (`Cseries=4.7 uF`,
`RVCOMP=40.2 kOhm`, `CVCOMP_P=220 nF`, `CICOMP=2.7 nF`), the full complex
equation-120 transfer gives `fIAVG=4.86 kHz`, unity-gain crossover
`9.970 Hz`, and phase margin `62.1°` for this reduced nominal plant. The
calculation includes the equation-111 integrator; it is still conditional on
the idealized plant and controller typical constants, not a hardware
stability guarantee.


## Checks and limits

The 768 kOhm single top resistor in the source gives a nominal divider ratio
close to 390 V, but it violates the TI design guidance to use series parts
for the top resistor's voltage rating unless its exact part data proves the
rating. The proposed five-part string dissipates about 0.152 W total at 390
V, or about 30 mW per resistor, subject to resistor voltage and creepage
limits.

The 2,240 uF bus bank has an ideal 120 Hz, full-load ripple estimate from
integrating the twice-line capacitor current. With the power-ripple
amplitude convention used by TI, the peak-to-peak result is
`dVpp ≈ P/(2*pi*fline*C*V) = 1692/(2*pi*60*2240uF*390) ≈ 5.14 V pp`.
This is only a capacitor-energy estimate; ESR, controller EDR thresholds,
line variation, and the downstream load dynamic response remain unmodeled.

No phase margin, crossover, current-loop gain, inductor-loss, or component
temperature claim is made here. The exact TI equations require the selected
controller constants, actual VCOMP operating point, switching waveform, and
power-stage small-signal parameters. Those must be iterated with the real
inductor at bias and hot temperature and then checked on hardware.

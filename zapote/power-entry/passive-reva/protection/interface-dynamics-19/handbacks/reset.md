# Revision 18 reset, cooldown, and gate discharge review

## Result

The existing 120 ms service-reset interval is defensible only for the
LT4363 timer-reset requirement. It is not a bound on MOSFET gate discharge,
output-capacitor discharge, or complete load shutdown. Those are separate
acceptance items.

The Rev. C LT4363 datasheet says the `-1` latch-off variant remains off after
the cool-down phase until reset. It specifies `tRESET = 100 us` with SHDN <=
0.4 V (electrical-characteristics table, p. 4). Its application text says
that a cool-down phase can be interrupted by holding SHDN low for at least
`1 s/uF` of CTMR, after which the `-1` restarts when SHDN goes high (p. 12).
For the selected C2, the screened effective range is 94.75775--105.26775 nF,
so the latter rule gives 94.8--105.3 ms. A 120 ms low interval covers the
maximum screened value with about 14% time margin. It does not prove the
external SHDN waveform reaches the required low level or that release is
fast enough; those remain measurements.

The datasheet also states that both GATE and FLT remain low for the `-1`
after timer expiry and points back to the same reset method. Thus there is no
datasheet claim that a normal /SHDN reset waits for a particular gate
discharge time. The reset acceptance should distinguish these cases:

* **Latched fault, after cooldown:** hold SHDN <= 0.4 V for >=120 ms in this
  prototype; then release only after the source has removed RUN/PERMIT and
  the rail is valid. A fresh authorization sequence is required.
* **Latched fault, during cooldown:** the same >=120 ms interval is intended
  to cover the `1 s/uF` interruption rule at C2's screened maximum, but the
  test must exercise a reset at several points in cooldown.
* **Normal service SHDN:** verify actual GATE/VGS fall, not merely the 100 us
  tRESET datum. The LT4363 table gives a minimum 50 uA pull-down in
  shutdown/UV mode at GATE=10 V. Using Rev. 18's 1.70 uF allocation and the
  intentionally conservative constant-current model gives
  `1.70 uF * 10 V / 50 uA = 340 ms` to remove 10 V of charge. To reach an
  observed safe VGS value Vsafe from an initial 10 V, the corresponding
  screen is `1.70 uF * (10 - Vsafe) / 50 uA`; e.g. 4 V is 204 ms. This is an
  illustrative lower-current screen, not a guaranteed complete turn-off
  time: MOSFET gate charge, Miller plateau, diode/resistor topology, leakage,
  and the actual pull-down current versus voltage all matter. The GATE node
  and Q1 VGS must be probed directly.
* **UV/brownout and cold startup:** UV low has its own 1 mA gate pull-down
  behavior in the datasheet description, but a slowly collapsing VCC, the
  external output capacitor, and downstream converters can create a
  different waveform. Hold RUN/PERMIT low and demonstrate that no switching
  resumes merely because AUX returns; record GATE, VGS, VOUT, VCC, SHDN, and
  permission signals from fault onset through restart.

The 330 uF C4 is downstream of the pass device. Turning Q1 off stops source
  delivery but does not itself discharge C4. Existing downstream loads may
  discharge it, yet their current is load- and mode-dependent. A complete
  shutdown requirement therefore needs either an explicit discharge path or a
  measured maximum VOUT decay under every intended no-load and powered-load
  condition. Do not infer output discharge from the LT4363 timer or from the
  gate waveform.

## Recommended bench acceptance

Use a current-limited SELV supply and the actual C2/C3/C4 corners where
possible. For each case trigger OV, OC, UV, and service SHDN separately and
capture VCC, SNS/OUT, GATE, Q1 VGS, VOUT, TMR, SHDN, FLT, RUN, and PERMIT.

Pass criteria should be stated as measured requirements: (1) SHDN is <=0.4 V
for >=120 ms and has a verified release slew >=10 V/ms; (2) Q1 VGS falls
below the selected safe value before any permission can return; (3) VOUT
falls below the chosen safe/restart threshold within a separately specified
time, including the no-load case; (4) no switching resumes without a fresh
ARM/PERMIT/session sequence; and (5) repeated fault/reset cycles do not
accumulate a precharge or bypass a latch. If a maximum complete-shutdown
time is required, choose it from these captures or add a discharge component;
do not label 100 us, 120 ms, or 340 ms as that maximum without this evidence.

Primary source: Analog Devices, LT4363 Rev. C datasheet,
https://www.analog.com/media/en/technical-documentation/data-sheets/4363fb.pdf
(pp. 4, 9--12). The 50 uA value is the shutdown/UV minimum pull-down row in
the electrical-characteristics table, conditioned at GATE=10 V.

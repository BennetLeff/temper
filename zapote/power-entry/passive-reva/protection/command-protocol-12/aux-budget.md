# AUX cutoff: static progress, transient limit still open

Evaluation topology remains HOT raw supply → 15 V regulator → TPS26601RHFT
cutoff → AUX consumers and 5 V buck input. The cutoff is downstream of the
regulator so it can address regulator pass-through. It is not a voltage clamp
and its overload latch setting does not establish latched overvoltage recovery.

The primary OVP threshold range is 1.17–1.225 V, and its pin leakage is ±100 nA
over the stated 0–4 V pin range. With a 120 kΩ ILIM resistor, the table gives
85 mA minimum active current limit and 45 mA minimum circuit-breaker threshold.
Factory UVLO can require 15.75 V on startup. The timing row's OVP endpoint is
FLT assertion, not a complete downstream-voltage bound.
[TI TPS2660 Rev G, §§7.5–7.6](https://www.ti.com/lit/ds/symlink/tps2660.pdf).

Parent Rust arithmetic uses 130 kΩ/10 kΩ, ±1% **total** resistance variation,
the threshold interval and both leakage signs. KCL gives
`Vtrip = Vthreshold × (1 + Rtop/Rbottom) + Ipin × Rtop`.
The derived interval is **16.065942–17.484847 V**. The maximum calculated OVP
pin voltage at normal AUX=15.75 V still lies below the 1.17 V minimum trip
threshold. These calculations omit unbounded transients and are not a complete
production qualification; see [aux-budget.csv](aux-budget.csv).

Three additional decisions remain necessary:

- **UVLO programming:** do not silently select factory UVLO by tying its pin
  low. Its possible 15.75 V startup threshold is incompatible with guaranteed
  startup from the existing supply candidate's 14.625 V static lower output.
  Program and budget an appropriate external threshold.
- **Current limit:** recomputing the historical 75 mA AUX and 75 mA logic budgets
  at 70% buck efficiency and 14.625 V gives 111.630037 mA downstream, before the
  new isolator and unbounded startup demand. The earlier 111.74 mA prose was
  slightly inaccurate; the current Rust calculation owns this result. Thus 120 kΩ is
  rejected for either quoted response mode. Luna's 56 kΩ suggestion is only an
  intermediate nominal setting; no exact value is selected here without the
  actual load/startup and fault-mode budget.
- **Fault recovery:** a source retry or cutoff recovery must not create an
  accepted start. The command protocol proposed in this round failed that
  independent design review and cannot be credited as the solution.

## What is missing from the voltage proof

A necessary lumped-capacitance budget has the form

`Vpeak ≤ Vbefore + Qnet/Ceffective + parasitic excursion < 18 V`,

where Qnet is the net charge reaching the protected output through the fault
interval until actual isolation. It requires a justified failed-regulator/source
waveform, path impedance, current response, FET turnoff endpoint, minimum
effective output capacitance and parasitic bound. Those inputs are not available.
The table's 6 µs entry is not used as a guaranteed FET turnoff time: the extracted
column assignment was not established, and the named endpoint is FLT.

Starting at 15.75 V and ignoring parasitic excursion, the available charge is
2.25 µC per effective µF. The program reports illustrative 1, 10 and 47 µF
values; none is an accepted assembly capacitance. A current-limit number cannot
be multiplied by an assumed response time to establish this charge without
proving when that limit applies during the fault.

The historical A5 47 µF nominal capacitor is attached to the **LDO output**.
With the new cutoff inserted after that node, it is upstream of the protected
fanout, so it cannot simply be credited to downstream hold-up/overshoot control.
Revision 11 separately includes nominal 1 µF driver and controller bypasses;
their effective capacitance, added buck input capacitance and connection
parasitics must be accounted for in the actual assembled graph. Moving the LDO
capacitor also requires preserving that regulator's stability requirements.

Normal supply loading, regulator heat, raw-source overshoot and driver/relay
startup remain the earlier A5 candidate's open assumptions. This round adds
static evidence and rejects inadequate settings; it does not certify AUX≤18 V.

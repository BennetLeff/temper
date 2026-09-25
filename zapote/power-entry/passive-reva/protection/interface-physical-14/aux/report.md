# AUX15 fault-envelope screen (interface 14)

This folder contains an arithmetic screen for a proposed series/current-limit
barrier between the 15 V producer and the protected driver rail. It does not
select a resistor, clamp, eFuse, MOSFET, or capacitor and it is not a circuit
qualification. The Rust source owns every number in `results.csv`.

## Result

The normal-dropout and fault-current requirements do not form a feasible
passive-resistor interval under the stated envelope. The protected rail may
fall no lower than 14.25 V while the producer is only 14.625 V. With the
revised conditional load bound (75 mA direct AUX plus a 5.25 V, 75 mA LOGIC5
load reflected through the assumed 70% buck efficiency at 14.25 V),

```text
Iload = 0.075 + (5.25 * 0.075)/(0.70 * 14.25)
      = 0.114473684 A
Rseries <= (14.625 - 14.25) / Iload
         = 3.275862 ohm
```

This is an optimistic ceiling: it leaves no voltage for switch on-resistance,
wiring, connector drop, or any regulator dropout not already represented by
the 14.25 V protected-rail contract. The older 111.630037 mA calculation is
retained in the CSV for comparison but is not the revised worst-case bound.

With an ideal stiff 35 V fault source, a 3.275862 ohm resistor would pass
5.189 A at an 18 V clamp boundary and dissipate 88.22 W instantaneously.
These are conditional stress figures, not measured IRM fault currents. To
limit current to 120 mA starting from a 14.25 V protected rail requires at
least 172.917 ohm; the nominal-load voltage-drop calculation is 19.794 V,
which exceeds the entire available source voltage and proves incompatibility. At 24.6 V the corresponding figures are 2.015 A
and 90.414 ohm (for a 114.474 mA bound). Therefore a passive resistor cannot
both preserve the normal rail and establish a low fault-current guarantee.

A downstream capacitor only bounds charge over a **bounded fault interval**:

```text
C_boundary = I_fault * t_fault / (18 V - Vstart)
C_effective > C_boundary for strictly below 18 V even before parasitic allowance
```

For a 120 mA limiter and a 15.75 V starting rail, the equality boundary is
53.33 uF for 1 ms, 533.33 uF for 10 ms, and unbounded as the fault interval becomes unbounded.
With a persistent 24.6 V or 35 V source, a finite capacitor eventually rises
to the source voltage. The capacitor therefore requires a guaranteed
interruption deadline (or a rated clamp) and a minimum effective capacitance;
it is not an independent proof of `Vout < 18 V`.

## What the source documents actually guarantee

| Source | Published fact used here | Boundary of that fact |
| --- | --- | --- |
| Mean Well IRM-10-24 spec, pp. 1–2 | 24 V model, 0.42 A rating, ±2.5% tolerance; OVP trigger range 27.6–32.4 V; protection is described as output shutoff/zener clamp and overload hiccup | The OVP range and protection description do not specify a transient waveform, source impedance, clamp current/energy, or maximum output peak after a downstream fault. The 35 V raw envelope is an explicit design assumption, not a datasheet guarantee. |
| TI TPS7A470x Rev G, §§5.1/5.5 | Recommended input 3–35 V, input absolute maximum 36 V; 15 V overall accuracy ±2.5% under `VI >= VO(nom)+1 V`, `COUT=20 uF`, 0–1 A; dropout is 307 mV typical / 450 mV maximum at 1 A | These are regulator operating/accuracy conditions, not a guarantee that a failed LDO output cannot follow its input. The 14.625–14.25 V drop budget is a system contract, and resistor/switch/wire loss consumes it. |
| TI TPS2660 Rev G, §§7.5–7.6 and 9.3.2 | TPS26601 adjustable OVP is a cutoff: OVP above threshold turns off the internal FET; 6 us nominal OVP-disable delay (MAX blank) is specified under `VIN=24 V`, `COUT=1 uF`, `RILIM=120 kOhm`; 120 kOhm current-limit range is 85–115 mA and short-circuit range 80–120 mA under stated tests | The 6 us row is not an OVP-to-FET-off/output-peak bound. It has no specified fault-source envelope or effective downstream capacitance. The 85 mA minimum limit is below the revised 114.474 mA load, so this setting is rejected; no reliance on its typical or maximum limit is allowed. TPS26601 OVP is not a clamp. |
| ADI LT4363 Rev C, §§8–9 / Applications Information | External MOSFET surge stopper, adjustable FB servo 1.25–1.30 V, current limit and timed latch/retry; the pass MOSFET regulates output during overvoltage | The data sheet requires input waveform, load, timer and external-MOSFET SOA analysis. No MOSFET, timer, compensation, source transient or effective output capacitance is established here, so the static screen cannot prove 18 V protection. |

The IRM's 32.4 V value must not be used as a clamp voltage. The TPS26602
fixed clamp is outside this architecture's 18 V target and is not credited.

## Actionable architecture decision

Do not integrate a passive series resistor/current-capacitor barrier into the
136-component candidate. To make this interface admissible, select one of two
bounded architectures and close its missing contract:

1. A cutoff/current limiter with a guaranteed maximum interruption time,
   plus measured or guaranteed minimum effective protected capacitance and
   bounded parasitic excursion; or
2. An active surge stopper such as LT4363-1 with a selected external MOSFET,
   a specified clamp setpoint below 18 V, and an SOA/timer proof for the full
   source waveform.

Neither choice is a part selection in this screen. The existing TPS26601
cutoff can only be reconsidered after its post-fault charge and interruption
envelope are supplied; its OVP threshold alone is insufficient.

## Minimum low-voltage bench evidence

Use a current-limited, isolated low-voltage DC source and a controlled LDO
short emulator; do not connect the experiment to mains. Exercise the raw
source at the stated nominal, 24.6 V, and 35 V assumption with measured rise
time and hold duration. Use the **minimum assembled protected capacitance**
including tolerance, DC-bias, temperature and aging, and both the maximum
normal load and the fault load-release case.

Record at the same time, with calibrated differential voltage probes and a
current probe or Kelvin shunt: source voltage at the barrier input, protected
output voltage directly at the driver pins, barrier current, switch gate,
fault/disable signal, and load current. The acquisition must capture the
fastest switching edge with known probe attenuation, bandwidth and sample
rate; a slow multimeter or regulator telemetry is not evidence of a peak.

For every run integrate positive net charging current from fault onset
(including the detection delay) through completed interruption and verify the independent inequality
`Vpeak <= Vstart + Qnet/Ceff + Vparasitic < 18 V`. For an LT4363-style option,
also compare the full measured MOSFET VDS/ID/time trajectory with its
applicable linear-mode SOA and thermal model, including tolerances and starting
temperature. Integrated energy alone does not prove SOA compliance.
The required report is a waveform-and-charge envelope, not a nominal SPICE
trace. No production or PCB claim follows until that envelope exists.

Primary documents: [Mean Well IRM-10 specification](https://www.meanwell.com/Upload/PDF/IRM-10/IRM-10-SPEC.PDF), [TI TPS7A47 Rev G](https://www.ti.com/lit/ds/symlink/tps7a47.pdf), [TI TPS2660 Rev G](https://www.ti.com/lit/ds/symlink/tps2660.pdf), and [ADI LT4363 Rev C](https://www.analog.com/media/en/technical-documentation/data-sheets/4363fb.pdf).

Parent source check: Mean Well specification page 2 was rendered and inspected
(2025-08-08 revision). The 0.42 A entry is rated output current; overload is
115–190% of rated output power with hiccup recovery, not a bound on immediate
fault current from stored output charge. The table supplies no peak/transient
guarantee at the driver. TI TPS7A47 Rev G §5.5 gives 450 mV maximum dropout
at 1 A, correcting the worker draft's mistaken use of the 307 mV typical value.

Parent timing-table check: TI TPS2660 Rev G page 9 was rendered and inspected.
The 6 µs OVP-disable figure is in the NOM column; MAX is blank. It measures
OVP at 20 mV above its rising threshold to FLT falling, not protected-output
peak or guaranteed FET interruption. This resolves the earlier uncertainty
about the table column without supplying the missing turnoff bound. The
render and source PDF are preserved under `../sources/`.

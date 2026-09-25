# Rev38 PFC driver-inhibit topology bakeoff

**2026-09-24 — outcome: UNRESOLVED.** Three independent read-only approach
sketches and a separate `ce-pov` assessment found no replacement ready for
U4 electrical selection. This is a circuit-selection result, not an assembled
fault-response or product-safety verdict. The joined source still uses the
[UCC27624 ENA shunt](gate-enable-corners.md), whose worst-case OFF proof is
blocked by an unspecified internal pull-up current over the joined AUX range.
Do not route U7 from any of the sketches below.

## Common brief and evidence

The replacement must keep the existing hardware `DRIVER_PERMISSION` fan-in
(receiver abort, STOP, retained RUN/session, PERMIT and faults), drive the
STW65N65DM2AG, and keep its output off with AUX present while HOT_LOGIC5 is
absent, partial, falling or recovering. A dead firmware task cannot be the
gate-inhibit mechanism. The OFF claim needs specified limits at the actual
driver pins, temperature and supply sequence, without powered-off backfeed.
Fault response ends at **sustained PFC current cessation**, not merely a low
logic pin. [Plan U4/U7](../../../../../docs/plans/2026-09-23-001-feat-power-entry-hot-receiver-plan.md)
and [timing analysis](timing-analysis.md) leave numerical acceptance open.

The frozen [driver source](source-build-06/elec/src/driver_stage.ato) and
[PFC controller source](source-build-06/elec/src/pfc_controller.ato) were
inspected along with [AUX-WINDOW](AUX-WINDOW.md), the acceptance ledger and
primary manufacturer data. The sketches are proposals; no Atopile, pin audit,
native PCB or physical capture was produced for them.

One narrower datum should remain visible: the [UCC27624 Rev. E electrical
table](https://www.ti.com/lit/ds/symlink/ucc27624.pdf) gives a **1.1 mA
maximum total disabled VDD current** with `VINx = 3.3 V`, `ENx = 0 V`
and the table's default `VDD = 12 V`, over its stated temperature range.
That total includes internal circuitry and any enable pull-up current in
that fixture, so it bounds the enable contribution there. It does **not**
specify ENA source current at the joined 15 V-class AUX rail or through an
AUX excursion. A separately regulated and qualified 12 V driver rail, or a
written full-range TI limit, would change the calculation; neither exists
in the joined source.

## Candidate comparison

| Independent candidate | Concrete mechanism | Decisive result |
| --- | --- | --- |
| A: UCC27614DSGR | Dual-input driver. AUX-powered open-collector rail and permission qualifiers pull `IN+` low unless both valid; inverse PWM drives `IN−`. OUT can rise only with `IN+` high and `IN−` low. | **Reject as drawn.** An open supply to the qualifier can leave both sinks high impedance while its external `IN+` pull-up remains live. Continuing PWM can then command OUT high. The data sheet's floating-input OFF feature does not apply to an externally pulled-high input. |
| B: TMUX7413FRRPR plus existing UCC27624 | A complementary mux disconnects UCC28180 PWM from INA and grounds INA when permission is low. Its select node uses a HOT_LOGIC5 pull-up, permission buffer and separate rail supervisor. ENA is tied high, outside the inhibit proof. | **Reject as drawn.** If only the permission buffer loses VCC, its open-drain output releases while HOT_LOGIC5 and the supervisor stay healthy. The select divider rises to about 2.5 V and selects PWM despite low permission. Mux behavior through AUX transition and actual-voltage leakage remain unresolved. |
| C: UCC27511ADBVR | A split-output dual-input driver takes PWM at `IN+`. AUX pulls `IN−` high to inhibit; two series MOSFETs may pull it low only when retained permission and a TLV809EA46DBZR HOT_LOGIC5 supervisor both release. Separate OUTH/OUTL gate resistors allow drive/discharge tuning. | **Best polarity for further design, not selected.** Loss of either proposed release drive tends to leave `IN−` high, but the MOSFETs were not selected and no full-temperature leakage, threshold, on-state or sub-POR proof exists. Its VDD is limited to 18 V recommended, while the protected AUX transient peak is unknown. |

[TI UCC27614](https://www.ti.com/lit/ds/symlink/ucc27614.pdf) specifies
the DSG dual-input truth table and 4.5–26 V recommended VDD. Its SOIC
variant has a different EN pin; package identity is essential. The proposed
[LM2903B](https://www.ti.com/lit/ds/symlink/lm2903b.pdf) comparator has no
unpowered low-clamp guarantee, and its specified VOL fixture does not bound
the threshold crossover. Supplying the `IN+` pull-up only from locally
qualified power, with a separate pull-down, is a possible redesign, not a
verified repair.

[TI TMUX7413F](https://www.ti.com/lit/ds/symlink/tmux7413f.pdf) confirms
the complementary truth table, 8–44 V single-supply range, powered-off
protection and break-before-make behavior. Its 12 V fixture limits for
leakage, on resistance and switching do not directly specify the proposed
14.25–15.75 V circuit. Break-before-make leaves an interval with both
channels open; the INA pull-down and charge injection need a transient
bound. [TI SN74LVC1G07](https://www.ti.com/lit/ds/symlink/sn74lvc1g07.pdf)
specifies that its Ioff circuit disables its output on VCC loss. That
protects against backfeed but creates B's permission-buffer supply-open
counterexample. [UCC28180](https://www.ti.com/lit/ds/symlink/ucc28180.pdf)
holds GATE off below its UVLO, with a 9.1 V minimum falling threshold. That
is favorable versus the mux's 8 V minimum only when the **actual device-pin
rail waveforms** and propagation establish the overlap. The netlist joins
both to AUX; branch impedance, an opened path or unequal local capacitor
discharge can change their instantaneous voltages.

[TI UCC27511A](https://www.ti.com/lit/ds/symlink/ucc27511a.pdf) confirms
that `IN−` high inhibits sourcing and selects its OUTL sink; `IN−` high
needs at least 2.4 V and released low at most 1.0 V. C's phrase “inhibit of
the driver's sink stage” was backwards; the drawn intent commands the sink.
VDD is 4.5–18 V recommended and 20 V absolute. [TI TLV809E](https://www.ti.com/lit/ds/symlink/tlv809e.pdf)
specifies the A46 nominal 4.63 V falling threshold, a 0.7 V POR guarantee
only at its stated light sink load, and an A-variant delayed release. Its
output is unspecified below POR. These limits do not select the two series
MOSFETs or bound their gates over the partial-rail range. The existing
[AUX window screen](AUX-WINDOW.md) gives conditional static crossings, not
a maximum voltage reached before overvoltage cutoff.

## Concrete adverse sequences

1. **A qualifier supply open:** driver AUX stays live, comparator outputs
   cease sinking, global-AUX `IN+` pull-up asserts high, PWM high pulls
   `IN−` low, and the gate may be driven. No firmware action is needed.
2. **B permission-buffer supply open:** HOT_LOGIC5 remains high at the
   select pull-up and rail supervisor, but buffer VCC is lost. Ioff leaves
   its output high impedance; the 10 kΩ/10 kΩ select network approaches
   2.5 V, above the mux's high threshold. A low hardware permission no
   longer disconnects PWM.
3. **C unbounded AUX peak:** a protected-AUX excursion to 19 V is not
   excluded by the current source evidence. It is above UCC27511A's
   recommended 18 V maximum. Its 20 V absolute rating is no operating
   allowance. Even if static inhibit works, this candidate cannot yet be
   selected for that rail.
4. **All three, short AUX dip:** the driver can stop through UVLO while
   HOT_LOGIC5 hold-up preserves retained RUN/session. On AUX recovery a
   released inhibit could restart PWM without acknowledged disarm. Prove
   the shortest relevant dip is captured and clears the retained state, or
   revise the rearm architecture. A driver truth table alone cannot do it.

## Decision and next design work

The independent judge and coordinator agree that **C's positive, default-high
inhibit polarity is the most useful mechanism to carry forward**, while
selection is blocked. A revision can explore that polarity with a driver
having sufficient supply headroom, exact orderable pull-down devices and a
rail qualifier whose own power/open/partial states fail low. It must specify
and test each connection at the actual pin rather than inherit a logic-net
name. Do not silently substitute a different driver/package: its pin map,
input current/threshold, gate drive, thermal and native footprint all change.

The next review needs (1) a qualified protected-AUX pin envelope including
overshoot and shortest dip, (2) exact release-device leakage and on-state
limits across temperature and HOT_LOGIC5 crossover, (3) a retained-clear
proof on AUX/logic loss and recovery, and (4) a loaded gate/fault-to-current
timing plan against independently derived allowable limits. Only then revise
the joined source, exact-pin mutation audit and native parity. [U4/U7
acceptance](ACCEPTANCE.md) remains OPEN; physical injections remain NOT RUN.

## Follow-up positive-release part screen (2026-09-24)

The [UCC27614DSGR data sheet](https://www.ti.com/lit/ds/symlink/ucc27614.pdf)
supports C's useful polarity with a wider 4.5–26 V recommended VDD range:
`IN+ = high, IN− = high` commands OUT low; `IN− = low` releases `IN+` to
command OUT. This is the **DSG** dual-input package, not the SOIC `D` part
with an EN pin. Its rising/falling VDD UVLO limits are 3.8–4.4 V and
3.5–4.1 V. The driver still requires an actual protected-AUX pin peak and
thermal/gate-loop review before selection.
The joined [UCC28180 PFC controller](https://www.ti.com/lit/ds/symlink/ucc28180.pdf)
shares `AUX_PROTECTED` and lists **21 V maximum recommended VCC**. Therefore
the new driver's 26 V headroom cannot make an AUX excursion above 21 V
acceptable for the joined circuit. Its GATE high limits, 10.8–12 V at
VCC = 12.2 V and 14.5–16.1 V at VCC = 20 V, are specified with a 4.7 nF
load; they are not a bound for the actual driver-input load or fast AUX
overshoot.

An external AUX pull-up on `IN−`, with series release MOSFETs driven by
retained permission and qualified HOT logic5, is a **screening sketch**.
The following limits must both hold at the driver pin through every rail
sequence; `0.8 V` is the guaranteed-low target and `2.3 V` the
guaranteed-high target from TI's input threshold table:

```text
released: I_release,max = I_external_pullup,max
                          + I_internal_pullup,max + I_other_source,max
          V_IN−,max = I_release,max × (R_DS1,max + R_DS2,max)
                       + V_return,max <= 0.8 V
inhibited: V_IN−,min = V_AUX,pin,min
                       - R_pullup,max × (I_switch_off,max
                           + I_IN−_sink,max + I_board_leak,max) >= 2.3 V
```

These are necessary static screens, not a transient proof. TI lists the
`IN−` internal pull-up as **200 kΩ typical only**; it does not specify a
minimum resistance or maximum sourced current at the actual 15 V-class
VDD. Thus `I_internal_pullup,max` in the released inequality is not bounded
by the driver sheet. Its published 12 V current fixtures do not turn into
a maximum `IN−` pull-up current at the selected AUX range. Replacing the
ENA shunt with a low-resistance `IN−` sink does not, by itself, close the
same kind of missing-limit proof.

The MOSFET screen also has a clear tradeoff. The
[Nexperia PMV30XN](https://assets.nexperia.com/documents/data-sheet/PMV30XN.pdf)
specifies 10 µA maximum drain leakage at 150 °C and 51 mΩ maximum on
resistance at 4.5 V gate drive, 3.2 A and 150 °C, but its 20 V drain rating is
not yet supported by a protected-AUX transient bound. The
[Nexperia 2N7002AK-Q](https://assets.nexperia.com/documents/data-sheet/2N7002AK-Q.pdf)
has 60 V drain rating and 5 µA maximum leakage at 125 °C, but its
published 5 V-gate on-resistance limit is at 25 °C; the high-temperature
on-resistance limit uses 10 V gate drive. The
[Nexperia NX6008NBK](https://assets.nexperia.com/documents/data-sheet/NX6008NBK.pdf)
has a 60 V rating and 5.7 Ω maximum on-resistance at 4.5 V, 300 mA and
150 °C, but no specified high-temperature drain-leakage maximum. None is an
approved release switch on the present evidence.

The existing [TPS3890](https://www.ti.com/lit/ds/symlink/tps3890.pdf)
`HOT_RAILS_OK` producer guarantees asserted-low RESET through undervoltage
only while its VDD exceeds power-on reset; below POR its open-drain output is
undefined. Its pull-up uses HOT logic5, but intermediate HOT5 and
output-charge behavior still need a pin-level bound. A short AUX
dip can stop the driver through UVLO without clearing retained RUN/session;
recovery is then a possible restart unless the actual fast-dip/retained-clear
path captures the pulse. Test the shortest dip and every rail-order
transition at the pin and at sustained PFC current, not just the static
driver truth table.

### PWM-input alternatives screened in parallel

Two read-only follow-ups tested the opposite direction: leave the
[UCC27624](https://www.ti.com/lit/ds/symlink/ucc27624.pdf) ENA tied to
its VDD and interrupt PWM before INA, whose floating-input state is
specified as output low. This avoids using ENA's typical-only pull-up as
the safety clamp. Neither follow-up is an approved circuit.

* A [SN74LVC1G08](https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf)
  AND gate could combine level-shifted PFC PWM and retained permission, with
  a local INA pull-down. TI bounds its output `Ioff` at ±10 µA with VCC = 0,
  so a 10 kΩ pull-down has a conditional 0.1 V leakage screen. But `Ioff`
  does not specify its output while HOT logic5 is between 0 and the gate's
  1.65 V minimum operating supply. The [UCC28180](https://www.ti.com/lit/ds/symlink/ucc28180.pdf)
  GATE output's stated 10.8–12 V at VCC = 12.2 V and 14.5–16.1 V at
  VCC = 20 V are 4.7 nF fixtures; a fixed divider must also keep the LVC
  input at or below 5.5 V in every actual AUX transient while meeting its
  HOT5-dependent high threshold. The direct AND path has no established
  partial-HOT5 OFF or full-range PWM-level proof.
* A corrected version of B could use the
  [TMUX7413F](https://www.ti.com/lit/ds/symlink/tmux7413f.pdf) fault-protected
  switch with an AUX-powered [TPS38](https://www.ti.com/lit/ds/symlink/tps38.pdf)
  dual undervoltage qualifier. Wire-AND its active-low open-drain outputs
  for HOT5 and retained permission, pull select up **only from the same
  local supply** and add a local select pull-down. This repairs B's
  permission-buffer Ioff counterexample in the common-supply case. It does
  not cover a qualifier VDD pin or bond opening while its external pull-up
  remains powered. TPS38 specifies reset low from its 1.4 V POR level to
  2.7 V UVLO at a stated 15 µA sink fixture; below POR its output is
  undefined. TMUX powered-off source protection is specified, but its
  intermediate-supply leakage, select transition, charge injection and
  PFC/driver rail-order behavior still require bounds at the installed
  voltages and load.
* [TMUX7212](https://www.ti.com/lit/ds/symlink/tmux7212.pdf) is not a
  substitute: its analog S/D absolute range ends at VDD + 0.5 V. PFC PWM
  present while the mux supply collapses can exceed that rating. The
  [ADI MAX313F](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX312F-MAX314F.pdf)
  explicitly keeps its switches off with power removed and tolerates
  powered-off analog pins to ±40 V, but its single-supply functional minimum
  is 9 V. A driver can remain active below that value; the 0–9 V crossover
  and retained-clear/rearm timing are unproved. Its 12 V leakage fixtures
  cannot be inherited as 15 V maxima.

A passive clamp on INA is another candidate for bench screening, with a
series resistor from PFC PWM to limit clamp current and a local pull-down.
It removes the undocumented ENA pull-up current from the OFF calculation.
It does **not** qualify HOT logic5 by itself: a diode from INA to HOT logic5
can back-power a floating HOT5 rail from PWM, while a MOSFET that releases
an AUX-biased transistor clamp can switch at a partial HOT5 voltage. The
[2N7002AK-Q](https://assets.nexperia.com/documents/data-sheet/2N7002AK-Q.pdf)
lists a 1.3 V minimum gate threshold at its 25 °C, 250 µA fixture, below
the [SN74LVC1G06](https://www.ti.com/lit/ds/symlink/sn74lvc1g06.pdf)
1.65 V minimum operating VCC; its hot on-resistance is not specified at a
partial 5 V gate. The [PMBT3904](https://assets.nexperia.com/documents/data-sheet/PMBT3904.pdf)
clamp's published saturation fixture cannot replace an all-temperature
calculation at the actual PWM source current. This path still needs bounded
PFC PWM amplitude/current, AUX and HOT5 rail sequences, input thresholds,
clamp current and saturation, and loaded gate turn-off timing.

The [TMUX6202](https://www.ti.com/lit/ds/symlink/tmux6202.pdf) is a more
direct PWM switch to examine than the 8 V-minimum TMUX7413F: it operates
from 4.5–36 V, connects S to D only when SEL is high, and has an internal
SEL pull-down (approximately 4 MΩ). A separate local pull-down would hold
SEL low when the qualifier is absent, and INA would need its own pull-down
while S/D are open. This part has **no powered-off protection on S/D**:
their recommended range is VSS–VDD and absolute range ends at VDD + 0.5 V.
The UCC28180 GATE pin can therefore violate the mux rating if its local
VCC remains charged while the mux VDD pin falls. Its specified off-leakage
and switching fixtures are at 12 V ±10% and 36 V ±10%, not the whole
joined AUX trajectory. SEL's guaranteed high threshold is as low as 1.3 V,
so direct partial-HOT5 logic could close the switch early. This remains a
candidate for a rail-coupled, AUX-qualified circuit and pin-level test, not
a selected default-off design.

An AUX-powered [TLV1701](https://www.ti.com/lit/ds/symlink/tlv1701.pdf)
qualifier is a possible way to establish a HOT5-valid threshold before
releasing that clamp: its 2.2–36 V operating range overlaps a live
UCC27624. Its open-collector output requires the **sink** state to mean
release; an external pull-up that means release would enable the path if
the comparator supply pin opened while AUX remained live. Even with sink
polarity, the comparator's output and input-clamp behavior under an opened
V+ pin, the upstream HOT5/permission signals, and short AUX dips need a
source-backed failure analysis. This is an investigation direction, not a
selected U4 circuit.

### AUX-powered positive-release PWM switch screen

A further read-only screen keeps the UCC27624 on protected AUX, ties ENA to
VDD, and inserts a normally-off P-channel switch between UCC28180 GATE and
INA. INA retains its local 10 kΩ pull-down. The switch's source is at PFC
PWM, drain at INA, and gate returns to its source. An AUX-powered comparator
would sink that gate only after the retained `DRIVER_PERMISSION` and HOT5
level are qualified. This changes the OFF argument from the unbounded ENA
pull-up to switch leakage, the INA pull-down, and PWM-edge behavior.

[TI's TLV1821DBVR open-drain comparator](https://www.ti.com/lit/ds/symlink/tlv1821.pdf)
operates at 2.4–40 V and holds its output high impedance during power-on
reset, including for up to 200 µs after crossing 2.4 V. A pull-up that keeps
the P-channel gate at its **own PWM source** therefore has the right static
polarity when comparator power or permission is missing. Its input has an
ESD clamp to V+, so retained HOT5 with AUX absent needs a back-power limit.
The exact reference, divider, input common mode, comparator output load and
rearm behavior are not specified by this sketch.

The [Nexperia NX3008PBKMB](https://assets.nexperia.com/documents/data-sheet/NX3008PBKMB.pdf)
lists at most 10 µA off leakage at 30 V and 150 °C with VGS = 0, and at
most 7.8 Ω on resistance at VGS = −4.5 V, 200 mA and 150 °C. At the
specified off-leakage fixture, 10 µA alone would make 0.1 V across the
nominal 10 kΩ INA pull-down, below the [UCC27624](https://www.ti.com/lit/ds/symlink/ucc27624.pdf)
0.8 V guaranteed-low target. That calculation excludes pull-down tolerance,
other leakage and transients. The part's **±8 V gate limit** is violated by
directly sinking its gate whenever the PWM source exceeds 8 V; a selected
source-to-gate clamp or different switch is required.
Although the oriented body diode blocks a steady PWM-high/INA-low state, a
fast PWM rise can leave the gate below the source through its capacitances
and briefly turn the switch on before the gate pull-up catches up. A
retained-high INA can also discharge through the diode into a falling PWM
source. Neither a static off-leakage calculation nor the comparator's safe
POR polarity bounds those edges. This circuit is **not selected**. A next
specimen must bound PWM amplitude/slew and gate tracking, supply/input
backfeed, INA retention, switch voltage and leakage at temperature, and
loaded OUTA/STW shutdown before replacing the joined source.

**Disposition:** keep the current joined source and U7 route gate unchanged.
The `IN−` sketch needs the missing TI source/sink current limits over the
selected AUX range, a release device with applicable temperature and voltage
bounds, a qualified AUX peak and minimum pulse capture, and loaded
gate/retained-clear timing. The PWM-input alternatives need their own
partial-supply, input-rating, and rail-order proofs before selection. None
presently closes U4's default-off requirement.

Participation: three independent `gpt-6-sol` high candidates (one native,
two read-only CLI) and one fresh read-only `gpt-6-astra` high `ce-pov` judge.
No production files were changed by candidate or judge work. The CLI did
not provide a reliable per-candidate token-usage receipt, so no usage total
is claimed.

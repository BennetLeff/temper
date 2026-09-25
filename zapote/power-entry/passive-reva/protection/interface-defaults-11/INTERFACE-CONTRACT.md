# Proposed producer contract for isolated revision 11

These are requirements for a future physical producer and its interconnect.
The nominal fixtures exercise selected behaviors; they do not establish that
an unspecified producer meets the contract. All command voltages are relative
to the HOT-domain return. A SELV MCU must not be wired directly to that return.
No isolation component or complete producer implementation has been selected here.

## ARM and PERMIT

PERMIT is a maintained permission. A low PERMIT removes driver permission and
clears retained RUN. Returning PERMIT high alone must not start switching.
ARM is an edge request: a deliberate low-to-high transition may set RUN only
when the other health conditions are satisfied. ARM low or disconnected alone
does not clear an already set RUN latch.

| Boundary | Proposed requirement |
|---|---|
| HOT logic rail, normal | 4.75–5.25 V at receiver devices |
| Producer high | At least 4.0 V while supplying approximately 0.56 mA input load |
| Producer low | At most 0.3 V |
| Command pin range | 0–5.5 V, including when the receiver supply is absent |
| Disconnected/high-impedance aggregate leakage | At most 25 µA per input, including receiver, producer and board leakage |
| Input plus cable capacitance | At most 1 nF for the stated RC decay budget |
| Input pulldowns | 10 kΩ, at most 1% total resistance deviation including temperature |

The existing SN74LVC1G17 buffers provide the partial-power boundary; new 10 kΩ
resistors bias their raw inputs. Existing output pulldowns are retained and
serve a different node. Datasheet endpoint thresholds include VT+ max 2.74 V
at VCC=4.5 V and 3.33 V at 5.5 V, and VT− min 1.51 V at 4.5 V.
The proposed producer levels leave margin to those endpoints. Qualification
must cover the actual rail range and temperature; this is not an interpolated
manufacturer threshold guarantee. See the
[SN74LVC1G17 datasheet](https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf).

Required sequencing:

1. On boot, reset and planned reconnection, hold ARM low and PERMIT low or high
   impedance. The receiver pulldown supplies the low default for an open signal.
2. Establish valid supply rails, return continuity and all required readiness
   conditions. Keep ARM low while making PERMIT high.
3. Start only with a deliberate fresh ARM rising edge after permission is valid.
4. To stop, take PERMIT low. Take ARM low before allowing permission to return.
5. After a fault or reset, repeat the sequence; a previously held ARM high is
   not permission to restart.

This protocol presupposes control of, or detection of, reconnection. An
undetected individual ARM wire reconnection while its source remains high
violates it and can restart the circuit. That exact counterexample is retained
as `arm_reconnect_high`. A stuck-high command, broken return, common-cause
isolation failure or arbitrary contact bounce is not covered by the pulldowns.
If those faults must be tolerated, the interface needs additional hardware or
an encoded/acknowledged command scheme; the current candidate is insufficient.

## AUX and logic rails

Normal AUX operation is 14.25–15.75 V at the consuming devices. Proposed AUX
OV detection is nominally 16.5 V; it is a fault guard band above the normal
range. The comparator's second channel compares AUX × 100/(560+100) with
2.5 V. Its healthy-high output is ANDed with the existing fast AUX UV channel.
A low result clears RUN and directly removes final gate permission. Recovery
does not itself rearm the latch.

The [TLV3202 datasheet](https://www.ti.com/lit/ds/symlink/tlv3202.pdf)
identifies OUT2 on pin 7, IN2+ on pin 5 and IN2− on pin 6. Its push-pull outputs
must remain separate. The new
[SN74LVC1G08](https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf) combines them.
Both comparator channels remain powered by logic5. This avoids putting the
new fast path through the [TPS3890 MR input](https://www.ti.com/lit/ds/symlink/tps3890.pdf),
whose pulse recognition requirements would need separate timing qualification.

The producer or an independent limiter must keep AUX within the driver's
**18 V recommended operating maximum**, including ripple, overshoot and the
fault interval. The OV detector turns switching off; it does not remove voltage
from the driver supply pin. An AUX source whose OVP can reach 20.25 V is not
qualified by this change. The
[UCC27511A datasheet](https://www.ti.com/lit/gpn/ucc27511a) gives the recommended
4.5–18 V supply range. Other consumers also need their own voltage-rating check.

## Conditional static calculation

The Rust calculation in `corners.rs` uses:

- Divider and series resistance deviation bounded to ±1% total, not just the
  initial tolerance printed on an unselected resistor.
- LM4040A25I industrial-temperature reference: 19 mV full-temperature allowance
  at 100 µA, plus 1 mV for current variation over 80 µA–1 mA. See
  [LM4040 §6.8](https://www.ti.com/lit/ds/symlink/lm4040.pdf).
- TLV3202 offset allowance of 6 mV and input bias allowance of 5 nA per input,
  using their specified conditions. The offset specification's common-mode
  condition is VCC/2; extending it to every actual operating point needs review.

These assumptions produce 16.049833–16.961738 V. The lower result is about
0.300 V above the normal AUX maximum; the upper result is about 1.038 V below
18 V. Those margins are not a transient clamp rating or a complete error budget.
Reference startup, actual common mode and supply dependence, hysteresis, noise,
layout leakage, resistor voltage coefficients and self-heating are not fully
bounded here. The comparator's typical hysteresis cannot be promoted into a
guaranteed noise margin. Its propagation-delay maximum at stated overdrive
cannot be applied to arbitrarily slow near-threshold crossings.

At logic5=4.75 V, a 10.1 kΩ reference bias resistor and 2.52 V reference give
about 220.77 µA after the modeled four comparator bias loads, above the reference's
80 µA minimum under the quoted conditions. This is a DC check, not startup proof.

Before hardware adoption, select exact passives and the actual supply and
command boundary; verify their static budgets, partial-power injection,
reconnection sequence, OV response and noise behavior. The existing nominal
simulation is evidence for the intended logic behavior only.

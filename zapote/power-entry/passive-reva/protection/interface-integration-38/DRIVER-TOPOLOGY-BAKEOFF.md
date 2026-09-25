# Rev38 PFC driver-inhibit topology bakeoff

**2026-09-24 — outcome: UNRESOLVED.** Three independent read-only approach
sketches and a separate `ce-pov` assessment found no replacement ready for
U4 electrical selection. This is a circuit-selection result, not an assembled
fault-response or product-safety verdict. The joined source still uses the
[UCC27624 ENA shunt](gate-enable-corners.md), whose worst-case OFF proof is
blocked by an unspecified internal pull-up current. Do not route U7 from any
of the sketches below.

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

Participation: three independent `gpt-6-sol` high candidates (one native,
two read-only CLI) and one fresh read-only `gpt-6-astra` high `ce-pov` judge.
No production files were changed by candidate or judge work. The CLI did
not provide a reliable per-candidate token-usage receipt, so no usage total
is claimed.

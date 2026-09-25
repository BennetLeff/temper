# Command crossing: conditional candidate

Luna proposed **ISO7740FDWR**, using three forward channels for ARM, PERMIT and
relay command. The parent retains it as an evaluation candidate, with corrected
supply-domain reasoning. The existing SELV interlock remains the proposed
PERMIT authority; a sequencing coordinator must own ARM and relay command.
That coordinator and its sensing/readiness inputs are not implemented here.

The device supports separate supply domains and level translation; the F
variant defaults low under the specified input-loss conditions. ISO7740 has
four forward channels, with EN2 controlling outputs. Its output state is not
guaranteed when the output supply is absent. Its 5 V output table specifies
VOH relative to VCCO and a 0.4 V maximum VOL at the stated 4 mA test load.
[TI ISO774x Rev K, §§4, 5.9–5.11, 7.4](https://www.ti.com/lit/ds/symlink/iso7740.pdf).

Proposed evaluation connections:

| Side | Supply/return | Signals |
|---|---|---|
| Input | Existing SELV 3.3 V / SELV ground | Interlock PERMIT and coordinator ARM/relay commands; local source-input pulldowns |
| Output | HOT logic5 / control_gnd | Existing raw hot_arm/hot_permit and relay_ctrl inputs |

Keep revision 11's HOT receiver pulldowns and Ioff buffers. Retain the relay
driver's gate pulldown. Ground the unused isolator input in its own domain.
Keep the two grounds physically separate. Barrier dimensions, working-voltage
and system insulation requirements still need layout/application review.

Luna suggested one isolator, two bypass capacitors and three input pulldowns:
**six estimated additions** before connector, qualification or feedback logic.
This is not a compiled 142-part revision. Isolation power consumption must be
added to the supply budget, and the existing 75 mA rail budgets cannot silently
be treated as spare capacity.

## Distinct contracts on each side

The existing requirement for a high of at least 4 V describes a HOT receiver
input. It does not require a SELV 3.3 V coordinator to produce 4 V. The isolator
can translate between the two domains. Check the actual coordinator/interlock
output specifications against the isolator's input thresholds and input supply.
Never apply the HOT 0–5.5 V input allowance to a 3.3 V isolator input pin.

The literal HOT low requirement of 0.3 V also needs reconciliation: the quoted
isolator output table permits 0.4 V at its specified test load. That value can
still be a logical low for the downstream Schmitt buffer, but it does not by
itself prove the stricter 0.3 V contract at the actual load. Qualify that load or
explicitly revise the contract with the full leakage/threshold budget.

## States and uncovered transitions

| Condition | Interpretation |
|---|---|
| Both domains valid | Output follows the command; valid levels and loading must be checked |
| Input power/signal lost, output domain valid | Default-low behavior is available under datasheet conditions |
| Output supply absent | Do not credit a driven low; qualify receiver bias, leakage and any injection |
| HOT supply returns while SELV ARM is high | Output may acquire high and create an ARM edge; isolation does not prove safe rearm |
| ARM conductor reconnects while its source is high | Same intent ambiguity demonstrated in revision 11 |

Tying EN2 to rails_ok or clear_ok can merely move the unwanted edge to the
enable transition. A local low-before-arm qualifier or an explicit handshake
needs its own design and fault scope. No readiness feedback is assumed to
exist merely because the parent named it. If feedback is needed, reconsider
channel direction/count before choosing the isolator variant.

Decisive next tests are powered/unpowered input defaults and injection; valid
PERMIT/ARM sequencing; and held-high ARM across HOT rail return and individual
wire reconnection. Directly connecting SELV ground to HOT through the existing
Ioff buffers is rejected as an alternative: Ioff is not galvanic isolation.

Local basis: `zapote/interlock/INTERFACES.md` and revision 11's
`INTERFACE-CONTRACT.md`. Their timing and voltage requirements are distinct;
the interlock's falling-edge RESET_N is not the PFC's rising-edge ARM.

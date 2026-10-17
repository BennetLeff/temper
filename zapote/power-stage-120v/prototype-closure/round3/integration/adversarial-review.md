# Required fault behavior for the round3 proposal

This is a design review and acceptance checklist. No row records a physical
pass. Design packets must name the actual circuit path; unresolved entries
remain implementation or qualification work.

| Challenge | Required behavior and evidence |
| --- | --- |
| Contactors open at cold start | Upstream auxiliary power boots the independent supervisor. A local pod START edge can request precharge while the cooking controller is still unpowered. RESET is a separate input that cannot start. The cooking controller boots from native PS1 only after bypass; IRM20-15 is not backfed through J4.1. |
| HOT5 absent before charging | Gates remain inhibited. Cold-state qualification recognizes the downstream fault channel is not ready; independent input/thermal/timeout protections remain active. RUN can never ignore the same fault. |
| MCU outputs boot high, crash, stop clock, or reset repeatedly | Hardware energy permission defaults false; a stationary output cannot maintain a valid watchdog handshake. Coil power and gate permission both disappear without software cleanup. A restart is explicit, never an automatic continuation of heat. |
| One main contactor welds or its coil drive sticks on | The other series contactor opens both conductors. The welded unit is detected before subsequent permission. Do not call two coil pins driven by one failing transistor independent. |
| Both main contactors weld | Gate inhibit and energy absorber do not remove upstream mains. Latch fault, forbid reset, and retain a manual upstream disconnection/service procedure. Upstream fuse clears only faults within demonstrated coordination, not arbitrary overloads. |
| Mirror feedback reports closed/open incorrectly | Closed NC mirror feedback is usable only within the selected manufacturer's certified relationship. **Open NC feedback is not proof that the main NO contacts closed.** Select excitation voltage/current from the auxiliary-contact specifications, rather than assuming a bare 3.3 V pullup is adequate. Check wiring plausibility and add electrical evidence where closure is required. |
| Bypass contact welded before start | Do not close the main path into discharged capacitors. Pre-enable feedback diagnostics must catch this or the architecture needs another inrush-limiting means. |
| Bypass coil open or bypass main contact fails to close | Do not enable heat through the resistor. A short bounded timeout de-energizes both mains contactors; electrical bypass proof cannot rely only on coil command or NC feedback opening. |
| Precharge resistor open or short | Open prevents successful downstream qualification; short bypasses inrush control and must be detected by a defined continuity/impedance test or remain a stated single-fault limitation. Two parallel resistors do not create redundant inrush protection against one short. |
| Brownout or rapid reclose | Drop permission; enforce a new sequence after power restoration. Thermal retry permission survives resets or defaults to locked out. A warm resistor cannot be assumed cool because the MCU rebooted. |
| Reversed L/N or missing PE | Open both current-carrying conductors; keep PE unswitched and unfused. A line-only fuse does not make reverse-wired neutral safe. Both sides of the fixed wiring remain treated as hazardous. PE monitoring, if used, does not replace a verified protective bond. |
| Bus-channel supply loss/saturation or broken sense lead | A zero or plausible stuck value cannot grant energy permission or prove discharge. Use independent validity/rail and plausibility checks. Native19 AMC1311 has approximately 240 V nominal linear bus range and depends on HOT5. |
| Gate shutdown at worst tank phase | Separate removal of new mains energy from redistribution of energy already in bus/tank. Validate actual absorber current, response, SOA, connection inductance and energy—not just a contactor opening time. |
| A power switch is already shorted | Gate disable cannot interrupt that device. A demonstrated current/energy path and upstream protective coordination are needed; generic TVS peak-power and fuse I²t values do not establish survival. |
| Catch diode/fuse open, diode/capacitor short or bleed open | Identify the resulting unavailable receiver, added bus bulk, short path or retained-energy state. Startup receiver checks and separate catch sensing are required; qualified local D3 backup and DC fuse coordination remain open. The catcher is not a sustained braking load. |
| Filter + controller create negative input impedance | Reject direct constant-power compensation through rectified-bus valleys. Verify the selected conductance/current-limited control law, update rates, saturation, slew and burst behavior in the coupled model and on the first unit. |
| Current allocation includes auxiliary loads | The 15 A input limit applies at the fixed inlet and includes controller, fan, contactor, losses and heating. A power-board-only current sensor is insufficient without a conservative accounted margin or whole-inlet sensing. |
| Protective cover removed/service cable unplugged | Hazardous terminals and bus/tank test contacts remain guarded. Cover interlock is supplemental; unplug, lockout and independently verify stored-energy absence before access. |

## Digital checks before implementing a new PCB

1. Reconcile exact net names, terminal numbers, asserted levels, reference domains,
   supply directions, isolation barriers and current paths in the three design
   packets. Resolve contradictory thresholds or timing as open decisions, never
   by silently selecting whichever document was read last.
2. Exercise the supervisor model against every row above with actual transition
   guards, including asynchronous failures between state transitions. Tests of
   an ideal switch or assumed signal do not qualify the physical detector.
3. Couple startup, bypass failure, normal modulation, abrupt stop and reclose to
   the line/filter/rectifier model. Repeat with independent component tolerances
   and deliberately failed parts. Bound energy using simultaneous state values.
4. Compile the actual changed electrical source and audit connectivity before
   projecting a native PCB. Preserve native19 as the comparison article. New
   sensing/dump conductors require layout, insulation and parasitic review.

## Physical work that digital checks cannot close

Coil/pan impedance and actual initial states; selected contactor bounce/release
and welded-contact behavior; resistor pulse/thermal mounting; input source and
prospective fault current; raw gate/current/bus/tank captures; sensor transfer
and failure behavior; insulation/PE/leakage; installed thermal/airflow and EMI;
touch/service access and strain relief. These require the selected parts,
fixtures, qualified station and first article, before completing sibling units.

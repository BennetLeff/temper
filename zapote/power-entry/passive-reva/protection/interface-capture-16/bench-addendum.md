# Revision16 additions to the revision15 bench worksheet

No bench measurements were performed. Keep all revision15 acceptance criteria
and add the following before claiming electrical acceptance:

- Record exact C3/C4 part numbers, effective min/max capacitance over voltage,
  temperature and aging, C4 ESR and physical position. Demonstrate the bulk
  floor and10:1 ratio against the **maximum total** converter-input ceramic
  capacitance. Record total downstream maximum≤300uF and C3 minimum≥1.35uF.
- Repeat startup and fault-step testing for the1.5uF gate network and220uF bulk
  target. Capture Vraw, Vprotected, Vgate, Vsense, timer, load current and case
  temperature from fault onset. Test source impedance and rise-time corners,
  partially charged output, repeat faults and hot-case SOA. A static clamp
  calculation is not the required less-than18V peak measurement.
- Hold relay/PWM off through startup. Demonstrate actual current stays within
  the applicable foldback capability until the output has exited that region.
  The129.700mA operating-plus-ramp screen cannot be reused below3V.
- R3/R5 “hardware trip/stop” means driver/PFC authorization is removed. Do not
  require /SHDN to follow PERMIT: that would remove HOT decoder power.
  Test the separate service reset with at least120ms low and measured release
  slew, then require a new protocol session. AUX restoration alone must never
  grant RUN. FLT/ENOUT remain observations with no unqualified pullup loading.
- For R4/R6, record actual HCS74 setup/hold, clear recovery, power-on clear,
  pulse level/width and mixed-voltage isolator behavior.1us is a stimulus,
  not a demonstrated electrical guarantee. Observe the HOT clear state before
  issuing a source rearm pulse, using a proven bound or explicit acknowledgement
  implemented by the future producer. No such acknowledgement exists in this
  isolated schematic.

The source/reset/watchdog/decoder and existing disable circuit interfaces are
required participants in these tests. Their omitted implementation cannot be
substituted by a constant logic-high source when testing fault coverage.

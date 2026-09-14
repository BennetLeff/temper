# Temperature supervision and cooling fault contract

No protective behavior is implemented by this study.  The following values are
candidate integration limits for the firmware and hardware owners.

Under the legacy 40 W allowance and assumed whole-bridge
`RθJC=1.25 °C/W`, the series screen would require a case sensor to trip below
`125 − 40×1.25 = 75 °C`, less sensor error and shutdown overshoot.  With a
2 K error and 3 K overshoot, that screen gives at most **70 °C**.
This is not an established trip setting: the assumed aggregate thermal
resistance, sensor error and overshoot still require validation. The recovered
datasheet's device resistance does not establish the aggregate bridge network.
The
PCB sensor must trip below `110 °C` less its own error and overshoot; the
baseline modeled 107.86 °C peak leaves only 2.14 K, so no useful PCB trip
window is established for that assembly.

The supervision contract shall:

1. monitor each fan tach independently and latch a heating inhibit on a missing
   or implausible tach signal;
2. detect a blocked duct or recirculation condition that leaves the tach
   spinning (tach is not a thermal proof);
3. place a case sensor at the bridge/spreader datum and a PCB sensor at the
   hottest modeled neck, with documented lag and calibration error;
4. test loss of each installed fan, total fan loss, blocked inlet, high inlet air and a
   disconnected sensor as separate faults; and
5. establish restart only after inspection and a latched fault clear.

The trip time and shutdown overshoot must come from a transient model or test.
No time-to-trip number is invented here.  If the measured or modeled normal
temperature leaves no nonempty window below the engineering ceiling, the
assembly is inadequate and must be redesigned or operated at a lower declared
power with a new product requirement.

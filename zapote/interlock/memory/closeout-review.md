# Interlock circuit review closeout

Review date: 2026-09-11

Scope: read-only review of `elec/src/interlock_unit.ato`,
`zapote/interlock/MODEL.md`, `zapote/interlock/INTERFACES.md`, and the
standalone interlock plan. This records circuit and datasheet findings only;
it does not claim native KiCad, ERC, DRC, powered-board, or whole-chain
acceptance.

Verified findings:

- The standalone flip-flop definition uses the manufacturer-correct map:
  `CLK=1`, `D=2`, `QBAR=3`, `GND=4`, `Q=5`, `CLR_N=6`, `PRE_N=7`, `VCC=8`.
  The earlier plain-text Q/QBAR mapping was wrong and must not be reused.
- The standalone TPS3823 definition uses `RESET_N=1`, `GND=2`, `MR_N=3`,
  `WDI=4`, `VDD=5`. The shared legacy component definition has RESET/GND
  reversed; this review does not reconcile that donor.
- Seven active-high fault inputs are locally pulled up, inverted, and fed as
  healthy states to the eight-input NAND. The eighth NAND input is the
  `WDT_RESET_N` AND `SENSOR_LIVE` common-good signal. NAND output inversion
  drives `CLR_N`, so any fault clears permission asynchronously.
- With `D` and `PRE_N` high, releasing a fault only releases asynchronous
  clear. It cannot set Q. A fresh falling `RESET_N` request creates the
  inverted positive CLK edge needed to set permission. A held request has no
  second edge after fault recovery, so it cannot autorestart the heater.
- TPS3823 `MR_N` is tied high intentionally. WDI has a 1 kΩ pulldown in the
  current source. TI Rev O says a negative WDI transition retriggers the
  watchdog and recommends 1 kΩ to ground because high impedance causes
  internally generated pulses that prevent reset. The specified TPS3823
  watchdog timeout is 0.9–2.5 s (1.6 s typical); reset delay is 120–300 ms
  (200 ms typical).
- `SENSOR_LIVE` is correctly modeled as an independent active-high input with
  a receiver pulldown. Its qualified producer remains an integration
  obligation; existing sensor units are not evidence that this producer
  exists.

Electrical bounds checked against the selected supplies:

- The 3.135–3.465 V rail is within SN74LVC14A (1.65–3.6 V),
  SN74LVC1G08 (1.65–5.5 V), SN74LVC1G74 (1.65–5.5 V), CD74HC30 (2–6 V),
  and TPS3823 (1.1–5.5 V) operating ranges.
- A 10 kΩ +1% fault pullup at the low rail with 20 µA leakage leaves
  `3.135 - 10.1k * 20µA = 2.933 V`, above the SN74LVC14A positive threshold
  maximum listed for the relevant supply range. This is a conditional
  open-wire margin, not proof against arbitrary cable capacitance,
  contamination, remote clamps, or power sequencing.
- The 1 kΩ WDI pulldown draws 3.135–3.465 mA while WDI is high. The host
  driver must support that load.

Remaining qualification boundary:

CD74HC30's guaranteed VIH table is given at VCC=2 V, 4.5 V, and 6 V; it does
not provide a dedicated 3.3 V VIH row. Therefore LVC14A-to-HC30 compatibility
at 3.135–3.465 V is plausible from the low input load and strong LVC output,
but is not a direct 3.3 V datasheet guarantee. Do not derive it by applying
the HC30 2 V row to a 3.3 V circuit. Resolve by a qualified interface
measurement or a NAND with an explicit 3.3 V VIH guarantee.

Remote push-pull fault outputs are not power-off isolation. A receiver pullup
can source up to about 346.5 µA into an unpowered remote output; source-board
backfeed and clamp behavior remain integration qualification items. No
startup-ramp, brownout-ramp, metastability, propagation-latency, or powered
whole-chain result is claimed here.

Primary sources read on 2026-09-11:

- TI SN74LVC14A Rev AC: https://www.ti.com/lit/ds/symlink/sn74lvc14a.pdf
- TI CD74HC30 Rev E: https://www.ti.com/lit/ds/symlink/cd74hc30.pdf
- TI SN74LVC1G08: https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf
- TI SN74LVC1G74 Rev G: https://www.ti.com/lit/ds/symlink/sn74lvc1g74.pdf
- TI TPS3823 Rev O: https://www.ti.com/lit/gpn/TPS3823

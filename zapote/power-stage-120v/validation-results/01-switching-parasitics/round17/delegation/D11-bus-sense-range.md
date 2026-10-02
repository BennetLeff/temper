# D-11: bus-voltage sense range and receiver (AMC1311B)

**Read [README.md](README.md) first (ground rules, board facts).**
Power-stage task 06 follow-up; indexed here with the other delegated work.

## Why it matters

D-10 ([`validation-results/06-controller-interface/README.md`](../../../06-controller-interface/README.md),
"AMC1311B" section) found that the isolated bus-voltage sense U4
(AMC1311BDWVR) leaves its specified linear input range (2 V, TI SBAS786C
§7.9/§8.3.3) at about **240 V bus** (divider R26–R29 = 1.88 MΩ over
R30 = 15.8 kΩ; corners 237.4–242.6 V), below the 280 V OVP level. Its
differential output (J4.11/J4.12) also has no differential receiver on any
counterpart: the root controller's `V_BUS_SENSE` (U27.38, GPIO2) is
single-ended and already driven. Bus OVP itself is the separate comparator
U7 and is **not** affected; this is the controller's measurement path.

## Task

1. **Required range:** from `docs/hardware/power-section-120v/POWER-SECTION.md`
   and the firmware (`firmware/`, read-only), establish what the controller
   uses the bus measurement for (control loop, power limit, OVP backup,
   telemetry) and so the range and accuracy it needs: up to 280 V? some
   overrange margin? accuracy at 170/198 V?
2. **Divider options:** compute R26–R30 values that keep the required maximum
   bus inside 2 V with margin, using E96/E192 values and the existing
   resistor families' voltage and power ratings (check the per-resistor
   voltage across the 1.88 MΩ string at 280 V and at OVP + transient).
   Report the resolution and accuracy cost at 170 V (smaller VIN), including
   the AMC1311B's offset, gain error and input bias current
   (cite SBAS786C pages), and resistor tolerance and tempco.
3. **Receiver:** specify a differential-to-single-ended stage (or a
   differential ADC input) for the controller side that meets the
   AMC1311B's output common mode (1.39–1.49 V) and load requirements and
   maps the required range onto the ESP32 ADC's usable input range (cite
   Espressif's datasheet/ADC characteristics; note ESP32 ADC nonlinearity
   near the rails). Say where it should physically live (power board vs
   controller), given J4's pinout.
4. **Overrange behaviour:** what the AMC1311B output does above 2 V (cite
   the clipping/fail-safe behaviour) and what the firmware must do with it.

## Deliverable

`round17/delegation/out-D11/README.md`: one-line recommendation (divider
values and receiver topology), the range/accuracy table at 170 / 198 / 240 /
280 V for current vs proposed, the per-resistor voltage and power check, and
a committed script (`bus_sense.py`) with its output. Proposals only: do not
edit the board, netlist or firmware.

## Acceptance

Every number traces to the netlist/BOM, a cited datasheet page or the
script; accuracy figures are stacked worst cases or labelled typical; the
recommendation states what the owner must decide (e.g. accuracy at 170 V vs
range to 280 V).

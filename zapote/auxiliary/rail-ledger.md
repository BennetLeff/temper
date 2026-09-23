# Auxiliary rail ledger — U1 in progress

Source snapshot: `06d9070c3` (Rev38 candidate). This is an inventory, not a selected supply or electrical acceptance. A numeric maximum is recorded only when the linked source provides one.

| Rail and return | Known consumers or branch | Current evidence | Missing input |
| --- | --- | --- | --- |
| `AUX_PROTECTED` / `HOT0` | UCC28180, UCC27624, protected gate path, relay coil, direct pull/sense branches, logic5 converter | Rev38 `AUX-WINDOW.md` enumerates 41.50 mA of nominal-resistance passive/relay paths at 15.75 V before the controller, driver, converter and dynamic loads. The historical 75 mA allowance is explicitly withdrawn. | Guaranteed steady/pulse current, gate charge at real drive/frequency, buck VIN startup waveform, cable/source impedance, maximum local temperature. |
| `HOT_LOGIC5` / `HOT0` | AVR64DA32, isolators, comparators, latches, supervisor and bleeds | Rev38 `AUX-WINDOW.md` requires a separate worst-case tally. `HOT-RAILS.md` gives monitoring topology and provisional thresholds. | Producer and voltage envelope, all device loads, ramp/dropout sequence, detector behavior when logic5 is absent. |
| Historical `+15V` / SELV `GND` | Full-board power management, interlock, fan and discharge coil network | `elec/src/main.ato` connects historical `AuxSupply.power_out` to this rail and `power_out.gnd` to SELV ground; `elec/src/modules.ato` describes IRM-10-15 driven from an old half-bus. | Whether this assembly remains part of the new architecture, updated load total, isolation and producer input after the Rev38 AC/PFC change. |
| `+3V3` / SELV `GND` | MCU, sensing and interlock | Historical full-board source derives it from `+15V` through power management; standalone interlock accepts 3.135–3.465 V. | Integrated buck identity, loaded transient current and restart/reset behavior. |
| `+15V_LS` / `HV_RETURN` | Standalone inverter gate-drive J2 | Accepted digital gate-drive interface requires an externally isolated low-side 15 V input and uses bootstrap high-side supply. | Producer, insulation, load/pulse budget and gate-switching measurement. |
| Fan rail / return | Candidate 12 V fan(s) | Current bridge-cooling candidates use different fans and assemblies; historical `ThermalSystem` uses a 15 V feed and series dropper for an older fan. | Selected fan, stall/start current, supply routing and fault/tach interface. |

## Startup and return graph to resolve

The Rev38 PFC RUN path consumes `AUX_PROTECTED` and `HOT_LOGIC5`, so their production must not depend on PFC RUN. The historical SELV auxiliary source uses a half-bus and cannot be assumed to replace the HOT-referenced source. `HOT0`, SELV `GND` and inverter `HV_RETURN` are distinct until a reviewed circuit proves their relationship. A combined-source option must explicitly prove insulation and partial-power behavior.

## U1 open decisions and evidence requests

1. Confirm whether the scope is one combined unit or separately accepted HOT and SELV supplies.
2. Trace the exact Rev38 source-side supply connection upstream of precharge and its off-board AC/F1 branch.
3. Measure or bound actual startup and dropout currents at `AUX_PROTECTED` and `HOT_LOGIC5`; nominal resistor arithmetic is insufficient.
4. Obtain the fan and gate-drive supply selections before finalizing their load contributions.

Source anchors: `zapote/power-entry/passive-reva/protection/interface-integration-38/AUX-WINDOW.md`, `HOT-RAILS.md`, `STATUS.md`; `elec/src/main.ato`; `elec/src/modules.ato`; `zapote/gate-drive/INTERFACES.md`; `zapote/interlock/INTERFACES.md`.

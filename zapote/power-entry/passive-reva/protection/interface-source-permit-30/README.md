# Interface source permit fixture 30

This standalone Atopile fixture captures a low on any of three external SELV
health inputs in a `SN74HCS74PWR` latch. Three `SN74LVC1G08DBVR` gates
combine `SOURCE_RESET_GOOD`, `SOURCE_WATCHDOG_GOOD`, and
`INTERLOCK_PERMIT`, then gate that result with an independent SELV rail
supervisor before driving the latch's asynchronous clear. A deliberate rising
edge on `SOURCE_REARM_PULSE` may set the latch only after the health inputs and
rail qualification are high. The latched `PERMIT_TX` crosses ISO7741FDWR
channel B (pin 4 INB to pin 13 OUTB), yielding `HOT_PERMIT_RX`.

`TPS389001DSER` monitors SELV3V3 through a nominal 16 kOhm / 10 kOhm divider.
The TPS3890 adjustable reference is nominally 1.15 V, so the nominal falling
threshold is `1.15 V × (1 + 16 kOhm / 10 kOhm) = 2.99 V`. Its open-drain
`RESET` pin is pulled up to SELV3V3 and feeds the third AND gate. That gate
combines `SOURCE_HEALTH` and `SELV_RAIL_RESET_N`; its push-pull output drives
`/CLR1`. The 10 kOhm pulldown on `/CLR1` keeps clear asserted while the gate
output is unpowered. There is no electrical contention between the supervisor
and the gate: the supervisor only sinks its own pulled-up RESET node, while the
gate alone drives the latch clear input.

The TPS3890 is specified from 1.5 V supply. Its functional table holds RESET
low between its 0.8 V POR level and 1.5 V minimum supply; RESET is undefined
below 0.8 V. The AND gate's valid supply range starts at 1.65 V, and the
SN74HCS74's valid supply range starts at 2.0 V. Thus the supervisor asserts
RESET before both logic devices reach their operating ranges, while the
external clear pulldown covers the unpowered logic state. The supervisor's
100 nF CT capacitor gives about 107 ms nominal release delay by TI's equation
(`tPD(r) = CCT × VCT / ICT + 25 µs`). The final guaranteed delay depends on
the selected capacitor, tolerance, leakage, layout, and temperature; this
fixture does not claim a qualified minimum.

The named healthy-high inputs are fixture ports. No MCU GPIO, ESP32 EN net, or
watchdog timeout is treated as an implemented source reset producer. The
producer must assert low during source startup/reset and stay low until the
SELV rail is valid. Passive pulldowns make open/high-impedance inputs default
low; they do not detect a stuck-high producer or promise capture of arbitrarily
narrow analog glitches. The supervisor protects the latch against its
unknown/high power-up state, but does not implement or qualify the external
source reset producer.

## Pin and connectivity contract

The source declaration records the TI pin maps directly:

| Device | Pins | Function and connection |
| --- | --- | --- |
| U1/U2/U4 SN74LVC1G08DBVR | 1 A, 2 B, 3 GND, 4 Y, 5 VCC | First two gates combine external health; U4 combines `SOURCE_HEALTH` with supervisor RESET to generate `SOURCE_CLEAR_N` |
| U3 TPS389001DSER | 1 SENSE, 2 GND, 3 MR, 4 VDD, 5 CT, 6 RESET | SELV3V3 monitor, MR tied high, 100 nF delay capacitor, pulled-up open-drain RESET |
| U5 SN74HCS74PWR | 1 /CLR1, 2 D1, 3 CLK1, 4 /PRE1, 5 Q1, 6 /Q1, 7 GND, 8 /Q2, 9 Q2, 10 /PRE2, 11 CLK2, 12 D2, 13 /CLR2, 14 VCC | Source permit latch; unused half held cleared |
| U6 ISO7741FDWR | 1 VCC1, 2 GND1, 3 INA, 4 INB, 5 INC, 6 OUTD, 7 EN1, 8 GND1, 9 GND2, 10 EN2, 11 IND, 12 OUTC, 13 OUTB, 14 OUTA, 15 GND2, 16 VCC2 | SELV3V3 / SELV_GND; PERMIT_TX to HOT_PERMIT_RX; unused inputs tied low and outputs biased low |

The supervisor pin assignment follows TI's DSE package pin diagram. A local
six-pad land-pattern candidate is documented in
[footprint-review/README.md](footprint-review/README.md), but its `.pretty`
library is not yet bound into this fixture's KiCad project configuration.
Accordingly the source footprint remains
`TBD_REVIEW_ONLY:TI_DSE0006A_1.5x1.5mm`; do not treat the fixture as package
ready until the library binding is added and the compiled output is verified.

External inputs and permit-facing outputs have 10 kOhm pulldowns. RESET has a
10 kOhm pullup to SELV3V3; the 16 kOhm / 10 kOhm divider monitors the rail.
Each logic IC and the supervisor has local 100 nF bypass. Keep the two
isolator ground domains separate; place its bypass at each local supply-pin
pair. `netlist.tsv` and `audit.rs` check critical pin/node memberships against
Atopile's compiled KiCad `default.net`, including the supervisor pins,
divider, RESET pullup, third AND gate, and the latch clear pulldown.

## Fault behavior and limits

| Condition | Expected fixture response | Limitation |
| --- | --- | --- |
| Any health input opens or is driven low | U4 `/CLR1` goes low, Q1/PERMIT_TX clears | Input must remain low through gate propagation and valid HCS74 clear pulse width |
| SELV3V3 ramps from zero with all health inputs high | Supervisor RESET holds low; U4 drives `/CLR1` low before HCS74's 2.0 V minimum operating rail | Below supervisor VPOR (0.8 V), RESET itself is undefined; circuit makes no functional claim below valid rails |
| SELV3V3 falls below nominal 2.99 V threshold | Supervisor asserts RESET and asynchronous clear | Actual threshold includes supervisor and resistor tolerances; exact resistor tolerances remain unselected |
| SELV3V3 rises above threshold | RESET remains asserted through CT delay, then releases | 107 ms is nominal only; no qualified worst-case delay claim |
| Health later returns high | Permit remains cleared | Requires a fresh explicit rearm edge after health and rail qualification are valid |
| Source rearm input opens | It stays low | Input pulldown does not prove authorized pulse generation |
| SELV isolator input-side supply or signal is lost | ISO7741F output defaults low | HOT-side unpowered output is not guaranteed driven low |
| Source health producer or conductor is stuck high | No source fault is captured by that input | Producer diagnostics and conductor fault coverage are outside this fixture |

`startup_test.rs` starts Q1 in the adverse high state, ramps SELV3V3 while all
external health inputs remain high, checks asynchronous clear by the HCS74's
2.0 V operating point, then checks that supervisor release with re-arm held
high does not set Q1. Only a new low-to-high re-arm edge can set it. This is a
discrete logical contract for the topology, not an analog
simulation, physical measurement, or timing qualification.

No worst-case source-fault-to-driver-disable/current-cessation time is claimed.
The end-to-end bound must include fault detection, source clear pulse width,
gate delays, supervisor and latch behavior, isolator propagation/power-loss
response, HOT qualification, gate-driver disable, and power-switch turn-off.
No acknowledgement or physical source producer is implemented here.

TI primary references: [TPS3890 Rev A](https://www.ti.com/lit/ds/symlink/tps3890.pdf),
[SN74LVC1G08 Rev AA](https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf),
[SN74HCS74 Rev D](https://www.ti.com/lit/ds/symlink/sn74hcs74.pdf), and
[ISO774x Rev K](https://www.ti.com/lit/ds/symlink/iso7741.pdf). The ISO774xF
option specifies default-low outputs when input power or input signal is lost;
it does not establish a valid low while the output-side rail is absent.

## Reproduction

From this directory, compile using the offline cache available in this
worktree, then run the compiled-netlist contract and startup check:

```sh
UV_CACHE_DIR=/private/tmp/temper09-uv-cache \
UV_TOOL_DIR=/private/tmp/temper09-uv-tools \
/Users/bennet/.local/bin/uv tool run --offline \
  --python /opt/homebrew/opt/python@3.12/bin/python3.12 \
  --from atopile==0.2.69 ato --non-interactive build \
  elec/src/source_permit.ato:SourcePermitFixture
rustc --edition=2021 audit.rs -o /tmp/source-permit-audit
/tmp/source-permit-audit
rustc --edition=2021 startup_test.rs -o /tmp/source-permit-startup-test
/tmp/source-permit-startup-test
```

Atopile compilation validates the source and emits a netlist; the audit checks
the critical compiled connections and MPN identities. Generic resistor and
capacitor MPNs remain unselected. These checks do not qualify package,
electrical timing, board layout, or fault response.

# Rev38 isolation pin fixture

`elec/src/receiver_isolation.ato` is a **partial** Atopile fixture for the
selected AVR, eight assignments across two isolators, and two raw HOT reset
pulse channels in `hardware-topology.md`.
It is not `power_entry_integrated_38.ato` and does not pass U4. The source
GPIOs, HOT retained latches, one-shots, F2 detectors, watchdog, rail
supervisors, gate driver, PFC stage, and reservoir are not present here.
Many named signals terminate at fixture pins or pull resistors; they are not
real producers yet.

The ISO7742FDWR uses a distinct provisional footprint key because Atopile
0.2.69 merged the compiled part identity with ISO7741FDWR when both used the
same stock SOIC footprint key. The generated BOM and netlist now preserve
both MPNs. The provisional key is **not** a validated physical footprint.

From this directory:

```sh
uvx --from atopile==0.2.69 ato --non-interactive build elec/src/receiver_isolation.ato:ReceiverIsolation38
rustc --edition=2021 --test audit.rs -o /tmp/temper-rev38-isolation-audit
/tmp/temper-rev38-isolation-audit
rustc --edition=2021 audit.rs -o /tmp/temper-rev38-isolation-check
/tmp/temper-rev38-isolation-check
```

The `SN74LV221AQPWRQ1` uses separate non-retriggerable channels. AVR PA4/2
triggers the preparation-abort reset channel; PC3/9 triggers the permit-seen
history reset channel. Each has its own 10 kΩ/10 nF nominal timing pair and
an active-low raw output with a local pull-down. The TI data sheet gives
85–115 µs at 5 V over −40 to 125 °C for its **test** R/C and load. The
installed capacitor's tolerance, voltage/temperature behavior and load are
not included in that range. These raw pulses are not yet connected to
retained clear pins. The joined circuit must qualify them against live
fault/disarm conditions and prove that a trip during either pulse dominates
reset, including minimum captured pulse width.

The Rust audit checks compiled MPN identities, exact channel and receiver
pin membership, local low defaults, separate RC/pulse channels, separated
relay request/output, and SELV/HOT net separation. Its mutation tests remove
a low default or timing capacitor, short the relay request to the driver,
swap reverse feedback or reset channels, change the ISO7742F MPN, and add a
copper boundary crossing. It does not establish pin electrical levels,
fault-pulse capture, component timing, or fault-to-current cessation.

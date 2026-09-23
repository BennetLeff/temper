# Rev38 isolation pin fixture

`elec/src/receiver_isolation.ato` is a **partial** Atopile fixture for the
selected AVR, eight assignments across two isolators, two HOT reset pulse
channels, and one retained preparation-abort element in `hardware-topology.md`.
It is not `power_entry_integrated_38.ato` and does not pass U4. The source
GPIOs, remaining HOT retained latches, F2 detectors, watchdog, rail
supervisors, gate driver, PFC stage, and reservoir are not present here.
Many named signals terminate at fixture pins or pull resistors; they are not
real producers yet.

The ISO7742FDWR and the 10 nF timing capacitor use distinct provisional
footprint keys. Atopile 0.2.69 merged different MPNs when either pair used
the same stock footprint key: ISO7742F became ISO7741F, and the 10 nF
capacitors became 100 nF after a new bypass capacitor was added. The
generated BOM and netlist now preserve their separate MPNs. Neither
provisional key is a validated physical footprint.

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
an active-low raw output with a local pull-down. Channel 1's positive Q
output clocks the `SN74HCS74PWR` preparation-abort memory once with D=0;
its `PRE1_N` is driven by an SN74HCS21 two-stage AND of physical attempt,
source health, STOP, rail, F2-fault summary, and watchdog-health inputs.
`HOT_PREP_TRIP_OK` has a local pull-down, so the partial fixture defaults to
aborted. A qualified low input after the clock edge asynchronously forces
Q high even while the one-shot output stays high. The receiver reads Q on
PC1/7. The complementary Q output is exposed as `HOT_PREP_ABORT_OK` with
a local pull-down, but the joined clear path does not yet consume it.
AVR PA6/4 exposes `HOT_ATTEMPT_VALID` with a local pull-down and enters
that fan-in so STOP or MCU reset is visible while `RECEIVER_ABORT_N` is
already low during preparation. The HOT watchdog, F2 summary, and rail
inputs still lack their actual producers; the SELV source-health and STOP
inputs still lack their source implementation. The gate's output is not an
end-to-end fault-capture proof.

The TI one-shot data sheet gives
85–115 µs at 5 V over −40 to 125 °C for its **test** R/C and load. The
installed capacitor's tolerance, voltage/temperature behavior and load are
not included in that range. The permit-history raw pulse is not connected
to a retained element. Neither pulse is connected to an asynchronous clear
pin. The joined circuit must produce the remaining fan-in inputs, qualify the history
reset against live fault/disarm conditions, and prove that a trip during
either pulse dominates reset, including minimum captured pulse width. Do
not connect the one-shot CLR_N to a live fault: a CLR_N rising transition
can itself trigger this part when A is low and B is high.

The Rust audit checks compiled MPN identities, exact channel and receiver
pin membership, local low defaults including PA6 and watchdog health,
separate RC/pulse channels, the retained abort preset/clock/readback and
six-input fan-in paths, separated
relay request/output, and SELV/HOT net separation. Its mutation tests remove
a low default or timing capacitor, miswire the abort preset, reset clock,
or F2 fault fan-in,
short the relay request to the driver,
swap reverse feedback or reset channels, change the ISO7742F MPN, and add a
copper boundary crossing. It does not establish pin electrical levels,
fault-pulse capture, component timing, or fault-to-current cessation.

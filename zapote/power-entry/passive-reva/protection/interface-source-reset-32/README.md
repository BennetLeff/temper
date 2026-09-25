# Source reset and watchdog producer, fixture 32

This standalone Atopile fixture supplies a physical external watchdog output
to `interface-source-permit-30` and documents a candidate ESP32-S3 reset-good
GPIO. It does not modify the PCB or claim complete capture of every ESP32-S3
CPU reset class.

## Implemented candidate path

`TPS3431SDRBR` is always enabled from SELV3V3. `SOURCE_VALIDATED_HEARTBEAT`
drives the Schmitt input of `SN74LVC1G17DBVR`; its push-pull output drives
WDI pin 6 through a separate node with a 100 kOhm pulldown. The ESP32 GPIO
input has a 100 kOhm pulldown. At 3.3 V this bias draws about 33 µA. At the
3.0 V test point, TI lists the buffer's positive-going threshold maximum as
1.92 V and Espressif lists GPIO VOH >= 0.8×VDD (2.4 V), measured at high
impedance, giving 0.48 V unloaded separation. The input threshold table does
not list 3.3 V, and Espressif does not specify VOH under the 33 µA bias load;
the full 3.0–3.6 V input-side margin remains open. Confirm the exact module's
loaded output across rail and temperature corners before sign-off. The WDI output node is driven
by the buffer, not the ESP GPIO. Its 100 kOhm pulldown contributes at most
33 µA at 3.3 V; TI guarantees buffer VOH >= VCC−0.1 V at 100 µA, while
TPS3431 WDI VIH is 0.8×VDD. Provided total WDI-node loading including input
leakage stays at or below 100 µA, both chips on the same SELV3V3 rail give
0.56 V static high-level margin at 3.3 V. The buffer DBV
pin map is pin 2 A, pin 3 GND, pin 4 Y, pin 5 VCC; pin 1 is NC.
WDO pin 7 and ENOUT pin 8 share the active-low open-drain
`SOURCE_WATCHDOG_GOOD` node and 10 kOhm SELV3V3 pullup. TI allows these two
open-drain outputs to be tied. A 1 nF C0G capacitor on CWD pin 2 gives 132.4
ms typical and 119.82–144.98 ms ideal-capacitor bounds; board capacitor
tolerance, leakage, temperature and other system delays are not included.
When a late/missing WDI edge occurs, WDO asserts low; a later valid WDI edge
can deassert WDO, so the fixture 30 asynchronous source latch must capture the
low and remain cleared until a distinct, deliberate re-arm edge.

The producer assumes the source latch in fixture 30. The local 10 kOhm
pulldown on `SOURCE_RESET_GOOD` biases an unpowered or high-impedance output
low. GPIO21 is a candidate only: ESP32-S3 datasheet table 2-1 shows it is not
a strap pin and it has no entry in the documented power-up GPIO-glitch list.
The actual module pin routing, VDDIO domain and pull-down strength must be
checked against the exact module/board before assigning this net.
This signal sees the 10 kOhm pulldown here and fixture 30's 10 kOhm pulldown
in parallel, loading a high output by about 0.66 mA at 3.3 V. Espressif only
specifies GPIO VOH under high-impedance load, so this GPIO's loaded high level
is not signed off here.

## Required firmware and reset contract

1. Configure every watchdog action that is relied on to reset the GPIO
   peripheral as a **core/system reset**, never CPU-only reset. ESP32-S3
   distinguishes these reset levels: CPU reset resets a CPU core; core reset
   also resets digital GPIO; system reset includes RTC.
2. Do not enable `gpio_hold_en`, RTC GPIO hold, or any peripheral/DMA/RMT
   source that can keep `SOURCE_RESET_GOOD` high or generate WDI edges during
   a CPU-only reset, reset loop, bootloader or application startup.
3. `SOURCE_RESET_GOOD` must be an ordinary non-strap output (GPIO21 candidate)
   with an external 10 kOhm pulldown. Firmware leaves it input/low through
   reset, boot, self-checks and session negotiation. It may become high only
   after the source is healthy and a new deliberate re-arm has been accepted.
4. WDI edges are software-generated only after accepting a complete,
   authenticated/validated peer frame in the currently re-armed session.
   No periodic free-running timer/DMA pulse is acceptable. After any reset,
   firmware must withhold WDI until fresh deliberate re-arm. This allows the
   external watchdog to time out even if the ESP32 restarts faster than its
   132 ms nominal timeout.
5. A reset or watchdog fault clears fixture 30's permit latch. Recovery of
   `SOURCE_RESET_GOOD`, WDO, peer traffic, or firmware state must not restore
   it. Only a new physical/authorized `SOURCE_REARM_PULSE` edge may set permit.
   The re-arm signal must not be synthesized automatically by boot code.

These requirements are a firmware/integration contract, not proved by this
passive Atopile circuit. In particular, the task requested coverage of all
internal CPU/watchdog resets with EN high. A CPU-only reset is a counterexample:
the ESP32-S3 datasheet says it resets only the selected CPU core and does not
say it resets digital GPIO. ESP-IDF also documents that `gpio_hold_en()` can
retain a pin through core/system watchdog reset. Thus a GPIO already high may
remain high across a CPU-only reset. If the application restarts WDI before
the external timeout, neither the reset-good input nor TPS3431 necessarily
changes, and source permit can remain high. EN/CHIP_PU is an external chip
reset input; it is not an observable pulse for internal CPU resets.

The required broad guarantee is therefore **rejected as not physically
proved** for arbitrary internal CPU resets. The smaller guarantee is
conditional: core/system reset that deconfigures GPIO, or a CPU reset followed
by WDI silence through the external timeout, will clear the downstream source
latch, provided the external latch/power rails remain valid and the input-low
pulse meets the latch clear timing. A CPU reset followed by automatic WDI
service before timeout violates the contract and is not detected. There is no
independent ESP32-S3 internal-reset output pin to wire into `SOURCE_RESET_GOOD`.

## Timing and fault limits

| Event | Candidate response | Bound / gap |
|---|---|---|
| Missing validated WDI edge | TPS3431 pulls `SOURCE_WATCHDOG_GOOD` low; fixture 30 asynchronously clears permit | 119.82–144.98 ms ideal 1 nF device range, excluding C tolerance, latch/isolation/driver delay |
| Core/system reset | GPIO21 is returned to reset configuration; board pulldown makes `SOURCE_RESET_GOOD` low | Full reset-to-low and latch capture timing must be measured/qualified |
| CPU-only reset | May leave digital GPIO state intact; WDI stops only if it is software-driven | Not captured if GPIO is retained high and WDI resumes before timeout |
| Source recovery | WDO may deassert after a good WDI edge, but fixture 30 latch remains off | Requires a fresh physical re-arm edge |
| SELV power ramp / unknown start | Fixture 30 TPS3890 supervisor and source latch own the rail ramp behavior | This fixture alone has no power-on latch; TPS3431 WDO is undefined below VPOR |
| GPIO or heartbeat stuck high/toggling | Not detected as a reset merely because CPU reset occurred | Requires independent safety monitor/protocol proving fresh accepted frames |
| Detection to current cessation | No system bound | Includes fixture 30, isolator, HOT receiver, driver and switch turn-off; no prototype measurement exists |

No assembled low-voltage prototype or bench capture exists. No component
footprint is bound for TPS3431 DRB0008A in this fixture; the source footprint
is deliberately `TBD_REVIEW_ONLY`.

## Verification

Offline Atopile compilation produces the pin-level KiCad netlist. `audit.rs`
checks TPS3431 and buffer power/ground, buffered WDI, CWD, shared open-drain
WDO/ENOUT, pullup, and reset-good pin membership. `fault_model.rs` reproduces both the conditional
capture sequence and the CPU-only reset counterexample. Both are discrete
contract checks, not analog simulation, silicon reset characterization, or a
latency qualification.

Reproduce the compiled and temporal checks from this directory:

```sh
UV_CACHE_DIR=/private/tmp/temper09-uv-cache \
UV_TOOL_DIR=/private/tmp/temper09-uv-tools \
/Users/bennet/.local/bin/uv tool run --offline \
  --python /opt/homebrew/opt/python@3.12/bin/python3.12 \
  --from atopile==0.2.69 ato --non-interactive build \
  elec/src/source_reset.ato:SourceResetProducer
rustc --edition=2021 audit.rs -o /tmp/source-reset32-audit
/tmp/source-reset32-audit
rustc --edition=2021 fault_model.rs -o /tmp/source-reset32-model
/tmp/source-reset32-model
```

## Primary references

- [ESP32-S3 Series Datasheet](https://documentation.espressif.com/esp32-s3_datasheet_en.pdf), reset levels and pin settings at reset.
- [ESP-IDF ESP32-S3 GPIO API](https://docs.espressif.com/projects/esp-idf/en/v5.0.4/esp32s3/api-reference/peripherals/gpio.html), pad hold across watchdog core/system reset.
- [ESP-IDF ESP32-S3 startup flow](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/startup.html), CPU and watchdog reset boot paths.
- [TI TPS3431 datasheet](https://www.ti.com/lit/ds/symlink/tps3431.pdf), WDI/WDO behavior and timeout equation/range.
- [TI SN74LVC1G17 datasheet](https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf), DBV pin map, Schmitt thresholds and buffered output VOH.

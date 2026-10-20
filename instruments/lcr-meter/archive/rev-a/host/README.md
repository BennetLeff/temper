# Temper LCR host

USB HID control and complex calibration for the revision-A AD5933/MCP2221A board.
This is prototype software. USB framing is based on Microchip DS20005565 section 3;
AD5933 register commands and tuning words follow the AD5933 revision-F data sheet.
No physical meter was available for hardware-in-loop testing. Successful tests
prove software calculations and selected protocol vectors, not instrument accuracy.

## Build

```
cargo build --release --locked
cargo test --locked
cargo clippy --all-targets --locked -- -D warnings
```

Use an explicit `CARGO_TARGET_DIR` if required by the enclosing Temper checkout.
`--no-default-features` builds the offline calibration/conversion functionality
without USB support. macOS uses HIDAPI/IOKit. Linux builds need a C compiler and
the development headers for libudev (default hidapi Linux backend); the MCP2221A
may already be claimed by the kernel I2C driver and require an appropriate udev
permission/driver configuration. Windows uses HIDAPI/Windows HID. These OS paths
must be checked on the actual host; only the development host was compiled here.
Some Linux MCP2221 driver configurations change GP2 to a GPIO input, disabling
the analog rail. Arrange driver ownership before use, then unplug/reconnect to
restore factory pin settings; do not run the kernel I2C driver and HID CLI
concurrently. The CLI only uses I2C commands and does not change pin functions.

The board uses factory MCP2221A firmware: do not reprogram its flash or change
GP2/USBCFG. Analog power is removed in USB suspend. Recalibrate after power,
temperature or fixture changes. USB is not isolated. Both measurement terminals
sit near 1.65 V relative to USB ground; neither is a ground terminal.

## Capture and calibrate

Fit exactly one range jumper while the meter is unplugged. Reconnect, allow the
board to settle, and use the same manually asserted range, fixture and unit IDs
for every capture. No physical range readback exists. Only isolated, externally
verified discharged components may be connected. No energized stage53 measurements.

From this directory, using the built `temper-lcr` binary on PATH:

```
temper-lcr list
temper-lcr capture --unit meter01 --fixture leads01 --range r20 --start 35000 --stop 60000 --points 51 --out open.json
```

Leave the fixture open for that capture. Then connect a measured, low-parasitic
10 ohm standard at the DUT contact plane and repeat the command with `--out a.json`.
Connect a measured 40 ohm standard and repeat with `--out b.json`. Substitute their
actual measured resistance values below. References must differ by at least 20%.
Never use an excited hard short as a reference on this board.

```
temper-lcr calibrate --open open.json --a a.json --ra 10 --b b.json --rb 40 --out cal.json
```

Connect the DUT, run the identical capture command with `--out dut.json`, then:

```
temper-lcr convert --cal cal.json --raw dut.json --out dut.csv
```

No output file is overwritten. Capture times and exact frequency words are saved;
frequency rounding follows the device's DDS. Calibration rejects mismatched
board/unit/fixture/range/clock/drive/PGA/settling/averaging/grid metadata. Physical
identity and switch placement remain operator responsibilities. There is no
temperature sensor reading or calibration expiry enforcement; repeat calibration
when conditions change and validate with an independent third reference.

## Ranges and limits

| ID | Selected feedback | Intended impedance | Frequency |
|---|---:|---:|---:|
| r20 | 20 ohm | 5–50 ohm | 1–100 kHz |
| r200 | 200 ohm | 50–500 ohm | 10–100 kHz |
| r2k | 2 kohm | 500 ohm–5 kohm | 10–100 kHz |
| r20k | 20 kohm | 5–50 kohm | 10–100 kHz |

These are design targets pending bench validation. 1kHz mode is experimental
because the 1024-point device DFT has a short record at the fixed 16MHz clock.
Every CSV point is labelled `prototype_unqualified`; outside-range and negative-R
results are flagged. The application refuses near-rail DFT-register components
and very weak corrected signals as a coarse sanity check. The AD5933 does not
expose raw ADC samples or a clipping flag: these checks CANNOT detect all analog
overload, distortion or oscillation. Verify waveforms at the board test points
before relying on results. Precision ESR or DC milliohm performance is not claimed.

## Calibration convention and qualification

The recorded complex sample is **real register minus i times imaginary register**.
The AD5933 data sheet pp19–20 gives impedance phase as raw DUT phase minus raw
resistor phase, including approximately -90 degrees for a capacitor. Conjugating
the device's result puts it into the standard admittance convention used here.
A manufacturer-convention regression checks a capacitor produces negative X.
This convention still needs a known physical capacitor/inductor check at bring-up.

At each frequency, open `o` and two loads fit the linear model
`d = o + k/(Z + zs)`; measurement computes `Z = k/(d-o) - zs`.
This removes fitted additive and series terms under a linear, repeatable fixture
model. It cannot remove current-dependent amplifier distortion, reference
parasitics, arbitrary lead motion or an inaccurate DUT model. Standards are
assumed resistive at the test frequency; a precision DC resistance value alone
does not qualify an RF standard. Third-reference validation and an external LCR
comparison are required before specifying accuracy or ESR floor.

The single selected range/drive is fixed to AD5933 range 4 (~0.198 Vpp unloaded),
PGA ×1 and an external 16 MHz clock. Hardware adds source impedance, so actual DUT
voltage varies with load. A sweep starts with a 300 ms settling interval for the
AC-rebias circuit, followed by 15 cycles (default) plus DFT time per reading.
There are 1–512 linear frequency points and 1–64 averages. USB/I2C/DFT waits are
bounded; ordinary errors attempt a power-down command and propagate failure.
After a forced interruption or host crash, unplug the board to stop excitation
before touching a range jumper or changing the fixture.
The software does not silently reuse synthetic data when no USB instrument exists.
The additional I2C address-NACK latch check follows the maintained Linux
[MCP2221 driver](https://github.com/torvalds/linux/blob/master/drivers/hid/hid-mcp2221.c),
including errors that may remain latched after the I2C engine returns to idle.

## Included executable

`bin/temper-lcr-macos-arm64` is the release executable built on the development
Mac. Run `./bin/temper-lcr-macos-arm64 --help` from this directory. The executable
is unsigned and has not been exercised against a physical meter. Rebuild from
the locked source for other operating systems or CPU architectures.

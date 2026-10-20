# Temper LCR Rev B host

This CLI operates the one-PCB TIDA-060029-based Rev B instrument over USB CDC on macOS/Linux. The included executable is macOS arm64. Rev A AD5933 software is preserved under `../archive/rev-a/host/` and is incompatible with this instrument.

The firmware and host have compiled and passed digital tests. **The instrument has not been built, electrically qualified or calibrated.** Numerical estimates are not an inherited TI accuracy claim. First verify supply rails, source amplitude, ADC common mode, timing and noise with bench equipment.

## Build

Rust 1.85+ and a POSIX host are required. Dependencies are locked in Cargo.lock.

```sh
CARGO_TARGET_DIR=/tmp/temper-lcr-host cargo test --locked
CARGO_TARGET_DIR=/tmp/temper-lcr-host cargo clippy --locked --all-targets -- -D warnings
CARGO_TARGET_DIR=/tmp/temper-lcr-host cargo build --locked --release
```

## Before connecting a DUT

Only test isolated, discharged parts or disconnected stage53 subassemblies. Remove external power and discharge/verify capacitors independently. The meter is not isolated from USB ground and does not support powered-circuit measurements. The 1 mΩ shunt is outside its useful range.

Power the board from its regulated external 5 V supply, flash `../firmware/bin/temper-lcr-rev-b.uf2` using BOOTSEL, then connect USB. Select **both** matched RG/RF jumpers with power off and record that selection in every command. Software cannot sense the jumpers. Use the 100 Ω range initially for the stage53 coil, 100 nF/0.5 µF resonant capacitors and 9 µF bus capacitor at 1 kHz. Typical target grid is `1000,35000,40000,50000,60000`. A 100 kΩ range includes nominal RF || 5 pF compensation; calibration still needs to determine actual parasitics.

Use `/dev/cu.usbmodem...` on macOS or `/dev/ttyACM...` on Linux. The serial baud setting is immaterial to USB throughput.

```sh
temper-lcr info /dev/cu.usbmodemXXXX
temper-lcr selftest /dev/cu.usbmodemXXXX
temper-lcr noise /dev/cu.usbmodemXXXX 100 fixture-1 1000,35000,40000,50000,60000 noise.json
```

`selftest` checks 256 samples of the ADC's A55A fixed pattern on both lanes. It tests the digital connection, not the analog circuitry. `noise` keeps the DDS DAC/accumulator asleep, saves raw data with `source_enabled=false`, and prints DC-removed RMS and the fitted tone amplitude at each requested frequency. RMS volts use nominal ±4.096 V ADC differential full scale. Check both open and short fixture conditions. This is a narrow-tone diagnostic plus broadband RMS, not a full spectrum analyzer. Source-off records are explicitly rejected by impedance analysis.

## Fixture calibration and measurement

Use a short and two independently known, low-inductance resistor standards measured at the same reference plane. For the 100 Ω range, 20 Ω and 100 Ω are useful starting values; enter their known values, not merely their markings. Their reactive parasitics must be negligible or separately characterized at each frequency. The current CLI accepts real resistor standards only. Keep the same unit, fixture identifier, manual range, wiring, frequencies and temperature. Each frequency receives its own bilinear three-standard correction; there is no interpolation or extrapolation.

```sh
temper-lcr capture /dev/cu.usbmodemXXXX 100 fixture-1 1000,35000,40000,50000,60000 short.json
# Replace the short with standard 1, then standard 2.
temper-lcr capture /dev/cu.usbmodemXXXX 100 fixture-1 1000,35000,40000,50000,60000 load20.json
temper-lcr capture /dev/cu.usbmodemXXXX 100 fixture-1 1000,35000,40000,50000,60000 load100.json
temper-lcr calibrate short.json load20.json 20.000 load100.json 100.000 calibration.json
# Connect a third, independent 47-ohm standard.
temper-lcr capture /dev/cu.usbmodemXXXX 100 fixture-1 1000,35000,40000,50000,60000 check47.json
temper-lcr validate check47.json calibration.json 47.000 1.0
# Connect the isolated DUT.
temper-lcr capture /dev/cu.usbmodemXXXX 100 fixture-1 1000,35000,40000,50000,60000 dut.json
temper-lcr analyze dut.json calibration.json
```

The example 1% validation threshold is a user acceptance criterion, **not established instrument accuracy**. Validate independent capacitive/inductive standards too before relying on reactance, ESR or Q. Repeat the short and standards after changing cables, jumpers or temperature. An open fixture is useful as an overload/leakage diagnostic; it is not used as a potentially saturated calibration standard. High-impedance/open DUTs and poor ranges can saturate the TIA before the ADC, so inspect analog waveforms during qualification.

The host fits DC+sin+cos to both simultaneous channels at the actual DDS tuning frequency, including fractional cycle counts. It computes `Z=(RF || CF) × channel_A/channel_B`, where A is DUT high minus low and B is low minus TIA output. Calibration solves `measured=(a×true+b)/(c×true+1)`. Capacitive reactance is negative; inductive reactance is positive. Reported R/L/C are the **series equivalent at that frequency**, not a full component model. Q is |X|/R for positive R.

A capture stores 16,384 simultaneous signed 16-bit pairs, with a CRC32 over the received little-endian packed words. Sampling is 1 MSPS divided by an integer 1–20; DDS MCLK is the same 120 MHz MCU clock divided by five (24 MHz). Low frequencies use a lower sample rate for sufficient cycles. Actual frequency quantization is included; absolute frequency accuracy still depends on the crystal.

Checks reject corrupted records, missing calibration points, identity/range/fixture mismatches, clipping (|code|≥32700), weak fitted amplitude (<16 codes), or large residuals (>5% of tone amplitude). These are screening thresholds and do not establish a calibrated noise floor. `analyze` emits diagnostics and returns nonzero for invalid measurements. Analog saturation that still looks sinusoidal can escape these digital checks.

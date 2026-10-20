# Temper LCR Rev C RP2040 firmware

Built target: bare RP2040, 12 MHz crystal, compatible 2 MiB W25Q16JV QSPI flash; Pico SDK 2.2.0, Arm GNU 14.2.rel1. Native USB CDC, no module or second PCB. Board uses external regulated 5 V power; USB VBUS is only sensed through a divider. GP25 is the status LED. BOOTSEL and SWD provide recovery.

This image belongs on the final Rev C PCB with one fixed, local 100 pF TIA feedback capacitor connected in all three ranges. The waveform transport is protocol 2 (on-device boxcar decimation, int32 sums; see below); the hardware/model identity is `C-local100p`. Host 0.5.0 rejects protocol-1 firmware, capture files and calibration files with explicit errors, and still rejects Rev B and the earlier `C` identity with per-range compensation, including their calibration files. Jumper position and physical board revision cannot be sensed automatically; flashing this image does not modify an older PCB.

## Build and flash

The packaged `bin/temper-lcr-rev-c.uf2` is a compiled firmware image. Hold BOOTSEL during reset, then copy it to the RP2040 RPI-RP2 drive. ELF is included for SWD debugging.

```sh
git clone --branch 2.2.0 https://github.com/raspberrypi/pico-sdk.git /tmp/pico-sdk
git -C /tmp/pico-sdk submodule update --init lib/tinyusb
export PICO_SDK_PATH=/tmp/pico-sdk
export PICO_TOOLCHAIN_PATH=/path/to/arm-gnu-toolchain-14.2.rel1-darwin-arm64-arm-none-eabi
./build.sh
```

SDK commit is pinned by build.sh to `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`; TinyUSB is `86ad6e56c1700e85f1c5678607a762cfe3aa2f47`. Build needs CMake, a host C/C++ compiler and Rust for UF2 conversion/verification. SDK pioasm assembles the PIO source. The UF2 utility implements the SDK's `boot/uf2.h` format and verifies the written payload and headers. It is not an analog simulation.

`src/boxcar.c` (deinterleave, accumulation, extremes and ring-overrun check) has no SDK dependency. build.sh also compiles it with the build host's C compiler and runs `test/test_boxcar.c`; to run that test alone:

```sh
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -Isrc test/test_boxcar.c src/boxcar.c -o /tmp/test_boxcar && /tmp/test_boxcar
```

## Wiring contract

| RP2040 GPIO | Function | IC physical pin |
|---|---|---|
| 2, 3 | ADC A/B data | ADS9224R 24 / 20 |
| 4, 5, 6 | ADC CS / SCLK / CONVST | 14 / 16 / 13 |
| 7, 8 | ADC SDI / PD-RST | 15 / 26 |
| 9, 10, 11 | DDS FSYNC / SCLK / SDATA | AD9833 8 / 7 / 6 |
| 12 | ADC READY | ADS9224R 25 |
| 13 | USB VBUS /2 sense | connector divider |
| 21 | 24 MHz CLK_GPOUT0 | AD9833 MCLK 5 via33 Ω |
| 25 | capture LED | board LED |

The system clock is 120 MHz. Division by five produces 24 MHz DDS MCLK, leaving frequency and short-half-cycle margin against the AD9833 25 MHz /16 ns limits. PIO starts a conversion every 120 cycles: the ADC always runs at 1 MSPS and the PIO clock divider is fixed at 1. All GPIO signals are 3.3 V.

## Acquisition timing

ADS9224R reset defaults are legacy SPI00, single data wire per ADC, 16-bit words. Two data wires are sampled in parallel; this is not a 32-clock single-wire transfer. Startup intentionally powers down the ADC for10 µs, then waits200 ms for its reference. Every startup and host selftest writes register5=2 and requires256 consecutive A55A results on each lane, then restores register5=0. A failure blocks acquisition.

CONVST rises at cycle 0 for 4 cycles (33.3 ns). READY is checked at cycle44 (366.7 ns), beyond315 ns worst-case READY plus input synchronization. Failure raises IRQ4 and halts, preventing timebase jitter. CS falls at cycle45 (375 ns); clocks startcycle49 (408.3 ns). Sixteen SCLK periods are each4 cycles (30 MHz), high/low16.7 ns. The input sample occurs on SCLK falling, following TI's ≥30 MHz recommendation; data GPIO input synchronizers are bypassed. CS rises two cycles after the last sampled edge. The next CONVST is cycle120. The diagram and a logic analyzer must confirm timing at the actual IC pins before relying on measurements.

PIO pushes one packed 32-bit word per conversion pair into DMA. A bounded count halts via IRQ0 after exactly DECIMATION × COUNT conversions, with no extra conversions. The PIO program is unchanged from protocol 1 (its assembled output is byte-identical); only its clock divider is now always 1. Data collection is a burst into RAM (at most 20 × 16,384 = 327,680 conversions, 0.33 s; 128 KiB of sums), followed by USB transfer; it is not continuous USB streaming.

## Boxcar decimation

Protocol 1 slowed the PIO clock by an integer N, so the ADC converted at 1 MSPS/N with no anti-alias filter: wideband noise and spurs from the several-MHz analog bandwidth aliased into the band, and N−1 of every N possible conversions were never taken. Protocol 2 always converts at 1 MSPS and sums N consecutive conversions per channel into one output sample (N = DECIMATION, 1–20). Record length and output rate are unchanged (COUNT outputs at 1 MSPS/N).

DMA writes each packed conversion into a 4096-word (16 KiB, 4.096 ms) RAM ring. Core 0 deinterleaves each word through a 256-entry nibble table in RAM, adds A and B to int32 accumulators, and stores both sums every N conversions. It also tracks the most negative and most positive single conversion on each channel for the whole capture, so one clipped conversion remains detectable after averaging. The ring wrap, deinterleave and accumulation run in `src/boxcar.c`; its hot loop is placed in SRAM.

A boxcar is a sinc-shaped low-pass filter with nulls at multiples of 1 MSPS/N; its gain at f, referenced to the window centre, is D(f) = sin(πfN/1 MHz)/(N·sin(πf/1 MHz)). With N = 20, a 51 kHz tone that undersampling folded exactly onto 1 kHz is attenuated by |D| = 0.0197 (−34 dB), and uncorrelated wideband noise RMS falls by √20 (13 dB). It is not a brick-wall filter: components close to multiples of the output rate are attenuated only by the sinc sidelobes. Both channels share the same window, delay and passband droop, so the A/B ratio is unaffected. Output k averages conversions kN…kN+N−1, whose centre is (kN + (N−1)/2) µs after the first conversion; the host fits at those times and divides each phasor by D(f) (≥0.983 at the ≥10 outputs/cycle the host requests).

Cycle budget at 120 MHz (120 system clocks per conversion): `tools/hot_loop_bound.rs` reads the disassembled ELF and bounds the compiled per-conversion loop at **88 clocks**, summing every loop instruction once with every branch charged as taken (Cortex-M0+ zero-wait-state timings; DMA bus-arbitration stalls are not modelled). Per-batch work (DMA count reads, PIO flag and timer polling) is a fixed cost per batch; because each batch consumes everything that has arrived, batches grow until the loop keeps pace, so sustained throughput needs only the per-conversion cost below 120. USB interrupts on core 0 are absorbed by the 4.096 ms ring. This design keeps the verified single-state-machine PIO timing; two lane-per-state-machine PIO programs would avoid the deinterleave but need lock-step state machines and two rings for no needed throughput.

Overrun is detected, not assumed away. While DMA runs, the newest four issued words are left unread so a word whose write is still in flight is never consumed. After each batch the firmware re-reads the DMA transfer count; if DMA could have issued word i + 4096 before word i was read, the capture fails with `ERR acquisition_overrun`. A READY fault, timeout, incomplete DMA, missing PIO end IRQ or RX FIFO stall fails with `ERR acquisition_timing`. Either error invalidates the capture and clears the selftest status. The firmware holds the DDS off outside capture, allows1000 ms or20 cycles settling (10 time constants of the 1 µF/100 kΩ source coupling), and shuts it off after acquisition. USB removal also disables the source.

## Protocol v2

ASCII commands end in LF. Responses are LF, without CR translation.

- `INFO` → `INFO 2 C-local100p UNIT_ID 120000000 24000000 120 16384 PASS|FAIL`
- `SELFTEST` → `SELFTEST PASS|FAIL`
- `OFF` → `OK`
- `CAPTURE WORD DECIMATION COUNT` → `DATA 2 WORD DECIMATION COUNT CRC32`
- `NOISE WORD DECIMATION COUNT` → `NOISE 2 WORD DECIMATION COUNT CRC32`

DATA/NOISE headers are followed immediately by 8 + 8 × COUNT payload bytes, then LF `END` LF. Bytes 0–7 are A min, A max, B min, B max: single-conversion extremes over the whole capture, little-endian int16. Each output sample follows as A sum then B sum, little-endian int32: the sum of DECIMATION consecutive signed 16-bit conversions (|sum| ≤ 20 × 32,768 = 655,360, 21 bits). CRC is IEEE reflected CRC32 over all payload bytes, including the extremes. NOISE keeps the DDS disabled throughout. Errors start `ERR`; acquisition errors require a new successful SELFTEST. Limits are 100 Hz–100 kHz, decimation 1–20, 256–16,384 output samples, at least 8 output samples/cycle and 10 cycles per burst. SELFTEST uses the same path with decimation 1: all 256 sums and all four extremes must equal A55A (−23,206) on both lanes.

Protocol 1 (raw packed 16-bit pairs, up to 32,768, at a PIO clock divided by N) is not implemented by this firmware.

## Verification status and first-board checks

`verification/` contains compiler output, assembled PIO, size, hash manifest, instruction-model checks (exact counts up to the 327,680-conversion maximum), the host-compiled boxcar test (`boxcar-test.txt`) and the static hot-loop cycle bound (`hot-loop.txt`). The host includes synthetic phase/calibration/CRC/decimation tests and reproduces the boxcar test's golden payload CRC. **No physical board has been tested.** Instruction-model checks and the static cycle bound do not prove GPIO propagation, metastability margin, real bus or interrupt latency, ADC/FDA settling, rail noise, DDS distortion or measurement accuracy. At first power-up, verify rails, common mode and DDS amplitude; scope CONVST/READY/CS/SCLK/data at 1 MSPS with a logic analyzer, including a full decimation-20 capture with USB connected to confirm 1 µs CONVST spacing throughout; confirm no `acquisition_overrun` at decimation 1 and 20; require fixed-pattern selftest; measure source-off noise; calibrate and validate independent standards using the host instructions.

Primary references: [ADS9224R SBAS876C](https://www.ti.com/lit/gpn/ads9224r), [AD9833 Rev G](https://www.analog.com/media/en/technical-documentation/data-sheets/AD9833.pdf), [RP2040 datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf), [Pico SDK2.2.0](https://github.com/raspberrypi/pico-sdk/tree/2.2.0).

The source coupling network is 1 µF into 100 kΩ (nominal100 ms time constant). Both source-on and source-off commands therefore wait at least1000 ms before acquisition. This nominal10τ delay is a design allowance, not measured transient performance. On the first board, scope DUT high/low and both ADC inputs through the transition and verify the DC transient has settled below the intended measurement error at the lowest frequency and worst load; increase the delay if needed.

The optional J6 UART0 header uses GPIO28/TX and GPIO29/RX (RP2040 pins40/41). UART stdio is disabled in the supplied firmware; USB CDC is the operational interface. The SDK UART defaults match the header for future diagnostics.

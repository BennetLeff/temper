# Temper LCR Rev B RP2040 firmware

Built target: bare RP2040, 12 MHz crystal, compatible 2 MiB W25Q16JV QSPI flash; Pico SDK 2.2.0, Arm GNU 14.2.rel1. Native USB CDC, no module or second PCB. Board uses external regulated 5 V power; USB VBUS is only sensed through a divider. GP25 is the status LED. BOOTSEL and SWD provide recovery.

## Build and flash

The packaged `bin/temper-lcr-rev-b.uf2` is a compiled firmware image. Hold BOOTSEL during reset, then copy it to the RP2040 RPI-RP2 drive. ELF is included for SWD debugging.

```sh
git clone --branch 2.2.0 https://github.com/raspberrypi/pico-sdk.git /tmp/pico-sdk
git -C /tmp/pico-sdk submodule update --init lib/tinyusb
export PICO_SDK_PATH=/tmp/pico-sdk
export PICO_TOOLCHAIN_PATH=/path/to/arm-gnu-toolchain-14.2.rel1-darwin-arm64-arm-none-eabi
./build.sh
```

SDK commit is pinned by build.sh to `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`; TinyUSB is `86ad6e56c1700e85f1c5678607a762cfe3aa2f47`. Build needs CMake, a host C++ compiler and Rust for UF2 conversion/verification. SDK pioasm assembles the PIO source. The UF2 utility implements the SDK's `boot/uf2.h` format and verifies the written payload and headers. It is not an analog simulation.

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

The system clock is 120 MHz. Division by five produces 24 MHz DDS MCLK, leaving frequency and short-half-cycle margin against the AD9833 25 MHz /16 ns limits. PIO samples every 120 cycles, giving 1 MSPS before an integer divider. All GPIO signals are 3.3 V.

## Acquisition timing

ADS9224R reset defaults are legacy SPI00, single data wire per ADC, 16-bit words. Two data wires are sampled in parallel; this is not a 32-clock single-wire transfer. Startup intentionally powers down the ADC for10 µs, then waits200 ms for its reference. Every startup and host selftest writes register5=2 and requires256 consecutive A55A results on each lane, then restores register5=0. A failure blocks acquisition.

At divider1, CONVST rises at cycle0 for4 cycles (33.3 ns). READY is checked at cycle44 (366.7 ns), beyond315 ns worst-case READY plus input synchronization. Failure raises IRQ4 and halts, preventing timebase jitter. CS falls at cycle45 (375 ns); clocks startcycle49 (408.3 ns). Sixteen SCLK periods are each4 cycles (30 MHz), high/low16.7 ns. The input sample occurs on SCLK falling, following TI's ≥30 MHz recommendation; data GPIO input synchronizers are bypassed. CS rises two cycles after the last sampled edge. The next CONVST is cycle120. The diagram and a logic analyzer must confirm timing at the actual IC pins before relying on measurements.

PIO pushes one packed32-bit word per sample pair into DMA. A bounded count halts viaIRQ0 after the requested number, with no extra conversions. READY faults, DMA incompletion, timeout or RX FIFO stalls invalidate the capture. Data collection is a burst into RAM (maximum32,768 pairs/128 KiB), followed by USB transfer; it is not continuous4 MB/s USB streaming. The firmware holds the DDS off outside capture, allows1000 ms or20 cycles settling (10 time constants of the 1 µF/100 kΩ source coupling), and shuts it off after acquisition. USB removal also disables the source.

## Protocol v1

ASCII commands end in LF. Responses are LF, without CR translation.

- `INFO` → `INFO 1 B UNIT_ID 120000000 24000000 120 32768 PASS|FAIL`
- `SELFTEST` → `SELFTEST PASS|FAIL`
- `OFF` → `OK`
- `CAPTURE WORD DIVIDER COUNT` → `DATA 1 WORD DIVIDER COUNT CRC32`
- `NOISE WORD DIVIDER COUNT` → `NOISE 1 WORD DIVIDER COUNT CRC32`

DATA/NOISE headers are followed immediately by COUNT little-endian32-bit words, then LF `END` LF. Within each word bits[31:0] are B15,A15,…,B0,A0. Both ADC words are signed two's complement. CRC is IEEE reflected CRC32 over the raw byte payload. NOISE keeps the DDS disabled throughout. Errors start`ERR`; acquisition errors require a new successful SELFTEST. Limits are100 Hz–100 kHz, divider1–20,256–32768 pairs, at least8 samples/cycle and10 cycles per burst.

## Verification status and first-board checks

`verification/` contains compiler output, assembled PIO, size, hash manifest and instruction-model checks. The host includes synthetic phase/calibration/CRC tests. **No physical board has been tested.** Instruction-model checks do not prove GPIO propagation, metastability margin, ADC/FDA settling, rail noise, DDS distortion or measurement accuracy. At first power-up, verify rails, common mode and DDS amplitude; scope CONVST/READY/CS/SCLK/data at1 MSPS; require fixed-pattern selftest; measure source-off noise; calibrate and validate independent standards using the host instructions.

Primary references: [ADS9224R SBAS876C](https://www.ti.com/lit/gpn/ads9224r), [AD9833 Rev G](https://www.analog.com/media/en/technical-documentation/data-sheets/AD9833.pdf), [RP2040 datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf), [Pico SDK2.2.0](https://github.com/raspberrypi/pico-sdk/tree/2.2.0).

The source coupling network is 1 µF into 100 kΩ (nominal100 ms time constant). Both source-on and source-off commands therefore wait at least1000 ms before acquisition. This nominal10τ delay is a design allowance, not measured transient performance. On the first board, scope DUT high/low and both ADC inputs through the transition and verify the DC transient has settled below the intended measurement error at the lowest frequency and worst load; increase the delay if needed.

The optional J6 UART0 header uses GPIO28/TX and GPIO29/RX (RP2040 pins40/41). UART stdio is disabled in the supplied firmware; USB CDC is the operational interface. The SDK UART defaults match the header for future diagnostics.

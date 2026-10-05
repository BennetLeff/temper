# Round5 target firmware implementation

**Inhibited bench targets, not a completed energized deployment.** This round
adds real peripheral code for STM32G071RBT6 and ESP32-S3, acquisition drivers and
fault tests. It does not close the whole target implementation workstream. The
STM32 startup and peripheral units compile to ARM Cortex-M0+ objects using the
official ST/ARM headers. A linked STM32 bench ELF and ESP-IDF v5.2.3 ESP32-S3 bench image now
build with the actual target compilers. Toolchains were downloaded into isolated
`/private/tmp` directories; no global installation was performed. Neither
board has been flashed. The existing round4 portable safety core is unchanged.

## What changed

`stm32/platform.c` implements the existing supervisor's exact pins from
`round4/supervisor/generated/pins.tsv`, including:

- HSI16 system clock; PA8 MCO supplies HSI16/2 (8 MHz) to ADS131M08. At OSR1024,
  actual nominal telemetry rate is **3906.25 samples/s**, not 4 kSPS or 32 kSPS.
- SPI1 PA4/5/6/7 at 4 MHz, CPOL0/CPHA1, 30-byte full-duplex frames. Hardware
  reset, register writes and readbacks initialize MODE=0x3110 and CLOCK=0xff0e.
  Input CRC follows the command/register payload; output CRC covers the first
  27 output bytes. These are deliberately different positions.
- PA0 EXTI falling-edge DRDY timestamping against a 1 MHz TIM2 counter; missed
  pending interrupts, bad status, clipping, CRC, duplicate sample, sample-gap
  and late-read conditions invalidate acquisition. Runtime ADC faults latch.
  No ADC data becomes valid merely because a transfer returned bytes.
- PA2/3 STM32 ADC calibration and long-acquisition-time raw NTC readings.
  Raw ADC counts are **not** classified as temperature/cold eligibility.
- PA9/10 USART1 at 115200 8N1; the existing CRC/sequence/freshness protocol is
  used in both directions. Fault status is emitted every 5 ms without a
  blocking full-frame transmit. UART parsing faults remove the received link.
- Actual coil, health, reset, proof and stop output pin writes; reset establishes
  low coil commands before GPIO output mode. MCU_RUN is removed first on fault.
  The portable sequencer is invoked at nominal 1 ms cadence. A stuck SPI wait
  is bounded; the external watchdog is fed only from the main loop after fresh
  acquisition, never from an unrelated free-running interrupt.
- Startup vector table and 128 KiB FLASH/36 KiB RAM linker script; a Makefile
  targeting the real ST part, not host stubs. SWD pins remain reserved.

The bench image deliberately has `commissioned=false`, invalid/unqualified
physical inputs and low MCU_HEALTHY. Thus the sequencer remains faulted and
cannot assert its coils or permission. Missing calibration/qualification is
visible in source rather than filled with optimistic boolean constants.

`esp32/` is a standalone ESP-IDF project for **proposed new carrier R5-CTRL-01**.
It does not change or borrow pins from the legacy Temper controller. The exact
module proposal is ESP32-S3-WROOM-1-N8 without PSRAM; GPIO35/36/37 cannot be
blindly transferred to an octal-PSRAM variant. The JSON pin contract records
module pad numbers, JCTRL directions, JFAST pins and reserved GPIOs.

The MCPWM driver allocates one 80 MHz timer and two operators. Both bridge legs
share that timer. The pair of generators for each leg uses hardware deadtime.
Configuration occurs while the timer is stopped and PWM request is low. The
bench image additionally disconnects the GPIO matrix and holds all four output
pads low; forcing a raw generator low is insufficient evidence of a low pad
through a downstream deadtime inverter. There is no API in this image that can
raise PWM_REQUEST. The 50 kHz/125 ns values are test setup parameters, not a
released frequency/deadtime choice.

**Live atomic phase changes are not implemented.** ESP-IDF's sequential writes
into compare shadows can straddle a timer boundary; calling them in sequence is
not a proof of atomic update. This driver does not present stop/restart as
continuous phase control. Active request is rejected, and the phase=1 endpoint
is rejected because its fall-at-period edge needs a different event topology.
A verified live transaction and endpoint treatment remain digital engineering.

## Acquisition and fast capture contracts

`common/acquisition.c` provides tested ADS131M08 CRC/status/sign/freshness checks,
volatile one-use POST records and a synchronized bus/catch correlation predicate.
The POST function requires a new nonzero serial, current boot nonce, cold/released
contacts, an explicit operator confirmation and resistance inside supplied
bounds. Invalid input invalidates the record; consumption never restores it.
The target image does **not** invent the boot-session admission/service protocol,
POST bounds or calibrated gains. This remains integration work.

`common/fast_capture.c` and `esp32/fast_spi.c` implement the receive side of a
concrete external four-channel logic-capture contract. SPI2 mode0 at 10 MHz
reads exactly 92 bytes; the frame's four periods, high times, rise positions and
four nonoverlap values must all come from a **single 80 MHz acquisition clock**.
The receiver checks version, flags, CRC32, contiguous snapshot sequence, source
age <=500 us and transaction duration <=200 us. A fault invalidates all channels
and latches. External physical rail/interlock/fault inputs are deliberately not
asserted by this packet. Snapshot sequence advances once per read transaction,
not once per switching cycle. Counter wrap is unsigned.

| Byte offset | Big-endian field |
|---|---|
| 0 | `TFC1` magic |
| 4 | version 1 |
| 5 | valid channel mask exactly 0x0f; other flags reserved/rejected |
| 6 | frame length 92 (u16) |
| 8 | snapshot sequence (u32) |
| 12 | clock frequency exactly 80000000 (u32) |
| 16 | common snapshot counter (u32), retained for diagnostics |
| 20 | age of oldest complete measured cycle in 80 MHz ticks (u32) |
| 24 | four periods (4 × u32) |
| 40 | four high times (4 × u32) |
| 56 | four rise positions relative to one common cycle origin (4 × u32) |
| 72 | four nonoverlap intervals, same order as existing bridge validator (4 × u32) |
| 88 | CRC32/ISO-HDLC over bytes 0..87 |

**The transmitting capture hardware/FPGA is not implemented.** The concrete
candidate agreed with the board owner is the official Lattice **iCE40HX8K-B-EVN**
breakout module (ICE40HX8K-CT256), with a separate common 80 MHz oscillator and
four level-qualified edge inputs, plus a separate AD7380-4
quad simultaneous 4 MSPS SAR path for tank voltage/current acquisition. This is
an ECO architecture, not a routed/synthesized design. The analog frontend,
isolation, anti-alias filter, module header/HDL/timing, external oscillator part
and input pin, clock tolerance budget and power sequencing are still missing.
The module's onboard 12 MHz clock is not treated as an automatically valid 80 MHz
source. Selecting the module avoids promising a new BGA FPGA PCB; it does not
replace FPGA implementation or timing checks. At 4 MSPS each analog sample is 250 ns apart;
that cannot by itself qualify a roughly 400 ns deadtime or prove ZVS. Independent
oscilloscope/probe measurements remain required. The slow ADS131M08 path is never
substituted for this fast capture.

## Verification and replay

From repository root:

```sh
CMSIS_DEVICE=/path/to/official/ST/Include \
CMSIS_CORE=/path/to/official/ARM/CMSIS/Core/Include \
  zapote/power-stage-120v/prototype-closure/round5/firmware/replay.sh
```

The replay always resets its status to INCOMPLETE before checking. It compiles
and executes new host tests with AddressSanitizer and UndefinedBehaviorSanitizer;
it checks the exact 64-pin STM32 authority and all 16 proposed ESP GPIOs. With
CMSIS paths, clang emits actual ARM EABI object files for platform/startup. It
reports `PASS_HOST_CHECKS_ONLY` rather than a target-release pass. No mocked
register or SDK headers are used. Compiler and source/header hashes are in
`evidence.json` and `source-inputs.sha256`.

New tests check the public CCITT and CRC32 check vectors, the different DIN/DOUT
CRC placements, all **240 single-bit ADS frame corruptions** and **736 single-bit
fast-frame corruptions**, clipping/status/freshness logic, duplicate timestamps,
counter wrap, one-use POST and open-catch correlation. Five unchanged round4
host executables also pass: power adapter, no-burst, state machine, PLL and
integration. Existing unrelated legacy warnings remain in their build log.

The actual linked builds used Arm GNU Toolchain 13.2.rel1 (13.2.1), official
ST/ARM CMSIS inputs, ESP-IDF v5.2.3 at commit
`c9763f62dd00c887a1a8fafe388db868a7e44069`, and its pinned Xtensa GCC 13.2.0.
The Arm archive matched its official SHA-256
`39c44f8af42695b7b871df42e346c09fee670ea8dfc11f17083e296ea2b0d279`.
Build receipts and inhibited ELF/bin artifacts are retained under the output
folder. A complete target build is:

```sh
cd zapote/power-stage-120v/prototype-closure/round5/firmware/stm32
make CMSIS_DEVICE=/path/to/ST/Include CMSIS_CORE=/path/to/CMSIS/Core/Include
# In a separate ESP-IDF v5.2 environment:
cd ../esp32
idf.py set-target esp32s3
idf.py build
```

Do not flash or energize on the strength of these commands. Both target builds passed. This establishes compile/link compatibility, not
peripheral execution or an energized target. The ESP bench loop reads capture
frames every 5 ms for diagnostics; that cadence does not meet the production
<=1 ms capture freshness requirement.

## Outstanding digital work, separate from physical qualification

1. Complete live atomic MCPWM phase commit and endpoint handling;
   compose the capture, line telemetry and characterized phase controller into
   `power_binding_t`. The current ESP project is a hardware-inhibited bench app.
2. Complete calibrated channel scaling, NTC conversion, mirror excitation tests,
   ADC injection/stuck-channel checks, crest-aware precharge/proof qualification,
   catch charge-history qualification and MCU independent health boot sequence.
   Wire fresh POST session/physical confirmation into STM32 admission. Merely
   setting `commissioned=true` would leave missing inputs; it is not a release.
3. Complete the proposed controller carrier and fast capture circuit/FPGA/analog
   path, or select a different explicitly verified architecture. The JSON pinmap
   is not evidence that an existing board already has those connections.
4. Complete STM32 flash/option-byte/BOR/watchdog settings and stack/timing
   analysis. The ARM/newlib and ESP SDK linked-build items are closed; no
   peripheral timing claim follows from their success.
5. Join the exact resulting targets, sensor delay/filter response and selected
   precharge/proof bounds into the coupled model, then review the entire revision.

Physical tests additionally include oscillator/timing accuracy, DMA/IRQ load,
clock/reset/power ramps, pin-level force/inhibit behavior, ADC calibration and
fault injection, real tank/pan waveforms and staged first-unit tests. No physical
result is asserted by this package.

## Primary references

- [TI ADS131M08 SBAS950B](https://www.ti.com/lit/ds/symlink/ads131m08.pdf), pp. 11,
  14, 29, 38–44, 51–56: clock, SPI mode, frame/CRC and register definitions.
- [ST official STM32G071 device header](https://github.com/STMicroelectronics/cmsis-device-g0/blob/master/Include/stm32g071xx.h)
  and [ST RCC low-level definitions](https://github.com/STMicroelectronics/stm32g0xx-hal-driver/blob/master/Inc/stm32g0xx_ll_rcc.h):
  exact register names and MCO HSI16/div2 selection. Downloaded headers are local
  compiler inputs, not redistributed as authored firmware.
- [Espressif ESP-IDF v5.2 MCPWM](https://docs.espressif.com/projects/esp-idf/en/v5.2/esp32s3/api-reference/peripherals/mcpwm.html):
  common timer/operators, compare update semantics, deadtime and force actions.
- [ESP32-S3-WROOM-1 datasheet](https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.html):
  module pad and memory-variant restrictions.
- [AD7380-4](https://www.analog.com/en/products/ad7380-4.html): quad simultaneous
  SAR up to 4 MSPS. Component capability is not a completed acquisition design.

- [Lattice HX8K breakout board](https://www.latticesemi.com/en/Products/DevelopmentBoardsAndKits/iCE40HX8KBreakoutBoard): verified CT256 package candidate; the earlier TQ144 name was a selection error and is not used.

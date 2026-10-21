# Temper LCR Rev E RP2040 firmware (codec front end)

This firmware is for the Rev E board: a TAC5112 codec in place of the ADS9224R, both THS4551s and the AD9833 ([front-end design](../docs/rev-e-front-end.md)), and three latching range relays ([range switching](../docs/rev-e-range-switching.md)). It does **not** run on Rev D; Rev D keeps `../firmware/`. No Rev E board exists yet. Everything below is checked by host tests, an instruction-level PIO model and a static cycle bound, not on hardware.

- **Target:** bare RP2040, 12 MHz crystal, 120 MHz system clock.
- **Toolchain:** Pico SDK 2.2.0 and Arm GNU 14.2.rel1, the same pins as Rev D.
- **Interface:** USB CDC, protocol 3.
- **Hardware identity:** `E-codec`.

## Build and flash

```sh
git clone --branch 2.2.0 https://github.com/raspberrypi/pico-sdk.git /tmp/pico-sdk
git -C /tmp/pico-sdk submodule update --init lib/tinyusb
export PICO_SDK_PATH=/tmp/pico-sdk
export PICO_TOOLCHAIN_PATH=/path/to/arm-gnu-toolchain-14.2.rel1-darwin-arm64-arm-none-eabi
./build.sh
```

`build.sh` does the following:
- pins the SDK commit (`a1438dff…`, TinyUSB `86ad6e56…`) and builds with `-Wall -Wextra -Werror`;
- runs `test/test_host.c` on the build host;
- converts the image to UF2 with `../firmware/tools/bin_to_uf2.rs`;
- runs `tools/verify_tdm.rs` against the assembled PIO program and `tools/hot_loop_bound.rs` against the disassembly;
- writes `verification/`.

Flash `bin/temper-lcr-rev-e.uf2` the same way as Rev D: send `BOOT`, or hold BOOTSEL, then copy it to the RPI-RP2 drive.

## Wiring contract

The Rev E schematic must follow `src/pins.h`.

| RP2040 GPIO | Function | Other end |
|---|---|---|
| 2 | I2S DOUT (in) | TAC5112 pin 4 |
| 3 | I2S DIN (out) | TAC5112 pin 5 |
| 4, 5 | BCLK, FSYNC (out; PIO side-set, consecutive) | TAC5112 pins 2, 3 |
| 8, 9 | I2C0 SDA, SCL, 4.7 kΩ pull-ups to 3V3 | TAC5112 pins 8, 7; ADDR (13) to ground = 0x50 |
| 13 | USB VBUS / 2 sense | connector divider |
| 14 | RNG_RESET: the three RESET coils' AO3400A | K1–K3 |
| 15, 16, 17 | RNG_SET_LO / MED / HI: SET coil AO3400A for 100 Ω / 5 kΩ / 100 kΩ | K1, K2, K3 |
| 25 | capture LED | |
| 26, 27 | ±12 V monitors (ADC0, ADC1), unchanged from Rev D | |
| 28, 29 | optional UART0 header | |

The relay GPIOs come from the free set in range-switching §3.2. The relay gates need 100 kΩ pull-downs: the RP2040 pads reset with pull-down, so the relays stay put through reset.

## Codec configuration (`src/tac5112.c`)

The RP2040 is the bus clock controller. BCLK is 12 MHz (120 MHz / 10) and FSYNC is 187.5 kHz (64 BCLK per frame). Both run from boot and never stop. The codec runs in target mode with its PLL on BCLK; auto clock detection should report the 167.6–197.8 kHz bin. The bring-up sequence, after the 2 ms POR wait:

1. SW_RESET, wait 10 ms (the datasheet's wait before an exit-sleep write; a reset ends in sleep).
2. Wake (DEV_MISC_CFG = 0x09: VREF on, AREG for AVDD 3.3 V), wait 10 ms.
3. Register writes:

| Register | Value | Meaning |
|---|---|---|
| INTF_CFG1 | 0x51 | DOUT = ASI DOUT, push-pull (the reset value drives a weak high) |
| PASI_CFG0 | 0x30 | TDM, 32-bit slots |
| PASI_TX_CH1/CH2 | 0x20 / 0x21 | ADC channel 1 → slot 0, channel 2 → slot 1 |
| PASI_RX_CH1/CH2 | 0x20 / 0x01 | slot 0 → DAC channel 1; DAC channel 2 off |
| ADC_CH1/CH2_CFG0 | 0x25 | differential, 40 kΩ, CM_TOL 01, 2 Vrms, wideband |
| OUT1x_CFG1 | 0x21 | line out, 0 dB, DAC wideband (VCOM 0.6 × VREF = 1.65 V by default) |
| DSP_CFG0/1 | 0x02 | linear-phase filters, HPF = programmable IIR at its all-pass default, no biquads, no soft-step |
| CH_EN | 0xC8 | inputs 1 and 2, output 1 |
| PWR_CFG | 0xC0 | ADC and DAC powered (last) |

The firmware then waits 50 ms and requires all three of these:
- DEV_STS0 shows both ADC channels and DAC channel 1 up;
- DEV_STS1 mode is 7 (active);
- CLK_DET_STS0 shows the 187.5 kHz bin.

**There is no analog channel gain.** The TAC5112 register map has no PGA field, only digital volume, and digital volume does not lower input-referred noise. The Rev E noise check that credited firmware 12 dB gain is corrected in `../validation/rev-e-codec/`. The firmware leaves digital volume at 0 dB.

## Stream (`src/tdm.pio`, `src/main.c`)

**PIO.** One PIO state machine runs full-duplex TDM. Each bit is 5 cycles high and 5 cycles low:
- DIN and FSYNC change on the rising edge; DOUT is sampled on the falling edge, straight from the pad. The input synchronizer is bypassed: DOUT is synchronous to the RP2040's own BCLK, so the sample sees the pad 41.7 ns after the codec's launch edge, against td(DOUT) ≤ 14 ns plus pad and rise time. The synchronizer would cost 2 of those 5 cycles.
- Slot 0 carries the DAC word out and ADC channel 1 (A) in.
- Slot 1 carries zeros out and ADC channel 2 (B) in.
- The next DAC word is pulled at slot 1 bit 16 (frame cycle 476). The two pushes are at cycles 316 and 636.
- A TX underflow stalls the blocking pull. A full RX FIFO drops the word on the non-blocking push. Either sets a sticky FDEBUG flag, and the flag fails the capture.

**DMA.** Four channels:
- **TXD** plays the active waveform buffer into the TX FIFO and chains to TXC.
- **TXC** re-triggers TXD from `tx_source` and chains to SNAP.
- **SNAP** copies the RX channel's transfer count to `snap_count`.
- **RXD** writes every word into an 8192-word (21.8 ms) RAM ring. Its count of 2³² words would run out after 3.2 h, so every waveform swap and every capture re-arms it before using a snapshot.

**Alignment.** The chain fires a fixed number of cycles after the pull that took the waveform's last word. Every snapshot therefore falls between the frame's two pushes, as long as the DMA refill lands within 160 cycles. A capture starts at the snapshot + 1 word, which is always slot 0 of the next frame. Capture frame *j* meets DAC word (*j* − 5) mod *period* at the pins: the 4-word FIFO plus the output shift register run five words ahead. `tools/verify_tdm.rs` checks this, and the codec loopback self-test checks it on hardware.

**Waveform swaps.** A swap writes the new buffer and reload count right after a wrap, with interrupts off. It takes effect at the next wrap, so the stream never stops. Both buffers only ever hold words within the source limit: a rejected upload is zeroed.

**Averaging.** `src/syncavg.c` sums frame *j* into bin *j* mod *period*, 24-bit samples into int64. It also tracks single-sample extremes per channel, so clipping stays visible after averaging.
- **Overruns.** It reads only words at least 4 behind the producer. It rechecks the producer count after every batch and fails the capture if a slot it read could have been overwritten.
- **Cycle budget.** The static bound is 209 cycles per frame against 640 available.

## Protocol 3

ASCII commands end in LF.

**Status and control.**

| Command | Reply |
|---|---|
| `INFO` | `INFO 3 E-codec UNIT_ID 120000000 187500 4096 RANGE PERIOD CYCLES MV PASS\|FAIL` (CYCLES and MV are 0 for silence or an uploaded waveform) |
| `SELFTEST` | `SELFTEST PASS`, or `SELFTEST FAIL reason` |
| `RANGE 100\|5000\|100000` | `OK`. Silences the source, sends a 20 ms RESET pulse then a 20 ms SET pulse, waits 10 ms, restores the waveform. Boot selects 100 kΩ. |
| `OFF` | `OK`. Silence (zeros, period 16). The stream keeps running. |
| `RAILS` | as Rev D |
| `CODEC` | `CODEC DEV_STS0 DEV_STS1 CLK_DET_STS0 CLK_ERR_STS0 CLK_ERR_STS1` (decimal) |
| `REG N` | `REG N VALUE`: reads page-0 register N (0–127), read-only |
| `BOOT` | as Rev D |

**Source.**

| Command | Reply |
|---|---|
| `TONE CYCLES PERIOD MV` | `OK`. Plays CYCLES sine cycles per PERIOD frames, peak MV mV at SOURCE_BUF. Frequency = 187500 × CYCLES / PERIOD exactly, so 1 kHz = `2 375`, 27 kHz = `18 125`, 60 kHz = `8 25`. Limits: PERIOD 16–4096, frequency ≤ 85 kHz, MV 1–1700. |
| `WAVE PERIOD CRC32` | Followed by PERIOD × 4 bytes of little-endian int32 DAC words; replies `OK`. Any waveform, multitone included. Every word must be within ±1,419,797,733: 1.7 V peak at SOURCE_BUF, since 2³¹ = 2 Vrms differential × 2.0/2.2. |

**Capture.**

| Command | Reply |
|---|---|
| `CAPTURE SKIP PERIODS` | `DATA 3 PERIOD PERIODS CRC32` + payload + LF `END` LF. Skips SKIP whole periods, then sums PERIODS periods. |
| `RAW COUNT` | `RAW 3 COUNT 0 CRC32` + payload + LF `END` LF. Up to 8192 consecutive frames. |

**Payloads.**
- **Header** (16 bytes): A min, A max, B min, B max, as little-endian int32. These are single 24-bit samples over the whole capture; full scale is ±8,388,608.
- **DATA body:** for each bin *k*, A sum then B sum as little-endian int64.
- **RAW body:** for each frame, A then B as little-endian int32.
- **CRC:** IEEE CRC32 over header and body.

**Capture rules.**
- A capture needs a passing self-test, VBUS, and at most 60 s of frames.
- It fails with `ERR stream_sync`, `ERR acquisition_overrun`, `ERR stream_fault` (a FIFO stall or drop) or `ERR codec_status` (the codec's power, mode or clock check failed after the capture). Each of these clears the self-test status.

**Host.** Divide each bin by PERIODS and fit the tone at bin `CYCLES` (one DFT line). A/B gives the impedance as in Rev D. Frame alignment does not affect the ratio, and the codec's filter delay is common to both channels. Settling is the host's choice through SKIP. The source is DC-coupled, so a few periods cover the DAC and ADC filters (about 17 frames each); a coil load needs its L/R time constant. **The host speaks protocol 3 from `../host/` 0.8.0** (`temper-lcr`; see its README, Rev E section).

## Self-test

The self-test is a digital loopback:
- DAC powered down (PWR_CFG ADC only), with INTF_CFG1 DOUT_SEL = 14, so DOUT echoes DIN.
- The firmware plays a pseudo-random period-61 pattern within the source limit.
- Two raw captures must each return slot 0 = pattern[(*j* − 5) mod 61] >> 8 and slot 1 = 0 for all 244 frames.

This exercises the PIO bit timing on real pins, the slot order, the DMA chain and the snapshot alignment. It runs at boot after codec bring-up and on `SELFTEST`.

- **Recovery.** If the codec fails its status check first (lost configuration, brown-out, bus fault), `SELFTEST` runs the full bring-up again once.
- **Cleanup.** Every exit path restores silence, normal DOUT and DAC power, so one transient fault cannot make later self-tests fail.

**UNVERIFIED:** the datasheet does not say whether the loopback is combinational or retimed. A retimed echo would shift the bits and fail this test on good hardware. The first board decides; the fix would be an expected bit offset.

## Verification status and first-board checks

`verification/` holds:
- the host test result;
- the PIO model result: 4 periods × 5 DOUT delays (0–33 ns) × 4 DMA latencies, plus two negative controls (a 5-cycle DOUT delay and a late refill must fail);
- the hot-loop bound, size, UF2 check, assembled PIO and hash manifest.

The PIO model was also checked against hand-mutated programs. A changed delay, a removed FSYNC, a short slot, forced-zero data and a misplaced push or pull all fail it.

**No physical board has been tested.** On the first board, check in this order:
1. `CODEC`: the codec reports the 187.5 kHz bin with its PLL locked.
2. BCLK, FSYNC, DIN and DOUT on a logic analyser: TDM timing, and DOUT settled well inside the 41.7 ns from the rising edge to the sample.
3. `SELFTEST`, including the loopback behaviour above.
4. Silence and `RAW` noise against the noise check.
5. `TONE` into a short and into an open, to see the 1.65 V common-mode rejection of the difference stage on a scope.
6. `RANGE` switching with the source silent.
7. Overrun-free `CAPTURE` at 60 s with USB traffic.

The bench items in rev-e-front-end.md (85 kHz response, gain compression, CM_TOL 01 in wideband mode) apply unchanged.

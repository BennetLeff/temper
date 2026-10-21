# Temper LCR Rev E RP2040 firmware (codec front end)

This firmware is for the Rev E board: a TAC5112 codec in place of the ADS9224R, both THS4551s and the AD9833 ([front-end design](../docs/rev-e-front-end.md)), three latching range relays ([range switching](../docs/rev-e-range-switching.md)) and a fourth latching relay, K4, that switches an internal 1 kΩ 0.1 % reference across HCUR–LCUR. It does **not** run on Rev D; Rev D keeps `../firmware/`. No Rev E board exists yet. Everything below is checked by host tests, an instruction-level PIO model and a static cycle bound, not on hardware.

- **Target:** bare RP2040, 12 MHz crystal. Two builds: the default 187.5 kHz image at a 120 MHz system clock, and a 375 kHz variant at 108 MHz ([Sample rate](#sample-rate)).
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

`build.sh` does the following, once per build (`-DLCR_FS_375K=0` and `=1`):
- pins the SDK commit (`a1438dff…`, TinyUSB `86ad6e56…`) and builds with `-Wall -Wextra -Werror`;
- runs `test/test_host.c` on the build host, compiled for that build;
- converts the image to UF2 with `../firmware/tools/bin_to_uf2.rs`;
- runs `tools/hot_loop_bound.rs` against the disassembly with that build's frame budget.

It then runs `tools/verify_tdm.rs` against both assembled PIO programs (`tdm`, `tdm375`; every build assembles both) and writes `verification/`.

Flash `bin/temper-lcr-rev-e.uf2` (or `bin/temper-lcr-rev-e-375k.uf2`) the same way as Rev D: send `BOOT`, or hold BOOTSEL, then copy it to the RPI-RP2 drive.

## Wiring contract

`src/pins.h` matches the routed Rev E board (`cad/design.json`, U1 pins), plus GPIO 14 (U1 pin 17) for K4, which is being added to the board now. GPIO 12 was the first choice but has no escape: USB_SENSE runs over U1 pin 15.

| RP2040 GPIO | Function | Other end |
|---|---|---|
| 2 | I2S DIN (out) | TAC5112 pin 5 |
| 3 | I2S DOUT (in) | TAC5112 pin 4 |
| 4, 5 | BCLK, FSYNC (out; PIO side-set, consecutive) | TAC5112 pins 2, 3 |
| 6 | RNG_SET_HI: SET coil AO3400A for 100 kΩ | K3 |
| 7 | RNG_SET_LO: SET coil AO3400A for 100 Ω | K1 |
| 8, 9 | I2C0 SDA, SCL, 4.7 kΩ pull-ups to 3V3 | TAC5112 pins 8, 7; ADDR (13) to ground = 0x50 |
| 10 | RNG_RESET: the four RESET coils' AO3400A | K1–K4 |
| 11 | RNG_SET_MED: SET coil AO3400A for 5 kΩ | K2 |
| 13 | USB VBUS / 2 sense | connector divider |
| 14 | RNG_SET_REF (board net RLY_SET_REF): SET coil AO3400A Q6, 100 Ω gate resistor R108, 100 kΩ pull-down R109, for the 1 kΩ reference | K4 |
| 25 | capture LED | |
| 26, 27 | ±12 V monitors (ADC0, ADC1), unchanged from Rev D | |
| 28, 29 | optional UART0 header | |

DIN and DOUT trade places against the first wiring draft so the board reuses the Rev D ADC/DDS breakouts. The relay GPIOs are the ADS9224R/AD9833 pins next to the codec bus, so the drive lines leave the RP2040 on the same side. All five relay gates (GPIO 6, 7, 10, 11, 14) need 100 kΩ pull-downs: the RP2040 pads reset with pull-down, so the relays stay put through reset. The firmware drives all five low at boot before anything else.

## Relays (`src/relay.c`, `src/main.c`)

K1–K4 are TQ2SA-L2-5V dual-coil latching relays, each coil on its own AO3400A low-side driver, except that the four RESET coils share GPIO 10. One RESET pulse therefore opens all four.

Every switch runs the same sequence, one coil driver on at a time:
1. Silence the source and wait 5 ms, so the contacts switch dry.
2. RESET for 20 ms (all four open).
3. SET the range relay for 20 ms.
4. Only for `REFCAPTURE`: SET K4 for 20 ms.
5. Wait 10 ms, then restore the waveform.

K4 is only ever set right after a RESET and a range SET, so it is never closed without exactly one range relay. Only `REFCAPTURE` sets it, and the same command RESETs it again before replying. Boot RESETs all four and selects 100 kΩ even if the source cannot be silenced, so a K4 latched closed by a power loss mid-`REFCAPTURE` opens at the next power-up. `test/test_host.c` checks the sequence against a model of the five drivers: RESET first, one range, K4 only when asked, 20 ms pulses, never two drivers on, and every relay state from any latched start.

**Coil-current budget.** The worst pulse is RESET: four coils at 28.1 mA each (TQ2SA-L2-5V, 178 Ω; `../sources/rev-e/TQ2SA.txt` line 156) through the 2.2 Ω coil-supply resistor (R101; [range switching](../docs/rev-e-range-switching.md) 3.2):
- 4 × 28.1 mA = 112 mA, so the resistor drops 0.25 V.
- At the 4.75 V minimum of the 5 V supply, each coil still sees at least 4.5 V. The set and reset voltage is at most 3.75 V.
- The 28.1 mA figure is at 5 V on the coil, so it overstates the current at 4.5 V; the AO3400A adds about 6 mV at 112 mA.
- SET pulses drive one coil (28.1 mA, 0.06 V drop).
- With three relays the worst pulse was 84 mA and 0.18 V.

## Codec configuration (`src/tac5112.c`)

The RP2040 is the bus clock controller. In the default build BCLK is 12 MHz (120 MHz / 10) and FSYNC is 187.5 kHz (64 BCLK per frame); the 375 kHz build uses 18 MHz and 48 BCLK ([Sample rate](#sample-rate)). Both run from boot and never stop. The codec runs in target mode with its PLL on BCLK; auto clock detection should report the 167.6–197.8 kHz bin (375 kHz: 335.2–395.5 kHz). The bring-up sequence, after the 2 ms POR wait:

1. SW_RESET, wait 10 ms (the datasheet's wait before an exit-sleep write; a reset ends in sleep).
2. Wake (DEV_MISC_CFG = 0x09: VREF on, AREG for AVDD 3.3 V), wait 10 ms.
3. Register writes:

| Register | Value | Meaning |
|---|---|---|
| INTF_CFG1 | 0x51 | DOUT = ASI DOUT, push-pull (the reset value drives a weak high) |
| PASI_CFG0 | 0x30 | TDM, 32-bit slots (375 kHz build: 0x20, 24-bit slots) |
| PASI_TX_CH1/CH2 | 0x20 / 0x21 | ADC channel 1 → slot 0, channel 2 → slot 1 |
| PASI_RX_CH1/CH2 | 0x20 / 0x01 | slot 0 → DAC channel 1; DAC channel 2 off |
| ADC_CH1/CH2_CFG0 | 0x25 | differential, 40 kΩ, CM_TOL 01, 2 Vrms, wideband |
| OUT1x_CFG1 | 0x21 | line out, 0 dB, DAC wideband (VCOM 0.6 × VREF = 1.65 V by default) |
| DSP_CFG0/1 | 0x42 | low-latency filters (375 kHz build: 0x02, linear-phase), HPF = programmable IIR at its all-pass default, no biquads, no soft-step |
| CH_EN | 0xC8 | inputs 1 and 2, output 1 |
| PWR_CFG | 0xC0 | ADC and DAC powered (last) |

The firmware then waits 50 ms and requires all three of these:
- DEV_STS0 shows both ADC channels and DAC channel 1 up;
- DEV_STS1 mode is 7 (active);
- CLK_DET_STS0 shows the build's bin (10 for 187.5 kHz, 5 for 375 kHz).

**Filters.** Earlier versions of this firmware wrote DSP_CFG0/1 = 0x02, which selects the linear-phase filters. In the 192 kHz class, which includes 187.5 kHz, those filters do not reach 85 kHz:
- The ADC filter is specified flat only to 0.223·fs = 41.8 kHz, and attenuates by at least 80 dB from 0.391·fs = 73.3 kHz (SLASF24A Table 7-31).
- The DAC filter is specified only to 0.258·fs = 48.4 kHz (Table 7-57).
- So 60 kHz fell in an unspecified transition band and 85 kHz in the stop band.

The low-latency filters (DSP_CFG0/1 [7:6] = 01, Tables 8-102 and 8-103) fix this:
- The ADC passes 0.456·fs = 85.5 kHz ±0.06 dB, with its stop band from 0.571·fs = 107 kHz (Table 7-38).
- The DAC passes 0.452·fs = 84.8 kHz (Table 7-64).
- Their phase deviation (±9.24° to 0.327·fs on the ADC) belongs to the filter: both ADC channels have the same one, so it cancels in A/B.
- The 85 kHz tone limit sits 0.25 kHz above the DAC filter's specified edge. DAC droop is common to both channels.

These are the filters the [acquisition survey](../docs/rev-e-acquisition-survey.md) derived the 85 kHz figure from. The datasheet specifies low-latency filters only up to the 192 kHz class (7.3.9.1.8.2), so the 375 kHz build keeps the linear-phase ones.

**There is no analog channel gain.** The TAC5112 register map has no PGA field, only digital volume, and digital volume does not lower input-referred noise. The Rev E noise check that credited firmware 12 dB gain is corrected in `../validation/rev-e-codec/`. The firmware leaves digital volume at 0 dB.

## Stream (`src/tdm.pio`, `src/main.c`)

**PIO.** One PIO state machine runs full-duplex TDM. The figures below are for the default build (`src/tdm.pio`); the 375 kHz build (`src/tdm375.pio`) is in [Sample rate](#sample-rate). Each bit is 5 cycles high and 5 cycles low:
- DIN and FSYNC change on the rising edge; DOUT is sampled on the falling edge, straight from the pad. The input synchronizer is bypassed: DOUT is synchronous to the RP2040's own BCLK, so the sample sees the pad 41.7 ns after the codec's launch edge, against td(DOUT) ≤ 14 ns plus pad and rise time. The synchronizer would cost 2 of those 5 cycles.
- Slot 0 carries the DAC word out and ADC channel 1 (A) in.
- Slot 1 carries zeros out and ADC channel 2 (B) in.
- The next DAC word is pulled at slot 1 bit 16 (frame cycle 476). The two pushes are at cycles 316 and 636.
- A TX underflow stalls the blocking pull. A full RX FIFO drops the word on the non-blocking push. Either sets a sticky FDEBUG flag, and the flag fails the capture.

**DMA.** Four channels:
- **TXD** plays the active waveform buffer into the TX FIFO and chains to TXC.
- **TXC** re-triggers TXD from `tx_source` and chains to SNAP.
- **SNAP** copies the RX channel's transfer count to `snap_count`.
- **RXD** writes every word into an 8192-word RAM ring (21.8 ms; 10.9 ms at 375 kHz). Its count of 2³² words would run out after 3.2 h (1.6 h at 375 kHz), so every waveform swap and every capture re-arms it before using a snapshot.

**Alignment.** The chain fires a fixed number of cycles after the pull that took the waveform's last word. Every snapshot therefore falls between the frame's two pushes, as long as the DMA refill lands within 160 cycles. A capture starts at the snapshot + 1 word, which is always slot 0 of the next frame. Capture frame *j* meets DAC word (*j* − 5) mod *period* at the pins: the 4-word FIFO plus the output shift register run five words ahead. `tools/verify_tdm.rs` checks this, and the codec loopback self-test checks it on hardware.

**Waveform swaps.** A swap writes the new buffer and reload count right after a wrap, with interrupts off. It takes effect at the next wrap, so the stream never stops. Both buffers only ever hold words within the source limit: a rejected upload is zeroed.

**Averaging.** `src/syncavg.c` sums frame *j* into bin *j* mod *period*, 24-bit samples into int64. It also tracks single-sample extremes per channel, so clipping stays visible after averaging.
- **Overruns.** It reads only words at least 4 behind the producer. It rechecks the producer count after every batch and fails the capture if a slot it read could have been overwritten.
- **Cycle budget.** The static bound is 209 cycles per frame against 640 available (375 kHz build: 288 available, 72 %).

## Protocol 3

ASCII commands end in LF.

**Status and control.**

| Command | Reply |
|---|---|
| `INFO` | `INFO 3 E-codec UNIT_ID 120000000 187500 4096 RANGE PERIOD CYCLES MV PASS\|FAIL` (CYCLES and MV are 0 for silence or an uploaded waveform). The 375 kHz build reports `108000000 375000`. |
| `SELFTEST` | `SELFTEST PASS`, or `SELFTEST FAIL reason` |
| `RANGE 100\|5000\|100000` | `OK`. Silences the source, sends a 20 ms RESET pulse (all four relays, K4 included) then a 20 ms SET pulse, waits 10 ms, restores the waveform ([Relays](#relays-srcrelayc-srcmainc)). Boot selects 100 kΩ. |
| `OFF` | `OK`. Silence (zeros, period 16). The stream keeps running. |
| `RAILS` | as Rev D |
| `CODEC` | `CODEC DEV_STS0 DEV_STS1 CLK_DET_STS0 CLK_ERR_STS0 CLK_ERR_STS1` (decimal) |
| `REG N` | `REG N VALUE`: reads page-0 register N (0–127), read-only |
| `BOOT` | as Rev D |

**Source.**

| Command | Reply |
|---|---|
| `TONE CYCLES PERIOD MV` | `OK`. Plays CYCLES sine cycles per PERIOD frames, peak MV mV at SOURCE_BUF. Frequency = 187500 × CYCLES / PERIOD exactly, so 1 kHz = `2 375`, 27 kHz = `18 125`, 60 kHz = `8 25`. At 375 kHz: `1 375`, `9 125`, `4 25`. Limits: PERIOD 16–4096, frequency ≤ 85 kHz, MV 1–1700. |
| `WAVE PERIOD CRC32` | Followed by PERIOD × 4 bytes of little-endian int32 DAC words; replies `OK`. Any waveform, multitone included. Every word must be within ±1,419,797,733: 1.7 V peak at SOURCE_BUF, since 2³¹ = 2 Vrms differential × 2.0/2.2. |

**Capture.**

| Command | Reply |
|---|---|
| `CAPTURE SKIP PERIODS` | `DATA 3 PERIOD PERIODS CRC32` + payload + LF `END` LF. Skips SKIP whole periods, then sums PERIODS periods. |
| `RAW COUNT` | `RAW 3 COUNT 0 CRC32` + payload + LF `END` LF. Up to 8192 consecutive frames. |
| `REFCAPTURE RANGE SKIP PERIODS` | As `CAPTURE`, measuring the internal 1 kΩ reference on RANGE (100, 5000 or 100000) with the waveform now playing, for a drift or self check. The firmware:<br>1. silences the source, RESETs, SETs RANGE, SETs K4, then restores the waveform;<br>2. captures as `CAPTURE SKIP PERIODS`;<br>3. silences, RESETs (K4 opens), SETs the range selected before the command, then restores the waveform;<br>4. replies `DATA 3 …`.<br>Step 3 runs even after a failed capture. `ERR range` for any other RANGE. |

**Payloads.**
- **Header** (16 bytes): A min, A max, B min, B max, as little-endian int32. These are single 24-bit samples over the whole capture; full scale is ±8,388,608.
- **DATA body:** for each bin *k*, A sum then B sum as little-endian int64.
- **RAW body:** for each frame, A then B as little-endian int32.
- **CRC:** IEEE CRC32 over header and body.

**Capture rules.**
- A capture needs a passing self-test, VBUS, and at most 60 s of frames.
- It fails with `ERR stream_sync`, `ERR acquisition_overrun`, `ERR stream_fault` (a FIFO stall or drop) or `ERR codec_status` (the codec's power, mode or clock check failed after the capture). Each of these clears the self-test status.
- `REFCAPTURE` measures 1 kΩ in parallel with whatever is on the DUT terminals: K4 adds the reference across HCUR–LCUR and does not disconnect the jacks. Leave the terminals open. The current channel sees the reference current times the range resistor. The channel clips above 5.66 V peak at the TIA (2 Vrms differential full scale behind the 1 kΩ/1 kΩ divider), so full level (1700 mV) is fine on 100 Ω but clips on 5 kΩ and 100 kΩ. The host's `refcheck` defaults to 75 % of full scale: 1700, 863 and 43 mV. The header extremes show any clipping.

**Host.** Divide each bin by PERIODS and fit the tone at bin `CYCLES` (one DFT line). A/B gives the impedance as in Rev D. Frame alignment does not affect the ratio, and the codec's filter delay is common to both channels. Settling is the host's choice through SKIP. The source is DC-coupled, so a few periods cover the DAC and ADC filters (about 17 frames each); a coil load needs its L/R time constant. **The host speaks protocol 3 from `../host/` 0.8.0** (`temper-lcr`; see its README, Rev E section).

## Sample rate

**Decision: 375 kHz is feasible within the datasheets, as an opt-in build (`-DLCR_FS_375K=1`, `bin/temper-lcr-rev-e-375k.uf2`). 187.5 kHz stays the default.** The 375 kHz build does not raise the tone ceiling: both builds stop at 85 kHz.

| | 187.5 kHz (default) | 375 kHz |
|---|---|---|
| System clock | 120 MHz | 108 MHz |
| BCLK | 12 MHz, 10 clocks (5 + 5) | 18 MHz, 6 clocks (3 + 3) |
| Frame | 64 BCLK, two 32-bit slots | 48 BCLK, two 24-bit slots |
| DOUT sample after the launch edge | 41.7 ns | 27.8 ns |
| Codec filters (DSP_CFG0/1) | low-latency (0x42) | linear-phase (0x02) |
| ADC / DAC passband | 85.5 / 84.8 kHz | 85.1 / 96.8 kHz |
| Hot-loop bound | 209 of 640 cycles | 209 of 288 cycles (72 %) |
| Lowest exact tone (PERIOD 4096) | 45.8 Hz | 91.6 Hz |
| RX ring, `RAW` 8192 frames | 21.8 ms, 43.7 ms | 10.9 ms, 21.8 ms |

**Datasheet evidence** (TAC5112 datasheet SLASF24A, January 2025; page numbers as printed, the same as in the [acquisition survey](../docs/rev-e-acquisition-survey.md)):
- **Rates and ratios.** ADC and DAC run at 4–768 kHz (6.5, p10 and p14). Table 7-7 (p38) lists BCLK/FSYNC = 48 (18.432 MHz) and 64 (24.576 MHz) in the 384 kHz column. 375 kHz falls in auto-detect bin 5, 335.16–395.52 kHz (Table 8-59, CLK_DET_STS0), and in the 1 % bucket 349.27–387.84 kHz (SLAAEG9 Table 1-1). It is the same kind of non-audio rate as 187.5 kHz is in the 192 kHz bin.
- **Bus timing.** BCLK period must be at least 40 ns, high and low at least 18 ns (6.10, p18). If DOUT is latched on the edge opposite the one the device transmits on, which is the falling edge here, high and low must exceed 25 ns (note 1, p19). At 18 MHz both are 27.8 ns. DIN and FSYNC setup and hold are 8 ns, against 27.8 ns. td(DOUT) is at most 14 ns at IOVDD 3.3 V (6.11).
  - 64 BCLK at 375 kHz is 24 MHz: a 41.7 ns period, legal, but with 20.8 ns half-periods it violates note 1 unless DOUT were sampled late in the bit.
- **Wideband.** "The device supports an input signal bandwidth up to 90kHz, which allows the high-frequency non-audio signal to be recorded by using a 216kHz (or higher) sample rate" (7.3.9.1, p48). The same sentence for the output is in 7.3.9.2 (p69). Wideband needs the 40 kΩ input and not high-swing mode (p48), and the analog configuration (40 kΩ, CM_TOL 01, wideband) does not depend on the rate. 375 kHz meets the 216 kHz condition; 187.5 kHz does not. The datasheet does not say what wideband mode does below 216 kHz. Either way, **90 kHz is the analog ceiling at any rate**, so a higher rate cannot lift the tone limit above it.
- **Filters at 384 kHz.** Linear-phase only:
  - ADC: ±0.07 dB to 0.227·fs = 85.1 kHz, stop band from 0.391·fs = 146.6 kHz, 11.4 frames of delay (Table 7-32, p59).
  - DAC: ±0.67 dB to 0.258·fs = 96.8 kHz (Table 7-58, p78).
  - The tone ceiling stays 85 kHz, set by the ADC passband.
  - At 768 kHz the ADC passband is 0.121·fs (Table 7-33, p60), and 90 kHz analog caps it anyway. Higher rates gain nothing.
- **"Limitations for sample rates higher than 48 kHz"** (p49 and p70). The datasheet says only that the number of simultaneous recording and playback channels and the number of biquads are limited, and points to the TAC5212 "Sampling Rates and Programmable Processing Blocks Supported" application report. That report is not in `../sources/`. The firmware uses two ADC channels, one DAC channel, no biquads, and the HPF as an all-pass IIR. **UNVERIFIED** whether the 384 kHz class allows exactly this set. The same sentence covers 187.5 kHz too. Both builds check it at boot: DEV_STS0 must show both ADC channels and DAC channel 1 powered, or the codec check fails.
- **Noise.** The datasheet gives no SNR against sample rate. Wideband SNR is 91 dB, integrated to 85 kHz (6.5, p9). The modulator clock does not follow the output rate (3.072 MHz class, 7.3.9.1.4, p50). So the in-band noise density at the tone, and the noise in one DFT bin over the same capture time, should not change with the rate. This is derived, **UNVERIFIED**. The cost is per frame: a capture of the same length in seconds has twice the frames.

**RP2040 clock.** 108 MHz (exact: PLL VCO 756 MHz / 7) is inside the 133 MHz rating "across all process, voltage and temperature variations" at the default core voltage (RP2040 datasheet 2025-02-20, `../sources/new/RP2040-datasheet.txt` lines 566 and 13345). The 192 MHz / 24 MHz / 64-BCLK alternative would need the elevated-DVDD, VSEL 1.15 V operation that the same note describes for 200 MHz, plus the note-1 workaround above, so it was not chosen.
- USB and the ADC run from the fixed 48 MHz USB PLL and do not change.
- I2C is configured after the clock change.
- XIP flash runs at clk_sys / 2 (`PICO_FLASH_SPI_CLKDIV` 2 for the pico board): 54 MHz, against 60 MHz today and the W25Q128JV's 133 MHz.

**PIO (`src/tdm375.pio`).** Each bit is 3 cycles high and 3 low, and DOUT is sampled on the falling edge, 27.8 ns after the launch edge. Slot 0 sends the top 24 bits of the DAC word, so the DAC word format and `WAVE` are unchanged. After each 24-bit ADC word, `in null, 8` left-justifies it, so the RX words have the 32-bit-slot layout and `syncavg` is unchanged. Pushes land at frame cycles 143 and 287, the pull at 214. A TX refill must land within 73 cycles (676 ns) of the pull, against 160 cycles (1.33 µs) at 187.5 kHz. The capture alignment (frame *j* meets DAC word *j* − 5) and the self-test are unchanged.

**Host.** `temper-lcr` 0.8.x speaks the default build only. It recognises the 375 kHz build's `INFO` and refuses it by name. Using the variant from the host means passing the frame rate from `INFO` through its tone, settling and capture-length rules (`../host/src/rev_e.rs`), which assume 187.5 kHz.

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

`verification/` holds, for both builds:
- the host test results;
- the PIO model results:
  - `tdm`: 4 periods × 5 DOUT delays (0–33 ns) × 4 DMA latencies;
  - `tdm375`: 4 periods × 3 DOUT delays (0–18.5 ns) × 4 DMA latencies (0–70 cycles);
  - each with two negative controls: a DOUT delay reaching the falling edge, and a refill past the slot-1 push, must both fail;
- the hot-loop bounds, sizes, UF2 checks, both assembled PIO programs and the hash manifest.

The PIO model was also checked against hand-mutated programs. For `tdm`: a changed delay, a removed FSYNC, a short slot, forced-zero data, and a misplaced push or pull all fail it. For `tdm375`: wrong loop counts in either slot, a short `in null`, a shortened high phase, a lengthened bit, a removed pull, data instead of zeros in slot 1, and two side-set errors all fail it.

**No physical board has been tested.** On the first board, check in this order:
1. `CODEC`: the codec reports the 187.5 kHz bin with its PLL locked.
2. BCLK, FSYNC, DIN and DOUT on a logic analyser: TDM timing, and DOUT settled well inside the 41.7 ns from the rising edge to the sample (27.8 ns in the 375 kHz build), and BCLK rise and fall within 10 ns (6.10).
3. `SELFTEST`, including the loopback behaviour above.
4. Silence and `RAW` noise against the noise check.
5. `TONE` into a short and into an open, to see the 1.65 V common-mode rejection of the difference stage on a scope.
6. `RANGE` switching with the source silent. On VRLY during the four-coil RESET pulse, look for at least 4.5 V. Check that K4 opens on every `RANGE` and at power-up after a power loss during `REFCAPTURE`.
7. `REFCAPTURE` on 100 Ω and 5 kΩ with the terminals open: 1 kΩ within the reference's 0.1 % after calibration, and repeatable.
8. Overrun-free `CAPTURE` at 60 s with USB traffic.
9. Low-latency filters: a `TONE` sweep to 85 kHz shows no roll-off at 60–85 kHz in either channel (the linear-phase filters would have attenuated 85 kHz by ≥ 80 dB).
10. For the 375 kHz build: steps 1–4 and 8, `CODEC` showing bin 5 and every channel powered (the >48 kHz channel-count limitation), and silence noise per DFT bin at equal capture time against the default build.

The bench items in rev-e-front-end.md (85 kHz response, gain compression, CM_TOL 01 in wideband mode) apply unchanged.

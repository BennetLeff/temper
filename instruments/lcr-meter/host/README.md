# Temper LCR host (Rev D and Rev E)

Host 0.8.0 drives both boards from one CLI: the board answers `INFO` with `INFO 2 D-riso22 ...` (Rev D, protocol 2, described first) or `INFO 3 E-codec ...` (Rev E, protocol 3, [its own section](#rev-e-e-codec-protocol-3) below), and the CLI follows. Capture and calibration files carry their revision and the two revisions refuse each other's files.

This CLI operates the one-PCB TIDA-060029-based Rev D instrument over USB CDC on macOS/Linux. Its identity is `D-riso22`: one fixed local 100 pF TIA feedback capacitor for all ranges, and R94 (22 Ω, 0.1 %) between J3 LO and the TIA summing node. Host 0.6.0 rejects the Rev C identity `C-local100p`, and calibration schema 4 files, because the Rev C feedback model has no isolation resistor. The included executable is macOS arm64. Rev A and Rev B software are preserved under `../archive/`. The host speaks USB protocol 2 only (firmware boxcar-sums 1 MSPS conversions; see below). It rejects protocol-1 firmware, protocol-1 capture files and schema-3 calibration files written by host 0.4.0 with explicit errors, and still rejects earlier identities including `C` with per-range compensation, and their calibration files; acquire fresh standards on the final board with protocol-2 firmware. Flashing firmware does not identify or modify an older physical PCB. Capture files may now carry a paired source-off record, its check and any hazards accepted with `--allow-hazard`; these fields are optional, so earlier protocol-2 capture files still load (they are reported as not source-off checked).

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

Power the board from its regulated external 5 V supply, flash `../firmware/bin/temper-lcr-rev-d.uf2` using BOOTSEL (later updates: `temper-lcr boot PORT` reboots into the bootloader, then copy the UF2 to the RPI-RP2 drive), then connect USB. Run `temper-lcr rails PORT` (also part of `info`, `capture` and `noise`): it reads the ±12 V monitors and the RP2040 die temperature, and refuses to measure when either rail is outside 10.8–13.2 V in magnitude. The monitors read ratiometrically to 3V3, so a 3V3 error scales both readings; this is a gross-fault check, not a rail calibration. Select **both** matched RG/RF jumpers with power off and record that selection in every command. Software cannot sense the jumpers. Use the 100 Ω range initially for the stage53 coil, 100 nF/0.5 µF resonant capacitors and 9 µF bus capacitor at 1.5 kHz. Typical target grid is `1500,35500,40500,50500,60500` (see **Measurement grid and frequency hazards**; the former whole-kHz grid is refused). At 1.5 kHz the 9 µF capacitor is −j11.8 Ω instead of −j17.7 Ω at 1 kHz, still well inside the 100 Ω range.

The LOW sense follower taps the J3 side of R94, so the current channel spans R94 in series with the selected RF‖CF. The Rev D host models these feedback networks explicitly:

| Range | Feedback capacitor | Host correction |
|---:|---:|---|
| 100 Ω | 100 pF | 22 Ω + (100 Ω in parallel with 100 pF) |
| 5 kΩ | 100 pF | 22 Ω + (5 kΩ in parallel with 100 pF) |
| 100 kΩ | 100 pF | 22 Ω + (100 kΩ in parallel with 100 pF) |

The values are centralized in `FEEDBACK_CAPACITORS_PF` and `ISOLATION_RESISTOR_OHM` in `src/lib.rs`. Fixture calibration still determines actual parasitics and component tolerances, including R94's. Calibration schema 5 and model `bilinear-short-two-resistors-v5-riso22-local100p-boxcar` record the selected nominal feedback capacitor, the isolation resistor and the boxcar decimation of each point. They reject a mismatch, an older schema/model (schema 4 from host 0.5.0 on Rev C; schema 3 from host 0.4.0, whose undersampled captures are not equivalent), or a different hardware identity.

With R94 fitted, LO is no longer a virtual ground: it sits at I·22 Ω, so cable capacitance on the LO lead diverts a small, fixed fraction of the DUT current (about 0.17 % for 200 pF at 60 kHz). Calibration removes it, but only for the lead position it saw. Fix the LO lead in place after calibration, or recalibrate after moving it. Renaming an old calibration file does not make it compatible.

Prefer the 100 kΩ range at **10 kHz or below** for current-channel signal strength. Its nominal feedback impedance falls to 15.721 kΩ at 100 kHz (−16.07 dB relative to its DC value), so numerical correction cannot recover the signal-to-noise ratio lost before conversion. The host allows frequency-specific calibrated measurements up to 100 kHz and applies its weak-signal and residual checks; this is not an accuracy guarantee. Use a lower range when practical. The 5 kΩ range's corresponding attenuation at 100 kHz is only about 0.41 dB. Stage53's coil and resonant capacitors primarily use the 100 Ω range.

Use `/dev/cu.usbmodem...` on macOS or `/dev/ttyACM...` on Linux. The serial baud setting is immaterial to USB throughput.

```sh
temper-lcr info /dev/cu.usbmodemXXXX
temper-lcr selftest /dev/cu.usbmodemXXXX
temper-lcr noise /dev/cu.usbmodemXXXX 100 fixture-1 1500,35500,40500,50500,60500 noise.json
```

`selftest` checks 256 samples of the ADC's A55A fixed pattern on both lanes. It tests the digital connection, not the analog circuitry. `noise` keeps the DDS DAC/accumulator asleep, saves the record with `source_enabled=false`, and prints DC-removed RMS, the fitted tone amplitude and the single-conversion extremes at each requested frequency. The RMS is of the N-conversion averages actually recorded (`decimation` is printed), so it covers roughly DC to the output rate and excludes noise the boxcar removed; only above 50 kHz (N = 1) is it the full 1 MSPS broadband RMS. The tone amplitude is input-referred (boxcar gain removed). RMS volts use nominal ±4.096 V ADC differential full scale. Check both open and short fixture conditions. This is a narrow-tone diagnostic plus broadband RMS, not a full spectrum analyzer. Source-off records are explicitly rejected by impedance analysis. `noise` applies the frequency hazard check below; to look at a hazardous frequency on purpose (for example the 1 kHz SOF line), add `--allow-hazard`.

## Measurement grid and frequency hazards

`validation/power-spurs` found two interferers that land exactly on whole-kHz test frequencies, where the DC + cos + sin fit has no rejection at all: USB start-of-frame (SOF) lines at every multiple of 1 kHz on the host's clock, and AD9833 harmonics that alias onto f with the decimation `decimation_for` picks. `capture` and `noise` therefore check every requested frequency before touching the instrument (R1), and refuse a hazardous one with an error that names each hazard and the nearest clean frequency. `--allow-hazard` captures anyway and stores the hazards in the record's `allowed_hazards`; `analyze` recomputes and reports them in `frequency_hazards` without invalidating the point. The source-off check below cannot see DDS harmonics, because the DDS is asleep.

```sh
temper-lcr advise-grid 1000,35000,40000,50000,60000   # JSON: hazards and nearest clean frequency per point
```

`advise-grid` prints JSON with `all_clean`, `suggested_grid` (a comma-separated list to pass to `capture`) and, per frequency, `clean`, the `hazards`, `suggested_hz` and the full report at the suggestion. It needs no device.

The check (`src/integrity.rs`) works on the quantized DDS frequency, the boxcar decimation N and the 16,384-output record. Each interferer at physical frequency p reaches the fit as D(p)·cos(2πp·t_k + φ) at the boxcar window centres, so its fitted error relative to the signal is |D(p)/D(f)| times the worst-phase response of the exact least-squares estimator, evaluated in closed form (a unit test checks it against the real fit). Aliasing at 1 MSPS, the boxcar, and folding at the output rate are therefore all included without approximation.

| Interferer | Frequencies | Level | Hazard when |
|---|---|---|---|
| AD9833 harmonics k = 2…200 | k·f, crystal-locked | −56 dBc each (the AD9833BRMZ THD maximum in `sources/new/AD9833.txt`, applied to every order; the typical wideband SFDR is −60 dBc and no limit is given above the 6th), scaled by the reconstruction filter (200 Ω, 330 Ω/1 nF, 330 Ω/1 nF) as in `power-spurs/dds_spurs.py` | predicted error > 1×10⁻⁵ of the signal: one tenth of the 10⁻⁴ source-off budget, leaving a factor of ten for the DUT ratio that does not cancel |
| USB SOF harmonics h = 1…300 | h·1 kHz ± 560 ppm (500 ppm USB frame tolerance plus 60 ppm board crystal) | unbounded | fit + boxcar response > 0.1 (less than 20 dB rejection) anywhere in the band, i.e. inside the main lobe or first sidelobe |

The report also lists main-lobe interferers that stay below their limit. Not covered: the TPS65131 switcher (its 1.25–1.50 MHz frequency is unknown until measured; use `validation/power-spurs/alias_map.py --fsw`), mains and adapter noise, SOF content above 300 kHz. The source-off check covers those at measurement time.

`advise-grid` output for the former and the new grid (rejection is the worst SOF response over ±560 ppm; DDS is the worst predicted error from any harmonic):

| Requested | N | Result | Hazards | Rejection of SOF | Worst DDS error |
|---:|---:|---|---|---:|---:|
| 1000 | 20 | refused | SOF h = 1 (0 dB); DDS k = 49, 51 (2.7×10⁻⁵) | — | — |
| 35000 | 2 | refused | SOF h = 35 (0 dB) | — | — |
| 40000 | 2 | refused | SOF h = 40; DDS k = 24, 26, 49, 51, 74, 76, 99, 101 (up to 1.7×10⁻⁴) | — | — |
| 50000 | 2 | refused | SOF h = 50; DDS k = 9, 11 (6.8×10⁻⁵, 5.5×10⁻⁵), 19, 21, 29, 31, 39, 41, 59, 61, 79, 81 | — | — |
| 60000 | 1 | refused | SOF h = 60; DDS k = 49, 51 (2.7×10⁻⁵) | — | — |
| **1500** | 20 | clean | none (DDS k = 99/101 sit 0.63 bins from f but are 4.9×10⁻⁶ after the filter and boxcar) | −53.1 dB | 4.9×10⁻⁶ |
| **35500** | 2 | clean | none | −34.8 dB | 3.7×10⁻⁷ |
| **40500** | 2 | clean | none | −34.6 dB | 2.1×10⁻⁷ |
| **50500** | 1 | clean | none | −28.5 dB | 5.8×10⁻⁷ |
| **60500** | 1 | clean | none | −28.4 dB | 3.9×10⁻⁷ |

The new grid is the power-spurs recommendation unchanged; the check prefers it to the nearest whole-hertz clean points (991, 34898, 39895, 49890 and 59802 Hz), which only just clear the 20 dB SOF limit. The N = 2 and N = 1 rejections match the power-spurs rectangular-fit figures within 0.5 dB; at 1.5 kHz the 20-conversion boxcar adds about 2.5 dB to their −50.6 dB. Moving every point up by 500 Hz barely changes the stage53 coil and resonant-capacitor impedances. Calibrate on the new grid; a calibration made on another grid has no points at these frequencies.

## Source-off integrity check

By default `capture` follows every source-on record immediately with a source-off (NOISE) record at the same tuning word, decimation and length, fits the tone at the measurement frequency in it, and requires that tone below 10⁻⁴ of the source-on amplitude on each channel (power-spurs R2). For a 15 Ω DUT on the 100 Ω range channel A is about 1440 codes, so the limit is 0.144 codes; the fit resolves about 0.011 codes per 1 LSB rms of white noise. This is the only check that sees SOF, ground loops, the adapter and switcher collisions, which the desk analysis cannot bound. It doubles capture time.

The source-off record is stored inside its source-on record (`source_off`), with the capture-time verdict in `source_off_check`. Each channel reports `source_on_codes`, `source_off_codes`, `limit_codes`, `ratio` and `noise_sigma_codes` (the source-off fit noise, residual RMS × √(2/16384) / D(f)); the `diagnostic` says whether a failure is coherent interference or a signal too weak for the gate to resolve 10⁻⁴. `capture` saves the file and then exits non-zero if any point failed. `analyze` and `validate` recompute the check from the stored source-off record (the stored verdict is not trusted), add a `source-off interference …` issue, mark the point invalid and exit non-zero, unless `--allow-source-off-fail`, which moves the issue to `waived_issues`. `calibrate` refuses a failing standard the same way and accepts the same override. `--no-source-off` skips the pair (open-fixture diagnostics, or to save time); such points, and capture files from earlier hosts, are reported with `source_off: null` and are not checked.

A short has almost no voltage signal, so capture it with `--short-standard`: its voltage channel is then judged against its current-channel amplitude, which bounds the short's offset error to 10⁻⁴ of the feedback impedance (0.01 Ω on the 100 Ω range). `calibrate` always applies that rule to the short.

## Fixture calibration and measurement

Use a short and two independently known, low-inductance resistor standards measured at the same reference plane. For the 100 Ω range, 20 Ω and 100 Ω are useful starting values; enter their known values, not merely their markings. Their reactive parasitics must be negligible or separately characterized at each frequency. The current CLI accepts real resistor standards only. Keep the same unit, fixture identifier, manual range, wiring, frequencies and temperature. Each frequency receives its own bilinear three-standard correction; there is no interpolation or extrapolation.

```sh
temper-lcr capture /dev/cu.usbmodemXXXX 100 fixture-1 1500,35500,40500,50500,60500 short.json --short-standard
# Replace the short with standard 1, then standard 2.
temper-lcr capture /dev/cu.usbmodemXXXX 100 fixture-1 1500,35500,40500,50500,60500 load20.json
temper-lcr capture /dev/cu.usbmodemXXXX 100 fixture-1 1500,35500,40500,50500,60500 load100.json
temper-lcr calibrate short.json load20.json 20.000 load100.json 100.000 calibration.json
# Connect a third, independent 47-ohm standard.
temper-lcr capture /dev/cu.usbmodemXXXX 100 fixture-1 1500,35500,40500,50500,60500 check47.json
temper-lcr validate check47.json calibration.json 47.000 1.0
# Connect the isolated DUT.
temper-lcr capture /dev/cu.usbmodemXXXX 100 fixture-1 1500,35500,40500,50500,60500 dut.json
temper-lcr analyze dut.json calibration.json
```

Every capture above also records and checks its source-off pair. If a capture exits non-zero for a source-off failure, find and remove the interference (USB cable route, adapter, ground loop) and recapture rather than overriding.

The example 1% validation threshold is a user acceptance criterion, **not established instrument accuracy**. Validate independent capacitive/inductive standards too before relying on reactance, ESR or Q. Repeat the short and standards after changing cables, jumpers or temperature. An open fixture is useful as an overload/leakage diagnostic; it is not used as a potentially saturated calibration standard. High-impedance/open DUTs and poor ranges can saturate the TIA before the ADC, so inspect analog waveforms during qualification.

The host fits DC+sin+cos to both simultaneous channels at the actual DDS tuning frequency, including fractional cycle counts. Each output sample is the sum of N conversions divided by N, timed at the centre of its window, (kN + (N−1)/2) µs after the first conversion; the fitted phasor is divided by the boxcar gain D(f) = sin(πfN/1 MHz)/(N·sin(πf/1 MHz)), at least 0.983 at the requested ≥10 outputs/cycle. D and the window delay are identical on both channels and cancel in A/B. It computes `Z=(RF || CF) × channel_A/channel_B`, where A is DUT high minus low and B is low minus TIA output. Calibration solves `measured=(a×true+b)/(c×true+1)`. Capacitive reactance is negative; inductive reactance is positive. Reported R/L/C are the **series equivalent at that frequency**, not a full component model. Q is |X|/R for positive R.

The ADC always converts both channels simultaneously at 1 MSPS. A capture stores 16,384 output samples per channel; each is the int32 sum of N consecutive conversions, with N = 1–20 chosen so the output rate (1 MSPS/N) gives at least 10 samples per cycle and enough cycles at 100 Hz (N = 20 up to 5 kHz, N = 1 above 50 kHz). Record length and output rate match the earlier undersampling scheme, but every conversion is now used: wideband noise is averaged (√N in RMS) and spurs that undersampling folded onto the measurement frequency are attenuated by the boxcar's sinc response (for example −34 dB for 51 kHz at a 1 kHz measurement), not removed. Records also hold each channel's most negative and most positive single conversion; a CRC32 covers those extremes and all sums exactly as received. DDS MCLK is the same 120 MHz MCU clock divided by five (24 MHz). Actual frequency quantization is included; absolute frequency accuracy still depends on the crystal. The on-device timing and overrun detection are described in `../firmware/README.md` and still need a logic-analyzer check on the first board.

Checks reject corrupted records (CRC, or sums outside N × the reported extremes), records or calibrations from protocol 1, missing calibration points, identity/range/fixture/decimation mismatches, clipping (any single conversion with |code|≥32700, from the firmware extremes, even when the averages are far from full scale), weak fitted amplitude (<16 codes), large residuals (>5% of tone amplitude), or a source-off tone above 10⁻⁴ of the source-on amplitude. Amplitudes and residuals are in single-conversion codes. These are screening thresholds and do not establish a calibrated noise floor. `analyze` emits diagnostics and returns nonzero for invalid measurements. Analog saturation that still looks sinusoidal can escape these digital checks.

## Rev E (`E-codec`, protocol 3)

The Rev E board replaces the DDS and the SAR ADC with a TAC5112 codec: the firmware (`../firmware-rev-e/`, protocol 3 in its README) plays any waveform of 16 to 4096 DAC words at exactly 187.5 kHz, and sums the codec's two 24-bit channels over any number of whole periods into one int64 bin per waveform index. Source and capture are coherent by construction, so the host takes one exact DFT line per requested bin: no window, no sine fit, no boxcar term. The code is `src/rev_e.rs` (wire formats, rules, analysis, calibration) and `DeviceE` in `src/transport.rs`; Rev D's code, files and tests are unchanged. **No Rev E board exists yet; everything here is checked against a circuit-level virtual instrument and a fake firmware on a pseudo-terminal, not against hardware.**

### Board selection and cross-use

`info`, `selftest`, `rails`, `boot`, `capture` and `calibrate`/`analyze`/`validate` work on both boards. The device commands read `INFO` first: protocol 2 with `D-riso22` is Rev D, protocol 3 with `E-codec` is Rev E, and a mixed pair (`INFO 3 D-riso22`, `INFO 2 E-codec`) is refused. File commands read `setup.revision`. Cross-use fails by name, in both directions: a Rev D calibration on a Rev E capture ("calibration belongs to revision D-riso22"), a Rev E calibration or capture on Rev D ("... Rev E (E-codec) ..."), Rev E-only commands on a Rev D board and the reverse, and Rev D-only options (`--allow-hazard`, `--no-source-off`, `--short-standard`, `noise`) on a Rev E board. `capture` now opens the port before it runs Rev D's hazard check; if the port cannot be opened, the Rev D check still runs first and its refusal carries the open error as a note.

### Commands

```sh
temper-lcr info /dev/cu.usbmodemXXXX            # setup, INFO, codec registers, rails (after SELFTEST)
temper-lcr range PORT 5000                       # RANGE: relay selection, source silenced around it
temper-lcr off PORT | codec PORT | reg PORT N    # OFF, CODEC, REG (page 0, 0-127, read-only)
temper-lcr tone PORT CYCLES PERIOD MV            # TONE: 187500 x CYCLES / PERIOD Hz, peak MV mV (1-1700)
temper-lcr tone-hz PORT 27000 1000               # smallest exact PERIOD (see below), at most 85 kHz
temper-lcr wave PORT wave.txt                    # WAVE: int32 DAC words, whitespace/comma separated, # comments
temper-lcr raw PORT 4096 raw.json                # RAW: up to 8192 consecutive frames, with rms/min/max
temper-lcr capture PORT 100 fixture-1 1500,27500,60500 coil.json [--mv=MV] [--skip=PERIODS] [--periods=N | --seconds=S]
temper-lcr capture-wave PORT 100 fixture-1 wave.txt 3,7,11 multi.json [--skip=PERIODS] [--periods=N | --seconds=S]
temper-lcr tone-plan 100 1500,27500,60500        # no device: what capture will do per frequency
temper-lcr refcheck PORT 5000 1500,27500 ref.json [--mv=MV] [--skip=PERIODS] [--periods=N | --seconds=S]
```

`refcheck PORT RANGE_OHM FREQ... OUT` measures the internal 1 kΩ 0.1 % reference (relay K4) on RANGE_OHM, for a drift or self check: `selftest`, `rails`, then per frequency `TONE` and `REFCAPTURE RANGE SKIP PERIODS`, and `OFF`. The firmware closes K4 together with that range, captures, then RESETs all relays and re-selects the range that was selected before, so the board's range is unchanged. It prints the uncalibrated |Z| and phase per frequency and saves an ordinary Rev E capture whose fixture is `internal-reference-1k`. K4 adds the reference across HCUR–LCUR without disconnecting the jacks, so leave the DUT terminals open. The default level is 1700 mV on every range. The range resistor RG (equal to R_F) and R104 (47 Ω) sit in series with the reference, so the current channel stays below the source level and cannot clip (`reference_default_mv`). Compare readings over time on the same range and frequency. The reference does not pass through the external fixture, so a fixture calibration does not apply to it.

This host speaks the firmware's default 187.5 kHz build. The firmware's opt-in 375 kHz build (`INFO … 108000000 375000 …`, `temper-lcr-rev-e-375k.uf2`) is refused by name, because the tone, settling and capture-length rules here assume 187.5 kHz.

`capture PORT RANGE_OHM FIXTURE FREQ... OUT` keeps Rev D's argument shape, but on Rev E the range is commanded (`RANGE`), not just recorded: `selftest`, `rails`, `range`, then per frequency `TONE` and `CAPTURE`, and `OFF` at the end (also on exit). The default level is 1700 mV, the cap the noise check assumes: pick a lower `--mv` when `capture` reports clipping. Payloads are decoded and CRC-checked exactly as the firmware sends them (16-byte int32 header A min, A max, B min, B max; `DATA` body int64 A, B per bin; `RAW` body int32 A, B per frame; IEEE CRC32 over header and body; `END` terminator), and replies that do not match the request are errors. The host checks the firmware's limits before sending: period 16 to 4096, tone at most 85 kHz, level 1 to 1700 mV, every `WAVE` word within ±1,419,797,733, a capture within 60 s, `RAW` at most 8192 frames.

### Exact frequencies

`tone-hz`, `capture` and `tone-plan` take a frequency in hertz and pick the smallest `PERIOD` from 16 to 4096 for which it is exactly `187500 × CYCLES / PERIOD`: 1 kHz is 2/375, 27 kHz is 18/125, 60 kHz is 8/25, 37.5 kHz is 4/20 (the reduced 1/5 is below the 16-frame minimum). A frequency that no such period represents (1000.5 Hz) or above 85 kHz is refused, with the nearest exact tone named, because an inexact tone is not coherent and the one DFT line would leak.

### Analysis

For each requested bin the host divides each bin sum by `PERIODS`, takes the DFT line at that bin for A and B (a peak phasor in 24-bit codes, the Rev D convention `a − jb`), and forms

`Z = −(R_iso + R_F‖C104) × (A/B) / (1 + jωC0·R_iso)`

with `R_iso = 22 Ω`, `C104 = 100 pF`, `C0 = 100 pF` (the new capacitor from DUT_LO to ground), and `R_F` from the range. The divider `K = 0.5` is the same on both channels and cancels. The last factor exists because `I_dut = I_Riso × (1 + jωC0·R_iso)`: the 100 pF takes a small part of the DUT current ahead of R_iso (0.12 % of the current at 85 kHz). The virtual-instrument test solves the circuit independently of this formula, and fails when the factor is removed.

**Channel B sign.** CH2 is LOW follower (IN2P) minus TIA output (IN2M), as Rev D channel B, so B = `K·I·(R_iso + Z_f)` and A = `K·I_dut·Z` carry the same sign. The calibration gain `a` would absorb a reversed pair, but the uncalibrated reading of a known resistor on the first board confirms the wiring (it reads negative if the pins are swapped).

**Checks.**
- **Clipping:** from the header extremes, a channel is clipped at 99.8 % of ±2²³ (256 × 32700, Rev D's margin); the record and the measurement say which channel.
- **Weak signal:** a tone phasor below 4096 codes (Rev D's 16 of 32768, scaled to 24 bits) is rejected.
- **Residual:** the rms of everything outside DC and the requested bins, relative to the rms inside them; at or above 5 % the measurement is invalid. A captured stream is coherent, so this is distortion, interference or noise, not leakage.
- **Consistency:** extremes ordered and 24-bit, every bin sum within `PERIODS × [min, max]`, CRC, bin and tone rules.

Multitone: `capture-wave` uploads a waveform and analyses every bin you list, one measurement each; the residual is what is left outside all listed bins. A calibration point is per frequency (equal `CYCLES/PERIOD` as a fraction), so 8/25 and 16/50 share one.

### Settling and capture length

`CAPTURE SKIP PERIODS` skips whole periods. The default `SKIP` covers `2 × 17` codec filter frames with a factor-2 margin, a floor of 2 ms (or four tone periods at low frequency) for the DC-coupled source and a resistive or capacitive DUT, and 20 feedback time constants `R_F × C104` of the selected range, rounded up to whole periods. The default length is the smallest whole number of periods that sums at least 0.25 s, inside the 0.16 to 0.33 s that `../validation/rev-e-codec/` shows brings the worst target to about 4 % of its tolerance. `tone-plan` prints both (range 100 Ω):

| Frequency | CYCLES/PERIOD | Settle | SKIP periods | PERIODS | Capture |
|---:|---:|---:|---:|---:|---:|
| 45.776 Hz | 1/4096 | 87.7 ms | 5 | 12 | 0.262 s |
| 1000 Hz | 2/375 | 4.36 ms | 3 | 125 | 0.25 s |
| 1500 Hz | 1/125 | 3.03 ms | 5 | 375 | 0.25 s |
| 27 kHz | 18/125 | 2.36 ms | 4 | 375 | 0.25 s |
| 60 kHz | 8/25 | 2.36 ms | 18 | 1875 | 0.25 s |
| 85 kHz | 34/75 | 2.36 ms | 6 | 625 | 0.25 s |

Override with `--skip=PERIODS` and `--periods=N` or `--seconds=S`. **A coil's L/R time constant and the codec's input coupling (1 µF into 40 kΩ, a 40 ms time constant whose transient is nearly DC) are not waited for by default**; raise `--skip` for a large inductance and check that the residual stays small. USB start-of-frame lines sit at every multiple of 1 kHz of the host's clock (±560 ppm), and a coherent line has no defence on top of one: `capture` warns when a frequency is inside that reach (1 kHz, 27 kHz, 60 kHz and 85 kHz in the table are; 1500 Hz and 45.776 Hz are not). Use the half-kHz grid 1500, 27500, 35500, 40500, 50500, 60500 Hz: every point is an exact tone (1/125, 11/75, 71/375, 27/125, 101/375, 121/375) with −51 to −54 dB SOF rejection ([power-spurs Rev E](../validation/power-spurs/README-rev-e.md)). Rev D's DDS-harmonic and boxcar hazard checks do not apply and are not run.

### Calibration

`calibrate` fits `measured = (a·true + b)/(c·true + 1)` per bin from a short and two resistors, as Rev D (the same `calibration_coefficients`). The Rev E calibration file is schema 1, model `bilinear-short-two-resistors-e1-riso22-lo100p-codec-dft`, with the setup (`E-codec`, unit, fixture, range, 120 MHz, 187.5 kHz), the feedback capacitance, the isolation resistor and the DUT_LO capacitance; `analyze` and `validate` refuse any mismatch. There is no source-off record on Rev E (the OFF command and `raw` can be used to look at the quiet board by hand), so `--allow-source-off-fail` is refused.

```sh
temper-lcr capture PORT 100 fixture-1 1500,27500,60500 short.json --mv=200
# Replace the short with standard 1, then standard 2 (and pick --mv so neither channel clips).
temper-lcr capture PORT 100 fixture-1 1500,27500,60500 load20.json --mv=500
temper-lcr capture PORT 100 fixture-1 1500,27500,60500 load100.json --mv=500
temper-lcr calibrate short.json load20.json 20.000 load100.json 100.000 calibration.json
temper-lcr analyze dut.json calibration.json
```

**Characterized standards (`--standards=KIT.json`).** The numeric form assumes a 0 Ω short and purely real resistors. With a standards file, `calibrate` and `validate` take standard names instead of ohms, and the short is the entry `SHORT`:

```sh
temper-lcr calibrate short.json r1.json R1 r3.json R3 calibration.json --standards=kit-SN03.json
temper-lcr validate r2.json calibration.json R2 0.1 --standards=kit-SN03.json
```

- **File.** Schema `temper-lcr-standards-1`: a `kit` string, an optional `temperature_c`, and `standards` by name, each `{"r_ohm", "l_h", "c_f"}`.
  - The model is R in series with L, the pair shunted by C; L and C default to 0.
  - Unknown fields, negative R or C, and |L| > 1 mH or C > 1 µF are refused, which catches unit slips.
  - The format and where each number comes from are in [../calkit/CHARACTERIZE.md](../calkit/CHARACTERIZE.md) §1.
- **Fit.** `calibrate_e_standards` solves the bilinear fit through the three complex impedances at each bin's frequency (`calibration_coefficients_e`). With a zero short and real loads it equals `calibration_coefficients`.
- **Record.** The calibration file records the values used (`standards`: `short`, `load1`, `load2`) and the kit string (`standards_kit`). The fields are optional, so the schema stays 1.
- **Validate.** `validate` compares against the named standard's complex impedance at each frequency.
- **What it buys** (simulation, [accuracy map](../validation/rev-e-accuracy-map/README.md) §3). The 100 kΩ range at 85 kHz goes from 1.2 % to 0.42 % (typical). With the cal kit's 1 MΩ standard R11 as LOAD2, 1 MΩ at 1 kHz goes from 0.40 % to 0.064 %.
- **Rev D** refuses `--standards`.

### Tests

`tests/rev_e.rs` holds the Rev E tests next to Rev D's `tests/cli.rs` (which passes unchanged): payload round trips, CRC and length errors; exact period selection; settling defaults; a virtual instrument that solves the circuit (source, DUT, the 100 pF at DUT_LO, R_iso, the TIA, K = 0.5), applies the −5 frame offset, quantises to 24 bits, clips and sums into int64 bins, and recovers R, C, coil and tank DUTs on all three ranges, clipping, residual and multitone cases, and a three-standard calibration through a lossy fixture; characterized standards (the complex fit equals the real one for ideal standards, and removes a short's 5 nH and the loads' 0.2–0.3 pF on the 100 Ω and 100 kΩ ranges, where the real-valued fit does not), standards-file checks, and `--standards` through the CLI; the identity and schema cross-rejection; the client and CLI end to end against a fake protocol-3 firmware on a pseudo-terminal, `REFCAPTURE`/`refcheck` included (the 1 kΩ comes back within 0.2 % on all three ranges, and the range is unchanged afterwards). `firmware_host_contract_rev_e` reads the constants from `../firmware-rev-e/src` so the two cannot drift silently.

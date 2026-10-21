//! Rev E (`E-codec`, protocol 3): TAC5112 codec front end.
//!
//! The Rev E firmware plays a waveform of `PERIOD` DAC words at exactly 187.5 kHz and sums the
//! codec's two 24-bit channels into one int64 bin per waveform index, over any number of
//! periods. Source and capture are coherent by construction, so the analysis is one exact DFT
//! line per requested bin: no window, no fit, no non-coherent frequency. Rev D lives in
//! `lib.rs` and is untouched; nothing here changes its file formats.
//! Digital tests do not establish the accuracy of an unbuilt analog instrument.
use crate::{
    calibration_coefficients, crc32, feedback, feedback_capacitance_pf, Complex, Result,
    ISOLATION_RESISTOR_OHM,
};
use serde::{Deserialize, Serialize};
use std::f64::consts::TAU;

// ------------------------------------------------------------------ constants (wave.h, main.c)
/// USB wire protocol of the Rev E firmware.
pub const PROTOCOL_VERSION_E: u32 = 3;
pub const HARDWARE_REVISION_E: &str = "E-codec";
/// Frame rate: 120 MHz / 10 = 12 MHz BCLK, 64 BCLK per frame. Exact.
pub const SAMPLE_RATE_HZ: u32 = 187_500;
pub const SYSTEM_CLOCK_HZ_E: u32 = 120_000_000;
/// The firmware's opt-in 375 kHz build (`LCR_FS_375K`): 108 MHz / 6, 48 BCLK per frame. This
/// host's tone, settling and length rules assume 187.5 kHz, so it refuses that build by name.
pub const SAMPLE_RATE_375K_HZ: u32 = 375_000;
pub const SYSTEM_CLOCK_375K_HZ: u32 = 108_000_000;
pub const MIN_PERIOD: u32 = 16;
pub const MAX_PERIOD: u32 = 4096;
/// Highest tone the firmware accepts (wideband-mode passband, 0.454 fs).
pub const TONE_MAX_HZ: u32 = 85_000;
pub const TONE_MAX_MV: u32 = 1700;
/// Default source level of the capture commands: the cap, which the noise check assumes.
pub const DEFAULT_TONE_MV: u32 = TONE_MAX_MV;
/// `SOURCE_LIMIT_CODE`: every DAC word must lie within +-this (1.7 V peak at SOURCE_BUF).
pub const SOURCE_LIMIT_CODE: i32 = 1_419_797_733;
/// Largest frame count of one `RAW` request.
pub const RAW_MAX_FRAMES: u32 = 8192;
/// A capture (skip plus summed frames) may last at most this many seconds.
pub const MAX_CAPTURE_SECONDS: u64 = 60;
/// Capture frame j meets DAC word (j - 5) mod PERIOD at the pins (firmware README, Alignment).
pub const FRAME_OFFSET: usize = 5;
/// 24-bit ADC samples: full scale is +-2^23.
pub const ADC_FULL_SCALE_CODE: i64 = 8_388_608;
/// Same 0.2 % margin as Rev D's 32700 of 32768: 256 x 32700.
pub const CLIP_CODE_E: i64 = 256 * 32_700;
/// Both codec channels pass through identical 1k/1k dividers. It cancels in A/B.
pub const CHANNEL_DIVIDER_K: f64 = 0.5;
/// Fixed C0G from DUT_LO to ground ahead of R_iso (new in Rev E).
pub const DUT_LO_CAPACITOR_PF: f64 = 100.0;
/// Calibration file schema and model for E-codec. Rev D's are 5 and its own model string.
pub const CALIBRATION_SCHEMA_VERSION_E: u32 = 1;
pub const CALIBRATION_MODEL_E: &str = "bilinear-short-two-resistors-e1-riso22-lo100p-codec-dft";
/// Smallest tone phasor (single-sample codes) accepted as a signal: Rev D's 16 of 32768,
/// scaled to 24 bits.
pub const MIN_TONE_CODES: f64 = 4096.0;
/// Energy outside the requested bins, relative to the energy inside them (rms ratio).
pub const MAX_RESIDUAL_RATIO: f64 = 0.05;

// ------------------------------------------------------------------ identity
/// Parsed `INFO 3 E-codec UNIT_ID SYSCLK FS MAX_PERIOD RANGE PERIOD CYCLES MV PASS|FAIL`.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct InfoE {
    pub unit_id: String,
    pub system_clock_hz: u32,
    pub sample_rate_hz: u32,
    pub max_period: u32,
    /// Selected range relay in ohms; 0 when the firmware could not select one at boot.
    pub range_ohm: u32,
    pub period: u32,
    /// 0 for silence or an uploaded waveform.
    pub cycles: u32,
    pub mv: u32,
    pub self_test_pass: bool,
}
pub fn parse_info_e(line: &str) -> Result<InfoE> {
    let w: Vec<_> = line.split_whitespace().collect();
    let bad = || format!("unexpected device identity: {line}");
    if w.len() != 12 || w[0] != "INFO" {
        return Err(bad());
    }
    if w[1] != PROTOCOL_VERSION_E.to_string() {
        return Err(bad());
    }
    if w[2] != HARDWARE_REVISION_E {
        return Err(format!(
            "protocol-3 firmware with identity {} (this host knows {HARDWARE_REVISION_E}): {line}",
            w[2]
        ));
    }
    let number = |i: usize| w[i].parse::<u32>().map_err(|_| bad());
    if (number(4)?, number(5)?) == (SYSTEM_CLOCK_375K_HZ, SAMPLE_RATE_375K_HZ) {
        return Err(format!(
            "this is the firmware's 375 kHz build (temper-lcr-rev-e-375k.uf2); this host speaks the default {SAMPLE_RATE_HZ} Hz build only: flash temper-lcr-rev-e.uf2 ({line})"
        ));
    }
    let info = InfoE {
        unit_id: w[3].into(),
        system_clock_hz: number(4)?,
        sample_rate_hz: number(5)?,
        max_period: number(6)?,
        range_ohm: number(7)?,
        period: number(8)?,
        cycles: number(9)?,
        mv: number(10)?,
        self_test_pass: match w[11] {
            "PASS" => true,
            "FAIL" => false,
            _ => return Err(bad()),
        },
    };
    if info.system_clock_hz != SYSTEM_CLOCK_HZ_E
        || info.sample_rate_hz != SAMPLE_RATE_HZ
        || info.max_period != MAX_PERIOD
        || !(MIN_PERIOD..=MAX_PERIOD).contains(&info.period)
        || ![0, 100, 5000, 100_000].contains(&info.range_ohm)
    {
        return Err(bad());
    }
    Ok(info)
}

/// Which board answered `INFO`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Protocol {
    /// Rev D, protocol 2, `D-riso22` (and anything else the Rev D identity check reports on).
    D,
    /// Rev E, protocol 3, `E-codec`.
    E,
}
/// Selects the protocol from the INFO reply. Mixed protocol/identity pairs are refused here;
/// every other reply is left to the Rev D identity check, which owns the older-board messages.
pub fn detect_protocol(line: &str) -> Result<Protocol> {
    let w: Vec<_> = line.split_whitespace().collect();
    match (w.first().copied(), w.get(1).copied(), w.get(2).copied()) {
        (Some("INFO"), Some("3"), Some(HARDWARE_REVISION_E)) => Ok(Protocol::E),
        (Some("INFO"), Some("3"), _) => Err(format!(
            "protocol-3 firmware must identify as {HARDWARE_REVISION_E}: {line}"
        )),
        (Some("INFO"), Some("2"), Some(HARDWARE_REVISION_E)) => Err(format!(
            "identity {HARDWARE_REVISION_E} is a protocol-3 board but the reply says protocol 2: {line}"
        )),
        (Some("INFO"), Some("2"), Some(crate::HARDWARE_REVISION)) => Ok(Protocol::D),
        _ => Ok(Protocol::D),
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SetupE {
    pub revision: String,
    pub unit_id: String,
    pub fixture: String,
    pub range_ohm: u32,
    pub system_clock_hz: u32,
    pub sample_rate_hz: u32,
}
impl SetupE {
    pub fn from_info(info: &InfoE, range_ohm: u32, fixture: &str) -> Result<Self> {
        let setup = Self {
            revision: HARDWARE_REVISION_E.into(),
            unit_id: info.unit_id.clone(),
            fixture: fixture.into(),
            range_ohm,
            system_clock_hz: info.system_clock_hz,
            sample_rate_hz: info.sample_rate_hz,
        };
        setup.validate()?;
        Ok(setup)
    }
    pub fn validate(&self) -> Result<()> {
        if self.revision != HARDWARE_REVISION_E
            || self.unit_id.is_empty()
            || self.fixture.is_empty()
            || self.system_clock_hz != SYSTEM_CLOCK_HZ_E
            || self.sample_rate_hz != SAMPLE_RATE_HZ
        {
            return Err("capture metadata does not describe the E-codec instrument".into());
        }
        feedback(self.range_ohm, 1000.0)?;
        Ok(())
    }
}

// ------------------------------------------------------------------ source rules
pub fn tone_frequency_hz(cycles: u32, period: u32) -> f64 {
    f64::from(SAMPLE_RATE_HZ) * f64::from(cycles) / f64::from(period)
}
/// The firmware's `TONE` rules, in its order: period, frequency, level.
pub fn check_tone(cycles: u32, period: u32, mv: u32) -> Result<()> {
    if !(MIN_PERIOD..=MAX_PERIOD).contains(&period) {
        return Err(format!("period must be {MIN_PERIOD}..{MAX_PERIOD} frames"));
    }
    if cycles == 0
        || u64::from(SAMPLE_RATE_HZ) * u64::from(cycles)
            > u64::from(TONE_MAX_HZ) * u64::from(period)
    {
        return Err(format!(
            "tone frequency must be above 0 Hz and at most {TONE_MAX_HZ} Hz"
        ));
    }
    if mv == 0 || mv > TONE_MAX_MV {
        return Err(format!("tone level must be 1..{TONE_MAX_MV} mV peak"));
    }
    Ok(())
}
/// Smallest `PERIOD` (at least the firmware minimum of 16, at most 4096) for which `hz` is
/// exactly `187500 * CYCLES / PERIOD`, and its CYCLES. Frequencies that no period represents
/// exactly, and those above 85 kHz, are refused: with an inexact tone the capture would not be
/// coherent and the single DFT line would leak.
pub fn tone_for_hz(hz: f64) -> Result<(u32, u32)> {
    if !hz.is_finite() || hz <= 0.0 {
        return Err("frequency must be positive".into());
    }
    if hz > f64::from(TONE_MAX_HZ) {
        return Err(format!(
            "{hz} Hz exceeds the {TONE_MAX_HZ} Hz the wideband codec path supports"
        ));
    }
    let fs = f64::from(SAMPLE_RATE_HZ);
    let mut nearest: Option<(f64, u32, u32)> = None;
    for period in MIN_PERIOD..=MAX_PERIOD {
        let ideal = hz * f64::from(period) / fs;
        let cycles = ideal.round();
        if cycles >= 1.0 {
            let candidate = fs * cycles / f64::from(period);
            if (ideal - cycles).abs() <= 1e-9 * ideal.max(1.0) {
                let cycles = cycles as u32;
                check_tone(cycles, period, 1)?;
                return Ok((cycles, period));
            }
            if candidate <= f64::from(TONE_MAX_HZ)
                && nearest.is_none_or(|(d, _, _)| (candidate - hz).abs() < d)
            {
                nearest = Some(((candidate - hz).abs(), cycles as u32, period));
            }
        }
    }
    let hint = nearest
        .map(|(_, c, p)| {
            format!(
                "; the nearest exact tone is {} Hz ({c}/{p})",
                tone_frequency_hz(c, p)
            )
        })
        .unwrap_or_default();
    Err(format!(
        "{hz} Hz cannot be represented exactly as 187500 x CYCLES / PERIOD with PERIOD {MIN_PERIOD}..{MAX_PERIOD}{hint}"
    ))
}
/// Host-side `WAVE` rules: legal period and every word within +-SOURCE_LIMIT_CODE.
pub fn check_wave(words: &[i32]) -> Result<()> {
    if !(MIN_PERIOD as usize..=MAX_PERIOD as usize).contains(&words.len()) {
        return Err(format!(
            "waveform must have {MIN_PERIOD}..{MAX_PERIOD} words, got {}",
            words.len()
        ));
    }
    if let Some((k, w)) = words
        .iter()
        .enumerate()
        .find(|(_, &w)| !(-SOURCE_LIMIT_CODE..=SOURCE_LIMIT_CODE).contains(&w))
    {
        return Err(format!(
            "waveform word {k} ({w}) exceeds the source limit +-{SOURCE_LIMIT_CODE}"
        ));
    }
    Ok(())
}
/// Little-endian int32 body of a `WAVE` upload and its CRC32 (checked first).
pub fn encode_wave(words: &[i32]) -> Result<(Vec<u8>, u32)> {
    check_wave(words)?;
    let bytes: Vec<u8> = words.iter().flat_map(|w| w.to_le_bytes()).collect();
    let crc = crc32(&bytes);
    Ok((bytes, crc))
}
/// Waveform file: whitespace- or comma-separated decimal int32 DAC words, `#` comments.
pub fn parse_wave_text(text: &str) -> Result<Vec<i32>> {
    let mut words = Vec::new();
    for line in text.lines() {
        let line = line.split('#').next().unwrap_or("");
        for field in line.split(|c: char| c.is_whitespace() || c == ',') {
            if !field.is_empty() {
                words.push(
                    field
                        .parse::<i32>()
                        .map_err(|_| format!("waveform word is not an int32: {field}"))?,
                );
            }
        }
    }
    check_wave(&words)?;
    Ok(words)
}
/// Bins must lie strictly below Nyquist, and a tone bin at most 85 kHz.
pub fn check_bins(bins: &[u32], period: u32) -> Result<()> {
    if bins.is_empty() {
        return Err("no analysis bins requested".into());
    }
    let mut sorted = bins.to_vec();
    sorted.sort_unstable();
    if sorted.windows(2).any(|w| w[0] == w[1]) {
        return Err("analysis bins must be distinct".into());
    }
    for &bin in bins {
        if bin == 0 || 2 * u64::from(bin) >= u64::from(period) {
            return Err(format!(
                "bin {bin} must be 1..{} for period {period}",
                (period - 1) / 2
            ));
        }
        if u64::from(SAMPLE_RATE_HZ) * u64::from(bin) > u64::from(TONE_MAX_HZ) * u64::from(period) {
            return Err(format!(
                "bin {bin} of period {period} is {} Hz, above {TONE_MAX_HZ} Hz",
                tone_frequency_hz(bin, period)
            ));
        }
    }
    Ok(())
}

// ------------------------------------------------------------------ settling and length
/// Codec decimation and DAC interpolation filters, frames each way (firmware README).
pub const CODEC_FILTER_FRAMES: u32 = 17;
/// Safety factor on the 2 x 17 filter frames.
pub const FILTER_SETTLE_MARGIN: u32 = 2;
/// The DC-coupled source and a resistive or capacitive DUT settle in microseconds; this floor is
/// what the host waits regardless of frequency. A coil's L/R time constant is not known to the
/// host: pass a larger `--skip`.
pub const SOURCE_SETTLE_FLOOR_S: f64 = 2e-3;
/// Tone periods the DUT network gets to settle at low frequencies.
pub const SETTLE_TONE_PERIODS: f64 = 4.0;
/// TIA feedback time constants waited for (RF x C104).
pub const SETTLE_TIA_TAU: f64 = 20.0;
/// Default summed capture time: 10x Rev D's 16-33 ms capture at the Temper targets, which the
/// codec noise check shows brings the worst target to about 4 % of its tolerance.
pub const DEFAULT_CAPTURE_SECONDS: f64 = 0.25;
/// Time to discard after a `TONE`/`WAVE` or `RANGE` change at `hz` on `range`.
pub fn settle_seconds(range: u32, hz: f64) -> Result<f64> {
    if !hz.is_finite() || hz <= 0.0 {
        return Err("frequency must be positive".into());
    }
    let filters =
        f64::from(2 * CODEC_FILTER_FRAMES * FILTER_SETTLE_MARGIN) / f64::from(SAMPLE_RATE_HZ);
    let tia = SETTLE_TIA_TAU * f64::from(range) * feedback_capacitance_pf(range)? * 1e-12;
    Ok(filters + tia + SOURCE_SETTLE_FLOOR_S.max(SETTLE_TONE_PERIODS / hz))
}
/// Whole periods to skip: the settle time rounded up, at least 0.
pub fn default_skip_periods(range: u32, hz: f64, period: u32) -> Result<u32> {
    let frames = (settle_seconds(range, hz)? * f64::from(SAMPLE_RATE_HZ)).ceil();
    Ok((frames / f64::from(period)).ceil() as u32)
}
/// Whole periods summed by default: at least `DEFAULT_CAPTURE_SECONDS`, at least one.
pub fn default_periods(period: u32) -> u32 {
    ((DEFAULT_CAPTURE_SECONDS * f64::from(SAMPLE_RATE_HZ) / f64::from(period)).ceil() as u32).max(1)
}
/// Whole periods for a requested summed time.
pub fn periods_for_seconds(seconds: f64, period: u32) -> Result<u32> {
    if !seconds.is_finite() || seconds <= 0.0 || seconds > MAX_CAPTURE_SECONDS as f64 {
        return Err(format!("capture time must be 0..{MAX_CAPTURE_SECONDS} s"));
    }
    Ok(((seconds * f64::from(SAMPLE_RATE_HZ) / f64::from(period)).ceil() as u32).max(1))
}
/// The firmware's capture limits, checked before sending: SKIP + PERIODS whole periods within 60 s.
pub fn check_capture(skip: u32, periods: u32, period: u32) -> Result<()> {
    let frames = u64::from(periods) * u64::from(period);
    let total = u64::from(skip) * u64::from(period) + frames;
    if periods == 0 || total > MAX_CAPTURE_SECONDS * u64::from(SAMPLE_RATE_HZ) {
        return Err(format!(
            "capture of {skip} + {periods} periods of {period} frames must be 1..{MAX_CAPTURE_SECONDS} s"
        ));
    }
    Ok(())
}
pub fn capture_seconds(skip: u32, periods: u32, period: u32) -> f64 {
    (f64::from(skip) + f64::from(periods)) * f64::from(period) / f64::from(SAMPLE_RATE_HZ)
}

// ------------------------------------------------------------------ internal reference (K4)
/// The internal reference K4 switches across HCUR-LCUR for `REFCAPTURE`: 1 kOhm, 0.1 %.
pub const REFERENCE_OHM: f64 = 1000.0;
pub const REFERENCE_TOLERANCE: f64 = 1e-3;
/// Fixture name of `refcheck` captures: the reference bypasses the external fixture.
pub const REFERENCE_FIXTURE: &str = "internal-reference-1k";
/// Current-channel peak at the TIA output that reaches ADC full scale: 2 Vrms differential
/// (2.828 V peak) behind the 1k/1k divider (`CHANNEL_DIVIDER_K`).
pub const TIA_FULL_SCALE_PEAK_V: f64 = 2.0 * std::f64::consts::SQRT_2 / CHANNEL_DIVIDER_K;
/// R104 between the source driver and the range resistor. The range resistor RG equals R_F and
/// sits in series with DUT_HI, so the source sees RG + R104 + the DUT + R_iso.
pub const SOURCE_SERIES_OHM: f64 = 47.0;
/// Default `refcheck` level on `range`: the current channel at 75 % of full scale with the
/// reference as the DUT at DC, behind RG + R104, capped at the source limit. RG equals R_F, so
/// the channel stays below the source level and the default is 1700 mV on every range.
pub fn reference_default_mv(range: u32) -> Result<u32> {
    feedback(range, 1000.0)?;
    let iso = ISOLATION_RESISTOR_OHM;
    let rf = f64::from(range);
    let mv = 0.75 * TIA_FULL_SCALE_PEAK_V * 1000.0 * (rf + SOURCE_SERIES_OHM + REFERENCE_OHM + iso)
        / (rf + iso);
    Ok((mv.floor() as u32).clamp(1, TONE_MAX_MV))
}

/// What the capture commands will do for one frequency on one range, without a device.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct TonePlan {
    pub frequency_hz: f64,
    pub cycles: u32,
    pub period: u32,
    pub settle_seconds: f64,
    pub skip_periods: u32,
    pub periods: u32,
    pub capture_seconds: f64,
    /// Fraction of a nearby USB SOF line the capture does not reject (see [`sof_response`]).
    pub sof_response: f64,
}
pub fn tone_plan(range: u32, hz: f64) -> Result<TonePlan> {
    let (cycles, period) = tone_for_hz(hz)?;
    let skip_periods = default_skip_periods(range, hz, period)?;
    let periods = default_periods(period);
    let capture_seconds = capture_seconds(0, periods, period);
    Ok(TonePlan {
        frequency_hz: tone_frequency_hz(cycles, period),
        cycles,
        period,
        settle_seconds: settle_seconds(range, hz)?,
        skip_periods,
        periods,
        capture_seconds,
        sof_response: sof_response(hz, capture_seconds),
    })
}
/// USB start-of-frame lines sit at every multiple of 1 kHz of the host's clock, +-560 ppm against
/// ours. A coherent DFT line has no defence against one that lands on the bin. Response of a
/// rectangular window of `seconds` to the nearest SOF line (1 = none rejected); above 0.1 is the
/// Rev D hazard criterion. The capture still runs: this is advice for the operator.
pub fn sof_response(hz: f64, seconds: f64) -> f64 {
    let harmonic = (hz / 1000.0).round().max(1.0) * 1000.0;
    let band = harmonic * 560e-6;
    let distance = ((hz - harmonic).abs() - band).max(0.0);
    let x = std::f64::consts::PI * distance * seconds;
    if x < 1e-12 {
        1.0
    } else {
        (x.sin() / x).abs()
    }
}

// ------------------------------------------------------------------ wire payloads
pub const HEADER_BYTES: usize = 16;
pub fn data_payload_len(period: usize) -> usize {
    HEADER_BYTES + 16 * period
}
pub fn raw_payload_len(count: usize) -> usize {
    HEADER_BYTES + 8 * count
}
fn i32_at(bytes: &[u8], at: usize) -> i32 {
    i32::from_le_bytes([bytes[at], bytes[at + 1], bytes[at + 2], bytes[at + 3]])
}
fn i64_at(bytes: &[u8], at: usize) -> i64 {
    let mut b = [0u8; 8];
    b.copy_from_slice(&bytes[at..at + 8]);
    i64::from_le_bytes(b)
}
fn header_of(bytes: &[u8]) -> [i32; 4] {
    [
        i32_at(bytes, 0),
        i32_at(bytes, 4),
        i32_at(bytes, 8),
        i32_at(bytes, 12),
    ]
}
/// `DATA` payload: header (A min, A max, B min, B max as int32), then A sum and B sum as int64
/// per bin. The CRC the firmware sends covers all of it.
pub fn encode_data(header: [i32; 4], sums: &[[i64; 2]]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(data_payload_len(sums.len()));
    bytes.extend(header.iter().flat_map(|v| v.to_le_bytes()));
    for pair in sums {
        bytes.extend(pair[0].to_le_bytes());
        bytes.extend(pair[1].to_le_bytes());
    }
    bytes
}
pub type DataPayload = ([i32; 4], Vec<[i64; 2]>);
/// Inverse of [`encode_data`]; the length must be exactly 16 + 16 x `period`.
pub fn decode_data(bytes: &[u8], period: usize) -> Result<DataPayload> {
    if bytes.len() != data_payload_len(period) {
        return Err(format!(
            "protocol-3 DATA payload is {} bytes, expected 16 + 16 x {period} = {}",
            bytes.len(),
            data_payload_len(period)
        ));
    }
    let sums = bytes[HEADER_BYTES..]
        .chunks_exact(16)
        .map(|c| [i64_at(c, 0), i64_at(c, 8)])
        .collect();
    Ok((header_of(bytes), sums))
}
/// `RAW` payload: header, then A and B as int32 per frame.
pub fn encode_raw(header: [i32; 4], frames: &[[i32; 2]]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(raw_payload_len(frames.len()));
    bytes.extend(header.iter().flat_map(|v| v.to_le_bytes()));
    for f in frames {
        bytes.extend(f[0].to_le_bytes());
        bytes.extend(f[1].to_le_bytes());
    }
    bytes
}
pub type RawPayload = ([i32; 4], Vec<[i32; 2]>);
pub fn decode_raw(bytes: &[u8], count: usize) -> Result<RawPayload> {
    if bytes.len() != raw_payload_len(count) {
        return Err(format!(
            "protocol-3 RAW payload is {} bytes, expected 16 + 8 x {count} = {}",
            bytes.len(),
            raw_payload_len(count)
        ));
    }
    let frames = bytes[HEADER_BYTES..]
        .chunks_exact(8)
        .map(|c| [i32_at(c, 0), i32_at(c, 4)])
        .collect();
    Ok((header_of(bytes), frames))
}
pub fn verify_crc(bytes: &[u8], expected: u32) -> Result<()> {
    let actual = crc32(bytes);
    if actual != expected {
        return Err(format!(
            "USB payload CRC mismatch (device {expected:#010x}, host {actual:#010x})"
        ));
    }
    Ok(())
}
/// `DATA 3 PERIOD PERIODS CRC32` or `RAW 3 COUNT 0 CRC32`: the three numbers after the protocol.
pub fn parse_reply_header(line: &str, tag: &str) -> Result<(u32, u32, u32)> {
    let w: Vec<_> = line.split_whitespace().collect();
    if w.len() == 2 && w[0] == "ERR" {
        return Err(format!("device refused: {}", w[1]));
    }
    if w.len() != 5 || w[0] != tag || w[1] != PROTOCOL_VERSION_E.to_string() {
        return Err(format!("capture failed: {line}"));
    }
    let n = |i: usize| {
        w[i].parse::<u32>()
            .map_err(|_| format!("bad {tag} header: {line}"))
    };
    Ok((n(2)?, n(3)?, n(4)?))
}
/// Header extremes must be ordered and inside the 24-bit range.
pub fn check_header(header: [i32; 4]) -> Result<()> {
    let range = -(ADC_FULL_SCALE_CODE as i32)..=ADC_FULL_SCALE_CODE as i32 - 1;
    for (lo, hi) in [(header[0], header[1]), (header[2], header[3])] {
        if lo > hi || !range.contains(&lo) || !range.contains(&hi) {
            return Err("payload extremes are not ordered 24-bit codes".into());
        }
    }
    Ok(())
}
/// Summary of a `RAW` capture: single-sample codes per channel (A, B).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RawStats {
    pub frames: usize,
    pub mean_codes: [f64; 2],
    /// DC-removed rms.
    pub rms_codes: [f64; 2],
    pub min_code: [i32; 2],
    pub max_code: [i32; 2],
    pub clipped: [bool; 2],
}
pub fn raw_stats(frames: &[[i32; 2]]) -> RawStats {
    let n = frames.len().max(1) as f64;
    let mut stats = RawStats {
        frames: frames.len(),
        mean_codes: [0.0; 2],
        rms_codes: [0.0; 2],
        min_code: [i32::MAX; 2],
        max_code: [i32::MIN; 2],
        clipped: [false; 2],
    };
    for c in 0..2 {
        stats.mean_codes[c] = frames.iter().map(|f| f64::from(f[c])).sum::<f64>() / n;
        stats.rms_codes[c] = (frames
            .iter()
            .map(|f| (f64::from(f[c]) - stats.mean_codes[c]).powi(2))
            .sum::<f64>()
            / n)
            .sqrt();
        stats.min_code[c] = frames.iter().map(|f| f[c]).min().unwrap_or(0);
        stats.max_code[c] = frames.iter().map(|f| f[c]).max().unwrap_or(0);
        stats.clipped[c] = i64::from(stats.min_code[c]) <= -CLIP_CODE_E
            || i64::from(stats.max_code[c]) >= CLIP_CODE_E;
    }
    stats
}

// ------------------------------------------------------------------ records
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum SourceE {
    /// `TONE cycles period mv`: the one analysed bin is `cycles`.
    Tone { cycles: u32, mv: u32 },
    /// An uploaded waveform: the bins are the caller's choice.
    Wave,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RecordE {
    /// Must equal [`PROTOCOL_VERSION_E`].
    #[serde(default)]
    pub protocol: u32,
    pub source: SourceE,
    /// Waveform length in frames; the number of bins in `sums`.
    pub period: u32,
    /// Whole periods summed into each bin.
    pub periods: u32,
    /// Whole periods skipped before summing.
    pub skip: u32,
    /// DFT bins analysed: CYCLES for a tone, any bins for a waveform.
    pub bins: Vec<u32>,
    /// Single-sample extremes over the whole capture, [A, B].
    pub min: [i32; 2],
    pub max: [i32; 2],
    /// Per bin, [sum of A, sum of B] over `periods` periods.
    pub sums: Vec<[i64; 2]>,
    /// CRC32 of the payload (extremes header and sums) as received.
    pub transport_crc32: u32,
}
impl RecordE {
    pub fn payload(&self) -> Vec<u8> {
        encode_data(
            [self.min[0], self.max[0], self.min[1], self.max[1]],
            &self.sums,
        )
    }
    /// Per bin, single-sample codes: sum / periods.
    pub fn means(&self, channel: usize) -> Vec<f64> {
        let n = f64::from(self.periods);
        self.sums.iter().map(|s| s[channel] as f64 / n).collect()
    }
    /// True when any single sample on the channel reached 99.8 % of full scale.
    pub fn clipped(&self, channel: usize) -> bool {
        i64::from(self.min[channel]) <= -CLIP_CODE_E || i64::from(self.max[channel]) >= CLIP_CODE_E
    }
    pub fn validate(&self) -> Result<()> {
        if self.protocol != PROTOCOL_VERSION_E {
            return Err(format!(
                "capture record protocol {} is not {PROTOCOL_VERSION_E}: this is not an E-codec record",
                self.protocol
            ));
        }
        if !(MIN_PERIOD..=MAX_PERIOD).contains(&self.period)
            || self.sums.len() != self.period as usize
            || self.periods == 0
        {
            return Err("invalid capture period, bin count or number of periods".into());
        }
        check_bins(&self.bins, self.period)?;
        if let SourceE::Tone { cycles, mv } = self.source {
            if self.bins != [cycles] {
                return Err("a tone record analyses exactly its CYCLES bin".into());
            }
            check_tone(cycles, self.period, mv)?;
        }
        check_capture(self.skip, self.periods, self.period)?;
        check_header([self.min[0], self.max[0], self.min[1], self.max[1]])?;
        if crc32(&self.payload()) != self.transport_crc32 {
            return Err("capture CRC mismatch".into());
        }
        // Every bin sum of `periods` samples lies within periods x [min, max] of the samples.
        let n = i64::from(self.periods);
        for channel in 0..2 {
            let (lo, hi) = (i64::from(self.min[channel]), i64::from(self.max[channel]));
            if self
                .sums
                .iter()
                .any(|s| !(n * lo..=n * hi).contains(&s[channel]))
            {
                return Err("bin sums are inconsistent with the reported sample extremes".into());
            }
        }
        Ok(())
    }
    /// Builds a record from a decoded `DATA` reply.
    pub fn from_capture(
        source: SourceE,
        bins: Vec<u32>,
        skip: u32,
        periods: u32,
        payload: DataPayload,
        transport_crc32: u32,
    ) -> Self {
        let (h, sums) = payload;
        Self {
            protocol: PROTOCOL_VERSION_E,
            source,
            period: sums.len() as u32,
            periods,
            skip,
            bins,
            min: [h[0], h[2]],
            max: [h[1], h[3]],
            sums,
            transport_crc32,
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SweepE {
    pub setup: SetupE,
    pub records: Vec<RecordE>,
}

// ------------------------------------------------------------------ analysis
/// Exact DFT line at `bin` of one period of `means`, as a peak phasor in codes: for
/// x = a cos(theta n) + b sin(theta n) it returns a - j b, the same phasor convention as Rev D.
/// The capture is coherent, so no window and no fit are needed.
pub fn dft_line(means: &[f64], bin: u32) -> Complex {
    let p = means.len();
    let (mut re, mut im) = (0.0, 0.0);
    for (n, &x) in means.iter().enumerate() {
        let theta = TAU * (((bin as usize * n) % p) as f64) / p as f64;
        re += x * theta.cos();
        im -= x * theta.sin();
    }
    Complex::new(2.0 * re / p as f64, 2.0 * im / p as f64)
}
/// One channel at one bin.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct LineFit {
    /// Peak phasor of the bin, in single-sample codes.
    pub phasor_codes: Complex,
    pub dc_codes: f64,
    /// RMS of everything outside DC and the requested bins, in codes.
    pub residual_rms_codes: f64,
    /// That residual relative to the rms inside the requested bins (all requested bins together).
    pub residual_ratio: f64,
    pub min_code: i32,
    pub max_code: i32,
    /// Any single sample reached 99.8 % of the 24-bit full scale.
    pub clipped: bool,
}
impl LineFit {
    pub fn valid_signal(&self) -> bool {
        self.phasor_codes.abs() >= MIN_TONE_CODES && self.residual_ratio < MAX_RESIDUAL_RATIO
    }
}
/// Fits every requested bin of one channel.
pub fn fit_channel_bins(record: &RecordE, channel: usize) -> Vec<LineFit> {
    let means = record.means(channel);
    let n = means.len() as f64;
    let dc = means.iter().sum::<f64>() / n;
    let lines: Vec<Complex> = record.bins.iter().map(|&b| dft_line(&means, b)).collect();
    // Bins are distinct (check_bins), each below Nyquist: a real tone carries |phasor|^2 / 2.
    let in_band: f64 = lines.iter().map(|l| l.abs().powi(2) / 2.0).sum();
    let total = means.iter().map(|m| (m - dc).powi(2)).sum::<f64>() / n;
    let residual = (total - in_band).max(0.0).sqrt();
    let ratio = if in_band > 0.0 {
        residual / in_band.sqrt()
    } else {
        f64::INFINITY
    };
    lines
        .into_iter()
        .map(|phasor| LineFit {
            phasor_codes: phasor,
            dc_codes: dc,
            residual_rms_codes: residual,
            residual_ratio: ratio,
            min_code: record.min[channel],
            max_code: record.max[channel],
            clipped: record.clipped(channel),
        })
        .collect()
}
/// DUT current = current through R_iso times (1 + j w C0 R_iso): the 100 pF at DUT_LO takes
/// the rest of the DUT current to ground ahead of the resistor.
pub fn dut_lo_factor(hz: f64) -> Complex {
    Complex::new(
        1.0,
        TAU * hz * DUT_LO_CAPACITOR_PF * 1e-12 * ISOLATION_RESISTOR_OHM,
    )
}
/// Nominal Rev E impedance from the A/B phasor ratio: `Z = (R_iso + RF || C104) x (A/B) /
/// (1 + j w C0 R_iso)`. Channel B is LOW minus TIA as on Rev D, so B = K I (R_iso + Z_f) with
/// A = K I_dut Z; K = 0.5 is the same on both channels and cancels.
pub fn nominal_impedance(range: u32, hz: f64, a_over_b: Complex) -> Result<Complex> {
    Ok(feedback(range, hz)? * a_over_b / dut_lo_factor(hz))
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MeasurementE {
    pub frequency_hz: f64,
    pub cycles: u32,
    pub period: u32,
    pub raw_impedance_ohm: Complex,
    pub impedance_ohm: Complex,
    pub magnitude_ohm: f64,
    pub phase_degrees: f64,
    pub series_resistance_ohm: f64,
    pub series_inductance_h: Option<f64>,
    pub series_capacitance_f: Option<f64>,
    pub q: Option<f64>,
    pub voltage: LineFit,
    pub current: LineFit,
    pub calibrated: bool,
    pub valid: bool,
    pub issues: Vec<String>,
}
fn derived(m: &mut MeasurementE) {
    let z = m.impedance_ohm;
    m.magnitude_ohm = z.abs();
    m.phase_degrees = z.im.atan2(z.re).to_degrees();
    m.series_resistance_ohm = z.re;
    m.series_inductance_h = (z.im > 0.0).then(|| z.im / (TAU * m.frequency_hz));
    m.series_capacitance_f = (z.im < 0.0).then(|| -1.0 / (TAU * m.frequency_hz * z.im));
    m.q = (z.re > 0.0).then(|| z.im.abs() / z.re);
}
/// Analyses every requested bin of a record: one measurement per bin, in `bins` order.
pub fn analyze_e(record: &RecordE, range: u32) -> Result<Vec<MeasurementE>> {
    record.validate()?;
    let voltage = fit_channel_bins(record, 0);
    let current = fit_channel_bins(record, 1);
    let mut out = Vec::new();
    for (i, &bin) in record.bins.iter().enumerate() {
        let hz = tone_frequency_hz(bin, record.period);
        let (v, c) = (voltage[i].clone(), current[i].clone());
        if c.phasor_codes.abs() < 1e-9 {
            return Err("no current signal; open DUT or wrong range".into());
        }
        let z = nominal_impedance(range, hz, v.phasor_codes / c.phasor_codes)?;
        if !z.finite() {
            return Err("non-finite impedance".into());
        }
        let mut issues = Vec::new();
        for (name, fit) in [("A (voltage)", &v), ("B (current)", &c)] {
            if fit.clipped {
                issues.push(format!("ADC clipping on channel {name}"));
            }
        }
        if !c.valid_signal() {
            issues.push("current signal too weak or distorted".into());
        }
        if !v.valid_signal() {
            issues.push("voltage signal too weak or distorted".into());
        }
        let mut m = MeasurementE {
            frequency_hz: hz,
            cycles: bin,
            period: record.period,
            raw_impedance_ohm: z,
            impedance_ohm: z,
            magnitude_ohm: 0.0,
            phase_degrees: 0.0,
            series_resistance_ohm: 0.0,
            series_inductance_h: None,
            series_capacitance_f: None,
            q: None,
            voltage: v,
            current: c,
            calibrated: false,
            valid: issues.is_empty(),
            issues,
        };
        derived(&mut m);
        out.push(m);
    }
    Ok(out)
}

// ------------------------------------------------------------------ calibration
/// Version-checked capture loader. Rev D files and anything else fail with an explicit message.
pub fn parse_sweep_e(text: &str) -> Result<SweepE> {
    let value: serde_json::Value = serde_json::from_str(text).map_err(|e| e.to_string())?;
    match crate::file_revision(&value).as_deref() {
        Some(HARDWARE_REVISION_E) => {}
        Some(other) => {
            return Err(format!(
                "capture file is for revision {other}, not {HARDWARE_REVISION_E}: analyze it without a Rev E board profile"
            ))
        }
        None => return Err("capture file has no setup.revision".into()),
    }
    serde_json::from_value(value).map_err(|e| e.to_string())
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CalibrationPointE {
    pub cycles: u32,
    pub period: u32,
    pub a: Complex,
    pub b: Complex,
    pub c: Complex,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CalibrationE {
    #[serde(default)]
    pub schema_version: u32,
    #[serde(default)]
    pub feedback_capacitance_pf: f64,
    #[serde(default)]
    pub isolation_resistor_ohm: f64,
    #[serde(default)]
    pub dut_lo_capacitance_pf: f64,
    pub setup: SetupE,
    pub model: String,
    pub standard1_ohm: f64,
    pub standard2_ohm: f64,
    pub points: Vec<CalibrationPointE>,
}
/// Version-checked calibration loader. A Rev D calibration (schema 5, `D-riso22`) is refused
/// by name, as are other schemas and models.
pub fn parse_calibration_e(text: &str) -> Result<CalibrationE> {
    let value: serde_json::Value = serde_json::from_str(text).map_err(|e| e.to_string())?;
    match crate::file_revision(&value).as_deref() {
        Some(HARDWARE_REVISION_E) => {}
        Some(other) => {
            return Err(format!(
                "calibration belongs to revision {other}, not {HARDWARE_REVISION_E}: it is not valid on a Rev E board; recalibrate with fresh standards"
            ))
        }
        None => return Err("calibration file has no setup.revision".into()),
    }
    let schema = value
        .get("schema_version")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or(0);
    if schema != u64::from(CALIBRATION_SCHEMA_VERSION_E) {
        return Err(format!(
            "calibration schema {schema} is not {CALIBRATION_SCHEMA_VERSION_E}; recalibrate with fresh standards"
        ));
    }
    serde_json::from_value(value).map_err(|e| e.to_string())
}
fn compatible_e(a: &SweepE, b: &SweepE) -> Result<()> {
    a.setup.validate()?;
    b.setup.validate()?;
    if a.setup != b.setup || a.records.is_empty() || a.records.len() != b.records.len() {
        return Err("unit, fixture, range, clocks or sweep grid differ".into());
    }
    for (a, b) in a.records.iter().zip(&b.records) {
        if a.period != b.period || a.bins != b.bins {
            return Err("tone frequency or analysed bins differ between standards".into());
        }
    }
    Ok(())
}
/// Three-standard calibration, one bilinear correction per analysed bin (a short and two
/// resistors, as Rev D). Standards need not use the same SKIP or PERIODS.
pub fn calibrate_e(
    short: &SweepE,
    load1: &SweepE,
    z1: f64,
    load2: &SweepE,
    z2: f64,
) -> Result<CalibrationE> {
    compatible_e(short, load1)?;
    compatible_e(short, load2)?;
    let range = short.setup.range_ohm;
    let mut points = Vec::new();
    for ((s, r1), r2) in short.records.iter().zip(&load1.records).zip(&load2.records) {
        let ms = analyze_e(s, range)?;
        let m1 = analyze_e(r1, range)?;
        let m2 = analyze_e(r2, range)?;
        for (i, &bin) in s.bins.iter().enumerate() {
            // The short intentionally has near-zero voltage. Current and clipping still matter.
            if !ms[i].current.valid_signal()
                || ms[i].voltage.clipped
                || ms[i].current.clipped
                || !m1[i].valid
                || !m2[i].valid
            {
                return Err(
                    "calibration standard has clipping, insufficient current, or poor fit".into(),
                );
            }
            let [a, b, c] = calibration_coefficients(
                ms[i].raw_impedance_ohm,
                m1[i].raw_impedance_ohm,
                z1,
                m2[i].raw_impedance_ohm,
                z2,
            )?;
            points.push(CalibrationPointE {
                cycles: bin,
                period: s.period,
                a,
                b,
                c,
            });
        }
    }
    Ok(CalibrationE {
        schema_version: CALIBRATION_SCHEMA_VERSION_E,
        feedback_capacitance_pf: feedback_capacitance_pf(range)?,
        isolation_resistor_ohm: ISOLATION_RESISTOR_OHM,
        dut_lo_capacitance_pf: DUT_LO_CAPACITOR_PF,
        setup: short.setup.clone(),
        model: CALIBRATION_MODEL_E.into(),
        standard1_ohm: z1,
        standard2_ohm: z2,
        points,
    })
}
/// Applies the bilinear correction of the same frequency (equal CYCLES/PERIOD as a fraction).
pub fn correct_e(m: &mut MeasurementE, setup: &SetupE, cal: &CalibrationE) -> Result<()> {
    setup.validate()?;
    if cal.setup != *setup
        || cal.model != CALIBRATION_MODEL_E
        || cal.schema_version != CALIBRATION_SCHEMA_VERSION_E
        || cal.feedback_capacitance_pf != feedback_capacitance_pf(setup.range_ohm)?
        || cal.isolation_resistor_ohm != ISOLATION_RESISTOR_OHM
        || cal.dut_lo_capacitance_pf != DUT_LO_CAPACITOR_PF
    {
        return Err("calibration does not match schema/unit/fixture/range/clock/revision/feedback network; recalibrate".into());
    }
    let p = cal
        .points
        .iter()
        .find(|p| {
            u64::from(p.cycles) * u64::from(m.period) == u64::from(m.cycles) * u64::from(p.period)
        })
        .ok_or("no calibration at this exact frequency")?;
    let denominator = p.a - m.raw_impedance_ohm * p.c;
    if !p.a.finite()
        || !p.b.finite()
        || !p.c.finite()
        || denominator.abs() < 1e-9 * p.a.abs().max(1.0)
    {
        return Err("calibration pole or non-finite coefficients".into());
    }
    m.impedance_ohm = (m.raw_impedance_ohm - p.b) / denominator;
    if !m.impedance_ohm.finite() {
        return Err("non-finite corrected impedance".into());
    }
    m.calibrated = true;
    derived(m);
    Ok(())
}

//! Acquisition and three-standard fixture correction for the TIDA-based Rev D.
//! Digital tests do not establish the accuracy of an unbuilt analog instrument.
use serde::{Deserialize, Serialize};
use std::f64::consts::{PI, TAU};
use std::ops::{Add, Div, Mul, Sub};
pub mod integrity;
pub mod transport;
pub use integrity::*;
pub type Result<T> = std::result::Result<T, String>;

#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct Complex {
    pub re: f64,
    pub im: f64,
}
impl Complex {
    pub fn new(re: f64, im: f64) -> Self {
        Self { re, im }
    }
    pub fn abs(self) -> f64 {
        self.re.hypot(self.im)
    }
    pub fn finite(self) -> bool {
        self.re.is_finite() && self.im.is_finite()
    }
}
impl Add for Complex {
    type Output = Self;
    fn add(self, b: Self) -> Self {
        Self::new(self.re + b.re, self.im + b.im)
    }
}
impl Sub for Complex {
    type Output = Self;
    fn sub(self, b: Self) -> Self {
        Self::new(self.re - b.re, self.im - b.im)
    }
}
impl Mul for Complex {
    type Output = Self;
    fn mul(self, b: Self) -> Self {
        Self::new(
            self.re * b.re - self.im * b.im,
            self.re * b.im + self.im * b.re,
        )
    }
}
impl Div for Complex {
    type Output = Self;
    fn div(self, b: Self) -> Self {
        let d = b.re * b.re + b.im * b.im;
        Self::new(
            (self.re * b.re + self.im * b.im) / d,
            (self.im * b.re - self.re * b.im) / d,
        )
    }
}

pub const DDS_CLOCK_HZ: f64 = 24_000_000.0;
/// The ADC always converts at this rate. The firmware boxcar-sums `decimation`
/// consecutive conversions per channel into each output sample.
pub const CONVERSION_RATE_HZ: f64 = 1_000_000.0;
/// Output samples per capture requested by this host.
pub const DEFAULT_COUNT: usize = 16_384;
/// Firmware limit on output samples (`MAX_SAMPLES` in firmware/src/pins.h).
pub const MAX_COUNT: usize = 16_384;
/// Firmware limit on conversions per output sample (`BOXCAR_MAX_DECIMATION`).
pub const MAX_DECIMATION: u32 = 20;
/// USB wire protocol. Version 1 (undersampled packed 16-bit pairs) is rejected.
pub const PROTOCOL_VERSION: u32 = 2;
/// A single conversion with |code| at or above this is treated as clipping.
pub const CLIP_CODE: i32 = 32_700;
pub const HARDWARE_REVISION: &str = "D-riso22";
pub const CALIBRATION_SCHEMA_VERSION: u32 = 5;
pub const CALIBRATION_MODEL: &str = "bilinear-short-two-resistors-v5-riso22-local100p-boxcar";
/// R94, 0.1 %, between J3 LO and the TIA summing node. The LOW sense follower
/// taps the J3 side, so channel B spans R94 + RF||CF on every range.
pub const ISOLATION_RESISTOR_OHM: f64 = 22.0;
/// One local 100 pF capacitor remains connected for every range. Calibrate parasitics.
pub const FEEDBACK_CAPACITORS_PF: [(u32, f64); 3] = [(100, 100.0), (5000, 100.0), (100000, 100.0)];

pub fn feedback_capacitance_pf(range: u32) -> Result<f64> {
    FEEDBACK_CAPACITORS_PF
        .iter()
        .find_map(|&(r, c)| (r == range).then_some(c))
        .ok_or_else(|| "range must be 100, 5000 or 100000 ohms".into())
}

/// RP2040 ADC reference: ADC_AVDD is the board 3V3, so both monitors read
/// ratiometrically to it and a 3V3 error scales the reported rails 1:1.
pub const RAIL_ADC_REFERENCE_V: f64 = 3.3;
/// Gross-fault windows for the analog rails: +-5 % rail, +-3 % 3V3, 1 % dividers.
pub const RAIL_P12_WINDOW_V: (f64, f64) = (10.8, 13.2);
pub const RAIL_N12_WINDOW_V: (f64, f64) = (-13.2, -10.8);
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Rails {
    pub plus12_v: f64,
    pub minus12_v: f64,
    /// RP2040 die sensor, +-several degC uncalibrated; logged for drift context.
    pub die_c: f64,
    pub pass: bool,
}
/// Parses "RAILS N SUM_ADC0 SUM_ADC1 SUM_ADC4" (sums of N 12-bit conversions).
/// ADC0: +12 V through R97 100k over R98 10k. ADC1: -12 V through R100 150k,
/// pulled toward 3V3 by R99 10k, so it never goes negative while 3V3 is up.
pub fn rails_from_line(line: &str) -> Result<Rails> {
    let w: Vec<_> = line.split_whitespace().collect();
    let parsed: Option<Vec<u32>> = w.iter().skip(1).map(|x| x.parse().ok()).collect();
    let v = match (w.first(), parsed) {
        (Some(&"RAILS"), Some(v))
            if v.len() == 4
                && v[0] > 0
                && v[1..]
                    .iter()
                    .all(|&s| u64::from(s) <= u64::from(v[0]) * 4095) =>
        {
            v
        }
        _ => return Err(format!("unexpected RAILS reply: {line}")),
    };
    let volts = |sum: u32| f64::from(sum) / f64::from(v[0]) / 4096.0 * RAIL_ADC_REFERENCE_V;
    let plus12_v = volts(v[1]) * (100.0 + 10.0) / 10.0;
    let minus12_v = (volts(v[2]) * (150.0 + 10.0) - RAIL_ADC_REFERENCE_V * 150.0) / 10.0;
    let die_c = 27.0 - (volts(v[3]) - 0.706) / 0.001721;
    let inside = |x: f64, (lo, hi): (f64, f64)| (lo..=hi).contains(&x);
    let pass = inside(plus12_v, RAIL_P12_WINDOW_V) && inside(minus12_v, RAIL_N12_WINDOW_V);
    Ok(Rails {
        plus12_v,
        minus12_v,
        die_c,
        pass,
    })
}
pub fn frequency_word(hz: f64) -> Result<u32> {
    if !hz.is_finite() || !(100.0..=100_000.0).contains(&hz) {
        return Err("frequency must be 100..100000 Hz".into());
    }
    Ok((hz * 268_435_456.0 / DDS_CLOCK_HZ).round() as u32)
}
pub fn frequency_hz(word: u32) -> f64 {
    f64::from(word) * DDS_CLOCK_HZ / 268_435_456.0
}
/// Boxcar decimation N: enough cycles at 100 Hz and >= 10 output samples/cycle
/// elsewhere. The output rate is 1 MSPS / N; the ADC itself always runs at 1 MSPS.
pub fn decimation_for(hz: f64) -> u32 {
    (CONVERSION_RATE_HZ / (hz * 10.0).max(50_000.0))
        .floor()
        .clamp(1.0, f64::from(MAX_DECIMATION)) as u32
}
/// Output sample rate after summing `decimation` conversions.
pub fn output_rate_hz(decimation: u32) -> f64 {
    CONVERSION_RATE_HZ / f64::from(decimation)
}
/// Amplitude response of an N-conversion boxcar at `hz`, referenced to the
/// window centre so that it is real: sin(pi f N / fs) / (N sin(pi f / fs)).
/// Identical on both channels, so it cancels in the A/B impedance ratio.
pub fn boxcar_gain(hz: f64, decimation: u32) -> f64 {
    let x = PI * hz / CONVERSION_RATE_HZ;
    let n = f64::from(decimation);
    if x.sin().abs() < 1e-15 {
        return 1.0;
    }
    (n * x).sin() / (n * x.sin())
}
pub fn feedback(range: u32, hz: f64) -> Result<Complex> {
    if !hz.is_finite() || hz <= 0.0 {
        return Err("frequency must be positive".into());
    }
    let cap = feedback_capacitance_pf(range)? * 1e-12;
    Ok(Complex::new(ISOLATION_RESISTOR_OHM, 0.0)
        + Complex::new(1.0, 0.0) / Complex::new(1.0 / f64::from(range), TAU * hz * cap))
}
/// Splits one raw PIO word (bits B15,A15,...,B0,A0) into [A, B]. Protocol 2
/// firmware performs this on the device; the host keeps it as the reference
/// for tests that mirror the firmware's deinterleave and boxcar.
pub fn decode_word(packed: u32) -> [i16; 2] {
    let mut words = [0u16; 2];
    for bit in 0..16 {
        for (channel, word) in words.iter_mut().enumerate() {
            *word |= (((packed >> (2 * bit + channel)) & 1) as u16) << bit;
        }
    }
    [words[0] as i16, words[1] as i16]
}
pub fn crc32(bytes: &[u8]) -> u32 {
    let mut crc = u32::MAX;
    for &byte in bytes {
        crc ^= u32::from(byte);
        for _ in 0..8 {
            crc = (crc >> 1) ^ (0xedb88320 & 0u32.wrapping_sub(crc & 1));
        }
    }
    !crc
}
/// Bytes before the sums: A min, A max, B min, B max as little-endian i16.
pub const PAYLOAD_HEADER_BYTES: usize = 8;
/// Protocol-2 binary payload length for `count` output samples.
pub fn payload_len(count: usize) -> usize {
    PAYLOAD_HEADER_BYTES + 8 * count
}
/// Protocol-2 payload: [A min, A max, B min, B max] as i16, then per output
/// sample [A sum, B sum] as i32, all little-endian. The CRC covers all of it.
pub fn encode_payload(raw_min: [i16; 2], raw_max: [i16; 2], sums: &[[i32; 2]]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(payload_len(sums.len()));
    for value in [raw_min[0], raw_max[0], raw_min[1], raw_max[1]] {
        bytes.extend_from_slice(&value.to_le_bytes());
    }
    for pair in sums {
        bytes.extend_from_slice(&pair[0].to_le_bytes());
        bytes.extend_from_slice(&pair[1].to_le_bytes());
    }
    bytes
}
/// Decoded protocol-2 payload: (raw_min, raw_max, sums).
pub type Payload = ([i16; 2], [i16; 2], Vec<[i32; 2]>);
/// Inverse of [`encode_payload`].
pub fn decode_payload(bytes: &[u8]) -> Result<Payload> {
    if bytes.len() < PAYLOAD_HEADER_BYTES || (bytes.len() - PAYLOAD_HEADER_BYTES) % 8 != 0 {
        return Err("protocol-2 payload length is not 8 + 8 x count bytes".into());
    }
    let i16_at = |i: usize| i16::from_le_bytes([bytes[i], bytes[i + 1]]);
    let sums = bytes[PAYLOAD_HEADER_BYTES..]
        .chunks_exact(8)
        .map(|c| {
            [
                i32::from_le_bytes([c[0], c[1], c[2], c[3]]),
                i32::from_le_bytes([c[4], c[5], c[6], c[7]]),
            ]
        })
        .collect();
    Ok(([i16_at(0), i16_at(4)], [i16_at(2), i16_at(6)], sums))
}
/// Version-checked capture loader: protocol-1 records fail with an explicit message.
pub fn parse_sweep(text: &str) -> Result<Sweep> {
    let value: serde_json::Value = serde_json::from_str(text).map_err(|e| e.to_string())?;
    let records = value
        .get("records")
        .and_then(serde_json::Value::as_array)
        .ok_or("capture file has no records array")?;
    for record in records {
        let protocol = record.get("protocol").and_then(serde_json::Value::as_u64);
        if protocol != Some(u64::from(PROTOCOL_VERSION)) {
            if record.get("packed_samples").is_some() || record.get("sample_divider").is_some() {
                return Err("capture file is protocol 1 (undersampled packed 16-bit samples); this host needs protocol-2 boxcar-decimated captures: flash protocol-2 firmware and recapture".into());
            }
            return Err(format!(
                "capture record protocol {protocol:?} is unsupported; this host needs protocol {PROTOCOL_VERSION}"
            ));
        }
    }
    serde_json::from_value(value).map_err(|e| e.to_string())
}
/// Version-checked calibration loader: schema 3 and older fail with an explicit message.
pub fn parse_calibration(text: &str) -> Result<Calibration> {
    let value: serde_json::Value = serde_json::from_str(text).map_err(|e| e.to_string())?;
    let schema = value
        .get("schema_version")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or(0);
    if schema != u64::from(CALIBRATION_SCHEMA_VERSION) {
        return Err(format!("calibration schema {schema} is not {CALIBRATION_SCHEMA_VERSION}: it predates protocol-2 boxcar captures or belongs to another revision; recalibrate with fresh standards"));
    }
    serde_json::from_value(value).map_err(|e| e.to_string())
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Setup {
    pub revision: String,
    pub unit_id: String,
    pub fixture: String,
    pub range_ohm: u32,
    pub system_clock_hz: u32,
    pub dds_clock_hz: u32,
}
impl Setup {
    pub fn validate(&self) -> Result<()> {
        if self.revision != HARDWARE_REVISION
            || self.unit_id.is_empty()
            || self.fixture.is_empty()
            || self.system_clock_hz != 120_000_000
            || self.dds_clock_hz != 24_000_000
        {
            return Err("capture metadata does not describe the D-riso22 instrument".into());
        }
        feedback(self.range_ohm, 1000.0)?;
        Ok(())
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Record {
    /// Wire protocol of the producing firmware; must equal [`PROTOCOL_VERSION`].
    #[serde(default)]
    pub protocol: u32,
    /// False only for an explicitly requested source-off diagnostic.
    pub source_enabled: bool,
    pub tuning_word: u32,
    /// Consecutive 1 MSPS conversions summed into each output sample (1..20).
    pub decimation: u32,
    /// Most negative single conversion on [A, B] over the whole capture.
    pub raw_min: [i16; 2],
    /// Most positive single conversion on [A, B] over the whole capture.
    pub raw_max: [i16; 2],
    /// Per output sample, [sum of A, sum of B] over `decimation` conversions.
    pub sums: Vec<[i32; 2]>,
    /// CRC32 of the protocol-2 payload (extremes header and sums) as received.
    pub transport_crc32: u32,
    /// Source-off record captured right after this one at the same tuning
    /// word, decimation and length (R2). `analyze` recomputes the check from it.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_off: Option<Box<Record>>,
    /// The check as `capture` evaluated it; informational.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_off_check: Option<SourceOffCheck>,
    /// Hazards that `capture --allow-hazard` accepted at this frequency (R1).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub allowed_hazards: Vec<Interference>,
}
impl Record {
    pub fn payload(&self) -> Vec<u8> {
        encode_payload(self.raw_min, self.raw_max, &self.sums)
    }
    pub fn output_rate_hz(&self) -> f64 {
        output_rate_hz(self.decimation)
    }
    /// Output samples in single-conversion codes: sum / decimation.
    pub fn means(&self, channel: usize) -> Vec<f64> {
        let n = f64::from(self.decimation);
        self.sums
            .iter()
            .map(|s| f64::from(s[channel]) / n)
            .collect()
    }
    /// True when any single conversion on the channel reached |code| >= 32700.
    pub fn clipped(&self, channel: usize) -> bool {
        i32::from(self.raw_min[channel]) <= -CLIP_CODE
            || i32::from(self.raw_max[channel]) >= CLIP_CODE
    }
    pub fn validate(&self) -> Result<()> {
        if self.protocol != PROTOCOL_VERSION {
            return Err(format!(
                "capture record protocol {} is not {PROTOCOL_VERSION}; recapture with protocol-2 firmware",
                self.protocol
            ));
        }
        let f = frequency_hz(self.tuning_word);
        if !(1..=MAX_DECIMATION).contains(&self.decimation)
            || !(256..=MAX_COUNT).contains(&self.sums.len())
            || !(99.9..=100000.1).contains(&f)
        {
            return Err("invalid capture length, boxcar decimation, or DDS frequency".into());
        }
        let rate = self.output_rate_hz();
        if rate / f < 8.0 || self.sums.len() as f64 * f / rate < 10.0 {
            return Err("record requires >=8 output samples/cycle and >=10 cycles".into());
        }
        if crc32(&self.payload()) != self.transport_crc32 {
            return Err("capture CRC mismatch".into());
        }
        // Every sum of N conversions lies within N x [min, max] of those conversions.
        let n = i64::from(self.decimation);
        for channel in 0..2 {
            let (lo, hi) = (
                i64::from(self.raw_min[channel]),
                i64::from(self.raw_max[channel]),
            );
            if lo > hi
                || self
                    .sums
                    .iter()
                    .any(|s| !(n * lo..=n * hi).contains(&i64::from(s[channel])))
            {
                return Err(
                    "boxcar sums are inconsistent with the reported conversion extremes".into(),
                );
            }
        }
        Ok(())
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Sweep {
    pub setup: Setup,
    pub records: Vec<Record>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Fit {
    /// Tone phasor in single-conversion codes, divided by the boxcar gain.
    pub phasor_codes: Complex,
    pub dc_codes: f64,
    /// RMS fit residual of the decimated samples, in single-conversion codes.
    pub residual_rms_codes: f64,
    /// Boxcar amplitude response at the fitted frequency (1 for decimation 1).
    pub boxcar_gain: f64,
    /// Single-conversion extremes reported by the firmware for this channel.
    pub raw_min_code: i16,
    pub raw_max_code: i16,
    /// Any single conversion reached |code| >= 32700.
    pub clipped: bool,
}
impl Fit {
    pub fn valid_signal(&self) -> bool {
        self.phasor_codes.abs() >= 16.0 && self.residual_rms_codes / self.phasor_codes.abs() < 0.05
    }
}

fn solve_real(mut a: [[f64; 4]; 3]) -> Result<[f64; 3]> {
    for col in 0..3 {
        let pivot = (col..3)
            .max_by(|&x, &y| a[x][col].abs().total_cmp(&a[y][col].abs()))
            .ok_or("empty solver")?;
        a.swap(col, pivot);
        if a[col][col].abs() < 1e-12 {
            return Err("singular sinusoid fit".into());
        }
        let divisor = a[col][col];
        for value in &mut a[col][col..] {
            *value /= divisor;
        }
        for row in 0..3 {
            if row == col {
                continue;
            }
            let scale = a[row][col];
            let pivot_row = a[col];
            for (value, pivot_value) in a[row][col..].iter_mut().zip(&pivot_row[col..]) {
                *value -= scale * pivot_value;
            }
        }
    }
    Ok([a[0][3], a[1][3], a[2][3]])
}
/// Effective time of output sample k: the centre of its boxcar window,
/// (k N + (N - 1) / 2) / 1 MHz, measured from the first conversion.
pub fn output_time_s(k: usize, decimation: u32) -> f64 {
    let n = f64::from(decimation);
    (k as f64 * n + (n - 1.0) / 2.0) / CONVERSION_RATE_HZ
}
/// Least-squares DC + cosine + sine fit to boxcar means (sum / N); valid for
/// non-integer cycle counts. Each output is timed at its window centre, which
/// makes the boxcar response real; the phasor is then divided by that gain so
/// it is in input-referred single-conversion codes. The cosine phasor
/// convention is a - j*b for a*cos(wt)+b*sin(wt). Clip fields are left clear;
/// [`fit_channel`] fills them from the record.
pub fn fit(means: &[f64], hz: f64, decimation: u32) -> Result<Fit> {
    if means.len() < 16
        || !hz.is_finite()
        || hz <= 0.0
        || !(1..=MAX_DECIMATION).contains(&decimation)
        || hz >= output_rate_hz(decimation) / 2.0
    {
        return Err("invalid sine-fit input".into());
    }
    let angle = |k: usize| TAU * hz * output_time_s(k, decimation);
    let mut matrix = [[0.0; 4]; 3];
    for (k, &sample) in means.iter().enumerate() {
        let basis = [1.0, angle(k).cos(), angle(k).sin()];
        for row in 0..3 {
            for col in 0..3 {
                matrix[row][col] += basis[row] * basis[col];
            }
            matrix[row][3] += basis[row] * sample;
        }
    }
    let [dc, c, s] = solve_real(matrix)?;
    let sum_sq = means
        .iter()
        .enumerate()
        .map(|(k, &y)| (y - dc - c * angle(k).cos() - s * angle(k).sin()).powi(2))
        .sum::<f64>();
    let gain = boxcar_gain(hz, decimation);
    Ok(Fit {
        phasor_codes: Complex::new(c / gain, -s / gain),
        dc_codes: dc,
        residual_rms_codes: (sum_sq / means.len() as f64).sqrt(),
        boxcar_gain: gain,
        raw_min_code: 0,
        raw_max_code: 0,
        clipped: false,
    })
}
/// Fit one channel of a validated record at its DDS frequency, with clip flags.
pub fn fit_channel(record: &Record, channel: usize) -> Result<Fit> {
    let mut fitted = fit(
        &record.means(channel),
        frequency_hz(record.tuning_word),
        record.decimation,
    )?;
    fitted.raw_min_code = record.raw_min[channel];
    fitted.raw_max_code = record.raw_max[channel];
    fitted.clipped = record.clipped(channel);
    Ok(fitted)
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Measurement {
    pub frequency_hz: f64,
    pub raw_impedance_ohm: Complex,
    pub impedance_ohm: Complex,
    pub magnitude_ohm: f64,
    pub phase_degrees: f64,
    pub series_resistance_ohm: f64,
    pub series_inductance_h: Option<f64>,
    pub series_capacitance_f: Option<f64>,
    pub q: Option<f64>,
    pub voltage: Fit,
    pub current: Fit,
    pub calibrated: bool,
    pub valid: bool,
    pub issues: Vec<String>,
    /// R2 check recomputed from the paired source-off record; absent when the
    /// capture has none (`capture --no-source-off` or an older file).
    #[serde(default)]
    pub source_off: Option<SourceOffCheck>,
    /// R1 hazards at this acquisition. Informational: `capture` refuses them
    /// unless `--allow-hazard`, and the source-off check cannot see DDS harmonics.
    #[serde(default)]
    pub frequency_hazards: Vec<Interference>,
    /// Issues overridden on the command line; still reported, no longer invalidating.
    #[serde(default)]
    pub waived_issues: Vec<String>,
}
/// Every source-off issue starts with this prefix.
pub const SOURCE_OFF_ISSUE: &str = "source-off";
/// Override a failed source-off check: move its issue to `waived_issues`.
pub fn waive_source_off(m: &mut Measurement) {
    let (waived, kept): (Vec<String>, Vec<String>) = m
        .issues
        .drain(..)
        .partition(|issue| issue.starts_with(SOURCE_OFF_ISSUE));
    m.issues = kept;
    m.waived_issues.extend(waived);
    m.valid = m.issues.is_empty();
}
pub fn analyze(record: &Record, range: u32) -> Result<Measurement> {
    record.validate()?;
    if !record.source_enabled {
        return Err("source-off record cannot produce impedance".into());
    }
    let hz = frequency_hz(record.tuning_word);
    let voltage = fit_channel(record, 0)?;
    let current = fit_channel(record, 1)?;
    if current.phasor_codes.abs() < 1e-9 {
        return Err("no current signal; open DUT or wrong range".into());
    }
    let z = feedback(range, hz)? * voltage.phasor_codes / current.phasor_codes;
    if !z.finite() {
        return Err("non-finite impedance".into());
    }
    let mut issues = Vec::new();
    if voltage.clipped || current.clipped {
        issues.push("ADC clipping".into());
    }
    if !current.valid_signal() {
        issues.push("current signal too weak or distorted".into());
    }
    if !voltage.valid_signal() {
        issues.push("voltage signal too weak or distorted".into());
    }
    let source_off = match &record.source_off {
        None => None,
        Some(off) => match source_off_check(record, off, false) {
            Ok(check) => {
                if !check.pass {
                    issues.push(check.diagnostic.clone());
                }
                Some(check)
            }
            Err(e) => {
                issues.push(format!("{SOURCE_OFF_ISSUE} record unusable: {e}"));
                None
            }
        },
    };
    let hazards = frequency_hazards(hz, record.decimation, record.sums.len())?
        .hazards()
        .cloned()
        .collect();
    let mut m = Measurement {
        frequency_hz: hz,
        raw_impedance_ohm: z,
        impedance_ohm: z,
        magnitude_ohm: 0.0,
        phase_degrees: 0.0,
        series_resistance_ohm: 0.0,
        series_inductance_h: None,
        series_capacitance_f: None,
        q: None,
        voltage,
        current,
        calibrated: false,
        valid: issues.is_empty(),
        issues,
        source_off,
        frequency_hazards: hazards,
        waived_issues: Vec::new(),
    };
    derived(&mut m);
    Ok(m)
}
fn derived(m: &mut Measurement) {
    let z = m.impedance_ohm;
    m.magnitude_ohm = z.abs();
    m.phase_degrees = z.im.atan2(z.re).to_degrees();
    m.series_resistance_ohm = z.re;
    m.series_inductance_h = if z.im > 0.0 {
        Some(z.im / (TAU * m.frequency_hz))
    } else {
        None
    };
    m.series_capacitance_f = if z.im < 0.0 {
        Some(-1.0 / (TAU * m.frequency_hz * z.im))
    } else {
        None
    };
    m.q = if z.re > 0.0 {
        Some(z.im.abs() / z.re)
    } else {
        None
    };
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CalibrationPoint {
    pub tuning_word: u32,
    pub decimation: u32,
    pub sample_count: usize,
    pub a: Complex,
    pub b: Complex,
    pub c: Complex,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Calibration {
    /// Missing in older files; zero deliberately fails compatibility validation.
    #[serde(default)]
    pub schema_version: u32,
    #[serde(default)]
    pub feedback_capacitance_pf: f64,
    /// Missing before schema 5 (Rev D); zero fails compatibility validation.
    #[serde(default)]
    pub isolation_resistor_ohm: f64,
    pub setup: Setup,
    pub model: String,
    pub standard1_ohm: f64,
    pub standard2_ohm: f64,
    pub points: Vec<CalibrationPoint>,
}
/// Fit measured = (a*true + b)/(c*true + 1), using a short and two resistors.
/// Three independent complex standards identify gain, series and shunt errors.
pub fn calibration_coefficients(
    short: Complex,
    m1: Complex,
    z1: f64,
    m2: Complex,
    z2: f64,
) -> Result<[Complex; 3]> {
    if !short.finite()
        || !m1.finite()
        || !m2.finite()
        || !z1.is_finite()
        || !z2.is_finite()
        || z1 <= 0.0
        || z2 <= 0.0
        || (z1 - z2).abs() < 0.1 * z1.max(z2)
    {
        return Err("use two distinct positive standards separated by at least 10%".into());
    }
    let denom = m2 - m1;
    if denom.abs() < 1e-6 * m1.abs().max(m2.abs()).max(1.0) {
        return Err("standards are indistinguishable; calibration is ill-conditioned".into());
    }
    let one = Complex::new(1.0, 0.0);
    let c = ((m1 - short) / Complex::new(z1, 0.0) - (m2 - short) / Complex::new(z2, 0.0)) / denom;
    let a = (m1 * (c * Complex::new(z1, 0.0) + one) - short) / Complex::new(z1, 0.0);
    if !a.finite() || !c.finite() || (a - short * c).abs() < 1e-12 {
        return Err("singular calibration transform".into());
    }
    Ok([a, short, c])
}
fn compatible(a: &Sweep, b: &Sweep) -> Result<()> {
    a.setup.validate()?;
    b.setup.validate()?;
    if a.setup != b.setup || a.records.is_empty() || a.records.len() != b.records.len() {
        return Err("unit, fixture, range, clocks or sweep grid differ".into());
    }
    for (a, b) in a.records.iter().zip(&b.records) {
        if a.tuning_word != b.tuning_word
            || a.decimation != b.decimation
            || a.sums.len() != b.sums.len()
        {
            return Err("frequency, sample rate or record length differ".into());
        }
    }
    Ok(())
}
/// Three-standard calibration. Standards that carry a source-off record must
/// pass the source-off check (the short with its voltage channel judged
/// against its current channel) unless `allow_source_off_fail`.
pub fn calibrate(
    short: &Sweep,
    load1: &Sweep,
    z1: f64,
    load2: &Sweep,
    z2: f64,
    allow_source_off_fail: bool,
) -> Result<Calibration> {
    compatible(short, load1)?;
    compatible(short, load2)?;
    let mut points = Vec::new();
    for ((s, r1), r2) in short.records.iter().zip(&load1.records).zip(&load2.records) {
        let ms = analyze(s, short.setup.range_ohm)?;
        let mut m1 = analyze(r1, short.setup.range_ohm)?;
        let mut m2 = analyze(r2, short.setup.range_ohm)?;
        if let Some(off) = &s.source_off {
            let check = source_off_check(s, off, true)?;
            if !check.pass && !allow_source_off_fail {
                return Err(format!("short standard: {}", check.diagnostic));
            }
        }
        for (name, m) in [("standard 1", &mut m1), ("standard 2", &mut m2)] {
            if allow_source_off_fail {
                waive_source_off(m);
            } else if let Some(issue) = m.issues.iter().find(|i| i.starts_with(SOURCE_OFF_ISSUE)) {
                return Err(format!("{name}: {issue}"));
            }
        }
        // Short intentionally has near-zero voltage. Current and clipping still matter.
        if !ms.current.valid_signal()
            || ms.voltage.clipped
            || ms.current.clipped
            || !m1.valid
            || !m2.valid
        {
            return Err(
                "calibration standard has clipping, insufficient current, or poor fit".into(),
            );
        }
        let [a, b, c] = calibration_coefficients(
            ms.raw_impedance_ohm,
            m1.raw_impedance_ohm,
            z1,
            m2.raw_impedance_ohm,
            z2,
        )?;
        points.push(CalibrationPoint {
            tuning_word: s.tuning_word,
            decimation: s.decimation,
            sample_count: s.sums.len(),
            a,
            b,
            c,
        });
    }
    Ok(Calibration {
        schema_version: CALIBRATION_SCHEMA_VERSION,
        feedback_capacitance_pf: feedback_capacitance_pf(short.setup.range_ohm)?,
        isolation_resistor_ohm: ISOLATION_RESISTOR_OHM,
        setup: short.setup.clone(),
        model: CALIBRATION_MODEL.into(),
        standard1_ohm: z1,
        standard2_ohm: z2,
        points,
    })
}
pub fn correct(
    m: &mut Measurement,
    record: &Record,
    setup: &Setup,
    cal: &Calibration,
) -> Result<()> {
    setup.validate()?;
    if cal.setup != *setup
        || cal.model != CALIBRATION_MODEL
        || cal.schema_version != CALIBRATION_SCHEMA_VERSION
        || cal.feedback_capacitance_pf != feedback_capacitance_pf(setup.range_ohm)?
        || cal.isolation_resistor_ohm != ISOLATION_RESISTOR_OHM
    {
        return Err("calibration does not match schema/unit/fixture/range/clock/revision/feedback network; recalibrate".into());
    }
    let p = cal
        .points
        .iter()
        .find(|p| {
            p.tuning_word == record.tuning_word
                && p.decimation == record.decimation
                && p.sample_count == record.sums.len()
        })
        .ok_or("no calibration at this exact frequency and acquisition setting")?;
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

#[derive(Debug, Serialize)]
pub struct Noise {
    pub frequency_hz: f64,
    /// Conversions averaged per output sample; RMS values describe the averages.
    pub decimation: u32,
    /// DC-removed RMS of the N-conversion averages, in single-conversion codes.
    pub rms_codes: [f64; 2],
    pub rms_volts: [f64; 2],
    /// Input-referred fitted tone amplitude (boxcar gain removed).
    pub tone_peak_codes: [f64; 2],
    pub raw_min_code: [i16; 2],
    pub raw_max_code: [i16; 2],
    pub clipped: [bool; 2],
}
pub fn noise(record: &Record) -> Result<Noise> {
    record.validate()?;
    if record.source_enabled {
        return Err("noise analysis requires a source-off record".into());
    }
    let mut result = Noise {
        frequency_hz: frequency_hz(record.tuning_word),
        decimation: record.decimation,
        rms_codes: [0.0; 2],
        rms_volts: [0.0; 2],
        tone_peak_codes: [0.0; 2],
        raw_min_code: record.raw_min,
        raw_max_code: record.raw_max,
        clipped: [record.clipped(0), record.clipped(1)],
    };
    for channel in 0..2 {
        let means = record.means(channel);
        let fitted = fit_channel(record, channel)?;
        let rms = (means
            .iter()
            .map(|&v| (v - fitted.dc_codes).powi(2))
            .sum::<f64>()
            / means.len() as f64)
            .sqrt();
        result.rms_codes[channel] = rms;
        result.rms_volts[channel] = rms * 4.096 / 32768.0;
        result.tone_peak_codes[channel] = fitted.phasor_codes.abs();
    }
    Ok(result)
}

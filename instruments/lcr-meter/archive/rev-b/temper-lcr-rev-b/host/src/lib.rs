//! Acquisition and three-standard fixture correction for the TIDA-based Rev B.
//! Digital tests do not establish the accuracy of an unbuilt analog instrument.
use serde::{Deserialize, Serialize};
use std::f64::consts::TAU;
use std::ops::{Add, Div, Mul, Sub};
pub mod transport;
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
pub const SAMPLE_BASE_HZ: f64 = 1_000_000.0;
pub const DEFAULT_COUNT: usize = 16_384;

pub fn frequency_word(hz: f64) -> Result<u32> {
    if !hz.is_finite() || !(100.0..=100_000.0).contains(&hz) {
        return Err("frequency must be 100..100000 Hz".into());
    }
    Ok((hz * 268_435_456.0 / DDS_CLOCK_HZ).round() as u32)
}
pub fn frequency_hz(word: u32) -> f64 {
    f64::from(word) * DDS_CLOCK_HZ / 268_435_456.0
}
pub fn divider_for(hz: f64) -> u32 {
    // Enough cycles at 100 Hz and >= 10 samples/cycle elsewhere.
    (SAMPLE_BASE_HZ / (hz * 10.0).max(50_000.0))
        .floor()
        .clamp(1.0, 20.0) as u32
}
pub fn feedback(range: u32, hz: f64) -> Result<Complex> {
    if ![100, 5000, 100000].contains(&range) || !hz.is_finite() || hz <= 0.0 {
        return Err("range must be 100, 5000 or 100000 ohms; frequency must be positive".into());
    }
    let cap = if range == 100000 { 5e-12 } else { 0.0 };
    Ok(Complex::new(1.0, 0.0) / Complex::new(1.0 / f64::from(range), TAU * hz * cap))
}
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
        if self.revision != "B"
            || self.unit_id.is_empty()
            || self.fixture.is_empty()
            || self.system_clock_hz != 120_000_000
            || self.dds_clock_hz != 24_000_000
        {
            return Err("capture metadata does not describe the Rev B instrument".into());
        }
        feedback(self.range_ohm, 1000.0)?;
        Ok(())
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Record {
    /// False only for an explicitly requested source-off diagnostic.
    pub source_enabled: bool,
    pub tuning_word: u32,
    pub sample_divider: u32,
    /// Interleaved B15,A15,...,B0,A0; exact words received over USB.
    pub packed_samples: Vec<u32>,
    pub transport_crc32: u32,
}
impl Record {
    pub fn validate(&self) -> Result<()> {
        let f = frequency_hz(self.tuning_word);
        if !(1..=20).contains(&self.sample_divider)
            || !(256..=32768).contains(&self.packed_samples.len())
            || !(99.9..=100000.1).contains(&f)
        {
            return Err("invalid capture length, clock divider, or DDS frequency".into());
        }
        let rate = SAMPLE_BASE_HZ / f64::from(self.sample_divider);
        if rate / f < 8.0 || self.packed_samples.len() as f64 * f / rate < 10.0 {
            return Err("record requires >=8 samples/cycle and >=10 cycles".into());
        }
        let bytes: Vec<u8> = self
            .packed_samples
            .iter()
            .flat_map(|v| v.to_le_bytes())
            .collect();
        if crc32(&bytes) != self.transport_crc32 {
            return Err("capture CRC mismatch".into());
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
    pub phasor_codes: Complex,
    pub dc_codes: f64,
    pub residual_rms_codes: f64,
    pub clipped_samples: usize,
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
/// Least-squares DC + cosine + sine fit; valid for non-integer cycle counts.
/// The cosine phasor convention is a - j*b for a*cos(wt)+b*sin(wt).
pub fn fit(samples: &[i16], hz: f64, rate: f64) -> Result<Fit> {
    if samples.len() < 16 || !hz.is_finite() || !rate.is_finite() || hz <= 0.0 || hz >= rate / 2.0 {
        return Err("invalid sine-fit input".into());
    }
    let mut matrix = [[0.0; 4]; 3];
    for (i, &sample) in samples.iter().enumerate() {
        let angle = TAU * hz * i as f64 / rate;
        let basis = [1.0, angle.cos(), angle.sin()];
        for row in 0..3 {
            for col in 0..3 {
                matrix[row][col] += basis[row] * basis[col];
            }
            matrix[row][3] += basis[row] * f64::from(sample);
        }
    }
    let [dc, c, s] = solve_real(matrix)?;
    let sum_sq = samples
        .iter()
        .enumerate()
        .map(|(i, &y)| {
            let angle = TAU * hz * i as f64 / rate;
            (f64::from(y) - dc - c * angle.cos() - s * angle.sin()).powi(2)
        })
        .sum::<f64>();
    Ok(Fit {
        phasor_codes: Complex::new(c, -s),
        dc_codes: dc,
        residual_rms_codes: (sum_sq / samples.len() as f64).sqrt(),
        clipped_samples: samples
            .iter()
            .filter(|&&x| i32::from(x).abs() >= 32700)
            .count(),
    })
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
}
pub fn analyze(record: &Record, range: u32) -> Result<Measurement> {
    record.validate()?;
    if !record.source_enabled {
        return Err("source-off record cannot produce impedance".into());
    }
    let hz = frequency_hz(record.tuning_word);
    let rate = SAMPLE_BASE_HZ / f64::from(record.sample_divider);
    let decoded: Vec<[i16; 2]> = record
        .packed_samples
        .iter()
        .map(|&v| decode_word(v))
        .collect();
    let a: Vec<i16> = decoded.iter().map(|v| v[0]).collect();
    let b: Vec<i16> = decoded.iter().map(|v| v[1]).collect();
    let voltage = fit(&a, hz, rate)?;
    let current = fit(&b, hz, rate)?;
    if current.phasor_codes.abs() < 1e-9 {
        return Err("no current signal; open DUT or wrong range".into());
    }
    let z = feedback(range, hz)? * voltage.phasor_codes / current.phasor_codes;
    if !z.finite() {
        return Err("non-finite impedance".into());
    }
    let mut issues = Vec::new();
    if voltage.clipped_samples > 0 || current.clipped_samples > 0 {
        issues.push("ADC clipping".into());
    }
    if !current.valid_signal() {
        issues.push("current signal too weak or distorted".into());
    }
    if !voltage.valid_signal() {
        issues.push("voltage signal too weak or distorted".into());
    }
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
    pub sample_divider: u32,
    pub sample_count: usize,
    pub a: Complex,
    pub b: Complex,
    pub c: Complex,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Calibration {
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
            || a.sample_divider != b.sample_divider
            || a.packed_samples.len() != b.packed_samples.len()
        {
            return Err("frequency, sample rate or record length differ".into());
        }
    }
    Ok(())
}
pub fn calibrate(
    short: &Sweep,
    load1: &Sweep,
    z1: f64,
    load2: &Sweep,
    z2: f64,
) -> Result<Calibration> {
    compatible(short, load1)?;
    compatible(short, load2)?;
    let mut points = Vec::new();
    for ((s, r1), r2) in short.records.iter().zip(&load1.records).zip(&load2.records) {
        let ms = analyze(s, short.setup.range_ohm)?;
        let m1 = analyze(r1, short.setup.range_ohm)?;
        let m2 = analyze(r2, short.setup.range_ohm)?;
        // Short intentionally has near-zero voltage. Current and clipping still matter.
        if !ms.current.valid_signal()
            || ms.voltage.clipped_samples > 0
            || ms.current.clipped_samples > 0
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
            sample_divider: s.sample_divider,
            sample_count: s.packed_samples.len(),
            a,
            b,
            c,
        });
    }
    Ok(Calibration {
        setup: short.setup.clone(),
        model: "bilinear-short-two-resistors-v1".into(),
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
    if cal.setup != *setup || cal.model != "bilinear-short-two-resistors-v1" {
        return Err("calibration does not match unit/fixture/range/clock/revision".into());
    }
    let p = cal
        .points
        .iter()
        .find(|p| {
            p.tuning_word == record.tuning_word
                && p.sample_divider == record.sample_divider
                && p.sample_count == record.packed_samples.len()
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
    pub rms_codes: [f64; 2],
    pub rms_volts: [f64; 2],
    pub tone_peak_codes: [f64; 2],
    pub clipped_samples: [usize; 2],
}
pub fn noise(record: &Record) -> Result<Noise> {
    record.validate()?;
    if record.source_enabled {
        return Err("noise analysis requires a source-off record".into());
    }
    let hz = frequency_hz(record.tuning_word);
    let rate = SAMPLE_BASE_HZ / f64::from(record.sample_divider);
    let decoded: Vec<_> = record
        .packed_samples
        .iter()
        .map(|&v| decode_word(v))
        .collect();
    let mut result = Noise {
        frequency_hz: hz,
        rms_codes: [0.0; 2],
        rms_volts: [0.0; 2],
        tone_peak_codes: [0.0; 2],
        clipped_samples: [0; 2],
    };
    for channel in 0..2 {
        let samples: Vec<_> = decoded.iter().map(|v| v[channel]).collect();
        let fitted = fit(&samples, hz, rate)?;
        let rms = (samples
            .iter()
            .map(|&v| (f64::from(v) - fitted.dc_codes).powi(2))
            .sum::<f64>()
            / samples.len() as f64)
            .sqrt();
        result.rms_codes[channel] = rms;
        result.rms_volts[channel] = rms * 4.096 / 32768.0;
        result.tone_peak_codes[channel] = fitted.phasor_codes.abs();
        result.clipped_samples[channel] = fitted.clipped_samples;
    }
    Ok(result)
}

//! Complex fixture calibration and recorded measurement data. No hardware accuracy is implied.
use std::ops::{Add, Div, Mul, Sub};

use serde::{Deserialize, Serialize};

pub mod instrument;
pub type Result<T> = std::result::Result<T, String>;

#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize, PartialEq)]
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

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Setup {
    pub board_revision: String,
    pub unit: String,
    pub fixture: String,
    pub range: String,
    pub clock_hz: u32,
    pub excitation_range: u8,
    pub pga: u8,
    pub settling_cycles: u16,
    pub averages: u16,
    pub dft_sign: String,
}
impl Setup {
    pub fn validate(&self) -> Result<()> {
        range_bounds(&self.range)?;
        if self.board_revision != "A"
            || self.unit.trim().is_empty()
            || self.fixture.trim().is_empty()
            || self.clock_hz != 16_000_000
            || self.excitation_range != 4
            || self.pga != 1
            || self.settling_cycles == 0
            || self.settling_cycles > 511
            || self.averages == 0
            || self.averages > 64
            || self.dft_sign != "AD5933-real-minus-i-imag"
        {
            return Err("unsupported or incomplete revision-A setup metadata".into());
        }
        Ok(())
    }
}
pub fn range_bounds(range: &str) -> Result<(f64, f64, f64)> {
    match range {
        "r20" => Ok((5.0, 50.0, 1_000.0)),
        "r200" => Ok((50.0, 500.0, 10_000.0)),
        "r2k" => Ok((500.0, 5_000.0, 10_000.0)),
        "r20k" => Ok((5_000.0, 50_000.0, 10_000.0)),
        _ => Err("range must be r20, r200, r2k, or r20k".into()),
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Point {
    pub frequency_word: u32,
    pub frequency_hz: f64,
    pub raw: Complex,
    /// Largest absolute individual DFT component before averaging; not an ADC clipping detector.
    pub peak_dft_component: u32,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Sweep {
    pub schema: String,
    pub captured_unix_seconds: u64,
    pub setup: Setup,
    pub points: Vec<Point>,
}
impl Sweep {
    pub fn validate(&self) -> Result<()> {
        self.setup.validate()?;
        if self.schema != "temper-lcr-raw-v1" || self.points.is_empty() || self.points.len() > 512 {
            return Err("invalid raw sweep schema or point count".into());
        }
        let (_, _, minimum) = range_bounds(&self.setup.range)?;
        let lsb = self.setup.clock_hz as f64 / 536_870_912.0;
        for (i, p) in self.points.iter().enumerate() {
            let expected = p.frequency_word as f64 * lsb;
            if !p.raw.finite()
                || !p.frequency_hz.is_finite()
                || p.frequency_word > 0xff_ffff
                || p.frequency_hz < minimum - lsb
                || p.frequency_hz > 100_000.0
                || (p.frequency_hz - expected).abs() > 1e-7
                || p.peak_dft_component >= 32_000
                || p.raw.re.abs() > 32_000.0
                || p.raw.im.abs() > 32_000.0
                || (i > 0 && self.points[i - 1].frequency_word >= p.frequency_word)
            {
                return Err(format!("invalid/near-register-limit raw point {i}"));
            }
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CalibrationPoint {
    pub frequency_word: u32,
    pub frequency_hz: f64,
    pub offset: Complex,
    pub scale: Complex,
    pub series: Complex,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Calibration {
    pub schema: String,
    pub setup: Setup,
    pub load_a_ohm: f64,
    pub load_b_ohm: f64,
    pub input_capture_times: [u64; 3],
    pub points: Vec<CalibrationPoint>,
}
fn matching(a: &Sweep, b: &Sweep) -> Result<()> {
    a.validate()?;
    b.validate()?;
    if a.setup != b.setup
        || a.points.len() != b.points.len()
        || a.points
            .iter()
            .zip(&b.points)
            .any(|(x, y)| x.frequency_word != y.frequency_word)
    {
        return Err(
            "sweeps have different unit, fixture, range, acquisition settings, or frequency grid"
                .into(),
        );
    }
    Ok(())
}
pub fn fit(open: &Sweep, a: &Sweep, ra: f64, b: &Sweep, rb: f64) -> Result<Calibration> {
    matching(open, a)?;
    matching(open, b)?;
    let (lo, hi, _) = range_bounds(&open.setup.range)?;
    if !ra.is_finite()
        || !rb.is_finite()
        || ra < lo
        || ra > hi
        || rb < lo
        || rb > hi
        || (ra - rb).abs() < 0.2 * ra.max(rb)
    {
        return Err("use two distinct measured resistive standards in this range, separated by at least 20%".into());
    }
    let mut points = Vec::with_capacity(open.points.len());
    for ((o, a), b) in open.points.iter().zip(&a.points).zip(&b.points) {
        let ya = a.raw - o.raw;
        let yb = b.raw - o.raw;
        let separation = (ya - yb).abs();
        if ya.abs() < 8.0
            || yb.abs() < 8.0
            || separation < 8.0
            || separation < 0.05 * ya.abs().max(yb.abs())
        {
            return Err(format!(
                "ill-conditioned calibration at {} Hz",
                o.frequency_hz
            ));
        }
        let series = (yb * Complex::new(rb, 0.0) - ya * Complex::new(ra, 0.0)) / (ya - yb);
        let scale = ya * (Complex::new(ra, 0.0) + series);
        if !series.finite() || !scale.finite() || scale.abs() < 1.0 || series.abs() > hi {
            return Err(format!("implausible calibration at {} Hz", o.frequency_hz));
        }
        points.push(CalibrationPoint {
            frequency_word: o.frequency_word,
            frequency_hz: o.frequency_hz,
            offset: o.raw,
            scale,
            series,
        });
    }
    Ok(Calibration {
        schema: "temper-lcr-cal-v1".into(),
        setup: open.setup.clone(),
        load_a_ohm: ra,
        load_b_ohm: rb,
        input_capture_times: [
            open.captured_unix_seconds,
            a.captured_unix_seconds,
            b.captured_unix_seconds,
        ],
        points,
    })
}
pub fn correct(cal: &Calibration, sweep: &Sweep) -> Result<Vec<Complex>> {
    sweep.validate()?;
    if cal.schema != "temper-lcr-cal-v1"
        || cal.setup != sweep.setup
        || cal.points.len() != sweep.points.len()
    {
        return Err("calibration metadata/grid mismatch; recalibrate this exact setup".into());
    }
    let mut result = Vec::with_capacity(sweep.points.len());
    for (c, p) in cal.points.iter().zip(&sweep.points) {
        if c.frequency_word != p.frequency_word
            || c.frequency_hz != p.frequency_hz
            || !c.offset.finite()
            || !c.scale.finite()
            || !c.series.finite()
            || c.scale.abs() < 1.0
        {
            return Err("invalid calibration point or mismatched frequency".into());
        }
        let y = p.raw - c.offset;
        if y.abs() < 8.0 {
            return Err(format!(
                "signal too close to open/noise at {} Hz",
                p.frequency_hz
            ));
        }
        let z = c.scale / y - c.series;
        if !z.finite() {
            return Err("non-finite corrected impedance".into());
        }
        result.push(z);
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn setup() -> Setup {
        Setup {
            board_revision: "A".into(),
            unit: "test1".into(),
            fixture: "fixture1".into(),
            range: "r20".into(),
            clock_hz: 16_000_000,
            excitation_range: 4,
            pga: 1,
            settling_cycles: 15,
            averages: 4,
            dft_sign: "AD5933-real-minus-i-imag".into(),
        }
    }
    fn sweep(raw: Complex) -> Sweep {
        Sweep {
            schema: "temper-lcr-raw-v1".into(),
            captured_unix_seconds: 0,
            setup: setup(),
            points: vec![Point {
                frequency_word: 1_677_721,
                frequency_hz: 1_677_721.0 * 16_000_000.0 / 536_870_912.0,
                raw,
                peak_dft_component: 10000,
            }],
        }
    }
    #[test]
    fn solves_series_and_open_error_for_a_capacitor() {
        // Explicit independently calculated vector: o=(10,5), k=(100000,0), zs=(10,0).
        let o = sweep(Complex::new(10.0, 5.0));
        let a = sweep(Complex::new(5010.0, 5.0)); // 10 ohm standard
        let b = sweep(Complex::new(2010.0, 5.0)); // 40 ohm standard
        let c = fit(&o, &a, 10.0, &b, 40.0).unwrap();
        // 10-j20 ohm DUT => 100000/(20-j20)+o = 2510+j2505.
        let z = correct(&c, &sweep(Complex::new(2510.0, 2505.0))).unwrap()[0];
        assert!((z.re - 10.0).abs() < 1e-9 && (z.im + 20.0).abs() < 1e-9);
    }
    #[test]
    fn rejects_identical_reference_measurements() {
        let o = sweep(Complex::new(0.0, 0.0));
        let a = sweep(Complex::new(100.0, 0.0));
        assert!(fit(&o, &a, 10.0, &a, 40.0).is_err());
    }
    #[test]
    fn refuses_wrong_physical_range_metadata() {
        let o = sweep(Complex::new(0.0, 0.0));
        let a = sweep(Complex::new(10000.0, 0.0));
        let b = sweep(Complex::new(2500.0, 0.0));
        let c = fit(&o, &a, 10.0, &b, 40.0).unwrap();
        let mut s = a;
        s.setup.range = "r200".into();
        assert!(correct(&c, &s).is_err());
    }
    #[test]
    fn rejects_nan_and_duplicate_frequencies() {
        let mut s = sweep(Complex::new(f64::NAN, 0.0));
        assert!(s.validate().is_err());
        s.points[0].raw = Complex::new(100.0, 0.0);
        s.points.push(s.points[0].clone());
        assert!(s.validate().is_err());
    }
}

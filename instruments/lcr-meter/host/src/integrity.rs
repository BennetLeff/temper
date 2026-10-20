//! Measurement-integrity checks from `validation/power-spurs` (R1 and R2).
//!
//! * [`frequency_hazards`] predicts, before capturing, which AD9833 harmonics
//!   and USB start-of-frame (SOF) lines the least-squares fit cannot reject at
//!   a DDS frequency, boxcar decimation and record length.
//! * [`source_off_check`] measures, after capturing, the tone that a
//!   source-off (DDS asleep) record shows at the measurement frequency.
//!
//! The hazard model is exact for the host fit: an interferer at physical
//! frequency p reaches the fit as D(p) cos(2 pi p t_k + phi) at the boxcar
//! window centres t_k (the boxcar is real when referenced to the centre), so
//! its error relative to the signal is |D(p) / D(f)| times the worst-phase
//! response of the DC + cos + sin least-squares estimator, computed here in
//! closed form from geometric sums. No folding approximation is involved; the
//! alias frequency is reported for reading only.
use crate::{
    boxcar_gain, decimation_for, fit_channel, frequency_hz, frequency_word, output_rate_hz,
    Complex, Record, Result, CONVERSION_RATE_HZ, DEFAULT_COUNT,
};
use serde::{Deserialize, Serialize};
use std::f64::consts::TAU;

/// Conservative per-harmonic AD9833 level, relative to the fundamental:
/// the THD maximum (-56 dBc, harmonics 2-6, `sources/new/AD9833.txt` spec
/// table, AD9833BRMZ) applied to every harmonic. It is above the -60 dBc
/// typical wideband SFDR (largest spur 0 to Nyquist); the datasheet gives no
/// guaranteed limit for harmonics above the sixth. As in
/// `validation/power-spurs/dds_spurs.py`, the level at k f is then scaled by
/// the reconstruction filter ratio |H(k f) / H(f)| ([`reconstruction_filter`]);
/// no credit is taken for the amplifiers or for the DUT ratio.
pub const AD9833_HARMONIC_BOUND_DBC: f64 = -56.0;
/// Highest AD9833 harmonic considered (as in `validation/power-spurs`).
pub const DDS_HARMONIC_MAX: u32 = 200;
/// Largest acceptable fitted error from one bounded DDS harmonic, relative to
/// the fundamental: one tenth of the 1e-4 source-off budget, leaving a factor
/// of ten for the DUT ratio |Z(kf)/Z(f) - Zf(kf)/Zf(f)| that does not cancel.
pub const DDS_LEAKAGE_LIMIT: f64 = 1e-5;
/// USB full-speed start-of-frame rate on the host clock.
pub const USB_SOF_HZ: f64 = 1000.0;
/// USB 2.0 full-speed frame tolerance (1.000 ms +-0.0005 ms).
pub const USB_SOF_TOLERANCE: f64 = 500e-6;
/// Board crystal tolerance plus stability (+-30 ppm + +-30 ppm), which moves
/// the DDS frequency relative to the host's SOF clock.
pub const BOARD_CLOCK_TOLERANCE: f64 = 60e-6;
/// SOF harmonics considered (to 300 kHz, as in `validation/power-spurs`).
pub const SOF_HARMONIC_MAX: u32 = 300;
/// The SOF amplitude cannot be bounded from datasheets, so a frequency is
/// clean only if the fit and boxcar reject every SOF line by at least 20 dB
/// across the whole tolerance band (outside the main lobe and first
/// sidelobe). What remains is measured by the source-off check.
pub const SOF_RESPONSE_LIMIT: f64 = 0.1;
/// Source-off tone limit relative to the source-on amplitude of the channel
/// (power-spurs R2: 0.01 % of the measurement).
pub const SOURCE_OFF_LIMIT: f64 = 1e-4;
/// Nearest-clean search span either side of a requested frequency.
pub const ADVICE_SEARCH_HZ: u32 = 5000;

/// Bins around each exact alias of f that are sampled densely for SOF bands.
/// Beyond 16 bins the rectangular sidelobe envelope 1/(pi x bins) is below
/// 0.02, five times under [`SOF_RESPONSE_LIMIT`]; band edges and the nearest
/// point are always evaluated exactly as well.
const DENSE_BINS: f64 = 16.0;
const DENSE_STEP_BINS: f64 = 0.05;

/// AD9833 200 ohm output resistance into R30 330 ohm / C34 1 nF and R31
/// 330 ohm / C35 1 nF (`manufacturing/bom-complete.csv`; nets DDS_OUT, LP1,
/// LP2), as `validation/power-spurs/common.py::recon_filter`. Returns |H(f)|.
pub fn reconstruction_filter(hz: f64) -> f64 {
    let (r0, r1, r2, c1, c2) = (200.0, 330.0, 330.0, 1e-9, 1e-9);
    let one = Complex::new(1.0, 0.0);
    let s = Complex::new(0.0, TAU * hz);
    let zc2 = one / (s * Complex::new(c2, 0.0));
    let z2 = Complex::new(r2, 0.0) + zc2;
    let z1p = one / (s * Complex::new(c1, 0.0) + one / z2);
    let v1 = z1p / (Complex::new(r0 + r1, 0.0) + z1p);
    (v1 * zc2 / z2).abs()
}

fn frac(x: f64) -> f64 {
    x - x.round()
}
fn cis(cycles: f64) -> Complex {
    let a = TAU * frac(cycles);
    Complex::new(a.cos(), a.sin())
}
fn scale(z: Complex, s: f64) -> Complex {
    Complex::new(z.re * s, z.im * s)
}
/// sum_{k=0}^{m-1} exp(i 2 pi r k), r in cycles per sample.
fn geometric(r: f64, m: usize) -> Complex {
    let g = TAU * frac(r);
    let half = (g / 2.0).sin();
    if half.abs() < 1e-300 {
        return Complex::new(m as f64, 0.0);
    }
    scale(
        cis(frac(r) * (m as f64 - 1.0) / 2.0),
        (m as f64 * g / 2.0).sin() / half,
    )
}

/// The host's DC + cos + sin least-squares estimator for one acquisition.
struct FitModel {
    f: f64,
    decimation: u32,
    count: usize,
    inverse: [[f64; 3]; 3],
    signal_gain: f64,
}
impl FitModel {
    fn new(f: f64, decimation: u32, count: usize) -> Result<Self> {
        if !(f > 0.0 && f < output_rate_hz(decimation) / 2.0) || count < 16 {
            return Err(
                "invalid frequency, decimation or record length for the hazard model".into(),
            );
        }
        // Gram matrix exactly as `fit` accumulates it.
        let mut g = [[0.0; 3]; 3];
        for k in 0..count {
            let angle = TAU * f * crate::output_time_s(k, decimation);
            let basis = [1.0, angle.cos(), angle.sin()];
            for row in 0..3 {
                for col in 0..3 {
                    g[row][col] += basis[row] * basis[col];
                }
            }
        }
        let det = g[0][0] * (g[1][1] * g[2][2] - g[1][2] * g[2][1])
            - g[0][1] * (g[1][0] * g[2][2] - g[1][2] * g[2][0])
            + g[0][2] * (g[1][0] * g[2][1] - g[1][1] * g[2][0]);
        if det.abs() < 1e-9 {
            return Err("singular fit model".into());
        }
        let mut inverse = [[0.0; 3]; 3];
        for (r, row) in inverse.iter_mut().enumerate() {
            for (c, value) in row.iter_mut().enumerate() {
                let (r1, r2) = ((c + 1) % 3, (c + 2) % 3);
                let (c1, c2) = ((r + 1) % 3, (r + 2) % 3);
                *value = (g[r1][c1] * g[r2][c2] - g[r1][c2] * g[r2][c1]) / det;
            }
        }
        Ok(Self {
            f,
            decimation,
            count,
            inverse,
            signal_gain: boxcar_gain(f, decimation).abs(),
        })
    }
    fn bin_hz(&self) -> f64 {
        output_rate_hz(self.decimation) / self.count as f64
    }
    /// Worst-phase fitted phasor magnitude, relative to the fitted signal, for
    /// a unit tone at physical frequency `p` (before the boxcar), including
    /// the boxcar ratio |D(p) / D(f)|.
    fn response(&self, p: f64) -> f64 {
        let n = f64::from(self.decimation);
        let centre = (n - 1.0) / 2.0;
        let (rp, pp) = (p * n / CONVERSION_RATE_HZ, p * centre / CONVERSION_RATE_HZ);
        let (rw, pw) = (
            self.f * n / CONVERSION_RATE_HZ,
            self.f * centre / CONVERSION_RATE_HZ,
        );
        let base = cis(pp) * geometric(rp, self.count);
        let sum = cis(pp + pw) * geometric(rp + rw, self.count);
        let diff = cis(pp - pw) * geometric(rp - rw, self.count);
        // Projections of cos(A) and sin(A) onto [1, cos(B), sin(B)].
        let u = [base.re, 0.5 * (sum.re + diff.re), 0.5 * (sum.im - diff.im)];
        let v = [base.im, 0.5 * (sum.im + diff.im), 0.5 * (diff.re - sum.re)];
        let solve = |x: [f64; 3]| {
            let row = |r: usize| (0..3).map(|c| self.inverse[r][c] * x[c]).sum::<f64>();
            (row(1), row(2))
        };
        let ((cc, sc), (cs, ss)) = (solve(u), solve(v));
        let pp2 = cc * cc + sc * sc + cs * cs + ss * ss;
        let q = cc * ss - cs * sc;
        let sigma = (pp2 / 2.0 + (pp2 * pp2 / 4.0 - q * q).max(0.0).sqrt()).sqrt();
        sigma * boxcar_gain(p, self.decimation).abs() / self.signal_gain
    }
    fn alias(&self, p: f64) -> f64 {
        let fs = output_rate_hz(self.decimation);
        let a = p.rem_euclid(fs);
        if a > fs / 2.0 {
            fs - a
        } else {
            a
        }
    }
    /// Physical frequencies m fs +- f, which alias exactly onto f, near [lo, hi].
    fn exact_aliases(&self, lo: f64, hi: f64) -> Vec<f64> {
        let fs = output_rate_hz(self.decimation);
        let margin = DENSE_BINS * self.bin_hz();
        let mut out = Vec::new();
        for sign in [1.0, -1.0] {
            let first = ((lo - margin - sign * self.f) / fs).floor() as i64;
            let last = ((hi + margin - sign * self.f) / fs).ceil() as i64;
            for m in first..=last {
                out.push(m as f64 * fs + sign * self.f);
            }
        }
        out
    }
}

/// One interferer that the fit cannot reject well enough, or that lands in
/// the fit's main lobe (within one bin of the DDS frequency after aliasing).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Interference {
    /// "AD9833 harmonic" or "USB SOF harmonic".
    pub source: String,
    /// Harmonic order (k for the DDS, h for 1 kHz SOF lines).
    pub order: u32,
    /// Worst physical frequency (for SOF, within the +-560 ppm band).
    pub physical_hz: f64,
    /// Half-width of the physical tolerance band (0 for crystal-locked DDS).
    pub tolerance_hz: f64,
    /// Where `physical_hz` lands in the output band [0, rate/2].
    pub alias_hz: f64,
    /// (alias - f) in fit bins (output rate / record length).
    pub offset_bins: f64,
    /// Fit and boxcar response relative to a unit signal (1 = no rejection).
    pub response: f64,
    /// Bounded level relative to the fundamental after the reconstruction
    /// filter; absent when unbounded (SOF).
    pub level_bound: Option<f64>,
    /// Predicted fitted error relative to the signal: response x level bound
    /// (response alone when unbounded).
    pub leakage: f64,
    /// Limit applied to `leakage`.
    pub limit: f64,
    /// Some part of the tolerance band is within one bin of f after aliasing.
    pub main_lobe: bool,
    /// `leakage` exceeds `limit`.
    pub hazard: bool,
}
impl Interference {
    pub fn describe(&self) -> String {
        let tolerance = if self.tolerance_hz > 0.0 {
            format!(" +-{:.2} Hz", self.tolerance_hz)
        } else {
            String::new()
        };
        format!(
            "{} {} at {:.2} Hz{tolerance} aliases to {:.2} Hz, {:+.2} bins from f{}; fit+boxcar response {:.3e}, predicted error {:.3e} > limit {:.0e}",
            self.source,
            self.order,
            self.physical_hz,
            self.alias_hz,
            self.offset_bins,
            if self.main_lobe { " (main lobe)" } else { "" },
            self.response,
            self.leakage,
            self.limit
        )
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct HazardReport {
    /// Quantized DDS frequency that is actually generated.
    pub frequency_hz: f64,
    pub decimation: u32,
    pub sample_count: usize,
    /// Fit main-lobe half-width.
    pub bin_hz: f64,
    /// Worst fit + boxcar response to any SOF line over its tolerance band.
    pub worst_sof_response: f64,
    /// Worst predicted error from any AD9833 harmonic at the bounded level.
    pub worst_dds_leakage: f64,
    /// Main-lobe interferers and every interferer above its limit.
    pub interference: Vec<Interference>,
    /// True when any interferer is above its limit.
    pub hazardous: bool,
}
impl HazardReport {
    pub fn hazards(&self) -> impl Iterator<Item = &Interference> {
        self.interference.iter().filter(|i| i.hazard)
    }
}

/// R1: interference that the least-squares fit cannot reject at DDS frequency
/// `dds_hz` (already quantized), boxcar `decimation` and `count` outputs.
pub fn frequency_hazards(dds_hz: f64, decimation: u32, count: usize) -> Result<HazardReport> {
    let model = FitModel::new(dds_hz, decimation, count)?;
    let bin = model.bin_hz();
    let bound = 10f64.powf(AD9833_HARMONIC_BOUND_DBC / 20.0);
    let fundamental = reconstruction_filter(dds_hz);
    let mut interference = Vec::new();
    let mut worst_dds: f64 = 0.0;
    let mut worst_sof: f64 = 0.0;
    let mut push = |source: &str,
                    order: u32,
                    p: f64,
                    tolerance: f64,
                    response: f64,
                    bound: Option<f64>,
                    limit: f64,
                    main_lobe: bool| {
        let alias = model.alias(p);
        let leakage = response * bound.unwrap_or(1.0);
        let hazard = leakage > limit;
        if hazard || main_lobe {
            interference.push(Interference {
                source: source.into(),
                order,
                physical_hz: p,
                tolerance_hz: tolerance,
                alias_hz: alias,
                offset_bins: (alias - dds_hz) / bin,
                response,
                level_bound: bound,
                leakage,
                limit,
                main_lobe,
                hazard,
            });
        }
        leakage
    };
    for k in 2..=DDS_HARMONIC_MAX {
        let p = f64::from(k) * dds_hz;
        let main_lobe = (model.alias(p) - dds_hz).abs() < bin;
        let leakage = push(
            "AD9833 harmonic",
            k,
            p,
            0.0,
            model.response(p),
            Some(bound * reconstruction_filter(p) / fundamental),
            DDS_LEAKAGE_LIMIT,
            main_lobe,
        );
        worst_dds = worst_dds.max(leakage);
    }
    let tolerance = USB_SOF_TOLERANCE + BOARD_CLOCK_TOLERANCE;
    for h in 1..=SOF_HARMONIC_MAX {
        let nominal = f64::from(h) * USB_SOF_HZ;
        let (lo, hi) = (nominal * (1.0 - tolerance), nominal * (1.0 + tolerance));
        let mut points = vec![lo, nominal, hi];
        let mut main_lobe = false;
        for centre in model.exact_aliases(lo, hi) {
            let nearest = centre.clamp(lo, hi);
            points.push(nearest);
            main_lobe |= (nearest - centre).abs() < bin;
            let (a, b) = (
                (centre - DENSE_BINS * bin).max(lo),
                (centre + DENSE_BINS * bin).min(hi),
            );
            if a < b {
                let steps = ((b - a) / (DENSE_STEP_BINS * bin)).ceil() as usize;
                points.extend((0..=steps).map(|i| a + (b - a) * i as f64 / steps as f64));
            }
        }
        let (p, response) =
            points
                .into_iter()
                .map(|p| (p, model.response(p)))
                .fold(
                    (nominal, 0.0),
                    |best, x| if x.1 > best.1 { x } else { best },
                );
        let leakage = push(
            "USB SOF harmonic",
            h,
            p,
            nominal * tolerance,
            response,
            None,
            SOF_RESPONSE_LIMIT,
            main_lobe,
        );
        worst_sof = worst_sof.max(leakage);
    }
    let hazardous = interference.iter().any(|i| i.hazard);
    Ok(HazardReport {
        frequency_hz: dds_hz,
        decimation,
        sample_count: count,
        bin_hz: bin,
        worst_sof_response: worst_sof,
        worst_dds_leakage: worst_dds,
        interference,
        hazardous,
    })
}

/// Hazards of a requested frequency as `capture` would acquire it.
pub fn request_hazards(hz: f64) -> Result<HazardReport> {
    let word = frequency_word(hz)?;
    frequency_hazards(frequency_hz(word), decimation_for(hz), DEFAULT_COUNT)
}

/// One line per hazard, naming each and the nearest clean frequency.
pub fn hazard_error(hz: f64, report: &HazardReport) -> String {
    let mut text = format!(
        "{hz} Hz (DDS {:.4} Hz, decimation {}) is hazardous:",
        report.frequency_hz, report.decimation
    );
    for hazard in report.hazards() {
        text.push_str("\n  - ");
        text.push_str(&hazard.describe());
    }
    match nearest_clean_hz(hz) {
        Ok(Some(clean)) => text.push_str(&format!("\n  nearest clean frequency: {clean} Hz")),
        _ => text.push_str(&format!(
            "\n  no clean frequency within +-{ADVICE_SEARCH_HZ} Hz"
        )),
    }
    text
}

/// Nearest whole-hertz frequency (or `hz` itself) with no hazard, searching
/// up to [`ADVICE_SEARCH_HZ`] either side; ties go to the lower frequency.
pub fn nearest_clean_hz(hz: f64) -> Result<Option<f64>> {
    if !request_hazards(hz)?.hazardous {
        return Ok(Some(hz));
    }
    let centre = hz.round();
    for d in 1..=ADVICE_SEARCH_HZ {
        for candidate in [centre - f64::from(d), centre + f64::from(d)] {
            if (100.0..=100_000.0).contains(&candidate)
                && candidate != hz
                && !request_hazards(candidate)?.hazardous
            {
                return Ok(Some(candidate));
            }
        }
    }
    Ok(None)
}

/// `advise-grid` output for one requested frequency.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Advice {
    pub requested_hz: f64,
    pub clean: bool,
    /// Hazards at the requested frequency (empty when clean).
    pub hazards: Vec<Interference>,
    /// The request itself when clean, otherwise the nearest clean whole hertz.
    pub suggested_hz: Option<f64>,
    /// Full report at the suggested frequency.
    pub suggested: Option<HazardReport>,
}
pub fn advise(hz: f64) -> Result<Advice> {
    let report = request_hazards(hz)?;
    let suggested_hz = nearest_clean_hz(hz)?;
    let suggested = suggested_hz.map(request_hazards).transpose()?;
    Ok(Advice {
        requested_hz: hz,
        clean: !report.hazardous,
        hazards: report.hazards().cloned().collect(),
        suggested_hz,
        suggested,
    })
}

/// Hazard reports for a requested grid. Without `allow_hazard`, any hazard is
/// an error that names each hazard and the nearest clean frequency.
pub fn check_grid(freqs: &[f64], allow_hazard: bool) -> Result<Vec<HazardReport>> {
    let reports = freqs
        .iter()
        .map(|&hz| request_hazards(hz))
        .collect::<Result<Vec<_>>>()?;
    let refused: Vec<String> = freqs
        .iter()
        .zip(&reports)
        .filter(|(_, r)| r.hazardous)
        .map(|(&hz, r)| hazard_error(hz, r))
        .collect();
    if refused.is_empty() || allow_hazard {
        return Ok(reports);
    }
    let list: Vec<String> = freqs.iter().map(f64::to_string).collect();
    Err(format!(
        "{}\nRefusing to capture: interference lands where the fit cannot reject it. Run `temper-lcr advise-grid {}` for clean frequencies, or pass --allow-hazard to capture anyway (the hazards are recorded in the capture file).",
        refused.join("\n"),
        list.join(",")
    ))
}

#[derive(Clone, Copy, Debug, Default)]
pub struct CaptureOptions {
    /// False for `noise` (DDS asleep).
    pub source_on: bool,
    /// Capture hazardous frequencies and record the hazards (R1 override).
    pub allow_hazard: bool,
    /// Pair every source-on record with a source-off record (R2).
    pub source_off: bool,
    /// Judge the voltage channel of a short against its current channel.
    pub short_standard: bool,
}
pub struct CapturedGrid {
    pub records: Vec<Record>,
    /// One diagnostic per point that failed the source-off check.
    pub source_off_failures: Vec<String>,
}
/// Captures a grid through `acquire(word, decimation, source_on)`. Hazards are
/// checked before anything is acquired. With `source_off`, each source-on
/// record is followed at once by a source-off record at the same word and
/// decimation, and the check is stored in the record. Failed checks do not
/// abort the sweep: the caller saves the records and then reports failure.
pub fn capture_grid<F>(
    freqs: &[f64],
    options: CaptureOptions,
    mut acquire: F,
) -> Result<CapturedGrid>
where
    F: FnMut(u32, u32, bool) -> Result<Record>,
{
    let reports = check_grid(freqs, options.allow_hazard)?;
    let mut records = Vec::new();
    let mut source_off_failures = Vec::new();
    for (&hz, report) in freqs.iter().zip(&reports) {
        let word = frequency_word(hz)?;
        let decimation = decimation_for(hz);
        let mut record = acquire(word, decimation, options.source_on)?;
        record.allowed_hazards = report.hazards().cloned().collect();
        if options.source_on && options.source_off {
            let off = acquire(word, decimation, false)?;
            let check = source_off_check(&record, &off, options.short_standard)?;
            if !check.pass {
                source_off_failures.push(format!("{hz} Hz: {}", check.diagnostic));
            }
            record.source_off = Some(Box::new(off));
            record.source_off_check = Some(check);
        }
        records.push(record);
    }
    Ok(CapturedGrid {
        records,
        source_off_failures,
    })
}

/// R2 result for one channel of a source-on/source-off pair.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SourceOffChannel {
    /// Input-referred fitted amplitude with the source on (codes).
    pub source_on_codes: f64,
    /// Amplitude the limit is relative to (normally `source_on_codes`).
    pub reference_codes: f64,
    /// Input-referred fitted tone at f with the source off (codes).
    pub source_off_codes: f64,
    /// `SOURCE_OFF_LIMIT` x `reference_codes`.
    pub limit_codes: f64,
    /// source_off_codes / reference_codes.
    pub ratio: f64,
    /// One-sigma noise of each fitted component in the source-off record,
    /// residual RMS x sqrt(2 / count) / D(f). A tone within about three of
    /// these is consistent with noise rather than coherent interference.
    pub noise_sigma_codes: f64,
    pub pass: bool,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SourceOffCheck {
    pub frequency_hz: f64,
    pub decimation: u32,
    pub limit_ratio: f64,
    /// Short-circuit standard: the voltage channel is judged against the
    /// current-channel amplitude, which bounds the short's offset error to
    /// 1e-4 of the feedback impedance.
    pub short_standard: bool,
    /// [voltage (A), current (B)].
    pub channels: [SourceOffChannel; 2],
    pub pass: bool,
    pub diagnostic: String,
}

/// R2: fit the tone at the measurement frequency in a source-off record
/// captured right after `on` at the same tuning word, decimation and length,
/// and require it below 1e-4 of the source-on amplitude on each channel.
pub fn source_off_check(on: &Record, off: &Record, short_standard: bool) -> Result<SourceOffCheck> {
    on.validate()?;
    off.validate()?;
    if !on.source_enabled || off.source_enabled {
        return Err("source-off check needs a source-on record and a source-off record".into());
    }
    if on.tuning_word != off.tuning_word
        || on.decimation != off.decimation
        || on.sums.len() != off.sums.len()
    {
        return Err("source-off record differs in frequency, decimation or length".into());
    }
    let fits = [
        (fit_channel(on, 0)?, fit_channel(off, 0)?),
        (fit_channel(on, 1)?, fit_channel(off, 1)?),
    ];
    let count = off.sums.len() as f64;
    let current_on = fits[1].0.phasor_codes.abs();
    let channels = [0, 1].map(|channel| {
        let (on_fit, off_fit) = &fits[channel];
        let source_on = on_fit.phasor_codes.abs();
        let reference = if short_standard && channel == 0 {
            current_on
        } else {
            source_on
        };
        let source_off = off_fit.phasor_codes.abs();
        let limit = SOURCE_OFF_LIMIT * reference;
        SourceOffChannel {
            source_on_codes: source_on,
            reference_codes: reference,
            source_off_codes: source_off,
            limit_codes: limit,
            ratio: source_off / reference,
            noise_sigma_codes: off_fit.residual_rms_codes * (2.0 / count).sqrt()
                / off_fit.boxcar_gain.abs(),
            // A NaN ratio (zero reference) fails.
            pass: source_off <= limit,
        }
    });
    let pass = channels.iter().all(|c| c.pass);
    let names = ["voltage (A)", "current (B)"];
    let diagnostic = if pass {
        "source-off tone below 1e-4 of the source-on amplitude on both channels".into()
    } else {
        let failures: Vec<String> = channels
            .iter()
            .zip(names)
            .filter(|(c, _)| !c.pass)
            .map(|(c, name)| {
                let cause = if c.source_off_codes > 3.0 * c.noise_sigma_codes {
                    "coherent interference (USB SOF, ground loop, adapter or switcher) above the noise"
                } else {
                    "within 3 sigma of the source-off noise: the signal is too weak for the gate to resolve 1e-4; raise the signal or change range"
                };
                format!(
                    "{name}: source-off tone {:.4} codes = {:.2e} of {:.1} codes > {:.0e} ({cause}; noise sigma {:.4} codes)",
                    c.source_off_codes, c.ratio, c.reference_codes, SOURCE_OFF_LIMIT, c.noise_sigma_codes
                )
            })
            .collect();
        format!(
            "source-off interference at {:.4} Hz: {}",
            frequency_hz(on.tuning_word),
            failures.join("; ")
        )
    };
    Ok(SourceOffCheck {
        frequency_hz: frequency_hz(on.tuning_word),
        decimation: on.decimation,
        limit_ratio: SOURCE_OFF_LIMIT,
        short_standard,
        channels,
        pass,
        diagnostic,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::fit;
    /// The closed-form response equals the fitted phasor of synthesized
    /// boxcar means, for an interferer at the worst phase found by sweeping.
    #[test]
    fn closed_form_response_matches_the_fit() {
        for (f, n, p) in [
            (1000.0169, 20, 49_000.83),
            (50_000.041_7, 2, 450_000.375),
            (43_721.3, 2, 131_000.0),
            (60_500.0, 1, 60_444.0),
        ] {
            let model = FitModel::new(f, n, 4096).unwrap();
            let mut worst: f64 = 0.0;
            for phase in 0..32 {
                let phi = TAU * f64::from(phase) / 32.0;
                let means: Vec<f64> = (0..4096)
                    .map(|k| {
                        // Boxcar mean of N conversions of cos(2 pi p t + phi).
                        (0..n)
                            .map(|j| {
                                let t =
                                    (k as f64 * f64::from(n) + f64::from(j)) / CONVERSION_RATE_HZ;
                                (TAU * p * t + phi).cos()
                            })
                            .sum::<f64>()
                            / f64::from(n)
                    })
                    .collect();
                worst = worst.max(fit(&means, f, n).unwrap().phasor_codes.abs());
            }
            let predicted = model.response(p);
            assert!(
                worst <= predicted * 1.0001 + 1e-12 && worst > predicted * 0.99,
                "f={f} p={p}: swept {worst}, closed form {predicted}"
            );
        }
    }
}

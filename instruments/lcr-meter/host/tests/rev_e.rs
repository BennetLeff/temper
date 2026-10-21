//! Rev E (E-codec, protocol 3) host tests: wire payloads, exact tone selection, settling, DFT
//! analysis against a circuit-level virtual instrument, calibration, clipping, residual checks,
//! cross-revision rejection, and the protocol client against a fake firmware on a pseudo-terminal.
use std::f64::consts::TAU;
use std::ffi::CStr;
use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::OpenOptionsExt;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use temper_lcr::rev_e::*;
use temper_lcr::transport::{parse_codec, parse_reg, Board};
use temper_lcr::{
    calibration_coefficients, crc32, parse_calibration, parse_sweep, Calibration, CalibrationPoint,
    Complex, Setup, Sweep,
};

// ------------------------------------------------------------------ virtual instrument
const K: f64 = 0.5;
const FS: f64 = 187_500.0;
/// Volts at SOURCE_BUF per DAC word: SOURCE_LIMIT_CODE is 1.7 V peak.
const SOURCE_V_PER_CODE: f64 = 1.7 / 1_419_797_733.0;
/// 24-bit codes per differential volt at the codec input: 2 Vrms = 2 sqrt 2 V peak is 2^23.
const CODES_PER_VOLT: f64 = 8_388_608.0 / (2.0 * std::f64::consts::SQRT_2);
const MAX_CODE: i32 = 8_388_607;
const MIN_CODE: i32 = -8_388_608;

type ZFn = Arc<dyn Fn(f64) -> Complex + Send + Sync>;
fn cx(re: f64, im: f64) -> Complex {
    Complex::new(re, im)
}
fn inv(z: Complex) -> Complex {
    cx(1.0, 0.0) / z
}
fn resistor(r: f64) -> ZFn {
    Arc::new(move |_| cx(r, 0.0))
}
fn capacitor(c: f64) -> ZFn {
    Arc::new(move |hz| cx(0.0, -1.0 / (TAU * hz * c)))
}
fn coil(r: f64, l: f64) -> ZFn {
    Arc::new(move |hz| cx(r, TAU * hz * l))
}
/// Series R-L in parallel with C.
fn tank(r: f64, l: f64, c: f64) -> ZFn {
    Arc::new(move |hz| {
        let w = TAU * hz;
        inv(inv(cx(r, w * l)) + cx(0.0, w * c))
    })
}

struct XorShift(u64);
impl XorShift {
    fn unit(&mut self) -> f64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        (self.0 >> 11) as f64 / (1u64 << 52) as f64 - 1.0
    }
}

/// Port of wave_tone() in firmware-rev-e/src/wave.c.
fn tone_words(cycles: u32, period: u32, mv: u32) -> Vec<i32> {
    let amplitude = (i64::from(SOURCE_LIMIT_CODE) * i64::from(mv) / 1700) as f64;
    (0..period)
        .map(|k| {
            let phase = (u64::from(cycles) * u64::from(k)) % u64::from(period);
            (amplitude * (TAU * phase as f64 / f64::from(period)).sin()).round() as i32
        })
        .collect()
}

#[derive(Clone)]
struct Virtual {
    range: u32,
    dut: ZFn,
    /// Uniform noise amplitude in codes added to every frame of both channels.
    noise_codes: f64,
    /// Extra coherent tone on channel B: (bin, peak codes).
    interferer: Option<(usize, f64)>,
}
impl Virtual {
    fn new(range: u32, dut: ZFn) -> Self {
        Self {
            range,
            dut,
            noise_codes: 0.0,
            interferer: None,
        }
    }
    /// Channel A and B phasors per volt at SOURCE_BUF, solved from the circuit, not from the
    /// host's formula: the source drives HIGH through RG (= R_F) and R104, the DUT current splits
    /// at DUT_LO between the 100 pF to ground and R_iso into the TIA summing node,
    /// TIA out = -I_riso Z_f.
    fn responses(&self, hz: f64) -> (Complex, Complex) {
        let w = TAU * hz;
        let z = (self.dut)(hz);
        let cap_factor = cx(1.0, w * 100e-12 * 22.0);
        let rf = f64::from(self.range);
        let i_dut = inv(cx(rf + SOURCE_SERIES_OHM, 0.0) + z + cx(22.0, 0.0) / cap_factor);
        let i_riso = i_dut / cap_factor;
        let zf = cx(rf, 0.0) / cx(1.0, w * rf * 100e-12);
        let a = cx(K, 0.0) * i_dut * z;
        let b = cx(K, 0.0) * i_riso * (cx(22.0, 0.0) + zf);
        (a, b)
    }
    /// Steady-state codes on A and B per DAC word index, AC-coupled (DC is dropped).
    fn steady(&self, words: &[i32]) -> (Vec<f64>, Vec<f64>) {
        let p = words.len();
        let table: Vec<(f64, f64)> = (0..p)
            .map(|m| {
                (
                    (TAU * m as f64 / p as f64).cos(),
                    (TAU * m as f64 / p as f64).sin(),
                )
            })
            .collect();
        let mut spectrum = Vec::new();
        for k in 1..=p / 2 {
            let (mut re, mut im) = (0.0, 0.0);
            for (n, &w) in words.iter().enumerate() {
                let (c, s) = table[(k * n) % p];
                re += f64::from(w) * c;
                im -= f64::from(w) * s;
            }
            spectrum.push((k, cx(re, im)));
        }
        let largest = spectrum.iter().map(|(_, w)| w.abs()).fold(0.0, f64::max);
        let (mut a, mut b) = (vec![0.0; p], vec![0.0; p]);
        for (k, w) in spectrum {
            if w.abs() <= 1e-9 * largest {
                continue;
            }
            let (ha, hb) = self.responses(FS * k as f64 / p as f64);
            let scale =
                if 2 * k == p { 1.0 } else { 2.0 } / p as f64 * SOURCE_V_PER_CODE * CODES_PER_VOLT;
            let (ya, yb) = (ha * w, hb * w);
            for n in 0..p {
                let (c, s) = table[(k * n) % p];
                a[n] += scale * (ya.re * c - ya.im * s);
                b[n] += scale * (yb.re * c - yb.im * s);
            }
        }
        (a, b)
    }
    /// ADC code of capture frame `j` (counted from the first frame, skip included): it meets DAC
    /// word (j - 5) mod PERIOD. 24-bit quantisation and clipping.
    fn sample(&self, steady: &(Vec<f64>, Vec<f64>), j: usize, rng: &mut XorShift) -> [i32; 2] {
        let p = steady.0.len();
        let n = (j + p - FRAME_OFFSET) % p;
        let mut b = steady.1[n];
        if let Some((bin, amplitude)) = self.interferer {
            b += amplitude * (TAU * (bin * (j % p)) as f64 / p as f64).cos();
        }
        let mut code = |x: f64| {
            (x + self.noise_codes * rng.unit())
                .round()
                .clamp(f64::from(MIN_CODE), f64::from(MAX_CODE)) as i32
        };
        [code(steady.0[n]), code(b)]
    }
    /// The bytes after a `DATA` header line: 16-byte header and int64 bin sums, written here
    /// byte by byte, independent of the host's encoder.
    fn data_payload(&self, words: &[i32], skip: u32, periods: u32) -> Vec<u8> {
        let p = words.len();
        let steady = self.steady(words);
        let mut rng = XorShift(0x9e37_79b9_7f4a_7c15);
        let mut sums = vec![[0i64; 2]; p];
        let mut min = [i32::MAX; 2];
        let mut max = [i32::MIN; 2];
        for j in (skip as usize * p)..((skip + periods) as usize * p) {
            let s = self.sample(&steady, j, &mut rng);
            for c in 0..2 {
                sums[j % p][c] += i64::from(s[c]);
                min[c] = min[c].min(s[c]);
                max[c] = max[c].max(s[c]);
            }
        }
        let mut bytes = Vec::new();
        for v in [min[0], max[0], min[1], max[1]] {
            bytes.extend_from_slice(&v.to_le_bytes());
        }
        for s in sums {
            bytes.extend_from_slice(&s[0].to_le_bytes());
            bytes.extend_from_slice(&s[1].to_le_bytes());
        }
        bytes
    }
    fn raw_payload(&self, words: &[i32], count: usize) -> Vec<u8> {
        let steady = self.steady(words);
        let mut rng = XorShift(0x1234_5678_9abc_def1);
        let frames: Vec<[i32; 2]> = (0..count)
            .map(|j| self.sample(&steady, j, &mut rng))
            .collect();
        let mut bytes = Vec::new();
        for c in [0usize, 1] {
            bytes.extend_from_slice(&frames.iter().map(|f| f[c]).min().unwrap().to_le_bytes());
            bytes.extend_from_slice(&frames.iter().map(|f| f[c]).max().unwrap().to_le_bytes());
        }
        for f in &frames {
            bytes.extend_from_slice(&f[0].to_le_bytes());
            bytes.extend_from_slice(&f[1].to_le_bytes());
        }
        bytes
    }
    /// Full path in-process: payload bytes, CRC, decode, record.
    fn record(
        &self,
        source: SourceE,
        words: &[i32],
        bins: &[u32],
        skip: u32,
        periods: u32,
    ) -> RecordE {
        let bytes = self.data_payload(words, skip, periods);
        let crc = crc32(&bytes);
        verify_crc(&bytes, crc).unwrap();
        let payload = decode_data(&bytes, words.len()).unwrap();
        RecordE::from_capture(source, bins.to_vec(), skip, periods, payload, crc)
    }
    fn tone_record(&self, hz: f64, mv: u32, skip: u32, periods: u32) -> RecordE {
        let (cycles, period) = tone_for_hz(hz).unwrap();
        self.record(
            SourceE::Tone { cycles, mv },
            &tone_words(cycles, period, mv),
            &[cycles],
            skip,
            periods,
        )
    }
    /// Peak source level that puts the larger channel at 30 % of ADC full scale.
    fn mv_for(&self, hz: f64) -> u32 {
        let (a, b) = self.responses(hz);
        let per_volt = a.abs().max(b.abs()) * CODES_PER_VOLT;
        ((0.3 * 8_388_608.0 / per_volt * 1000.0).floor() as u32).clamp(1, 1700)
    }
}

fn setup_e(range: u32) -> SetupE {
    SetupE {
        revision: HARDWARE_REVISION_E.into(),
        unit_id: "test-device".into(),
        fixture: "fixture-1".into(),
        range_ohm: range,
        system_clock_hz: 120_000_000,
        sample_rate_hz: 187_500,
    }
}
fn assert_close(got: Complex, want: Complex, relative: f64, what: &str) {
    let error = (got - want).abs() / want.abs();
    assert!(
        error < relative,
        "{what}: got {got:?}, want {want:?}, relative error {error:e}"
    );
}

// ------------------------------------------------------------------ wire formats
#[test]
fn data_payload_round_trip_crc_and_length_errors() {
    let sums = vec![[i64::MIN, i64::MAX], [-3, 7], [1 << 40, -(1 << 40)]];
    let header = [-8_388_608, 8_388_607, -5, 9];
    let bytes = encode_data(header, &sums);
    assert_eq!(bytes.len(), data_payload_len(3));
    assert_eq!(bytes.len(), 16 + 16 * 3);
    // Header order: A min, A max, B min, B max, little-endian int32.
    assert_eq!(&bytes[..4], &(-8_388_608i32).to_le_bytes());
    assert_eq!(&bytes[4..8], &8_388_607i32.to_le_bytes());
    assert_eq!(&bytes[8..12], &(-5i32).to_le_bytes());
    assert_eq!(&bytes[12..16], &9i32.to_le_bytes());
    // Body: A sum then B sum as little-endian int64.
    assert_eq!(&bytes[16..24], &i64::MIN.to_le_bytes());
    assert_eq!(&bytes[24..32], &i64::MAX.to_le_bytes());
    let (h, decoded) = decode_data(&bytes, 3).unwrap();
    assert_eq!((h, decoded.as_slice()), (header, sums.as_slice()));
    for wrong in [&bytes[..bytes.len() - 1], &bytes[..15], &[][..]] {
        assert!(decode_data(wrong, 3).unwrap_err().contains("expected"));
    }
    let mut longer = bytes.clone();
    longer.push(0);
    assert!(decode_data(&longer, 3).is_err());
    assert!(decode_data(&bytes, 4).is_err());
    // CRC covers header and body.
    let crc = crc32(&bytes);
    verify_crc(&bytes, crc).unwrap();
    for position in [0, 15, 16, bytes.len() - 1] {
        let mut flipped = bytes.clone();
        flipped[position] ^= 1;
        assert!(
            verify_crc(&flipped, crc)
                .unwrap_err()
                .contains("CRC mismatch"),
            "byte {position}"
        );
    }
}
#[test]
fn raw_payload_round_trip_and_length_errors() {
    let frames = vec![[-8_388_608, 8_388_607], [1, -1], [0, 123_456]];
    let bytes = encode_raw([-8_388_608, 8_388_607, -1, 123_456], &frames);
    assert_eq!(bytes.len(), raw_payload_len(3));
    assert_eq!(bytes.len(), 16 + 8 * 3);
    assert_eq!(&bytes[16..20], &(-8_388_608i32).to_le_bytes());
    assert_eq!(&bytes[20..24], &8_388_607i32.to_le_bytes());
    let (h, decoded) = decode_raw(&bytes, 3).unwrap();
    assert_eq!(h, [-8_388_608, 8_388_607, -1, 123_456]);
    assert_eq!(decoded, frames);
    assert!(decode_raw(&bytes[..bytes.len() - 4], 3).is_err());
    assert!(decode_raw(&bytes, 2).is_err());
    let stats = raw_stats(&frames);
    assert_eq!(
        (stats.min_code, stats.max_code),
        ([-8_388_608, -1], [1, 8_388_607])
    );
    assert!(stats.clipped[0] && stats.clipped[1]);
}
#[test]
fn reply_headers_and_extremes_are_checked() {
    assert_eq!(
        parse_reply_header("DATA 3 375 125 4242", "DATA").unwrap(),
        (375, 125, 4242)
    );
    assert_eq!(
        parse_reply_header("RAW 3 100 0 7", "RAW").unwrap(),
        (100, 0, 7)
    );
    assert!(parse_reply_header("ERR stream_sync", "DATA")
        .unwrap_err()
        .contains("stream_sync"));
    assert!(parse_reply_header("DATA 2 375 125 1", "DATA").is_err());
    assert!(parse_reply_header("RAW 3 375 125 1", "DATA").is_err());
    assert!(parse_reply_header("DATA 3 375 x 1", "DATA").is_err());
    assert!(parse_reply_header("DATA 3 375 125", "DATA").is_err());
    check_header([-8_388_608, 8_388_607, 0, 0]).unwrap();
    assert!(check_header([5, 4, 0, 0]).is_err());
    assert!(check_header([0, 0, 0, 8_388_608]).is_err());
    assert!(check_header([0, 0, -8_388_609, 0]).is_err());
    assert_eq!(parse_codec("CODEC 200 112 3 0 0").unwrap().clk_det_sts0, 3);
    assert!(parse_codec("CODEC 200 112 3 0").is_err());
    assert!(parse_codec("CODEC 1 2 3 4 300").is_err());
    assert_eq!(parse_reg("REG 5 17", 5).unwrap(), 17);
    assert!(parse_reg("REG 6 17", 5).is_err());
}
#[test]
fn wave_encoding_enforces_the_source_limit_on_the_host() {
    let words: Vec<i32> = (0..16).map(|k| (k - 8) * 1000).collect();
    let (bytes, crc) = encode_wave(&words).unwrap();
    assert_eq!(bytes.len(), 64);
    assert_eq!(&bytes[..4], &(-8000i32).to_le_bytes());
    assert_eq!(crc, crc32(&bytes));
    let mut edge = vec![0; 16];
    edge[0] = SOURCE_LIMIT_CODE;
    edge[1] = -SOURCE_LIMIT_CODE;
    check_wave(&edge).unwrap();
    edge[2] = SOURCE_LIMIT_CODE + 1;
    assert!(check_wave(&edge).unwrap_err().contains("source limit"));
    edge[2] = -SOURCE_LIMIT_CODE - 1;
    assert!(check_wave(&edge).is_err());
    edge[2] = i32::MIN;
    assert!(encode_wave(&edge).is_err());
    assert!(check_wave(&[0; 15]).is_err());
    assert!(check_wave(&[0; 4097]).is_err());
    check_wave(&[0; 4096]).unwrap();
    assert!(parse_wave_text("1, 2\n3 # comment\n-4")
        .unwrap_err()
        .contains("words"));
    let text: String = (0..16).map(|k| format!("{k}\n")).collect();
    assert_eq!(parse_wave_text(&text).unwrap().len(), 16);
    assert!(parse_wave_text("x").is_err());
}

// ------------------------------------------------------------------ tones
#[test]
fn exact_period_selection() {
    assert_eq!(tone_for_hz(1000.0).unwrap(), (2, 375));
    assert_eq!(tone_for_hz(27_000.0).unwrap(), (18, 125));
    assert_eq!(tone_for_hz(60_000.0).unwrap(), (8, 25));
    assert_eq!(tone_for_hz(1500.0).unwrap(), (1, 125));
    // Reduced period below the firmware minimum of 16: the smallest legal multiple.
    assert_eq!(tone_for_hz(37_500.0).unwrap(), (4, 20));
    assert_eq!(tone_for_hz(85_000.0).unwrap(), (34, 75));
    assert_eq!(tone_for_hz(187_500.0 / 4096.0).unwrap(), (1, 4096));
    // Refusals: inexact, above 85 kHz, nonsense.
    let inexact = tone_for_hz(1000.5).unwrap_err();
    assert!(
        inexact.contains("cannot be represented exactly") && inexact.contains("nearest exact"),
        "{inexact}"
    );
    assert!(tone_for_hz(45.0).is_err());
    assert!(tone_for_hz(85_001.0).unwrap_err().contains("exceeds"));
    assert!(tone_for_hz(90_000.0).is_err());
    assert!(
        tone_for_hz(0.0).is_err() && tone_for_hz(-1.0).is_err() && tone_for_hz(f64::NAN).is_err()
    );
    // Every exact tone is found with the smallest legal period and the same ratio.
    for period in (16..=4096u32).step_by(7) {
        for cycles in [1, 2, 3, period / 3, period * 4 / 10] {
            if cycles == 0 || 2 * cycles >= period || 187_500 * cycles > 85_000 * period {
                continue;
            }
            let hz = 187_500.0 * f64::from(cycles) / f64::from(period);
            let (c, p) = tone_for_hz(hz).unwrap();
            assert_eq!(
                u64::from(c) * u64::from(period),
                u64::from(cycles) * u64::from(p),
                "{cycles}/{period}"
            );
            assert!(p <= period && p >= 16, "{cycles}/{period} -> {c}/{p}");
            // No smaller legal period represents the same frequency.
            for smaller in 16..p {
                assert_ne!(
                    (u64::from(cycles) * u64::from(smaller)) % u64::from(period),
                    0,
                    "{cycles}/{period} also fits {smaller}"
                );
            }
        }
    }
}
#[test]
fn tone_rules_mirror_the_firmware() {
    check_tone(2, 375, 1700).unwrap();
    check_tone(7, 16, 1).unwrap(); // 82.0 kHz
    assert!(check_tone(8, 16, 100).unwrap_err().contains("85000")); // 93.75 kHz
    assert!(check_tone(2, 15, 100).unwrap_err().contains("period"));
    assert!(check_tone(2, 4097, 100).is_err());
    assert!(check_tone(0, 375, 100).is_err());
    assert!(check_tone(2, 375, 0).unwrap_err().contains("level"));
    assert!(check_tone(2, 375, 1701).is_err());
    // 85 kHz exactly is allowed, one more cycle is not.
    check_tone(34, 75, 100).unwrap();
    assert!(check_tone(35, 75, 100).is_err());
    for bins in [&[0u32][..], &[8], &[1, 1], &[]] {
        assert!(check_bins(bins, 16).is_err(), "{bins:?}");
    }
    check_bins(&[1, 7], 16).unwrap();
    assert!(check_bins(&[8], 16).is_err());
    assert!(check_bins(&[35], 75).is_err());
}
#[test]
fn settling_and_capture_length_defaults() {
    // A default capture sums at least 0.25 s of whole periods.
    assert_eq!(default_periods(375), 125);
    assert_eq!(default_periods(125), 375);
    assert_eq!(default_periods(4096), 12);
    assert!(f64::from(default_periods(25)) * 25.0 / FS >= DEFAULT_CAPTURE_SECONDS);
    assert_eq!(default_periods(4096) * 4096, 49_152);
    // Skip: the 2 x 17 codec filter frames with margin, the source floor or four tone periods,
    // and a few TIA time constants, rounded up to whole periods.
    let frames = |range: u32, hz: f64, period: u32| {
        f64::from(default_skip_periods(range, hz, period).unwrap() * period)
    };
    let need = |range: u32, hz: f64| settle_seconds(range, hz).unwrap() * FS;
    for (range, hz, period) in [
        (100, 1000.0, 375),
        (5000, 27_000.0, 125),
        (100_000, 60_000.0, 25),
        (100, 187_500.0 / 4096.0, 4096),
    ] {
        assert!(frames(range, hz, period) >= need(range, hz), "{range} {hz}");
        assert!(
            frames(range, hz, period) < need(range, hz) + f64::from(period) + 1.0,
            "{range} {hz}"
        );
        assert!(need(range, hz) > 68.0, "covers the filters with margin");
    }
    // Low frequencies wait for several tone periods; high ones for the 2 ms floor.
    assert!(settle_seconds(100, 100.0).unwrap() > 0.04);
    assert!(settle_seconds(100, 60_000.0).unwrap() < 0.004);
    assert!(settle_seconds(100, 60_000.0).unwrap() > SOURCE_SETTLE_FLOOR_S);
    // The range matters through the TIA feedback time constant.
    assert!(settle_seconds(100_000, 60_000.0).unwrap() > settle_seconds(100, 60_000.0).unwrap());
    assert!(settle_seconds(7, 1000.0).is_err());
    assert_eq!(default_skip_periods(100, 1000.0, 375).unwrap(), 3);
    assert_eq!(periods_for_seconds(1.0, 375).unwrap(), 500);
    assert!(periods_for_seconds(0.0, 375).is_err() && periods_for_seconds(61.0, 375).is_err());
    check_capture(3, 125, 375).unwrap();
    assert!(check_capture(3, 0, 375).is_err());
    // 60 s = 11,250,000 frames.
    check_capture(0, 3000, 3750).unwrap();
    assert!(check_capture(0, 3001, 3750).is_err());
    // SOF lines at 1 kHz multiples are only rejected away from them.
    assert!(sof_response(1000.0, 0.25) > 0.99);
    assert!(sof_response(1000.0 + 17.0, 0.25) < 0.1);
    assert!(sof_response(27_000.0, 0.25) > 0.99);
    assert!(sof_response(1500.0, 0.25) < 0.1);
}

// ------------------------------------------------------------------ analysis
#[test]
fn virtual_instrument_payload_is_aligned_quantised_and_summed() {
    // A resistor has no frequency dependence, so channel A is the DAC word, delayed by five
    // frames, times a real gain: this pins the -5 offset, K, the 24-bit scale and the sums.
    let model = Virtual::new(100, resistor(30.0));
    let (cycles, period, mv) = (2u32, 375u32, 400u32);
    let words = tone_words(cycles, period, mv);
    let record = model.record(SourceE::Tone { cycles, mv }, &words, &[cycles], 3, 7);
    record.validate().unwrap();
    // Gain per DAC word: K Z/(RG + R104 + Z + R_iso) V/code codes/V (the 100 pF at DUT_LO is
    // ~1e-5 here).
    let gain =
        K * 30.0 / (100.0 + SOURCE_SERIES_OHM + 30.0 + 22.0) * SOURCE_V_PER_CODE * CODES_PER_VOLT;
    // Rounding (0.5 code) plus the 5.8e-6 rad phase of the 100 pF at DUT_LO on the tone peak.
    let peak = gain * f64::from(SOURCE_LIMIT_CODE) * 400.0 / 1700.0;
    for bin in 0..period as usize {
        let want = gain * f64::from(words[(bin + period as usize - 5) % period as usize]);
        let got = record.sums[bin][0] as f64 / 7.0;
        assert!(
            (got - want).abs() < 0.6 + 1e-5 * peak,
            "bin {bin}: {got} vs {want}"
        );
        assert_eq!(
            record.sums[bin][0] % 7,
            0,
            "noise-free sums are 7 x one code"
        );
    }
    // Headers are the single-sample extremes of what was summed.
    let codes_a: Vec<i64> = record.sums.iter().map(|s| s[0] / 7).collect();
    assert_eq!(i64::from(record.min[0]), *codes_a.iter().min().unwrap());
    assert_eq!(i64::from(record.max[0]), *codes_a.iter().max().unwrap());
    assert_eq!(record.payload().len(), data_payload_len(375));
    assert_eq!(crc32(&record.payload()), record.transport_crc32);
    // The same stream seen as a RAW capture is the same samples frame for frame.
    let raw = decode_raw(&model.raw_payload(&words, 750), 750).unwrap().1;
    assert_eq!(raw[0][0], (record.sums[0][0] / 7) as i32);
    assert_eq!(raw[375][0], raw[0][0]);
}
#[test]
fn recovers_r_c_coil_and_tank_on_all_three_ranges() {
    type Case = (&'static str, u32, ZFn, f64);
    let cases: Vec<Case> = vec![
        ("10 ohm", 100, resistor(10.0), 1000.0),
        ("0.5 ohm", 100, resistor(0.5), 27_000.0),
        ("9 uF", 100, capacitor(9e-6), 1500.0),
        ("coil 0.5 ohm 100 uH", 100, coil(0.5, 100e-6), 27_000.0),
        (
            "tank off resonance",
            100,
            tank(0.1, 20e-6, 0.35e-6),
            27_000.0,
        ),
        ("700 ohm", 5000, resistor(700.0), 1000.0),
        ("100 nF", 5000, capacitor(100e-9), 10_000.0),
        ("coil 20 ohm 10 mH", 5000, coil(20.0, 10e-3), 3000.0),
        (
            "tank at resonance",
            5000,
            tank(0.1, 20e-6, 0.35e-6),
            60_000.0,
        ),
        ("20 kohm", 100_000, resistor(20_000.0), 1500.0),
        ("1 nF", 100_000, capacitor(1e-9), 5000.0),
        ("coil 100 ohm 100 mH", 100_000, coil(100.0, 0.1), 3000.0),
        ("tank 500 pF", 100_000, tank(50.0, 5e-3, 500e-12), 85_000.0),
    ];
    for (name, range, dut, hz) in cases {
        let model = Virtual::new(range, dut.clone());
        let mv = model.mv_for(hz);
        let record = model.tone_record(hz, mv, 0, default_periods(tone_for_hz(hz).unwrap().1));
        let measurements = analyze_e(&record, range).unwrap();
        assert_eq!(measurements.len(), 1);
        let m = &measurements[0];
        assert!(m.valid, "{name}: {:?}", m.issues);
        assert!(!m.voltage.clipped && !m.current.clipped, "{name}");
        // The nominal model is exact for the circuit it was derived from; what is left is
        // 24-bit quantisation of the smaller channel.
        assert_close(m.impedance_ohm, dut(hz), 5e-4, name);
        assert!((m.frequency_hz - hz).abs() < 1e-9);
        assert!(
            m.voltage.residual_ratio < 1e-3,
            "{name}: {}",
            m.voltage.residual_ratio
        );
    }
}
#[test]
fn measured_series_equivalents_have_the_right_signs() {
    let hz = 27_000.0;
    let model = Virtual::new(100, coil(0.5, 100e-6));
    let m = &analyze_e(&model.tone_record(hz, model.mv_for(hz), 0, 40), 100).unwrap()[0];
    assert!(
        (m.series_inductance_h.unwrap() - 100e-6).abs() < 1e-8 && m.series_capacitance_f.is_none()
    );
    assert!((m.series_resistance_ohm - 0.5).abs() < 0.01 && m.q.unwrap() > 20.0);
    let hz = 1500.0;
    let model = Virtual::new(100, capacitor(9e-6));
    let m = &analyze_e(&model.tone_record(hz, model.mv_for(hz), 0, 40), 100).unwrap()[0];
    assert!(
        (m.series_capacitance_f.unwrap() - 9e-6).abs() < 1e-8 && m.series_inductance_h.is_none()
    );
    assert!(m.phase_degrees < -89.0);
}
#[test]
fn the_dut_lo_capacitor_factor_matters_at_high_frequency() {
    // At 85 kHz on 100 kohm with a 1 nF DUT: without the (1 + j w C R_iso) factor the capacitance
    // would read about 0.06 % (w C0 R_iso = 0.0010) off and the series resistance would be wrong.
    let hz = 85_000.0;
    let model = Virtual::new(100_000, capacitor(1e-9));
    let record = model.tone_record(hz, model.mv_for(hz), 0, 40);
    let m = &analyze_e(&record, 100_000).unwrap()[0];
    let ratio = m.voltage.phasor_codes / m.current.phasor_codes;
    let without = temper_lcr::feedback(100_000, hz).unwrap() * ratio;
    let truth = capacitor(1e-9)(hz);
    // Ignoring the factor is wrong by w C0 R_iso = 1.2e-3; with it the error is quantisation only.
    assert!((without - truth).abs() / truth.abs() > 8e-4);
    assert_close(m.impedance_ohm, truth, 2e-4, "with the factor");
    let want = dut_lo_factor(hz);
    assert!((want.im - TAU * hz * 100e-12 * 22.0).abs() < 1e-18 && want.re == 1.0);
}
#[test]
fn averaging_noise_and_period_4096() {
    // Uniform noise of +-20000 codes per frame (about 1.2e4 rms) averages down over 12 periods
    // of a 4096-frame period: the line error is a few codes against a 2.5e6 signal.
    let mut model = Virtual::new(5000, resistor(700.0));
    model.noise_codes = 20_000.0;
    let hz = 187_500.0 * 21.0 / 4096.0;
    let record = model.tone_record(hz, model.mv_for(hz), 1, default_periods(4096));
    assert_eq!((record.period, record.periods), (4096, 12));
    let m = &analyze_e(&record, 5000).unwrap()[0];
    assert!(m.valid, "{:?}", m.issues);
    assert_close(m.impedance_ohm, cx(700.0, 0.0), 2e-3, "noisy");
    // The residual counts the noise outside the tone bin, not the tone.
    assert!(m.current.residual_rms_codes > 100.0 && m.current.residual_ratio < 0.01);
}
#[test]
fn clipping_is_reported_from_the_header_against_full_scale() {
    // RG in series keeps both channels below 30 % of full scale at the 1.7 V cap, so overload
    // comes from outside the tone: a large out-of-band signal on channel B.
    let mut model = Virtual::new(100, resistor(1.0));
    model.interferer = Some((1, 2.0 * f64::from(MAX_CODE)));
    let record = model.tone_record(1000.0, 1700, 0, 4);
    record.validate().unwrap();
    assert_eq!(record.min[1], MIN_CODE);
    assert_eq!(record.max[1], MAX_CODE);
    assert!(record.clipped(1) && !record.clipped(0));
    let m = &analyze_e(&record, 100).unwrap()[0];
    assert!(!m.valid && m.current.clipped && !m.voltage.clipped);
    assert!(
        m.issues
            .iter()
            .any(|i| i.starts_with("ADC clipping") && i.contains("B")),
        "{:?}",
        m.issues
    );
    assert!(m.current.max_code == MAX_CODE && m.current.min_code == MIN_CODE);
    // Just under the margin is not clipping; the 99.8 % threshold is 256 x 32700.
    let mut edge = record.clone();
    edge.min[1] = -(CLIP_CODE_E as i32) + 1;
    edge.max[1] = CLIP_CODE_E as i32 - 1;
    assert!(!edge.clipped(1));
    edge.max[1] = CLIP_CODE_E as i32;
    assert!(edge.clipped(1));
    // A clean tone on the right range is not flagged.
    let ok = Virtual::new(100, resistor(10.0));
    let clean = ok.tone_record(1000.0, ok.mv_for(1000.0), 0, 4);
    assert!(!clean.clipped(0) && !clean.clipped(1));
}
#[test]
fn residual_check_sees_energy_outside_the_tone_bin() {
    let hz = 27_000.0;
    let (cycles, period) = tone_for_hz(hz).unwrap();
    let quiet = Virtual::new(100, resistor(10.0));
    let mv = quiet.mv_for(hz);
    let tone_b = quiet.responses(hz).1.abs() * f64::from(mv) / 1000.0 * CODES_PER_VOLT;
    assert!(analyze_e(&quiet.tone_record(hz, mv, 0, 8), 100).unwrap()[0].valid);
    // 10 % of the tone, in another bin, on channel B only.
    let mut noisy = quiet.clone();
    noisy.interferer = Some((7, 0.1 * tone_b));
    let record = noisy.tone_record(hz, mv, 0, 8);
    let m = &analyze_e(&record, 100).unwrap()[0];
    assert!(
        !m.valid
            && m.issues
                .iter()
                .any(|i| i.contains("current signal too weak or distorted")),
        "{:?}",
        m.issues
    );
    assert!(
        (m.current.residual_ratio - 0.1).abs() < 0.01,
        "{}",
        m.current.residual_ratio
    );
    assert!(m.voltage.residual_ratio < 1e-3 && m.voltage.valid_signal());
    // The same energy 1 % of the tone passes (below the 5 % screening limit).
    noisy.interferer = Some((7, 0.01 * tone_b));
    assert!(analyze_e(&noisy.tone_record(hz, mv, 0, 8), 100).unwrap()[0].valid);
    // Requesting that bin as well makes it part of the signal: a two-bin record is clean.
    let mut two = quiet.clone();
    two.interferer = Some((7, 0.3 * tone_b));
    let mut record = two.tone_record(hz, mv, 0, 8);
    record.source = SourceE::Wave;
    record.bins = vec![cycles, 7];
    assert_eq!(record.period, period);
    let both = analyze_e(&record, 100).unwrap();
    assert!(both[0].current.residual_ratio < 1e-3);
    // And a weak tone is refused outright.
    let weak = quiet.tone_record(hz, 1, 0, 8);
    let m = &analyze_e(&weak, 100).unwrap()[0];
    assert!(
        !m.valid && m.issues.iter().any(|i| i.contains("too weak")),
        "{:?}",
        m.issues
    );
}
#[test]
fn multitone_waveform_analyses_every_requested_bin() {
    let period = 125usize;
    let bins = [3u32, 7, 11, 40];
    let amplitudes = [0.2, 0.15, 0.1, 0.05];
    let words: Vec<i32> = (0..period)
        .map(|n| {
            bins.iter()
                .zip(amplitudes)
                .enumerate()
                .map(|(i, (&b, a))| {
                    a * f64::from(SOURCE_LIMIT_CODE)
                        * (TAU * f64::from(b) * n as f64 / period as f64 + i as f64).sin()
                })
                .sum::<f64>()
                .round() as i32
        })
        .collect();
    check_wave(&words).unwrap();
    let dut = coil(2.0, 200e-6);
    let model = Virtual::new(100, dut.clone());
    let record = model.record(SourceE::Wave, &words, &bins, 4, 60);
    let measurements = analyze_e(&record, 100).unwrap();
    assert_eq!(measurements.len(), 4);
    for (m, &bin) in measurements.iter().zip(&bins) {
        let hz = FS * f64::from(bin) / period as f64;
        assert_eq!((m.cycles, m.period), (bin, 125));
        assert!((m.frequency_hz - hz).abs() < 1e-9);
        assert!(m.valid, "bin {bin}: {:?}", m.issues);
        assert_close(m.impedance_ohm, dut(hz), 2e-3, &format!("bin {bin}"));
        // All four tones are inside the analysed set: nothing is left over.
        assert!(m.voltage.residual_ratio < 1e-3);
    }
    // Leaving one out turns its energy into residual.
    let mut partial = record.clone();
    partial.bins = vec![3, 7, 11];
    assert!(analyze_e(&partial, 100).unwrap()[0].current.residual_ratio > 0.01);
    // A tone record analyses exactly its CYCLES bin; wave records may use any legal bins.
    let mut wrong = model.tone_record(1000.0, 400, 0, 4);
    wrong.bins = vec![3];
    assert!(wrong.validate().is_err());
    let mut high = record.clone();
    high.bins = vec![60];
    assert!(high.validate().is_err());
}
#[test]
fn record_validation_rejects_corruption() {
    let model = Virtual::new(100, resistor(10.0));
    let good = model.tone_record(1000.0, 400, 0, 4);
    good.validate().unwrap();
    let mut bad = good.clone();
    bad.sums[5][1] += 1;
    assert!(bad.validate().unwrap_err().contains("CRC"));
    let mut bad = good.clone();
    bad.sums[5][0] = i64::from(good.max[0]) * 4 + 4;
    bad.transport_crc32 = crc32(&bad.payload());
    assert!(bad.validate().unwrap_err().contains("inconsistent"));
    let mut bad = good.clone();
    bad.protocol = 2;
    assert!(bad.validate().unwrap_err().contains("protocol 2"));
    let mut bad = good.clone();
    bad.periods = 0;
    assert!(bad.validate().is_err());
    let mut bad = good.clone();
    bad.sums.pop();
    assert!(bad.validate().is_err());
    // No current at all is an error, not an infinity.
    let mut open = good.clone();
    open.sums.iter_mut().for_each(|s| s[1] = 0);
    open.min[1] = 0;
    open.max[1] = 0;
    open.transport_crc32 = crc32(&open.payload());
    assert!(analyze_e(&open, 100).unwrap_err().contains("no current"));
}

// ------------------------------------------------------------------ calibration
/// A fixture around the DUT: series lead (R, L) after a shunt capacitance, plus a gain error.
fn fixture(z: ZFn) -> ZFn {
    Arc::new(move |hz| {
        let w = TAU * hz;
        let shunted = inv(inv(z(hz) * cx(1.02, 0.0)) + cx(0.0, w * 30e-12));
        shunted + cx(0.2, w * 80e-9)
    })
}
fn sweep_of(range: u32, dut: ZFn, grid: &[f64]) -> SweepE {
    let model = Virtual::new(range, fixture(dut));
    SweepE {
        setup: setup_e(range),
        records: grid
            .iter()
            .map(|&hz| {
                let period = tone_for_hz(hz).unwrap().1;
                model.tone_record(hz, model.mv_for(hz), 0, default_periods(period) / 4)
            })
            .collect(),
    }
}
#[test]
fn three_standard_calibration_recovers_the_true_dut() {
    let grid = [1000.0, 27_000.0, 60_000.0];
    let short = sweep_of(100, resistor(1e-4), &grid);
    let a = sweep_of(100, resistor(20.0), &grid);
    let b = sweep_of(100, resistor(100.0), &grid);
    let cal = calibrate_e(&short, &a, 20.0, &b, 100.0).unwrap();
    assert_eq!(cal.points.len(), 3);
    assert_eq!(
        (cal.schema_version, cal.model.as_str()),
        (CALIBRATION_SCHEMA_VERSION_E, CALIBRATION_MODEL_E)
    );
    let truth = coil(0.8, 60e-6);
    let dut = sweep_of(100, truth.clone(), &grid);
    for r in &dut.records {
        let mut m = analyze_e(r, 100).unwrap().remove(0);
        let uncorrected = (m.impedance_ohm - truth(m.frequency_hz)).abs();
        correct_e(&mut m, &dut.setup, &cal).unwrap();
        assert!(m.calibrated);
        let error = (m.impedance_ohm - truth(m.frequency_hz)).abs();
        assert!(
            error < 2e-3 * truth(m.frequency_hz).abs(),
            "{} Hz: {error}",
            m.frequency_hz
        );
        assert!(
            error < uncorrected,
            "calibration must improve on the nominal model"
        );
    }
    // The same calibration serves any waveform at an exactly equal frequency: 8/25 and 16/50.
    let model = Virtual::new(100, fixture(truth.clone()));
    let other = model.record(
        SourceE::Tone {
            cycles: 16,
            mv: 300,
        },
        &tone_words(16, 50, 300),
        &[16],
        0,
        200,
    );
    let mut m = analyze_e(&other, 100).unwrap().remove(0);
    correct_e(&mut m, &dut.setup, &cal).unwrap();
    assert_close(
        m.impedance_ohm,
        truth(60_000.0),
        3e-3,
        "16/50 reuses the 8/25 point",
    );
    // A frequency with no point is refused, not interpolated.
    let lone = sweep_of(100, truth.clone(), &[10_500.0]);
    let mut m = analyze_e(&lone.records[0], 100).unwrap().remove(0);
    assert!(correct_e(&mut m, &lone.setup, &cal)
        .unwrap_err()
        .contains("no calibration"));
}
fn standard(s: StandardE) -> ZFn {
    Arc::new(move |hz| s.impedance(hz))
}
const KIT: &str = r#"{
  "schema": "temper-lcr-standards-1",
  "kit": "test kit",
  "temperature_c": 23.0,
  "standards": {
    "SHORT": {"r_ohm": 0.0002, "l_h": 5e-9},
    "R1": {"r_ohm": 20.003, "l_h": 2e-9, "c_f": 0.2e-12},
    "R3": {"r_ohm": 99.98, "l_h": 2e-9, "c_f": 0.2e-12}
  }
}"#;
#[test]
fn complex_fit_matches_the_real_fit_with_ideal_standards() {
    let (ms, m1, m2) = (cx(0.03, 0.01), cx(21.0, -0.4), cx(104.0, 2.0));
    let real = calibration_coefficients(ms, m1, 20.0, m2, 100.0).unwrap();
    let complex = calibration_coefficients_e([
        (ms, cx(0.0, 0.0)),
        (m1, cx(20.0, 0.0)),
        (m2, cx(100.0, 0.0)),
    ])
    .unwrap();
    for (r, c) in real.iter().zip(&complex) {
        assert_close(*c, *r, 1e-12, "coefficient");
    }
    // A non-zero short reads back as itself through its own calibration.
    let zs = cx(2e-4, 1.9e-3);
    let [a, b, c] =
        calibration_coefficients_e([(ms, zs), (m1, cx(20.0, 0.0)), (m2, cx(100.0, 0.0))]).unwrap();
    assert_close((ms - b) / (a - ms * c), zs, 1e-9, "short");
    // The short must be small, the loads distinct.
    assert!(calibration_coefficients_e([
        (ms, cx(5.0, 0.0)),
        (m1, cx(20.0, 0.0)),
        (m2, cx(100.0, 0.0))
    ])
    .is_err());
    assert!(
        calibration_coefficients_e([(ms, zs), (m1, cx(20.0, 0.0)), (m2, cx(21.0, 0.0))]).is_err()
    );
}
#[test]
fn characterized_standards_remove_their_own_parasitics() {
    // 100 ohm range: a short with 5 nH, loads with 2 nH; the DUT is a 50 mOhm, 100 nH coil.
    // 100 kOhm range: loads with 0.3 pF; the DUT is 1 MOhm with 0.5 pF.
    let cases: [(u32, StandardE, StandardE, StandardE, ZFn); 2] = [
        (
            100,
            StandardE {
                r_ohm: 2e-4,
                l_h: 5e-9,
                c_f: 0.0,
            },
            StandardE {
                r_ohm: 20.0,
                l_h: 2e-9,
                c_f: 0.2e-12,
            },
            StandardE {
                r_ohm: 100.0,
                l_h: 2e-9,
                c_f: 0.2e-12,
            },
            coil(0.05, 100e-9),
        ),
        (
            100_000,
            StandardE::resistor(1e-4),
            StandardE {
                r_ohm: 20e3,
                l_h: 2e-9,
                c_f: 0.3e-12,
            },
            StandardE {
                r_ohm: 100e3,
                l_h: 2e-9,
                c_f: 0.3e-12,
            },
            tank(1e6, 0.0, 0.5e-12),
        ),
    ];
    let grid = [60_000.0];
    for (range, s0, s1, s2, truth) in cases {
        let short = sweep_of(range, standard(s0), &grid);
        let a = sweep_of(range, standard(s1), &grid);
        let b = sweep_of(range, standard(s2), &grid);
        let known = calibrate_e_standards(&short, s0, &a, s1, &b, s2, Some("kit")).unwrap();
        let nominal = calibrate_e(&short, &a, s1.r_ohm, &b, s2.r_ohm).unwrap();
        assert_eq!(known.standards.as_ref().unwrap()["short"], s0);
        assert!(nominal.standards.is_none() && nominal.standards_kit.is_none());
        let dut = sweep_of(range, truth.clone(), &grid);
        let raw = analyze_e(&dut.records[0], range).unwrap().remove(0);
        let z = truth(raw.frequency_hz);
        let error = |cal: &CalibrationE| {
            let mut m = raw.clone();
            correct_e(&mut m, &dut.setup, cal).unwrap();
            (m.impedance_ohm - z).abs() / z.abs()
        };
        let (with, without) = (error(&known), error(&nominal));
        assert!(with < 1e-3, "range {range}: {with}");
        assert!(
            without > 10.0 * with && without > 5e-3,
            "range {range}: {without} vs {with}"
        );
    }
}
#[test]
fn standards_files_are_checked() {
    let kit = parse_standards_e(KIT).unwrap();
    assert_eq!(kit.get("R3").unwrap().r_ohm, 99.98);
    assert!(kit.get("R9").unwrap_err().contains("R1, R3, SHORT"));
    for (from, to) in [
        ("temper-lcr-standards-1", "temper-lcr-standards-0"),
        ("\"c_f\": 0.2e-12}\n  }", "\"c_f\": -1e-12}\n  }"),
        ("\"l_h\": 5e-9", "\"l_h\": 5.0"),
        ("\"l_h\": 5e-9", "\"l_h\": 5e-9, \"q\": 1"),
        ("\"r_ohm\": 0.0002", "\"r_ohm\": -0.0002"),
    ] {
        assert!(KIT.contains(from), "{from}");
        assert!(parse_standards_e(&KIT.replace(from, to)).is_err(), "{to}");
    }
    assert!(parse_standards_e(r#"{"schema": "temper-lcr-standards-1", "standards": {}}"#).is_err());
}
#[test]
fn calibration_refuses_mismatches_and_bad_standards() {
    let grid = [27_000.0];
    let short = sweep_of(100, resistor(1e-4), &grid);
    let a = sweep_of(100, resistor(20.0), &grid);
    let b = sweep_of(100, resistor(100.0), &grid);
    let cal = calibrate_e(&short, &a, 20.0, &b, 100.0).unwrap();
    let mut m = analyze_e(&a.records[0], 100).unwrap().remove(0);
    correct_e(&mut m, &a.setup, &cal).unwrap();
    // Setup, range, schema, model and feedback-network fields all have to match.
    let mut other = a.setup.clone();
    other.fixture = "different".into();
    assert!(correct_e(&mut m, &other, &cal).is_err());
    other = a.setup.clone();
    other.range_ohm = 5000;
    assert!(correct_e(&mut m, &other, &cal).is_err());
    other = a.setup.clone();
    other.revision = "D-riso22".into();
    assert!(correct_e(&mut m, &other, &cal).is_err());
    for edit in [
        |c: &mut CalibrationE| c.schema_version = 5,
        |c: &mut CalibrationE| {
            c.model = "bilinear-short-two-resistors-v5-riso22-local100p-boxcar".into()
        },
        |c: &mut CalibrationE| c.feedback_capacitance_pf = 22.0,
        |c: &mut CalibrationE| c.isolation_resistor_ohm = 0.0,
        |c: &mut CalibrationE| c.dut_lo_capacitance_pf = 0.0,
        |c: &mut CalibrationE| c.setup.revision = "D-riso22".into(),
    ] {
        let mut changed = cal.clone();
        edit(&mut changed);
        assert!(correct_e(&mut m, &a.setup, &changed).is_err());
    }
    // Standards must share the grid; a clipped or weak standard is refused.
    let off_grid = sweep_of(100, resistor(100.0), &[60_000.0]);
    assert!(calibrate_e(&short, &a, 20.0, &off_grid, 100.0).is_err());
    let mut model = Virtual::new(100, resistor(2.0));
    model.interferer = Some((1, 2.0 * f64::from(MAX_CODE)));
    let clipped = SweepE {
        setup: setup_e(100),
        records: vec![model.tone_record(27_000.0, 1700, 0, 4)],
    };
    assert!(calibrate_e(&short, &clipped, 20.0, &b, 100.0)
        .unwrap_err()
        .contains("clipping"));
    assert!(calibrate_e(&short, &a, 20.0, &b, 21.0).is_err()); // standards within 10 %
}

// ------------------------------------------------------------------ identity and cross-revision rejection
const INFO_E: &str = "INFO 3 E-codec e66052 120000000 187500 4096 100000 16 0 0 PASS";
const INFO_D: &str = "INFO 2 D-riso22 device 120000000 24000000 120 16384 PASS";
#[test]
fn identity_is_parsed_and_the_protocol_selected_from_info() {
    let fast =
        parse_info_e("INFO 3 E-codec u 108000000 375000 4096 100000 16 0 0 PASS").unwrap_err();
    assert!(fast.contains("375 kHz build"), "{fast}");
    let info = parse_info_e(INFO_E).unwrap();
    assert_eq!(
        (info.range_ohm, info.period, info.cycles, info.mv),
        (100_000, 16, 0, 0)
    );
    assert!(info.self_test_pass && info.unit_id == "e66052");
    let playing =
        parse_info_e("INFO 3 E-codec u 120000000 187500 4096 5000 375 2 1700 FAIL").unwrap();
    assert_eq!(
        (
            playing.range_ohm,
            playing.period,
            playing.cycles,
            playing.mv,
            playing.self_test_pass
        ),
        (5000, 375, 2, 1700, false)
    );
    assert_eq!(
        parse_info_e(&INFO_E.replace("100000 16", "0 16"))
            .unwrap()
            .range_ohm,
        0
    );
    for (what, line) in [
        ("clock", INFO_E.replace("120000000", "125000000")),
        ("fs", INFO_E.replace("187500", "192000")),
        ("max period", INFO_E.replace("4096", "8192")),
        ("period", INFO_E.replace("100000 16", "100000 8")),
        ("range", INFO_E.replace("100000 16", "7 16")),
        ("status", INFO_E.replace("PASS", "MAYBE")),
        ("short", INFO_E.replace(" PASS", "")),
        ("rev d identity", INFO_E.replace("E-codec", "D-riso22")),
        ("protocol 2", INFO_E.replace("INFO 3", "INFO 2")),
    ] {
        assert!(parse_info_e(&line).is_err(), "{what}");
    }
    assert_eq!(detect_protocol(INFO_E).unwrap(), Protocol::E);
    assert_eq!(detect_protocol(INFO_D).unwrap(), Protocol::D);
    // Mixed pairs are refused by name; older boards are left to the Rev D identity check.
    assert!(detect_protocol(&INFO_E.replace("INFO 3", "INFO 2"))
        .unwrap_err()
        .contains("protocol-3 board"));
    assert!(detect_protocol(&INFO_D.replace("INFO 2", "INFO 3"))
        .unwrap_err()
        .contains("E-codec"));
    assert_eq!(
        detect_protocol("INFO 1 D-riso22 device 120000000 24000000 120 32768 PASS").unwrap(),
        Protocol::D
    );
    // Rev D's own identity check still refuses the Rev E banner.
    assert!(SetupE::from_info(&info, 100, "fixture").is_ok());
    assert!(SetupE::from_info(&info, 7, "fixture").is_err());
    assert!(SetupE::from_info(&info, 100, "").is_err());
}
fn d_calibration() -> Calibration {
    Calibration {
        schema_version: 5,
        feedback_capacitance_pf: 100.0,
        isolation_resistor_ohm: 22.0,
        setup: Setup {
            revision: "D-riso22".into(),
            unit_id: "u".into(),
            fixture: "f".into(),
            range_ohm: 100,
            system_clock_hz: 120_000_000,
            dds_clock_hz: 24_000_000,
        },
        model: "bilinear-short-two-resistors-v5-riso22-local100p-boxcar".into(),
        standard1_ohm: 20.0,
        standard2_ohm: 100.0,
        points: vec![CalibrationPoint {
            tuning_word: 11185,
            decimation: 20,
            sample_count: 16384,
            a: cx(1.0, 0.0),
            b: cx(0.0, 0.0),
            c: cx(0.0, 0.0),
        }],
    }
}
fn e_files() -> (String, String) {
    let grid = [27_000.0];
    let short = sweep_of(100, resistor(1e-4), &grid);
    let a = sweep_of(100, resistor(20.0), &grid);
    let b = sweep_of(100, resistor(100.0), &grid);
    let cal = calibrate_e(&short, &a, 20.0, &b, 100.0).unwrap();
    (
        serde_json::to_string(&a).unwrap(),
        serde_json::to_string(&cal).unwrap(),
    )
}
#[test]
fn rev_d_and_rev_e_files_reject_each_other_by_name() {
    let (e_sweep, e_cal) = e_files();
    let d_cal = serde_json::to_string(&d_calibration()).unwrap();
    // Each revision's loader accepts its own files and names the other's.
    assert!(parse_sweep_e(&e_sweep).is_ok() && parse_calibration_e(&e_cal).is_ok());
    assert!(parse_calibration(&d_cal).is_ok());
    assert!(parse_calibration(&e_cal).unwrap_err().contains("Rev E"));
    assert!(parse_sweep(&e_sweep).unwrap_err().contains("Rev E"));
    assert!(parse_calibration_e(&d_cal)
        .unwrap_err()
        .contains("D-riso22"));
    let d_sweep = serde_json::json!({"setup": d_calibration().setup, "records": []}).to_string();
    assert!(parse_sweep_e(&d_sweep).unwrap_err().contains("D-riso22"));
    assert!(parse_sweep_e("{\"records\": []}").is_err());
    assert!(parse_calibration_e("{}").is_err());
    // Schema numbers are not a back door: a Rev E file relabelled as schema 5 is still refused.
    let mut relabelled: serde_json::Value = serde_json::from_str(&e_cal).unwrap();
    relabelled["schema_version"] = 5.into();
    assert!(parse_calibration(&relabelled.to_string()).is_err());
    assert!(parse_calibration_e(&relabelled.to_string())
        .unwrap_err()
        .contains("schema 5"));
    // And a Rev D calibration cannot be corrected into a Rev E measurement.
    let mut as_e: serde_json::Value = serde_json::from_str(&e_cal).unwrap();
    as_e["setup"]["revision"] = "D-riso22".into();
    assert!(parse_calibration_e(&as_e.to_string()).is_err());
    // Rev D capture setups reject the E identity as before.
    let mut setup = d_calibration().setup;
    setup.revision = "E-codec".into();
    assert!(setup.validate().is_err());
    assert!(setup_e(100).validate().is_ok());
    let mut bad = setup_e(100);
    bad.revision = "D-riso22".into();
    assert!(bad.validate().is_err());
}
fn run_cli(args: &[&str]) -> std::process::Output {
    std::process::Command::new(env!("CARGO_BIN_EXE_temper-lcr"))
        .args(args)
        .output()
        .unwrap()
}
fn stderr(output: &std::process::Output) -> String {
    String::from_utf8_lossy(&output.stderr).into_owned()
}
fn scratch(name: &str) -> std::path::PathBuf {
    let folder =
        std::env::temp_dir().join(format!("temper-lcr-rev-e-{name}-{}", std::process::id()));
    std::fs::create_dir_all(&folder).unwrap();
    folder
}
#[test]
fn cli_files_select_their_revision_and_refuse_cross_use() {
    let folder = scratch("files");
    let (e_sweep, e_cal) = e_files();
    let d_cal = serde_json::to_string(&d_calibration()).unwrap();
    let d_sweep = serde_json::to_string(&Sweep {
        setup: d_calibration().setup,
        records: vec![],
    })
    .unwrap();
    let path = |n: &str, text: &str| {
        let p = folder.join(n);
        std::fs::write(&p, text).unwrap();
        p.to_str().unwrap().to_owned()
    };
    let (es, ec, ds, dc) = (
        path("e.json", &e_sweep),
        path("ecal.json", &e_cal),
        path("d.json", &d_sweep),
        path("dcal.json", &d_cal),
    );
    // A Rev E capture analyses (uncalibrated and calibrated); the 20 ohm standard reads 20 ohm.
    for args in [vec!["analyze", &es], vec!["analyze", &es, &ec]] {
        let out = run_cli(&args);
        assert!(out.status.success(), "{}", stderr(&out));
        let values: Vec<MeasurementE> = serde_json::from_slice(&out.stdout).unwrap();
        assert_eq!(values.len(), 1);
        assert!(values[0].valid && (values[0].impedance_ohm.re - 20.0).abs() < 1.0);
    }
    let out = run_cli(&["validate", &es, &ec, "20", "0.5"]);
    assert!(
        out.status.success(),
        "{}{}",
        stderr(&out),
        String::from_utf8_lossy(&out.stdout)
    );
    // Cross-use in every direction fails with the revision named.
    let out_path = path("out.json", "");
    let cases: [(Vec<&str>, &str); 4] = [
        (vec!["analyze", &es, &dc], "D-riso22"),
        (vec!["analyze", &ds, &ec], "Rev E"),
        (vec!["validate", &es, &dc, "20", "1"], "D-riso22"),
        (
            vec!["calibrate", &es, &ds, "20", &es, "100", &out_path],
            "D-riso22",
        ),
    ];
    for (args, want) in cases {
        let out = run_cli(&args);
        assert!(!out.status.success(), "{args:?}");
        assert!(stderr(&out).contains(want), "{args:?}: {}", stderr(&out));
    }
    let out = run_cli(&["analyze", &es, "--allow-source-off-fail"]);
    assert!(!out.status.success() && stderr(&out).contains("Rev E"));
    // Rev E calibrate through the CLI writes a loadable file.
    let calibrated = folder.join("new-cal.json");
    let short = {
        let s = sweep_of(100, resistor(1e-4), &[27_000.0]);
        path("short.json", &serde_json::to_string(&s).unwrap())
    };
    let (a, b) = (
        path(
            "a.json",
            &serde_json::to_string(&sweep_of(100, resistor(20.0), &[27_000.0])).unwrap(),
        ),
        path(
            "b.json",
            &serde_json::to_string(&sweep_of(100, resistor(100.0), &[27_000.0])).unwrap(),
        ),
    );
    let out = run_cli(&[
        "calibrate",
        &short,
        &a,
        "20",
        &b,
        "100",
        calibrated.to_str().unwrap(),
    ]);
    assert!(out.status.success(), "{}", stderr(&out));
    parse_calibration_e(&std::fs::read_to_string(&calibrated).unwrap()).unwrap();
    // With a standards file, the loads are named and the short is SHORT; validate takes a name.
    let kit = parse_standards_e(KIT).unwrap();
    let sweep = |name: &str| {
        let s = sweep_of(100, standard(kit.get(name).unwrap()), &[27_000.0]);
        path(&format!("{name}.json"), &serde_json::to_string(&s).unwrap())
    };
    let (ks, k1, k3, kit_path) = (
        sweep("SHORT"),
        sweep("R1"),
        sweep("R3"),
        path("kit.json", KIT),
    );
    let standards = format!("--standards={kit_path}");
    let kit_cal = folder.join("kit-cal.json");
    let kit_cal = kit_cal.to_str().unwrap();
    let out = run_cli(&["calibrate", &ks, &k1, "R1", &k3, "R3", kit_cal, &standards]);
    assert!(out.status.success(), "{}", stderr(&out));
    let cal = parse_calibration_e(&std::fs::read_to_string(kit_cal).unwrap()).unwrap();
    assert_eq!(cal.standards.unwrap()["load2"], kit.get("R3").unwrap());
    assert!(cal.standards_kit.unwrap().starts_with("test kit"));
    let out = run_cli(&["validate", &k1, kit_cal, "R1", "0.05", &standards]);
    assert!(
        out.status.success(),
        "{}{}",
        stderr(&out),
        String::from_utf8_lossy(&out.stdout)
    );
    let refused: [(Vec<&str>, &str); 3] = [
        (
            vec!["calibrate", &ks, &k1, "R2", &k3, "R3", kit_cal, &standards],
            "R2 is not in kit",
        ),
        (
            vec!["validate", &k1, kit_cal, "20", "0.05", &standards],
            "20 is not in kit",
        ),
        (
            vec!["calibrate", &ds, &ds, "R1", &ds, "R3", kit_cal, &standards],
            "Rev E captures only",
        ),
    ];
    for (args, want) in refused {
        let out = run_cli(&args);
        assert!(
            !out.status.success() && stderr(&out).contains(want),
            "{args:?}: {}",
            stderr(&out)
        );
    }
    std::fs::remove_dir_all(folder).unwrap();
}

// ------------------------------------------------------------------ fake firmware on a pseudo-terminal
struct Fake {
    path: String,
    stop: Arc<AtomicBool>,
    _slave: File,
}
impl Drop for Fake {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
    }
}
/// What a firmware handler can do besides reading the command line.
struct Wire {
    master: File,
    stop: Arc<AtomicBool>,
}
impl Wire {
    fn byte(&mut self) -> Option<u8> {
        loop {
            if self.stop.load(Ordering::SeqCst) {
                return None;
            }
            let mut pfd = libc::pollfd {
                fd: self.master.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            // SAFETY: pfd is one initialised pollfd.
            let n = unsafe { libc::poll(&mut pfd, 1, 50) };
            if n > 0 {
                let mut b = [0u8];
                match self.master.read(&mut b) {
                    Ok(1) => return Some(b[0]),
                    Ok(_) => continue,
                    Err(_) => return None,
                }
            }
        }
    }
    fn line(&mut self) -> Option<String> {
        let mut bytes = Vec::new();
        loop {
            match self.byte()? {
                b'\n' => return Some(String::from_utf8_lossy(&bytes).into_owned()),
                b => bytes.push(b),
            }
        }
    }
    fn exact(&mut self, n: usize) -> Option<Vec<u8>> {
        (0..n).map(|_| self.byte()).collect()
    }
}
fn spawn_fake(mut handler: impl FnMut(&str, &mut Wire) -> Vec<u8> + Send + 'static) -> Fake {
    // SAFETY: plain libc pty calls; the fd is owned by the File below.
    let (master, path) = unsafe {
        let fd = libc::posix_openpt(libc::O_RDWR | libc::O_NOCTTY);
        assert!(fd >= 0);
        assert_eq!(libc::grantpt(fd), 0);
        assert_eq!(libc::unlockpt(fd), 0);
        let name = CStr::from_ptr(libc::ptsname(fd))
            .to_str()
            .unwrap()
            .to_owned();
        (File::from_raw_fd(fd), name)
    };
    // Holding the slave open keeps the line alive between the host's opens.
    let slave = OpenOptions::new()
        .read(true)
        .write(true)
        .custom_flags(libc::O_NOCTTY)
        .open(&path)
        .unwrap();
    let stop = Arc::new(AtomicBool::new(false));
    let mut wire = Wire {
        master,
        stop: stop.clone(),
    };
    std::thread::spawn(move || {
        while let Some(command) = wire.line() {
            let reply = handler(&command, &mut wire);
            if wire.master.write_all(&reply).is_err() {
                return;
            }
        }
    });
    Fake {
        path,
        stop,
        _slave: slave,
    }
}

struct EState {
    model: Virtual,
    words: Vec<i32>,
    cycles: u32,
    mv: u32,
    selftest: &'static str,
    commands: Vec<String>,
    /// Flip one payload bit after the CRC was computed.
    corrupt: bool,
    /// Drop the last payload byte.
    truncate: bool,
    capture_error: Option<&'static str>,
}
type Shared = Arc<Mutex<EState>>;
fn fake_e_state(model: Virtual) -> Shared {
    Arc::new(Mutex::new(EState {
        model,
        words: vec![0; 16],
        cycles: 0,
        mv: 0,
        selftest: "SELFTEST PASS",
        commands: Vec::new(),
        corrupt: false,
        truncate: false,
        capture_error: None,
    }))
}
fn sum_for(volts: f64, count: f64) -> u32 {
    (volts / 3.3 * 4096.0 * count).round() as u32
}
fn framed(tag: &str, a: usize, b: usize, mut payload: Vec<u8>, state: &EState) -> Vec<u8> {
    let crc = crc32(&payload);
    if state.corrupt {
        payload[20] ^= 0x10;
    }
    if state.truncate {
        payload.pop();
    }
    let mut out = format!("{tag} 3 {a} {b} {crc}\n").into_bytes();
    out.extend(payload);
    out.extend(b"\nEND\n");
    out
}
/// A Rev E firmware (protocol 3 as in firmware-rev-e/src/main.c) in front of the virtual instrument.
fn spawn_fake_e(state: Shared) -> Fake {
    spawn_fake(move |line, wire| {
        let mut st = state.lock().unwrap();
        st.commands.push(line.to_owned());
        let w: Vec<&str> = line.split_whitespace().collect();
        let n = |i: usize| w.get(i).and_then(|x| x.parse::<u32>().ok());
        let reply = |s: &str| format!("{s}\n").into_bytes();
        match (w[0], w.len()) {
            ("INFO", 1) => reply(&format!(
                "INFO 3 E-codec fake-e 120000000 187500 4096 {} {} {} {} PASS",
                st.model.range,
                st.words.len(),
                st.cycles,
                st.mv
            )),
            ("SELFTEST", 1) => reply(st.selftest),
            ("RANGE", 2) => match n(1) {
                Some(r @ (100 | 5000 | 100_000)) => {
                    st.model.range = r;
                    reply("OK")
                }
                _ => reply("ERR range"),
            },
            ("OFF", 1) => {
                st.words = vec![0; 16];
                st.cycles = 0;
                st.mv = 0;
                reply("OK")
            }
            ("RAILS", 1) => reply(&format!(
                "RAILS 256 {} {} {}",
                sum_for(12.0 / 11.0, 256.0),
                sum_for(2.34375, 256.0),
                sum_for(0.706, 256.0)
            )),
            ("CODEC", 1) => reply("CODEC 200 112 3 0 0"),
            ("REG", 2) => match n(1) {
                Some(r) if r <= 127 => reply(&format!("REG {r} {}", (r * 2 + 1) % 256)),
                _ => reply("ERR codec_bus"),
            },
            ("BOOT", 1) => reply("OK"),
            ("TONE", 4) => {
                let (c, p, mv) = (n(1).unwrap_or(0), n(2).unwrap_or(0), n(3).unwrap_or(0));
                match check_tone(c, p, mv) {
                    Err(e) if e.contains("period") => reply("ERR period"),
                    Err(e) if e.contains("frequency") => reply("ERR frequency"),
                    Err(_) => reply("ERR level"),
                    Ok(()) => {
                        st.words = tone_words(c, p, mv);
                        st.cycles = c;
                        st.mv = mv;
                        reply("OK")
                    }
                }
            }
            ("WAVE", 3) => {
                let (period, crc) = (n(1).unwrap_or(0) as usize, n(2).unwrap_or(0));
                if !(16..=4096).contains(&period) {
                    return reply("ERR period");
                }
                let Some(bytes) = wire.exact(4 * period) else {
                    return Vec::new();
                };
                if crc32(&bytes) != crc {
                    return reply("ERR crc");
                }
                let words: Vec<i32> = bytes
                    .chunks_exact(4)
                    .map(|c| i32::from_le_bytes([c[0], c[1], c[2], c[3]]))
                    .collect();
                if words.iter().any(|w| w.abs() > SOURCE_LIMIT_CODE) {
                    return reply("ERR level");
                }
                st.words = words;
                st.cycles = 0;
                st.mv = 0;
                reply("OK")
            }
            ("CAPTURE", 3) => {
                if let Some(e) = st.capture_error {
                    return reply(&format!("ERR {e}"));
                }
                let (skip, periods) = (n(1).unwrap_or(0), n(2).unwrap_or(0));
                let payload = st.model.data_payload(&st.words, skip, periods);
                framed("DATA", st.words.len(), periods as usize, payload, &st)
            }
            ("REFCAPTURE", 4) => {
                // K4 puts the 1 kOhm reference on the requested range; the previous range is
                // re-selected afterwards, so the model's range does not change.
                let (range, skip, periods) =
                    (n(1).unwrap_or(0), n(2).unwrap_or(0), n(3).unwrap_or(0));
                if ![100, 5000, 100_000].contains(&range) {
                    return reply("ERR range");
                }
                if let Some(e) = st.capture_error {
                    return reply(&format!("ERR {e}"));
                }
                let mut reference = st.model.clone();
                reference.range = range;
                reference.dut = resistor(REFERENCE_OHM);
                let payload = reference.data_payload(&st.words, skip, periods);
                framed("DATA", st.words.len(), periods as usize, payload, &st)
            }
            ("RAW", 2) => {
                let count = n(1).unwrap_or(0) as usize;
                let payload = st.model.raw_payload(&st.words, count);
                framed("RAW", count, 0, payload, &st)
            }
            _ => reply("ERR command"),
        }
    })
}
fn commands(state: &Shared) -> Vec<String> {
    state.lock().unwrap().commands.clone()
}

#[test]
fn client_speaks_every_protocol_3_command() {
    let state = fake_e_state(Virtual::new(100_000, resistor(50.0)));
    let fake = spawn_fake_e(state.clone());
    let Board::E(mut d) = Board::open(&fake.path, 100, "fixture-1").unwrap() else {
        panic!("INFO 3 E-codec must select Rev E");
    };
    assert_eq!(d.info.unit_id, "fake-e");
    assert_eq!((d.info.range_ohm, d.info.period), (100_000, 16));
    assert_eq!(
        d.setup,
        SetupE {
            unit_id: "fake-e".into(),
            ..setup_e(100)
        }
    );
    d.selftest().unwrap();
    d.range(5000).unwrap();
    assert_eq!(d.setup.range_ohm, 5000);
    assert!(d.range(7).is_err());
    let rails = d.rails().unwrap();
    assert!((rails.plus12_v - 12.0).abs() < 0.01 && (rails.minus12_v + 12.0).abs() < 0.01);
    assert_eq!(d.codec().unwrap().dev_sts1, 112);
    assert_eq!(d.reg(5).unwrap(), 11);
    assert!(d.reg(128).is_err());
    d.tone(2, 375, 300).unwrap();
    assert_eq!(d.period(), 375);
    let info = d.refresh_info().unwrap();
    assert_eq!(
        (info.range_ohm, info.period, info.cycles, info.mv),
        (5000, 375, 2, 300)
    );
    assert_eq!(d.tone_hz(27_000.0, 200).unwrap(), (18, 125));
    // Refused on the host before anything is sent.
    let sent = commands(&state).len();
    assert!(d.tone(2, 375, 1701).is_err() && d.tone(0, 375, 10).is_err());
    assert!(d.tone_hz(1000.5, 100).is_err() && d.tone_hz(90_000.0, 100).is_err());
    let mut over = vec![0; 16];
    over[3] = SOURCE_LIMIT_CODE + 1;
    assert!(d.wave(&over).is_err());
    assert_eq!(commands(&state).len(), sent);
    // WAVE upload and a capture with explicit SKIP and PERIODS.
    let words = tone_words(3, 125, 100);
    d.wave(&words).unwrap();
    assert_eq!(state.lock().unwrap().words, words);
    d.tone(8, 25, 300).unwrap();
    let (payload, crc) = d.capture(2, 6).unwrap();
    assert_eq!(payload.1.len(), 25);
    assert_eq!(crc32(&encode_data(payload.0, &payload.1)), crc);
    assert!(commands(&state).contains(&"CAPTURE 2 6".to_owned()));
    // RAW frames.
    let (header, frames) = d.raw(100).unwrap();
    assert_eq!(frames.len(), 100);
    assert_eq!(header[0], frames.iter().map(|f| f[0]).min().unwrap());
    assert!(d.raw(0).is_err() && d.raw(8193).is_err());
    d.off().unwrap();
    assert_eq!(d.period(), 16);
    d.boot().unwrap();
    let all = commands(&state);
    for expected in [
        "SELFTEST",
        "RANGE 5000",
        "RAILS",
        "CODEC",
        "REG 5",
        "TONE 2 375 300",
        "TONE 18 125 200",
        "TONE 8 25 300",
        "RAW 100",
        "OFF",
        "BOOT",
    ] {
        assert!(all.contains(&expected.to_owned()), "{expected} in {all:?}");
    }
    assert!(all.iter().any(|c| c.starts_with("WAVE 125 ")));
}
#[test]
fn reference_capture_measures_the_internal_1k_and_keeps_the_range() {
    // Defaults: RG = R_F in series keeps the current channel below the source level, so full
    // level on every range.
    for range in [100, 5000, 100_000] {
        assert_eq!(reference_default_mv(range).unwrap(), 1700);
    }
    assert!(reference_default_mv(7).is_err());
    let state = fake_e_state(Virtual::new(100, coil(0.5, 100e-6)));
    let fake = spawn_fake_e(state.clone());
    let Board::E(mut d) = Board::open(&fake.path, 100, "fixture-1").unwrap() else {
        panic!("Rev E expected");
    };
    for range in [100, 5000, 100_000] {
        let mv = reference_default_mv(range).unwrap();
        let record = d.reference_tone(range, 27_000.0, mv, None, None).unwrap();
        assert!(!record.clipped(0) && !record.clipped(1), "range {range}");
        let m = &analyze_e(&record, range).unwrap()[0];
        assert!(m.valid, "range {range}: {:?}", m.issues);
        assert_close(m.impedance_ohm, cx(REFERENCE_OHM, 0.0), 2e-3, "reference");
    }
    // The coil on the DUT terminals was never measured, and the range is unchanged.
    assert_eq!(d.refresh_info().unwrap().range_ohm, 100);
    assert_eq!(d.setup.range_ohm, 100);
    let sent = commands(&state);
    let skip = default_skip_periods(5000, 27_000.0, 125).unwrap();
    assert!(sent.contains(&format!("REFCAPTURE 5000 {skip} {}", default_periods(125))));
    assert!(!sent.iter().any(|c| c.starts_with("RANGE")));
    // A bad range is refused on the host; the firmware's ERR range is reported too.
    assert!(d.reference_capture(1000, 1, 1).is_err());
    assert_eq!(commands(&state).len(), sent.len());
    state.lock().unwrap().capture_error = Some("stream_sync");
    let err = d.reference_capture(100, 1, 1).unwrap_err();
    assert!(err.contains("stream_sync"), "{err}");
}
#[test]
fn cli_refcheck_reports_and_saves_the_reference() {
    let state = fake_e_state(Virtual::new(5000, resistor(10.0)));
    let fake = spawn_fake_e(state.clone());
    let folder = scratch("refcheck");
    let out_file = folder.join("reference.json");
    let out = run_cli(&[
        "refcheck",
        &fake.path,
        "5000",
        "1000,27000",
        out_file.to_str().unwrap(),
        "--skip=2",
        "--periods=40",
    ]);
    assert!(out.status.success(), "{}", stderr(&out));
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert_eq!(
        stdout.matches("|Z| 1000.").count() + stdout.matches("|Z| 999.").count(),
        2,
        "{stdout}"
    );
    let sent = commands(&state);
    for expected in [
        "SELFTEST",
        "TONE 2 375 1700",
        "REFCAPTURE 5000 2 40",
        "TONE 18 125 1700",
        "OFF",
    ] {
        assert!(
            sent.contains(&expected.to_owned()),
            "{expected} in {sent:?}"
        );
    }
    let sweep = parse_sweep_e(&std::fs::read_to_string(&out_file).unwrap()).unwrap();
    assert_eq!(sweep.setup.fixture, REFERENCE_FIXTURE);
    assert_eq!((sweep.setup.range_ohm, sweep.records.len()), (5000, 2));
    let analyzed = run_cli(&["analyze", out_file.to_str().unwrap()]);
    assert!(analyzed.status.success(), "{}", stderr(&analyzed));
    assert!(!run_cli(&["refcheck", &fake.path, "7", "1000", "x.json"])
        .status
        .success());
    std::fs::remove_dir_all(folder).unwrap();
}
#[test]
fn client_reports_device_errors_and_damaged_payloads() {
    let state = fake_e_state(Virtual::new(100, resistor(10.0)));
    let fake = spawn_fake_e(state.clone());
    let Board::E(mut d) = Board::open(&fake.path, 100, "fixture-1").unwrap() else {
        panic!("Rev E expected");
    };
    d.tone_hz(1000.0, 300).unwrap();
    state.lock().unwrap().capture_error = Some("stream_sync");
    assert!(d.capture(0, 2).unwrap_err().contains("stream_sync"));
    state.lock().unwrap().capture_error = None;
    state.lock().unwrap().corrupt = true;
    assert!(d.capture(0, 2).unwrap_err().contains("CRC mismatch"));
    assert!(d.raw(50).unwrap_err().contains("CRC mismatch"));
    state.lock().unwrap().corrupt = false;
    state.lock().unwrap().selftest = "SELFTEST FAIL loopback";
    assert!(d.selftest().unwrap_err().contains("loopback"));
    // A payload one byte short stalls the read: the terminator check or the deadline fails it.
    // (Not run: the client waits 10 s for the missing byte by design.)
    // The device's own limits come back as errors, not panics: a capture longer than 60 s is
    // caught on the host first.
    assert!(d.capture(0, 40000).unwrap_err().contains("60 s"));
    // The client refuses a reply that does not match what it asked for.
    let mismatched = spawn_fake(|line, _| match line {
        l if l.starts_with("INFO") => {
            b"INFO 3 E-codec fake 120000000 187500 4096 100 16 0 0 PASS\n".to_vec()
        }
        l if l.starts_with("CAPTURE") => {
            let payload = encode_data([0, 0, 0, 0], &vec![[0, 0]; 16]);
            let mut out = format!("DATA 3 16 99 {}\n", crc32(&payload)).into_bytes();
            out.extend(payload);
            out.extend(b"\nEND\n");
            out
        }
        _ => b"ERR command\n".to_vec(),
    });
    let Board::E(mut d) = Board::open(&mismatched.path, 100, "f").unwrap() else {
        panic!("Rev E expected");
    };
    assert!(d.capture(0, 2).unwrap_err().contains("does not match"));
    // An ERR reply to a command is an error carrying the device's word.
    let refusing = spawn_fake(|line, _| match line {
        "INFO" => b"INFO 3 E-codec fake 120000000 187500 4096 100 16 0 0 PASS\n".to_vec(),
        _ => b"ERR stream_sync\n".to_vec(),
    });
    let Board::E(mut d) = Board::open(&refusing.path, 100, "f").unwrap() else {
        panic!("Rev E expected");
    };
    assert!(d.range(5000).unwrap_err().contains("stream_sync"));
    assert!(d.off().unwrap_err().contains("stream_sync"));
}
#[test]
fn board_selection_follows_info_and_refuses_cross_use() {
    // Rev D, protocol 2: Board::D, and Rev E commands are refused by the CLI.
    let d = spawn_fake(|line, _| match line {
        "INFO" => format!("{INFO_D}\n").into_bytes(),
        "OFF" => b"OK\n".to_vec(),
        _ => b"ERR command\n".to_vec(),
    });
    assert!(matches!(
        Board::open(&d.path, 100, "f").unwrap(),
        Board::D(_)
    ));
    for args in [
        vec!["range", &d.path, "100"],
        vec!["tone-hz", &d.path, "1000", "100"],
        vec!["codec", &d.path],
        vec!["raw", &d.path, "10", "/dev/null"],
    ] {
        let out = run_cli(&args);
        assert!(!out.status.success(), "{args:?}");
        assert!(stderr(&out).contains("Rev E"), "{args:?}: {}", stderr(&out));
    }
    // Rev D-only options are refused on the codec board by name, before any capture.
    let state = fake_e_state(Virtual::new(100, resistor(10.0)));
    let e = spawn_fake_e(state.clone());
    let capture = |extra: &str| {
        run_cli(&[
            "capture",
            &e.path,
            "100",
            "fixture-1",
            "1000",
            "/dev/null",
            extra,
        ])
    };
    for flag in ["--allow-hazard", "--no-source-off", "--short-standard"] {
        let out = capture(flag);
        assert!(
            !out.status.success() && stderr(&out).contains("Rev D options"),
            "{}",
            stderr(&out)
        );
    }
    let out = run_cli(&["noise", &e.path, "100", "fixture-1", "1000", "/dev/null"]);
    assert!(
        !out.status.success() && stderr(&out).contains("Rev D command"),
        "{}",
        stderr(&out)
    );
    assert!(!commands(&state)
        .iter()
        .any(|c| c.starts_with("CAPTURE") || c.starts_with("TONE")));
    // Rev E options on a Rev D board.
    let out = run_cli(&[
        "capture",
        &d.path,
        "100",
        "fixture-1",
        "1500",
        "/dev/null",
        "--skip=3",
    ]);
    assert!(
        !out.status.success() && stderr(&out).contains("Rev E options"),
        "{}",
        stderr(&out)
    );
    // Rev D's own client refuses a Rev E board by name, and the INFO of a Rev E board with a
    // Rev D identity is refused.
    let err = temper_lcr::transport::Device::open(&e.path, 100, "f")
        .err()
        .unwrap();
    assert!(err.contains("Rev E"), "{err}");
    let mixed =
        spawn_fake(|_, _| format!("{}\n", INFO_E.replace("E-codec", "D-riso22")).into_bytes());
    assert!(Board::open(&mixed.path, 100, "f")
        .err()
        .unwrap()
        .contains("E-codec"));
}
#[test]
fn cli_captures_and_analyses_a_codec_board_end_to_end() {
    let dut = coil(0.5, 100e-6);
    let state = fake_e_state(Virtual::new(100_000, dut.clone()));
    let fake = spawn_fake_e(state.clone());
    let folder = scratch("e2e");
    let out_file = folder.join("capture.json");
    let out_path = out_file.to_str().unwrap();
    // Range 100 ohm, two exact frequencies, explicit level and lengths.
    let out = run_cli(&[
        "capture",
        &fake.path,
        "100",
        "fixture-1",
        "27000,60000",
        out_path,
        "--mv=200",
        "--skip=2",
        "--periods=40",
    ]);
    assert!(out.status.success(), "{}", stderr(&out));
    let sent = commands(&state);
    for expected in [
        "RANGE 100",
        "TONE 18 125 200",
        "TONE 8 25 200",
        "CAPTURE 2 40",
        "OFF",
    ] {
        assert!(
            sent.contains(&expected.to_owned()),
            "{expected} in {sent:?}"
        );
    }
    let order: Vec<usize> = [
        "SELFTEST",
        "RAILS",
        "RANGE 100",
        "TONE 18 125 200",
        "CAPTURE 2 40",
        "TONE 8 25 200",
    ]
    .iter()
    .map(|c| sent.iter().position(|s| s == c).unwrap())
    .collect();
    assert!(order.windows(2).all(|w| w[0] < w[1]), "{sent:?}");
    let saved: SweepE = parse_sweep_e(&std::fs::read_to_string(&out_file).unwrap()).unwrap();
    assert_eq!(saved.setup.range_ohm, 100);
    assert_eq!(saved.records.len(), 2);
    assert!(saved.records.iter().all(|r| r.skip == 2 && r.periods == 40));
    let analysed = run_cli(&["analyze", out_path]);
    assert!(analysed.status.success(), "{}", stderr(&analysed));
    let values: Vec<MeasurementE> = serde_json::from_slice(&analysed.stdout).unwrap();
    assert_eq!(values.len(), 2);
    for m in &values {
        assert!(m.valid, "{:?}", m.issues);
        assert_close(m.impedance_ohm, dut(m.frequency_hz), 3e-3, "cli");
    }
    // Defaults: SKIP from the settling rule and about 0.25 s of whole periods, 1.7 V.
    let out = run_cli(&[
        "capture",
        &fake.path,
        "100",
        "fixture-1",
        "1500",
        out_path,
        "--mv=100",
    ]);
    assert!(out.status.success(), "{}", stderr(&out));
    let skip = default_skip_periods(100, 1500.0, 125).unwrap();
    assert!(commands(&state).contains(&format!("CAPTURE {skip} {}", default_periods(125))));
    // Inexact and too-fast frequencies are refused before the instrument is touched.
    let before = commands(&state).len();
    for bad in ["1000.5", "90000"] {
        let out = run_cli(&["capture", &fake.path, "100", "fixture-1", bad, out_path]);
        assert!(
            !out.status.success() && stderr(&out).contains("Hz"),
            "{bad}: {}",
            stderr(&out)
        );
    }
    assert!(
        commands(&state)[before..]
            .iter()
            .all(|c| c == "INFO" || c == "OFF"),
        "{:?}",
        &commands(&state)[before..]
    );
    // Multitone through an uploaded waveform.
    let words: Vec<i32> = (0..125)
        .map(|n| {
            (0.2 * f64::from(SOURCE_LIMIT_CODE) * (TAU * 3.0 * f64::from(n) / 125.0).sin()
                + 0.1
                    * f64::from(SOURCE_LIMIT_CODE)
                    * (TAU * 11.0 * f64::from(n) / 125.0).sin()
                    * 0.1)
                .round() as i32
        })
        .collect();
    let wave_file = folder.join("wave.txt");
    std::fs::write(
        &wave_file,
        words.iter().map(|w| format!("{w}\n")).collect::<String>(),
    )
    .unwrap();
    let multi = folder.join("multi.json");
    let out = run_cli(&[
        "capture-wave",
        &fake.path,
        "100",
        "fixture-1",
        wave_file.to_str().unwrap(),
        "3,11",
        multi.to_str().unwrap(),
        "--skip=1",
        "--periods=20",
    ]);
    assert!(out.status.success(), "{}", stderr(&out));
    assert!(commands(&state).iter().any(|c| c.starts_with("WAVE 125 ")));
    let analysed = run_cli(&["analyze", multi.to_str().unwrap()]);
    let values: Vec<MeasurementE> = serde_json::from_slice(&analysed.stdout).unwrap();
    assert_eq!(
        values.iter().map(|m| m.cycles).collect::<Vec<_>>(),
        vec![3, 11]
    );
    assert_close(values[0].impedance_ohm, dut(4500.0), 5e-3, "bin 3");
    // Diagnostics: info, range, tone-hz, codec, reg, raw.
    let info = run_cli(&["info", &fake.path]);
    assert!(info.status.success(), "{}", stderr(&info));
    assert!(String::from_utf8_lossy(&info.stdout).contains("E-codec"));
    assert!(run_cli(&["range", &fake.path, "5000"]).status.success());
    assert!(run_cli(&["tone-hz", &fake.path, "1000", "50"])
        .status
        .success());
    assert!(commands(&state).contains(&"TONE 2 375 50".to_owned()));
    assert!(run_cli(&["codec", &fake.path]).status.success());
    let reg = run_cli(&["reg", &fake.path, "9"]);
    assert!(String::from_utf8_lossy(&reg.stdout).contains("REG 9 = 19"));
    let raw_file = folder.join("raw.json");
    let raw = run_cli(&["raw", &fake.path, "200", raw_file.to_str().unwrap()]);
    assert!(raw.status.success(), "{}", stderr(&raw));
    let saved: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(&raw_file).unwrap()).unwrap();
    assert_eq!(saved["frames"].as_array().unwrap().len(), 200);
    std::fs::remove_dir_all(folder).unwrap();
}

/// The host constants are the firmware's: parsed from firmware-rev-e's headers and main.c.
#[test]
fn firmware_host_contract_rev_e() {
    let wave = include_str!("../../firmware-rev-e/src/wave.h");
    let pins = include_str!("../../firmware-rev-e/src/pins.h");
    let syncavg = include_str!("../../firmware-rev-e/src/syncavg.h");
    let main = include_str!("../../firmware-rev-e/src/main.c");
    let constant = |source: &str, name: &str| -> i64 {
        source
            .lines()
            .find_map(|line| {
                let parts: Vec<_> = line.split_whitespace().collect();
                (parts.len() >= 3 && parts[0] == "#define" && parts[1] == name)
                    .then(|| parts[2].trim_end_matches('u').parse().unwrap())
            })
            .unwrap_or_else(|| panic!("{name} not found"))
    };
    let revision = pins
        .lines()
        .find_map(|line| line.strip_prefix("#define HARDWARE_REVISION "))
        .unwrap()
        .trim_matches('"');
    assert_eq!(revision, HARDWARE_REVISION_E);
    assert_eq!(constant(wave, "FS_HZ"), i64::from(SAMPLE_RATE_HZ));
    assert_eq!(constant(wave, "WAVE_MIN_PERIOD"), i64::from(MIN_PERIOD));
    assert_eq!(constant(wave, "WAVE_MAX_PERIOD"), i64::from(MAX_PERIOD));
    assert_eq!(constant(wave, "SOURCE_LIMIT_MV"), i64::from(TONE_MAX_MV));
    assert_eq!(
        constant(wave, "SOURCE_LIMIT_CODE"),
        i64::from(SOURCE_LIMIT_CODE)
    );
    assert_eq!(constant(wave, "TONE_MAX_HZ"), i64::from(TONE_MAX_HZ));
    assert_eq!(
        constant(pins, "SYSTEM_CLOCK_HZ"),
        i64::from(SYSTEM_CLOCK_HZ_E)
    );
    assert_eq!(
        constant(pins, "SYSTEM_CLOCK_HZ")
            / constant(pins, "BCLK_CYCLES")
            / constant(pins, "FRAME_BCLKS"),
        i64::from(SAMPLE_RATE_HZ)
    );
    // 24-bit samples in 32-bit words: the firmware shifts by 8.
    assert_eq!(constant(syncavg, "SYNCAVG_SHIFT"), 8);
    assert_eq!(ADC_FULL_SCALE_CODE, 1 << 23);
    // Wire tags, protocol number and limits as printed by main.c.
    assert!(main.contains(&format!("printf(\"INFO {PROTOCOL_VERSION_E} %s")));
    assert!(main.contains(&format!("\"%s {PROTOCOL_VERSION_E} %\" PRIu32")));
    assert!(main.contains("#define RAW_MAX_FRAMES 8192u") && RAW_MAX_FRAMES == 8192);
    assert!(main.contains("60u * (uint64_t)FS_HZ") && MAX_CAPTURE_SECONDS == 60);
    assert!(main.contains("(j + skip - 5) mod period") && FRAME_OFFSET == 5);
    for command in ["INFO", "OFF", "RAILS", "CODEC", "BOOT", "SELFTEST"] {
        assert!(
            main.contains(&format!("strcmp(line, \"{command}\")")),
            "{command}"
        );
    }
    for format in [
        "\"RANGE %",
        "\"TONE %",
        "\"WAVE %",
        "\"CAPTURE %",
        "\"RAW %",
        "\"REG %",
    ] {
        assert!(main.contains(format), "{format}");
    }
    // The firmware's range set and its error replies.
    assert!(main.contains("a != 100u && a != 5000u && a != 100000u"));
    // REFCAPTURE and the K4 driver on GPIO14 (RP2040 pin 17; GPIO12 has no escape).
    assert!(main.contains("\"REFCAPTURE %"));
    assert_eq!(constant(pins, "PIN_RNG_SET_REF"), 14);
    // The firmware's 375 kHz build, which this host refuses by name.
    assert!(pins.contains(&format!("#define SYSTEM_CLOCK_HZ {SYSTEM_CLOCK_375K_HZ}u")));
    assert!(wave.contains(&format!("#define FS_HZ {SAMPLE_RATE_375K_HZ}u")));
    for reply in [
        "ERR period",
        "ERR frequency",
        "ERR level",
        "ERR crc",
        "ERR timeout",
        "ERR range",
    ] {
        assert!(main.contains(reply), "{reply}");
    }
}

#[test]
fn tone_plan_reports_the_defaults_without_a_device() {
    let plan = tone_plan(100, 27_000.0).unwrap();
    assert_eq!((plan.cycles, plan.period, plan.periods), (18, 125, 375));
    assert_eq!(
        plan.skip_periods,
        default_skip_periods(100, 27_000.0, 125).unwrap()
    );
    assert!((plan.capture_seconds - 0.25).abs() < 1e-12 && plan.frequency_hz == 27_000.0);
    assert!(tone_plan(100, 1000.5).is_err() && tone_plan(7, 1000.0).is_err());
    let out = run_cli(&["tone-plan", "5000", "1000,60000"]);
    assert!(out.status.success(), "{}", stderr(&out));
    let plans: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(plans[0]["cycles"], 2);
    assert_eq!(plans[0]["period"], 375);
    assert_eq!(plans[1]["period"], 25);
    assert!(!run_cli(&["tone-plan", "5000", "1000.5"]).status.success());
}

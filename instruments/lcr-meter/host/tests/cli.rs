use temper_lcr::*;
/// Raw PIO word for one simultaneous conversion: bits B15,A15,...,B0,A0.
fn packed(a: i16, b: i16) -> u32 {
    (0..16).fold(0, |v, i| {
        v | ((((a as u16 >> i) & 1) as u32) << (2 * i))
            | ((((b as u16 >> i) & 1) as u32) << (2 * i + 1))
    })
}
/// Test-side mirror of firmware/src/boxcar.c: deinterleave each packed word,
/// sum `decimation` consecutive conversions per channel, track extremes.
fn reference_boxcar(stream: &[u32], decimation: usize) -> Payload {
    assert_eq!(stream.len() % decimation, 0);
    let mut raw_min = [i16::MAX; 2];
    let mut raw_max = [i16::MIN; 2];
    let mut sums = Vec::new();
    let mut acc = [0i32; 2];
    for (i, &word) in stream.iter().enumerate() {
        let ab = decode_word(word);
        for channel in 0..2 {
            acc[channel] += i32::from(ab[channel]);
            raw_min[channel] = raw_min[channel].min(ab[channel]);
            raw_max[channel] = raw_max[channel].max(ab[channel]);
        }
        if (i + 1) % decimation == 0 {
            sums.push(acc);
            acc = [0; 2];
        }
    }
    (raw_min, raw_max, sums)
}
/// Builds a protocol-2 record exactly as firmware + transport would from
/// quantized 1 MSPS conversions.
fn record_from_conversions(conversions: &[[i16; 2]], decimation: u32, tuning_word: u32) -> Record {
    let stream: Vec<u32> = conversions.iter().map(|c| packed(c[0], c[1])).collect();
    let (raw_min, raw_max, sums) = reference_boxcar(&stream, decimation as usize);
    Record {
        protocol: PROTOCOL_VERSION,
        source_enabled: true,
        tuning_word,
        decimation,
        transport_crc32: crc32(&encode_payload(raw_min, raw_max, &sums)),
        raw_min,
        raw_max,
        sums,
    }
}
fn quantize(x: f64) -> i16 {
    x.round().clamp(-32768.0, 32767.0) as i16
}
/// Simulated 1 MSPS conversions of a, b, decimated as the firmware does.
fn simulated(hz: f64, decimation: u32, a: impl Fn(f64) -> f64, b: impl Fn(f64) -> f64) -> Record {
    let tuning_word = frequency_word(hz).unwrap();
    let conversions: Vec<[i16; 2]> = (0..DEFAULT_COUNT * decimation as usize)
        .map(|i| {
            let t = i as f64 / CONVERSION_RATE_HZ;
            [quantize(a(t)), quantize(b(t))]
        })
        .collect();
    record_from_conversions(&conversions, decimation, tuning_word)
}
fn synthetic(z: Complex, range: u32) -> Record {
    synthetic_at(z, range, 43721.0)
}
fn synthetic_at(z: Complex, range: u32, hz: f64) -> Record {
    let f = frequency_hz(frequency_word(hz).unwrap());
    // Independent circuit oracle: I/V = 1/R + jwC, not the production Zf helper.
    let cap = match range {
        100 => 100e-12,
        5000 => 100e-12,
        100000 => 100e-12,
        _ => panic!("unsupported test range"),
    };
    let a = z
        * Complex::new(1.0 / f64::from(range), std::f64::consts::TAU * f * cap)
        * Complex::new(8000.0, 0.0);
    let w = std::f64::consts::TAU * f;
    simulated(
        hz,
        decimation_for(hz),
        |t| 123.0 + a.re * (w * t).cos() - a.im * (w * t).sin(),
        |t| -213.0 + 8000.0 * (w * t).cos(),
    )
}
struct XorShift(u32);
impl XorShift {
    fn next(&mut self) -> u32 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 17;
        self.0 ^= self.0 << 5;
        self.0
    }
    /// Approximately uniform in [-1, 1).
    fn unit(&mut self) -> f64 {
        f64::from(self.next()) / 2_147_483_648.0 - 1.0
    }
}
#[test]
fn signed_wire_order_and_crc() {
    assert_eq!(decode_word(packed(-32768, 0x1234)), [-32768, 0x1234]);
    assert_eq!(decode_word(packed(-1, 0)), [-1, 0]);
    assert_eq!(crc32(b"123456789"), 0xcbf43926);
}
#[test]
fn payload_encoding_round_trip_and_length_checks() {
    let sums = vec![[-20 * 32768, 20 * 32767], [1, -1], [i32::MIN, i32::MAX]];
    let bytes = encode_payload([-32768, -5], [32767, 7], &sums);
    assert_eq!(bytes.len(), payload_len(3));
    // Header order: A min, A max, B min, B max, then A sum, B sum per sample.
    assert_eq!(
        &bytes[..8],
        &[0x00, 0x80, 0xff, 0x7f, 0xfb, 0xff, 0x07, 0x00]
    );
    assert_eq!(&bytes[8..12], &(-20 * 32768i32).to_le_bytes());
    let (raw_min, raw_max, decoded) = decode_payload(&bytes).unwrap();
    assert_eq!((raw_min, raw_max), ([-32768, -5], [32767, 7]));
    assert_eq!(decoded, sums);
    assert!(decode_payload(&bytes[..bytes.len() - 1]).is_err());
    assert!(decode_payload(&bytes[..7]).is_err());
    assert!(decode_payload(&bytes[..8]).unwrap().2.is_empty());
}
/// Same stream, decimation and CRC as firmware/test/test_boxcar.c: the C
/// firmware module and this reference produce the identical payload.
#[test]
fn golden_payload_matches_firmware_vector() {
    let mut rng = XorShift(0x1234_5678);
    let stream: Vec<u32> = (0..7 * 300).map(|_| rng.next()).collect();
    let (raw_min, raw_max, sums) = reference_boxcar(&stream, 7);
    assert_eq!(sums.len(), 300);
    assert_eq!(crc32(&encode_payload(raw_min, raw_max, &sums)), 0x2b37_8b6f);
}
#[test]
fn boxcar_reference_matches_direct_sums_for_every_decimation() {
    let mut rng = XorShift(0x2545_f491);
    for decimation in 1..=MAX_DECIMATION as usize {
        let conversions: Vec<[i16; 2]> = (0..decimation * 300)
            .map(|_| {
                let w = rng.next();
                [w as i16, (w >> 16) as i16]
            })
            .collect();
        let stream: Vec<u32> = conversions.iter().map(|c| packed(c[0], c[1])).collect();
        let (raw_min, raw_max, sums) = reference_boxcar(&stream, decimation);
        for (k, pair) in sums.iter().enumerate() {
            for channel in 0..2 {
                let direct: i32 = conversions[k * decimation..(k + 1) * decimation]
                    .iter()
                    .map(|c| i32::from(c[channel]))
                    .sum();
                assert_eq!(pair[channel], direct);
            }
        }
        for channel in 0..2 {
            assert_eq!(
                raw_min[channel],
                conversions.iter().map(|c| c[channel]).min().unwrap()
            );
            assert_eq!(
                raw_max[channel],
                conversions.iter().map(|c| c[channel]).max().unwrap()
            );
        }
    }
    // Full-scale sums of 20 conversions need 21 bits: int32 holds them exactly.
    let full = vec![packed(-32768, 32767); 20 * 256];
    let (_, _, sums) = reference_boxcar(&full, 20);
    assert!(sums.iter().all(|s| *s == [-655_360, 655_340]));
}
#[test]
fn boxcar_timebase_is_the_window_centre_and_gain_is_removed() {
    let f = frequency_hz(frequency_word(1000.0).unwrap());
    let w = std::f64::consts::TAU * f;
    assert_eq!(decimation_for(1000.0), 20);
    let r = simulated(
        1000.0,
        20,
        |t| 8000.0 * (w * t + 0.7).cos(),
        |t| 8000.0 * (w * t).cos(),
    );
    r.validate().unwrap();
    let a = fit_channel(&r, 0).unwrap();
    // Without the (N - 1)/2 centre offset the phase would be 2 pi f 9.5 us = 0.0597 rad off.
    assert!(
        (a.phasor_codes.im.atan2(a.phasor_codes.re) - 0.7).abs() < 2e-4,
        "{:?}",
        a.phasor_codes
    );
    assert!((a.phasor_codes.abs() - 8000.0).abs() < 0.5);
    assert!((a.boxcar_gain - boxcar_gain(f, 20)).abs() < 1e-15);
    assert!(a.boxcar_gain < 1.0 && a.boxcar_gain > 0.999);
    // Uniform-in-time centres: output k is the mean of conversions 20k..20k+19.
    assert!((output_time_s(0, 20) - 9.5e-6).abs() < 1e-18);
    assert!((output_time_s(3, 20) - 69.5e-6).abs() < 1e-18);
    assert_eq!(output_time_s(5, 1), 5e-6);
    assert_eq!(boxcar_gain(f, 1), 1.0);
    // The boxcar has nulls at multiples of the output rate.
    assert!(boxcar_gain(50_000.0, 20).abs() < 1e-12);
}
/// A 51 kHz interferer aliases exactly onto a 1 kHz measurement when every
/// 20th conversion is kept (50 kS/s undersampling, protocol 1). The boxcar sum
/// of the same 1 MSPS conversions attenuates it by |D(51 kHz)| = -34 dB, and
/// averages white noise down by sqrt(20).
#[test]
fn boxcar_suppresses_tone_that_undersampling_aliased() {
    let hz = 1000.0;
    let decimation = decimation_for(hz);
    assert_eq!(decimation, 20);
    let f = frequency_hz(frequency_word(hz).unwrap());
    let interferer = output_rate_hz(decimation) + f; // 50 kHz + f aliases onto f.
    let (w, wi) = (
        std::f64::consts::TAU * f,
        std::f64::consts::TAU * interferer,
    );
    let wanted = 8000.0;
    let spur = 4000.0;
    let r = simulated(
        hz,
        decimation,
        |t| wanted * (w * t).cos() + spur * (wi * t).cos(),
        |t| wanted * (w * t).cos(),
    );
    r.validate().unwrap();
    // Protocol-1 behaviour: one conversion per 20, timed at its own instant.
    let undersampled: Vec<f64> = (0..DEFAULT_COUNT)
        .map(|k| {
            let t = (k * decimation as usize) as f64 / CONVERSION_RATE_HZ;
            f64::from(quantize(wanted * (w * t).cos() + spur * (wi * t).cos()))
        })
        .collect();
    let legacy = legacy_fit(&undersampled, f, decimation);
    let legacy_error = (legacy - Complex::new(wanted, 0.0)).abs();
    let boxcar = fit_channel(&r, 0).unwrap().phasor_codes;
    let boxcar_error = (boxcar - Complex::new(wanted, 0.0)).abs();
    let predicted = spur * boxcar_gain(interferer, decimation).abs() / boxcar_gain(f, decimation);
    assert!(
        legacy_error > 0.99 * spur,
        "undersampled error {legacy_error}"
    );
    assert!(
        (boxcar_error - predicted).abs() < 0.05 * predicted,
        "boxcar error {boxcar_error}, predicted {predicted}"
    );
    let suppression_db = 20.0 * (boxcar_error / legacy_error).log10();
    assert!(suppression_db < -33.0, "suppression {suppression_db} dB");
    // The ratio measurement inherits the suppression: |A/B| error ~2% vs ~50%.
    let m = analyze(&r, 100).unwrap();
    let z_expected = feedback(100, f).unwrap();
    assert!((m.impedance_ohm - z_expected).abs() / z_expected.abs() < 0.025);

    // White noise: averaging 20 conversions cuts RMS by sqrt(20) (13 dB).
    let mut rng = XorShift(7);
    let noise: Vec<f64> = (0..DEFAULT_COUNT * decimation as usize)
        .map(|_| 400.0 * rng.unit())
        .collect();
    let tone = |t: f64| wanted * (w * t).cos();
    let conversions: Vec<[i16; 2]> = noise
        .iter()
        .enumerate()
        .map(|(i, n)| {
            let t = i as f64 / CONVERSION_RATE_HZ;
            [quantize(tone(t) + n), quantize(tone(t))]
        })
        .collect();
    let noisy = record_from_conversions(&conversions, decimation, frequency_word(hz).unwrap());
    let averaged = fit_channel(&noisy, 0).unwrap().residual_rms_codes;
    let picked: Vec<f64> = conversions
        .iter()
        .step_by(decimation as usize)
        .map(|c| f64::from(c[0]))
        .collect();
    let single = legacy_residual(&picked, f, decimation);
    let ratio = averaged / single;
    let expected = 1.0 / f64::from(decimation).sqrt();
    assert!(
        (ratio - expected).abs() < 0.1 * expected,
        "noise ratio {ratio}, expected {expected}"
    );
}
/// Protocol-1 fit: samples at k N / 1 MHz, no boxcar.
fn legacy_basis(k: usize, hz: f64, decimation: u32) -> [f64; 3] {
    let angle =
        std::f64::consts::TAU * hz * (k as f64 * f64::from(decimation)) / CONVERSION_RATE_HZ;
    [1.0, angle.cos(), angle.sin()]
}
fn legacy_solve(samples: &[f64], hz: f64, decimation: u32) -> [f64; 3] {
    let mut m = [[0.0; 4]; 3];
    for (k, &y) in samples.iter().enumerate() {
        let b = legacy_basis(k, hz, decimation);
        for row in 0..3 {
            for col in 0..3 {
                m[row][col] += b[row] * b[col];
            }
            m[row][3] += b[row] * y;
        }
    }
    // Gauss-Jordan without pivoting is adequate for this well-conditioned basis.
    for col in 0..3 {
        let d = m[col][col];
        for v in &mut m[col] {
            *v /= d;
        }
        for row in 0..3 {
            if row != col {
                let s = m[row][col];
                let pivot = m[col];
                for (v, p) in m[row].iter_mut().zip(pivot) {
                    *v -= s * p;
                }
            }
        }
    }
    [m[0][3], m[1][3], m[2][3]]
}
fn legacy_fit(samples: &[f64], hz: f64, decimation: u32) -> Complex {
    let [_, c, s] = legacy_solve(samples, hz, decimation);
    Complex::new(c, -s)
}
fn legacy_residual(samples: &[f64], hz: f64, decimation: u32) -> f64 {
    let x = legacy_solve(samples, hz, decimation);
    let sum: f64 = samples
        .iter()
        .enumerate()
        .map(|(k, &y)| {
            let b = legacy_basis(k, hz, decimation);
            (y - x[0] * b[0] - x[1] * b[1] - x[2] * b[2]).powi(2)
        })
        .sum();
    (sum / samples.len() as f64).sqrt()
}
#[test]
fn single_clipped_conversion_is_flagged_after_averaging() {
    let hz = 1000.0;
    let f = frequency_hz(frequency_word(hz).unwrap());
    let w = std::f64::consts::TAU * f;
    let tuning_word = frequency_word(hz).unwrap();
    let base: Vec<[i16; 2]> = (0..DEFAULT_COUNT * 20)
        .map(|i| {
            let t = i as f64 / CONVERSION_RATE_HZ;
            [
                quantize(3000.0 * (w * t).cos()),
                quantize(-2000.0 * (w * t).cos()),
            ]
        })
        .collect();
    let clean = record_from_conversions(&base, 20, tuning_word);
    let m = analyze(&clean, 100).unwrap();
    assert!(m.valid, "{:?}", m.issues);
    assert!(!m.voltage.clipped && !m.current.clipped);
    for (channel, code, clipped) in [
        (0, 32700, true),
        (0, 32699, false),
        (1, -32700, true),
        (1, -32768, true),
        (1, -32699, false),
    ] {
        let mut conversions = base.clone();
        conversions[123_457][channel] = code;
        let r = record_from_conversions(&conversions, 20, tuning_word);
        // The 20-conversion mean that contains it stays far below full scale.
        let mean = f64::from(r.sums[123_457 / 20][channel]) / 20.0;
        assert!(mean.abs() < 5000.0);
        assert_eq!(r.clipped(channel), clipped, "channel {channel} code {code}");
        let m = analyze(&r, 100).unwrap();
        assert_eq!(!m.valid, clipped);
        assert_eq!(m.issues.iter().any(|i| i == "ADC clipping"), clipped);
        let fitted = if channel == 0 { &m.voltage } else { &m.current };
        assert_eq!(fitted.clipped, clipped);
        assert_eq!(
            if code > 0 {
                fitted.raw_max_code
            } else {
                fitted.raw_min_code
            },
            code
        );
    }
}
#[test]
fn extremes_are_crc_covered_and_must_bound_the_sums() {
    let r = synthetic_at(Complex::new(5.0, -26.0), 100, 1000.0);
    r.validate().unwrap();
    // Hiding a clip without updating the CRC is a transport error.
    let mut hidden = r.clone();
    hidden.raw_max[0] = 100;
    assert!(hidden.validate().unwrap_err().contains("CRC"));
    // Even with a matching CRC, extremes must bound every N-conversion sum.
    hidden.transport_crc32 = crc32(&hidden.payload());
    assert!(hidden.validate().unwrap_err().contains("inconsistent"));
    let mut wrong_n = r.clone();
    wrong_n.decimation = 21;
    assert!(wrong_n.validate().is_err());
}
#[test]
fn noncoherent_capacitor_and_inductor() {
    for z in [Complex::new(5.0, -26.0), Complex::new(10.0, 30.0)] {
        let m = analyze(&synthetic(z, 100), 100).unwrap();
        assert!(m.valid);
        assert!((m.impedance_ohm - z).abs() < 0.002);
        assert_eq!(m.series_capacitance_f.is_some(), z.im < 0.0);
        assert_eq!(m.series_inductance_h.is_some(), z.im > 0.0);
    }
}
#[test]
fn parallel_feedback_capacitance() {
    let z = Complex::new(25000.0, -12000.0);
    let m = analyze(&synthetic(z, 100000), 100000).unwrap();
    assert!(m.valid);
    assert!((m.impedance_ohm - z).abs() < 1.0);
    let f = feedback(100000, 100000.0).unwrap();
    assert!((f.im.atan2(f.re).to_degrees() + 80.95693892).abs() < 1e-6);
    assert!((f.abs() - 15717.672548).abs() < 1e-6);
}
#[test]
fn every_compensated_range_uses_its_fitted_capacitor() {
    for (r, cap) in [(100, 100e-12), (5000, 100e-12), (100000, 100e-12)] {
        for hz in [1000.0, 35000.0, 60000.0, 100000.0] {
            let x = std::f64::consts::TAU * hz * f64::from(r) * cap;
            let expected = Complex::new(
                f64::from(r) / (1.0 + x * x),
                -f64::from(r) * x / (1.0 + x * x),
            );
            assert!((feedback(r, hz).unwrap() - expected).abs() < 1e-10);
            let z = Complex::new(f64::from(r) * 0.3, -f64::from(r) * 0.2);
            let m = analyze(&synthetic_at(z, r, hz), r).unwrap();
            assert!(m.valid);
            // At 100 kHz only ten distinct phases occur per cycle: quantization
            // repeats instead of averaging away. Bound two codes of phasor error
            // on each channel, including the current-channel denominator.
            let quantization_bound = (expected.abs() + z.abs()) * 2.0 / (8000.0 - 2.0);
            assert!(
                (m.impedance_ohm - z).abs() < quantization_bound,
                "range={r}, hz={hz}, normalized error={}",
                (m.impedance_ohm - z).abs() / f64::from(r)
            );
        }
        let z = Complex::new(f64::from(r) * 0.3, -f64::from(r) * 0.2);
        let m = analyze(&synthetic(z, r), r).unwrap();
        assert!(m.valid);
        assert!((m.impedance_ohm - z).abs() < f64::from(r) * 1e-5);
    }
}
#[test]
fn bilinear_fixture_recovers_complex_dut() {
    let a = Complex::new(1.08, 0.03);
    let b = Complex::new(0.4, 0.05);
    let c = Complex::new(0.0002, 0.0001);
    let one = Complex::new(1.0, 0.0);
    let forward = |z| (a * z + b) / (c * z + one);
    let got = calibration_coefficients(
        b,
        forward(Complex::new(20.0, 0.0)),
        20.0,
        forward(Complex::new(100.0, 0.0)),
        100.0,
    )
    .unwrap();
    for z in [Complex::new(7.0, -28.0), Complex::new(14.0, 22.0)] {
        let m = forward(z);
        let recovered = (m - got[1]) / (got[0] - m * got[2]);
        assert!((recovered - z).abs() < 1e-10);
    }
}
#[test]
fn corruption_and_weak_signal_rejected() {
    let mut r = synthetic(Complex::new(5.0, -26.0), 100);
    r.sums[50][0] ^= 1;
    assert!(analyze(&r, 100).is_err());
    let m = analyze(&synthetic(Complex::new(0.001, 0.0), 100), 100).unwrap();
    assert!(!m.valid);
    assert!(calibration_coefficients(
        Complex::default(),
        Complex::new(1.0, 0.0),
        100.0,
        Complex::new(2.0, 0.0),
        100.0
    )
    .is_err());
}
#[test]
fn noise_records_cannot_be_impedance() {
    let mut r = synthetic(Complex::new(5.0, -26.0), 100);
    assert!(noise(&r).is_err());
    r.source_enabled = false;
    assert!(analyze(&r, 100).is_err());
    let n = noise(&r).unwrap();
    // 43.7 kHz uses N = 2. The tone peak is input-referred; RMS describes the
    // 2-conversion averages, so the tone inside it carries the boxcar gain.
    assert_eq!(n.decimation, 2);
    assert!((n.tone_peak_codes[1] - 8000.0).abs() < 0.1);
    let gain = boxcar_gain(n.frequency_hz, 2);
    assert!(gain < 0.991);
    assert!((n.rms_codes[1] - 8000.0 * gain / 2.0f64.sqrt()).abs() < 2.0);
    assert_eq!(n.clipped, [false, false]);
    // At 1 kHz (N = 20) the input-referred tone amplitude is still recovered.
    let mut low = synthetic_at(Complex::new(5.0, -26.0), 100, 1000.0);
    low.source_enabled = false;
    let n = noise(&low).unwrap();
    assert_eq!(n.decimation, 20);
    assert!((n.tone_peak_codes[1] - 8000.0).abs() < 0.5);
}
#[test]
fn clock_and_frequency_bounds() {
    assert_eq!(frequency_word(100000.0).unwrap(), 1118481);
    assert!(frequency_word(f64::NAN).is_err());
    assert!(frequency_word(99.0).is_err());
    assert_eq!(decimation_for(100.0), 20);
    assert_eq!(decimation_for(1000.0), 20);
    assert_eq!(decimation_for(10000.0), 10);
    assert_eq!(decimation_for(35000.0), 2);
    assert_eq!(decimation_for(60000.0), 1);
    // Output rate and record length are unchanged from protocol 1.
    for hz in [100.0, 1000.0, 35000.0, 100000.0] {
        let rate = output_rate_hz(decimation_for(hz));
        assert!(rate / hz >= 10.0);
        assert!(DEFAULT_COUNT as f64 * hz / rate >= 10.0);
    }
}
fn setup() -> Setup {
    Setup {
        revision: HARDWARE_REVISION.into(),
        unit_id: "test-device".into(),
        fixture: "fixture-1".into(),
        range_ohm: 100,
        system_clock_hz: 120000000,
        dds_clock_hz: 24000000,
    }
}
#[test]
fn full_calibration_and_identity_checks() {
    let sweep = |z| Sweep {
        setup: setup(),
        records: vec![synthetic(z, 100)],
    };
    let s = sweep(Complex::new(0.2, 0.03));
    let a = sweep(Complex::new(20.6, 0.43));
    let b = sweep(Complex::new(102.2, 2.03));
    let cal = calibrate(&s, &a, 20.0, &b, 100.0).unwrap();
    let true_z = Complex::new(7.0, -26.0);
    let r = synthetic(
        Complex::new(1.02, 0.02) * true_z + Complex::new(0.2, 0.03),
        100,
    );
    let mut m = analyze(&r, 100).unwrap();
    correct(&mut m, &r, &setup(), &cal).unwrap();
    assert!(m.calibrated);
    assert!((m.impedance_ohm - true_z).abs() < 0.003);
    let mut wrong = setup();
    wrong.fixture = "different".into();
    assert!(correct(&mut m, &r, &wrong, &cal).is_err());
    wrong = setup();
    wrong.system_clock_hz = 125000000;
    assert!(wrong.validate().is_err());
    wrong = setup();
    wrong.revision = "B".into();
    assert!(wrong.validate().is_err());
    let mut old = cal.clone();
    old.setup.revision = "B".into();
    assert!(correct(&mut m, &r, &setup(), &old).is_err());
    old = cal.clone();
    old.model = "bilinear-short-two-resistors-v1".into();
    assert!(correct(&mut m, &r, &setup(), &old).is_err());
    // Even the old 100-ohm C range used 100 pF; identity and model must reject it.
    old = cal.clone();
    old.setup.revision = "C".into();
    assert!(correct(&mut m, &r, &setup(), &old).is_err());
    for schema in [2, 3] {
        old = cal.clone();
        old.schema_version = schema;
        assert!(correct(&mut m, &r, &setup(), &old).is_err());
    }
    for model in [
        "bilinear-short-two-resistors-v2",
        "bilinear-short-two-resistors-v3-local100p",
    ] {
        old = cal.clone();
        old.model = model.into();
        assert!(correct(&mut m, &r, &setup(), &old).is_err());
    }
    old = cal.clone();
    old.feedback_capacitance_pf = 0.0;
    assert!(correct(&mut m, &r, &setup(), &old).is_err());
    let mut old_json = serde_json::to_value(&cal).unwrap();
    old_json.as_object_mut().unwrap().remove("schema_version");
    old_json
        .as_object_mut()
        .unwrap()
        .remove("feedback_capacitance_pf");
    let old: Calibration = serde_json::from_value(old_json).unwrap();
    assert_eq!(old.schema_version, 0);
    assert!(correct(&mut m, &r, &setup(), &old).is_err());
    // A current calibration file round-trips through the checked loader.
    let text = serde_json::to_string(&cal).unwrap();
    assert_eq!(parse_calibration(&text).unwrap().points.len(), 1);
    // A different decimation at the same frequency has no calibration point.
    let mut other = r.clone();
    other.decimation = 2;
    other.sums.truncate(DEFAULT_COUNT / 2);
    assert!(correct(&mut m, &other, &setup(), &cal).is_err());
}
/// Protocol-1 capture files and schema-3 calibrations (both written by host
/// 0.4.0) fail with explicit messages rather than a serde field error.
#[test]
fn protocol_one_files_are_rejected_with_a_clear_error() {
    let v1_capture = serde_json::json!({
        "setup": setup(),
        "records": [{
            "source_enabled": true,
            "tuning_word": 11185,
            "sample_divider": 20,
            "packed_samples": vec![0u32; 256],
            "transport_crc32": 0
        }]
    })
    .to_string();
    let error = parse_sweep(&v1_capture).unwrap_err();
    assert!(error.contains("protocol 1"), "{error}");
    let mut v3 = serde_json::to_value(Sweep {
        setup: setup(),
        records: vec![synthetic(Complex::new(5.0, -26.0), 100)],
    })
    .unwrap();
    v3["records"][0]["protocol"] = 3.into();
    assert!(parse_sweep(&v3.to_string())
        .unwrap_err()
        .contains("unsupported"));
    v3["records"][0].as_object_mut().unwrap().remove("protocol");
    assert!(parse_sweep(&v3.to_string()).is_err());
    v3["records"][0]["protocol"] = 2.into();
    assert_eq!(parse_sweep(&v3.to_string()).unwrap().records.len(), 1);
    // In-memory records that skip the loader are still rejected by validate().
    let mut r = synthetic(Complex::new(5.0, -26.0), 100);
    r.protocol = 1;
    assert!(analyze(&r, 100).unwrap_err().contains("protocol"));

    let v1_calibration = serde_json::json!({
        "schema_version": 3,
        "feedback_capacitance_pf": 100.0,
        "setup": setup(),
        "model": "bilinear-short-two-resistors-v3-local100p",
        "standard1_ohm": 20.0,
        "standard2_ohm": 100.0,
        "points": [{"tuning_word": 11185, "sample_divider": 20, "sample_count": 16384,
                    "a": {"re": 1.0, "im": 0.0}, "b": {"re": 0.0, "im": 0.0},
                    "c": {"re": 0.0, "im": 0.0}}]
    })
    .to_string();
    let error = parse_calibration(&v1_calibration).unwrap_err();
    assert!(
        error.contains("schema 3") && error.contains("recalibrate"),
        "{error}"
    );
}
#[test]
fn cli_produces_correct_negative_reactance() {
    let folder = std::env::temp_dir().join(format!("temper-lcr-revc-test-{}", std::process::id()));
    std::fs::create_dir_all(&folder).unwrap();
    let file = folder.join("capture.json");
    let s = Sweep {
        setup: setup(),
        records: vec![synthetic(Complex::new(5.0, -26.0), 100)],
    };
    std::fs::write(&file, serde_json::to_vec(&s).unwrap()).unwrap();
    let output = std::process::Command::new(env!("CARGO_BIN_EXE_temper-lcr"))
        .arg("analyze")
        .arg(&file)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let values: Vec<Measurement> = serde_json::from_slice(&output.stdout).unwrap();
    assert!(values[0].impedance_ohm.im < 0.0);
    assert!(values[0].valid);
    // A protocol-1 file is refused by the CLI with the explicit message.
    let old = folder.join("old.json");
    let mut v1 = serde_json::to_value(&s).unwrap();
    let record = v1["records"][0].as_object_mut().unwrap();
    record.remove("protocol");
    record.insert("packed_samples".into(), serde_json::json!(vec![0u32; 4]));
    std::fs::write(&old, v1.to_string()).unwrap();
    let output = std::process::Command::new(env!("CARGO_BIN_EXE_temper-lcr"))
        .arg("analyze")
        .arg(&old)
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("protocol 1"));
    std::fs::remove_dir_all(folder).unwrap();
}
#[test]
fn firmware_host_clock_contract() {
    let pins = include_str!("../../firmware/src/pins.h");
    let boxcar = include_str!("../../firmware/src/boxcar.h");
    let main = include_str!("../../firmware/src/main.c");
    let revision = pins
        .lines()
        .find_map(|line| line.strip_prefix("#define HARDWARE_REVISION "))
        .unwrap()
        .trim_matches('"');
    assert_eq!(revision, HARDWARE_REVISION);
    let constant = |source: &str, name: &str| -> u32 {
        source
            .lines()
            .find_map(|line| {
                let parts: Vec<_> = line.split_whitespace().collect();
                (parts.len() >= 3 && parts[0] == "#define" && parts[1] == name)
                    .then(|| parts[2].trim_end_matches('u').parse().unwrap())
            })
            .unwrap()
    };
    assert_eq!(constant(pins, "SYSTEM_CLOCK_HZ"), setup().system_clock_hz);
    assert_eq!(f64::from(constant(pins, "DDS_CLOCK_HZ")), DDS_CLOCK_HZ);
    assert_eq!(
        constant(pins, "SYSTEM_CLOCK_HZ") / 5,
        constant(pins, "DDS_CLOCK_HZ")
    );
    assert_eq!(
        constant(pins, "SYSTEM_CLOCK_HZ") / constant(pins, "CAPTURE_CYCLES"),
        CONVERSION_RATE_HZ as u32
    );
    assert_eq!(constant(pins, "MAX_SAMPLES") as usize, MAX_COUNT);
    assert_eq!(constant(boxcar, "BOXCAR_MAX_DECIMATION"), MAX_DECIMATION);
    // Protocol number in INFO and DATA/NOISE headers; PIO clock never divided.
    assert!(main.contains(&format!("printf(\"INFO {PROTOCOL_VERSION} %s")));
    assert!(main.contains(&format!("printf(\"%s {PROTOCOL_VERSION} %")));
    assert!(main.contains("sm_config_set_clkdiv_int_frac(&config, 1, 0);"));
}

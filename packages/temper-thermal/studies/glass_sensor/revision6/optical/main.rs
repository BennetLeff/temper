//! Hypothetical nonreflecting optical-stack screen, not a product temperature prediction.
use std::{error::Error, f64::consts::PI, fs, io::Write};
fn planck(wavelength_m: f64, temperature_k: f64) -> f64 {
    const H: f64 = 6.62607015e-34;
    const C: f64 = 299792458.;
    const K: f64 = 1.380649e-23;
    let exponent = H * C / (wavelength_m * K * temperature_k);
    if exponent > 700. {
        return 0.;
    }
    2. * H * C * C / (wavelength_m.powi(5) * exponent.exp_m1())
}
fn band(t_c: f64, lo: f64, hi: f64, n: usize) -> f64 {
    let step = (hi - lo) / n as f64;
    (0..n)
        .map(|i| planck(lo + (i as f64 + 0.5) * step, t_c + 273.15) * step)
        .sum()
}
#[derive(Clone, Copy, Debug)]
struct State {
    pan: f64,
    glass: f64,
    filter: f64,
    can: f64,
    background: f64,
    emissivity: f64,
    glass_scale: f64,
}
impl Default for State {
    fn default() -> Self {
        Self {
            pan: 200.,
            glass: 80.,
            filter: 40.,
            can: 40.,
            background: 25.,
            emissivity: 0.6,
            glass_scale: 1.,
        }
    }
}
#[derive(Clone, Copy, Debug)]
enum Filter {
    None,
    Gray,
    Shaped,
}
impl Filter {
    fn name(self) -> &'static str {
        match self {
            Self::None => "none",
            Self::Gray => "gray_50pct",
            Self::Shaped => "synthetic_shaped",
        }
    }
    fn transmission(self, wavelength_m: f64) -> f64 {
        match self {
            Self::None => 1.,
            Self::Gray => 0.5,
            Self::Shaped => glass_transmission(wavelength_m, 1.),
        }
    }
}
// Deliberately invented spectrum. The real glass/coating has not been selected.
fn glass_transmission(w: f64, scale: f64) -> f64 {
    (scale * (0.75 - 0.30 * (w * 1e6 - 3.))).clamp(0., 1.)
}
fn signal(s: State, filter: Filter, n: usize) -> f64 {
    let dl = 2e-6 / n as f64;
    (0..n)
        .map(|i| {
            let w = 3e-6 + (i as f64 + 0.5) * dl;
            let tg = glass_transmission(w, s.glass_scale);
            let tf = filter.transmission(w);
            let pan = s.emissivity * planck(w, s.pan + 273.15)
                + (1. - s.emissivity) * planck(w, s.background + 273.15);
            let glass = tg * pan + (1. - tg) * planck(w, s.glass + 273.15);
            let incoming = tf * glass + (1. - tf) * planck(w, s.filter + 273.15);
            (incoming - planck(w, s.can + 273.15)) * dl
        })
        .sum()
}
fn invert(measured: f64, mut assumed: State, filter: Filter) -> Option<f64> {
    if !measured.is_finite() || assumed.emissivity <= 0. || assumed.glass_scale <= 0. {
        return None;
    }
    let (mut lo, mut hi) = (-20., 500.);
    assumed.pan = lo;
    let a = signal(assumed, filter, 400);
    assumed.pan = hi;
    let b = signal(assumed, filter, 400);
    if measured < a || measured > b {
        return None;
    }
    for _ in 0..55 {
        let mid = (lo + hi) / 2.;
        assumed.pan = mid;
        if signal(assumed, filter, 400) < measured {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    Some((lo + hi) / 2.)
}
fn main() -> Result<(), Box<dyn Error>> {
    fs::create_dir_all("results")?;
    let mut out = fs::File::create("results/sensitivity.csv")?;
    writeln!(out,"filter,case,pan_C,emissivity,glass_C,filter_C,glass_scale,signal_W_m2_sr,inferred_pan_C,error_C,status")?;
    for filter in [Filter::None, Filter::Gray, Filter::Shaped] {
        for pan in [50., 100., 200., 250.] {
            let base = State {
                pan,
                ..State::default()
            };
            let cases = [
                ("matched", base),
                (
                    "emissivity_low",
                    State {
                        emissivity: 0.3,
                        ..base
                    },
                ),
                (
                    "emissivity_high",
                    State {
                        emissivity: 0.9,
                        ..base
                    },
                ),
                (
                    "hot_glass",
                    State {
                        glass: 150.,
                        ..base
                    },
                ),
                (
                    "hot_filter",
                    State {
                        filter: 100.,
                        ..base
                    },
                ),
                (
                    "transmission_loss",
                    State {
                        glass_scale: 0.8,
                        ..base
                    },
                ),
                ("hot_can", State { can: 70., ..base }),
            ];
            for (name, actual) in cases {
                let reading = signal(actual, filter, 400);
                let estimate = invert(reading, base, filter);
                let (temperature, error, status) = match estimate {
                    Some(t) => (
                        format!("{t:.6}"),
                        format!("{:.6}", t - pan),
                        "HYPOTHETICAL_OPTICS",
                    ),
                    None => (String::new(), String::new(), "OUTSIDE_INVERSION_RANGE"),
                };
                writeln!(
                    out,
                    "{},{name},{pan},{},{},{},{},{reading:.9},{temperature},{error},{status}",
                    filter.name(),
                    actual.emissivity,
                    actual.glass,
                    actual.filter,
                    actual.glass_scale
                )?;
            }
        }
    }
    let mut noise = fs::File::create("results/radiance_sensitivity.csv")?;
    writeln!(noise,"filter,pan_C,band_radiance_W_m2_sr,dSignal_dT_W_m2_sr_K,offset_W_m2_sr,equivalent_temperature_K,status")?;
    for filter in [Filter::None, Filter::Gray, Filter::Shaped] {
        for pan in [25., 50., 100., 200., 250.] {
            let s = State {
                pan,
                ..State::default()
            };
            let slope = (signal(
                State {
                    pan: pan + 0.01,
                    ..s
                },
                filter,
                800,
            ) - signal(
                State {
                    pan: pan - 0.01,
                    ..s
                },
                filter,
                800,
            )) / 0.02;
            for offset in [0.001, 0.01, 0.1] {
                writeln!(
                    noise,
                    "{},{pan},{:.9},{slope:.9},{offset},{:.6},ASSUMED_OFFSET_NOT_DETECTOR_NETD",
                    filter.name(),
                    band(pan, 3e-6, 5e-6, 800),
                    offset / slope
                )?;
            }
        }
    }
    let mut views = fs::File::create("results/field_of_view.csv")?;
    writeln!(
        views,
        "full_angle_deg,distance_mm,footprint_diameter_mm,status"
    )?;
    for angle in [20_f64, 90.] {
        for distance in [5., 10., 20.] {
            writeln!(
                views,
                "{angle},{distance},{:.6},IDEAL_CONE_NO_GLASS_REFRACTION",
                2. * distance * (angle * PI / 360.).tan()
            )?;
        }
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn integrated_planck_matches_stefan_boltzmann() {
        let t = 500.;
        let n = 40000;
        let lo: f64 = 1e-8;
        let hi: f64 = 0.01;
        let dx = (hi / lo).ln() / n as f64;
        let radiance: f64 = (0..n)
            .map(|i| {
                let w = lo * ((i as f64 + 0.5) * dx).exp();
                planck(w, t) * w * dx
            })
            .sum();
        assert!((radiance * PI / (5.670374419e-8 * t.powi(4)) - 1.).abs() < 1e-6);
    }
    #[test]
    fn equal_temperatures_have_zero_net_flux() {
        let s = State {
            pan: 150.,
            glass: 150.,
            filter: 150.,
            can: 150.,
            background: 150.,
            ..State::default()
        };
        for f in [Filter::None, Filter::Gray, Filter::Shaped] {
            assert!(signal(s, f, 500).abs() < 1e-10);
        }
    }
    #[test]
    fn transparent_blackbody_matches_band_difference() {
        let s = State {
            emissivity: 1.,
            glass_scale: 100.,
            ..State::default()
        };
        assert!(
            (signal(s, Filter::None, 400)
                - (band(s.pan, 3e-6, 5e-6, 400) - band(s.can, 3e-6, 5e-6, 400)))
            .abs()
                < 1e-10
        );
    }
    #[test]
    fn opaque_glass_hides_pan() {
        let s = State {
            glass_scale: 0.,
            ..State::default()
        };
        assert!(
            (signal(s, Filter::Shaped, 400)
                - signal(State { pan: 450., ..s }, Filter::Shaped, 400))
            .abs()
                < 1e-12
        );
    }
    #[test]
    fn pan_signal_monotonic_and_quadrature_converges() {
        let s = State::default();
        assert!(
            signal(State { pan: 201., ..s }, Filter::Shaped, 400) > signal(s, Filter::Shaped, 400)
        );
        assert!(
            (signal(s, Filter::Shaped, 400) - signal(s, Filter::Shaped, 1600)).abs()
                / signal(s, Filter::Shaped, 1600).abs()
                < 1e-5
        );
    }
    #[test]
    fn inversion_recovers_known_parameters_but_rejects_outside_range() {
        for f in [Filter::None, Filter::Gray, Filter::Shaped] {
            let s = State::default();
            assert!((invert(signal(s, f, 400), s, f).unwrap() - s.pan).abs() < 1e-8);
            assert!(invert(1e9, s, f).is_none());
            assert!(invert(f64::NAN, s, f).is_none());
        }
    }
    #[test]
    fn unknown_emissivity_produces_large_error() {
        let assumed = State::default();
        let actual = State {
            emissivity: 0.3,
            ..assumed
        };
        assert!(
            invert(signal(actual, Filter::None, 400), assumed, Filter::None).unwrap()
                < assumed.pan - 10.
        );
    }
    #[test]
    fn gray_filter_halves_pan_sensitivity() {
        let s = State::default();
        let hotter = State { pan: 201., ..s };
        let plain = signal(hotter, Filter::None, 400) - signal(s, Filter::None, 400);
        let filtered = signal(hotter, Filter::Gray, 400) - signal(s, Filter::Gray, 400);
        assert!((filtered / plain - 0.5).abs() < 1e-10);
    }
}

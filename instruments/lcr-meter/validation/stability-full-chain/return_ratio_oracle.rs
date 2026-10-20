//! Independent bilateral return-ratio algebra, crossing and sampled-Nyquist oracle.
//! Does not edit or import the implementation under review (loop_matrix.rs).
use std::{
    f64::consts::{PI, TAU},
    fs,
    ops::{Add, Div, Mul, Sub},
    path::Path,
    process::Command,
};
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Complex {
    pub re: f64,
    pub im: f64,
}
impl Complex {
    pub const fn new(re: f64, im: f64) -> Self {
        Self { re, im }
    }
    pub fn abs(self) -> f64 {
        self.re.hypot(self.im)
    }
    pub fn arg(self) -> f64 {
        self.im.atan2(self.re)
    }
    pub fn conj(self) -> Self {
        Self::new(self.re, -self.im)
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
fn c(x: f64) -> Complex {
    Complex::new(x, 0.)
}
#[derive(Clone, Copy, Debug)]
pub struct Matrix2 {
    pub a: Complex,
    pub b: Complex,
    pub c: Complex,
    pub d: Complex,
}
impl Matrix2 {
    pub fn inverse(self) -> Result<Self, String> {
        let det = self.a * self.d - self.b * self.c;
        if !det.finite() || det.abs() == 0. {
            return Err("singular/nonfinite two-port".into());
        }
        Ok(Self {
            a: self.d / det,
            b: (c(0.) - self.b) / det,
            c: (c(0.) - self.c) / det,
            d: self.a / det,
        })
    }
    pub fn with_bridge(self, r: f64) -> Self {
        let g = c(1. / r);
        Self {
            a: self.a + g,
            b: self.b - g,
            c: self.c - g,
            d: self.d + g,
        }
    }
}
/// Currents enter both ports. Remove the bridge admittance from inverse measured Z.
pub fn deembedded_return(z: Matrix2, r: f64) -> Result<Complex, String> {
    if !r.is_finite() || r <= 0. {
        return Err("invalid bridge".into());
    }
    let mut y = z.inverse()?;
    let g = c(1. / r);
    y.a = y.a - g;
    y.d = y.d - g;
    y.b = y.b + g;
    y.c = y.c + g;
    let t = (y.b + y.c) / (y.a + y.d);
    if !t.finite() {
        return Err("nonfinite return ratio".into());
    }
    Ok(t)
}
/// Independently checked against inverse/de-embed, identical to the reviewed fast formula.
pub fn determinant_return(z: Matrix2, r: f64) -> Complex {
    let gd = c(2. / r) * (z.a * z.d - z.b * z.c);
    (gd - z.b - z.c) / (z.a + z.d - gd)
}
#[derive(Clone, Copy, Debug)]
pub struct Point {
    pub hz: f64,
    pub t: Complex,
}
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Direction {
    Up,
    Down,
}
#[derive(Clone, Copy, Debug)]
pub struct Crossing {
    pub hz: f64,
    pub direction: Direction,
    pub unwrapped_phase_deg: f64,
    pub principal_phase_deg: f64,
    pub signed_angle_from_minus_one_deg: f64,
}
pub fn wrap180(deg: f64) -> f64 {
    (deg + 180.).rem_euclid(360.) - 180.
}
/// Local angular separation is NOT a general phase-margin stability verdict.
pub fn crossings(p: &[Point]) -> Result<Vec<Crossing>, String> {
    if p.len() < 2 {
        return Err("too few points".into());
    }
    let mut prev = None;
    let mut v = Vec::new();
    for (i, x) in p.iter().enumerate() {
        if !x.hz.is_finite()
            || x.hz < 0.
            || !x.t.finite()
            || x.t.abs() == 0.
            || i > 0 && x.hz <= p[i - 1].hz
        {
            return Err("invalid frequency/return samples".into());
        }
        let raw = x.t.arg().to_degrees();
        let phase = if let Some(old) = prev {
            old + wrap180(raw - old)
        } else {
            raw
        };
        prev = Some(phase);
        v.push((x.hz, 20. * x.t.abs().log10(), phase));
    }
    let mut out = Vec::new();
    for w in v.windows(2) {
        let (a, b) = (w[0], w[1]);
        if (a.1 >= 0. && b.1 < 0.) || (a.1 < 0. && b.1 >= 0.) {
            let k = a.1 / (a.1 - b.1);
            let hz = if a.0 > 0. {
                (a.0.ln() + k * (b.0 / a.0).ln()).exp()
            } else {
                a.0 + k * (b.0 - a.0)
            };
            let phase = a.2 + k * (b.2 - a.2);
            out.push(Crossing {
                hz,
                direction: if b.1 > a.1 {
                    Direction::Up
                } else {
                    Direction::Down
                },
                unwrapped_phase_deg: phase,
                principal_phase_deg: wrap180(phase),
                signed_angle_from_minus_one_deg: wrap180(phase + 180.),
            });
        }
    }
    Ok(out)
}
#[derive(Clone, Debug)]
pub struct Nyquist {
    pub ccw_winding: i32,
    pub closed_rhp_poles: Option<i32>,
    pub minimum_sampled_return_difference: f64,
    pub maximum_segment_angle_deg: f64,
}
/// Sampled full conjugate Nyquist contour, omega -infinity to +infinity.
/// Assumes real coefficients, finite DC, strictly proper T, no imaginary-axis poles,
/// and no unobserved excursions between samples. P must be supplied independently.
/// This orientation gives W_ccw=P-Z, hence Z=P-W_ccw.
pub fn nyquist(p: &[Point], open_rhp_poles: Option<u32>) -> Result<Nyquist, String> {
    if p.len() < 3 || p[0].hz != 0. {
        return Err("need an explicit DC limit plus positive-frequency samples".into());
    }
    if p[0].t.im.abs() > 1e-10 * (1. + p[0].t.abs()) {
        return Err("DC limit must be real".into());
    }
    if p.last().unwrap().t.abs() > 0.01 {
        return Err("high-frequency limit not reached (|T|>0.01)".into());
    }
    for (i, x) in p.iter().enumerate() {
        if !x.t.finite() || !x.hz.is_finite() || i > 0 && x.hz <= p[i - 1].hz {
            return Err("invalid samples".into());
        }
    }
    let one = c(1.);
    let mut contour = vec![one];
    contour.extend(p.iter().skip(1).rev().map(|v| one + v.t.conj()));
    contour.extend(p.iter().map(|v| one + v.t));
    contour.push(one);
    let mut sum = 0.;
    let mut max_angle = 0f64;
    let mut min = f64::INFINITY;
    for w in contour.windows(2) {
        let (a, b) = (w[0], w[1]);
        min = min.min(a.abs()).min(b.abs());
        let u = b - a;
        let frac = if u.abs() == 0. {
            0.
        } else {
            (-(a.re * u.re + a.im * u.im) / (u.re * u.re + u.im * u.im)).clamp(0., 1.)
        };
        if (a + u * c(frac)).abs() < 1e-8 {
            return Err(
                "return-difference segment touches origin; refine/inspect marginal loop".into(),
            );
        }
        let angle = (a.conj() * b).arg();
        max_angle = max_angle.max(angle.abs());
        sum += angle;
    }
    if max_angle > PI / 2. {
        return Err("Nyquist segments too coarse; refine frequency samples".into());
    }
    let turns = sum / TAU;
    let winding = turns.round() as i32;
    if (turns - f64::from(winding)).abs() > 1e-6 {
        return Err("contour not closed numerically".into());
    }
    let closed = open_rhp_poles.map(|p| p as i32 - winding);
    if closed.is_some_and(|z| z < 0) {
        return Err("pole-count/orientation/coverage inconsistent (negative Z)".into());
    }
    Ok(Nyquist {
        ccw_winding: winding,
        closed_rhp_poles: closed,
        minimum_sampled_return_difference: min,
        maximum_segment_angle_deg: max_angle.to_degrees(),
    })
}
fn samples(f: impl Fn(Complex) -> Complex) -> Vec<Point> {
    let mut p = vec![Point {
        hz: 0.,
        t: f(c(0.)),
    }];
    for i in 0..=20000 {
        let w = 10f64.powf(-5. + i as f64 / 20000. * 11.);
        p.push(Point {
            hz: w / TAU,
            t: f(Complex::new(0., w)),
        });
    }
    p
}
fn notch(s: Complex, k: f64) -> Complex {
    c(k) * (s * s - c(0.2) * s + c(100.)) / ((s + c(1.)) * (s * s + c(20.) * s + c(100.)))
}
fn fixture_y(hz: f64) -> Matrix2 {
    let s = Complex::new(0., TAU * hz);
    Matrix2 {
        a: c(0.001) + s * c(1e-9),
        b: c(0.002),
        c: c(0.01) / (c(1.) + s * c(1e-5)),
        d: c(0.0005) + s * c(2e-9),
    }
}
fn read_data(p: &Path) -> Vec<Vec<f64>> {
    fs::read_to_string(p)
        .unwrap()
        .lines()
        .skip(1)
        .filter(|l| !l.trim().is_empty())
        .map(|l| {
            l.split_whitespace()
                .map(|v| {
                    let n: f64 = v.parse().unwrap();
                    assert!(n.is_finite());
                    n
                })
                .collect()
        })
        .collect()
}
fn main() {
    let dir = Path::new("return-ratio-oracle");
    fs::create_dir_all(dir).unwrap();
    let args: Vec<_> = std::env::args().collect();
    if args.get(1).is_some_and(|s| s == "--inspect") {
        let mut report = String::from("# Existing loop CSV inspection\n\nRead-only evaluation of existing return-ratio arrays. The real DC limit is estimated from the lowest-frequency real value. The high-frequency arc is approximated by F→1. Open-loop RHP pole count is UNKNOWN, so the winding below is conditional and no closed-loop stability verdict is issued. Refinement and limit/pole verification remain necessary.\n\n");
        for path in &args[2..] {
            let text = fs::read_to_string(path).unwrap();
            let mut points: Vec<Point> = text
                .lines()
                .skip(1)
                .map(|line| {
                    let v: Vec<f64> = line.split(',').map(|s| s.parse().unwrap()).collect();
                    Point {
                        hz: v[0],
                        t: Complex::new(v[1], v[2]),
                    }
                })
                .collect();
            assert!(
                points[0].t.im.abs() / points[0].t.abs() < 0.01,
                "DC extrapolation not adequate"
            );
            points.insert(
                0,
                Point {
                    hz: 0.,
                    t: c(points[0].t.re),
                },
            );
            let result = nyquist(&points, None);
            report += &format!("## {path}\n\nSampled winding result: {result:?}\n\n| Frequency MHz | Direction | Unwrapped phase | Principal phase | Signed local separation from −1 |\n|---:|---|---:|---:|---:|\n");
            for x in crossings(&points).unwrap() {
                report += &format!(
                    "| {:.6} | {:?} | {:.3}° | {:.3}° | {:.3}° |\n",
                    x.hz / 1e6,
                    x.direction,
                    x.unwrapped_phase_deg,
                    x.principal_phase_deg,
                    x.signed_angle_from_minus_one_deg
                );
            }
            let worst = points
                .windows(2)
                .max_by(|a, b| {
                    let angle =
                        |w: &[Point]| ((c(1.) + w[0].t).conj() * (c(1.) + w[1].t)).arg().abs();
                    angle(a).total_cmp(&angle(b))
                })
                .unwrap();
            let angle = ((c(1.) + worst[0].t).conj() * (c(1.) + worst[1].t))
                .arg()
                .abs()
                .to_degrees();
            report += &format!("\nLargest adjacent F=1+T phase step: {angle:.6}° between {:.9} and {:.9} MHz. Refine this band before accepting a winding.\n", worst[0].hz/1e6, worst[1].hz/1e6);
            report.push('\n');
        }
        fs::write(dir.join("case-inspection.md"), report).unwrap();
        println!("Read-only loop inspection saved; no P=0 assumption.");
        return;
    }
    let mut report=String::from("# Independent return-ratio oracle\n\nThe matrix inverse/de-embedding calculation is independent of the determinant expression under review. Fixture Y11=1/1000+s·1nF;Y22=1/2000+s·2nF;Y12=2mS;Y21=10mS/(1+s·10µs). Therefore T=(Y12+Y21)/(Y11+Y22). The fixture includes reverse transmission and actual port loading.\n\n| Bridge Ω | Samples | Max relative error vs analytic | Max disagreement with determinant shortcut |\n|---:|---:|---:|---:|\n");
    for r in [1., 10., 100., 1000.] {
        let name = format!("bridge{r}");
        let deck=format!("Independent bilateral bridge oracle\n.options reltol=1e-10 abstol=1e-14 vntol=1e-12\nR1 e 0 1k\nC1 e 0 1n\nR2 f 0 2k\nC2 f 0 2n\nEbuffer buf 0 e 0 1\nRfilter buf q 1k\nCfilter q 0 10n\nGforward f 0 q 0 0.01\nGreverse e 0 f 0 0.002\nRbridge e f {r}\nI1 0 e DC 0 AC 1\nI2 0 f DC 0 AC 0\n.control\nset klu\nset numdgt=17\nset wr_singlescale\nset wr_vecnames\nac dec 160 1 1G\nwrdata {name}_e.dat real(v(e)) imag(v(e)) real(v(f)) imag(v(f))\nalter I1 ac=0\nalter I2 ac=1\nac dec 160 1 1G\nwrdata {name}_f.dat real(v(e)) imag(v(e)) real(v(f)) imag(v(f))\nquit\n.endc\n.end\n");
        fs::write(dir.join(format!("{name}.cir")), deck).unwrap();
        let o = Command::new(std::env::var("NGSPICE").unwrap_or_else(|_| "ngspice".into()))
            .current_dir(dir)
            .args(["-b", &format!("{name}.cir")])
            .output()
            .unwrap();
        let mut log = o.stdout;
        log.extend(o.stderr);
        assert!(o.status.success());
        assert!(!String::from_utf8_lossy(&log).contains("Error"));
        fs::write(dir.join(format!("{name}.log")), log).unwrap();
        let e = read_data(&dir.join(format!("{name}_e.dat")));
        let f = read_data(&dir.join(format!("{name}_f.dat")));
        assert_eq!(e.len(), 1441);
        assert_eq!(e.len(), f.len());
        let (mut maxerr, mut maxdiff) = (0f64, 0f64);
        for (e, f) in e.iter().zip(f.iter()) {
            assert_eq!(e[0], f[0]);
            let z = Matrix2 {
                a: Complex::new(e[1], e[2]),
                c: Complex::new(e[3], e[4]),
                b: Complex::new(f[1], f[2]),
                d: Complex::new(f[3], f[4]),
            };
            let t = deembedded_return(z, r).unwrap();
            let shortcut = determinant_return(z, r);
            let y = fixture_y(e[0]);
            let analytic = (y.b + y.c) / (y.a + y.d);
            maxerr = maxerr.max((t - analytic).abs() / analytic.abs());
            maxdiff = maxdiff.max((t - shortcut).abs() / analytic.abs());
        }
        assert!(maxerr < 1e-8 && maxdiff < 1e-8);
        report += &format!("| {r} | {} | {maxerr:.6e} | {maxdiff:.6e} |\n", e.len());
    }
    report+="\n## Known-pole analytical regressions\n\nW is counterclockwise winding of F=1+T for frequency −∞→+∞. Z=P−W. P is supplied from the independently known denominator; a winding without P is not a stability verdict.\n\n| Fixture | P | W | Z | Unity directions |\n|---|---:|---:|---:|---|\n";
    let mut details = String::new();
    for (name, p, kind, k) in [
        ("one_pole_stable", 0, 0, 10.),
        ("three_pole_unstable", 0, 1, 27.),
        ("rhp_open_stabilized", 1, 2, 2.),
        ("notch_stable_multiple", 0, 3, 100.),
        ("notch_unstable_multiple", 0, 3, 200.),
    ] {
        let pts = samples(|s| match kind {
            0 => c(k) / (s + c(1.)),
            1 => c(k) / ((s + c(1.)) * (s + c(1.)) * (s + c(1.))),
            2 => c(k) / (s - c(1.)),
            _ => notch(s, k),
        });
        let n = nyquist(&pts, Some(p)).unwrap();
        let x = crossings(&pts).unwrap();
        let directions = x
            .iter()
            .map(|v| format!("{:?}", v.direction))
            .collect::<Vec<_>>()
            .join(" / ");
        report += &format!(
            "| {name} | {p} | {} | {} | {directions} |\n",
            n.ccw_winding,
            n.closed_rhp_poles.unwrap()
        );
        let mut csv = String::from("frequency_hz,return_real,return_imag\n");
        for x in pts {
            csv += &format!("{:.12e},{:.12e},{:.12e}\n", x.hz, x.t.re, x.t.im)
        }
        fs::write(dir.join(format!("{name}.csv")), csv).unwrap();
        details += &format!("\n{name} crossings (local angle; not conventional PM):\n\n");
        for v in x {
            details+=&format!("- {:.8}Hz {:?}; unwrapped {:.4}°; principal {:.4}°; signed separation from −1 {:.4}°.\n",v.hz,v.direction,v.unwrapped_phase_deg,v.principal_phase_deg,v.signed_angle_from_minus_one_deg)
        }
    }
    report += &details;
    report+="\nStable notch fixture: T=100(s²−0.2s+100)/[(s+1)(s²+20s+100)]. Closed polynomial s³+121s²+100s+10100 is Hurwitz because all coefficients are positive and121·100>10100. Its three unity crossings include an upward crossing with a negative local signed phase separation and a final downward crossing whose unwrapped phase is below−360°. It is nevertheless stable. At K=200,221·80<20100 and two closed poles are in the RHP.\n";
    fs::write(dir.join("report.md"), report).unwrap();
    println!("Four bridge SPICE fixtures and five analytical Nyquist fixtures completed.");
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn algebra_and_bridge_invariance() {
        for hz in [1., 100., 1e4, 1e6, 1e9] {
            let y = fixture_y(hz);
            let expected = (y.b + y.c) / (y.a + y.d);
            for r in [1., 10., 100., 1000.] {
                let z = y.with_bridge(r).inverse().unwrap();
                let t = deembedded_return(z, r).unwrap();
                assert!((t - expected).abs() < 1e-9 * expected.abs());
                assert!((t - determinant_return(z, r)).abs() < 1e-9 * expected.abs());
            }
        }
    }
    #[test]
    fn not_deembedding_is_detected() {
        let y = fixture_y(1e4);
        let closed = y.with_bridge(10.);
        let wrong = (closed.b + closed.c) / (closed.a + closed.d);
        let expected = (y.b + y.c) / (y.a + y.d);
        assert!((wrong - expected).abs() > 0.1);
    }
    #[test]
    fn stable_one_pole() {
        let p = samples(|s| c(10.) / (s + c(1.)));
        let n = nyquist(&p, Some(0)).unwrap();
        assert_eq!(n.ccw_winding, 0);
        assert_eq!(n.closed_rhp_poles, Some(0));
    }
    #[test]
    fn unstable_three_pole() {
        let p = samples(|s| c(27.) / ((s + c(1.)) * (s + c(1.)) * (s + c(1.))));
        let n = nyquist(&p, Some(0)).unwrap();
        assert_eq!(n.ccw_winding, -2);
        assert_eq!(n.closed_rhp_poles, Some(2));
    }
    #[test]
    fn unstable_open_loop_stabilized_and_unknown_p() {
        let p = samples(|s| c(2.) / (s - c(1.)));
        let n = nyquist(&p, Some(1)).unwrap();
        assert_eq!(n.ccw_winding, 1);
        assert_eq!(n.closed_rhp_poles, Some(0));
        assert!(nyquist(&p, Some(0)).is_err());
        assert_eq!(nyquist(&p, None).unwrap().closed_rhp_poles, None);
    }
    #[test]
    fn stable_multiple_crossings_negative_upward_angle() {
        assert!(121. * 100. > 10100.);
        let p = samples(|s| notch(s, 100.));
        let n = nyquist(&p, Some(0)).unwrap();
        assert_eq!(n.closed_rhp_poles, Some(0));
        let x = crossings(&p).unwrap();
        assert_eq!(
            x.iter().map(|x| x.direction).collect::<Vec<_>>(),
            vec![Direction::Down, Direction::Up, Direction::Down]
        );
        assert!(x[1].signed_angle_from_minus_one_deg < 0.);
        assert!(x[2].unwrapped_phase_deg + 180. < 0.);
        assert!(x[2].signed_angle_from_minus_one_deg > 0.);
    }
    #[test]
    fn unstable_multiple_crossings() {
        assert!(221. * 80. < 20100.);
        let p = samples(|s| notch(s, 200.));
        assert_eq!(nyquist(&p, Some(0)).unwrap().closed_rhp_poles, Some(2));
    }
    #[test]
    fn phase_branch_invariance() {
        for x in [-274.4, -94.4, 70.1, 259.76] {
            assert!((wrap180(x) - wrap180(x + 720.)).abs() < 1e-10);
        }
    }
    #[test]
    fn finite_band_and_marginal_are_not_certificates() {
        let p = vec![
            Point { hz: 0., t: c(10.) },
            Point {
                hz: 1.,
                t: Complex::new(5., -5.),
            },
            Point {
                hz: 10.,
                t: Complex::new(0.1, -1.),
            },
        ];
        assert!(nyquist(&p, Some(0)).is_err());
        let p = vec![
            Point { hz: 0., t: c(-1.) },
            Point {
                hz: 1.,
                t: Complex::new(-0.5, -0.5),
            },
            Point { hz: 1e6, t: c(0.) },
        ];
        assert!(nyquist(&p, Some(0)).is_err());
    }
}

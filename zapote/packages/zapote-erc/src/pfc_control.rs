//! UCC28180 nominal control calculation following datasheet equations 78-121.
//! This is a design calculator, not a hardware or stability qualification.

use std::f64::consts::PI;

#[derive(Clone, Copy)]
struct C {
    re: f64,
    im: f64,
}
impl C {
    fn n(re: f64, im: f64) -> Self {
        Self { re, im }
    }
    fn norm(self) -> f64 {
        (self.re * self.re + self.im * self.im).sqrt()
    }
    fn arg(self) -> f64 {
        self.im.atan2(self.re)
    }
}
use serde::Serialize;
use std::ops::{Add, Div, Mul};
impl Add for C {
    type Output = Self;
    fn add(self, o: Self) -> Self {
        Self::n(self.re + o.re, self.im + o.im)
    }
}
impl Mul for C {
    type Output = Self;
    fn mul(self, o: Self) -> Self {
        Self::n(
            self.re * o.re - self.im * o.im,
            self.re * o.im + self.im * o.re,
        )
    }
}
impl Div for C {
    type Output = Self;
    fn div(self, o: Self) -> Self {
        let d = o.re * o.re + o.im * o.im;
        Self::n(
            (self.re * o.re + self.im * o.im) / d,
            (self.im * o.re - self.re * o.im) / d,
        )
    }
}
impl Mul<f64> for C {
    type Output = Self;
    fn mul(self, o: f64) -> Self {
        Self::n(self.re * o, self.im * o)
    }
}
impl Div<f64> for C {
    type Output = Self;
    fn div(self, o: f64) -> Self {
        Self::n(self.re / o, self.im / o)
    }
}

#[derive(Clone, Copy, Debug, Serialize)]
pub struct PfcControlInput {
    pub input_power_w: f64,
    pub vin_rms: f64,
    pub vout: f64,
    pub cout: f64,
    pub rsense: f64,
    pub fsw: f64,
    pub gmi: f64,
    pub gmv: f64,
    pub k1: f64,
    pub rfb1: f64,
    pub rfb2: f64,
    pub fvoltage: f64,
    pub fpole: f64,
}

#[derive(Clone, Copy, Debug, Serialize)]
pub struct PfcControlResult {
    pub k_fq: f64,
    pub m1m2: f64,
    pub vcomp: f64,
    pub m1: f64,
    pub m2: f64,
    pub m3: f64,
    pub cicomp: f64,
    pub f_iavg: f64,
    pub f_pwm_ps: f64,
    pub gfb: f64,
    pub gvld_b_at_fv: f64,
    pub cvcomp: f64,
    pub rvcomp: f64,
    pub cvcomp_p: f64,
    pub crossover_hz: f64,
    pub phase_margin_deg: f64,
}

fn valid(x: f64) -> bool {
    x.is_finite() && x > 0.0
}

fn m1(v: f64) -> f64 {
    if v < 1.0 {
        0.068
    } else if v < 2.0 {
        0.156 * v - 0.088
    } else if v < 4.5 {
        0.313 * v - 0.401
    } else {
        1.007
    }
}

fn m2(v: f64, fsw: f64) -> f64 {
    if v <= 0.5 {
        0.0
    } else if v <= 4.6 {
        fsw / 65_000.0 * 0.1223 * (v - 0.5).powi(2)
    } else {
        fsw / 65_000.0 * 2.056
    }
}

fn m3(v: f64, fsw: f64) -> Option<f64> {
    if !(2.0..=4.5).contains(&v) {
        return None;
    }
    Some(fsw / 65_000.0 * (0.1148 * v * v - 0.1746 * v + 0.0586))
}

fn m1m2_at(v: f64, fsw: f64) -> f64 {
    m1(v) * m2(v, fsw)
}

fn complex_gain(
    i: &PfcControlInput,
    r: &PfcControlResult,
    hz: f64,
    cv: f64,
    rv: f64,
    cp: f64,
) -> C {
    let s = C::n(0.0, 2.0 * PI * hz);
    let gfb = i.rfb2 / (i.rfb1 + i.rfb2);
    let gpwm0 = r.m3 * i.vout / (r.m1m2 * 1.0); // volts; M1M2 is V/us in both ratios
    let gpwm = C::n(gpwm0, 0.0) / (C::n(1.0, 0.0) + s / (2.0 * PI * r.f_pwm_ps));
    let den_cap = cv + cp;
    let gea = C::n(i.gmv, 0.0) * (C::n(1.0, 0.0) + s * (rv * cv))
        / (s * den_cap * (C::n(1.0, 0.0) + s * (rv * cv * cp / den_cap)));
    C::n(gfb, 0.0) * gpwm * gea
}

fn crossover(
    i: &PfcControlInput,
    r: &PfcControlResult,
    cv: f64,
    rv: f64,
    cp: f64,
) -> Result<(f64, f64), &'static str> {
    let mut lo = 1e-3;
    let mut hi = i.fsw / 2.0;
    if complex_gain(i, r, lo, cv, rv, cp).norm() <= 1.0
        || complex_gain(i, r, hi, cv, rv, cp).norm() >= 1.0
    {
        return Err("selected compensation has no bracketed unity-gain crossover");
    }
    for _ in 0..100 {
        let mid = (lo * hi).sqrt();
        if complex_gain(i, r, mid, cv, rv, cp).norm() > 1.0 {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    let f = (lo * hi).sqrt();
    let phase = complex_gain(i, r, f, cv, rv, cp).arg().to_degrees();
    Ok((f, 180.0 + phase))
}

#[derive(Clone, Copy, Debug, Serialize)]
pub struct PfcSelectedEvaluation {
    pub f_iavg_actual: f64,
    pub crossover_hz: f64,
    pub phase_margin_deg: f64,
}

pub fn evaluate_selected(
    i: &PfcControlInput,
    cicomp: f64,
    cv: f64,
    rv: f64,
    cp: f64,
) -> Result<PfcSelectedEvaluation, &'static str> {
    for x in [cicomp, cv, rv, cp] {
        if !valid(x) {
            return Err("selected compensation values must be finite and positive");
        }
    }
    let base = calculate(*i)?;
    let (fc, pm) = crossover(i, &base, cv, rv, cp)?;
    Ok(PfcSelectedEvaluation {
        f_iavg_actual: i.gmi * base.m1 / (i.k1 * 2.0 * PI * cicomp),
        crossover_hz: fc,
        phase_margin_deg: pm,
    })
}

pub fn calculate(i: PfcControlInput) -> Result<PfcControlResult, &'static str> {
    for x in [
        i.input_power_w,
        i.vin_rms,
        i.vout,
        i.cout,
        i.rsense,
        i.fsw,
        i.gmi,
        i.gmv,
        i.k1,
        i.rfb1,
        i.rfb2,
        i.fvoltage,
        i.fpole,
    ] {
        if !valid(x) {
            return Err("all inputs must be finite and positive");
        }
    }
    let k_fq = 1.0 / i.fsw;
    // Equation 78: P_IN*VOUT*2.5*Rs*K1*fSW/VIN².
    // Reported in V/us, hence the 1e6 scale.
    let m1m2 =
        i.input_power_w * i.vout * 2.5 * i.rsense * i.k1 * i.fsw / (i.vin_rms * i.vin_rms * 1e6);
    let mut lo = 2.0;
    let mut hi = 4.5;
    if !(m1m2_at(lo, i.fsw) <= m1m2 && m1m2 <= m1m2_at(hi, i.fsw)) {
        return Err("M1M2 outside eq83/87 bisection range");
    }
    for _ in 0..100 {
        let mid = (lo + hi) / 2.0;
        if m1m2_at(mid, i.fsw) < m1m2 {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    let vcomp = (lo + hi) / 2.0;
    let m_1 = m1(vcomp);
    let m_2 = m2(vcomp, i.fsw);
    let m_3 = m3(vcomp, i.fsw).ok_or("M3 eq96 requires 2V <= VCOMP <= 4.5V")?;
    let cicomp = i.gmi * m_1 / (i.k1 * 2.0 * PI * 5_000.0);
    let f_iavg = i.gmi * m_1 / (i.k1 * 2.0 * PI * cicomp);
    let f_pwm_ps = 1.0
        / (2.0 * PI * i.k1 * 2.5 * i.rsense * i.vout.powi(3) * i.cout
            / (k_fq * m1m2 * 1e6 * i.vin_rms.powi(2)));
    let gfb = i.rfb2 / (i.rfb1 + i.rfb2);
    let r0 = PfcControlResult {
        k_fq,
        m1m2,
        vcomp,
        m1: m_1,
        m2: m_2,
        m3: m_3,
        cicomp,
        f_iavg,
        f_pwm_ps,
        gfb,
        gvld_b_at_fv: 0.0,
        cvcomp: 0.0,
        rvcomp: 0.0,
        cvcomp_p: 0.0,
        crossover_hz: 0.0,
        phase_margin_deg: 0.0,
    };
    let gvl = gfb * (m_3 * i.vout / m1m2) / (1.0 + (i.fvoltage / f_pwm_ps).powi(2)).sqrt();
    let gvld_b = 20.0 * gvl.log10();
    let cv =
        (i.gmv / 10f64.powf(-gvld_b / 20.0)) * (i.fvoltage / f_pwm_ps) / (2.0 * PI * i.fvoltage);
    let rv = 1.0 / (2.0 * PI * f_pwm_ps * cv);
    let cp_den = 2.0 * PI * i.fpole * rv * cv - 1.0;
    if !cp_den.is_finite() || cp_den <= 0.0 {
        return Err("VCOMP pole target is incompatible with selected series network");
    }
    let cp = cv / cp_den;
    let mut r = PfcControlResult {
        gvld_b_at_fv: gvld_b,
        cvcomp: cv,
        rvcomp: rv,
        cvcomp_p: cp,
        ..r0
    };
    let (fc, pm) = crossover(&i, &r, cv, rv, cp)?;
    r.crossover_hz = fc;
    r.phase_margin_deg = pm;
    Ok(r)
}

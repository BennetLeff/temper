//! Conditional immediate-gate-off LC screen for the F2-open topology.
//! This does not model controller delay, cold start, restart, ESR/ESL, or a
//! failed-short switch. It includes constant-source work during commutation.

use std::f64::consts::PI;

#[derive(Clone, Copy)]
struct Case { name: &'static str, vin: f64, v0: f64, i0: f64, l: f64, c: f64 }

fn immediate_off(c: Case) -> Result<(f64, f64, f64, f64), &'static str> {
    if !(c.vin.is_finite() && c.v0.is_finite() && c.i0.is_finite() && c.l.is_finite() && c.c.is_finite()) { return Err("non-finite input"); }
    if c.l <= 0.0 { return Err("L must be positive"); }
    if c.c <= 0.0 { return Err("C must be positive"); }
    if c.i0 < 0.0 { return Err("I0 must be non-negative"); }
    if c.v0 <= c.vin { return Err("contract requires V0 > Vin"); }
    let x0 = c.v0 - c.vin;
    let z = (c.l / c.c).sqrt();
    let x1 = (x0 * x0 + c.l / c.c * c.i0 * c.i0).sqrt();
    let v1 = c.vin + x1;
    let theta = (c.i0 * z / x0).atan();
    let t = theta * (c.l * c.c).sqrt();
    let q = c.c * (v1 - c.v0);
    let e_cap = 0.5 * c.c * (v1 * v1 - c.v0 * c.v0);
    Ok((v1, t, q, e_cap))
}

fn check(c: Case) {
    let (v, t, q, e) = immediate_off(c).expect("valid positive immediate-off case");
    assert!(v >= c.v0 && t >= 0.0 && q >= 0.0 && e >= 0.0);
    let source_work = c.vin * q;
    let inductor_energy = 0.5 * c.l * c.i0 * c.i0;
    let cap_energy = 0.5 * c.c * (v*v - c.v0*c.v0);
    assert!((cap_energy - (inductor_energy + source_work)).abs() < 1e-12);
    assert!(t < PI * (c.l*c.c).sqrt() / 2.0);
}

fn main() {
    // Same-phase retained pfc_power CCM input: 120 Vrms line peak, 389.615 V
    // bus, 15 A input RMS, 129.107 kHz, I_L,peak = 23.231838 A.
    let vin = 120.0 * 2.0_f64.sqrt();
    let v0 = 389.6153846;
    let i0 = 23.23183831948713;
    let mut cases: Vec<Case> = Vec::new();
    for (name, c) in [("470nF",470e-9), ("1uF",1e-6), ("1p5uF",1.5e-6)] {
        cases.push(Case { name, vin, v0, i0, l: 180e-6, c });
    }
    // Separate assumed sensitivity: L=216 uH and C=90% of each nominal C.
    for (name, c) in [("470nF_L216uH_C90",423e-9), ("1uF_L216uH_C90",900e-9), ("1p5uF_L216uH_C90",1.35e-6)] {
        cases.push(Case { name, vin, v0, i0, l: 216e-6, c });
    }
    println!("case,vin_v,v0_v,i0_a,l_uH,c_nF,vfinal_v,tzero_us,q_uC,ecap_mJ");
    for &c in &cases { let (v,t,q,e) = immediate_off(c).unwrap();
        println!("{},{:.9},{:.3},{:.6},{:.3},{:.3},{:.6},{:.6},{:.6},{:.6}", c.name,c.vin,c.v0,c.i0,c.l*1e6,c.c*1e9,v,t*1e6,q*1e6,e*1e3); }
    for &c in &cases { check(c); }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn energy_and_zero_current_oracles() {
        check(Case { name:"t", vin:169.7, v0:389.6, i0:23.2, l:180e-6, c:470e-9 });
        check(Case { name:"zero", vin:169.7, v0:389.6, i0:0.0, l:180e-6, c:470e-9 });
    }
    #[test] fn rejects_out_of_contract() {
        for c in [
            Case { name:"negative_i",vin:1.,v0:2.,i0:-1.,l:1.,c:1. },
            Case { name:"zero_l",vin:1.,v0:2.,i0:1.,l:0.,c:1. },
            Case { name:"zero_c",vin:1.,v0:2.,i0:1.,l:1.,c:0. },
            Case { name:"coldstart",vin:2.,v0:0.,i0:1.,l:1.,c:1. },
            Case { name:"equal_nodes",vin:2.,v0:2.,i0:1.,l:1.,c:1. },
        ] { assert!(immediate_off(c).is_err(), "{} must fail closed", c.name); }
    }
}

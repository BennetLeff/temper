//! Independent checks for the source-bound surrogate constants.
//! These are deliberately algebraic, not a differential test of the netlist.

const VT: f64 = 25.85e-3;
const D_IS: f64 = 1e-14;
const D_N: f64 = 1.4;
const D_RS: f64 = 20e-3;
const D_C400: f64 = 45e-12;
const MOS_KP: f64 = 4.0;
const MOS_VTO: f64 = 4.0;
const MOS_RSERIES: f64 = 2e-3;

fn diode_forward(i: f64) -> f64 {
    D_N * VT * (1.0 + i / D_IS).ln() + i * D_RS
}

#[test]
fn sic_forward_drop_is_in_the_datasheet_band() {
    let vf = diode_forward(10.0);
    assert!((1.0..=1.9).contains(&vf), "VF={vf} V");
}

#[test]
fn sic_capacitive_energy_matches_400v_anchor() {
    let e = 0.5 * D_C400 * 400.0_f64.powi(2);
    assert!((e - 3.6e-6).abs() < 1e-12, "EC={e} J");
}

#[test]
fn mos_gate_charge_and_miller_charge_are_explicit() {
    let qg: f64 = 12e-9 * 10.0;
    let qgd: f64 = 112e-12 * 520.0;
    assert!((qg - 120e-9).abs() < 1e-15);
    assert!((qgd - 58.24e-9).abs() < 0.5e-9);
}

// Level-1 NMOS triode current, including the declared 1 mΩ drain and source
// resistors.  This is the same finite-I/V law used by ngspice's STWMOS model;
// checking a concrete 32.5 A operating point catches a reversion to an
// unlimited voltage-controlled resistor.
fn mos_current(vgs: f64, vds_external: f64) -> f64 {
    let vov = (vgs - MOS_VTO).max(0.0);
    if vov == 0.0 { return 0.0; }
    let i_sat = 0.5 * MOS_KP * vov * vov;
    if vds_external >= vov + MOS_RSERIES * i_sat {
        return i_sat;
    }
    let mut vch = vds_external.max(0.0);
    for _ in 0..20 {
        let i = MOS_KP * (vov * vch - 0.5 * vch * vch).max(0.0);
        let f = vch + MOS_RSERIES * i - vds_external;
        let di_dv = if vch < vov { MOS_KP * (vov - vch) } else { 0.0 };
        vch = (vch - f / (1.0 + MOS_RSERIES * di_dv)).max(0.0);
    }
    MOS_KP * (vov * vch - 0.5 * vch * vch).max(0.0)
}

#[test]
fn mos_output_current_is_finite_and_matches_10v_datasheet_anchor() {
    let i_at_10v_1p62 = mos_current(10.0, 1.62);
    assert!((i_at_10v_1p62 - 32.5).abs() < 1.0, "I(10 V,1.62 V)={i_at_10v_1p62} A");
    let i_sat = mos_current(10.0, 10.0);
    assert!((i_sat - 72.0).abs() < 0.5, "I_sat(10 V)={i_sat} A");
    assert!(mos_current(4.5, 10.0) < 1.0, "near-threshold current must remain finite");
}

fn main() {}

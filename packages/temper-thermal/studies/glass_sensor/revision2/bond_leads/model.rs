//! Screening of sourced chip dimensions and candidate bond/lead processes; no measured results.
use std::{
    error::Error,
    f64::consts::PI,
    fs::File,
    io::{BufWriter, Write},
};
#[derive(Clone, Copy)]
struct Wire {
    name: &'static str,
    diameter_mm: f64,
    k: f64,
    resistivity: f64,
}
const CU: Wire = Wire {
    name: "TFCP003_Cu40",
    diameter_mm: 0.08,
    k: 401.,
    resistivity: 1.69e-8,
};
const CONSTANTAN: Wire = Wire {
    name: "TFCC005_CuNi36",
    diameter_mm: 0.13,
    k: 19.5,
    resistivity: 4.9e-7,
};
const NI: Wire = Wire {
    name: "Goodfellow1000047402_Ni",
    diameter_mm: 0.1,
    k: 90.9,
    resistivity: 6.9e-8,
};
fn area(d_mm: f64) -> f64 {
    PI * (d_mm * 0.0005).powi(2)
}
fn wire_r(w: Wire, l_m: f64) -> f64 {
    w.resistivity * l_m / area(w.diameter_mm)
}
fn lead_g(w: Wire, l_m: f64, stub_m: f64) -> f64 {
    // Two shared native stubs in parallel, then four extension conductors in parallel.
    1. / (stub_m / (2. * 90.9 * area(0.2)) + l_m / (4. * w.k * area(w.diameter_mm)))
}
fn fin_g(w: Wire, l_m: f64, stub_m: f64, ambient_h: f64) -> f64 {
    if ambient_h == 0. {
        return lead_g(w, l_m, stub_m);
    }
    // PFA k=0.25 is a sensitivity assumption. All surroundings set to cold anchor:
    // an intentionally adverse 1-D fin boundary, not the unknown real axial air profile.
    let di = w.diameter_mm * 1e-3;
    let outer = di + 2. * 0.076e-3;
    let per_length = 1. / ((outer / di).ln() / (2. * PI * 0.25) + 1. / (ambient_h * PI * outer));
    let ka = w.k * area(w.diameter_mm);
    let m = (per_length / ka).sqrt();
    let extension = 4. * ka * m / (m * l_m).tanh();
    1. / (stub_m / (2. * 90.9 * area(0.2)) + 1. / extension)
}
fn rtd(t: f64) -> f64 {
    100. * (1. + 3.9083e-3 * t - 5.775e-7 * t * t)
}
fn drdt(t: f64) -> f64 {
    100. * (3.9083e-3 - 2. * 5.775e-7 * t)
}
#[derive(Clone, Copy)]
struct Chip {
    name: &'static str,
    l: f64,
    w: f64,
    h: f64,
    blob_mm3: f64,
}
const M222: Chip = Chip {
    name: "M222_envelope_proxy",
    l: 2.3,
    w: 2.1,
    h: 0.9,
    blob_mm3: 0.,
};
const IST: Chip = Chip {
    name: "IST161_substrate_plus_blob",
    l: 1.6,
    w: 1.2,
    h: 0.25,
    blob_mm3: 0.3,
};
#[derive(Clone, Copy)]
struct Interface {
    name: &'static str,
    bond_mm: f64,
    bond_k: f64,
    plate_mm: f64,
    plate_k: f64,
    plate_cv: f64,
}
const RESBOND: Interface = Interface {
    name: "Resbond908_0p10",
    bond_mm: 0.1,
    bond_k: 2.163418635,
    plate_mm: 0.,
    plate_k: 1.,
    plate_cv: 0.,
};
fn capacitance(chip: Chip, cv: f64) -> f64 {
    chip.l * chip.w * chip.h * 1e-9 * cv + chip.blob_mm3 * 1e-9 * 2.5e6
}
fn interface_r(chip: Chip, p: Interface) -> f64 {
    let a = chip.l * chip.w * 1e-6;
    let bonds = if p.plate_mm > 0. { 2. } else { 1. };
    (0.15e-3 / 15.
        + bonds * p.bond_mm * 1e-3 / p.bond_k
        + p.plate_mm * 1e-3 / p.plate_k
        + 0.5 * chip.h * 1e-3 / 25.)
        / a
}
#[derive(Clone, Copy)]
struct Network {
    cap_c: f64,
    chip_c: f64,
    g: f64,
    input: f64,
    loss: f64,
    lead: f64,
}
fn network(chip: Chip, p: Interface, h: f64, lead: f64, cv: f64) -> Network {
    let bond_c = (chip.l + 0.4)
        * (chip.w + 0.4)
        * p.bond_mm
        * 1e-9
        * 2.0e6
        * if p.plate_mm > 0. { 2. } else { 1. };
    let plate_c = 2.8 * 2.8 * p.plate_mm * 1e-9 * p.plate_cv;
    Network {
        cap_c: PI * 4_f64.powi(2) * 0.15 * 1e-9 * 4e6 + 0.5 * bond_c,
        chip_c: capacitance(chip, cv) + 0.5 * bond_c + plate_c,
        g: 1. / interface_r(chip, p),
        input: h * PI * 0.004_f64.powi(2),
        loss: 0.0005,
        lead,
    }
}
fn steady(n: Network, pan: f64, body: f64, power: f64) -> [f64; 2] {
    let a = n.input + n.loss + n.g;
    let d = n.g + n.lead;
    let b = n.input * pan + n.loss * body;
    let e = n.lead * body + power;
    let det = a * d - n.g * n.g;
    [(d * b + n.g * e) / det, (a * e + n.g * b) / det]
}
fn step(n: Network, dt: f64) -> (f64, f64) {
    let final_t = steady(n, 100., 25., 0.)[1];
    let target = 25. + 0.9 * (final_t - 25.);
    let mut y = [25.; 2];
    let mut relative = f64::NAN;
    let mut imposed = f64::NAN;
    let a = n.cap_c / dt + n.input + n.loss + n.g;
    let d = n.chip_c / dt + n.g + n.lead;
    let det = a * d - n.g * n.g;
    for i in 1..=(120. / dt) as usize {
        let b = n.cap_c / dt * y[0] + n.input * 100. + n.loss * 25.;
        let e = n.chip_c / dt * y[1] + n.lead * 25.;
        y = [(d * b + n.g * e) / det, (a * e + n.g * b) / det];
        if relative.is_nan() && y[1] >= target {
            relative = i as f64 * dt;
        }
        if imposed.is_nan() && y[1] >= 92.5 {
            imposed = i as f64 * dt;
        }
    }
    (relative, imposed)
}
fn main() -> Result<(), Box<dyn Error>> {
    std::fs::create_dir_all("results")?;
    let mut fins = BufWriter::new(File::create("results/lead_fin_sensitivity.csv")?);
    writeln!(fins,"status,wire,length_mm,h_ambient_w_m2k_ASSUMED,anchor_and_all_air_c,lead_g_w_k,heat_at190k_w")?;
    for w in [CU, CONSTANTAN, NI] {
        for l in [0.03, 0.06, 0.1] {
            for h in [0., 5., 10., 15.] {
                let g = fin_g(w, l, 0.001, h);
                writeln!(
                    fins,
                    "SIMULATION,{},{},{h},60,{g:.9},{:.9}",
                    w.name,
                    l * 1000.,
                    g * 190.
                )?;
            }
        }
    }
    let mut out = BufWriter::new(File::create("results/lead_tradeoffs.csv")?);
    writeln!(out,"status,wire,length_mm,stub_mm,current_ma,extension_r_ohm_per_wire,shared_stub_r_ohm_two,thermal_g_w_k,heat_leak_at190k_w,johnson_temp_rms_c_10hz_523k,current_leads_drop_mv,emf_40uv_equiv_c,one_na_sense_bias_c")?;
    for w in [CU, CONSTANTAN, NI] {
        for length in [0.03, 0.06, 0.1] {
            for stub in [0.001, 0.005, 0.008] {
                for current in [0.0003, 0.001] {
                    let r = wire_r(w, length);
                    let stub_r = 2. * 6.9e-8 * stub / area(0.2);
                    let g = lead_g(w, length, stub);
                    let noise = (4. * 1.380649e-23 * 523.15 * (rtd(250.) + 2. * r) * 10.).sqrt()
                        / (current * drdt(250.));
                    writeln!(out,"SIMULATION,{},{},{},{},{r:.9},{stub_r:.9},{g:.9},{:.9},{noise:.9},{:.9},{:.9},{:.9}",w.name,length*1000.,stub*1000.,current*1000.,g*190.,2.*r*current*1000.,40e-6/(current*drdt(250.)),r*1e-9/(current*drdt(250.)))?;
                }
            }
        }
    }
    let mut out = BufWriter::new(File::create("results/thermal_comparison.csv")?);
    writeln!(out,"status,chip,interface,h_w_m2k,chip_cv_j_m3k,lead_g_w_k,chip_c_j_k,interface_r_k_w,t90_final_s,t90_pan_s,error200_c,selfheat250_c_0p3ma")?;
    let interfaces = [
        RESBOND,
        Interface {
            name: "Resbond908_0p075_PROCESS_UNQUALIFIED",
            bond_mm: 0.075,
            ..RESBOND
        },
        Interface {
            name: "Resbond908_0p15",
            bond_mm: 0.15,
            ..RESBOND
        },
        Interface {
            name: "Alumina0p25_two_bonds0p075_RFQ",
            bond_mm: 0.075,
            plate_mm: 0.25,
            plate_k: 24.7,
            plate_cv: 3.12e6,
            ..RESBOND
        },
        Interface {
            name: "AlN0p25_two_bonds0p075_RFQ",
            bond_mm: 0.075,
            plate_mm: 0.25,
            plate_k: 170.,
            plate_cv: 2.4e6,
            ..RESBOND
        },
    ];
    for chip in [M222, IST] {
        for p in interfaces {
            for h in [250., 1000., 4000.] {
                for cv in [2.7e6, 3.12e6, 3.8e6] {
                    for lead in [
                        lead_g(CU, 0.06, 0.001),
                        lead_g(CONSTANTAN, 0.06, 0.001),
                        0.0003,
                    ] {
                        let n = network(chip, p, h, lead, cv);
                        let (a, b) = step(n, 0.002);
                        let base = steady(n, 250., 60., 0.)[1];
                        let hot = steady(n, 250., 60., 0.0003_f64.powi(2) * rtd(base))[1];
                        writeln!(out,"SIMULATION,{},{},{h},{cv},{lead:.9},{:.9},{:.9},{a:.6},{b:.6},{:.6},{:.9}",chip.name,p.name,capacitance(chip,cv),interface_r(chip,p),steady(n,200.,60.,0.)[1]-200.,hot-base)?;
                    }
                }
            }
        }
    }
    let mut out = BufWriter::new(File::create("results/cte_mismatch.csv")?);
    writeln!(out,"status,span_mm,bond_mm,delta_t_c,cap_cte_ppm_k,ceramic_cte_ppm_k,edge_to_edge_mismatch_um,kinematic_shear_strain_NOT_STRESS")?;
    for l in [1.6, 2.3, 2.8] {
        for bond in [0.075, 0.1, 0.15] {
            for ceramic in [8.1, 8.2, 4.7] {
                let mismatch = (16.0_f64 - ceramic) * 1e-6 * 225. * l;
                writeln!(
                    out,
                    "SIMULATION,{l},{bond},225,16,{ceramic},{:.9},{:.9}",
                    mismatch * 1000.,
                    mismatch / bond
                )?;
            }
        }
    }
    let mut out = BufWriter::new(File::create("results/shared_stub_calibration.csv")?);
    writeln!(out,"status,stub_mm,temperature_c,ni_resistivity_factor_ASSUMPTION,shared_stub_ohm,approx_c_error_if_uncompensated")?;
    for stub in [0.001, 0.005, 0.008] {
        for t in [20., 100., 250.] {
            let factor = 1. + 0.006 * (t - 20.);
            let r = 2. * 6.9e-8 * factor * stub / area(0.2);
            writeln!(
                out,
                "SIMULATION,{},{t},{factor},{r:.9},{:.9}",
                stub * 1000.,
                r / drdt(t)
            )?;
        }
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fin_zero_h_recovers_conduction() {
        assert_eq!(fin_g(CU, 0.06, 0.001, 0.), lead_g(CU, 0.06, 0.001));
    }
    #[test]
    fn ambient_loss_defeats_unlimited_length_benefit() {
        assert!(fin_g(CU, 0.1, 0.001, 10.) > lead_g(CU, 0.03, 0.001));
    }
    #[test]
    fn wire_r_doubles_with_length() {
        assert!((wire_r(CU, 0.12) / wire_r(CU, 0.06) - 2.).abs() < 1e-12);
    }
    #[test]
    fn four_wire_thermal_paths_are_counted() {
        assert!((lead_g(CU, 0.06, 0.) - 4. * 401. * area(0.08) / 0.06).abs() < 1e-15);
    }
    #[test]
    fn common_stubs_reduce_parallel_thermal_conductance() {
        assert!(lead_g(CU, 0.06, 0.008) < lead_g(CU, 0.06, 0.001));
    }
    #[test]
    fn constantan_low_heat_is_not_low_resistance() {
        assert!(
            lead_g(CONSTANTAN, 0.06, 0.001) < lead_g(CU, 0.06, 0.001)
                && wire_r(CONSTANTAN, 0.06) > wire_r(CU, 0.06)
        );
    }
    #[test]
    fn rtd_reference_at100() {
        assert!((rtd(100.) - 138.5055).abs() < 1e-8);
    }
    #[test]
    fn extra_plate_requires_two_bonds() {
        let p = Interface {
            plate_mm: 0.25,
            plate_k: 170.,
            ..RESBOND
        };
        assert!(interface_r(M222, p) > interface_r(M222, RESBOND));
    }
    #[test]
    fn steady_no_loss_returns_pan() {
        let mut n = network(M222, RESBOND, 1000., 0., 3.12e6);
        n.loss = 0.;
        assert!((steady(n, 200., 25., 0.)[1] - 200.).abs() < 1e-10);
    }
    #[test]
    fn time_refinement() {
        let n = network(M222, RESBOND, 1000., 0.00013, 3.12e6);
        let a = step(n, 0.002);
        let b = step(n, 0.001);
        assert!((a.0 - b.0).abs() < 0.005 && (a.1 - b.1).abs() < 0.005);
    }
    #[test]
    fn current_square_scales_heat() {
        let n = network(M222, RESBOND, 1000., 0.00013, 3.12e6);
        let base = steady(n, 250., 60., 0.)[1];
        let a = steady(n, 250., 60., 0.0003_f64.powi(2) * rtd(250.))[1] - base;
        let b = steady(n, 250., 60., 0.001_f64.powi(2) * rtd(250.))[1] - base;
        assert!((b / a - 100. / 9.).abs() < 1e-6);
    }
}

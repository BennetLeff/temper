//! Cap-local differential contact concept: bounded mechanical fault exploration.
//! No geometry, errors or classifications here are measured hardware results.
use std::error::Error;
use std::fs::{self, File};
use std::io::{BufWriter, Write};
use std::path::Path;

const LOWER_UM: f64 = 25.0;
const UPPER_UM: f64 = 220.0;
const STOP_UM: f64 = 250.0;

#[derive(Clone, Copy, Debug)]
enum Fault {
    CleanLoaded,
    Released,
    GuideJamPanRemoved,
    SealJamPanRemoved,
    IslandJamPanRemoved,
    InsulatingDebris,
    OverloadStop,
    WitnessRodSeized,
    SensorFrozenFresh,
    SensorStale,
    OpticalBlocked,
    ReferenceShift,
}
const FAULTS: [Fault; 12] = [
    Fault::CleanLoaded,
    Fault::Released,
    Fault::GuideJamPanRemoved,
    Fault::SealJamPanRemoved,
    Fault::IslandJamPanRemoved,
    Fault::InsulatingDebris,
    Fault::OverloadStop,
    Fault::WitnessRodSeized,
    Fault::SensorFrozenFresh,
    Fault::SensorStale,
    Fault::OpticalBlocked,
    Fault::ReferenceShift,
];
impl Fault {
    fn name(self) -> &'static str {
        match self {
            Self::CleanLoaded => "clean_loaded",
            Self::Released => "released",
            Self::GuideJamPanRemoved => "guide_jam_pan_removed",
            Self::SealJamPanRemoved => "seal_jam_pan_removed",
            Self::IslandJamPanRemoved => "island_jam_pan_removed",
            Self::InsulatingDebris => "insulating_debris",
            Self::OverloadStop => "overload_stop",
            Self::WitnessRodSeized => "witness_rod_seized",
            Self::SensorFrozenFresh => "sensor_frozen_fresh",
            Self::SensorStale => "sensor_stale",
            Self::OpticalBlocked => "optical_blocked",
            Self::ReferenceShift => "reference_shift",
        }
    }
}
struct Observation {
    differential_um: f64,
    old_plunger_loaded: bool,
    diagnostics_ok: bool,
    actual_cap_load: bool,
    thermal_contact: bool,
}
fn scenario(
    fault: Fault,
    force_n: f64,
    stiffness_n_mm: f64,
    bias_um: f64,
    residual_force_n: f64,
) -> Observation {
    let loaded_um = force_n / stiffness_n_mm * 1000.0;
    let unloaded_um = residual_force_n / stiffness_n_mm * 1000.0;
    let (delta, old_loaded, diagnostics, cap_load, thermal_contact) = match fault {
        Fault::CleanLoaded => (loaded_um, true, true, true, true),
        Fault::Released => (unloaded_um, false, true, false, false),
        Fault::GuideJamPanRemoved | Fault::SealJamPanRemoved => {
            (unloaded_um, true, true, false, false)
        }
        // These are adversarial retained deflections AFTER a valid acquisition.
        // The model deliberately reports the false positives, rather than
        // granting a fictional diagnostic that would make them disappear.
        Fault::IslandJamPanRemoved | Fault::WitnessRodSeized | Fault::SensorFrozenFresh => {
            (loaded_um, true, true, false, false)
        }
        Fault::InsulatingDebris => (loaded_um, true, true, true, false),
        Fault::OverloadStop => (STOP_UM, true, true, true, true),
        Fault::SensorStale | Fault::OpticalBlocked => (loaded_um, true, false, false, false),
        Fault::ReferenceShift => (100.0, false, true, false, false),
    };
    Observation {
        differential_um: delta + bias_um,
        old_plunger_loaded: old_loaded,
        diagnostics_ok: diagnostics,
        actual_cap_load: cap_load,
        thermal_contact,
    }
}
fn mechanically_permitted(o: &Observation) -> bool {
    o.diagnostics_ok
        && o.differential_um.is_finite()
        && o.differential_um >= LOWER_UM
        && o.differential_um < UPPER_UM
}

// Worst-case interval arithmetic, with no assumed cancellation or distribution.
fn margins(force_n: f64, error_um: f64, stiction_n: f64) -> (f64, f64) {
    let loaded_low = (force_n - stiction_n).max(0.0) / 2.4 * 1000.0 - error_um;
    let unloaded_high = stiction_n / 1.6 * 1000.0 + error_um;
    (loaded_low - LOWER_UM, LOWER_UM - unloaded_high)
}

// Main-plunger top stop carries preload until the local island load exceeds it.
fn series_contact_force(
    penetration_mm: f64,
    effective_preload_n: f64,
    main_rate: f64,
    island_rate: f64,
) -> f64 {
    let local_only = penetration_mm.max(0.0) * island_rate;
    if local_only <= effective_preload_n {
        local_only
    } else {
        (effective_preload_n + main_rate * penetration_mm) / (1.0 + main_rate / island_rate)
    }
}

fn output(dir: &Path) -> Result<(), Box<dyn Error>> {
    fs::create_dir_all(dir)?;
    let mut rows = BufWriter::new(File::create(dir.join("fault_sweep.csv"))?);
    writeln!(rows,"scenario,force_n,island_rate_n_mm,bias_um,residual_force_n,observed_um,actual_cap_load,thermal_contact,old_plunger_loaded,candidate_mechanical_permission,false_mechanical_permission,false_thermal_permission")?;
    let mut summary = BufWriter::new(File::create(dir.join("fault_summary.csv"))?);
    writeln!(summary,"scenario,cases,mechanical_permissions,false_mechanical_permissions,false_thermal_permissions,old_false_mechanical_permissions")?;
    let mut qualified = BufWriter::new(File::create(dir.join("qualified_summary.csv"))?);
    writeln!(
        qualified,
        "scenario,cases,false_mechanical_permissions,false_thermal_permissions"
    )?;
    for fault in FAULTS {
        let mut cases = 0;
        let mut false_mechanical = 0;
        let mut false_thermal = 0;
        for force in [0.12, 0.18, 0.28] {
            for rate in [1.6, 2.0, 2.4] {
                for bias in [-15.0, 0.0, 15.0] {
                    for residual in [0.0, 0.005, 0.01] {
                        let o = scenario(fault, force, rate, bias, residual);
                        let permit = mechanically_permitted(&o);
                        cases += 1;
                        false_mechanical += u32::from(permit && !o.actual_cap_load);
                        false_thermal += u32::from(permit && !o.thermal_contact);
                    }
                }
            }
        }
        writeln!(
            qualified,
            "{},{cases},{false_mechanical},{false_thermal}",
            fault.name()
        )?;
    }
    let mut total = 0;

    for fault in FAULTS {
        let mut counts = [0_u32; 5];
        for force in [0.08, 0.10, 0.12, 0.18, 0.28] {
            for rate in [1.6, 2.0, 2.4] {
                for bias in [-30.0, -15.0, 0.0, 15.0, 30.0] {
                    for residual in [0.0, 0.005, 0.01, 0.03] {
                        let o = scenario(fault, force, rate, bias, residual);
                        let permit = mechanically_permitted(&o);
                        let false_mech = permit && !o.actual_cap_load;
                        let false_thermal = permit && !o.thermal_contact;
                        counts[0] += 1;
                        counts[1] += u32::from(permit);
                        counts[2] += u32::from(false_mech);
                        counts[3] += u32::from(false_thermal);
                        counts[4] += u32::from(
                            o.diagnostics_ok && o.old_plunger_loaded && !o.actual_cap_load,
                        );
                        writeln!(rows,"{},{force:.3},{rate:.3},{bias:.3},{residual:.3},{:.3},{},{},{},{permit},{false_mech},{false_thermal}",
                                 fault.name(),o.differential_um,o.actual_cap_load,o.thermal_contact,o.old_plunger_loaded)?;
                    }
                }
            }
        }
        total += counts[0];
        writeln!(
            summary,
            "{},{},{},{},{},{}",
            fault.name(),
            counts[0],
            counts[1],
            counts[2],
            counts[3],
            counts[4]
        )?;
    }
    let mut budget = BufWriter::new(File::create(dir.join("threshold_budget.csv"))?);
    writeln!(budget,"minimum_force_n,error_bound_um,residual_stiction_n,loaded_margin_um,unloaded_margin_um,separated")?;
    for f in 6..=16 {
        for error in (0..=50).step_by(5) {
            for stiction in [0.0, 0.005, 0.01, 0.02, 0.03] {
                let force = f64::from(f) / 100.0;
                let (on, off) = margins(force, f64::from(error), stiction);
                writeln!(
                    budget,
                    "{force:.3},{error},{stiction:.3},{on:.3},{off:.3},{}",
                    on > 0.0 && off > 0.0
                )?;
            }
        }
    }
    let mut travel = BufWriter::new(File::create(dir.join("series_force.csv"))?);
    writeln!(travel,"available_depression_mm,effective_preload_n,island_rate_n_mm,cap_force_n,island_motion_mm,main_motion_mm")?;
    for depression in [0.05, 0.10, 0.25, 0.60] {
        for preload in [0.09, 0.12, 0.15] {
            for rate in [1.6, 2.0, 2.4] {
                let force = series_contact_force(depression, preload, 0.2, rate);
                let island = force / rate;
                writeln!(
                    travel,
                    "{depression:.3},{preload:.3},{rate:.3},{force:.6},{island:.6},{:.6}",
                    depression - island
                )?;
            }
        }
    }
    let mut dynamics = BufWriter::new(File::create(dir.join("release_dynamics.csv"))?);
    writeln!(dynamics,"island_mass_g,island_rate_n_mm,damping_ratio,estimated_2pct_settling_ms,plus_filter_and_task_ms")?;
    for mass_g in [0.2_f64, 0.5, 1.0] {
        for rate in [1.6_f64, 2.0, 2.4] {
            for damping in [0.02, 0.05, 0.10, 0.20, 0.40] {
                let omega = (rate * 1000.0 / (mass_g / 1000.0)).sqrt();
                let settling_ms = 4.0 / (damping * omega) * 1000.0;
                // 9 samples at 2kHz, conservative full-window4.5ms + loop10ms.
                writeln!(
                    dynamics,
                    "{mass_g:.3},{rate:.3},{damping:.3},{settling_ms:.3},{:.3}",
                    settling_ms + 14.5
                )?;
            }
        }
    }
    println!("{total} fault cases; 605 interval-budget cases; 36 series-force cases; 45 release-dynamics cases.");
    let mut pulse = BufWriter::new(File::create(dir.join("pulse_identifiability.csv"))?);
    writeln!(
        pulse,
        "truth,capacity_j_k,total_conductance_w_k,pulse_w,pulse_s,predicted_delta_c"
    )?;
    for (truth, conductances) in [
        ("contact", [0.05, 0.10, 0.20, 0.50, 1.00]),
        ("no_contact", [0.01, 0.03, 0.05, 0.10, 0.20]),
    ] {
        for conductance in conductances {
            for capacity in [0.03, 0.06, 0.10, 0.30] {
                let delta = 0.25 / conductance * (1.0 - (-conductance * 0.10_f64 / capacity).exp());
                writeln!(
                    pulse,
                    "{truth},{capacity:.3},{conductance:.3},0.25,0.10,{delta:.6}"
                )?;
            }
        }
    }
    for writer in [
        &mut rows,
        &mut summary,
        &mut qualified,
        &mut budget,
        &mut travel,
        &mut dynamics,
        &mut pulse,
    ] {
        writer.flush()?;
    }
    println!("Also 972 bounded fault cases and 40 heat-pulse identifiability cases.");

    println!(
        "Results are hypothesis sweeps.
 Seizure/contamination false positives intentionally remain."
    );
    Ok(())
}
fn main() -> Result<(), Box<dyn Error>> {
    let dir = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "results".to_owned());
    output(Path::new(&dir))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn guide_jam_unloads_the_local_island() {
        let o = scenario(Fault::GuideJamPanRemoved, 0.18, 2.0, 15.0, 0.01);
        assert!(!mechanically_permitted(&o));
        assert!(o.old_plunger_loaded);
    }
    #[test]
    fn island_jam_remains_a_false_positive() {
        let o = scenario(Fault::IslandJamPanRemoved, 0.18, 2.0, 0.0, 0.0);
        assert!(mechanically_permitted(&o) && !o.actual_cap_load);
    }
    #[test]
    fn insulating_debris_is_not_thermal_contact() {
        let o = scenario(Fault::InsulatingDebris, 0.18, 2.0, 0.0, 0.0);
        assert!(mechanically_permitted(&o) && o.actual_cap_load && !o.thermal_contact);
    }
    #[test]
    fn calibrated_budget_has_two_positive_margins() {
        let (on, off) = margins(0.12, 15.0, 0.01);
        assert!((on - 5.833333).abs() < 0.00001 && (off - 3.75).abs() < 0.00001);
    }
    #[test]
    fn unqualified_budget_cannot_separate() {
        let (on, off) = margins(0.12, 45.0, 0.01);
        assert!(on < 0.0 && off < 0.0);
    }
    #[test]
    fn overload_must_not_report_normal_contact() {
        assert!(!mechanically_permitted(&scenario(
            Fault::OverloadStop,
            0.28,
            2.0,
            -15.0,
            0.0
        )));
    }
    #[test]
    fn stale_and_blocked_are_unavailable() {
        for fault in [Fault::SensorStale, Fault::OpticalBlocked] {
            assert!(!mechanically_permitted(&scenario(
                fault, 0.18, 2.0, 0.0, 0.0
            )));
        }
    }
    #[test]
    fn fresh_frozen_sensor_is_not_magically_diagnosed() {
        let o = scenario(Fault::SensorFrozenFresh, 0.18, 2.0, 0.0, 0.0);
        assert!(mechanically_permitted(&o) && !o.actual_cap_load);
    }
    #[test]
    fn preload_and_local_compliance_are_coupled() {
        assert!((series_contact_force(0.10, 0.12, 0.2, 2.0) - 0.127272727).abs() < 1e-8);
    }
    #[test]
    fn small_motion_occurs_before_main_stop_releases() {
        assert!((series_contact_force(0.05, 0.15, 0.2, 2.0) - 0.10).abs() < 1e-12);
    }
}

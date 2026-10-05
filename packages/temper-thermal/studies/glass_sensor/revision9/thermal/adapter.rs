// R9 process sensitivity, appended to the pinned R5/R6/R7 thermal implementation.
// These virtual dimensions do not describe a released CAD assembly or a selected adhesive.
const R9_REFERENCE_BOND_K: f64 = 2.163418635;

fn r9_process_plant(g: &Geometry, case: Case, thickness_mm: f64, bond_k: f64) -> Result<Plant> {
    if !thickness_mm.is_finite() || thickness_mm <= 0. || !bond_k.is_finite() || bond_k <= 0. {
        return Err("bond thickness and conductivity must be finite and positive".into());
    }
    // The inherited model fixes bond k. An equivalent thickness preserves t/k
    // in BOTH half-bond resistances without creating another conduction model.
    let mut equivalent = g.clone();
    let equivalent_mm = thickness_mm * R9_REFERENCE_BOND_K / bond_k;
    let equivalent_volume = g.get("bond_footprint_mm2") * equivalent_mm;
    let actual_capacity = g.get("bond_footprint_mm2") * thickness_mm * 0.002;
    if !equivalent_mm.is_finite()
        || equivalent_mm <= 0.
        || !equivalent_volume.is_finite()
        || equivalent_volume <= 0.
        || !actual_capacity.is_finite()
        || actual_capacity <= 0.
    {
        return Err("bond process overflows or underflows the model representation".into());
    }
    equivalent
        .p
        .insert("bond_thickness_mm".into(), equivalent_mm);
    equivalent
        .p
        .insert("bond_volume_mm3".into(), equivalent_volume);
    let mut plant = r7_candidate(&equivalent, case, 1., 1.)?;
    // Capacity uses physical thickness, never the equivalent resistance length.
    // 2 MJ/m3/K is the inherited proxy, NOT a property of an alternate adhesive.
    plant.net.capacity[case.rings] = actual_capacity;
    Ok(plant)
}

pub fn run_r9() -> Result<()> {
    fs::create_dir_all("results")?;
    let geometries = r7_geometries()?;
    let mut baseline = fs::File::create("results/baseline.csv")?;
    writeln!(baseline, "variant,t90_pan_s,underread200_C")?;
    for g in &geometries {
        let m = score(&r7_candidate(g, Case::default(), 1., 1.)?, 0.01);
        writeln!(baseline, "{},{:.6},{:.6}", g.name, m.pan, m.underread)?;
    }
    baseline.flush()?;
    let mut output = fs::File::create("results/process_sensitivity.csv")?;
    writeln!(output,"source_variant,bond_mm,bond_k_W_mK,bond_volumetric_capacity_J_m3K,pattern,href_W_m2K,contact_G_W_K,t90_own_s,t90_pan_s,underread200_C,finite5C_s_ramp_underread_C,glass_contribution_C,body_contribution_C,geometry_status,physical_result")?;
    for g in geometries.iter().filter(|g| g.name != "M222_thin_0075") {
        for thickness in [0.075, 0.100, 0.127, 0.150, 0.200, 0.254, 0.508] {
            for conductivity in [0.5, 1., R9_REFERENCE_BOND_K, 4.] {
                for (pattern, href) in [
                    (Pattern::Uniform, 2000.),
                    (Pattern::Uniform, 4000.),
                    (Pattern::Rim, 2000.),
                ] {
                    let case = Case {
                        pattern,
                        href,
                        ..Case::default()
                    };
                    let plant = r9_process_plant(g, case, thickness, conductivity)?;
                    let m = score(&plant, 0.01);
                    let glass = 120. * plant.steady(0., 1., 0.)[plant.sensor];
                    let body = 140. * plant.steady(0., 0., 1.)[plant.sensor];
                    if (glass + body - m.underread).abs() > 1e-7 {
                        return Err("boundary contributions do not reproduce steady error".into());
                    }
                    writeln!(output,"{},{thickness},{conductivity},2000000,{pattern:?},{href},{:.9},{:.6},{:.6},{:.6},{:.6},{glass:.6},{body:.6},PARAMETRIC_NOT_CAD_OR_PROCESS_APPROVED,NOT_RUN",g.name,contact(g,case),m.own,m.pan,m.underread,m.ramp_underread)?;
                }
            }
        }
    }
    output.flush()?;
    let mut convergence = fs::File::create("results/convergence.csv")?;
    writeln!(
        convergence,
        "variant,bond_mm,bond_k_W_mK,pattern,rings,wire_cells,dt_s,t90_pan_s,underread200_C"
    )?;
    for g in geometries.iter().filter(|g| g.name != "M222_thin_0075") {
        for (bond, k, pattern) in [(0.075, 4., Pattern::Uniform), (0.508, 0.5, Pattern::Rim)] {
            for (rings, wire_cells, dt) in [(24, 12, 0.01), (48, 24, 0.005)] {
                let case = Case {
                    rings,
                    wire_cells,
                    pattern,
                    ..Case::default()
                };
                let m = score(&r9_process_plant(g, case, bond, k)?, dt);
                writeln!(
                    convergence,
                    "{},{bond},{k},{pattern:?},{rings},{wire_cells},{dt},{:.6},{:.6}",
                    g.name, m.pan, m.underread
                )?;
            }
        }
    }
    convergence.flush()?;
    Ok(())
}

#[cfg(test)]
mod r9_tests {
    use super::*;

    #[test]
    fn reference_process_is_identical_to_every_r7_candidate() {
        for g in r7_geometries().unwrap() {
            let old = r7_candidate(&g, Case::default(), 1., 1.).unwrap();
            let new = r9_process_plant(
                &g,
                Case::default(),
                g.get("bond_thickness_mm"),
                R9_REFERENCE_BOND_K,
            )
            .unwrap();
            assert_eq!(old.net.capacity, new.net.capacity);
            assert_eq!(old.net.k, new.net.k);
        }
    }

    #[test]
    fn equivalent_resistance_keeps_actual_bond_capacity_and_series_resistance() {
        let g = r7_geometries().unwrap().remove(0);
        let case = Case::default();
        let p = r9_process_plant(&g, case, 0.2, 1.).unwrap();
        let area = g.get("rtd_length_mm") * g.get("rtd_width_mm") * 1e-6;
        let expected_sensor_half =
            0.2e-3 / (2. * area) + g.get("film_path_mm") * 1e-3 / (25. * area);
        assert!((-p.net.k[case.rings][p.sensor] - 1. / expected_sensor_half).abs() < 1e-12);
        let cap_to_bond: f64 = (0..case.rings).map(|i| -p.net.k[i][case.rings]).sum();
        let expected_cap_half =
            0.2e-3 / (2. * area) + g.get("disc_thickness_mm") * 1e-3 / (15. * area);
        assert!((cap_to_bond - 1. / expected_cap_half).abs() < 1e-12);
        assert!(
            (p.net.capacity[case.rings] - g.get("bond_footprint_mm2") * 0.2 * 0.002).abs() < 1e-14
        );
    }

    #[test]
    fn invalid_process_values_are_rejected() {
        let g = r7_geometries().unwrap().remove(0);
        for value in [0., -0.1, f64::NAN, f64::INFINITY] {
            assert!(r9_process_plant(&g, Case::default(), value, 1.).is_err());
            assert!(r9_process_plant(&g, Case::default(), 0.1, value).is_err());
        }
    }

    #[test]
    fn unrepresentable_process_values_are_rejected() {
        let g = r7_geometries().unwrap().remove(0);
        assert!(r9_process_plant(&g, Case::default(), f64::MAX, 1.).is_err());
        assert!(r9_process_plant(&g, Case::default(), 1., f64::MIN_POSITIVE).is_err());
    }

    #[test]
    fn boundary_weights_conserve_equilibrium_for_extreme_process_scenarios() {
        for g in r7_geometries().unwrap() {
            for (t, k) in [(0.075, 4.), (0.508, 0.5)] {
                let p = r9_process_plant(&g, Case::default(), t, k).unwrap();
                let sum = p.steady(1., 0., 0.)[p.sensor]
                    + p.steady(0., 1., 0.)[p.sensor]
                    + p.steady(0., 0., 1.)[p.sensor];
                assert!((sum - 1.).abs() < 1e-8);
                assert!(p.net.capacity.iter().all(|v| v.is_finite() && *v > 0.));
            }
        }
    }
}

// Appended inside the pinned R5 module; changes only explicit component terms.
#[derive(Clone, Copy, Debug)]
struct Package {
    name: &'static str,
    length_mm: f64,
    width_mm: f64,
    capacity_height_mm: f64,
    film_path_mm: f64,
    native_diameter_mm: f64,
    native_length_mm: f64,
    bond_mm: f64,
    bracket: &'static str,
}
impl Package {
    fn area(self) -> f64 {
        self.length_mm * self.width_mm
    }
    fn chip_capacity(self) -> f64 {
        self.area() * self.capacity_height_mm * 0.00312
    }
    fn nickel_capacity(self) -> f64 {
        2. * PI * (self.native_diameter_mm / 2.).powi(2) * self.native_length_mm * 0.00395
    }
    fn bond_resistance(self) -> f64 {
        self.bond_mm * 1e-3 / (2.163418635 * self.area() * 1e-6)
    }
}
fn packages() -> Vec<Package> {
    let mut out = Vec::new();
    for bond_mm in [0.075, 0.10, 0.15] {
        for (bracket, height) in [("half_envelope_assumption", 0.45), ("envelope_proxy", 0.9)] {
            out.push(Package {
                name: "M222",
                length_mm: 2.3,
                width_mm: 2.1,
                capacity_height_mm: height,
                film_path_mm: 0.45,
                native_diameter_mm: 0.2,
                native_length_mm: 1.,
                bond_mm,
                bracket,
            });
        }
        for (name, length_mm, width_mm, native_diameter_mm) in [
            ("IST308", 3., 0.8, 0.15),
            ("IST161_GEOMETRY_ONLY", 1.6, 1.2, 0.2),
        ] {
            for (bracket, capacity_height_mm) in [
                ("substrate_only_lower_proxy", 0.25),
                ("envelope_proxy", 0.6),
            ] {
                // Both compare an explicitly assumed 1 mm trimmed native lead, not the shipped length.
                out.push(Package {
                    name,
                    length_mm,
                    width_mm,
                    capacity_height_mm,
                    film_path_mm: 0.125,
                    native_diameter_mm,
                    native_length_mm: 1.,
                    bond_mm,
                    bracket,
                });
            }
        }
    }
    out
}
fn replace_link(net: &mut Network, i: usize, j: usize, conductance: f64) {
    assert!(conductance.is_finite() && conductance >= 0.);
    let old = -net.k[i][j];
    net.k[i][i] += conductance - old;
    net.k[j][j] += conductance - old;
    net.k[i][j] = -conductance;
    net.k[j][i] = -conductance;
}
fn candidate(g: &Geometry, c: Case, pkg: Package) -> Result<Plant> {
    let mut p = build(g, c)?;
    let n = c.rings;
    let area = pkg.area() * 1e-6;
    let sw = weights(n, g.get("head_radius_mm") * 1e-3, 0., (area / PI).sqrt());
    let half_bond = pkg.bond_resistance() / 2.;
    for (i, weight) in sw.iter().enumerate() {
        replace_link(
            &mut p.net,
            i,
            n,
            weight / (half_bond + g.get("disc_thickness_mm") * 1e-3 / (15. * area)),
        );
    }
    replace_link(
        &mut p.net,
        n,
        p.sensor,
        1. / (half_bond + pkg.film_path_mm * 1e-3 / (25. * area)),
    );
    // Preserve the complete R5 overhanging bond pad instead of comparing candidate bare footprint mass.
    p.net.capacity[n] = g.get("bond_footprint_mm2") * pkg.bond_mm * 0.002;
    p.net.capacity[p.sensor] = pkg.chip_capacity() + pkg.nickel_capacity();
    let nickel_r =
        pkg.native_length_mm * 1e-3 / (2. * 90.9 * PI * (pkg.native_diameter_mm * 0.0005).powi(2));
    let hot_cells = (c.wire_cells / 3).max(2);
    let hot_dl =
        (g.get("wire_hot_length_mm") - g.get("wire_anchor_length_mm")) * 1e-3 / hot_cells as f64;
    let (ka, _, _) = wire_properties(g);
    replace_link(
        &mut p.net,
        p.sensor,
        n + 8,
        1. / (nickel_r + hot_dl / (2. * ka)),
    );
    Ok(p)
}
#[derive(Debug)]
struct Score {
    own: f64,
    pan: f64,
    underread: f64,
    ramp_underread: f64,
}
fn score(p: &Plant, dt: f64) -> Score {
    let own_target = 25. + 0.9 * (p.steady(100., 25., 25.)[p.sensor] - 25.);
    let fac = p.net.factor(Some(dt));
    let input = p.forcing(100., 25., 25.);
    let mut t = vec![25.; p.net.capacity.len()];
    let (mut own, mut pan) = (f64::NAN, f64::NAN);
    for i in 1..=(60. / dt) as usize {
        t = advance(&p.net, &fac, &t, &input, dt);
        if own.is_nan() && t[p.sensor] >= own_target {
            own = i as f64 * dt;
        }
        if pan.is_nan() && t[p.sensor] >= 92.5 {
            pan = i as f64 * dt;
        }
        if own.is_finite() && pan.is_finite() {
            break;
        }
    }
    let underread = 200. - p.steady(200., 80., 60.)[p.sensor];
    t.fill(25.);
    for i in 1..=(35. / dt) as usize {
        t = advance(
            &p.net,
            &fac,
            &t,
            &p.forcing(25. + i as f64 * dt * 5., 25., 25.),
            dt,
        );
    }
    Score {
        own,
        pan,
        underread,
        ramp_underread: 200. - t[p.sensor],
    }
}
fn d6() -> Result<Geometry> {
    geometries()?
        .into_iter()
        .find(|g| g.name == "D6")
        .ok_or_else(|| "D6 missing".into())
}
pub fn run_r6() -> Result<()> {
    let g = d6()?;
    fs::create_dir_all("results")?;
    let mut f = fs::File::create("results/comparison.csv")?;
    writeln!(f,"package,capacity_bracket,bond_mm,native_length_mm,pattern,environment,href_W_m2K,contact_G_W_K,bond_R_K_W,chip_C_J_K,native_C_J_K,t90_own_s,t90_pan_s,underread200_C,finite5C_s_ramp_underread_at200_C,geometry_status,physical_result")?;
    for pattern in [Pattern::Uniform, Pattern::Center, Pattern::Rim] {
        for (environment, wire_h, loss, seal) in [
            ("nominal", 5., 0.0002, 0.0002),
            ("high_loss", 15., 0.0005, 0.001),
        ] {
            for href in [1000., 2000., 4000.] {
                let case = Case {
                    pattern,
                    wire_h,
                    loss,
                    seal,
                    href,
                    ..Case::default()
                };
                for pkg in packages() {
                    let result = score(&candidate(&g, case, pkg)?, 0.01);
                    writeln!(f,"{},{},{},{},{pattern:?},{environment},{href},{:.9},{:.9},{:.9},{:.9},{:.4},{:.4},{:.6},{:.6},PARAMETRIC_NOT_CAD_RELEASED,NOT_RUN", pkg.name,pkg.bracket,pkg.bond_mm,pkg.native_length_mm,contact(&g,case),pkg.bond_resistance(),pkg.chip_capacity(),pkg.nickel_capacity(),result.own,result.pan,result.underread,result.ramp_underread)?;
                }
            }
        }
    }
    let mut f = fs::File::create("results/baseline.csv")?;
    let result = score(&build(&g, Case::default())?, 0.01);
    writeln!(f,"head,t90_own_s,t90_pan_s,underread200_C,finite5C_s_ramp_underread_at200_C,geometry_status,physical_result")?;
    writeln!(
        f,
        "D6,{:.4},{:.4},{:.6},{:.6},FROZEN_R5_CAD,NOT_RUN",
        result.own, result.pan, result.underread, result.ramp_underread
    )?;
    let mut f = fs::File::create("results/convergence.csv")?;
    writeln!(
        f,
        "package,pattern,rings,wire_cells,dt_s,t90_pan_s,underread200_C"
    )?;
    for name in ["M222", "IST308", "IST161_GEOMETRY_ONLY"] {
        let pkg = packages()
            .into_iter()
            .find(|x| x.name == name && x.bond_mm == 0.1 && x.bracket == "envelope_proxy")
            .ok_or("package missing")?;
        for pattern in [Pattern::Uniform, Pattern::Rim] {
            for (rings, wire_cells, dt) in [(24, 12, 0.01), (48, 24, 0.005)] {
                let c = Case {
                    rings,
                    wire_cells,
                    pattern,
                    ..Case::default()
                };
                let result = score(&candidate(&g, c, pkg)?, dt);
                writeln!(
                    f,
                    "{name},{pattern:?},{rings},{wire_cells},{dt},{:.6},{:.6}",
                    result.pan, result.underread
                )?;
            }
        }
    }
    let mut f = fs::File::create("results/native_lead_sensitivity.csv")?;
    writeln!(f,"package,native_length_mm,capacity_bracket,bond_mm,native_C_J_K,t90_pan_s,underread200_C,geometry_status,physical_result")?;
    for name in ["M222", "IST308", "IST161_GEOMETRY_ONLY"] {
        let base = packages()
            .into_iter()
            .find(|p| p.name == name && p.bond_mm == 0.1 && p.bracket == "envelope_proxy")
            .ok_or("package missing")?;
        for native_length_mm in [1., 3., 7.] {
            let pkg = Package {
                native_length_mm,
                ..base
            };
            let m = score(&candidate(&g, Case::default(), pkg)?, 0.01);
            writeln!(f,"{name},{native_length_mm},{},{},{:.9},{:.4},{:.6},PARAMETRIC_NOT_CAD_RELEASED,NOT_RUN",pkg.bracket,pkg.bond_mm,pkg.nickel_capacity(),m.pan,m.underread)?;
        }
    }
    let mut f = fs::File::create("results/film_path_sensitivity.csv")?;
    writeln!(f,"package,film_path_mm,capacity_bracket,bond_mm,t90_pan_s,underread200_C,geometry_status,physical_result")?;
    for name in ["M222", "IST308", "IST161_GEOMETRY_ONLY"] {
        let base = packages()
            .into_iter()
            .find(|p| p.name == name && p.bond_mm == 0.1 && p.bracket == "envelope_proxy")
            .ok_or("package missing")?;
        let paths: &[f64] = if name == "M222" {
            &[0.45, 0.9]
        } else {
            &[0.125, 0.25, 0.6]
        };
        for &film_path_mm in paths {
            let pkg = Package {
                film_path_mm,
                ..base
            };
            let m = score(&candidate(&g, Case::default(), pkg)?, 0.01);
            writeln!(
                f,
                "{name},{film_path_mm},{},{},{:.4},{:.6},PARAMETRIC_NOT_CAD_RELEASED,NOT_RUN",
                pkg.bracket, pkg.bond_mm, m.pan, m.underread
            )?;
        }
    }
    Ok(())
}
#[cfg(test)]
mod r6_tests {
    use super::*;
    fn base_pkg() -> Package {
        packages()
            .into_iter()
            .find(|p| p.name == "M222" && p.bond_mm == 0.1 && p.bracket == "envelope_proxy")
            .unwrap()
    }
    #[test]
    fn no_change_adapter_preserves_every_network_coefficient() {
        let g = d6().unwrap();
        let c = Case::default();
        let a = build(&g, c).unwrap();
        let b = candidate(&g, c, base_pkg()).unwrap();
        let worst = a
            .net
            .k
            .iter()
            .flatten()
            .zip(b.net.k.iter().flatten())
            .map(|(x, y)| (x - y).abs())
            .fold(0., f64::max);
        assert!(worst < 1e-14, "coefficient error {worst}");
        assert!(a
            .net
            .capacity
            .iter()
            .zip(&b.net.capacity)
            .all(|(x, y)| (x - y).abs() < 1e-14));
    }
    #[test]
    fn baseline_reproduces_r5_pan_response_and_bias() {
        let m = score(
            &candidate(&d6().unwrap(), Case::default(), base_pkg()).unwrap(),
            0.01,
        );
        assert!(
            (m.pan - 2.94).abs() < 1e-9 && (m.underread - 2.474231).abs() < 0.000001,
            "{m:?}"
        );
    }
    #[test]
    fn bond_resistance_matches_si_slab_formula() {
        for p in packages() {
            assert!(
                (p.bond_resistance()
                    - p.bond_mm / (2.163418635 * p.length_mm * p.width_mm) * 1000.)
                    .abs()
                    < 1e-12
            );
        }
    }
    #[test]
    fn smaller_area_increases_bond_resistance() {
        let m = base_pkg();
        let i = packages()
            .into_iter()
            .find(|p| p.name == "IST308" && p.bond_mm == 0.1)
            .unwrap();
        assert!((i.bond_resistance() / m.bond_resistance() - 4.83 / 2.4).abs() < 1e-12);
    }
    #[test]
    fn capacity_brackets_bound_all_candidate_material_proxy_volumes() {
        for p in packages() {
            assert!(p.chip_capacity() > 0. && p.chip_capacity() <= p.area() * 0.9 * 0.00312);
        }
    }
    #[test]
    fn unchanged_support_cover_and_complete_wire_capacities_are_retained() {
        let g = d6().unwrap();
        let c = Case::default();
        let a = build(&g, c).unwrap();
        for pkg in packages() {
            let b = candidate(&g, c, pkg).unwrap();
            for (i, cap) in a.net.capacity.iter().enumerate() {
                if i != c.rings && i != a.sensor {
                    assert_eq!(*cap, b.net.capacity[i]);
                }
            }
        }
    }
    #[test]
    fn all_equal_boundaries_preserved_for_each_package() {
        for pkg in packages() {
            let p = candidate(&d6().unwrap(), Case::default(), pkg).unwrap();
            assert!(p
                .steady(200., 200., 200.)
                .iter()
                .all(|t| (t - 200.).abs() < 1e-7));
        }
    }
    #[test]
    fn thinner_bond_reduces_step_delay_without_changing_external_contact() {
        let g = d6().unwrap();
        let c = Case::default();
        let pkg = base_pkg();
        let thin = score(
            &candidate(
                &g,
                c,
                Package {
                    bond_mm: 0.075,
                    ..pkg
                },
            )
            .unwrap(),
            0.01,
        );
        let thick = score(
            &candidate(
                &g,
                c,
                Package {
                    bond_mm: 0.15,
                    ..pkg
                },
            )
            .unwrap(),
            0.01,
        );
        assert!(thin.pan < thick.pan, "thin{thin:?} thick{thick:?}");
    }
    #[test]
    fn candidate_spatial_and_temporal_refinement_stays_within_screening_resolution() {
        let g = d6().unwrap();
        for name in ["M222", "IST308", "IST161_GEOMETRY_ONLY"] {
            let pkg = packages()
                .into_iter()
                .find(|p| p.name == name && p.bond_mm == 0.1 && p.bracket == "envelope_proxy")
                .unwrap();
            for pattern in [Pattern::Uniform, Pattern::Rim] {
                let a = score(
                    &candidate(
                        &g,
                        Case {
                            pattern,
                            ..Case::default()
                        },
                        pkg,
                    )
                    .unwrap(),
                    0.01,
                );
                let b = score(
                    &candidate(
                        &g,
                        Case {
                            pattern,
                            rings: 48,
                            wire_cells: 24,
                            ..Case::default()
                        },
                        pkg,
                    )
                    .unwrap(),
                    0.005,
                );
                assert!(
                    (a.pan - b.pan).abs() < 0.11 && (a.underread - b.underread).abs() < 0.06,
                    "{name} {pattern:?} {a:?} {b:?}"
                );
            }
        }
    }
}

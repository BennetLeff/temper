// Appended after pinned R5 and R6 sources: geometry comes from R7 STEP solids.
fn r7_geometries_from(text: &str) -> Result<Vec<Geometry>> {
    let baseline = d6()?;
    let mut lines = text.lines();
    let keys: Vec<_> = lines
        .next()
        .ok_or("empty R7 geometry")?
        .split(',')
        .collect();
    if keys.first() != Some(&"variant") {
        return Err("R7 first column must be variant".into());
    }
    let mut seen = std::collections::BTreeSet::new();
    if keys.iter().any(|k| !seen.insert(*k)) {
        return Err("duplicate R7 geometry column".into());
    }
    for key in baseline.p.keys().map(String::as_str).chain([
        "rtd_length_mm",
        "rtd_width_mm",
        "rtd_height_mm",
        "rtd_volume_mm3",
        "rtd_substrate_height_mm",
        "rtd_max_length_mm",
        "rtd_max_width_mm",
        "rtd_max_height_mm",
        "rtd_max_envelope_volume_mm3",
        "native_lead_installation",
        "film_orientation",
        "package_part",
        "geometry_status",
        "physical_result",
        "contract_pose",
        "film_path_mm",
        "native_nickel_diameter_mm",
        "native_lead_volume_mm3",
    ]) {
        if !keys.contains(&key) {
            return Err(format!("R7 missing geometry field {key}").into());
        }
    }
    let mut rows = Vec::new();
    for line in lines {
        let fields: Vec<_> = line.split(',').collect();
        if fields.len() != keys.len() {
            return Err("R7 geometry row width differs".into());
        }
        let mut p = BTreeMap::new();
        for (key, value) in keys.iter().zip(&fields).skip(1) {
            if [
                "native_lead_installation",
                "film_orientation",
                "package_part",
                "geometry_status",
                "physical_result",
                "contract_pose",
            ]
            .contains(key)
            {
                if value.is_empty()
                    || (*key == "physical_result" && *value != "NOT_RUN")
                    || (*key == "geometry_status"
                        && *value != "EXPERIMENTAL_CAD_NOT_PRODUCTION_RELEASE")
                    || (*key == "contract_pose" && *value != "rest")
                {
                    return Err(format!("invalid R7 metadata {key}").into());
                }
                continue;
            }
            let value: f64 = value.parse()?;
            if !value.is_finite() || value < 0. {
                return Err(format!("invalid R7 geometry {key}").into());
            }
            p.insert((*key).to_string(), value);
        }
        for key in [
            "rtd_length_mm",
            "rtd_width_mm",
            "rtd_height_mm",
            "rtd_volume_mm3",
            "rtd_substrate_height_mm",
            "film_path_mm",
            "native_nickel_diameter_mm",
            "native_lead_volume_mm3",
            "bond_volume_mm3",
            "bond_thickness_mm",
            "wire_hot_length_mm",
        ] {
            if p[key] <= 0. {
                return Err(format!("nonpositive R7 geometry {key}").into());
            }
        }
        if (p["wire_hot_length_mm"] + p["wire_cold_length_mm"] - 60.).abs() > 1e-5
            || p["wire_hot_length_mm"] <= p["wire_anchor_length_mm"]
            || p["wire_outer_diameter_mm"] <= p["wire_copper_diameter_mm"]
            || p["cover_outer_radius_mm"] > p["head_radius_mm"]
            || p["cover_outer_radius_mm"] <= p["cover_inner_radius_mm"]
            || p["rtd_length_mm"] * p["rtd_width_mm"] > p["bond_footprint_mm2"]
            || p["film_path_mm"] > p["rtd_height_mm"]
            || p["rtd_substrate_height_mm"] <= 0.
            || p["rtd_substrate_height_mm"] > p["rtd_height_mm"]
            || p["cap_volume_mm3"] <= p["disc_volume_mm3"] + p["hook_volume_mm3"]
        {
            return Err("invalid R7 geometry relation".into());
        }
        let g = Geometry {
            name: fields[0].to_string(),
            p,
        };
        let max_slab =
            g.get("rtd_max_length_mm") * g.get("rtd_max_width_mm") * g.get("rtd_max_height_mm");
        if (g.get("rtd_max_envelope_volume_mm3") - max_slab).abs() > 1e-6
            || g.get("rtd_max_envelope_volume_mm3") < g.get("rtd_volume_mm3")
            || g.get("rtd_max_height_mm") < g.get("rtd_height_mm")
        {
            return Err("R7 maximum package envelope inconsistent".into());
        }
        let slab = g.get("rtd_length_mm") * g.get("rtd_width_mm") * g.get("rtd_height_mm");
        if (g.get("rtd_volume_mm3") - slab).abs() > 1e-6 {
            return Err("R7 package envelope volume inconsistent".into());
        }
        let nickel = 2.
            * PI
            * (g.get("native_nickel_diameter_mm") / 2.).powi(2)
            * g.get("native_nickel_length_mm");
        if (g.get("native_lead_volume_mm3") - nickel).abs() > 1e-6 {
            return Err("R7 native lead volume inconsistent".into());
        }
        if (g.get("bond_volume_mm3") - g.get("bond_footprint_mm2") * g.get("bond_thickness_mm"))
            .abs()
            > 1e-6
        {
            return Err("R7 bond volume inconsistent".into());
        }
        rows.push(g);
    }
    let names: std::collections::BTreeSet<_> = rows.iter().map(|g| g.name.as_str()).collect();
    let expected = std::collections::BTreeSet::from([
        "M222_control_010",
        "M222_thin_0075",
        "IST308_thin_0075",
    ]);
    if names != expected || rows.len() != 3 {
        return Err("R7 expected three unique coupon variants".into());
    }
    Ok(rows)
}
fn r7_geometries() -> Result<Vec<Geometry>> {
    r7_geometries_from(&fs::read_to_string(
        "../mechanical/r7_thermal_geometry.csv",
    )?)
}
fn r7_package(g: &Geometry, film_factor: f64) -> Package {
    Package {
        name: if g.name.starts_with("M222") {
            "M222"
        } else {
            "IST308"
        },
        length_mm: g.get("rtd_length_mm"),
        width_mm: g.get("rtd_width_mm"),
        capacity_height_mm: g.get("rtd_height_mm"),
        film_path_mm: g.get("film_path_mm") * film_factor,
        native_diameter_mm: g.get("native_nickel_diameter_mm"),
        native_length_mm: g.get("native_nickel_length_mm"),
        bond_mm: g.get("bond_thickness_mm"),
        bracket: "CAD_envelope_proxy",
    }
}
fn r7_candidate(g: &Geometry, c: Case, chip_cp_factor: f64, film_factor: f64) -> Result<Plant> {
    if !chip_cp_factor.is_finite()
        || chip_cp_factor <= 0.
        || !film_factor.is_finite()
        || film_factor <= 0.
    {
        return Err("invalid R7 material/path factor".into());
    }
    let mut p = candidate(g, c, r7_package(g, film_factor))?;
    p.net.capacity[c.rings] = g.get("bond_volume_mm3") * 0.002;
    p.net.capacity[p.sensor] = g.get("rtd_volume_mm3") * 0.00312 * chip_cp_factor
        + g.get("native_lead_volume_mm3") * 0.00395;
    Ok(p)
}
fn r7_group(i: usize, c: Case) -> &'static str {
    let n = c.rings;
    if i < n {
        return "cap_face_and_anchor_bond";
    }
    match i - n {
        0 => "sensor_bond",
        1 => "rtd_envelope_and_native_leads",
        2 => "support_clamp_and_witness",
        3 => "cap_periphery_excluding_hooks",
        4 => "extension_wire_anchor",
        5 => "join_covers_and_attachment_bond",
        6 => "seal_capacity_hypothesis",
        7 => "retention_hooks",
        _ => "extension_wires_and_welds",
    }
}
pub fn run_r7() -> Result<()> {
    let geometries = r7_geometries()?;
    fs::create_dir_all("results")?;
    let mut f = fs::File::create("results/comparison.csv")?;
    writeln!(f,"variant,pattern,environment,href_W_m2K,chip_capacity_factor,film_path_factor,contact_G_W_K,t90_own_s,t90_pan_s,underread200_C,finite5C_s_ramp_underread_at200_C,geometry_status,physical_result")?;
    for g in &geometries {
        for pattern in [Pattern::Uniform, Pattern::Center, Pattern::Rim] {
            for (environment, wire_h, loss, seal) in [
                ("nominal", 5., 0.0002, 0.0002),
                ("high_loss", 15., 0.0005, 0.001),
            ] {
                for href in [1000., 2000., 4000.] {
                    let c = Case {
                        pattern,
                        wire_h,
                        loss,
                        seal,
                        href,
                        ..Case::default()
                    };
                    let m = score(&r7_candidate(g, c, 1., 1.)?, 0.01);
                    writeln!(f,"{},{pattern:?},{environment},{href},1,1,{:.9},{:.4},{:.4},{:.6},{:.6},R7_CAD_COUPLED_ENVELOPE_PROXY,NOT_RUN",g.name,contact(g,c),m.own,m.pan,m.underread,m.ramp_underread)?;
                }
            }
        }
    }
    f.flush()?;
    let mut f = fs::File::create("results/uncertainty.csv")?;
    writeln!(f,"variant,chip_capacity_factor,film_path_factor,film_path_mm,t90_own_s,t90_pan_s,underread200_C,finite5C_s_ramp_underread_at200_C")?;
    for g in &geometries {
        let lower_cp = if g.name.starts_with("IST308") {
            g.get("rtd_substrate_height_mm") / g.get("rtd_height_mm")
        } else {
            0.5
        };
        let max_film = g.get("rtd_max_height_mm") / g.get("film_path_mm");
        let max_capacity = g.get("rtd_max_envelope_volume_mm3") / g.get("rtd_volume_mm3");
        for cp in [lower_cp, 1., max_capacity] {
            for film in [0.5, 1., max_film] {
                let m = score(&r7_candidate(g, Case::default(), cp, film)?, 0.01);
                writeln!(
                    f,
                    "{},{cp},{film},{:.6},{:.4},{:.4},{:.6},{:.6}",
                    g.name,
                    g.get("film_path_mm") * film,
                    m.own,
                    m.pan,
                    m.underread,
                    m.ramp_underread
                )?;
            }
        }
    }
    f.flush()?;
    let mut f = fs::File::create("results/capacity_ledger.csv")?;
    writeln!(f, "variant,component_group,capacity_J_K,source")?;
    for g in &geometries {
        let c = Case::default();
        let p = r7_candidate(g, c, 1., 1.)?;
        let mut groups = BTreeMap::<&str, f64>::new();
        for (i, cap) in p.net.capacity.iter().enumerate() {
            *groups.entry(r7_group(i, c)).or_default() += cap;
        }
        for (name, cap) in &groups {
            writeln!(
                f,
                "{},{name},{cap:.12},{}",
                g.name,
                if *name == "seal_capacity_hypothesis" {
                    "R5_unqualified_seal_assumption"
                } else {
                    "CAD_volume_or_length_with_material_proxy"
                }
            )?;
        }
        writeln!(
            f,
            "{},TOTAL,{:.12},network_sum",
            g.name,
            groups.values().sum::<f64>()
        )?;
    }
    f.flush()?;
    let mut f = fs::File::create("results/convergence.csv")?;
    writeln!(
        f,
        "variant,pattern,rings,wire_cells,dt_s,t90_pan_s,underread200_C"
    )?;
    for g in &geometries {
        for pattern in [Pattern::Uniform, Pattern::Rim] {
            for (rings, wire_cells, dt) in [(24, 12, 0.01), (48, 24, 0.005)] {
                let c = Case {
                    rings,
                    wire_cells,
                    pattern,
                    ..Case::default()
                };
                let m = score(&r7_candidate(g, c, 1., 1.)?, dt);
                writeln!(
                    f,
                    "{},{pattern:?},{rings},{wire_cells},{dt},{:.6},{:.6}",
                    g.name, m.pan, m.underread
                )?;
            }
        }
    }
    f.flush()?;
    let mut f = fs::File::create("results/baseline.csv")?;
    writeln!(
        f,
        "geometry,t90_own_s,t90_pan_s,underread200_C,finite5C_s_ramp_underread_at200_C"
    )?;
    let m = score(&build(&d6()?, Case::default())?, 0.01);
    writeln!(
        f,
        "R5_D6,{:.4},{:.4},{:.6},{:.6}",
        m.own, m.pan, m.underread, m.ramp_underread
    )?;
    f.flush()?;
    Ok(())
}
#[cfg(test)]
mod r7_tests {
    use super::*;
    #[test]
    fn clearance_corrected_control_maps_changed_mass_and_preserves_cap_contact() {
        let g = r7_geometries()
            .unwrap()
            .into_iter()
            .find(|g| g.name == "M222_control_010")
            .unwrap();
        let c = Case::default();
        let actual = r7_candidate(&g, c, 1., 1.).unwrap();
        let old_g = d6().unwrap();
        let baseline = build(&old_g, c).unwrap();
        // This revision deliberately relieves the covers to fit the maximum package.
        assert!((g.get("cover_volume_mm3") - old_g.get("cover_volume_mm3")).abs() > 1e-6);
        let n = c.rings;
        let cover_expected =
            g.get("cover_volume_mm3") * 0.0028 + g.get("cover_bond_volume_mm3") * 0.002;
        assert!((actual.net.capacity[n + 5] - cover_expected).abs() < 1e-12);
        let face_expected =
            g.get("disc_volume_mm3") * 0.004 + g.get("anchor_pad_volume_mm3") * 0.002;
        assert!((actual.net.capacity[..n].iter().sum::<f64>() - face_expected).abs() < 1e-12);
        let attach_g = 1.
            / (1. / c.cover_g
                + g.get("cover_bond_thickness_mm") * 1e-3
                    / (2.163418635 * g.get("cover_bond_area_mm2") * 1e-6));
        let cover_weights = weights(
            n,
            g.get("head_radius_mm") * 1e-3,
            g.get("cover_inner_radius_mm") * 1e-3,
            g.get("cover_outer_radius_mm") * 1e-3,
        );
        for (i, w) in cover_weights.iter().enumerate() {
            assert!((-actual.net.k[i][n + 5] - w * attach_g).abs() < 1e-12);
        }
        for i in 0..n - 1 {
            assert_eq!(actual.net.k[i][i + 1], baseline.net.k[i][i + 1]);
        }
        assert_eq!(actual.pan, baseline.pan);
        assert_eq!(&actual.glass[..n], &baseline.glass[..n]);
        assert_eq!(&actual.body[..n], &baseline.body[..n]);
    }
    #[test]
    fn matched_m222_pair_changes_only_bond_thermal_terms() {
        let rows = r7_geometries().unwrap();
        let control = rows.iter().find(|g| g.name == "M222_control_010").unwrap();
        let thin = rows.iter().find(|g| g.name == "M222_thin_0075").unwrap();
        let c = Case::default();
        let a = r7_candidate(control, c, 1., 1.).unwrap();
        let b = r7_candidate(thin, c, 1., 1.).unwrap();
        for (i, (left, right)) in a.net.capacity.iter().zip(&b.net.capacity).enumerate() {
            if i != c.rings {
                assert!(
                    (left - right).abs() < 1e-10,
                    "non-bond capacity changed at {i}"
                );
            }
        }
        for i in 0..a.net.capacity.len() {
            for j in 0..i {
                if i != c.rings && j != c.rings {
                    assert!(
                        (a.net.k[i][j] - b.net.k[i][j]).abs() < 1e-10,
                        "non-bond link changed at {i},{j}"
                    );
                }
            }
        }
        assert!(b.net.capacity[c.rings] < a.net.capacity[c.rings]);
        assert_eq!(a.pan, b.pan);
    }
    #[test]
    fn cad_rows_are_complete_and_three_unique_candidates() {
        assert_eq!(r7_geometries().unwrap().len(), 3);
    }
    #[test]
    fn rejects_nonfinite_and_duplicate_geometry_columns() {
        let text = fs::read_to_string("../mechanical/r7_thermal_geometry.csv").unwrap();
        assert!(r7_geometries_from(&text.replacen("head_radius_mm", "variant", 1)).is_err());
        assert!(r7_geometries_from(&text.replacen("NOT_RUN", "PASS", 1)).is_err());
        let mut lines = text.lines();
        let header = lines.next().unwrap();
        let mut row: Vec<_> = lines.next().unwrap().split(',').collect();
        row[1] = "NaN";
        let malformed = format!(
            "{header}\n{}\n{}",
            row.join(","),
            lines.collect::<Vec<_>>().join("\n")
        );
        assert!(r7_geometries_from(&malformed).is_err());
    }
    #[test]
    fn volume_ledger_consumes_cad_mass_without_omitting_chip_or_native_leads() {
        for g in r7_geometries().unwrap() {
            let p = r7_candidate(&g, Case::default(), 1., 1.).unwrap();
            assert!(
                (p.net.capacity[p.sensor]
                    - (g.get("rtd_volume_mm3") * 0.00312
                        + g.get("native_lead_volume_mm3") * 0.00395))
                    .abs()
                    < 1e-14
            );
            assert!((p.net.capacity[24] - g.get("bond_volume_mm3") * 0.002).abs() < 1e-14);
            assert!(p.net.capacity.iter().all(|x| x.is_finite() && *x > 0.));
        }
    }
    #[test]
    fn shared_temperature_is_an_equilibrium_for_every_candidate() {
        for g in r7_geometries().unwrap() {
            let p = r7_candidate(&g, Case::default(), 1., 1.).unwrap();
            assert!(p
                .steady(200., 200., 200.)
                .iter()
                .all(|t| (*t - 200.).abs() < 1e-7));
        }
    }
    #[test]
    fn envelope_capacity_does_not_change_steady_solution() {
        for g in r7_geometries().unwrap() {
            let a = r7_candidate(&g, Case::default(), 0.5, 1.).unwrap();
            let b = r7_candidate(&g, Case::default(), 1.25, 1.).unwrap();
            assert_eq!(a.steady(200., 80., 60.), b.steady(200., 80., 60.));
        }
    }
    #[test]
    fn spatial_and_temporal_refinement_is_bounded() {
        for g in r7_geometries().unwrap() {
            for pattern in [Pattern::Uniform, Pattern::Rim] {
                let a = score(
                    &r7_candidate(
                        &g,
                        Case {
                            pattern,
                            ..Case::default()
                        },
                        1.,
                        1.,
                    )
                    .unwrap(),
                    0.01,
                );
                let b = score(
                    &r7_candidate(
                        &g,
                        Case {
                            pattern,
                            rings: 48,
                            wire_cells: 24,
                            ..Case::default()
                        },
                        1.,
                        1.,
                    )
                    .unwrap(),
                    0.005,
                );
                assert!(
                    (a.pan - b.pan).abs() < 0.12 && (a.underread - b.underread).abs() < 0.07,
                    "{} {pattern:?}: {a:?} {b:?}",
                    g.name
                );
            }
        }
    }
}

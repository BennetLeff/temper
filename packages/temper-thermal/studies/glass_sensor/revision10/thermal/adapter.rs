// C9 conductance-only sensitivity appended to the pinned R5/R6/R7/R9 network.
// A rest-position clearance means the new island-to-bracket leg is OPEN.
// Engaged cases are hypothetical cold-carrier sinks, not C9 predictions.

const C9_ISLAND_CONTACT_MM2: f64 = 0.594_658_637_955_58;
const C9_HEAD_CONTACT_MM2: f64 = 4.523_893_421_169_301;
const C9_NUT_CONTACT_MM2: f64 = 6.323_410;
const C9_UPRIGHT_SECTION_MM2: f64 = 0.5 * 0.8;
const C9_FOOT_SECTION_MM2: f64 = 3.4 * 0.3;
const C9_ISLAND_CONTACT_RADIUS_MM: f64 = 3.621_685_668_387_881;
const C9_FOOT_ROOT_RADIUS_MM: f64 = 4.05;
const C9_SCREW_RADIUS_MM: f64 = 7.1;
const C9_VERTICAL_OFFSET_MM: f64 = 1.72;
const C9_SHAFT_SECTION_MM2: f64 = std::f64::consts::PI * 0.8 * 0.8;
const C9_SHAFT_LENGTH_MM: f64 = 1.3;
const C9_BRACKETS: f64 = 3.;

// This straight line to the inner foot root is a lower bound on the bent path.
// The inherited upright section is 0.5 x 0.8 mm; local bends and constrictions
// remain outside this uniform-bar approximation.
fn c9_common_metal_length_mm() -> f64 {
    ((C9_FOOT_ROOT_RADIUS_MM - C9_ISLAND_CONTACT_RADIUS_MM).powi(2) + C9_VERTICAL_OFFSET_MM.powi(2))
        .sqrt()
}

fn c9_effective_sink_g(
    engaged: bool,
    interface_h_w_m2k: f64,
    metal_k_w_mk: f64,
    carrier_to_reservoir_g_w_k: f64,
    foot_to_carrier_g_w_k: f64,
) -> Result<f64> {
    if !engaged {
        return Ok(0.);
    }
    if interface_h_w_m2k.is_nan()
        || interface_h_w_m2k <= 0.
        || metal_k_w_mk.is_nan()
        || !metal_k_w_mk.is_finite()
        || metal_k_w_mk <= 0.
        || carrier_to_reservoir_g_w_k.is_nan()
        || carrier_to_reservoir_g_w_k <= 0.
        || !foot_to_carrier_g_w_k.is_finite()
        || foot_to_carrier_g_w_k < 0.
    {
        return Err(
            "C9 thermal assumptions must be positive and finite or +infinity for ideal contact"
                .into(),
        );
    }
    let contact_r = |area_mm2: f64| {
        if interface_h_w_m2k.is_infinite() {
            0.
        } else {
            1. / (interface_h_w_m2k * area_mm2 * 1e-6)
        }
    };
    let screw_r = (C9_SCREW_RADIUS_MM - C9_FOOT_ROOT_RADIUS_MM) * 1e-3
        / (metal_k_w_mk * C9_FOOT_SECTION_MM2 * 1e-6)
        + contact_r(C9_HEAD_CONTACT_MM2)
        + C9_SHAFT_LENGTH_MM * 1e-3 / (metal_k_w_mk * C9_SHAFT_SECTION_MM2 * 1e-6)
        + contact_r(C9_NUT_CONTACT_MM2);
    // The foot can also touch the carrier directly. Its effective contact is
    // independent because the CAD audit did not measure that thermal joint.
    let one_leg_r = contact_r(C9_ISLAND_CONTACT_MM2)
        + c9_common_metal_length_mm() * 1e-3 / (metal_k_w_mk * C9_UPRIGHT_SECTION_MM2 * 1e-6)
        + 1. / (1. / screw_r + foot_to_carrier_g_w_k);
    let carrier_r = if carrier_to_reservoir_g_w_k.is_infinite() {
        0.
    } else {
        1. / carrier_to_reservoir_g_w_k
    };
    let total = 1. / (one_leg_r / C9_BRACKETS + carrier_r);
    if !total.is_finite() || total <= 0. {
        return Err("unrepresentable C9 conductance".into());
    }
    Ok(total)
}

fn c9_plant(g: &Geometry, case: Case, added_sink_g: f64) -> Result<Plant> {
    if !added_sink_g.is_finite() || added_sink_g < 0. {
        return Err("invalid added C9 sink".into());
    }
    let mut p = r7_candidate(g, case, 1., 1.)?;
    let island = case.rings + 2;
    p.net.boundary(island, added_sink_g);
    p.body[island] += added_sink_g;
    Ok(p)
}

pub fn run_c9() -> Result<()> {
    fs::create_dir_all("results")?;
    let geometry = r7_geometries()?
        .into_iter()
        .find(|g| g.name == "M222_control_010")
        .ok_or("M222 control missing")?;
    let case = Case::default();
    let mut out = fs::File::create("results/c9_conductance_sensitivity.csv")?;
    writeln!(out, "pose,interface_h_W_m2K,metal_k_W_mK,carrier_to_reservoir_G_W_K,foot_to_carrier_G_per_bracket_W_K,added_island_to_reservoir_G_W_K,t90_pan_s_fixed_R7_capacity,reservoir_to_sensor_steady_weight,underread200_C_if_reservoir60,underread200_C_if_reservoir120,underread200_C_if_reservoir200,physical_result")?;
    let scenarios = std::iter::once(("rest_open", 0., 15., 0., 0.))
        .chain([1e3, 1e4, 1e5, f64::INFINITY].into_iter().flat_map(|h| {
            [1e-3, 1e-2].into_iter().flat_map(move |carrier| {
                [0., 1e-3, 1e-2]
                    .into_iter()
                    .map(move |foot| ("engaged", h, 15., carrier, foot))
            })
        }))
        .chain(
            [5., 30.]
                .into_iter()
                .map(|k| ("engaged", 1e4, k, 1e-2, 1e-3)),
        );
    for (pose, h, k, carrier, foot) in scenarios {
        let added = c9_effective_sink_g(pose == "engaged", h, k, carrier, foot)?;
        let plant = c9_plant(&geometry, case, added)?;
        let result = score(&plant, 0.01);
        let mut reservoir_rhs = vec![0.; plant.net.capacity.len()];
        reservoir_rhs[case.rings + 2] = added;
        let reservoir_weight = plant.net.factor(None).solve(&reservoir_rhs)[plant.sensor];
        let warm120 = result.underread - 60. * reservoir_weight;
        let hot200 = result.underread - 140. * reservoir_weight;
        if !reservoir_weight.is_finite() || !(0. ..=1.).contains(&reservoir_weight) {
            return Err("invalid C9 reservoir temperature weight".into());
        }
        writeln!(
            out,
            "{pose},{h},{k},{carrier},{foot},{added:.9},{:.4},{reservoir_weight:.9},{:.6},{warm120:.6},{hot200:.6},NOT_RUN",
            result.pan, result.underread
        )?;
    }
    out.flush()?;
    Ok(())
}

#[cfg(test)]
mod c9_tests {
    use super::*;

    #[test]
    fn rest_gap_adds_no_metal_sink_and_preserves_full_r7_matrix() {
        let g = r7_geometries().unwrap().remove(0);
        let c = Case::default();
        let original = r7_candidate(&g, c, 1., 1.).unwrap();
        let open = c9_plant(
            &g,
            c,
            c9_effective_sink_g(false, 1e4, 15., 1e-2, 1e-3).unwrap(),
        )
        .unwrap();
        assert_eq!(original.net.k, open.net.k);
        assert_eq!(original.net.capacity, open.net.capacity);
        assert_eq!(original.body, open.body);
    }

    #[test]
    fn each_unknown_series_bottleneck_limits_added_conductance() {
        let g = c9_effective_sink_g(true, 1e4, 15., 1e-2, 0.).unwrap();
        let island_contact_ceiling = C9_BRACKETS * 1e4 * C9_ISLAND_CONTACT_MM2 * 1e-6;
        let metal_ceiling = C9_BRACKETS * 15. * C9_UPRIGHT_SECTION_MM2 * 1e-6
            / (c9_common_metal_length_mm() * 1e-3);
        assert!(g < island_contact_ceiling && g < metal_ceiling && g < 1e-2);
    }

    #[test]
    fn better_contacts_and_carrier_path_cannot_reduce_sink_conductance() {
        let low = c9_effective_sink_g(true, 1e3, 15., 1e-3, 0.).unwrap();
        let high = c9_effective_sink_g(true, 1e5, 15., 1e-2, 1e-2).unwrap();
        assert!(high > low);
    }

    #[test]
    fn direct_foot_branch_increases_conductance_without_duplicating_common_leg() {
        let screw_only = c9_effective_sink_g(true, 1e4, 15., 1e-2, 0.).unwrap();
        let direct_foot = c9_effective_sink_g(true, 1e4, 15., 1e-2, 1e-2).unwrap();
        let common_leg_ceiling = C9_BRACKETS * 15. * C9_UPRIGHT_SECTION_MM2 * 1e-6
            / (c9_common_metal_length_mm() * 1e-3);
        assert!(direct_foot > screw_only && direct_foot < common_leg_ceiling);
    }

    #[test]
    fn invalid_and_unrepresentable_parameters_are_rejected() {
        assert!(c9_effective_sink_g(true, 0., 15., 1e-2, 0.).is_err());
        assert!(c9_effective_sink_g(true, 1e4, f64::NAN, 1e-2, 0.).is_err());
        assert!(c9_effective_sink_g(true, 1e4, 15., -1., 0.).is_err());
        assert!(c9_effective_sink_g(true, 1e4, 15., 1e-2, -1.).is_err());
        assert!(c9_effective_sink_g(true, f64::INFINITY, 15., f64::INFINITY, 0.).is_ok());
    }

    #[test]
    fn added_cold_sink_increases_steady_underread() {
        let g = r7_geometries().unwrap().remove(0);
        let c = Case::default();
        let base = c9_plant(&g, c, 0.).unwrap();
        let sink = c9_plant(&g, c, 1e-3).unwrap();
        assert!(score(&sink, 0.01).underread > score(&base, 0.01).underread);
    }

    #[test]
    fn independent_downstream_reservoir_temperature_uses_linear_network_weight() {
        let g = r7_geometries().unwrap().remove(0);
        let c = Case::default();
        let added = c9_effective_sink_g(true, 1e4, 15., 1e-2, 1e-3).unwrap();
        let p = c9_plant(&g, c, added).unwrap();
        let mut rhs = p.forcing(200., 80., 60.);
        let baseline = p.net.factor(None).solve(&rhs)[p.sensor];
        rhs[c.rings + 2] += 60. * added;
        let warmer = p.net.factor(None).solve(&rhs)[p.sensor];
        let mut reservoir_rhs = vec![0.; p.net.capacity.len()];
        reservoir_rhs[c.rings + 2] = added;
        let weight = p.net.factor(None).solve(&reservoir_rhs)[p.sensor];
        assert!((warmer - baseline - 60. * weight).abs() < 1e-9);
    }
}

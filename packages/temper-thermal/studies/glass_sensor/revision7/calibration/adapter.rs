// Appended inside the immutable bench module. Legacy screens are not re-exported.
fn r7_identity_pair(a: &BTreeMap<String, String>, b: &BTreeMap<String, String>) -> Result<()> {
    for m in [a, b] {
        for key in ["geometry_sha256", "bom_sha256"] {
            let value = m.get(key).ok_or("missing R7 geometry/BOM identity")?;
            if value.len() != 64 || !value.bytes().all(|c| c.is_ascii_hexdigit()) {
                return Err("R7 geometry/BOM identities require full SHA256".into());
            }
        }
        for key in ["bond_batch_id", "join_process_revision"] {
            if m.get(key).is_none_or(|v| v.trim().is_empty()) {
                return Err("missing bond/join process identity".into());
            }
        }
    }
    for key in [
        "cartridge_id",
        "geometry_sha256",
        "bom_sha256",
        "bond_batch_id",
        "join_process_revision",
        "evidence_kind",
    ] {
        if a.get(key) != b.get(key) {
            return Err(format!("changed fit/holdout configuration: {key}").into());
        }
    }
    if a.get("pan_id") == b.get("pan_id") {
        return Err("whole-pan holdout must use a different pan identity".into());
    }
    if a.get("role").map(String::as_str) != Some("fit")
        || b.get("role").map(String::as_str) != Some("holdout")
    {
        return Err("R7 requires declared fit then holdout roles".into());
    }
    Ok(())
}

fn r7_guarded(error: f64, expanded: f64, limit: f64) -> &'static str {
    if !error.is_finite() || !expanded.is_finite() || expanded <= 0. {
        return "INDETERMINATE";
    }
    if error.abs() + expanded < limit {
        "WITHIN_PROPOSED_SCREEN"
    } else if error.abs() - expanded >= limit {
        "OUTSIDE_PROPOSED_SCREEN"
    } else {
        "INDETERMINATE"
    }
}

fn r7_screen(rows: &[Row], m: &BTreeMap<String, String>) -> Result<String> {
    let legacy = thermal_metrics(rows, m)?;
    let fields: BTreeMap<_, _> = legacy.lines().filter_map(|s| s.split_once('=')).collect();
    let metric =
        |key| -> Result<&str> { Ok(*fields.get(key).ok_or("pinned metric contract changed")?) };
    let stable = metric("plateau_stable")? == "true";
    let error = metric("local_error_c")?.parse::<f64>()?;
    let expanded = metric("expanded_error_c")?.parse::<f64>()?;
    let step_ready =
        number(m, "reference_transition_s")? + number(m, "reference_lag_bound_s")? <= 0.2;
    let plateau = number(m, "plateau_start_s")?;
    let in_range = rows
        .iter()
        .filter(|r| r.t >= plateau)
        .all(|r| (40.0..=250.).contains(&r.pan));
    let error_screen = if stable && in_range {
        r7_guarded(error, expanded + 1e-6, 2.)
    } else {
        "INDETERMINATE"
    };
    let t90 = metric("t90_imposed_pan_step_s")?;
    let response = match t90.parse::<f64>() {
        Ok(t) if stable && in_range && step_ready => {
            r7_guarded(t, 2. * number(m, "u_time_s")? + 1e-6, 2.)
        }
        _ => "INDETERMINATE",
    };
    Ok(format!("local_error_c={error:.6}\nexpanded_error_c={expanded:.6}\nr7_error_screen={error_screen}\nt90_pan_s={t90}\nexpanded_time_s={:.6}\nr7_reference_step_ready={step_ready}\nr7_response_screen={response}\n", 2. * number(m, "u_time_s")?))
}

pub fn run_r7() -> Result<()> {
    let args: Vec<_> = env::args().collect();
    if args.len() != 5 {
        return Err("usage: r7-calibrate fit.csv fit.meta holdout.csv holdout.meta".into());
    }
    let (rows, m) = load(&args[1], &args[2])?;
    let (hold, hm) = load(&args[3], &args[4])?;
    r7_identity_pair(&m, &hm)?;
    let fit_hash = hash(Path::new(&args[1]))?;
    let hold_hash = hash(Path::new(&args[3]))?;
    if m["run_id"] == hm["run_id"] || m["raw_origin"] == hm["raw_origin"] || fit_hash == hold_hash {
        return Err("holdout acquisition must have independent run, origin and bytes".into());
    }
    let f = fit(&rows)?;
    let predictions = prediction(&hold, f.tau, f.gain, f.offset);
    let residual = rmse(&hold, &predictions);
    let (dynamic_rmse, dynamic_max) =
        holdout_residual(&hold, &predictions, number(&hm, "step_time_s")?, f.tau)?;
    let threshold = 2. * number(&hm, "u_error_c")?;
    let transfer = if !f.edge && residual <= threshold && dynamic_max <= threshold {
        "SURROGATE_WITHIN_DECLARED_UNCERTAINTY"
    } else {
        "REJECT_TRANSFER"
    };
    let screens = r7_screen(&hold, &hm)?;
    let output = format!("schema=temper-r7-calibration-v1\nevidence_kind={}\nphysical_validation={}\nfit_pan={}\nholdout_pan={}\ngeometry_sha256={}\nbom_sha256={}\nfit_raw_sha256={fit_hash}\nholdout_raw_sha256={hold_hash}\nfit_metadata_sha256={}\nholdout_metadata_sha256={}\nmodel=effective_first_order_not_component_identification\ntau_s={:.6}\npan_gain={:.6}\noffset_c={:.6}\nfit_rmse_c={:.6}\nholdout_rmse_c={residual:.6}\nholdout_dynamic_rmse_c={dynamic_rmse:.6}\nholdout_dynamic_max_c={dynamic_max:.6}\nsurrogate_transfer={transfer}\n{screens}release_authorization=NONE\n",
        m["evidence_kind"], if m["evidence_kind"] == "SYNTHETIC" {"NOT_RUN"} else {"ACQUIRED_REQUIRES_REVIEW"},
        m["pan_id"], hm["pan_id"], m["geometry_sha256"], m["bom_sha256"], hash(Path::new(&args[2]))?,hash(Path::new(&args[4]))?,f.tau,f.gain,f.offset,f.rmse);
    use std::io::Write;
    let mut stdout = std::io::stdout().lock();
    stdout.write_all(output.as_bytes())?;
    stdout.flush()?;
    Ok(())
}

#[cfg(test)]
mod r7_tests {
    use super::*;
    fn identity(pan: &str, role: &str) -> BTreeMap<String, String> {
        [
            ("pan_id", pan),
            ("role", role),
            ("cartridge_id", "coupon"),
            ("evidence_kind", "SYNTHETIC"),
            ("bond_batch_id", "SYNTHETIC-bond"),
            ("join_process_revision", "SYNTHETIC-join"),
        ]
        .into_iter()
        .map(|(k, v)| (k.to_owned(), v.to_owned()))
        .chain([
            ("geometry_sha256".into(), "a".repeat(64)),
            ("bom_sha256".into(), "b".repeat(64)),
        ])
        .collect()
    }
    #[test]
    fn accepts_separate_pans_same_configuration() {
        assert!(r7_identity_pair(&identity("a", "fit"), &identity("b", "holdout")).is_ok());
    }
    #[test]
    fn rejects_same_pan_even_for_distinct_run() {
        assert!(r7_identity_pair(&identity("a", "fit"), &identity("a", "holdout")).is_err());
    }
    #[test]
    fn rejects_short_identity() {
        let a = identity("a", "fit");
        let mut b = identity("b", "holdout");
        b.insert("geometry_sha256".into(), "a".repeat(16));
        assert!(r7_identity_pair(&a, &b).is_err());
    }
    #[test]
    fn rejects_geometry_change() {
        let a = identity("a", "fit");
        let mut b = identity("b", "holdout");
        b.insert("geometry_sha256".into(), "c".repeat(64));
        assert!(r7_identity_pair(&a, &b).is_err());
    }
    #[test]
    fn rejects_process_change() {
        let a = identity("a", "fit");
        let mut b = identity("b", "holdout");
        b.insert("join_process_revision".into(), "different".into());
        assert!(r7_identity_pair(&a, &b).is_err());
    }
    #[test]
    fn guarded_screen_accepts_strictly_inside_bound() {
        assert_eq!(r7_guarded(-1.0, 0.4, 2.), "WITHIN_PROPOSED_SCREEN");
        assert_eq!(r7_guarded(1.2, 0.1, 2.), "WITHIN_PROPOSED_SCREEN");
    }
    #[test]
    fn uncertainty_cannot_manufacture_pass() {
        assert_eq!(r7_guarded(1.8, 0.4, 2.), "INDETERMINATE");
    }
    #[test]
    fn strict_limit_equality_does_not_pass() {
        assert_eq!(r7_guarded(1.5, 0.5, 2.), "INDETERMINATE");
    }
    #[test]
    fn gross_error_fails_even_with_uncertainty() {
        assert_eq!(r7_guarded(-3., 0.4, 2.), "OUTSIDE_PROPOSED_SCREEN");
    }
    #[test]
    fn unknown_uncertainty_rejects_pass() {
        assert_eq!(r7_guarded(0., 0., 2.), "INDETERMINATE");
    }
}

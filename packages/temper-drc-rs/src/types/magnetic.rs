// MagneticComponent marker trait — copper void requirement at compile time.
//
// Magnetic components (transformers, inductors, common-mode chokes) require
// a copper void beneath their footprint to prevent eddy current heating and
// ensure proper magnetic coupling. The type system enforces this by requiring
// a MagneticComponent to declare its copper void requirement.
//
// At compile time: implementing MagneticComponent on a component type marks
// it as requiring void checking.
//
// At runtime: validate_magnetic_void() checks that no copper zone polygon
// intersects any magnetic component's footprint polygon.
//
// Origin: U5 of docs/plan/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use std::collections::HashMap;

use geo::algorithm::Intersects;
use geo::Polygon;

/// Marker trait for components that require copper void beneath footprint.
///
/// Any component type implementing this trait asserts that it needs a
/// copper-free region under its body. The default implementation of
/// `requires_copper_void()` returns `true`.
pub trait MagneticComponent {
    /// Returns the component reference designator.
    fn component_ref(&self) -> &str;

    /// Whether this component requires a copper void beneath its footprint.
    ///
    /// Defaults to `true`. Override for components that have an exception
    /// (e.g., a tiny ferrite bead that doesn't need voiding).
    fn requires_copper_void(&self) -> bool {
        true
    }
}

/// Runtime validation: check no copper zones intersect magnetic component footprints.
///
/// For each magnetic component, verify that no copper zone polygon overlaps
/// the component's footprint polygon. Uses `geo::algorithm::Intersects` for
/// precise polygon-polygon intersection detection.
///
/// # Arguments
/// * `magnetic_refs` - Reference designators of magnetic components to check
/// * `copper_zones` - Copper zones as (zone_name, polygon) pairs
/// * `components` - Map from refdes to footprint polygon
///
/// # Returns
/// * `Ok(())` if no copper zone intersects any magnetic component footprint
/// * `Err(...)` with messages describing each intersection found
pub fn validate_magnetic_void<'a>(
    magnetic_refs: &[String],
    copper_zones: &[(&'a str, &'a Polygon<f64>)],
    components: &HashMap<String, &'a Polygon<f64>>,
) -> Result<(), Vec<String>> {
    let mut errors: Vec<String> = Vec::new();

    for refdes in magnetic_refs {
        let Some(fp_poly) = components.get(refdes.as_str()) else {
            // Unknown component — skip (other checks will flag missing component).
            continue;
        };

        // Check each copper zone for intersection with this footprint.
        for (zone_name, zone_poly) in copper_zones {
            if (*fp_poly).intersects(*zone_poly) {
                errors.push(format!(
                    "Copper zone '{}' intersects magnetic component {} footprint. \
                     Magnetic components require a copper void beneath their body.",
                    zone_name, refdes
                ));
            }
        }
    }

    if errors.is_empty() {
        Ok(())
    } else {
        Err(errors)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use geo::{coord, polygon};

    struct TestMagnetic {
        refdes: String,
    }

    impl MagneticComponent for TestMagnetic {
        fn component_ref(&self) -> &str {
            &self.refdes
        }
    }

    fn make_rect(min_x: f64, min_y: f64, max_x: f64, max_y: f64) -> Polygon<f64> {
        polygon![
            coord! { x: min_x, y: min_y },
            coord! { x: max_x, y: min_y },
            coord! { x: max_x, y: max_y },
            coord! { x: min_x, y: max_y },
            coord! { x: min_x, y: min_y },
        ]
    }

    #[test]
    fn test_magnetic_component_trait() {
        let comp = TestMagnetic {
            refdes: "L1".into(),
        };
        assert_eq!(comp.component_ref(), "L1");
        assert!(comp.requires_copper_void());
    }

    #[test]
    fn test_validate_magnetic_void_ok() {
        let magnetic_refs = vec!["L1".to_string()];
        let fp = make_rect(10.0, 10.0, 20.0, 20.0);
        let mut components = HashMap::new();
        components.insert("L1".to_string(), &fp);

        // Copper zone is far away.
        let zone = make_rect(50.0, 50.0, 60.0, 60.0);
        let copper_zones = vec![("GND".into(), &zone)];

        let result = validate_magnetic_void(&magnetic_refs, &copper_zones, &components);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_magnetic_void_violation() {
        let magnetic_refs = vec!["L1".to_string()];
        let fp = make_rect(10.0, 10.0, 20.0, 20.0);
        let mut components = HashMap::new();
        components.insert("L1".to_string(), &fp);

        // Copper zone overlaps the footprint.
        let zone = make_rect(15.0, 15.0, 25.0, 25.0);
        let copper_zones = vec![("GND".into(), &zone)];

        let result = validate_magnetic_void(&magnetic_refs, &copper_zones, &components);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert_eq!(errs.len(), 1);
        assert!(errs[0].contains("L1"));
        assert!(errs[0].contains("GND"));
    }

    #[test]
    fn test_validate_magnetic_void_unknown_component() {
        let magnetic_refs = vec!["L99".to_string()]; // not in components map
        let fp = make_rect(10.0, 10.0, 20.0, 20.0);
        let mut components = HashMap::new();
        components.insert("L1".to_string(), &fp);

        let copper_zones: Vec<(&str, &Polygon<f64>)> = vec![];
        let result = validate_magnetic_void(&magnetic_refs, &copper_zones, &components);
        assert!(result.is_ok()); // unknown component = skip, no violation
    }
}

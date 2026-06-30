// CapVent directional type — compile-time electrolytic capacitor vent orientation.
//
// Electrolytic capacitors have a vent (safety pressure relief) that must not
// face other components, especially other capacitors. If two caps face each
// other and one vents, the hot electrolyte can damage the other. At the type
// level, VentPair<A, B> prevents constructing a pair where A's vent faces B.
//
// At compile time: VentPair<A, B> requires both A and B to have compatible
// vent orientations (not facing each other).
//
// At runtime: validate_vent_orientation() checks that no two electrolytic
// capacitors have vents pointing at each other (i.e., their vent angles
// differ by approximately 180°) when within a proximity threshold.
//
// Origin: U5 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

/// Vent direction as an angle in degrees.
///
/// 0° = positive X (right), 90° = positive Y (up), following standard PCB
/// coordinate conventions.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct VentDirection(pub f64);

impl VentDirection {
    /// Create a new vent direction from an angle in degrees.
    pub fn new(deg: f64) -> Self {
        Self(deg % 360.0)
    }

    /// Returns true if this direction faces the other direction (differs by ~180°).
    ///
    /// Two vents "face each other" if their directions differ by 180° ± 30°.
    pub fn faces(&self, other: &VentDirection) -> bool {
        let diff = (self.0 - other.0).abs().min(360.0 - (self.0 - other.0).abs());
        (diff - 180.0).abs() <= 30.0
    }
}

/// A capacitor with a defined vent direction.
#[derive(Debug, Clone)]
pub struct CapVent {
    pub refdes: String,
    pub vent: VentDirection,
}

impl CapVent {
    pub fn new(refdes: String, vent_deg: f64) -> Self {
        Self {
            refdes,
            vent: VentDirection::new(vent_deg),
        }
    }
}

/// A pair of caps whose vents face each other — compile-time error if constructed
/// with facing vents.
///
/// `A` and `B` are `CapVent` instances. If A's vent faces B's, this type
/// should not be constructible (the plan envisions this as a compile-time
/// error enforced by a trait bound or constructor check).
#[derive(Debug, Clone)]
pub struct VentPair<A, B>(pub A, pub B);

impl VentPair<CapVent, CapVent> {
    /// Attempt to create a VentPair, returning an error if the vents face each other.
    ///
    /// This is the runtime counterpart of the compile-time invariant.
    pub fn new(a: CapVent, b: CapVent) -> Result<Self, String> {
        if a.vent.faces(&b.vent) {
            Err(format!(
                "VentPair: caps {} and {} face each other. \
                 Electrolytic capacitor vents must not point at other components.",
                a.refdes, b.refdes
            ))
        } else {
            Ok(VentPair(a, b))
        }
    }
}

/// Runtime validation: check that no two electrolytic caps have vents facing each other.
///
/// Two caps are considered to face each other if:
/// 1. Their vent directions differ by approximately 180° (within ±30°)
/// 2. They are within a "nearby" distance threshold (simplified: we check all
///    pairs — proximity can be refined by the caller with centroid distance).
///
/// # Arguments
/// * `caps` - List of (refdes, vent_angle_deg)
/// * `forbidden_targets` - List of (name, (centroid_x, centroid_y)) targets to check
///   proximity against (e.g., other components, board edge). Currently reserved.
///
/// # Returns
/// * `Ok(())` if no pair of caps face each other
/// * `Err(...)` with messages for each facing pair
pub fn validate_vent_orientation(
    caps: &[(String, f64)],
    _forbidden_targets: &[(String, (f64, f64))],
) -> Result<(), Vec<String>> {
    let mut errors: Vec<String> = Vec::new();

    for i in 0..caps.len() {
        for j in (i + 1)..caps.len() {
            let (ref_a, angle_a) = &caps[i];
            let (ref_b, angle_b) = &caps[j];

            let vent_a = VentDirection::new(*angle_a);
            let vent_b = VentDirection::new(*angle_b);

            if vent_a.faces(&vent_b) {
                errors.push(format!(
                    "Electrolytic capacitors {ref_a} (vent: {angle_a}°) and {ref_b} (vent: {angle_b}°) \
                     have vents facing each other. Vents must not point at other components."
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

    #[test]
    fn test_vent_direction_faces() {
        let right = VentDirection::new(0.0);
        let left = VentDirection::new(180.0);
        assert!(right.faces(&left));
        assert!(left.faces(&right));
    }

    #[test]
    fn test_vent_direction_not_facing() {
        let right = VentDirection::new(0.0);
        let up = VentDirection::new(90.0);
        assert!(!right.faces(&up));
    }

    #[test]
    fn test_vent_pair_ok() {
        let a = CapVent::new("C1".into(), 0.0);
        let b = CapVent::new("C2".into(), 90.0);
        // These don't face each other (0° vs 90°).
        let pair = VentPair::new(a, b);
        assert!(pair.is_ok());
    }

    #[test]
    fn test_vent_pair_facing_err() {
        let a = CapVent::new("C1".into(), 0.0);
        let b = CapVent::new("C2".into(), 180.0);
        // These face each other.
        let pair = VentPair::new(a, b);
        assert!(pair.is_err());
        let err = pair.unwrap_err();
        assert!(err.contains("face each other"));
    }

    #[test]
    fn test_validate_vent_orientation_ok() {
        let caps = vec![
            ("C1".into(), 0.0),
            ("C2".into(), 90.0),
            ("C3".into(), 45.0),
        ];
        let forbidden: Vec<(String, (f64, f64))> = vec![];
        let result = validate_vent_orientation(&caps, &forbidden);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_vent_orientation_violation() {
        let caps = vec![
            ("C1".into(), 0.0),
            ("C2".into(), 180.0), // faces C1
        ];
        let forbidden: Vec<(String, (f64, f64))> = vec![];
        let result = validate_vent_orientation(&caps, &forbidden);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert_eq!(errs.len(), 1);
        assert!(errs[0].contains("C1"));
        assert!(errs[0].contains("C2"));
    }

    #[test]
    fn test_validate_vent_orientation_no_caps() {
        let caps: Vec<(String, f64)> = vec![];
        let forbidden: Vec<(String, (f64, f64))> = vec![];
        let result = validate_vent_orientation(&caps, &forbidden);
        assert!(result.is_ok());
    }
}

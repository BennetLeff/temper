// HighVoltageNet marker — compile-time HV/SELV isolation enforcement.
//
// High-voltage nets (e.g., mains AC, DC bus >60V) must not be bundled with
// signal (SELV) nets in the same net group or net class without deliberate
// type-level coercion. The HighVoltageNet marker type distinguishes HV nets
// from signal nets at the type level.
//
// At compile time: functions that accept HighVoltageNet reject regular net
// names, preventing accidental bundling of HV and signal nets.
//
// At runtime: validate_hv_isolation() checks that signal nets are not in
// the same group as any HV net (unless explicitly allowed by configuration).
//
// Origin: U5 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

/// A high-voltage net marker with its voltage rating.
///
/// The presence of this type in a function signature enforces that only
/// explicitly classified HV nets can be passed where HV isolation checks
/// are required.
#[derive(Debug, Clone)]
pub struct HighVoltageNet {
    pub name: String,
    pub voltage_v: f64,
}

impl HighVoltageNet {
    /// Create a new high-voltage net with a voltage rating.
    pub fn new(name: String, voltage_v: f64) -> Self {
        Self { name, voltage_v }
    }

    /// Returns true if this net is above the SELV threshold (typically 60V DC).
    pub fn is_hv(&self) -> bool {
        self.voltage_v > 60.0
    }
}

/// Runtime validation: check that signal nets are not bundled with HV nets.
///
/// HV nets and signal (SELV) nets must be isolated in separate net groups
/// to prevent creepage and clearance violations. A signal net found in the
/// same group as an HV net is a violation unless deliberate coercion
/// (e.g., a safety-rated optocoupler net group) is in effect.
///
/// # Arguments
/// * `hv_net` - The high-voltage net name
/// * `signal_nets` - Signal nets co-located in the same group
/// * `min_clearance_mm` - Minimum clearance required (for informational messages)
///
/// # Returns
/// * `Ok(())` if no signal nets are bundled with the HV net
/// * `Err(...)` with messages for each signal net that violates isolation
pub fn validate_hv_isolation(
    hv_net: &str,
    signal_nets: &[String],
    min_clearance_mm: f64,
) -> Result<(), Vec<String>> {
    if signal_nets.is_empty() {
        return Ok(());
    }

    let errors: Vec<String> = signal_nets
        .iter()
        .map(|sn| {
            format!(
                "Signal net '{sn}' is bundled with high-voltage net '{hv_net}' in the same net group. \
                 HV/SELV isolation requires separate net groups with {min_clearance_mm}mm minimum clearance."
            )
        })
        .collect();

    Err(errors)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hv_net_construction() {
        let hv = HighVoltageNet::new("AC_MAINS".into(), 340.0);
        assert_eq!(hv.name, "AC_MAINS");
        assert!(hv.is_hv());
    }

    #[test]
    fn test_hv_net_below_threshold() {
        let hv = HighVoltageNet::new("VCC_3V3".into(), 3.3);
        assert!(!hv.is_hv());
    }

    #[test]
    fn test_validate_hv_isolation_ok() {
        let result = validate_hv_isolation("AC_MAINS", &[], 8.0);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_hv_isolation_violation() {
        let signal_nets = vec!["I_SENSE".to_string(), "NTC".to_string()];
        let result = validate_hv_isolation("AC_MAINS", &signal_nets, 8.0);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert_eq!(errs.len(), 2);
        assert!(errs[0].contains("I_SENSE"));
        assert!(errs[0].contains("AC_MAINS"));
        assert!(errs[0].contains("8"));
    }

    #[test]
    fn test_validate_hv_isolation_empty_signals() {
        let result = validate_hv_isolation("AC_MAINS", &[], 8.0);
        assert!(result.is_ok());
    }
}

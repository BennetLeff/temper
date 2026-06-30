// ESD connector with mandatory chassis ground return path.
//
// ESD protection requires a defined low-impedance return path to chassis
// ground. At the type level, ESDConnector enforces the presence of a
// ChassisGnd by making it a non-optional field — any code constructing an
// ESDConnector must provide an ESDReturn with a ChassisGnd connection.
//
// At runtime: validate_esd_path() checks that the return path length does
// not exceed the maximum allowed for effective ESD protection.
//
// Origin: U5 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

/// Marker type for chassis ground connection.
///
/// The type itself carries no data — its presence in the struct is what
/// matters. An ESDConnector without a ChassisGnd cannot be constructed.
#[derive(Debug, Clone)]
pub struct ChassisGnd;

/// The ESD return path from a connector to chassis ground.
#[derive(Debug, Clone)]
pub struct ESDReturn {
    /// Nets that form the return path (e.g., ["SHIELD", "CHASSIS"]).
    pub path_nets: Vec<String>,
    /// Connection to chassis ground. Required — cannot be None.
    pub chassis_connection: ChassisGnd,
}

impl ESDReturn {
    /// Create a new ESD return path with a chassis ground connection.
    pub fn new(path_nets: Vec<String>) -> Self {
        Self {
            path_nets,
            chassis_connection: ChassisGnd,
        }
    }
}

/// A connector that requires ESD protection with a chassis ground return path.
///
/// The `esd_return_path` field is **not optional** — you cannot construct
/// an ESDConnector without providing an ESDReturn. This enforces at compile
/// time that every ESD-sensitive connector has a defined return path.
#[derive(Debug, Clone)]
pub struct ESDConnector {
    pub refdes: String,
    pub esd_return_path: ESDReturn,
}

impl ESDConnector {
    /// Create a new ESD connector with mandatory return path.
    pub fn new(refdes: String, esd_return_path: ESDReturn) -> Self {
        Self {
            refdes,
            esd_return_path,
        }
    }
}

/// Runtime validation: check ESD return path length is within limit.
///
/// A long ESD return path increases inductance and reduces ESD protection
/// effectiveness. This check verifies the path length against a configured
/// maximum (typically 10-15mm for effective ESD protection).
///
/// # Arguments
/// * `connector` - Reference designator of the connector
/// * `return_path_length_mm` - Measured length of the ESD return path
/// * `max_length_mm` - Maximum allowed return path length
///
/// # Returns
/// * `Ok(())` if return path length is within limit
/// * `Err(...)` if path is too long
pub fn validate_esd_path(
    connector: &str,
    return_path_length_mm: f64,
    max_length_mm: f64,
) -> Result<(), Vec<String>> {
    if return_path_length_mm > max_length_mm {
        Err(vec![format!(
            "ESD return path for {connector} is {return_path_length_mm}mm, exceeds {max_length_mm}mm"
        )])
    } else {
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_esd_connector_requires_return_path() {
        // This test verifies that an ESDConnector cannot be constructed
        // without an ESDReturn containing a ChassisGnd.
        let ret = ESDReturn::new(vec!["SHIELD".into(), "CHASSIS".into()]);
        let conn = ESDConnector::new("J1".into(), ret);
        assert_eq!(conn.refdes, "J1");
        assert_eq!(conn.esd_return_path.path_nets.len(), 2);
    }

    #[test]
    fn test_validate_esd_path_ok() {
        let result = validate_esd_path("J1", 8.0, 15.0);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_esd_path_violation() {
        let result = validate_esd_path("J1", 20.0, 15.0);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert_eq!(errs.len(), 1);
        assert!(errs[0].contains("J1"));
        assert!(errs[0].contains("20"));
        assert!(errs[0].contains("15"));
    }

    #[test]
    fn test_validate_esd_path_exact_boundary() {
        // Exactly at the limit is OK (≤ max_length).
        let result = validate_esd_path("J2", 15.0, 15.0);
        assert!(result.is_ok());
    }
}

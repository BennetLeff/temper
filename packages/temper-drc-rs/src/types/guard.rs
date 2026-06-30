// GuardedPin<T> — compile-time protection for high-impedance analog inputs.
//
// High-impedance analog inputs (e.g., NTC thermistor sense, current sense)
// must be surrounded by a guard ring driven to the same potential to prevent
// leakage currents from corrupting the measurement. The GuardedPin<T> wrapper
// type makes the guard ring requirement explicit at compile time: to connect
// a high-impedance pin, you must wrap it in GuardedPin<T>, which carries the
// GuardRing marker.
//
// At compile time: passing a raw pin where a GuardedPin<T> is expected fails
// to compile with a type mismatch error.
//
// At runtime: validate_guard_ring() checks that any pin declared as
// high-impedance has an associated guard ring.
//
// Origin: U5 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

/// Marker type for a guard ring structure surrounding an analog pin.
///
/// Carries no data — its presence in GuardedPin<T> is what distinguishes a
/// guarded pin from an unguarded one at the type level.
#[derive(Debug, Clone)]
pub struct GuardRing;

/// A pin wrapped with an explicit guard ring requirement.
///
/// The generic parameter `T` is the underlying pin type (typically a string
/// identifier or enum). The `guard` field ensures at compile time that a
/// GuardRing exists alongside the pin.
#[derive(Debug, Clone)]
pub struct GuardedPin<T> {
    pub pin: T,
    pub guard: GuardRing,
}

impl<T> GuardedPin<T> {
    /// Wrap a pin in a guard ring.
    pub fn new(pin: T) -> Self {
        Self {
            pin,
            guard: GuardRing,
        }
    }
}

/// Runtime validation: check that high-impedance analog inputs have guard rings.
///
/// A high-impedance analog input without a guard ring is susceptible to
/// leakage currents that can corrupt the measurement. This validation ensures
/// every such pin has been explicitly marked as guarded.
///
/// # Arguments
/// * `pin_name` - The name of the pin being checked
/// * `has_guard` - Whether the pin has a guard ring (from GuardedPin<T>)
/// * `is_high_impedance` - Whether the pin is a high-impedance analog input
///
/// # Returns
/// * `Ok(())` if the pin is either low-impedance or has a guard ring
/// * `Err(...)` if the pin is high-impedance and lacks a guard ring
pub fn validate_guard_ring(
    pin_name: &str,
    has_guard: bool,
    is_high_impedance: bool,
) -> Result<(), Vec<String>> {
    if is_high_impedance && !has_guard {
        Err(vec![format!(
            "High-impedance analog input {pin_name} requires a guard ring"
        )])
    } else {
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_guarded_pin_construction() {
        let pin = GuardedPin::new("NTC_SENSE");
        // The guard field is populated by construction.
        assert_eq!(pin.pin, "NTC_SENSE");
    }

    #[test]
    fn test_validate_guard_ring_ok_with_guard() {
        let result = validate_guard_ring("NTC_SENSE", true, true);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_guard_ring_low_impedance_no_guard_ok() {
        // Low-impedance pins don't need guard rings.
        let result = validate_guard_ring("GPIO1", false, false);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_guard_ring_violation() {
        let result = validate_guard_ring("NTC_SENSE", false, true);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert_eq!(errs.len(), 1);
        assert!(errs[0].contains("NTC_SENSE"));
        assert!(errs[0].contains("guard ring"));
    }
}

// PointToPoint clock nets — type-level invariant against branching.
//
// Clock nets in PCB design must be point-to-point: one source drives exactly
// one sink. Any branching (fan-out) on a clock net creates signal integrity
// issues (reflections, impedance mismatch, timing skew).
//
// At compile time: PointToPoint<SourcePin, SinkPin> guarantees a single
// source-sink pair. Multiple sinks can only be represented by constructing
// separate PointToPoint instances, making the violation syntactically visible.
//
// At runtime: validate() checks net topology and returns errors describing
// the violation with specific pin names.
//
// Origin: U5 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

/// A named pin on a component (e.g., "U_MCU.18").
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClockPin(pub String);

/// A point-to-point connection between a source pin and a single sink pin.
///
/// `SourcePin` and `SinkPin` are distinct type parameters so that the type
/// system enforces a single source and a single sink. Both typically
/// instantiated as `ClockPin`.
#[derive(Debug, Clone)]
pub struct PointToPoint<SourcePin, SinkPin>(pub SourcePin, pub SinkPin);

impl<A, B> PointToPoint<A, B> {
    /// Runtime validation: returns Err if multiple sinks are attached to one source.
    ///
    /// Clock nets must drive exactly one load. A source with zero sinks is
    /// also an error (unconnected clock). The error messages name the
    /// specific pins involved.
    ///
    /// # Arguments
    /// * `source` - The name of the source pin (e.g., "U_MCU.18")
    /// * `sinks` - The list of sink pin names connected to this source
    ///
    /// # Returns
    /// * `Ok(())` if exactly one sink is attached
    /// * `Err(...)` if zero sinks (unloaded) or more than one sink (branched)
    pub fn validate(source: &str, sinks: &[&str]) -> Result<(), Vec<String>> {
        if sinks.len() > 1 {
            Err(sinks
                .iter()
                .map(|s| {
                    format!(
                        "Clock net branched: {source} drives {s}. Clock nets must be PointToPoint"
                    )
                })
                .collect())
        } else if sinks.is_empty() {
            Err(vec![format!(
                "Clock net {source} has no load. Clock nets must drive exactly one sink"
            )])
        } else {
            Ok(())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_point_to_point_ok() {
        let result = PointToPoint::<ClockPin, ClockPin>::validate("U_MCU.18", &["U_ADC.3"]);
        assert!(result.is_ok());
    }

    #[test]
    fn test_point_to_point_branched() {
        let result =
            PointToPoint::<ClockPin, ClockPin>::validate("U_MCU.18", &["U_ADC.3", "U_DAC.7"]);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert_eq!(errs.len(), 2);
        assert!(errs[0].contains("branched"));
        assert!(errs[0].contains("U_MCU.18"));
    }

    #[test]
    fn test_point_to_point_unloaded() {
        let result = PointToPoint::<ClockPin, ClockPin>::validate("U_MCU.18", &[]);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert_eq!(errs.len(), 1);
        assert!(errs[0].contains("no load"));
    }
}

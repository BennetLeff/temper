// Noise domain phantom types — Emitter/Victim separation at compile time.
//
// Noise coupling between emitter nets (noisy switching nodes, clock lines)
// and victim nets (sensitive analog sense lines) must be controlled at the
// PCB layout level. The type system prevents accidentally assigning the
// same net to both an Emitter and a Victim domain without explicit handling.
//
// NetBundle<T> carries a phantom type parameter T that is either Emitter or
// Victim. This prevents passing an emitter bundle where a victim bundle is
// expected (and vice versa) at compile time.
//
// At runtime: validate_noise_domains() checks that no bundle contains nets
// from both emitter and victim domains — a configuration error that would
// make noise-domain-based checks vacuous.
//
// Origin: U5 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use std::marker::PhantomData;

/// Marker type for noise emitter nets (e.g., GATE_HS, SW_NODE, SPI_CLK).
pub struct Emitter;

/// Marker type for noise victim nets (e.g., I_SENSE, V_SENSE, NTC_SENSE).
pub struct Victim;

/// A bundle of nets classified as either Emitters or Victims.
///
/// The phantom type parameter T prevents mixing emitter and victim bundles
/// at compile time: a function expecting `NetBundle<Victim>` will not accept
/// a `NetBundle<Emitter>`.
#[derive(Debug, Clone)]
pub struct NetBundle<T> {
    pub name: String,
    pub nets: Vec<String>,
    _phantom: PhantomData<T>,
}

impl<T> NetBundle<T> {
    /// Create a new net bundle with the given name and net list.
    pub fn new(name: String, nets: Vec<String>) -> Self {
        Self {
            name,
            nets,
            _phantom: PhantomData,
        }
    }
}

/// Runtime validation: returns Err if a bundle contains nets of conflicting noise domains.
///
/// Checks that no bundle mixes emitter and victim nets. Such a bundle would
/// make noise-domain-based routing checks (e.g., parallel-run coupling detection)
/// impossible to evaluate correctly.
///
/// # Arguments
/// * `emitters` - List of emitter net names
/// * `victims` - List of victim net names
/// * `bundles` - List of bundles, each as (name, net_list)
///
/// # Returns
/// * `Ok(())` if no bundle mixes emitter and victim nets
/// * `Err(...)` with messages describing each conflicting bundle
pub fn validate_noise_domains(
    emitters: &[String],
    victims: &[String],
    bundles: &[(String, Vec<String>)],
) -> Result<(), Vec<String>> {
    let mut errors: Vec<String> = Vec::new();

    // Build sets for fast lookup.
    let emitter_set: std::collections::HashSet<&str> =
        emitters.iter().map(|s| s.as_str()).collect();
    let victim_set: std::collections::HashSet<&str> =
        victims.iter().map(|s| s.as_str()).collect();

    for (bundle_name, bundle_nets) in bundles {
        let mut has_emitter = false;
        let mut has_victim = false;

        for net in bundle_nets {
            if emitter_set.contains(net.as_str()) {
                has_emitter = true;
            }
            if victim_set.contains(net.as_str()) {
                has_victim = true;
            }
        }

        if has_emitter && has_victim {
            errors.push(format!(
                "Bundle '{}' contains nets from both emitter and victim noise domains. \
                 Noise domain routing checks require homogeneous bundles.",
                bundle_name
            ));
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
    fn test_net_bundle_phantom_types() {
        let emitter_bundle: NetBundle<Emitter> =
            NetBundle::new("switching".into(), vec!["GATE_HS".into(), "SW_NODE".into()]);
        let _victim_bundle: NetBundle<Victim> =
            NetBundle::new("sense".into(), vec!["I_SENSE".into()]);

        // Verify the phantom type is present in the type signature.
        // (This compiles because the phantom type is what distinguishes them.)
        assert_eq!(emitter_bundle.name, "switching");
    }

    #[test]
    fn test_validate_noise_domains_ok() {
        let emitters = vec!["GATE_HS".to_string(), "SW_NODE".to_string()];
        let victims = vec!["I_SENSE".to_string(), "V_SENSE".to_string()];
        let bundles = vec![
            ("switching".to_string(), vec!["GATE_HS".to_string(), "SW_NODE".to_string()]),
            ("sense".to_string(), vec!["I_SENSE".to_string(), "V_SENSE".to_string()]),
        ];

        let result = validate_noise_domains(&emitters, &victims, &bundles);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_noise_domains_conflict() {
        let emitters = vec!["GATE_HS".to_string()];
        let victims = vec!["I_SENSE".to_string()];
        let bundles = vec![
            ("mixed".to_string(), vec!["GATE_HS".to_string(), "I_SENSE".to_string()]),
        ];

        let result = validate_noise_domains(&emitters, &victims, &bundles);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert_eq!(errs.len(), 1);
        assert!(errs[0].contains("mixed"));
        assert!(errs[0].contains("emitter"));
        assert!(errs[0].contains("victim"));
    }

    #[test]
    fn test_validate_noise_domains_empty() {
        let emitters: Vec<String> = vec![];
        let victims: Vec<String> = vec![];
        let bundles: Vec<(String, Vec<String>)> = vec![];

        let result = validate_noise_domains(&emitters, &victims, &bundles);
        assert!(result.is_ok());
    }
}

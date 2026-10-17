// ---------------------------------------------------------------------------
// MCU candidate gates (P1 U2): build freshness + net admission.
//
// Atopile writes netlist/BOM artifacts even when an assertion FAILS (it exits
// nonzero but leaves the files behind), so downstream stages must gate on
// the return code AND the assertions report AND input-hash agreement before
// consuming anything. These kernels are that gate, plus the rule that empty
// reference nets (unconnected interface members) never become copper.
// ---------------------------------------------------------------------------

use std::collections::HashMap;

use crate::error::DesignBundleError as CandidateBundleError;
use crate::error::diagnostic as candidate_diagnostic;

/// Fail-closed build-freshness gate for one candidate build.
///
/// - `returncode != 0` (or an assertion `FAILED` line in the build stdout)
///   means the artifacts are unqualified, even though they exist on disk.
/// - `recorded` is `{path: sha256}` captured at build time; `current` is the
///   same map re-read before consumption. Any missing, changed, or added
///   file is a stale export, never a silent substitution.
pub fn check_candidate_freshness(
    recorded_json: &str,
    current_json: &str,
    returncode: i64,
    stdout_text: &str,
) -> Result<(), CandidateBundleError> {
    if returncode != 0 {
        return Err(candidate_diagnostic(
            "failed_build",
            format!("compiler exited {returncode}; artifacts are unqualified"),
            vec![],
        ));
    }
    if stdout_text.contains("FAILED") {
        return Err(candidate_diagnostic(
            "failed_assertion",
            "build report contains a FAILED assertion; artifacts are unqualified",
            vec![],
        ));
    }
    let recorded: HashMap<String, String> = serde_json::from_str(recorded_json)
        .map_err(|e| CandidateBundleError::Document(format!("recorded hashes: {e}")))?;
    let current: HashMap<String, String> = serde_json::from_str(current_json)
        .map_err(|e| CandidateBundleError::Document(format!("current hashes: {e}")))?;
    let mut changed: Vec<String> = recorded
        .iter()
        .filter_map(|(path, sha)| {
            if current.get(path).is_some_and(|now| now == sha) {
                None
            } else {
                Some(path.clone())
            }
        })
        .collect();
    let mut added: Vec<String> = current
        .keys()
        .filter(|path| !recorded.contains_key(*path))
        .cloned()
        .collect();
    changed.sort();
    added.sort();
    if !changed.is_empty() || !added.is_empty() {
        let mut references = changed.clone();
        references.extend(added.clone());
        let mut parts = Vec::new();
        if !changed.is_empty() {
            parts.push(format!("changed/missing: {}", changed.join(", ")));
        }
        if !added.is_empty() {
            parts.push(format!("added: {}", added.join(", ")));
        }
        return Err(candidate_diagnostic(
            "stale_export",
            format!("source inputs moved under the build ({})", parts.join("; ")),
            references,
        ));
    }
    Ok(())
}

/// Fail-closed net-admission gate: the board's net set must equal the
/// compiled non-empty net set exactly.
///
/// - A non-empty source net missing from the board is a dropped net.
/// - A board net absent from the source is extra connectivity.
/// - An empty source net (unconnected interface members such as
///   `mcu-reference*`) admitted to the board is an unintended short across
///   members that were never joined.
pub fn check_candidate_net_admission(
    netlist_json: &str,
    admitted_json: &str,
) -> Result<(), CandidateBundleError> {
    let nets: Vec<crate::atopile::BridgeNetlistNet> = serde_json::from_str(netlist_json)
        .map_err(|e| CandidateBundleError::Document(format!("bridge netlist: {e}")))?;
    let admitted: Vec<String> = serde_json::from_str(admitted_json)
        .map_err(|e| CandidateBundleError::Document(format!("admitted nets: {e}")))?;
    let source: HashMap<&str, usize> = nets
        .iter()
        .map(|net| (net.name.as_str(), net.nodes.len()))
        .collect();
    let mut admitted_sorted = admitted.clone();
    admitted_sorted.sort();
    let mut admitted_unique = admitted_sorted.clone();
    admitted_unique.dedup();
    if admitted_unique.len() != admitted_sorted.len() {
        return Err(candidate_diagnostic(
            "duplicate_net",
            "admitted net list names a net more than once",
            vec![],
        ));
    }
    for name in &admitted_unique {
        match source.get(name.as_str()) {
            None => {
                return Err(candidate_diagnostic(
                    "extra_net",
                    format!("board net '{name}' does not exist in the compiled netlist"),
                    vec![name.clone()],
                ));
            }
            Some(0) => {
                return Err(candidate_diagnostic(
                    "empty_net_admitted",
                    format!(
                        "board net '{name}' is empty in the compiled netlist and must never become copper"
                    ),
                    vec![name.clone()],
                ));
            }
            _ => {}
        }
    }
    let mut dropped: Vec<String> = source
        .iter()
        .filter(|(name, count)| **count > 0 && !admitted_unique.iter().any(|a| a == *name))
        .map(|(name, _)| (*name).to_string())
        .collect();
    dropped.sort();
    if !dropped.is_empty() {
        return Err(candidate_diagnostic(
            "dropped_net",
            format!(
                "compiled non-empty nets missing from the board: {}",
                dropped.join(", ")
            ),
            dropped,
        ));
    }
    Ok(())
}



#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod candidate_gate_tests {
    use super::*;

    fn code(err: &CandidateBundleError) -> String {
        match err {
            CandidateBundleError::Validation(diags) => diags[0].code.clone(),
            other => panic!("expected Validation, got {other:?}"),
        }
    }

    const NETS: &str = r#"[{"name":"vcc","nodes":[["U1","2"],["C1","1"]]},
        {"name":"solo","nodes":[["U1","11"]]},
        {"name":"mcu-reference","nodes":[]}]"#;

    #[test]
    fn freshness_passes_on_identical_maps_and_clean_report() {
        let maps = r#"{"elec/src/modules.ato":"abc","mcu.ato":"def"}"#;
        check_candidate_freshness(maps, maps, 0, "3 passed").expect("clean build passes");
    }

    #[test]
    fn freshness_rejects_failed_builds_changed_and_added_inputs() {
        let maps = r#"{"a":"1"}"#;
        assert_eq!(
            code(&check_candidate_freshness(maps, maps, 1, "x").unwrap_err()),
            "failed_build"
        );
        assert_eq!(
            code(&check_candidate_freshness(maps, maps, 0, "1 FAILED").unwrap_err()),
            "failed_assertion"
        );
        assert_eq!(
            code(&check_candidate_freshness(maps, r#"{"a":"2"}"#, 0, "ok").unwrap_err()),
            "stale_export"
        );
        assert_eq!(
            code(&check_candidate_freshness(maps, r#"{"a":"1","b":"2"}"#, 0, "ok").unwrap_err()),
            "stale_export"
        );
    }

    #[test]
    fn admission_requires_exact_nonempty_cover() {
        check_candidate_net_admission(NETS, r#"["vcc","solo"]"#).expect("exact cover passes");
        assert_eq!(
            code(&check_candidate_net_admission(NETS, r#"["vcc"]"#).unwrap_err()),
            "dropped_net"
        );
        assert_eq!(
            code(&check_candidate_net_admission(NETS, r#"["vcc","solo","nope"]"#).unwrap_err()),
            "extra_net"
        );
        assert_eq!(
            code(
                &check_candidate_net_admission(NETS, r#"["vcc","solo","mcu-reference"]"#)
                    .unwrap_err()
            ),
            "empty_net_admitted"
        );
    }
}

//! Semantic identity and repeatability envelopes for raw KiCad DRC findings.
//!
//! KiCad may report the same creepage path through a different connected
//! copper primitive on consecutive runs.  This module keeps that provider
//! churn in a raw identity while deriving a second, engineering-semantic
//! identity from the rule message, exact measured distance, net multiset,
//! and component multiset.  All bag operations preserve duplicate findings.

use std::collections::{BTreeMap, BTreeSet};
use std::sync::OnceLock;

use regex::Regex;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

#[derive(Clone, Debug, Deserialize)]
pub struct RawFinding {
    #[serde(rename = "type")]
    pub category: String,
    pub description: String,
    pub items: Vec<RawItem>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct RawItem {
    pub description: String,
    pub pos: RawPosition,
}

#[derive(Clone, Debug, Deserialize)]
pub struct RawPosition {
    x: serde_json::Number,
    y: serde_json::Number,
}

#[cfg(test)]
impl RawPosition {
    fn new(x: &str, y: &str) -> Self {
        fn number(value: &str) -> serde_json::Number {
            match value.parse::<serde_json::Number>() {
                Ok(value) => value,
                Err(error) => panic!("invalid test number {value}: {error}"),
            }
        }
        Self {
            x: number(x),
            y: number(y),
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
pub struct FamilyKey {
    pub category: String,
    pub message_semantics: String,
    pub nets: Vec<String>,
    pub components: Vec<String>,
    /// Empty only for creepage, whose connected-copper representative is
    /// provider-selected. Every other category keeps canonical raw items so
    /// this narrowly-scoped exception cannot hide a physical item change.
    pub items: Vec<RawItemKey>,
}

#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
pub struct ObservationKey {
    pub family: FamilyKey,
    pub actual_distance_mm: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
pub struct RawProviderKey {
    pub category: String,
    pub description: String,
    pub items: Vec<RawItemKey>,
}

#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
pub struct RawItemKey {
    pub description: String,
    pub x: String,
    pub y: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct SampleDigest {
    pub finding_count: usize,
    pub family_digest: String,
    pub observation_digest: String,
    pub raw_digest: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct BagEntry<K> {
    pub key: K,
    pub count: usize,
}

#[derive(Clone, Debug, Serialize)]
pub struct FringeEntry<K> {
    pub key: K,
    pub counts: Vec<usize>,
    pub deltas_from_sample_0: Vec<i64>,
}

#[derive(Clone, Debug, Serialize)]
pub struct BagEnvelope<K> {
    pub stable: bool,
    pub sample_digests: Vec<String>,
    pub intersection_size: usize,
    pub union_size: usize,
    pub intersection: Vec<BagEntry<K>>,
    pub unstable_fringe: Vec<FringeEntry<K>>,
}

#[derive(Clone, Debug, Serialize)]
pub struct EvidenceEnvelope {
    pub schema: &'static str,
    pub sample_count: usize,
    pub samples: Vec<SampleDigest>,
    pub family: BagEnvelope<FamilyKey>,
    pub observation: BagEnvelope<ObservationKey>,
    pub raw: BagEnvelope<RawProviderKey>,
}

#[derive(Debug, Error)]
pub enum EvidenceError {
    #[error("DRC_EVIDENCE_EMPTY_SAMPLES: at least one sample is required")]
    EmptySamples,
    #[error("DRC_EVIDENCE_INVALID_JSON: {0}")]
    InvalidJson(#[from] serde_json::Error),
    #[error("DRC_EVIDENCE_MISSING_FIELD: sample {sample}, finding {finding}: {field}")]
    MissingField {
        sample: usize,
        finding: usize,
        field: &'static str,
    },
    #[error("DRC_EVIDENCE_MALFORMED_DISTANCE: sample {sample}, finding {finding}: {description}")]
    MalformedDistance {
        sample: usize,
        finding: usize,
        description: String,
    },
    #[error("DRC_EVIDENCE_SERIALIZATION: {0}")]
    Serialization(serde_json::Error),
    #[error("DRC_SILK_SCOPE_BOARD: {0}")]
    MalformedBoard(String),
    #[error(
        "DRC_SILK_SCOPE_DECLARED_REF: declared footprint {reference} is absent from the subject census"
    )]
    MissingDeclaredReference { reference: String },
    #[error("DRC_SILK_SCOPE_CENSUS_DRIFT: source and subject footprint censuses differ")]
    FootprintCensusDrift,
    #[error("DRC_SILK_SCOPE_UNDECLARED_MUTATION: {references:?}")]
    UndeclaredMutation { references: Vec<String> },
    #[error(
        "DRC_SILK_SCOPE_AMBIGUOUS_PAIR: expected two footprint references, found {references:?}"
    )]
    AmbiguousSilkPair { references: Vec<String> },
}

const SILK_SAFE_MARGIN: u32 = 20;

#[derive(Debug, Deserialize)]
struct SilkScopeRequest {
    source_board: String,
    subject_board: String,
    declared_refs: Vec<String>,
    #[serde(default)]
    use_declared_scope: bool,
    raw_global_capped: bool,
    #[serde(default)]
    leaves: Vec<SilkLeaf>,
}

#[derive(Debug, Deserialize)]
struct SilkLeaf {
    pairs: Vec<[String; 2]>,
    sample_counts: Vec<u32>,
}

#[derive(Debug, Serialize)]
struct SilkScopeReceipt {
    schema: &'static str,
    source_sha256: String,
    subject_sha256: String,
    silk_projection_sha256: String,
    safe_ceiling: u32,
    declared_refs: Vec<String>,
    actual_mutated_refs: Vec<String>,
    measurement_scope_refs: Vec<String>,
    expected_pair_count: usize,
    covered_pair_count: usize,
    missing_pairs: Vec<[String; 2]>,
    duplicate_pairs: Vec<[String; 2]>,
    foreign_pairs: Vec<[String; 2]>,
    unresolved_leaf_count: usize,
    complete: bool,
    category_state: &'static str,
}

fn net_re() -> &'static Regex {
    static VALUE: OnceLock<Regex> = OnceLock::new();
    VALUE.get_or_init(|| {
        #[expect(clippy::unwrap_used, reason = "constant regex covered by unit tests")]
        Regex::new(r"\[([^\]]+)\]").unwrap()
    })
}

fn component_re() -> &'static Regex {
    static VALUE: OnceLock<Regex> = OnceLock::new();
    VALUE.get_or_init(|| {
        #[expect(clippy::unwrap_used, reason = "constant regex covered by unit tests")]
        Regex::new(r"\bof (\S+?)(?:\s+on\s+\S.*)?$").unwrap()
    })
}

fn net_pair_re() -> &'static Regex {
    static VALUE: OnceLock<Regex> = OnceLock::new();
    VALUE.get_or_init(|| {
        #[expect(clippy::unwrap_used, reason = "constant regex covered by unit tests")]
        Regex::new(r"\(nets (.+) and (.+)\)$").unwrap()
    })
}

fn normalize_net_pair(description: &str) -> String {
    let Some(captures) = net_pair_re().captures(description) else {
        return description.to_string();
    };
    let (Some(whole), Some(first), Some(second)) =
        (captures.get(0), captures.get(1), captures.get(2))
    else {
        return description.to_string();
    };
    let mut nets = [first.as_str(), second.as_str()];
    nets.sort_unstable();
    format!(
        "{}(nets {} and {})",
        &description[..whole.start()],
        nets[0],
        nets[1]
    )
}

/// Separate the exact reported actual distance from the remaining message.
/// The string representation stays exact: no float round-trip can merge two
/// distinct KiCad observations.
fn split_actual_distance(description: &str) -> Result<(String, Option<String>), ()> {
    let Some(start) = description.rfind("; actual ") else {
        return if description.contains("actual ") {
            Err(())
        } else {
            Ok((normalize_net_pair(description), None))
        };
    };
    let value_start = start + "; actual ".len();
    let Some(value) = description[value_start..].strip_suffix(" mm)") else {
        return Err(());
    };
    if value.is_empty() || value.parse::<f64>().is_err() {
        return Err(());
    }
    let family_message = format!("{})", &description[..start]);
    Ok((normalize_net_pair(&family_message), Some(value.to_string())))
}

fn identities(
    finding: &RawFinding,
    sample: usize,
    finding_index: usize,
) -> Result<(FamilyKey, ObservationKey, RawProviderKey), EvidenceError> {
    if finding.category.is_empty() {
        return Err(EvidenceError::MissingField {
            sample,
            finding: finding_index,
            field: "type must be non-empty",
        });
    }
    if finding.description.is_empty() {
        return Err(EvidenceError::MissingField {
            sample,
            finding: finding_index,
            field: "description must be non-empty",
        });
    }
    let (message_semantics, actual_distance_mm) = split_actual_distance(&finding.description)
        .map_err(|()| EvidenceError::MalformedDistance {
            sample,
            finding: finding_index,
            description: finding.description.clone(),
        })?;

    let mut nets = Vec::new();
    let mut components = Vec::new();
    let mut raw_items = Vec::with_capacity(finding.items.len());
    for item in &finding.items {
        if item.description.is_empty() {
            return Err(EvidenceError::MissingField {
                sample,
                finding: finding_index,
                field: "items[].description must be non-empty",
            });
        }
        nets.extend(
            net_re()
                .captures_iter(&item.description)
                .filter_map(|capture| capture.get(1).map(|value| value.as_str().to_string())),
        );
        if let Some(component) = component_re()
            .captures(&item.description)
            .and_then(|capture| capture.get(1))
        {
            components.push(component.as_str().to_string());
        }
        raw_items.push(RawItemKey {
            description: item.description.clone(),
            x: item.pos.x.to_string(),
            y: item.pos.y.to_string(),
        });
    }
    nets.sort();
    components.sort();
    raw_items.sort();

    let family = FamilyKey {
        category: finding.category.clone(),
        message_semantics,
        nets,
        components,
        items: if finding
            .category
            .strip_prefix("W:")
            .unwrap_or(&finding.category)
            == "creepage"
        {
            Vec::new()
        } else {
            raw_items.clone()
        },
    };
    let observation = ObservationKey {
        family: family.clone(),
        actual_distance_mm,
    };
    let raw = RawProviderKey {
        category: finding.category.clone(),
        description: normalize_net_pair(&finding.description),
        items: raw_items,
    };
    Ok((family, observation, raw))
}

fn digest_bag<K: Serialize>(bag: &BTreeMap<K, usize>) -> Result<String, EvidenceError> {
    // JSON objects require string keys.  A sorted list of `(key, count)`
    // pairs is both type-preserving and canonical for any serializable key.
    let entries: Vec<(&K, &usize)> = bag.iter().collect();
    let bytes = serde_json::to_vec(&entries).map_err(EvidenceError::Serialization)?;
    let digest = Sha256::digest(bytes);
    Ok(digest.iter().map(|byte| format!("{byte:02x}")).collect())
}

fn bag_envelope<K>(bags: &[BTreeMap<K, usize>]) -> Result<BagEnvelope<K>, EvidenceError>
where
    K: Clone + Ord + Serialize,
{
    let mut keys = BTreeSet::new();
    for bag in bags {
        keys.extend(bag.keys().cloned());
    }
    let mut intersection = Vec::new();
    let mut unstable_fringe = Vec::new();
    let mut intersection_size = 0;
    let mut union_size = 0;
    for key in keys {
        let counts: Vec<usize> = bags
            .iter()
            .map(|bag| bag.get(&key).copied().unwrap_or(0))
            .collect();
        let min = counts.iter().copied().min().unwrap_or(0);
        let max = counts.iter().copied().max().unwrap_or(0);
        intersection_size += min;
        union_size += max;
        if min > 0 {
            intersection.push(BagEntry {
                key: key.clone(),
                count: min,
            });
        }
        if min != max {
            let origin = counts.first().copied().unwrap_or(0) as i64;
            unstable_fringe.push(FringeEntry {
                key,
                deltas_from_sample_0: counts.iter().map(|count| *count as i64 - origin).collect(),
                counts,
            });
        }
    }
    let sample_digests = bags.iter().map(digest_bag).collect::<Result<Vec<_>, _>>()?;
    Ok(BagEnvelope {
        stable: unstable_fringe.is_empty(),
        sample_digests,
        intersection_size,
        union_size,
        intersection,
        unstable_fringe,
    })
}

pub fn evidence_envelope(samples: &[Vec<RawFinding>]) -> Result<EvidenceEnvelope, EvidenceError> {
    if samples.is_empty() {
        return Err(EvidenceError::EmptySamples);
    }
    let mut family_bags = Vec::with_capacity(samples.len());
    let mut observation_bags = Vec::with_capacity(samples.len());
    let mut raw_bags = Vec::with_capacity(samples.len());

    for (sample_index, sample) in samples.iter().enumerate() {
        let mut families = BTreeMap::new();
        let mut observations = BTreeMap::new();
        let mut raw = BTreeMap::new();
        for (finding_index, finding) in sample.iter().enumerate() {
            let (family, observation, provider) = identities(finding, sample_index, finding_index)?;
            *families.entry(family).or_insert(0) += 1;
            *observations.entry(observation).or_insert(0) += 1;
            *raw.entry(provider).or_insert(0) += 1;
        }
        family_bags.push(families);
        observation_bags.push(observations);
        raw_bags.push(raw);
    }

    let family = bag_envelope(&family_bags)?;
    let observation = bag_envelope(&observation_bags)?;
    let raw = bag_envelope(&raw_bags)?;
    let samples = family_bags
        .iter()
        .zip(&observation_bags)
        .zip(&raw_bags)
        .map(|((families, observations), raw)| {
            Ok(SampleDigest {
                finding_count: observations.values().sum(),
                family_digest: digest_bag(families)?,
                observation_digest: digest_bag(observations)?,
                raw_digest: digest_bag(raw)?,
            })
        })
        .collect::<Result<Vec<_>, EvidenceError>>()?;

    Ok(EvidenceEnvelope {
        schema: "temper.drc-semantic-envelope/v1",
        sample_count: samples.len(),
        samples,
        family,
        observation,
        raw,
    })
}

pub fn evidence_envelope_json(samples_json: &str) -> Result<String, EvidenceError> {
    let samples: Vec<Vec<RawFinding>> = serde_json::from_str(samples_json)?;
    let envelope = evidence_envelope(&samples)?;
    serde_json::to_string(&envelope).map_err(EvidenceError::Serialization)
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn footprint_start_re() -> &'static Regex {
    static VALUE: OnceLock<Regex> = OnceLock::new();
    VALUE.get_or_init(|| {
        #[expect(clippy::unwrap_used, reason = "constant regex covered by unit tests")]
        Regex::new(r"(?m)^  \(footprint\s").unwrap()
    })
}

fn reference_property_re() -> &'static Regex {
    static VALUE: OnceLock<Regex> = OnceLock::new();
    VALUE.get_or_init(|| {
        #[expect(clippy::unwrap_used, reason = "constant regex covered by unit tests")]
        Regex::new(r#"\(property\s+"Reference"\s+"([^"\\]*(?:\\.[^"\\]*)*)""#).unwrap()
    })
}

fn balanced_end(text: &str, start: usize) -> Result<usize, EvidenceError> {
    let bytes = text.as_bytes();
    let mut depth = 0usize;
    let mut in_string = false;
    let mut escaped = false;
    for (offset, byte) in bytes[start..].iter().copied().enumerate() {
        if in_string {
            if escaped {
                escaped = false;
            } else if byte == b'\\' {
                escaped = true;
            } else if byte == b'"' {
                in_string = false;
            }
            continue;
        }
        match byte {
            b'"' => in_string = true,
            b'(' => depth += 1,
            b')' => {
                if depth == 0 {
                    return Err(EvidenceError::MalformedBoard(
                        "encountered unmatched closing parenthesis".to_string(),
                    ));
                }
                depth -= 1;
                if depth == 0 {
                    return Ok(start + offset + 1);
                }
            }
            _ => {}
        }
    }
    Err(EvidenceError::MalformedBoard(
        "unterminated footprint s-expression".to_string(),
    ))
}

fn footprint_blocks(text: &str) -> Result<BTreeMap<String, String>, EvidenceError> {
    let mut blocks = BTreeMap::new();
    for start in footprint_start_re()
        .find_iter(text)
        .map(|matched| matched.start() + 2)
    {
        let end = balanced_end(text, start)?;
        let block = &text[start..end];
        let reference = reference_property_re()
            .captures(block)
            .and_then(|capture| capture.get(1))
            .ok_or_else(|| {
                EvidenceError::MalformedBoard(
                    "footprint is missing a Reference property".to_string(),
                )
            })?
            .as_str()
            .to_string();
        if blocks
            .insert(reference.clone(), block.to_string())
            .is_some()
        {
            return Err(EvidenceError::MalformedBoard(format!(
                "duplicate footprint reference {reference}"
            )));
        }
    }
    if blocks.is_empty() {
        return Err(EvidenceError::MalformedBoard(
            "board contains no direct footprint blocks".to_string(),
        ));
    }
    Ok(blocks)
}

fn normalized_pair(first: &str, second: &str) -> [String; 2] {
    if first <= second {
        [first.to_string(), second.to_string()]
    } else {
        [second.to_string(), first.to_string()]
    }
}

fn expected_pairs(all_refs: &BTreeSet<String>, scope: &BTreeSet<String>) -> BTreeSet<[String; 2]> {
    let mut pairs = BTreeSet::new();
    for affected in scope {
        for other in all_refs {
            if affected != other {
                pairs.insert(normalized_pair(affected, other));
            }
        }
    }
    pairs
}

fn silk_projection_digest(blocks: &BTreeMap<String, String>) -> String {
    let mut bytes = Vec::new();
    for (reference, block) in blocks {
        bytes.extend_from_slice(reference.as_bytes());
        bytes.push(0);
        bytes.extend_from_slice(block.as_bytes());
        bytes.push(0xff);
    }
    sha256_hex(&bytes)
}

/// Validate a complete mutation-cone silk receipt. Board text is parsed only
/// to census exact footprint blocks; Python remains responsible for staging
/// KiCad projects and transporting raw leaf results.
pub fn silk_scope_receipt_json(request_json: &str) -> Result<String, EvidenceError> {
    let request: SilkScopeRequest = serde_json::from_str(request_json)?;
    let source = footprint_blocks(&request.source_board)?;
    let subject = footprint_blocks(&request.subject_board)?;
    let source_refs: BTreeSet<String> = source.keys().cloned().collect();
    let subject_refs: BTreeSet<String> = subject.keys().cloned().collect();
    if source_refs != subject_refs {
        return Err(EvidenceError::FootprintCensusDrift);
    }

    let declared: BTreeSet<String> = request.declared_refs.into_iter().collect();
    for reference in &declared {
        if !subject.contains_key(reference) {
            return Err(EvidenceError::MissingDeclaredReference {
                reference: reference.clone(),
            });
        }
    }
    let actual: BTreeSet<String> = source
        .iter()
        .filter_map(|(reference, source_block)| {
            (subject.get(reference) != Some(source_block)).then_some(reference.clone())
        })
        .collect();
    let undeclared: Vec<String> = actual.difference(&declared).cloned().collect();
    if !undeclared.is_empty() {
        return Err(EvidenceError::UndeclaredMutation {
            references: undeclared,
        });
    }
    let scope = if request.use_declared_scope {
        declared.clone()
    } else {
        actual.clone()
    };
    let expected = expected_pairs(&subject_refs, &scope);
    let safe_ceiling = crate::drc_count::cap_for("silk_overlap")
        .unwrap_or(crate::drc_count::KICAD_ERROR_LIMIT)
        .saturating_sub(SILK_SAFE_MARGIN);

    let mut coverage: BTreeMap<[String; 2], usize> = BTreeMap::new();
    let mut unresolved_leaf_count = 0usize;
    for leaf in &request.leaves {
        let samples_agree = leaf.sample_counts.len() == 3
            && leaf
                .sample_counts
                .first()
                .is_some_and(|first| leaf.sample_counts.iter().all(|count| count == first));
        let safely_below_cap = leaf.sample_counts.iter().all(|count| *count < safe_ceiling);
        if !samples_agree || !safely_below_cap {
            unresolved_leaf_count += 1;
        }
        for pair in &leaf.pairs {
            *coverage
                .entry(normalized_pair(&pair[0], &pair[1]))
                .or_insert(0) += 1;
        }
    }
    let covered: BTreeSet<[String; 2]> = coverage.keys().cloned().collect();
    let missing_pairs: Vec<[String; 2]> = expected.difference(&covered).cloned().collect();
    let duplicate_pairs: Vec<[String; 2]> = coverage
        .iter()
        .filter_map(|(pair, count)| (*count > 1).then_some(pair.clone()))
        .collect();
    let foreign_pairs: Vec<[String; 2]> = covered.difference(&expected).cloned().collect();
    let scoped_complete = missing_pairs.is_empty()
        && duplicate_pairs.is_empty()
        && foreign_pairs.is_empty()
        && unresolved_leaf_count == 0;
    let complete = !request.raw_global_capped || scoped_complete;
    let category_state = if !request.raw_global_capped {
        "uncapped-exact"
    } else if scoped_complete {
        "raw-saturated-scoped-complete"
    } else {
        "raw-saturated-unresolved"
    };
    let receipt = SilkScopeReceipt {
        schema: "temper.silk-mutation-scope/v1",
        source_sha256: sha256_hex(request.source_board.as_bytes()),
        subject_sha256: sha256_hex(request.subject_board.as_bytes()),
        silk_projection_sha256: silk_projection_digest(&subject),
        safe_ceiling,
        declared_refs: declared.into_iter().collect(),
        actual_mutated_refs: actual.into_iter().collect(),
        measurement_scope_refs: scope.into_iter().collect(),
        expected_pair_count: expected.len(),
        covered_pair_count: expected.intersection(&covered).count(),
        missing_pairs,
        duplicate_pairs,
        foreign_pairs,
        unresolved_leaf_count,
        complete,
        category_state,
    };
    serde_json::to_string(&receipt).map_err(EvidenceError::Serialization)
}

/// Extract the canonical footprint pair from one raw `silk_overlap` record.
/// The raw item descriptions remain KiCad's oracle; Rust owns the parsing and
/// rejects ambiguous records rather than letting Python invent a pair.
pub fn silk_finding_pair_json(finding_json: &str) -> Result<String, EvidenceError> {
    let finding: RawFinding = serde_json::from_str(finding_json)?;
    let mut references = BTreeSet::new();
    for item in &finding.items {
        if let Some(reference) = component_re()
            .captures(&item.description)
            .and_then(|capture| capture.get(1))
        {
            references.insert(reference.as_str().to_string());
        }
    }
    let references: Vec<String> = references.into_iter().collect();
    if references.len() != 2 {
        return Err(EvidenceError::AmbiguousSilkPair { references });
    }
    serde_json::to_string(&normalized_pair(&references[0], &references[1]))
        .map_err(EvidenceError::Serialization)
}

#[cfg(feature = "python")]
#[pyo3::pyfunction(name = "drc_evidence_envelope_json")]
fn evidence_envelope_json_py(samples_json: &str) -> pyo3::PyResult<String> {
    evidence_envelope_json(samples_json)
        .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))
}

#[cfg(feature = "python")]
#[pyo3::pyfunction(name = "drc_silk_scope_receipt_json")]
fn silk_scope_receipt_json_py(request_json: &str) -> pyo3::PyResult<String> {
    silk_scope_receipt_json(request_json)
        .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))
}

#[cfg(feature = "python")]
#[pyo3::pyfunction(name = "drc_silk_finding_pair_json")]
fn silk_finding_pair_json_py(finding_json: &str) -> pyo3::PyResult<String> {
    silk_finding_pair_json(finding_json)
        .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))
}

#[cfg(feature = "python")]
pub fn register(module: &pyo3::Bound<'_, pyo3::types::PyModule>) -> pyo3::PyResult<()> {
    use pyo3::prelude::PyModuleMethods;
    module.add_function(pyo3::wrap_pyfunction!(evidence_envelope_json_py, module)?)?;
    module.add_function(pyo3::wrap_pyfunction!(silk_scope_receipt_json_py, module)?)?;
    module.add_function(pyo3::wrap_pyfunction!(silk_finding_pair_json_py, module)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn creepage(actual: &str, net_b: &str, component: &str, provider: &str) -> RawFinding {
        RawFinding {
            category: "creepage".to_string(),
            description: format!(
                "Creepage violation (rule 'HighVoltageSignal to LV' creepage 12.6000 mm; actual {actual} mm)"
            ),
            items: vec![
                RawItem {
                    description: format!("Pad 2 [discharge.r_snub1-p2] of {component} on F.Cu"),
                    pos: RawPosition::new("130.0", "87.5"),
                },
                RawItem {
                    description: format!("Track [{net_b}] on F.Cu, length {provider} mm"),
                    pos: RawPosition::new("139.1", "87.5"),
                },
            ],
        }
    }

    #[test]
    fn provider_churn_is_semantically_stable_and_raw_visible() {
        let samples = vec![
            vec![creepage("10.2975", "V_BUS_SENSE", "R14", "0.8485")],
            vec![creepage("10.2975", "V_BUS_SENSE", "R14", "11.9000")],
            vec![creepage("10.2975", "V_BUS_SENSE", "R14", "0.8485")],
        ];

        let envelope = evidence_envelope(&samples).expect("valid production-shaped findings");

        assert!(envelope.observation.stable);
        assert_eq!(envelope.observation.intersection_size, 1);
        assert_eq!(envelope.observation.union_size, 1);
        assert_eq!(envelope.raw.intersection_size, 0);
        assert_eq!(envelope.raw.union_size, 2);
        assert_eq!(envelope.raw.unstable_fringe.len(), 2);
        assert_ne!(
            envelope.samples[0].raw_digest,
            envelope.samples[1].raw_digest
        );
        assert_eq!(
            envelope.samples[0].observation_digest,
            envelope.samples[1].observation_digest
        );
    }

    #[test]
    fn identity_bearing_mutations_are_not_normalized() {
        let baseline = creepage("10.2975", "V_BUS_SENSE", "R14", "0.8485");
        let cases = [
            creepage("10.1975", "V_BUS_SENSE", "R14", "0.8485"),
            creepage("10.2975", "DIFFERENT_NET", "R14", "0.8485"),
            creepage("10.2975", "V_BUS_SENSE", "R99", "0.8485"),
            RawFinding {
                description: "Creepage violation (rule 'Different rule' creepage 12.6000 mm; actual 10.2975 mm)".to_string(),
                ..baseline.clone()
            },
        ];

        for changed in cases {
            let envelope = evidence_envelope(&[vec![baseline.clone()], vec![changed]])
                .expect("valid mutation");
            assert!(!envelope.observation.stable);
        }
    }

    #[test]
    fn order_canonicalizes_but_duplicate_multisets_survive() {
        let mut a = creepage("10.2975", "V_BUS_SENSE", "R14", "0.8485");
        a.items.push(a.items[1].clone());
        let mut reordered = a.clone();
        reordered.items.reverse();
        let one = evidence_envelope(&[vec![a.clone()], vec![reordered]])
            .expect("valid reordered finding");
        assert!(one.observation.stable);

        let without_duplicate = creepage("10.2975", "V_BUS_SENSE", "R14", "0.8485");
        let changed = evidence_envelope(&[vec![a], vec![without_duplicate]])
            .expect("valid multiplicity mutation");
        assert!(!changed.observation.stable);
    }

    #[test]
    fn duplicate_findings_use_multiset_intersection_and_union() {
        let v = creepage("10.2975", "V_BUS_SENSE", "R14", "0.8485");
        let envelope = evidence_envelope(&[
            vec![v.clone(), v.clone()],
            vec![v.clone()],
            vec![v.clone(), v.clone(), v],
        ])
        .expect("valid duplicate findings");

        assert_eq!(envelope.observation.intersection_size, 1);
        assert_eq!(envelope.observation.union_size, 3);
        assert_eq!(
            envelope.observation.unstable_fringe[0].counts,
            vec![2, 1, 3]
        );
        assert_eq!(
            envelope.observation.unstable_fringe[0].deltas_from_sample_0,
            vec![0, -1, 1]
        );
    }

    #[test]
    fn non_creepage_item_position_remains_identity_bearing() {
        let baseline = RawFinding {
            category: "clearance".to_string(),
            description:
                "Clearance violation (netclass 'Power' clearance 0.5000 mm; actual 0.2868 mm)"
                    .to_string(),
            items: vec![RawItem {
                description: "Via [gnd] on F.Cu".to_string(),
                pos: RawPosition::new("100.0", "80.0"),
            }],
        };
        let mut changed = baseline.clone();
        changed.items[0].pos = RawPosition::new("100.1", "80.0");

        let envelope = evidence_envelope(&[vec![baseline], vec![changed]])
            .expect("valid non-creepage mutation");

        assert!(!envelope.family.stable);
        assert!(!envelope.observation.stable);
    }

    #[test]
    fn malformed_identity_field_is_typed_error() {
        let err = evidence_envelope_json(
            r#"[[{"type":"creepage","description":"Creepage violation (actual nope mm)","items":[]}]]"#,
        )
        .expect_err("malformed distance must fail closed");
        assert!(matches!(err, EvidenceError::MalformedDistance { .. }));
    }

    fn board(r2_at: &str) -> String {
        format!(
            "(kicad_pcb\n  (footprint \"Test:R\" (property \"Reference\" \"R1\") (at 0 0))\n  (footprint \"Test:R\" (property \"Reference\" \"R2\") (at {r2_at}))\n  (footprint \"Test:R\" (property \"Reference\" \"R3\") (at 20 0))\n)\n"
        )
    }

    #[test]
    fn silk_scope_receipt_binds_actual_mutation_and_exact_pair_coverage() {
        let request = serde_json::json!({
            "source_board": board("10 0"),
            "subject_board": board("11 0"),
            "declared_refs": ["R2"],
            "use_declared_scope": false,
            "raw_global_capped": true,
            "leaves": [
                {"pairs": [["R1", "R2"]], "sample_counts": [3, 3, 3]},
                {"pairs": [["R2", "R3"]], "sample_counts": [0, 0, 0]}
            ]
        });
        let receipt: serde_json::Value = serde_json::from_str(
            &silk_scope_receipt_json(&request.to_string()).expect("complete scope"),
        )
        .expect("valid receipt JSON");
        assert_eq!(receipt["actual_mutated_refs"], serde_json::json!(["R2"]));
        assert_eq!(receipt["expected_pair_count"], 2);
        assert_eq!(receipt["covered_pair_count"], 2);
        assert_eq!(receipt["complete"], true);
        assert_eq!(receipt["category_state"], "raw-saturated-scoped-complete");
    }

    #[test]
    fn silk_scope_rejects_undeclared_mutation() {
        let request = serde_json::json!({
            "source_board": board("10 0"),
            "subject_board": board("10 0").replace("(at 20 0)", "(at 21 0)"),
            "declared_refs": ["R2"],
            "use_declared_scope": false,
            "raw_global_capped": true,
            "leaves": []
        });
        let error = silk_scope_receipt_json(&request.to_string())
            .expect_err("undeclared mutation must fail closed");
        assert!(matches!(error, EvidenceError::UndeclaredMutation { .. }));
    }

    #[test]
    fn silk_scope_marks_duplicate_missing_disagreeing_and_near_cap_unresolved() {
        let request = serde_json::json!({
            "source_board": board("10 0"),
            "subject_board": board("10 0"),
            "declared_refs": ["R2"],
            "use_declared_scope": true,
            "raw_global_capped": true,
            "leaves": [
                {"pairs": [["R1", "R2"], ["R1", "R2"]], "sample_counts": [179, 179, 179]},
                {"pairs": [["R2", "R3"]], "sample_counts": [1, 2, 1]}
            ]
        });
        let receipt: serde_json::Value = serde_json::from_str(
            &silk_scope_receipt_json(&request.to_string()).expect("typed unresolved receipt"),
        )
        .expect("valid receipt JSON");
        assert_eq!(receipt["complete"], false);
        assert_eq!(receipt["category_state"], "raw-saturated-unresolved");
        assert_eq!(
            receipt["duplicate_pairs"],
            serde_json::json!([["R1", "R2"]])
        );
        assert_eq!(receipt["unresolved_leaf_count"], 2);
    }

    #[test]
    fn silk_finding_pair_is_rust_owned_and_ambiguous_records_fail() {
        let finding = serde_json::json!({
            "type": "silk_overlap",
            "description": "Silkscreen overlap",
            "items": [
                {"description": "Text REF of R2 on F.Silkscreen", "pos": {"x": 0, "y": 0}},
                {"description": "Arc of C3 on F.Silkscreen", "pos": {"x": 1, "y": 1}}
            ]
        });
        assert_eq!(
            silk_finding_pair_json(&finding.to_string()).expect("two-ref pair"),
            r#"["C3","R2"]"#
        );
        let ambiguous = finding.to_string().replace(" of C3 on", " of R2 on");
        assert!(matches!(
            silk_finding_pair_json(&ambiguous).expect_err("same-ref record is ambiguous"),
            EvidenceError::AmbiguousSilkPair { .. }
        ));
    }
}

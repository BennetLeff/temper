//! Semantic identity and repeatability envelopes for raw KiCad DRC findings.
//!
//! KiCad may report the same creepage path or missing connection through a
//! different connected copper primitive on consecutive runs. This module
//! keeps that provider churn in a raw identity while deriving a second,
//! engineering-semantic identity from the rule message, exact measured
//! distance, net multiset, and component multiset. All bag operations preserve
//! duplicate findings.

use std::collections::{BTreeMap, BTreeSet};
use std::sync::OnceLock;

use regex::Regex;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

#[cfg(feature = "python")]
use pyo3::pyfunction;

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct RawFinding {
    #[serde(rename = "type")]
    pub category: String,
    pub description: String,
    pub items: Vec<RawItem>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct RawItem {
    pub description: String,
    pub pos: RawPosition,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct RawPosition {
    x: serde_json::Number,
    y: serde_json::Number,
}

#[cfg(any(test, feature = "wasm-registry"))]
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

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Ord, PartialOrd, Serialize)]
pub struct FamilyKey {
    pub category: String,
    pub message_semantics: String,
    pub nets: Vec<String>,
    pub components: Vec<String>,
    /// Empty only for categories whose connected-copper representative is
    /// provider-selected (`creepage` and `unconnected_items`). Every other
    /// category keeps canonical raw items so this exception cannot hide a
    /// physical item change.
    pub items: Vec<RawItemKey>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Ord, PartialOrd, Serialize)]
pub struct ObservationKey {
    pub family: FamilyKey,
    pub actual_distance_mm: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Ord, PartialOrd, Serialize)]
pub struct RawProviderKey {
    pub category: String,
    pub description: String,
    pub items: Vec<RawItemKey>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Ord, PartialOrd, Serialize)]
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

#[derive(Clone, Debug, Deserialize, Serialize)]
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
    #[error("DRC_SILK_SCOPE_NON_RIGID_MUTATION: {references:?}")]
    NonRigidMutation { references: Vec<String> },
    #[error(
        "DRC_SILK_SCOPE_AMBIGUOUS_PAIR: expected two footprint references, found {references:?}"
    )]
    AmbiguousSilkPair { references: Vec<String> },
    #[error("DRC_ADMISSION_COMPARISON: {0}")]
    InvalidComparison(String),
}

const SILK_SAFE_MARGIN: u32 = 20;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
struct SilkInstrumentContext {
    schema: String,
    kicad_cli_version: String,
    runner: String,
    runner_flags: Vec<String>,
    project_sha256: String,
    dru_sha256: String,
    fp_lib_table_sha256: String,
    libraries_sha256: String,
}

#[derive(Debug, Deserialize)]
struct SilkScopeRequest {
    source_board: String,
    subject_board: String,
    declared_refs: Vec<String>,
    #[serde(default)]
    use_declared_scope: bool,
    raw_global_capped: bool,
    instrument_context: SilkInstrumentContext,
    #[serde(default)]
    execution: Option<SilkExecution>,
    #[serde(default)]
    leaves: Vec<SilkLeaf>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct SilkExecution {
    kicad_invocation_count: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    reused_projection_receipt_sha256: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    partition_seed_receipt_sha256: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct SilkLeaf {
    pairs: Vec<[String; 2]>,
    cells: Vec<SilkCell>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct SilkCell {
    sample_counts: Vec<u32>,
    #[serde(default)]
    sample_findings: Vec<Vec<RawFinding>>,
    #[serde(default)]
    item_region: Option<SilkItemRegion>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct SilkItemRegion {
    pair: [String; 2],
    first_item_count: usize,
    second_item_count: usize,
    first_indices: Vec<usize>,
    second_indices: Vec<usize>,
}

#[derive(Debug, Deserialize)]
struct SilkCellCheckRequest {
    pairs: Vec<[String; 2]>,
    safe_ceiling: u32,
    cell: SilkCell,
}

#[derive(Debug, Serialize)]
struct SilkCellCheckReceipt {
    schema: &'static str,
    sample_count: usize,
    safely_below_cap: bool,
    semantic_samples_agree: bool,
    resolved: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Ord, PartialOrd, Serialize)]
struct ScopedSilkFinding {
    pair: [String; 2],
    message_semantics: String,
    item_descriptions: Vec<String>,
}

#[derive(Debug, Serialize)]
#[serde(tag = "kind", rename_all = "kebab-case")]
enum SilkFindingSubject {
    Pair { pair: [String; 2] },
    SelfOverlap { reference: String },
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct SilkScopeReceipt {
    schema: String,
    source_sha256: String,
    subject_sha256: String,
    silk_projection_sha256: String,
    instrument_context: SilkInstrumentContext,
    instrument_context_sha256: String,
    partition_manifest_sha256: String,
    leaf_hashes: Vec<String>,
    leaves: Vec<SilkLeaf>,
    safe_ceiling: u32,
    declared_refs: Vec<String>,
    actual_mutated_refs: Vec<String>,
    rigid_only_mutated_refs: Vec<String>,
    measurement_scope_refs: Vec<String>,
    expected_pair_count: usize,
    covered_pair_count: usize,
    missing_pairs: Vec<[String; 2]>,
    duplicate_pairs: Vec<[String; 2]>,
    foreign_pairs: Vec<[String; 2]>,
    unresolved_leaf_count: usize,
    finding_count: usize,
    findings: Vec<BagEntry<ScopedSilkFinding>>,
    complete: bool,
    category_state: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    execution: Option<SilkExecution>,
}

#[derive(Debug, Deserialize)]
struct ComparisonRequest {
    baseline_samples: Vec<Vec<RawFinding>>,
    candidate_samples: Vec<Vec<RawFinding>>,
    #[serde(default)]
    baseline_capped_categories: Vec<String>,
    #[serde(default)]
    candidate_capped_categories: Vec<String>,
    baseline_silk_receipt: Option<SilkScopeReceipt>,
    candidate_silk_receipt: Option<SilkScopeReceipt>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "kebab-case")]
enum CategoryState {
    UncappedExact,
    RawSaturatedScopedComplete,
    RawSaturatedUnresolved,
}

#[derive(Debug, Serialize)]
struct ComparisonReceipt {
    schema: &'static str,
    instrument_conclusive: bool,
    semantic_repeats_agree: bool,
    category_states: BTreeMap<String, CategoryState>,
    raw_global_capped_categories: Vec<String>,
    unresolved_cap_categories: Vec<String>,
    new_hard_observation_count: usize,
    worsened_hard_observation_count: usize,
    indeterminate_hard_comparison_count: usize,
    new_scoped_silk_finding_count: usize,
}

#[derive(Clone, Debug, Serialize)]
struct WorsenedHardObservation {
    baseline: ObservationKey,
    candidate: ObservationKey,
    count: usize,
}

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd, Serialize)]
struct IndeterminateHardComparison {
    reason: &'static str,
    category: Option<String>,
    family: Option<FamilyKey>,
    baseline: Vec<ObservationKey>,
    candidate: Vec<ObservationKey>,
    count: usize,
}

#[derive(Debug, Serialize)]
struct ComparisonReceiptV3 {
    schema: &'static str,
    instrument_conclusive: bool,
    semantic_repeats_agree: bool,
    category_states: BTreeMap<String, CategoryState>,
    raw_global_capped_categories: Vec<String>,
    unresolved_cap_categories: Vec<String>,
    new_hard_observations: Vec<BagEntry<ObservationKey>>,
    removed_hard_observations: Vec<BagEntry<ObservationKey>>,
    worsened_hard_observations: Vec<WorsenedHardObservation>,
    indeterminate_hard_comparisons: Vec<IndeterminateHardComparison>,
    new_scoped_silk_findings: Vec<BagEntry<ScopedSilkFinding>>,
    new_hard_observation_count: usize,
    worsened_hard_observation_count: usize,
    indeterminate_hard_comparison_count: usize,
    new_scoped_silk_finding_count: usize,
}

struct ComparisonParts {
    instrument_conclusive: bool,
    semantic_repeats_agree: bool,
    category_states: BTreeMap<String, CategoryState>,
    raw_global_capped_categories: Vec<String>,
    unresolved_cap_categories: Vec<String>,
    new_hard_observations: Vec<BagEntry<ObservationKey>>,
    removed_hard_observations: Vec<BagEntry<ObservationKey>>,
    worsened_hard_observations: Vec<WorsenedHardObservation>,
    indeterminate_hard_comparisons: Vec<IndeterminateHardComparison>,
    new_scoped_silk_findings: Vec<BagEntry<ScopedSilkFinding>>,
    v2_new_hard_observation_count: usize,
    v2_worsened_hard_observation_count: usize,
    v2_indeterminate_hard_comparison_count: usize,
    v2_new_scoped_silk_finding_count: usize,
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
        items: if matches!(
            finding
                .category
                .strip_prefix("W:")
                .unwrap_or(&finding.category),
            "creepage" | "unconnected_items"
        ) {
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
    Ok(sha256_hex(&bytes))
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

fn bare_category(category: &str) -> &str {
    category.strip_prefix("W:").unwrap_or(category)
}

fn is_hard_category(category: &str) -> bool {
    matches!(
        bare_category(category),
        "shorting_items" | "clearance" | "creepage" | "hole_clearance" | "copper_edge_clearance"
    )
}

fn observations_by_family(
    sample: &[RawFinding],
) -> Result<BTreeMap<FamilyKey, Vec<Option<String>>>, EvidenceError> {
    let mut observations: BTreeMap<FamilyKey, Vec<Option<String>>> = BTreeMap::new();
    for (finding_index, finding) in sample.iter().enumerate() {
        let (_family, observation, _raw) = identities(finding, 0, finding_index)?;
        observations
            .entry(observation.family)
            .or_default()
            .push(observation.actual_distance_mm);
    }
    for values in observations.values_mut() {
        values.sort_by(|left, right| match (left, right) {
            (Some(left), Some(right)) => left
                .parse::<f64>()
                .unwrap_or(f64::NAN)
                .total_cmp(&right.parse::<f64>().unwrap_or(f64::NAN)),
            (None, Some(_)) => std::cmp::Ordering::Less,
            (Some(_), None) => std::cmp::Ordering::Greater,
            (None, None) => std::cmp::Ordering::Equal,
        });
    }
    Ok(observations)
}

fn receipt_completes_silk(receipt: Option<&SilkScopeReceipt>) -> bool {
    receipt.is_some_and(|receipt| {
        receipt.schema == "temper.silk-mutation-scope/v4"
            && receipt.complete
            && receipt.category_state == "raw-saturated-scoped-complete"
            && receipt.expected_pair_count == receipt.covered_pair_count
            && receipt.missing_pairs.is_empty()
            && receipt.duplicate_pairs.is_empty()
            && receipt.foreign_pairs.is_empty()
            && receipt.unresolved_leaf_count == 0
    })
}

fn silk_receipts_comparable(
    baseline: Option<&SilkScopeReceipt>,
    candidate: Option<&SilkScopeReceipt>,
) -> bool {
    match (baseline, candidate) {
        (Some(baseline), Some(candidate)) => {
            receipt_completes_silk(Some(baseline))
                && receipt_completes_silk(Some(candidate))
                && baseline.source_sha256 == candidate.source_sha256
                && baseline.instrument_context_sha256 == candidate.instrument_context_sha256
                && baseline.safe_ceiling == candidate.safe_ceiling
                && baseline.declared_refs == candidate.declared_refs
        }
        _ => false,
    }
}

fn scoped_silk_finding_bag(
    receipt: &SilkScopeReceipt,
    scope: &BTreeSet<String>,
) -> BTreeMap<ScopedSilkFinding, usize> {
    let mut findings = BTreeMap::new();
    for entry in &receipt.findings {
        if entry
            .key
            .pair
            .iter()
            .any(|reference| scope.contains(reference))
        {
            *findings.entry(entry.key.clone()).or_insert(0) += entry.count;
        }
    }
    findings
}

/// Compare two immutable subjects using the same semantic identity used for
/// repeatability. Reporting caps remain explicit typed states; only a complete
/// Rust-issued silk mutation-cone receipt can resolve a saturated category.
fn comparison_parts(request: &ComparisonRequest) -> Result<ComparisonParts, EvidenceError> {
    let baseline_envelope = evidence_envelope(&request.baseline_samples)?;
    let candidate_envelope = evidence_envelope(&request.candidate_samples)?;
    let semantic_repeats_agree =
        baseline_envelope.observation.stable && candidate_envelope.observation.stable;

    let baseline_caps: BTreeSet<String> =
        request.baseline_capped_categories.iter().cloned().collect();
    let candidate_caps: BTreeSet<String> = request
        .candidate_capped_categories
        .iter()
        .cloned()
        .collect();
    let all_caps: BTreeSet<String> = baseline_caps.union(&candidate_caps).cloned().collect();
    let mut categories = BTreeSet::new();
    for sample in request
        .baseline_samples
        .iter()
        .chain(&request.candidate_samples)
    {
        categories.extend(sample.iter().map(|finding| finding.category.clone()));
    }
    categories.extend(all_caps.iter().cloned());

    let baseline_silk_complete = receipt_completes_silk(request.baseline_silk_receipt.as_ref());
    let candidate_silk_complete = receipt_completes_silk(request.candidate_silk_receipt.as_ref());
    let silk_receipts_comparable = silk_receipts_comparable(
        request.baseline_silk_receipt.as_ref(),
        request.candidate_silk_receipt.as_ref(),
    );
    let mut category_states = BTreeMap::new();
    let mut unresolved_cap_categories = Vec::new();
    for category in categories {
        let baseline_capped = baseline_caps.contains(&category);
        let candidate_capped = candidate_caps.contains(&category);
        let state = if !baseline_capped && !candidate_capped {
            CategoryState::UncappedExact
        } else if bare_category(&category) == "silk_overlap"
            && baseline_silk_complete
            && candidate_silk_complete
            && silk_receipts_comparable
        {
            CategoryState::RawSaturatedScopedComplete
        } else {
            unresolved_cap_categories.push(category.clone());
            CategoryState::RawSaturatedUnresolved
        };
        category_states.insert(category, state);
    }

    let mut new_hard_observation_count = 0usize;
    let mut worsened_hard_observation_count = 0usize;
    let mut indeterminate_hard_comparison_count = 0usize;
    let mut new_hard_observations = BTreeMap::new();
    let mut removed_hard_observations = BTreeMap::new();
    let mut worsened_hard_observations = BTreeMap::new();
    let mut indeterminate_hard_comparisons = Vec::new();
    if semantic_repeats_agree {
        let baseline = observations_by_family(&request.baseline_samples[0])?;
        let candidate = observations_by_family(&request.candidate_samples[0])?;
        let families: BTreeSet<FamilyKey> = baseline
            .keys()
            .chain(candidate.keys())
            .filter(|family| is_hard_category(&family.category))
            .cloned()
            .collect();
        for family in families {
            let baseline_values = baseline.get(&family).map(Vec::as_slice).unwrap_or(&[]);
            let candidate_values = candidate.get(&family).map(Vec::as_slice).unwrap_or(&[]);
            new_hard_observation_count +=
                candidate_values.len().saturating_sub(baseline_values.len());
            let category_is_unresolved = unresolved_cap_categories
                .binary_search(&family.category)
                .is_ok();
            let mut missing_distance_count = 0;
            for (baseline_value, candidate_value) in
                baseline_values.iter().zip(candidate_values.iter())
            {
                match (baseline_value, candidate_value) {
                    (Some(baseline), Some(candidate)) => {
                        let baseline = baseline.parse::<f64>().map_err(|_| {
                            EvidenceError::InvalidComparison(
                                "validated baseline distance no longer parses".to_string(),
                            )
                        })?;
                        let candidate = candidate.parse::<f64>().map_err(|_| {
                            EvidenceError::InvalidComparison(
                                "validated candidate distance no longer parses".to_string(),
                            )
                        })?;
                        if candidate < baseline {
                            worsened_hard_observation_count += 1;
                            if !category_is_unresolved {
                                let baseline_key = ObservationKey {
                                    family: family.clone(),
                                    actual_distance_mm: baseline_value.clone(),
                                };
                                let candidate_key = ObservationKey {
                                    family: family.clone(),
                                    actual_distance_mm: candidate_value.clone(),
                                };
                                *worsened_hard_observations
                                    .entry((baseline_key, candidate_key))
                                    .or_insert(0) += 1;
                            }
                        }
                    }
                    (None, None) => {}
                    _ => {
                        indeterminate_hard_comparison_count += 1;
                        missing_distance_count += 1;
                    }
                }
            }
            if !category_is_unresolved {
                if missing_distance_count > 0 {
                    indeterminate_hard_comparisons.push(IndeterminateHardComparison {
                        reason: "missing-actual-distance",
                        category: Some(family.category.clone()),
                        family: Some(family.clone()),
                        baseline: baseline_values
                            .iter()
                            .map(|value| ObservationKey {
                                family: family.clone(),
                                actual_distance_mm: value.clone(),
                            })
                            .collect(),
                        candidate: candidate_values
                            .iter()
                            .map(|value| ObservationKey {
                                family: family.clone(),
                                actual_distance_mm: value.clone(),
                            })
                            .collect(),
                        count: missing_distance_count,
                    });
                }
                for value in candidate_values.iter().skip(baseline_values.len()) {
                    let key = ObservationKey {
                        family: family.clone(),
                        actual_distance_mm: value.clone(),
                    };
                    *new_hard_observations.entry(key).or_insert(0) += 1;
                }
                for value in baseline_values.iter().skip(candidate_values.len()) {
                    let key = ObservationKey {
                        family: family.clone(),
                        actual_distance_mm: value.clone(),
                    };
                    *removed_hard_observations.entry(key).or_insert(0) += 1;
                }
            }
        }
    } else {
        indeterminate_hard_comparison_count = 1;
        let baseline = observations_by_family(&request.baseline_samples[0])?;
        let candidate = observations_by_family(&request.candidate_samples[0])?;
        let families: BTreeSet<FamilyKey> = baseline
            .keys()
            .chain(candidate.keys())
            .filter(|family| is_hard_category(&family.category))
            .cloned()
            .collect();
        let mut emitted = false;
        for family in families {
            if unresolved_cap_categories
                .binary_search(&family.category)
                .is_ok()
            {
                continue;
            }
            emitted = true;
            indeterminate_hard_comparisons.push(IndeterminateHardComparison {
                reason: "semantic-repeats-disagree",
                category: Some(family.category.clone()),
                family: Some(family.clone()),
                baseline: baseline
                    .get(&family)
                    .into_iter()
                    .flatten()
                    .map(|value| ObservationKey {
                        family: family.clone(),
                        actual_distance_mm: value.clone(),
                    })
                    .collect(),
                candidate: candidate
                    .get(&family)
                    .into_iter()
                    .flatten()
                    .map(|value| ObservationKey {
                        family: family.clone(),
                        actual_distance_mm: value.clone(),
                    })
                    .collect(),
                count: 1,
            });
        }
        if !emitted {
            indeterminate_hard_comparisons.push(IndeterminateHardComparison {
                reason: "semantic-repeats-disagree",
                category: None,
                family: None,
                baseline: Vec::new(),
                candidate: Vec::new(),
                count: 1,
            });
        }
    }

    for category in &unresolved_cap_categories {
        if is_hard_category(category) {
            indeterminate_hard_comparisons.push(IndeterminateHardComparison {
                reason: "unresolved-cap",
                category: Some(category.clone()),
                family: None,
                baseline: Vec::new(),
                candidate: Vec::new(),
                count: 1,
            });
        }
    }
    indeterminate_hard_comparisons.sort();

    let mut new_scoped_silk_finding_count = 0usize;
    let mut new_scoped_silk_findings = BTreeMap::new();
    if silk_receipts_comparable {
        let candidate_receipt = request.candidate_silk_receipt.as_ref().ok_or_else(|| {
            EvidenceError::InvalidComparison("candidate silk receipt vanished".into())
        })?;
        let baseline_receipt = request.baseline_silk_receipt.as_ref().ok_or_else(|| {
            EvidenceError::InvalidComparison("baseline silk receipt vanished".into())
        })?;
        let scope: BTreeSet<String> = candidate_receipt
            .measurement_scope_refs
            .iter()
            .cloned()
            .collect();
        let baseline_silk = scoped_silk_finding_bag(baseline_receipt, &scope);
        let candidate_silk = scoped_silk_finding_bag(candidate_receipt, &scope);
        for (finding, candidate_count) in candidate_silk {
            let new_count =
                candidate_count.saturating_sub(baseline_silk.get(&finding).copied().unwrap_or(0));
            new_scoped_silk_finding_count += new_count;
            if new_count > 0 {
                new_scoped_silk_findings.insert(finding, new_count);
            }
        }
    }

    let instrument_conclusive = semantic_repeats_agree
        && unresolved_cap_categories.is_empty()
        && indeterminate_hard_comparison_count == 0;
    Ok(ComparisonParts {
        instrument_conclusive,
        semantic_repeats_agree,
        category_states,
        raw_global_capped_categories: all_caps.into_iter().collect(),
        unresolved_cap_categories,
        new_hard_observations: new_hard_observations
            .into_iter()
            .map(|(key, count)| BagEntry { key, count })
            .collect(),
        removed_hard_observations: removed_hard_observations
            .into_iter()
            .map(|(key, count)| BagEntry { key, count })
            .collect(),
        worsened_hard_observations: worsened_hard_observations
            .into_iter()
            .map(|((baseline, candidate), count)| WorsenedHardObservation {
                baseline,
                candidate,
                count,
            })
            .collect(),
        indeterminate_hard_comparisons,
        new_scoped_silk_findings: new_scoped_silk_findings
            .into_iter()
            .map(|(key, count)| BagEntry { key, count })
            .collect(),
        v2_new_hard_observation_count: new_hard_observation_count,
        v2_worsened_hard_observation_count: worsened_hard_observation_count,
        v2_indeterminate_hard_comparison_count: indeterminate_hard_comparison_count,
        v2_new_scoped_silk_finding_count: new_scoped_silk_finding_count,
    })
}

pub fn comparison_receipt_json(request_json: &str) -> Result<String, EvidenceError> {
    let request: ComparisonRequest = serde_json::from_str(request_json)?;
    let parts = comparison_parts(&request)?;
    let receipt = ComparisonReceipt {
        schema: "temper.drc-admission-comparison/v2",
        instrument_conclusive: parts.instrument_conclusive,
        semantic_repeats_agree: parts.semantic_repeats_agree,
        category_states: parts.category_states,
        raw_global_capped_categories: parts.raw_global_capped_categories,
        unresolved_cap_categories: parts.unresolved_cap_categories,
        new_hard_observation_count: parts.v2_new_hard_observation_count,
        worsened_hard_observation_count: parts.v2_worsened_hard_observation_count,
        // Keep the v2 count semantics: an unstable semantic repeat contributes
        // one, while a stable family with a missing distance contributes one
        // per paired observation. Cap states remain represented separately.
        indeterminate_hard_comparison_count: parts.v2_indeterminate_hard_comparison_count,
        new_scoped_silk_finding_count: parts.v2_new_scoped_silk_finding_count,
    };
    serde_json::to_string(&receipt).map_err(EvidenceError::Serialization)
}

/// Versioned exact comparison receipt for feasibility admission. The v2
/// endpoint above intentionally keeps its historical byte shape; this endpoint
/// carries canonical multiset deltas and derives every summary count from the
/// emitted identity entries.
pub fn comparison_receipt_v3_json(request_json: &str) -> Result<String, EvidenceError> {
    let request: ComparisonRequest = serde_json::from_str(request_json)?;
    let parts = comparison_parts(&request)?;
    let receipt = ComparisonReceiptV3 {
        schema: "temper.drc-admission-comparison/v3",
        instrument_conclusive: parts.instrument_conclusive,
        semantic_repeats_agree: parts.semantic_repeats_agree,
        category_states: parts.category_states,
        raw_global_capped_categories: parts.raw_global_capped_categories,
        unresolved_cap_categories: parts.unresolved_cap_categories,
        new_hard_observation_count: parts
            .new_hard_observations
            .iter()
            .map(|entry| entry.count)
            .sum(),
        worsened_hard_observation_count: parts
            .worsened_hard_observations
            .iter()
            .map(|entry| entry.count)
            .sum(),
        indeterminate_hard_comparison_count: parts
            .indeterminate_hard_comparisons
            .iter()
            .map(|entry| entry.count)
            .sum(),
        new_scoped_silk_finding_count: parts
            .new_scoped_silk_findings
            .iter()
            .map(|entry| entry.count)
            .sum(),
        new_hard_observations: parts.new_hard_observations,
        removed_hard_observations: parts.removed_hard_observations,
        worsened_hard_observations: parts.worsened_hard_observations,
        indeterminate_hard_comparisons: parts.indeterminate_hard_comparisons,
        new_scoped_silk_findings: parts.new_scoped_silk_findings,
    };
    serde_json::to_string(&receipt).map_err(EvidenceError::Serialization)
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

fn top_level_placement_span(block: &str) -> Result<Option<(usize, usize)>, EvidenceError> {
    let bytes = block.as_bytes();
    let mut depth = 0usize;
    let mut in_string = false;
    let mut escaped = false;
    for (index, byte) in bytes.iter().copied().enumerate() {
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
            b'(' => {
                if depth == 1
                    && bytes.get(index + 1..index + 3) == Some(b"at")
                    && bytes
                        .get(index + 3)
                        .is_some_and(|next| next.is_ascii_whitespace() || *next == b')')
                {
                    return Ok(Some((index, balanced_end(block, index)?)));
                }
                depth += 1;
            }
            b')' => depth = depth.saturating_sub(1),
            _ => {}
        }
    }
    Ok(None)
}

fn direct_child_spans(
    block: &str,
    wanted_head: &str,
) -> Result<Vec<(usize, usize)>, EvidenceError> {
    let bytes = block.as_bytes();
    let mut spans = Vec::new();
    let mut depth = 0usize;
    let mut in_string = false;
    let mut escaped = false;
    for (index, byte) in bytes.iter().copied().enumerate() {
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
            b'(' => {
                if depth == 1 {
                    let mut head_start = index + 1;
                    while bytes.get(head_start).is_some_and(u8::is_ascii_whitespace) {
                        head_start += 1;
                    }
                    let mut head_end = head_start;
                    while bytes.get(head_end).is_some_and(|next| {
                        !next.is_ascii_whitespace() && *next != b'(' && *next != b')'
                    }) {
                        head_end += 1;
                    }
                    if block.get(head_start..head_end) == Some(wanted_head) {
                        spans.push((index, balanced_end(block, index)?));
                    }
                }
                depth += 1;
            }
            b')' => depth = depth.saturating_sub(1),
            _ => {}
        }
    }
    Ok(spans)
}

fn at_values(expression: &str) -> Result<(f64, f64, f64), EvidenceError> {
    let values: Vec<&str> = expression
        .trim_matches(|character| character == '(' || character == ')')
        .split_ascii_whitespace()
        .collect();
    if values.len() < 3 || values.len() > 4 || values[0] != "at" {
        return Err(EvidenceError::MalformedBoard(format!(
            "unsupported placement expression {expression}"
        )));
    }
    let parse = |value: &str| {
        value
            .parse::<f64>()
            .map_err(|_| EvidenceError::MalformedBoard(format!("invalid placement scalar {value}")))
    };
    Ok((
        parse(values[1])?,
        parse(values[2])?,
        values.get(3).map_or(Ok(0.0), |value| parse(value))?,
    ))
}

fn sexpr_tokens(text: &str) -> Result<Vec<String>, EvidenceError> {
    let bytes = text.as_bytes();
    let mut tokens = Vec::new();
    let mut index = 0usize;
    while index < bytes.len() {
        if bytes[index].is_ascii_whitespace() {
            index += 1;
        } else if matches!(bytes[index], b'(' | b')') {
            tokens.push((bytes[index] as char).to_string());
            index += 1;
        } else if bytes[index] == b'"' {
            let start = index;
            index += 1;
            let mut escaped = false;
            while index < bytes.len() {
                let byte = bytes[index];
                index += 1;
                if escaped {
                    escaped = false;
                } else if byte == b'\\' {
                    escaped = true;
                } else if byte == b'"' {
                    break;
                }
            }
            if bytes.get(index.saturating_sub(1)) != Some(&b'"') {
                return Err(EvidenceError::MalformedBoard(
                    "unterminated string in footprint".to_string(),
                ));
            }
            tokens.push(text[start..index].to_string());
        } else {
            let start = index;
            while bytes
                .get(index)
                .is_some_and(|byte| !byte.is_ascii_whitespace() && *byte != b'(' && *byte != b')')
            {
                index += 1;
            }
            tokens.push(text[start..index].to_string());
        }
    }
    Ok(tokens)
}

/// Canonicalize only the representation changes made by the established
/// exact placement writer: layout whitespace, the footprint's root `(at)`,
/// and pad body angles re-expressed relative to that root angle. Pad offsets
/// and every non-placement child token remain identity-bearing.
fn rigid_placement_projection(block: &str) -> Result<Vec<String>, EvidenceError> {
    let (root_start, root_end) = top_level_placement_span(block)?.ok_or_else(|| {
        EvidenceError::MalformedBoard("footprint has no top-level placement".to_string())
    })?;
    let (_, _, root_angle) = at_values(&block[root_start..root_end])?;
    let mut replacements = vec![(root_start, root_end, "(at <rigid-placement>)".to_string())];
    for (pad_start, pad_end) in direct_child_spans(block, "pad")? {
        let pad = &block[pad_start..pad_end];
        let (relative_start, relative_end) = top_level_placement_span(pad)?
            .ok_or_else(|| EvidenceError::MalformedBoard("pad has no placement".to_string()))?;
        let (x, y, pad_angle) = at_values(&pad[relative_start..relative_end])?;
        let mut local_angle = (pad_angle - root_angle).rem_euclid(360.0);
        if local_angle.abs() < 1e-12 || (360.0 - local_angle).abs() < 1e-12 {
            local_angle = 0.0;
        }
        replacements.push((
            pad_start + relative_start,
            pad_start + relative_end,
            format!("(at {x} {y} {local_angle})"),
        ));
    }
    replacements.sort_by_key(|replacement| replacement.0);
    let mut projected = block.to_string();
    for (start, end, replacement) in replacements.into_iter().rev() {
        projected.replace_range(start..end, &replacement);
    }
    sexpr_tokens(&projected)
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

fn silk_child_count(block: &str) -> Result<usize, EvidenceError> {
    [
        "fp_text",
        "fp_text_box",
        "fp_line",
        "fp_rect",
        "fp_circle",
        "fp_arc",
        "fp_poly",
    ]
    .into_iter()
    .try_fold(0usize, |count, head| {
        Ok(count + direct_child_spans(block, head)?.len())
    })
}

fn scoped_sample_bag(
    findings: &[RawFinding],
    leaf_pairs: &BTreeSet<[String; 2]>,
    sample_index: usize,
) -> Result<BTreeMap<ScopedSilkFinding, usize>, EvidenceError> {
    let mut bag = BTreeMap::new();
    for (finding_index, finding) in findings.iter().enumerate() {
        if bare_category(&finding.category) != "silk_overlap" {
            return Err(EvidenceError::InvalidComparison(format!(
                "scoped silk cell contains {}",
                finding.category
            )));
        }
        let pair = match silk_finding_subject(finding)? {
            SilkFindingSubject::SelfOverlap { .. } => continue,
            SilkFindingSubject::Pair { pair } => pair,
        };
        if !leaf_pairs.contains(&pair) {
            continue;
        }
        // Scoped silk comparison deliberately omits absolute positions: a
        // rigid footprint move changes those coordinates even when the same
        // two silk primitives remain in contact. Primitive descriptions are
        // retained so an equal-count Text->Segment substitution is new
        // evidence rather than an invisible footprint-pair count tie.
        let (message_semantics, _actual_distance_mm) = split_actual_distance(&finding.description)
            .map_err(|()| EvidenceError::MalformedDistance {
                sample: sample_index,
                finding: finding_index,
                description: finding.description.clone(),
            })?;
        let mut item_descriptions: Vec<String> = finding
            .items
            .iter()
            .map(|item| item.description.clone())
            .collect();
        item_descriptions.sort();
        *bag.entry(ScopedSilkFinding {
            pair,
            message_semantics,
            item_descriptions,
        })
        .or_insert(0) += 1;
    }
    Ok(bag)
}

fn cell_resolution(
    cell: &SilkCell,
    leaf_pairs: &BTreeSet<[String; 2]>,
    safe_ceiling: u32,
) -> Result<(bool, bool, Vec<BTreeMap<ScopedSilkFinding, usize>>), EvidenceError> {
    let counts_match_findings = cell.sample_counts.len() == cell.sample_findings.len()
        && cell
            .sample_counts
            .iter()
            .zip(&cell.sample_findings)
            .all(|(count, findings)| *count as usize == findings.len());
    let safely_below_cap = counts_match_findings
        && cell.sample_counts.len() == 3
        && cell.sample_counts.iter().all(|count| *count < safe_ceiling);
    let bags = cell
        .sample_findings
        .iter()
        .enumerate()
        .map(|(sample_index, findings)| scoped_sample_bag(findings, leaf_pairs, sample_index))
        .collect::<Result<Vec<_>, _>>()?;
    let samples_agree = bags.len() == 3
        && bags
            .first()
            .is_some_and(|first| bags.iter().all(|bag| bag == first));
    Ok((safely_below_cap, samples_agree, bags))
}

pub fn silk_cell_check_json(request_json: &str) -> Result<String, EvidenceError> {
    let request: SilkCellCheckRequest = serde_json::from_str(request_json)?;
    let pairs = request
        .pairs
        .iter()
        .map(|pair| normalized_pair(&pair[0], &pair[1]))
        .collect();
    let (safely_below_cap, semantic_samples_agree, _bags) =
        cell_resolution(&request.cell, &pairs, request.safe_ceiling)?;
    serde_json::to_string(&SilkCellCheckReceipt {
        schema: "temper.silk-cell-check/v1",
        sample_count: request.cell.sample_findings.len(),
        safely_below_cap,
        semantic_samples_agree,
        resolved: safely_below_cap && semantic_samples_agree,
    })
    .map_err(EvidenceError::Serialization)
}

fn item_partition_complete(
    leaf: &SilkLeaf,
    subject: &BTreeMap<String, String>,
) -> Result<bool, EvidenceError> {
    let regions: Vec<&SilkItemRegion> = leaf
        .cells
        .iter()
        .filter_map(|cell| cell.item_region.as_ref())
        .collect();
    if regions.is_empty() {
        return Ok(leaf.cells.len() == 1);
    }
    if regions.len() != leaf.cells.len() || leaf.pairs.len() != 1 {
        return Ok(false);
    }
    let pair = normalized_pair(&leaf.pairs[0][0], &leaf.pairs[0][1]);
    let first_count = silk_child_count(subject.get(&pair[0]).ok_or_else(|| {
        EvidenceError::MissingDeclaredReference {
            reference: pair[0].clone(),
        }
    })?)?;
    let second_count = silk_child_count(subject.get(&pair[1]).ok_or_else(|| {
        EvidenceError::MissingDeclaredReference {
            reference: pair[1].clone(),
        }
    })?)?;
    let mut coverage = BTreeMap::<(usize, usize), usize>::new();
    for region in regions {
        if normalized_pair(&region.pair[0], &region.pair[1]) != pair
            || region.pair != pair
            || region.first_item_count != first_count
            || region.second_item_count != second_count
            || region.first_indices.is_empty()
            || region.second_indices.is_empty()
            || region
                .first_indices
                .iter()
                .any(|index| *index >= first_count)
            || region
                .second_indices
                .iter()
                .any(|index| *index >= second_count)
        {
            return Ok(false);
        }
        for first in &region.first_indices {
            for second in &region.second_indices {
                *coverage.entry((*first, *second)).or_insert(0) += 1;
            }
        }
    }
    Ok(coverage.len() == first_count.saturating_mul(second_count)
        && coverage.values().all(|count| *count == 1))
}

/// Validate a complete mutation-cone silk receipt. Board text is parsed only
/// to census exact footprint blocks; Python remains responsible for staging
/// KiCad projects and transporting raw leaf results.
pub fn silk_scope_receipt_json(request_json: &str) -> Result<String, EvidenceError> {
    let request: SilkScopeRequest = serde_json::from_str(request_json)?;
    if request.instrument_context.schema != "temper.kicad-drc-instrument/v1"
        || request
            .instrument_context
            .kicad_cli_version
            .trim()
            .is_empty()
        || request.instrument_context.runner.trim().is_empty()
        || request.instrument_context.runner_flags.is_empty()
        || [
            &request.instrument_context.project_sha256,
            &request.instrument_context.dru_sha256,
            &request.instrument_context.fp_lib_table_sha256,
            &request.instrument_context.libraries_sha256,
        ]
        .iter()
        .any(|digest| digest.len() != 64 || !digest.bytes().all(|byte| byte.is_ascii_hexdigit()))
    {
        return Err(EvidenceError::InvalidComparison(
            "invalid scoped silk instrument context".to_string(),
        ));
    }
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
    let mut non_rigid = Vec::new();
    for reference in &actual {
        let source_block = source
            .get(reference)
            .expect("actual mutations are drawn from the source census");
        let subject_block = subject
            .get(reference)
            .expect("source and subject footprint censuses already match");
        if rigid_placement_projection(source_block)? != rigid_placement_projection(subject_block)? {
            non_rigid.push(reference.clone());
        }
    }
    if !non_rigid.is_empty() {
        return Err(EvidenceError::NonRigidMutation {
            references: non_rigid,
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
    let mut scoped_findings: BTreeMap<ScopedSilkFinding, usize> = BTreeMap::new();
    let mut unresolved_leaf_count = 0usize;
    for leaf in &request.leaves {
        for pair in &leaf.pairs {
            *coverage
                .entry(normalized_pair(&pair[0], &pair[1]))
                .or_insert(0) += 1;
        }
        let leaf_pairs: BTreeSet<[String; 2]> = leaf
            .pairs
            .iter()
            .map(|pair| normalized_pair(&pair[0], &pair[1]))
            .collect();
        let mut leaf_resolved = !leaf.cells.is_empty() && item_partition_complete(leaf, &subject)?;
        let mut stable_bags = Vec::new();
        for cell in &leaf.cells {
            let (safely_below_cap, samples_agree, bags) =
                cell_resolution(cell, &leaf_pairs, safe_ceiling)?;
            leaf_resolved &= safely_below_cap && samples_agree;
            if samples_agree {
                stable_bags.push(bags[0].clone());
            }
        }
        if !leaf_resolved {
            unresolved_leaf_count += 1;
            continue;
        }
        for bag in stable_bags {
            for (finding, count) in bag {
                *scoped_findings.entry(finding).or_insert(0) += count;
            }
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
    let instrument_context_json =
        serde_json::to_vec(&request.instrument_context).map_err(EvidenceError::Serialization)?;
    let partition_manifest_json =
        serde_json::to_vec(&request.leaves).map_err(EvidenceError::Serialization)?;
    let leaf_hashes = request
        .leaves
        .iter()
        .map(|leaf| {
            serde_json::to_vec(leaf)
                .map(|bytes| sha256_hex(&bytes))
                .map_err(EvidenceError::Serialization)
        })
        .collect::<Result<Vec<_>, _>>()?;
    let receipt = SilkScopeReceipt {
        schema: "temper.silk-mutation-scope/v4".to_string(),
        source_sha256: sha256_hex(request.source_board.as_bytes()),
        subject_sha256: sha256_hex(request.subject_board.as_bytes()),
        silk_projection_sha256: silk_projection_digest(&subject),
        instrument_context_sha256: sha256_hex(&instrument_context_json),
        instrument_context: request.instrument_context,
        partition_manifest_sha256: sha256_hex(&partition_manifest_json),
        leaf_hashes,
        leaves: request.leaves,
        safe_ceiling,
        declared_refs: declared.into_iter().collect(),
        actual_mutated_refs: actual.iter().cloned().collect(),
        rigid_only_mutated_refs: actual.into_iter().collect(),
        measurement_scope_refs: scope.into_iter().collect(),
        expected_pair_count: expected.len(),
        covered_pair_count: expected.intersection(&covered).count(),
        missing_pairs,
        duplicate_pairs,
        foreign_pairs,
        unresolved_leaf_count,
        finding_count: scoped_findings.values().sum(),
        findings: scoped_findings
            .into_iter()
            .map(|(key, count)| BagEntry { key, count })
            .collect(),
        complete,
        category_state: category_state.to_string(),
        execution: request.execution,
    };
    serde_json::to_string(&receipt).map_err(EvidenceError::Serialization)
}

/// Extract the canonical footprint pair from one raw `silk_overlap` record.
/// The raw item descriptions remain KiCad's oracle; Rust owns the parsing and
/// rejects ambiguous records rather than letting Python invent a pair.
fn silk_finding_subject(finding: &RawFinding) -> Result<SilkFindingSubject, EvidenceError> {
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
    match references.as_slice() {
        [reference] => Ok(SilkFindingSubject::SelfOverlap {
            reference: reference.clone(),
        }),
        [first, second] => Ok(SilkFindingSubject::Pair {
            pair: normalized_pair(first, second),
        }),
        _ => Err(EvidenceError::AmbiguousSilkPair { references }),
    }
}

fn silk_finding_pair(finding: &RawFinding) -> Result<[String; 2], EvidenceError> {
    match silk_finding_subject(finding)? {
        SilkFindingSubject::Pair { pair } => Ok(pair),
        SilkFindingSubject::SelfOverlap { reference } => Err(EvidenceError::AmbiguousSilkPair {
            references: vec![reference],
        }),
    }
}

pub fn silk_finding_pair_json(finding_json: &str) -> Result<String, EvidenceError> {
    let finding: RawFinding = serde_json::from_str(finding_json)?;
    serde_json::to_string(&silk_finding_pair(&finding)?).map_err(EvidenceError::Serialization)
}

pub fn silk_finding_subject_json(finding_json: &str) -> Result<String, EvidenceError> {
    let finding: RawFinding = serde_json::from_str(finding_json)?;
    serde_json::to_string(&silk_finding_subject(&finding)?).map_err(EvidenceError::Serialization)
}

#[cfg(feature = "python")]
#[pyfunction(name = "drc_evidence_envelope_json")]
fn evidence_envelope_json_py(samples_json: &str) -> pyo3::PyResult<String> {
    evidence_envelope_json(samples_json)
        .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))
}

#[cfg(feature = "python")]
#[pyfunction(name = "drc_silk_scope_receipt_json")]
fn silk_scope_receipt_json_py(request_json: &str) -> pyo3::PyResult<String> {
    silk_scope_receipt_json(request_json)
        .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))
}

#[cfg(feature = "python")]
#[pyfunction(name = "drc_silk_cell_check_json")]
fn silk_cell_check_json_py(request_json: &str) -> pyo3::PyResult<String> {
    silk_cell_check_json(request_json)
        .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))
}

#[cfg(feature = "python")]
#[pyfunction(name = "drc_admission_comparison_json")]
fn comparison_receipt_json_py(request_json: &str) -> pyo3::PyResult<String> {
    comparison_receipt_json(request_json)
        .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))
}

#[cfg(feature = "python")]
#[pyfunction(name = "drc_admission_comparison_v3_json")]
fn comparison_receipt_v3_json_py(request_json: &str) -> pyo3::PyResult<String> {
    comparison_receipt_v3_json(request_json)
        .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))
}

#[cfg(feature = "python")]
pub fn register(module: &pyo3::Bound<'_, pyo3::types::PyModule>) -> pyo3::PyResult<()> {
    use pyo3::prelude::PyModuleMethods;
    module.add_function(pyo3::wrap_pyfunction!(evidence_envelope_json_py, module)?)?;
    module.add_function(pyo3::wrap_pyfunction!(silk_scope_receipt_json_py, module)?)?;
    module.add_function(pyo3::wrap_pyfunction!(silk_cell_check_json_py, module)?)?;
    module.add_function(pyo3::wrap_pyfunction!(comparison_receipt_json_py, module)?)?;
    module.add_function(pyo3::wrap_pyfunction!(
        comparison_receipt_v3_json_py,
        module
    )?)?;
    Ok(())
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
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

    #[cfg_attr(test, test)]
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

    fn missing_connection(provider: &str, net: &str, component: &str) -> RawFinding {
        RawFinding {
            category: "unconnected_items".to_string(),
            description: "Missing connection between items".to_string(),
            items: vec![
                RawItem {
                    description: format!("PTH pad 2 [{net}] of {component}"),
                    pos: RawPosition::new("102.5", "243.0"),
                },
                RawItem {
                    description: format!("Track [{net}] on In3.Cu, length {provider} mm"),
                    pos: RawPosition::new("98.95", "240.15"),
                },
            ],
        }
    }

    #[cfg_attr(test, test)]
    fn missing_connection_provider_churn_is_stable_but_identity_changes_are_not() {
        let baseline = missing_connection("0.1414", "rtd_sense_p", "J1");
        let provider_changed = missing_connection("8.9000", "rtd_sense_p", "J1");
        let envelope = evidence_envelope(&[
            vec![baseline.clone()],
            vec![provider_changed.clone()],
            vec![baseline.clone()],
        ])
        .expect("valid production-shaped missing connection");
        assert!(envelope.observation.stable);
        assert!(!envelope.raw.stable);

        for changed in [
            missing_connection("8.9000", "different_net", "J1"),
            missing_connection("8.9000", "rtd_sense_p", "J2"),
        ] {
            let changed = evidence_envelope(&[vec![baseline.clone()], vec![changed]])
                .expect("valid identity mutation");
            assert!(!changed.observation.stable);
        }
    }

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    fn instrument_context() -> serde_json::Value {
        serde_json::json!({
            "schema": "temper.kicad-drc-instrument/v1",
            "kicad_cli_version": "10.0.5",
            "runner": "test-runner/v1",
            "runner_flags": ["drc", "--format", "json", "--all-track-errors", "single-thread"],
            "project_sha256": "1".repeat(64),
            "dru_sha256": "2".repeat(64),
            "fp_lib_table_sha256": "3".repeat(64),
            "libraries_sha256": "4".repeat(64)
        })
    }

    #[cfg_attr(test, test)]
    fn silk_scope_receipt_binds_actual_mutation_and_exact_pair_coverage() {
        let request = serde_json::json!({
            "source_board": board("10 0"),
            "subject_board": board("11 0"),
            "declared_refs": ["R2"],
            "use_declared_scope": false,
            "raw_global_capped": true,
            "instrument_context": instrument_context(),
            "leaves": [
                {"pairs": [["R1", "R2"]], "cells": [{"sample_counts": [0, 0, 0], "sample_findings": [[], [], []]}]},
                {"pairs": [["R2", "R3"]], "cells": [{"sample_counts": [0, 0, 0], "sample_findings": [[], [], []]}]}
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

    #[cfg_attr(test, test)]
    fn silk_scope_rejects_undeclared_mutation() {
        let request = serde_json::json!({
            "source_board": board("10 0"),
            "subject_board": board("10 0").replace("(at 20 0)", "(at 21 0)"),
            "declared_refs": ["R2"],
            "use_declared_scope": false,
            "raw_global_capped": true,
            "instrument_context": instrument_context(),
            "leaves": []
        });
        let error = silk_scope_receipt_json(&request.to_string())
            .expect_err("undeclared mutation must fail closed");
        assert!(matches!(error, EvidenceError::UndeclaredMutation { .. }));
    }

    #[cfg_attr(test, test)]
    fn silk_scope_rejects_declared_non_rigid_mutation() {
        let request = serde_json::json!({
            "source_board": board("10 0"),
            "subject_board": board("10 0").replace(
                "(property \"Reference\" \"R2\")",
                "(property \"Reference\" \"R2\") (fp_text value \"changed\")"
            ),
            "declared_refs": ["R2"],
            "use_declared_scope": false,
            "raw_global_capped": true,
            "instrument_context": instrument_context(),
            "leaves": []
        });
        let error = silk_scope_receipt_json(&request.to_string())
            .expect_err("declared child mutation must fail before measurement");
        assert!(matches!(error, EvidenceError::NonRigidMutation { .. }));
    }

    #[cfg_attr(test, test)]
    fn rigid_projection_accepts_writer_formatting_and_relative_pad_reorientation() {
        let source = r#"(footprint "Test:R" (property "Reference" "R1") (at 0 0)
  (pad "1" smd rect (at 1 2) (size 1 1) (layers "F.Cu")))"#;
        let subject = r#"(footprint "Test:R"
  (property "Reference" "R1")
  (at 10 20 180)
  (pad "1" smd rect
    (at 1 2 180)
    (size 1 1)
    (layers "F.Cu")
  )
)"#;
        assert_eq!(
            rigid_placement_projection(source).expect("source projection"),
            rigid_placement_projection(subject).expect("subject projection")
        );
        let moved_pad = subject.replace("(at 1 2 180)", "(at 1.1 2 180)");
        assert_ne!(
            rigid_placement_projection(source).expect("source projection"),
            rigid_placement_projection(&moved_pad).expect("mutated projection")
        );
    }

    #[cfg_attr(test, test)]
    fn silk_scope_marks_duplicate_missing_disagreeing_and_near_cap_unresolved() {
        let request = serde_json::json!({
            "source_board": board("10 0"),
            "subject_board": board("10 0"),
            "declared_refs": ["R2"],
            "use_declared_scope": true,
            "raw_global_capped": true,
            "instrument_context": instrument_context(),
            "leaves": [
                {"pairs": [["R1", "R2"], ["R1", "R2"]], "cells": [{"sample_counts": [179, 179, 179], "sample_findings": [[], [], []]}]},
                {"pairs": [["R2", "R3"]], "cells": [{"sample_counts": [1, 2, 1], "sample_findings": [[], [], []]}]}
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

    #[cfg_attr(test, test)]
    fn silk_cell_rejects_equal_counts_with_different_semantic_sets() {
        let first = serde_json::json!({
            "type": "silk_overlap",
            "description": "Silkscreen overlap",
            "items": [
                {"description": "Text REF of R1 on F.Silkscreen", "pos": {"x": 0, "y": 0}},
                {"description": "Arc of R2 on F.Silkscreen", "pos": {"x": 1, "y": 1}}
            ]
        });
        let changed = serde_json::json!({
            "type": "silk_overlap",
            "description": "Silkscreen overlap",
            "items": [
                {"description": "Segment of R1 on F.Silkscreen", "pos": {"x": 0, "y": 0}},
                {"description": "Arc of R2 on F.Silkscreen", "pos": {"x": 1, "y": 1}}
            ]
        });
        let request = serde_json::json!({
            "pairs": [["R1", "R2"]],
            "safe_ceiling": 179,
            "cell": {
                "sample_counts": [1, 1, 1],
                "sample_findings": [[first.clone()], [changed], [first]]
            }
        });
        let receipt: serde_json::Value = serde_json::from_str(
            &silk_cell_check_json(&request.to_string()).expect("typed cell receipt"),
        )
        .expect("valid receipt JSON");
        assert_eq!(receipt["safely_below_cap"], true);
        assert_eq!(receipt["semantic_samples_agree"], false);
        assert_eq!(receipt["resolved"], false);
    }

    #[cfg_attr(test, test)]
    fn silk_scope_reports_missing_and_foreign_pairs_independently() {
        let missing_request = serde_json::json!({
            "source_board": board("10 0"),
            "subject_board": board("10 0"),
            "declared_refs": ["R2"],
            "use_declared_scope": true,
            "raw_global_capped": true,
            "instrument_context": instrument_context(),
            "leaves": [
                {"pairs": [["R1", "R2"]], "cells": [{"sample_counts": [0, 0, 0], "sample_findings": [[], [], []]}]}
            ]
        });
        let missing: serde_json::Value = serde_json::from_str(
            &silk_scope_receipt_json(&missing_request.to_string()).expect("missing receipt"),
        )
        .expect("valid receipt JSON");
        assert_eq!(missing["missing_pairs"], serde_json::json!([["R2", "R3"]]));
        assert_eq!(missing["foreign_pairs"], serde_json::json!([]));

        let foreign_request = serde_json::json!({
            "source_board": board("10 0"),
            "subject_board": board("10 0"),
            "declared_refs": ["R2"],
            "use_declared_scope": true,
            "raw_global_capped": true,
            "instrument_context": instrument_context(),
            "leaves": [
                {"pairs": [["R1", "R2"], ["R2", "R3"], ["R1", "R3"]], "cells": [{"sample_counts": [0, 0, 0], "sample_findings": [[], [], []]}]}
            ]
        });
        let foreign: serde_json::Value = serde_json::from_str(
            &silk_scope_receipt_json(&foreign_request.to_string()).expect("foreign receipt"),
        )
        .expect("valid receipt JSON");
        assert_eq!(foreign["missing_pairs"], serde_json::json!([]));
        assert_eq!(foreign["foreign_pairs"], serde_json::json!([["R1", "R3"]]));
    }

    #[cfg_attr(test, test)]
    fn silk_finding_subject_is_rust_owned_and_ambiguous_records_fail() {
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
        let self_overlap = finding.to_string().replace(" of C3 on", " of R2 on");
        assert_eq!(
            silk_finding_subject_json(&self_overlap).expect("one-ref self overlap"),
            r#"{"kind":"self-overlap","reference":"R2"}"#
        );
        assert!(matches!(
            silk_finding_pair_json(&self_overlap).expect_err("self overlap is not a pair"),
            EvidenceError::AmbiguousSilkPair { .. }
        ));
        let ambiguous = serde_json::json!({
            "type": "silk_overlap",
            "description": "Silkscreen overlap",
            "items": []
        });
        assert!(matches!(
            silk_finding_subject_json(&ambiguous.to_string())
                .expect_err("zero-ref finding is ambiguous"),
            EvidenceError::AmbiguousSilkPair { .. }
        ));
    }

    fn creepage_value(actual: &str, provider: &str) -> serde_json::Value {
        serde_json::json!({
            "type": "creepage",
            "description": format!("Creepage violation (rule 'HV to LV' creepage 12.6000 mm; actual {actual} mm)"),
            "items": [
                {"description": "Pad 2 [HV] of R14 on F.Cu", "pos": {"x": 1, "y": 2}},
                {"description": format!("Track [LV] on F.Cu, length {provider} mm"), "pos": {"x": 3, "y": 4}}
            ]
        })
    }

    #[cfg_attr(test, test)]
    fn admission_comparison_ranks_hard_distances_after_provider_normalization() {
        let baseline =
            ["0.8", "11.9", "0.8"].map(|provider| vec![creepage_value("10.2", provider)]);
        let candidate =
            ["11.9", "0.8", "11.9"].map(|provider| vec![creepage_value("10.1", provider)]);
        let request = serde_json::json!({
            "baseline_samples": baseline,
            "candidate_samples": candidate,
            "baseline_capped_categories": [],
            "candidate_capped_categories": [],
            "baseline_silk_receipt": null,
            "candidate_silk_receipt": null
        });
        let receipt: serde_json::Value = serde_json::from_str(
            &comparison_receipt_json(&request.to_string()).expect("comparable evidence"),
        )
        .expect("valid receipt");
        assert_eq!(receipt["semantic_repeats_agree"], true);
        assert_eq!(receipt["instrument_conclusive"], true);
        assert_eq!(receipt["new_hard_observation_count"], 0);
        assert_eq!(receipt["worsened_hard_observation_count"], 1);
        assert_eq!(receipt["indeterminate_hard_comparison_count"], 0);
    }

    #[cfg_attr(test, test)]
    fn admission_comparison_v3_empty_delta_is_canonical_and_count_derived() {
        let request = serde_json::json!({
            "baseline_samples": [[], [], []],
            "candidate_samples": [[], [], []],
            "baseline_capped_categories": [],
            "candidate_capped_categories": [],
            "baseline_silk_receipt": null,
            "candidate_silk_receipt": null
        });
        let receipt: serde_json::Value = serde_json::from_str(
            &comparison_receipt_v3_json(&request.to_string()).expect("empty v3 comparison"),
        )
        .expect("valid v3 comparison receipt");

        assert_eq!(receipt["schema"], "temper.drc-admission-comparison/v3");
        assert_eq!(receipt["new_hard_observations"], serde_json::json!([]));
        assert_eq!(receipt["removed_hard_observations"], serde_json::json!([]));
        assert_eq!(receipt["worsened_hard_observations"], serde_json::json!([]));
        assert_eq!(
            receipt["indeterminate_hard_comparisons"],
            serde_json::json!([])
        );
        assert_eq!(receipt["new_scoped_silk_findings"], serde_json::json!([]));
        assert_eq!(receipt["new_hard_observation_count"], 0);
        assert_eq!(receipt["worsened_hard_observation_count"], 0);
        assert_eq!(receipt["indeterminate_hard_comparison_count"], 0);
        assert_eq!(receipt["new_scoped_silk_finding_count"], 0);
    }

    fn comparison_request(
        baseline_samples: Vec<Vec<RawFinding>>,
        candidate_samples: Vec<Vec<RawFinding>>,
    ) -> serde_json::Value {
        serde_json::json!({
            "baseline_samples": baseline_samples,
            "candidate_samples": candidate_samples,
            "baseline_capped_categories": [],
            "candidate_capped_categories": [],
            "baseline_silk_receipt": null,
            "candidate_silk_receipt": null
        })
    }

    #[cfg_attr(test, test)]
    fn admission_comparison_v3_preserves_equal_count_identity_substitution() {
        let baseline = creepage("10.2", "V_BUS_SENSE", "R14", "0.8");
        let candidate = creepage("10.2", "OTHER_NET", "R14", "0.8");
        let request = comparison_request(
            vec![
                vec![baseline.clone()],
                vec![baseline.clone()],
                vec![baseline],
            ],
            vec![
                vec![candidate.clone()],
                vec![candidate.clone()],
                vec![candidate],
            ],
        );
        let receipt: serde_json::Value = serde_json::from_str(
            &comparison_receipt_v3_json(&request.to_string()).expect("v3 substitution"),
        )
        .expect("valid v3 substitution receipt");

        assert_eq!(receipt["instrument_conclusive"], true);
        assert_eq!(receipt["new_hard_observation_count"], 1);
        assert_eq!(receipt["removed_hard_observations"][0]["count"], 1);
        assert_eq!(receipt["new_hard_observations"][0]["count"], 1);
        assert_ne!(
            receipt["new_hard_observations"][0]["key"]["family"]["nets"],
            receipt["removed_hard_observations"][0]["key"]["family"]["nets"]
        );
    }

    #[cfg_attr(test, test)]
    fn admission_comparison_v3_retains_new_multiplicity() {
        let finding = creepage("10.2", "V_BUS_SENSE", "R14", "0.8");
        let request = comparison_request(
            vec![
                vec![finding.clone()],
                vec![finding.clone()],
                vec![finding.clone()],
            ],
            vec![
                vec![finding.clone(), finding.clone()],
                vec![finding.clone(), finding.clone()],
                vec![finding.clone(), finding],
            ],
        );
        let receipt: serde_json::Value = serde_json::from_str(
            &comparison_receipt_v3_json(&request.to_string()).expect("v3 multiplicity"),
        )
        .expect("valid v3 multiplicity receipt");

        assert_eq!(receipt["new_hard_observation_count"], 1);
        assert_eq!(
            receipt["new_hard_observations"].as_array().unwrap().len(),
            1
        );
        assert_eq!(receipt["new_hard_observations"][0]["count"], 1);
    }

    #[cfg_attr(test, test)]
    fn admission_comparison_v3_emits_exact_worsened_distance_pair() {
        let baseline = creepage("10.2", "V_BUS_SENSE", "R14", "0.8");
        let candidate = creepage("10.1", "V_BUS_SENSE", "R14", "0.8");
        let request = comparison_request(
            vec![
                vec![baseline.clone()],
                vec![baseline.clone()],
                vec![baseline],
            ],
            vec![
                vec![candidate.clone()],
                vec![candidate.clone()],
                vec![candidate],
            ],
        );
        let receipt: serde_json::Value = serde_json::from_str(
            &comparison_receipt_v3_json(&request.to_string()).expect("v3 worsened distance"),
        )
        .expect("valid v3 worsened receipt");
        let worsened = &receipt["worsened_hard_observations"][0];

        assert_eq!(receipt["worsened_hard_observation_count"], 1);
        assert_eq!(worsened["count"], 1);
        assert_eq!(worsened["baseline"]["actual_distance_mm"], "10.2");
        assert_eq!(worsened["candidate"]["actual_distance_mm"], "10.1");
    }

    #[cfg_attr(test, test)]
    fn admission_comparison_v3_represents_unstable_and_capped_hard_evidence_as_indeterminate() {
        let finding = |actual: &str| creepage(actual, "V_BUS_SENSE", "R14", "0.8");
        let unstable = serde_json::json!({
            "baseline_samples": [[finding("10.2")], [finding("10.3")], [finding("10.2")]],
            "candidate_samples": [[finding("10.2")], [finding("10.2")], [finding("10.2")]],
            "baseline_capped_categories": [],
            "candidate_capped_categories": [],
            "baseline_silk_receipt": null,
            "candidate_silk_receipt": null
        });
        let unstable_receipt: serde_json::Value = serde_json::from_str(
            &comparison_receipt_v3_json(&unstable.to_string()).expect("v3 unstable evidence"),
        )
        .expect("valid unstable v3 receipt");
        assert_eq!(unstable_receipt["instrument_conclusive"], false);
        assert_eq!(
            unstable_receipt["new_hard_observations"],
            serde_json::json!([])
        );
        assert_eq!(
            unstable_receipt["worsened_hard_observations"],
            serde_json::json!([])
        );
        assert_eq!(
            unstable_receipt["indeterminate_hard_comparisons"][0]["reason"],
            "semantic-repeats-disagree"
        );
        assert_eq!(unstable_receipt["indeterminate_hard_comparison_count"], 1);

        let capped = serde_json::json!({
            "baseline_samples": [[finding("10.2")], [finding("10.2")], [finding("10.2")]],
            "candidate_samples": [[finding("10.1")], [finding("10.1")], [finding("10.1")]],
            "baseline_capped_categories": ["creepage"],
            "candidate_capped_categories": ["creepage"],
            "baseline_silk_receipt": null,
            "candidate_silk_receipt": null
        });
        let capped_receipt: serde_json::Value = serde_json::from_str(
            &comparison_receipt_v3_json(&capped.to_string()).expect("v3 capped evidence"),
        )
        .expect("valid capped v3 receipt");
        assert_eq!(capped_receipt["instrument_conclusive"], false);
        assert_eq!(
            capped_receipt["new_hard_observations"],
            serde_json::json!([])
        );
        assert_eq!(
            capped_receipt["worsened_hard_observations"],
            serde_json::json!([])
        );
        assert_eq!(
            capped_receipt["indeterminate_hard_comparisons"][0]["reason"],
            "unresolved-cap"
        );
        assert_eq!(
            capped_receipt["indeterminate_hard_comparisons"][0]["category"],
            "creepage"
        );
        assert_eq!(capped_receipt["indeterminate_hard_comparison_count"], 1);
    }

    #[cfg_attr(test, test)]
    fn admission_comparison_v2_empty_request_is_byte_stable() {
        let request =
            comparison_request(vec![vec![], vec![], vec![]], vec![vec![], vec![], vec![]]);
        assert_eq!(
            comparison_receipt_json(&request.to_string()).expect("v2 comparison"),
            r#"{"schema":"temper.drc-admission-comparison/v2","instrument_conclusive":true,"semantic_repeats_agree":true,"category_states":{},"raw_global_capped_categories":[],"unresolved_cap_categories":[],"new_hard_observation_count":0,"worsened_hard_observation_count":0,"indeterminate_hard_comparison_count":0,"new_scoped_silk_finding_count":0}"#
        );
    }

    #[cfg_attr(test, test)]
    fn admission_comparison_allows_only_complete_silk_scope_to_resolve_a_cap() {
        let scope_request = serde_json::json!({
            "source_board": board("10 0"),
            "subject_board": board("10 0"),
            "declared_refs": ["R2"],
            "use_declared_scope": true,
            "raw_global_capped": true,
            "instrument_context": instrument_context(),
            "leaves": [
                {"pairs": [["R1", "R2"]], "cells": [{"sample_counts": [0, 0, 0], "sample_findings": [[], [], []]}]},
                {"pairs": [["R2", "R3"]], "cells": [{"sample_counts": [0, 0, 0], "sample_findings": [[], [], []]}]}
            ]
        });
        let silk_receipt: serde_json::Value = serde_json::from_str(
            &silk_scope_receipt_json(&scope_request.to_string()).expect("complete silk scope"),
        )
        .expect("valid silk receipt");
        let one_sided_request = serde_json::json!({
            "baseline_samples": [[], [], []],
            "candidate_samples": [[], [], []],
            "baseline_capped_categories": ["W:silk_overlap"],
            "candidate_capped_categories": [],
            "baseline_silk_receipt": silk_receipt.clone(),
            "candidate_silk_receipt": null
        });
        let one_sided: serde_json::Value = serde_json::from_str(
            &comparison_receipt_json(&one_sided_request.to_string())
                .expect("one-sided cap remains typed"),
        )
        .expect("valid comparison receipt");
        assert_eq!(
            one_sided["category_states"]["W:silk_overlap"],
            "raw-saturated-unresolved"
        );
        let request = serde_json::json!({
            "baseline_samples": [[], [], []],
            "candidate_samples": [[], [], []],
            "baseline_capped_categories": ["W:silk_overlap", "clearance"],
            "candidate_capped_categories": ["W:silk_overlap"],
            "baseline_silk_receipt": silk_receipt,
            "candidate_silk_receipt": silk_receipt
        });
        let receipt: serde_json::Value = serde_json::from_str(
            &comparison_receipt_json(&request.to_string()).expect("typed cap states"),
        )
        .expect("valid comparison receipt");
        assert_eq!(
            receipt["category_states"]["W:silk_overlap"],
            "raw-saturated-scoped-complete"
        );
        assert_eq!(
            receipt["category_states"]["clearance"],
            "raw-saturated-unresolved"
        );
        assert_eq!(
            receipt["unresolved_cap_categories"],
            serde_json::json!(["clearance"])
        );
    }

    #[cfg_attr(test, test)]
    fn scoped_silk_comparison_uses_primitive_identity_not_moved_coordinates() {
        let finding = |x: i32, first_kind: &str| {
            serde_json::json!({
                "type": "silk_overlap",
                "description": "Silkscreen overlap",
                "items": [
                    {"description": format!("{first_kind} of R1 on F.Silkscreen"), "pos": {"x": x, "y": 0}},
                    {"description": "Arc of R2 on F.Silkscreen", "pos": {"x": 1, "y": 1}}
                ]
            })
        };
        let scope_receipt = |findings: Vec<serde_json::Value>| {
            let finding_count = findings.len();
            let request = serde_json::json!({
                "source_board": board("10 0"),
                "subject_board": board("10 0"),
                "declared_refs": ["R2"],
                "use_declared_scope": true,
                "raw_global_capped": true,
                "instrument_context": instrument_context(),
                "leaves": [
                    {"pairs": [["R1", "R2"]], "cells": [{"sample_counts": [finding_count, finding_count, finding_count], "sample_findings": [findings.clone(), findings.clone(), findings]}]},
                    {"pairs": [["R2", "R3"]], "cells": [{"sample_counts": [0, 0, 0], "sample_findings": [[], [], []]}]}
                ]
            });
            serde_json::from_str::<serde_json::Value>(
                &silk_scope_receipt_json(&request.to_string()).expect("complete silk receipt"),
            )
            .expect("valid receipt")
        };
        let baseline = scope_receipt(vec![finding(0, "Text REF")]);
        let moved = scope_receipt(vec![finding(99, "Text REF")]);
        let substituted = scope_receipt(vec![finding(99, "Segment")]);
        let added = scope_receipt(vec![finding(99, "Text REF"), finding(100, "Text REF")]);
        let compare = |candidate: serde_json::Value| {
            let request = serde_json::json!({
                "baseline_samples": [[], [], []],
                "candidate_samples": [[], [], []],
                "baseline_capped_categories": ["W:silk_overlap"],
                "candidate_capped_categories": ["W:silk_overlap"],
                "baseline_silk_receipt": baseline.clone(),
                "candidate_silk_receipt": candidate
            });
            serde_json::from_str::<serde_json::Value>(
                &comparison_receipt_json(&request.to_string()).expect("silk comparison"),
            )
            .expect("valid comparison")
        };
        let compare_v3 = |candidate: serde_json::Value| {
            let request = serde_json::json!({
                "baseline_samples": [[], [], []],
                "candidate_samples": [[], [], []],
                "baseline_capped_categories": ["W:silk_overlap"],
                "candidate_capped_categories": ["W:silk_overlap"],
                "baseline_silk_receipt": baseline.clone(),
                "candidate_silk_receipt": candidate
            });
            serde_json::from_str::<serde_json::Value>(
                &comparison_receipt_v3_json(&request.to_string()).expect("v3 silk comparison"),
            )
            .expect("valid v3 comparison")
        };
        assert_eq!(compare(moved)["new_scoped_silk_finding_count"], 0);
        assert_eq!(compare(substituted)["new_scoped_silk_finding_count"], 1);
        assert_eq!(compare(added.clone())["new_scoped_silk_finding_count"], 1);
        let exact_added = compare_v3(added);
        assert_eq!(exact_added["new_scoped_silk_finding_count"], 1);
        assert_eq!(exact_added["new_scoped_silk_findings"][0]["count"], 1);
        assert_eq!(
            exact_added["new_scoped_silk_findings"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("drc_evidence::tests::provider_churn_is_semantically_stable_and_raw_visible", provider_churn_is_semantically_stable_and_raw_visible),
        ("drc_evidence::tests::missing_connection_provider_churn_is_stable_but_identity_changes_are_not", missing_connection_provider_churn_is_stable_but_identity_changes_are_not),
        ("drc_evidence::tests::identity_bearing_mutations_are_not_normalized", identity_bearing_mutations_are_not_normalized),
        ("drc_evidence::tests::order_canonicalizes_but_duplicate_multisets_survive", order_canonicalizes_but_duplicate_multisets_survive),
        ("drc_evidence::tests::duplicate_findings_use_multiset_intersection_and_union", duplicate_findings_use_multiset_intersection_and_union),
        ("drc_evidence::tests::non_creepage_item_position_remains_identity_bearing", non_creepage_item_position_remains_identity_bearing),
        ("drc_evidence::tests::malformed_identity_field_is_typed_error", malformed_identity_field_is_typed_error),
        ("drc_evidence::tests::silk_scope_receipt_binds_actual_mutation_and_exact_pair_coverage", silk_scope_receipt_binds_actual_mutation_and_exact_pair_coverage),
        ("drc_evidence::tests::silk_scope_rejects_undeclared_mutation", silk_scope_rejects_undeclared_mutation),
        ("drc_evidence::tests::silk_scope_rejects_declared_non_rigid_mutation", silk_scope_rejects_declared_non_rigid_mutation),
        ("drc_evidence::tests::rigid_projection_accepts_writer_formatting_and_relative_pad_reorientation", rigid_projection_accepts_writer_formatting_and_relative_pad_reorientation),
        ("drc_evidence::tests::silk_scope_marks_duplicate_missing_disagreeing_and_near_cap_unresolved", silk_scope_marks_duplicate_missing_disagreeing_and_near_cap_unresolved),
        ("drc_evidence::tests::silk_cell_rejects_equal_counts_with_different_semantic_sets", silk_cell_rejects_equal_counts_with_different_semantic_sets),
        ("drc_evidence::tests::silk_scope_reports_missing_and_foreign_pairs_independently", silk_scope_reports_missing_and_foreign_pairs_independently),
        ("drc_evidence::tests::silk_finding_subject_is_rust_owned_and_ambiguous_records_fail", silk_finding_subject_is_rust_owned_and_ambiguous_records_fail),
        ("drc_evidence::tests::admission_comparison_ranks_hard_distances_after_provider_normalization", admission_comparison_ranks_hard_distances_after_provider_normalization),
        ("drc_evidence::tests::admission_comparison_v3_empty_delta_is_canonical_and_count_derived", admission_comparison_v3_empty_delta_is_canonical_and_count_derived),
        ("drc_evidence::tests::admission_comparison_v3_preserves_equal_count_identity_substitution", admission_comparison_v3_preserves_equal_count_identity_substitution),
        ("drc_evidence::tests::admission_comparison_v3_retains_new_multiplicity", admission_comparison_v3_retains_new_multiplicity),
        ("drc_evidence::tests::admission_comparison_v3_emits_exact_worsened_distance_pair", admission_comparison_v3_emits_exact_worsened_distance_pair),
        ("drc_evidence::tests::admission_comparison_v3_represents_unstable_and_capped_hard_evidence_as_indeterminate", admission_comparison_v3_represents_unstable_and_capped_hard_evidence_as_indeterminate),
        ("drc_evidence::tests::admission_comparison_v2_empty_request_is_byte_stable", admission_comparison_v2_empty_request_is_byte_stable),
        ("drc_evidence::tests::admission_comparison_allows_only_complete_silk_scope_to_resolve_a_cap", admission_comparison_allows_only_complete_silk_scope_to_resolve_a_cap),
        ("drc_evidence::tests::scoped_silk_comparison_uses_primitive_identity_not_moved_coordinates", scoped_silk_comparison_uses_primitive_identity_not_moved_coordinates),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

//! Deterministic coarse placement partitions.
//!
//! This module owns the small, data-only contract between the production
//! netlist and the future CP-SAT envelope solver.  It deliberately does not
//! know about CP-SAT variables or Python netlist classes.  The caller supplies
//! complete pin records and the electrical net terminals; this lets the
//! planner reject an incomplete graph instead of silently making a singleton
//! partition that is unsafe to solve.
//!
//! The planner computes connected components of the electrical graph within
//! each complete pin-class signature.  A shared global net therefore cannot
//! collapse unrelated safety domains: an `HV+Ground` component, a
//! `Signal+Ground` component, and a `Ground` component remain separate, while
//! same-signature components on that net still cluster.  A mixed-class
//! component (for example a gate driver with `GATE_H` and `PWM_HS` pins)
//! retains its complete signature.  Each returned cluster also carries the
//! complete sorted set of pin classes and net names, so the CP-SAT boundary
//! can apply the generated cross-class creepage matrix without re-discovering
//! connectivity.  Output ordering is independent of input ordering.
//!
//! `compact_partition_envelopes` is the companion data-only shelf sizer.  It
//! uses the board aspect ratio for its initial target width and reports the
//! actual shelf extents, with a board-width fallback when the compact target
//! would be too tall.
//!
//! `partition_creepage_requirements` reduces the generated class-pair matrix
//! into cross-partition maxima and per-partition internal gaps.  The
//! `*_with_internal_gaps` sizer applies those gaps only where needed, rather
//! than imposing a board-wide 12.6 mm shelf gap.
//!
//! `internal_component_creepage_requirements` retains the exact component-pair
//! rows needed by the local envelope solver.  Unlike the coarse partition
//! reduction, it uses every component's complete pin-class signature, so a
//! mixed-class partition does not turn one restrictive class pair into a gap
//! between every member.

use std::collections::{BTreeMap, BTreeSet, HashMap};

#[cfg(feature = "python")]
use pyo3::prelude::*;

/// `(pin_name, net_name, pin_class)` supplied for one component.
pub type PinClassRecord = (String, String, String);

/// `(component_ref, pin_name)` terminal supplied for one electrical net.
pub type NetTerminal = (String, String);

/// One input component and its complete pin-class records.
pub type ComponentPinClasses = (String, Vec<PinClassRecord>);

/// One named electrical net and all of its terminals.
pub type ElectricalNet = (String, Vec<NetTerminal>);

/// `(partition_id, component_refs, net_names, pin_classes)`.
///
/// IDs are assigned after sorting partitions by their lexicographically first
/// component reference.  All three vectors are sorted and duplicate-free.
pub type PartitionPlan = (usize, Vec<String>, Vec<String>, Vec<String>);

/// `(partition_id, component_refs, envelope_width_mm, envelope_height_mm)`.
pub type PartitionEnvelope = (usize, Vec<String>, f64, f64);

/// `(partition_a, partition_b, required_creepage_mm)` for distinct partition
/// pairs, and `(partition_id, required_internal_gap_mm)` for every partition.
pub type PartitionCreepageRequirements = (Vec<(usize, usize, f64)>, Vec<(usize, f64)>);

/// `(groups, dense_group_pairs)` for shared-direction creepage encoding.
pub type GroupedCreepagePlan = (Vec<Vec<String>>, Vec<(usize, usize)>);

/// Group refs with similar cut neighborhoods, then identify dense group pairs.
/// Requirements remain attached to their original component pairs; this plan
/// only permits the caller to share relative-direction literals.
pub fn plan_grouped_creepage_cuts(
    cuts: Vec<(String, String, f64)>,
    max_group_size: usize,
    min_cross_edges: usize,
) -> Result<GroupedCreepagePlan, String> {
    if max_group_size == 0 {
        return Err("max_group_size must be positive".into());
    }
    if min_cross_edges < 2 {
        return Err("min_cross_edges must be at least 2".into());
    }
    let mut edges = BTreeMap::<(String, String), f64>::new();
    let mut refs = BTreeSet::<String>::new();
    for (left, right, required) in cuts {
        if left.trim().is_empty() || right.trim().is_empty() || left == right {
            return Err("creepage cuts require two distinct non-empty refs".into());
        }
        if !required.is_finite() || required < 0.0 {
            return Err("creepage cut distance must be finite and non-negative".into());
        }
        let key = if left < right {
            (left, right)
        } else {
            (right, left)
        };
        refs.insert(key.0.clone());
        refs.insert(key.1.clone());
        let entry = edges.entry(key).or_insert(0.0);
        *entry = entry.max(required);
    }
    let refs: Vec<String> = refs.into_iter().collect();
    let mut neighbors = BTreeMap::<String, BTreeSet<String>>::new();
    for ((left, right), _) in &edges {
        neighbors
            .entry(left.clone())
            .or_default()
            .insert(right.clone());
        neighbors
            .entry(right.clone())
            .or_default()
            .insert(left.clone());
    }
    let mut candidates = Vec::<(usize, String, String)>::new();
    for (index, left) in refs.iter().enumerate() {
        for right in refs.iter().skip(index + 1) {
            let score = neighbors[left].intersection(&neighbors[right]).count();
            if score > 0 {
                candidates.push((score, left.clone(), right.clone()));
            }
        }
    }
    candidates.sort_by(|a, b| {
        b.0.cmp(&a.0)
            .then_with(|| a.1.cmp(&b.1))
            .then_with(|| a.2.cmp(&b.2))
    });
    let mut groups: Vec<BTreeSet<String>> =
        refs.iter().map(|r| BTreeSet::from([r.clone()])).collect();
    for (_, left, right) in candidates {
        let li = groups.iter().position(|g| g.contains(&left)).unwrap();
        let ri = groups.iter().position(|g| g.contains(&right)).unwrap();
        if li == ri || groups[li].len() + groups[ri].len() > max_group_size {
            continue;
        }
        let (keep, remove) = if li < ri { (li, ri) } else { (ri, li) };
        let removed = groups.remove(remove);
        groups[keep].extend(removed);
    }
    groups.sort_by(|a, b| a.iter().next().cmp(&b.iter().next()));
    let output_groups: Vec<Vec<String>> =
        groups.iter().map(|g| g.iter().cloned().collect()).collect();
    let mut group_of = BTreeMap::<String, usize>::new();
    for (id, group) in output_groups.iter().enumerate() {
        for r in group {
            group_of.insert(r.clone(), id);
        }
    }
    let mut counts = BTreeMap::<(usize, usize), usize>::new();
    for ((left, right), _) in edges {
        let a = group_of[&left];
        let b = group_of[&right];
        if a != b {
            let key = if a < b { (a, b) } else { (b, a) };
            *counts.entry(key).or_default() += 1;
        }
    }
    let dense_pairs = counts
        .into_iter()
        .filter_map(|(pair, count)| (count >= min_cross_edges).then_some(pair))
        .collect();
    Ok((output_groups, dense_pairs))
}

#[derive(Clone, Debug)]
struct UnionFind {
    parent: Vec<usize>,
    rank: Vec<u8>,
}

impl UnionFind {
    fn new(size: usize) -> Self {
        Self {
            parent: (0..size).collect(),
            rank: vec![0; size],
        }
    }

    fn find(&mut self, mut item: usize) -> usize {
        while self.parent[item] != item {
            let parent = self.parent[item];
            self.parent[item] = self.parent[parent];
            item = parent;
        }
        item
    }

    fn union(&mut self, left: usize, right: usize) {
        let left_root = self.find(left);
        let right_root = self.find(right);
        if left_root == right_root {
            return;
        }
        if self.rank[left_root] < self.rank[right_root] {
            self.parent[left_root] = right_root;
        } else if self.rank[left_root] > self.rank[right_root] {
            self.parent[right_root] = left_root;
        } else {
            self.parent[right_root] = left_root;
            self.rank[left_root] += 1;
        }
    }
}

fn invalid(message: impl Into<String>) -> Result<Vec<PartitionPlan>, String> {
    Err(message.into())
}

fn canonical_creepage_class(class: &str) -> String {
    if class == "GND" {
        "Ground".into()
    } else {
        class.into()
    }
}

fn canonical_creepage_key(class_a: &str, class_b: &str) -> (String, String) {
    let a = canonical_creepage_class(class_a);
    let b = canonical_creepage_class(class_b);
    if a <= b { (a, b) } else { (b, a) }
}

/// Reduce the generated class-pair creepage matrix over the complete class
/// signatures carried by the coarse partitions.
///
/// The first result is the maximum requirement for each unordered distinct
/// partition pair.  The second result contains every partition, including a
/// zero, and is the requirement that must separate shelves inside it.  Matrix
/// rows are canonicalized by unordered class pair and reduced by maximum, as
/// in `netclass.rs`; this accepts the generated table's symmetric rows while
/// making `GND` and `Ground` one class.
pub fn partition_creepage_requirements(
    partitions: Vec<PartitionPlan>,
    class_pair_creepage: Vec<(String, String, f64)>,
) -> Result<PartitionCreepageRequirements, String> {
    let mut by_id = BTreeMap::<usize, BTreeSet<String>>::new();
    let mut seen_refs = BTreeSet::<String>::new();
    for (partition_id, refs, _net_names, classes) in partitions {
        if by_id.contains_key(&partition_id) {
            return Err(format!("duplicate partition id: {partition_id}"));
        }
        if refs.is_empty() {
            return Err(format!("partition {partition_id} has no components"));
        }
        for reference in refs {
            if reference.trim().is_empty() {
                return Err(format!(
                    "partition {partition_id} has an empty component reference"
                ));
            }
            if !seen_refs.insert(reference.clone()) {
                return Err(format!(
                    "component appears in multiple partitions: {reference}"
                ));
            }
        }
        let mut signature = BTreeSet::new();
        for class in classes {
            if class.trim().is_empty() {
                return Err(format!("partition {partition_id} has an empty pin class"));
            }
            let canonical = canonical_creepage_class(&class);
            if !signature.insert(canonical.clone()) {
                return Err(format!(
                    "duplicate pin class in partition {partition_id}: {canonical}"
                ));
            }
        }
        by_id.insert(partition_id, signature);
    }

    let mut matrix = BTreeMap::<(String, String), f64>::new();
    for (class_a, class_b, required) in class_pair_creepage {
        if class_a.trim().is_empty() || class_b.trim().is_empty() {
            return Err("creepage matrix class names must be non-empty".into());
        }
        if !required.is_finite() || required < 0.0 {
            return Err(format!(
                "creepage requirement for {class_a}/{class_b} must be finite and non-negative"
            ));
        }
        let key = canonical_creepage_key(&class_a, &class_b);
        // Generated matrices legitimately contain self rows (for example
        // HighVoltageTank/HighVoltageTank).  The netclass owner skips equal
        // classes in its cross-product, so accept these rows for parity but
        // keep them out of both distinct-class reductions below.
        if key.0 == key.1 {
            continue;
        }
        let entry = matrix.entry(key).or_insert(0.0);
        *entry = (*entry).max(required);
    }

    let ids: Vec<usize> = by_id.keys().copied().collect();
    let mut cross_partition = Vec::new();
    let mut internal = Vec::with_capacity(ids.len());
    for partition_id in &ids {
        let classes = by_id
            .get(partition_id)
            .ok_or_else(|| format!("missing partition {partition_id}"))?;
        let mut internal_required: f64 = 0.0;
        let class_list: Vec<&String> = classes.iter().collect();
        for (index, class_a) in class_list.iter().enumerate() {
            for class_b in class_list.iter().skip(index + 1) {
                if let Some(required) = matrix.get(&canonical_creepage_key(class_a, class_b)) {
                    internal_required = internal_required.max(*required);
                }
            }
        }
        internal.push((*partition_id, internal_required));
    }
    for (index, partition_a) in ids.iter().enumerate() {
        for partition_b in ids.iter().skip(index + 1) {
            let classes_a = by_id
                .get(partition_a)
                .ok_or_else(|| format!("missing partition {partition_a}"))?;
            let classes_b = by_id
                .get(partition_b)
                .ok_or_else(|| format!("missing partition {partition_b}"))?;
            let mut required: f64 = 0.0;
            for class_a in classes_a {
                for class_b in classes_b {
                    if let Some(value) = matrix.get(&canonical_creepage_key(class_a, class_b)) {
                        required = required.max(*value);
                    }
                }
            }
            if required > 0.0 {
                cross_partition.push((*partition_a, *partition_b, required));
            }
        }
    }
    Ok((cross_partition, internal))
}

/// Compute exact non-zero creepage requirements for component pairs inside
/// each partition.
///
/// The component records are authoritative: every component reference must
/// occur in exactly one partition and every pin must have a unique name,
/// non-empty net/class fields, and a finite class signature.  The class list
/// carried by each partition is checked against the union of its component
/// classes as a consistency guard, but is not used for the reduction.  This
/// is important for mixed partitions: only the component pairs whose own
/// class cross-product contains a generated row receive that row's gap.
///
/// Matrix rows are canonicalized as unordered pairs, with `GND` and `Ground`
/// treated as one class.  Duplicate/symmetric rows are max-reduced and
/// same-class pairs are skipped, matching `netclass.rs`.  Output is ordered by
/// partition ID and then lexicographically by the two component references.
pub fn internal_component_creepage_requirements(
    partitions: Vec<PartitionPlan>,
    components_pin_classes: Vec<ComponentPinClasses>,
    class_pair_creepage: Vec<(String, String, f64)>,
) -> Result<Vec<(usize, String, String, f64)>, String> {
    let mut components = BTreeMap::<String, BTreeSet<String>>::new();
    for (component_ref, pins) in components_pin_classes {
        if component_ref.trim().is_empty() {
            return Err("component reference must be non-empty".into());
        }
        if pins.is_empty() {
            return Err(format!("component {component_ref} has no pin records"));
        }
        let mut pin_names = BTreeSet::new();
        let mut classes = BTreeSet::new();
        for (pin_name, net_name, pin_class) in pins {
            if pin_name.trim().is_empty() {
                return Err(format!("component {component_ref} has an empty pin name"));
            }
            if net_name.trim().is_empty() {
                return Err(format!(
                    "component {component_ref} pin {pin_name} has an empty net name"
                ));
            }
            if pin_class.trim().is_empty() {
                return Err(format!(
                    "component {component_ref} pin {pin_name} has an empty pin class"
                ));
            }
            if !pin_names.insert(pin_name.clone()) {
                return Err(format!("duplicate pin {component_ref}:{pin_name}"));
            }
            classes.insert(canonical_creepage_class(&pin_class));
        }
        if components.insert(component_ref.clone(), classes).is_some() {
            return Err(format!("duplicate component reference: {component_ref}"));
        }
    }

    let mut partition_refs = BTreeMap::<usize, Vec<String>>::new();
    let mut covered_refs = BTreeSet::<String>::new();
    for (partition_id, refs, net_names, declared_classes) in partitions {
        if partition_refs.contains_key(&partition_id) {
            return Err(format!("duplicate partition id: {partition_id}"));
        }
        if refs.is_empty() {
            return Err(format!("partition {partition_id} has no components"));
        }
        let mut sorted_refs = refs;
        sorted_refs.sort();
        if sorted_refs.windows(2).any(|pair| pair[0] == pair[1]) {
            return Err(format!("duplicate component in partition {partition_id}"));
        }
        for reference in &sorted_refs {
            if reference.trim().is_empty() {
                return Err(format!(
                    "partition {partition_id} has an empty component reference"
                ));
            }
            if !components.contains_key(reference) {
                return Err(format!(
                    "partition {partition_id} references unknown component {reference}"
                ));
            }
            if !covered_refs.insert(reference.clone()) {
                return Err(format!(
                    "component appears in multiple partitions: {reference}"
                ));
            }
        }
        let mut seen_nets = BTreeSet::new();
        for net_name in net_names {
            if net_name.trim().is_empty() || !seen_nets.insert(net_name.clone()) {
                return Err(format!(
                    "malformed net metadata in partition {partition_id}"
                ));
            }
        }
        let mut canonical_declared_classes = BTreeSet::new();
        for class in declared_classes {
            if class.trim().is_empty() {
                return Err(format!("partition {partition_id} has an empty pin class"));
            }
            if !canonical_declared_classes.insert(canonical_creepage_class(&class)) {
                return Err(format!(
                    "duplicate pin class in partition {partition_id}: {class}"
                ));
            }
        }
        let expected_classes = sorted_refs
            .iter()
            .flat_map(|reference| components[reference].iter().cloned())
            .collect::<BTreeSet<_>>();
        if canonical_declared_classes != expected_classes {
            return Err(format!(
                "partition {partition_id} has incomplete class metadata"
            ));
        }
        partition_refs.insert(partition_id, sorted_refs);
    }
    if covered_refs.len() != components.len() {
        let missing = components
            .keys()
            .find(|reference| !covered_refs.contains(*reference))
            .cloned()
            .unwrap_or_else(|| "<unknown>".into());
        return Err(format!(
            "component reference is not covered by partitions: {missing}"
        ));
    }

    let mut matrix = BTreeMap::<(String, String), f64>::new();
    for (class_a, class_b, required) in class_pair_creepage {
        if class_a.trim().is_empty() || class_b.trim().is_empty() {
            return Err("creepage matrix class names must be non-empty".into());
        }
        if !required.is_finite() || required < 0.0 {
            return Err(format!(
                "creepage requirement for {class_a}/{class_b} must be finite and non-negative"
            ));
        }
        let key = canonical_creepage_key(&class_a, &class_b);
        if key.0 == key.1 {
            continue;
        }
        let entry = matrix.entry(key).or_insert(0.0);
        *entry = (*entry).max(required);
    }

    let mut output = Vec::new();
    for (partition_id, refs) in partition_refs {
        for (index, reference_a) in refs.iter().enumerate() {
            for reference_b in refs.iter().skip(index + 1) {
                let classes_a = &components[reference_a];
                let classes_b = &components[reference_b];
                let mut required: f64 = 0.0;
                for class_a in classes_a {
                    for class_b in classes_b {
                        if class_a == class_b {
                            continue;
                        }
                        if let Some(value) = matrix.get(&canonical_creepage_key(class_a, class_b)) {
                            required = required.max(*value);
                        }
                    }
                }
                if required > 0.0 {
                    output.push((
                        partition_id,
                        reference_a.clone(),
                        reference_b.clone(),
                        required,
                    ));
                }
            }
        }
    }
    Ok(output)
}

/// Build a deterministic electrical connectivity partition plan.
///
/// Every component pin must occur exactly once in the net terminal lists and
/// every terminal must point to an existing component pin whose declared net
/// agrees with the net containing that terminal.  These checks are strict by
/// design: an unresolved or duplicate terminal would otherwise make a coarse
/// envelope appear safe while dropping an electrical relationship.
pub fn plan_component_partitions(
    components_pin_classes: Vec<ComponentPinClasses>,
    nets: Vec<ElectricalNet>,
) -> Result<Vec<PartitionPlan>, String> {
    let mut component_index = BTreeMap::<String, usize>::new();
    let mut refs_by_index = Vec::<String>::with_capacity(components_pin_classes.len());
    let mut pins_by_component =
        Vec::<BTreeMap<String, (String, String)>>::with_capacity(components_pin_classes.len());

    for (component_ref, pins) in components_pin_classes {
        if component_ref.trim().is_empty() {
            return invalid("component reference must be non-empty");
        }
        if component_index
            .insert(component_ref.clone(), pins_by_component.len())
            .is_some()
        {
            return invalid(format!("duplicate component reference: {component_ref}"));
        }
        refs_by_index.push(component_ref.clone());
        let mut pin_map = BTreeMap::new();
        for (pin_name, net_name, pin_class) in pins {
            if pin_name.trim().is_empty() {
                return invalid(format!("component {component_ref} has an empty pin name"));
            }
            if net_name.trim().is_empty() {
                return invalid(format!(
                    "component {component_ref} pin {pin_name} has an empty net name"
                ));
            }
            if pin_class.trim().is_empty() {
                return invalid(format!(
                    "component {component_ref} pin {pin_name} has an empty pin class"
                ));
            }
            if pin_map
                .insert(pin_name.clone(), (net_name.clone(), pin_class))
                .is_some()
            {
                return invalid(format!("duplicate pin {component_ref}:{pin_name}"));
            }
        }
        pins_by_component.push(pin_map);
    }

    let mut net_terminals = BTreeMap::<String, Vec<NetTerminal>>::new();
    for (net_name, terminals) in nets {
        if net_name.trim().is_empty() {
            return invalid("electrical net name must be non-empty");
        }
        if terminals.is_empty() {
            return invalid(format!("electrical net {net_name} has no terminals"));
        }
        if net_terminals.insert(net_name.clone(), terminals).is_some() {
            return invalid(format!("duplicate electrical net: {net_name}"));
        }
    }

    // A component's complete sorted pin-class signature is the safety-domain
    // identity used by the coarse graph.  It is intentionally derived from
    // every pin, not from one most-restrictive class: mixed-domain components
    // must not become a bridge through a shared global rail.
    let signatures: Vec<Vec<String>> = pins_by_component
        .iter()
        .map(|pins| {
            pins.values()
                .map(|(_, class)| class.clone())
                .collect::<BTreeSet<_>>()
                .into_iter()
                .collect()
        })
        .collect();

    // Mark each pin terminal exactly once while validating every cross-link.
    let mut seen_pins = BTreeSet::<(String, String)>::new();
    let mut uf = UnionFind::new(component_index.len());
    for (net_name, terminals) in &net_terminals {
        // Global rails commonly contain many safety domains.  Union only
        // within an identical complete signature; this is what keeps a
        // GND-connected board decomposable by safety domain by construction.
        let mut net_components_by_signature = BTreeMap::<Vec<String>, Vec<usize>>::new();
        for (component_ref, pin_name) in terminals {
            let component_number = match component_index.get(component_ref) {
                Some(index) => *index,
                None => {
                    return invalid(format!(
                        "net {net_name} references unknown component {component_ref}"
                    ));
                }
            };
            let pin = match pins_by_component[component_number].get(pin_name) {
                Some(pin) => pin,
                None => {
                    return invalid(format!(
                        "net {net_name} references unknown pin {component_ref}:{pin_name}"
                    ));
                }
            };
            if pin.0 != *net_name {
                return invalid(format!(
                    "pin {component_ref}:{pin_name} declares net {} but appears on {net_name}",
                    pin.0
                ));
            }
            if !seen_pins.insert((component_ref.clone(), pin_name.clone())) {
                return invalid(format!("duplicate net terminal {component_ref}:{pin_name}"));
            }
            net_components_by_signature
                .entry(signatures[component_number].clone())
                .or_default()
                .push(component_number);
        }
        for members in net_components_by_signature.values() {
            let mut members = members.iter().copied();
            if let Some(first) = members.next() {
                for member in members {
                    uf.union(first, member);
                }
            }
        }
    }

    for (component_number, pins) in pins_by_component.iter().enumerate() {
        for (pin_name, (net_name, _)) in pins {
            if !seen_pins.contains(&(refs_by_index[component_number].clone(), pin_name.clone())) {
                return invalid(format!(
                    "unresolved pin on component {}: {pin_name} (net {net_name})",
                    refs_by_index[component_number]
                ));
            }
        }
    }

    // Build output through ordered maps.  The union-find roots are an
    // implementation detail and are intentionally not exposed as IDs.
    let mut partitions =
        HashMap::<usize, (BTreeSet<String>, BTreeSet<String>, BTreeSet<String>)>::new();
    for (component_number, component_ref) in refs_by_index.iter().enumerate() {
        let root = uf.find(component_number);
        let entry = partitions
            .entry(root)
            .or_insert_with(|| (BTreeSet::new(), BTreeSet::new(), BTreeSet::new()));
        entry.0.insert(component_ref.clone());
        for (pin_name, (net_name, pin_class)) in &pins_by_component[component_number] {
            let _ = pin_name;
            entry.1.insert(net_name.clone());
            entry.2.insert(pin_class.clone());
        }
    }
    for (net_name, terminals) in &net_terminals {
        let first_ref = terminals
            .first()
            .map(|(reference, _)| reference)
            .ok_or_else(|| format!("electrical net {net_name} has no terminals"))?;
        let first_index = *component_index
            .get(first_ref)
            .ok_or_else(|| format!("net {net_name} references unknown component {first_ref}"))?;
        let root = uf.find(first_index);
        let entry = partitions
            .get_mut(&root)
            .ok_or_else(|| format!("net {net_name} has no component partition"))?;
        entry.1.insert(net_name.clone());
    }

    let mut ordered: Vec<_> = partitions.into_values().collect();
    ordered.sort_by(|left, right| left.0.iter().next().cmp(&right.0.iter().next()));
    Ok(ordered
        .into_iter()
        .enumerate()
        .map(|(partition_id, (refs, net_names, classes))| {
            (
                partition_id,
                refs.into_iter().collect(),
                net_names.into_iter().collect(),
                classes.into_iter().collect(),
            )
        })
        .collect())
}

#[derive(Clone, Debug)]
struct SizedComponent {
    reference: String,
    width: f64,
    height: f64,
}

fn finite_positive(value: f64, label: &str) -> Result<(), String> {
    if value.is_finite() && value > 0.0 {
        Ok(())
    } else {
        Err(format!("{label} must be finite and positive"))
    }
}

fn finite_nonnegative(value: f64, label: &str) -> Result<(), String> {
    if value.is_finite() && value >= 0.0 {
        Ok(())
    } else {
        Err(format!("{label} must be finite and non-negative"))
    }
}

fn finite_sum(left: f64, right: f64, label: &str) -> Result<f64, String> {
    let result = left + right;
    if result.is_finite() {
        Ok(result)
    } else {
        Err(format!("{label} overflowed a finite number"))
    }
}

/// Pack one partition into deterministic horizontal shelves.
fn pack_shelves(
    components: &[SizedComponent],
    target_width: f64,
    internal_gap_mm: f64,
) -> Result<(f64, f64), String> {
    let mut envelope_width: f64 = 0.0;
    let mut shelf_width: f64 = 0.0;
    let mut shelf_height: f64 = 0.0;
    let mut envelope_height: f64 = 0.0;
    let mut shelves = 0usize;

    for component in components {
        let required_width = if shelf_width == 0.0 {
            component.width
        } else {
            finite_sum(
                finite_sum(shelf_width, internal_gap_mm, "shelf width")?,
                component.width,
                "shelf width",
            )?
        };
        if shelf_width != 0.0 && required_width > target_width {
            envelope_width = envelope_width.max(shelf_width);
            envelope_height = if shelves == 0 {
                shelf_height
            } else {
                finite_sum(
                    finite_sum(envelope_height, internal_gap_mm, "envelope height")?,
                    shelf_height,
                    "envelope height",
                )?
            };
            shelves += 1;
            shelf_width = component.width;
            shelf_height = component.height;
        } else {
            shelf_width = required_width;
            shelf_height = shelf_height.max(component.height);
        }
    }

    if shelf_width != 0.0 {
        envelope_width = envelope_width.max(shelf_width);
        envelope_height = if shelves == 0 {
            shelf_height
        } else {
            finite_sum(
                finite_sum(envelope_height, internal_gap_mm, "envelope height")?,
                shelf_height,
                "envelope height",
            )?
        };
    }
    Ok((envelope_width, envelope_height))
}

/// Size all coarse partitions using deterministic shelf packing.
///
/// The initial shelf target follows the board aspect ratio and the partition
/// area (`sqrt(area * board_width / board_height)`), clamped so every item can
/// fit.  If that compact target is too tall, the same ordered shelves are
/// repacked at the board width; this is the widest safe fallback and avoids
/// rejecting a partition merely because the aspect target chose too many
/// shelves.  The returned dimensions are measured from the actual shelf
/// arrangement, never from the target width, so they are sufficient by
/// construction for the adapter's envelope constraints.
pub fn compact_partition_envelopes(
    partitions: Vec<PartitionPlan>,
    component_dimensions: Vec<(String, f64, f64)>,
    board_width_mm: f64,
    board_height_mm: f64,
    internal_gap_mm: f64,
) -> Result<Vec<PartitionEnvelope>, String> {
    compact_partition_envelopes_with_internal_gaps(
        partitions,
        component_dimensions,
        board_width_mm,
        board_height_mm,
        internal_gap_mm,
        Vec::new(),
    )
}

/// Size partitions with an optional per-partition internal creepage gap.
/// Missing map entries use the base gap; every used gap is
/// `max(base_gap, internal_creepage_gap)`.
pub fn compact_partition_envelopes_with_internal_gaps(
    partitions: Vec<PartitionPlan>,
    component_dimensions: Vec<(String, f64, f64)>,
    board_width_mm: f64,
    board_height_mm: f64,
    internal_gap_mm: f64,
    partition_internal_gaps: Vec<(usize, f64)>,
) -> Result<Vec<PartitionEnvelope>, String> {
    finite_positive(board_width_mm, "board_width_mm")?;
    finite_positive(board_height_mm, "board_height_mm")?;
    finite_nonnegative(internal_gap_mm, "internal_gap_mm")?;

    let mut dimensions = BTreeMap::<String, (f64, f64)>::new();
    for (reference, width, height) in component_dimensions {
        if reference.trim().is_empty() {
            return Err("component dimension reference must be non-empty".into());
        }
        finite_positive(width, &format!("width for {reference}"))?;
        finite_positive(height, &format!("height for {reference}"))?;
        if dimensions
            .insert(reference.clone(), (width, height))
            .is_some()
        {
            return Err(format!("duplicate component dimensions for {reference}"));
        }
    }

    let mut seen_refs = BTreeSet::<String>::new();
    let mut seen_partition_ids = BTreeSet::<usize>::new();
    let mut internal_gaps = BTreeMap::<usize, f64>::new();
    for (partition_id, gap) in partition_internal_gaps {
        finite_nonnegative(gap, &format!("internal gap for partition {partition_id}"))?;
        if internal_gaps.insert(partition_id, gap).is_some() {
            return Err(format!(
                "duplicate internal gap for partition {partition_id}"
            ));
        }
    }
    let mut ordered_partitions = Vec::<(usize, Vec<String>)>::with_capacity(partitions.len());
    for (partition_id, refs, _net_names, _pin_classes) in partitions {
        if !seen_partition_ids.insert(partition_id) {
            return Err(format!("duplicate partition id: {partition_id}"));
        }
        if refs.is_empty() {
            return Err(format!("partition {partition_id} has no components"));
        }
        let mut partition_refs = refs;
        partition_refs.sort();
        for reference in &partition_refs {
            if reference.trim().is_empty() {
                return Err(format!(
                    "partition {partition_id} has an empty component reference"
                ));
            }
            if !seen_refs.insert(reference.clone()) {
                return Err(format!(
                    "component appears in multiple partitions: {reference}"
                ));
            }
            if !dimensions.contains_key(reference) {
                return Err(format!("missing dimensions for component {reference}"));
            }
        }
        if partition_refs.windows(2).any(|pair| pair[0] == pair[1]) {
            return Err(format!("duplicate component in partition {partition_id}"));
        }
        ordered_partitions.push((partition_id, partition_refs));
    }
    if let Some(partition_id) = internal_gaps
        .keys()
        .find(|partition_id| !seen_partition_ids.contains(partition_id))
    {
        return Err(format!(
            "internal gap references unknown partition {partition_id}"
        ));
    }
    if seen_refs.len() != dimensions.len() {
        let unresolved = dimensions
            .keys()
            .find(|reference| !seen_refs.contains(*reference))
            .cloned()
            .unwrap_or_else(|| "<unknown>".into());
        return Err(format!(
            "component dimensions are not covered by a partition: {unresolved}"
        ));
    }
    ordered_partitions.sort_by_key(|(partition_id, _)| *partition_id);

    let mut output = Vec::with_capacity(ordered_partitions.len());
    for (partition_id, refs) in ordered_partitions {
        let partition_gap =
            internal_gap_mm.max(internal_gaps.get(&partition_id).copied().unwrap_or(0.0));
        let mut components: Vec<SizedComponent> = refs
            .iter()
            .map(|reference| {
                let (width, height) = dimensions
                    .get(reference)
                    .copied()
                    .ok_or_else(|| format!("missing dimensions for component {reference}"))?;
                if width > board_width_mm || height > board_height_mm {
                    return Err(format!(
                        "component {reference} ({width}x{height} mm) cannot fit board ({board_width_mm}x{board_height_mm} mm)"
                    ));
                }
                Ok(SizedComponent {
                    reference: reference.clone(),
                    width,
                    height,
                })
            })
            .collect::<Result<_, String>>()?;
        components.sort_by(|left, right| {
            right
                .width
                .max(right.height)
                .total_cmp(&left.width.max(left.height))
                .then_with(|| (right.width * right.height).total_cmp(&(left.width * left.height)))
                .then_with(|| left.reference.cmp(&right.reference))
        });

        let mut area = 0.0;
        for component in &components {
            let footprint = finite_sum(component.width, partition_gap, "partition area")?
                * finite_sum(component.height, partition_gap, "partition area")?;
            if !footprint.is_finite() {
                return Err(format!(
                    "partition {partition_id} area overflowed a finite number"
                ));
            }
            area = finite_sum(area, footprint, "partition area")?;
        }
        let aspect_area = area * board_width_mm / board_height_mm;
        if !aspect_area.is_finite() {
            return Err(format!(
                "partition {partition_id} aspect target overflowed a finite number"
            ));
        }
        let largest_width = components
            .iter()
            .map(|component| component.width)
            .fold(0.0, f64::max);
        let mut target_width = aspect_area.sqrt().max(largest_width).min(board_width_mm);
        let mut envelope = pack_shelves(&components, target_width, partition_gap)?;
        if envelope.1 > board_height_mm {
            target_width = board_width_mm;
            envelope = pack_shelves(&components, target_width, partition_gap)?;
        }
        if envelope.0 > board_width_mm || envelope.1 > board_height_mm {
            return Err(format!(
                "partition {partition_id} envelope ({:.6}x{:.6} mm) cannot fit board ({board_width_mm}x{board_height_mm} mm)",
                envelope.0, envelope.1
            ));
        }
        output.push((partition_id, refs, envelope.0, envelope.1));
    }
    Ok(output)
}

/// Plain pyo3 boundary for [`plan_component_partitions`].
#[cfg(feature = "python")]
#[pyfunction]
pub fn plan_component_partitions_py(
    components_pin_classes: Vec<ComponentPinClasses>,
    nets: Vec<ElectricalNet>,
) -> PyResult<Vec<PartitionPlan>> {
    plan_component_partitions(components_pin_classes, nets)
        .map_err(pyo3::exceptions::PyValueError::new_err)
}

/// Python boundary for [`partition_creepage_requirements`].
#[cfg(feature = "python")]
#[pyfunction]
pub fn partition_creepage_requirements_py(
    partitions: Vec<PartitionPlan>,
    class_pair_creepage: Vec<(String, String, f64)>,
) -> PyResult<PartitionCreepageRequirements> {
    partition_creepage_requirements(partitions, class_pair_creepage)
        .map_err(pyo3::exceptions::PyValueError::new_err)
}

/// Python boundary for [`internal_component_creepage_requirements`].
#[cfg(feature = "python")]
#[pyfunction]
pub fn internal_component_creepage_requirements_py(
    partitions: Vec<PartitionPlan>,
    components_pin_classes: Vec<ComponentPinClasses>,
    class_pair_creepage: Vec<(String, String, f64)>,
) -> PyResult<Vec<(usize, String, String, f64)>> {
    internal_component_creepage_requirements(
        partitions,
        components_pin_classes,
        class_pair_creepage,
    )
    .map_err(pyo3::exceptions::PyValueError::new_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn plan_grouped_creepage_cuts_py(
    cuts: Vec<(String, String, f64)>,
    max_group_size: usize,
    min_cross_edges: usize,
) -> PyResult<GroupedCreepagePlan> {
    plan_grouped_creepage_cuts(cuts, max_group_size, min_cross_edges)
        .map_err(pyo3::exceptions::PyValueError::new_err)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[test]
    fn grouped_creepage_plan_finds_dense_bipartite_blocks_deterministically() {
        let cuts = vec![
            ("A1".into(), "B1".into(), 8.0),
            ("A1".into(), "B2".into(), 9.0),
            ("A2".into(), "B1".into(), 10.0),
            ("A2".into(), "B2".into(), 12.6),
            ("X".into(), "Y".into(), 3.0),
        ];
        let plan = plan_grouped_creepage_cuts(cuts.clone(), 2, 3).unwrap();
        assert_eq!(
            plan.0,
            vec![
                vec!["A1".to_string(), "A2".to_string()],
                vec!["B1".to_string(), "B2".to_string()],
                vec!["X".to_string()],
                vec!["Y".to_string()]
            ]
        );
        assert_eq!(plan.1, vec![(0, 1)]);
        let mut reversed = cuts;
        reversed.reverse();
        assert_eq!(plan_grouped_creepage_cuts(reversed, 2, 3).unwrap(), plan);
    }

    fn sample() -> (Vec<ComponentPinClasses>, Vec<ElectricalNet>) {
        (
            vec![
                (
                    "U_GATE".into(),
                    vec![
                        ("1".into(), "GATE_H".into(), "HighVoltage".into()),
                        ("2".into(), "PWM_HS".into(), "Signal".into()),
                    ],
                ),
                (
                    "Q1".into(),
                    vec![("1".into(), "GATE_H".into(), "HighVoltage".into())],
                ),
                (
                    "Q2".into(),
                    vec![("1".into(), "GATE_H".into(), "HighVoltage".into())],
                ),
                (
                    "MCU".into(),
                    vec![("1".into(), "SPI_CLK".into(), "Signal".into())],
                ),
                (
                    "TANK".into(),
                    vec![("1".into(), "tank.c_tank1-p2".into(), "HighVoltage".into())],
                ),
                (
                    "BUS".into(),
                    vec![("1".into(), "DC_BUS+".into(), "HighVoltage".into())],
                ),
            ],
            vec![
                (
                    "GATE_H".into(),
                    vec![
                        ("Q1".into(), "1".into()),
                        ("Q2".into(), "1".into()),
                        ("U_GATE".into(), "1".into()),
                    ],
                ),
                ("PWM_HS".into(), vec![("U_GATE".into(), "2".into())]),
                ("SPI_CLK".into(), vec![("MCU".into(), "1".into())]),
                ("tank.c_tank1-p2".into(), vec![("TANK".into(), "1".into())]),
                ("DC_BUS+".into(), vec![("BUS".into(), "1".into())]),
            ],
        )
    }

    #[cfg_attr(test, test)]
    fn groups_connectivity_and_retains_mixed_pin_classes() {
        let (components, nets) = sample();
        let plan = plan_component_partitions(components, nets).unwrap();
        assert_eq!(plan.len(), 5);
        assert_eq!(
            plan[0],
            (
                0,
                vec!["BUS".into()],
                vec!["DC_BUS+".into()],
                vec!["HighVoltage".into()]
            )
        );
        let gate_partition = plan
            .iter()
            .find(|(_, refs, _, _)| refs == &["Q1".to_string(), "Q2".to_string()])
            .expect("same-signature GATE_H components form one partition");
        assert_eq!(gate_partition.2, vec!["GATE_H".to_string()]);
        assert_eq!(gate_partition.3, vec!["HighVoltage".to_string()]);
        let mixed_partition = plan
            .iter()
            .find(|(_, refs, _, _)| refs == &["U_GATE".to_string()])
            .expect("the mixed-signature gate driver remains distinct");
        assert_eq!(
            mixed_partition.2,
            vec!["GATE_H".to_string(), "PWM_HS".to_string()]
        );
        assert_eq!(
            mixed_partition.3,
            vec!["HighVoltage".to_string(), "Signal".to_string()]
        );
    }

    #[cfg_attr(test, test)]
    fn output_is_invariant_to_input_order() {
        let (mut components, mut nets) = sample();
        let expected = plan_component_partitions(components.clone(), nets.clone()).unwrap();
        components.reverse();
        nets.reverse();
        assert_eq!(
            expected,
            plan_component_partitions(components, nets).unwrap()
        );
    }

    #[cfg_attr(test, test)]
    fn shared_ground_does_not_bridge_safety_signatures() {
        let components = vec![
            (
                "HV_SENSE".into(),
                vec![
                    ("1".into(), "GND".into(), "Ground".into()),
                    ("2".into(), "DC_BUS+".into(), "HighVoltage".into()),
                ],
            ),
            (
                "SIGNAL_SENSE".into(),
                vec![
                    ("1".into(), "GND".into(), "Ground".into()),
                    ("2".into(), "SPI_CLK".into(), "Signal".into()),
                ],
            ),
            (
                "GROUND_ONLY".into(),
                vec![("1".into(), "GND".into(), "Ground".into())],
            ),
            (
                "GROUND_RETURN".into(),
                vec![("1".into(), "GND".into(), "Ground".into())],
            ),
        ];
        let nets = vec![
            (
                "GND".into(),
                vec![
                    ("HV_SENSE".into(), "1".into()),
                    ("SIGNAL_SENSE".into(), "1".into()),
                    ("GROUND_ONLY".into(), "1".into()),
                    ("GROUND_RETURN".into(), "1".into()),
                ],
            ),
            ("DC_BUS+".into(), vec![("HV_SENSE".into(), "2".into())]),
            ("SPI_CLK".into(), vec![("SIGNAL_SENSE".into(), "2".into())]),
        ];
        let plan = plan_component_partitions(components, nets).unwrap();
        assert_eq!(plan.len(), 3);
        assert!(plan.iter().any(|(_, refs, _, classes)| {
            refs == &["GROUND_ONLY".to_string(), "GROUND_RETURN".to_string()]
                && classes == &["Ground".to_string()]
        }));
        assert!(plan.iter().any(|(_, refs, _, classes)| {
            refs == &["HV_SENSE".to_string()]
                && classes == &["Ground".to_string(), "HighVoltage".to_string()]
        }));
        assert!(plan.iter().any(|(_, refs, _, classes)| {
            refs == &["SIGNAL_SENSE".to_string()]
                && classes == &["Ground".to_string(), "Signal".to_string()]
        }));
    }

    #[cfg_attr(test, test)]
    fn malformed_duplicate_and_unresolved_inputs_fail_closed() {
        let (mut components, nets) = sample();
        components.push(("BUS".into(), vec![]));
        assert!(plan_component_partitions(components, nets.clone()).is_err());
        let (components, mut nets) = sample();
        nets.push(("GATE_H".into(), vec![]));
        assert!(plan_component_partitions(components, nets).is_err());
        let (mut components, nets) = sample();
        components[0].1[0].1 = "MISSING".into();
        assert!(plan_component_partitions(components, nets).is_err());
    }

    #[cfg_attr(test, test)]
    fn compact_shelves_are_stable_and_fit_the_board() {
        let partitions = vec![
            (
                7,
                vec!["U_GATE".into(), "Q1".into()],
                vec!["GATE_H".into(), "PWM_HS".into()],
                vec!["HighVoltage".into(), "Signal".into()],
            ),
            (
                2,
                vec!["TANK".into(), "MCU".into()],
                vec!["tank.c_tank1-p2".into(), "SPI_CLK".into()],
                vec!["HighVoltage".into(), "Signal".into()],
            ),
        ];
        let dimensions = vec![
            ("MCU".into(), 10.0, 5.0),
            ("Q1".into(), 20.0, 10.0),
            ("TANK".into(), 6.0, 6.0),
            ("U_GATE".into(), 8.0, 8.0),
        ];
        let envelopes =
            compact_partition_envelopes(partitions, dimensions, 100.0, 80.0, 2.0).unwrap();
        assert_eq!(envelopes[0].0, 2);
        assert_eq!(envelopes[0].1, vec!["MCU".to_string(), "TANK".to_string()]);
        assert!(
            envelopes
                .iter()
                .all(|(_, _, width, height)| *width <= 100.0 && *height <= 80.0)
        );
        assert!(envelopes[0].2 < 100.0);
        assert!(envelopes[0].3 < 80.0);
    }

    #[cfg_attr(test, test)]
    fn compact_shelves_reject_bad_coverage_and_dimensions() {
        let partition = vec![(0, vec!["Q1".into()], vec![], vec!["HighVoltage".into()])];
        assert!(compact_partition_envelopes(partition.clone(), vec![], 100.0, 80.0, 1.0).is_err());
        assert!(
            compact_partition_envelopes(
                partition.clone(),
                vec![("Q1".into(), f64::NAN, 1.0)],
                100.0,
                80.0,
                1.0,
            )
            .is_err()
        );
        assert!(
            compact_partition_envelopes(
                partition.clone(),
                vec![("Q1".into(), 101.0, 1.0)],
                100.0,
                80.0,
                1.0,
            )
            .is_err()
        );
        assert!(
            compact_partition_envelopes(
                partition,
                vec![("Q1".into(), 1.0, 1.0)],
                100.0,
                80.0,
                -1.0,
            )
            .is_err()
        );
    }

    #[cfg_attr(test, test)]
    fn creepage_requirements_reduce_cross_and_internal_maxima() {
        let partitions = vec![
            (
                7,
                vec!["U_GATE".into()],
                vec!["GATE_H".into(), "PWM_HS".into()],
                vec!["GateDriveHV".into(), "Signal".into()],
            ),
            (
                2,
                vec!["MCU".into()],
                vec!["SPI_CLK".into(), "GND".into()],
                vec!["Signal".into(), "Ground".into()],
            ),
            (
                10,
                vec!["TANK".into()],
                vec!["tank.c_tank1-p2".into()],
                vec!["GateDriveHV".into()],
            ),
            (
                11,
                vec!["TANK_SELF".into()],
                vec!["tank.c_tank1-p2".into()],
                vec!["HighVoltageTank".into()],
            ),
        ];
        let rows = vec![
            ("GateDriveHV".into(), "Signal".into(), 12.6),
            ("Signal".into(), "GateDriveHV".into(), 10.0),
            ("GND".into(), "GateDriveHV".into(), 8.0),
            ("Ground".into(), "GateDriveHV".into(), 9.5),
            ("Ground".into(), "Signal".into(), 9.5),
            ("HighVoltageTank".into(), "HighVoltageTank".into(), 12.6),
        ];
        let (cross, internal) = partition_creepage_requirements(partitions, rows).unwrap();
        assert_eq!(cross, vec![(2, 7, 12.6), (2, 10, 12.6), (7, 10, 12.6)]);
        assert_eq!(internal, vec![(2, 9.5), (7, 12.6), (10, 0.0), (11, 0.0)]);
    }

    #[cfg_attr(test, test)]
    fn creepage_requirements_reject_duplicate_and_bad_rows() {
        let base = vec![(0, vec!["Q1".into()], vec![], vec!["Signal".into()])];
        let duplicate_id = vec![
            (0, vec!["Q1".into()], vec![], vec!["Signal".into()]),
            (0, vec!["Q2".into()], vec![], vec!["Signal".into()]),
        ];
        assert!(partition_creepage_requirements(duplicate_id, vec![]).is_err());
        let duplicate_class = vec![(
            0,
            vec!["Q1".into()],
            vec![],
            vec!["Signal".into(), "Signal".into()],
        )];
        assert!(partition_creepage_requirements(duplicate_class, vec![]).is_err());
        assert!(
            partition_creepage_requirements(
                base.clone(),
                vec![("Signal".into(), "HV".into(), -1.0)]
            )
            .is_err()
        );
        assert!(
            partition_creepage_requirements(
                base,
                vec![("Signal".into(), "HV".into(), f64::INFINITY)]
            )
            .is_err()
        );
    }

    #[cfg_attr(test, test)]
    fn internal_creepage_gap_is_applied_per_partition() {
        let partitions = vec![(
            0,
            vec!["Q1".into(), "Q2".into()],
            vec![],
            vec!["GateDriveHV".into(), "Signal".into()],
        )];
        let dimensions = vec![("Q1".into(), 10.0, 10.0), ("Q2".into(), 10.0, 10.0)];
        let base =
            compact_partition_envelopes(partitions.clone(), dimensions.clone(), 100.0, 80.0, 1.0)
                .unwrap();
        let with_creepage = compact_partition_envelopes_with_internal_gaps(
            partitions,
            dimensions,
            100.0,
            80.0,
            1.0,
            vec![(0, 12.6)],
        )
        .unwrap();
        assert!(with_creepage[0].2 > base[0].2);
        assert!(with_creepage[0].2 >= 12.6 + 10.0 + 10.0);
    }

    #[cfg_attr(test, test)]
    fn internal_component_requirements_are_pair_specific() {
        let partitions = vec![(
            4,
            vec![
                "HV_GATE".into(),
                "SPI_DEVICE".into(),
                "PWM_DEVICE".into(),
                "TANK".into(),
                "GROUND".into(),
            ],
            vec![
                "DC_BUS+".into(),
                "GATE_H".into(),
                "PWM_HS".into(),
                "SPI_CLK".into(),
                "tank.c_tank1-p2".into(),
                "GND".into(),
            ],
            vec![
                "Ground".into(),
                "HighVoltage".into(),
                "HighVoltageTank".into(),
                "Signal".into(),
            ],
        )];
        let components = vec![
            (
                "HV_GATE".into(),
                vec![
                    ("1".into(), "DC_BUS+".into(), "HighVoltage".into()),
                    ("2".into(), "GATE_H".into(), "HighVoltage".into()),
                ],
            ),
            (
                "SPI_DEVICE".into(),
                vec![("1".into(), "SPI_CLK".into(), "Signal".into())],
            ),
            (
                "PWM_DEVICE".into(),
                vec![("1".into(), "PWM_HS".into(), "Signal".into())],
            ),
            (
                "TANK".into(),
                vec![(
                    "1".into(),
                    "tank.c_tank1-p2".into(),
                    "HighVoltageTank".into(),
                )],
            ),
            (
                "GROUND".into(),
                vec![("1".into(), "GND".into(), "GND".into())],
            ),
        ];
        let rows = vec![
            ("Signal".into(), "HighVoltage".into(), 12.6),
            ("HighVoltage".into(), "HighVoltageTank".into(), 4.0),
            ("Signal".into(), "HighVoltageTank".into(), 6.0),
            ("GND".into(), "HighVoltage".into(), 8.0),
        ];
        let requirements =
            internal_component_creepage_requirements(partitions, components, rows).unwrap();
        assert_eq!(
            requirements,
            vec![
                (4, "GROUND".into(), "HV_GATE".into(), 8.0),
                (4, "HV_GATE".into(), "PWM_DEVICE".into(), 12.6),
                (4, "HV_GATE".into(), "SPI_DEVICE".into(), 12.6),
                (4, "HV_GATE".into(), "TANK".into(), 4.0),
                (4, "PWM_DEVICE".into(), "TANK".into(), 6.0),
                (4, "SPI_DEVICE".into(), "TANK".into(), 6.0),
            ]
        );
        assert!(!requirements.iter().any(|(_, left, right, gap)| {
            left == "PWM_DEVICE" && right == "SPI_DEVICE" && *gap == 12.6
        }));
        assert!(
            requirements
                .iter()
                .filter(|(_, _, _, gap)| *gap == 12.6)
                .all(|(_, left, right, _)| {
                    (left == "HV_GATE" && (right == "PWM_DEVICE" || right == "SPI_DEVICE"))
                        || (right == "HV_GATE" && (left == "PWM_DEVICE" || left == "SPI_DEVICE"))
                })
        );
    }

    #[cfg_attr(test, test)]
    fn internal_component_requirements_reject_bad_coverage_and_rows() {
        let partition = vec![(
            0,
            vec!["A".into()],
            vec!["DC_BUS+".into()],
            vec!["HighVoltage".into()],
        )];
        let component = vec![(
            "A".into(),
            vec![("1".into(), "DC_BUS+".into(), "HighVoltage".into())],
        )];
        assert!(
            internal_component_creepage_requirements(
                partition.clone(),
                vec![
                    component[0].clone(),
                    (
                        "B".into(),
                        vec![("1".into(), "SPI_CLK".into(), "Signal".into())]
                    ),
                ],
                vec![],
            )
            .is_err()
        );
        assert!(
            internal_component_creepage_requirements(
                partition.clone(),
                vec![(
                    "A".into(),
                    vec![
                        ("1".into(), "DC_BUS+".into(), "HighVoltage".into()),
                        ("1".into(), "GATE_H".into(), "HighVoltage".into()),
                    ],
                )],
                vec![],
            )
            .is_err()
        );
        assert!(
            internal_component_creepage_requirements(
                partition.clone(),
                component.clone(),
                vec![("HighVoltage".into(), "Signal".into(), f64::NAN)],
            )
            .is_err()
        );
        assert!(
            internal_component_creepage_requirements(
                partition,
                component,
                vec![("HighVoltage".into(), "Signal".into(), -1.0)],
            )
            .is_err()
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        (
            "partition_planner::tests::groups_connectivity_and_retains_mixed_pin_classes",
            groups_connectivity_and_retains_mixed_pin_classes,
        ),
        (
            "partition_planner::tests::output_is_invariant_to_input_order",
            output_is_invariant_to_input_order,
        ),
        (
            "partition_planner::tests::shared_ground_does_not_bridge_safety_signatures",
            shared_ground_does_not_bridge_safety_signatures,
        ),
        (
            "partition_planner::tests::malformed_duplicate_and_unresolved_inputs_fail_closed",
            malformed_duplicate_and_unresolved_inputs_fail_closed,
        ),
        (
            "partition_planner::tests::compact_shelves_are_stable_and_fit_the_board",
            compact_shelves_are_stable_and_fit_the_board,
        ),
        (
            "partition_planner::tests::compact_shelves_reject_bad_coverage_and_dimensions",
            compact_shelves_reject_bad_coverage_and_dimensions,
        ),
        (
            "partition_planner::tests::creepage_requirements_reduce_cross_and_internal_maxima",
            creepage_requirements_reduce_cross_and_internal_maxima,
        ),
        (
            "partition_planner::tests::creepage_requirements_reject_duplicate_and_bad_rows",
            creepage_requirements_reject_duplicate_and_bad_rows,
        ),
        (
            "partition_planner::tests::internal_creepage_gap_is_applied_per_partition",
            internal_creepage_gap_is_applied_per_partition,
        ),
        (
            "partition_planner::tests::internal_component_requirements_are_pair_specific",
            internal_component_requirements_are_pair_specific,
        ),
        (
            "partition_planner::tests::internal_component_requirements_reject_bad_coverage_and_rows",
            internal_component_requirements_reject_bad_coverage_and_rows,
        ),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

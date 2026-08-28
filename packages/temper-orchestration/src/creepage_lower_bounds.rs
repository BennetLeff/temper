//! Necessary lower bounds for the component-box creepage model.
//!
//! This module deliberately does not build a CP-SAT model.  It supplies
//! independently checkable conditions which a placement satisfying the
//! component-box interpretation must obey.  In particular, for a threshold
//! `d`, every edge in a clique requires two component rectangles to have
//! L-infinity distance at least `d`.  Expanding each rectangle by `d / 2` in
//! every direction therefore makes the expanded rectangles pairwise
//! interior-disjoint.  They all lie in the board expanded by `d / 2`, hence
//! their total area cannot exceed `(board_width + d) * (board_height + d)`.
//!
//! The production graph has only eleven weighted-twin classes.  At each
//! distinct requirement threshold, the exact maximum weighted clique on this
//! quotient is evaluated.  A class contributes all of its members when its
//! internal requirement reaches the threshold (true twins), and otherwise at
//! most one member can be selected (false twins).  The latter contribution is
//! the largest member area, which is still a valid and tight choice for the
//! necessary bound.

use std::collections::BTreeMap;

#[cfg(feature = "python")]
use pyo3::prelude::*;

/// Data-only Python representation of one threshold certificate.
pub type ThresholdCliqueBoundPy = (f64, Vec<usize>, Vec<String>, usize, f64, f64, f64, f64);

/// Data-only Python representation of the complete necessary-condition report.
pub type CreepageLowerBoundReportPy = (
    usize,
    usize,
    usize,
    Vec<usize>,
    f64,
    f64,
    f64,
    f64,
    Vec<ThresholdCliqueBoundPy>,
    bool,
);

/// The result for one requirement threshold and its maximum weighted clique.
#[derive(Clone, Debug, PartialEq)]
pub struct ThresholdCliqueBound {
    /// The threshold whose edges define this clique.
    pub threshold_mm: f64,
    /// Quotient class IDs included in the clique.
    pub class_ids: Vec<usize>,
    /// Concrete component references represented by the selected classes.
    pub component_refs: Vec<String>,
    /// Number of concrete rectangles in the clique.
    pub component_count: usize,
    /// Sum of `(width + d) * (height + d)` over the concrete rectangles.
    pub expanded_area_mm2: f64,
    /// Expanded board area `(board_width + d) * (board_height + d)`.
    pub board_expanded_area_mm2: f64,
    /// Area-derived necessary lower bound on board width with board height
    /// held fixed: `area / (board_height + d) - d`.
    pub required_board_width_mm: f64,
    /// Area-derived necessary lower bound on board height with board width
    /// held fixed: `area / (board_width + d) - d`.
    pub required_board_height_mm: f64,
}

/// Necessary-condition analysis for a component-box creepage instance.
#[derive(Clone, Debug, PartialEq)]
pub struct CreepageLowerBoundReport {
    pub component_count: usize,
    pub requirement_count: usize,
    pub quotient_class_count: usize,
    pub quotient_class_sizes: Vec<usize>,
    pub max_component_width_mm: f64,
    pub max_component_height_mm: f64,
    pub board_width_mm: f64,
    pub board_height_mm: f64,
    /// One exact maximum-clique certificate for every positive threshold.
    pub threshold_bounds: Vec<ThresholdCliqueBound>,
    /// False only when a necessary condition is violated.  True means only
    /// that this analysis found no contradiction; it is not a feasibility
    /// claim.
    pub passes_necessary_conditions: bool,
}

#[derive(Clone, Debug)]
struct Class {
    refs: Vec<String>,
    dimensions: Vec<(f64, f64)>,
    internal_requirement: f64,
}

fn finite_positive(value: f64, name: &str) -> Result<(), String> {
    if !value.is_finite() || value <= 0.0 {
        return Err(format!("{name} must be finite and positive"));
    }
    Ok(())
}

fn finite_nonnegative(value: f64, name: &str) -> Result<(), String> {
    if !value.is_finite() || value < 0.0 {
        return Err(format!("{name} must be finite and non-negative"));
    }
    Ok(())
}

fn expanded_area(width: f64, height: f64, threshold: f64) -> f64 {
    (width + threshold) * (height + threshold)
}

/// An exact, deterministic maximum weighted clique for a small quotient.
///
/// The branch-and-bound upper bound colors the candidate graph greedily into
/// independent sets.  A clique contains at most one vertex from each color,
/// so summing each color's largest vertex weight is an admissible upper bound.
/// This remains exact even when the quotient is larger than the production
/// eleven classes; it may simply take longer on adversarial graphs.
fn maximum_weighted_clique(
    adjacency: &[Vec<bool>],
    weights: &[f64],
    labels: &[String],
) -> Vec<usize> {
    struct Search<'a> {
        adjacency: &'a [Vec<bool>],
        weights: &'a [f64],
        labels: &'a [String],
        best_weight: f64,
        best: Vec<usize>,
    }

    impl<'a> Search<'a> {
        fn upper_bound(&self, candidates: &[usize]) -> f64 {
            let mut remaining = candidates.to_vec();
            let mut bound = 0.0;
            while !remaining.is_empty() {
                let mut color: Vec<usize> = Vec::new();
                let mut next: Vec<usize> = Vec::new();
                for vertex in remaining {
                    if color.iter().all(|other| !self.adjacency[vertex][*other]) {
                        color.push(vertex);
                    } else {
                        next.push(vertex);
                    }
                }
                bound += color
                    .iter()
                    .map(|vertex| self.weights[*vertex])
                    .fold(0.0, f64::max);
                remaining = next;
            }
            bound
        }

        fn consider(&mut self, current: &mut Vec<usize>, candidates: Vec<usize>, weight: f64) {
            if candidates.is_empty() {
                if weight > self.best_weight
                    || (weight == self.best_weight && self.lexically_precedes(current))
                {
                    self.best_weight = weight;
                    self.best = current.clone();
                }
                return;
            }
            if weight + self.upper_bound(&candidates) < self.best_weight {
                return;
            }

            // Highest degree first improves the bound while lexical labels
            // make equal-degree traversal deterministic.
            let mut ordered = candidates;
            let degree_candidates = ordered.clone();
            ordered.sort_by(|left, right| {
                let left_degree = degree_candidates
                    .iter()
                    .filter(|other| self.adjacency[*left][**other])
                    .count();
                let right_degree = degree_candidates
                    .iter()
                    .filter(|other| self.adjacency[*right][**other])
                    .count();
                right_degree
                    .cmp(&left_degree)
                    .then_with(|| self.labels[*left].cmp(&self.labels[*right]))
            });
            let vertex = ordered[0];
            let rest = ordered[1..].to_vec();

            let included: Vec<usize> = rest
                .iter()
                .copied()
                .filter(|other| self.adjacency[vertex][*other])
                .collect();
            current.push(vertex);
            self.consider(current, included, weight + self.weights[vertex]);
            current.pop();

            self.consider(current, rest, weight);
        }

        fn lexically_precedes(&self, candidate: &[usize]) -> bool {
            let mut left: Vec<&str> = candidate.iter().map(|i| self.labels[*i].as_str()).collect();
            let mut right: Vec<&str> = self.best.iter().map(|i| self.labels[*i].as_str()).collect();
            left.sort_unstable();
            right.sort_unstable();
            left < right
        }
    }

    let mut search = Search {
        adjacency,
        weights,
        labels,
        best_weight: 0.0,
        best: Vec::new(),
    };
    let candidates: Vec<usize> = (0..weights.len()).collect();
    search.consider(&mut Vec::new(), candidates, 0.0);
    search.best
}

fn quotient_classes(
    refs: &[String],
    dimensions: &BTreeMap<String, (f64, f64)>,
    cuts: &BTreeMap<(String, String), f64>,
) -> Result<Vec<Class>, String> {
    let weight = |left: &str, right: &str| {
        let key = if left < right {
            (left.to_owned(), right.to_owned())
        } else {
            (right.to_owned(), left.to_owned())
        };
        cuts.get(&key).copied().unwrap_or(0.0)
    };
    let mut groups: Vec<Vec<String>> = Vec::new();
    for reference in refs {
        let compatible = groups.iter().position(|group| {
            let representative = &group[0];
            refs.iter().all(|other| {
                other == reference
                    || other == representative
                    || weight(reference, other) == weight(representative, other)
            })
        });
        if let Some(index) = compatible {
            groups[index].push(reference.clone());
        } else {
            groups.push(vec![reference.clone()]);
        }
    }
    groups.sort_by(|left, right| left[0].cmp(&right[0]));
    groups
        .into_iter()
        .map(|mut group| {
            group.sort();
            let internal_requirement = group
                .get(1)
                .map(|other| weight(&group[0], other))
                .unwrap_or(0.0);
            let group_dimensions = group
                .iter()
                .map(|reference| {
                    dimensions
                        .get(reference)
                        .copied()
                        .ok_or_else(|| format!("missing component dimensions for {reference}"))
                })
                .collect::<Result<Vec<_>, _>>()?;
            Ok(Class {
                refs: group,
                dimensions: group_dimensions,
                internal_requirement,
            })
        })
        .collect()
}

/// Compute sound necessary lower bounds for the axis-aligned component-box
/// creepage model.  A passing report is explicitly not a feasibility proof.
pub fn analyze_creepage_lower_bounds(
    component_dimensions: Vec<(String, f64, f64)>,
    cuts: Vec<(String, String, f64)>,
    board_width_mm: f64,
    board_height_mm: f64,
) -> Result<CreepageLowerBoundReport, String> {
    finite_positive(board_width_mm, "board_width_mm")?;
    finite_positive(board_height_mm, "board_height_mm")?;
    if component_dimensions.is_empty() {
        return Err("at least one component dimension is required".into());
    }

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

    let refs: Vec<String> = dimensions.keys().cloned().collect();
    let mut normalized_cuts = BTreeMap::<(String, String), f64>::new();
    for (left, right, required) in cuts {
        if left.trim().is_empty() || right.trim().is_empty() || left == right {
            return Err("creepage cuts require two distinct non-empty refs".into());
        }
        if !dimensions.contains_key(&left) || !dimensions.contains_key(&right) {
            return Err("creepage cut references an unknown component".into());
        }
        finite_nonnegative(required, "creepage cut distance")?;
        let key = if left < right {
            (left, right)
        } else {
            (right, left)
        };
        let entry = normalized_cuts.entry(key).or_insert(0.0);
        *entry = entry.max(required);
    }

    let classes = quotient_classes(&refs, &dimensions, &normalized_cuts)?;
    let max_component_width_mm = dimensions.values().map(|(w, _)| *w).fold(0.0, f64::max);
    let max_component_height_mm = dimensions.values().map(|(_, h)| *h).fold(0.0, f64::max);
    let mut thresholds: Vec<f64> = normalized_cuts
        .values()
        .copied()
        .filter(|value| *value > 0.0)
        .collect();
    thresholds.sort_by(f64::total_cmp);
    thresholds.dedup_by(|left, right| left.total_cmp(right).is_eq());

    let mut threshold_bounds = Vec::with_capacity(thresholds.len());
    for threshold in thresholds {
        let class_count = classes.len();
        let mut adjacency = vec![vec![false; class_count]; class_count];
        let mut weights = vec![0.0; class_count];
        let mut members = Vec::<Vec<String>>::with_capacity(class_count);
        for (class_id, class) in classes.iter().enumerate() {
            let mut class_members = Vec::new();
            if class.internal_requirement >= threshold {
                for (reference, (width, height)) in class.refs.iter().zip(&class.dimensions) {
                    weights[class_id] += expanded_area(*width, *height, threshold);
                    class_members.push(reference.clone());
                }
            } else if let Some((index, _)) =
                class
                    .dimensions
                    .iter()
                    .enumerate()
                    .max_by(|(left, (lw, lh)), (right, (rw, rh))| {
                        expanded_area(*lw, *lh, threshold)
                            .total_cmp(&expanded_area(*rw, *rh, threshold))
                            .then_with(|| class.refs[*right].cmp(&class.refs[*left]))
                    })
            {
                let (width, height) = class.dimensions[index];
                weights[class_id] = expanded_area(width, height, threshold);
                class_members.push(class.refs[index].clone());
            }
            members.push(class_members);
        }
        for left in 0..class_count {
            for right in (left + 1)..class_count {
                let key = if classes[left].refs[0] < classes[right].refs[0] {
                    (
                        classes[left].refs[0].clone(),
                        classes[right].refs[0].clone(),
                    )
                } else {
                    (
                        classes[right].refs[0].clone(),
                        classes[left].refs[0].clone(),
                    )
                };
                if normalized_cuts.get(&key).copied().unwrap_or(0.0) >= threshold {
                    adjacency[left][right] = true;
                    adjacency[right][left] = true;
                }
            }
        }
        let labels: Vec<String> = classes.iter().map(|class| class.refs[0].clone()).collect();
        let selected_classes = maximum_weighted_clique(&adjacency, &weights, &labels);
        let mut selected_refs = selected_classes
            .iter()
            .flat_map(|class_id| members[*class_id].iter().cloned())
            .collect::<Vec<_>>();
        selected_refs.sort();
        let expanded_area_mm2 = selected_classes
            .iter()
            .map(|class_id| weights[*class_id])
            .sum::<f64>();
        let board_expanded_area_mm2 = (board_width_mm + threshold) * (board_height_mm + threshold);
        let required_board_width_mm =
            (expanded_area_mm2 / (board_height_mm + threshold) - threshold).max(0.0);
        let required_board_height_mm =
            (expanded_area_mm2 / (board_width_mm + threshold) - threshold).max(0.0);
        threshold_bounds.push(ThresholdCliqueBound {
            threshold_mm: threshold,
            class_ids: selected_classes,
            component_count: selected_refs.len(),
            component_refs: selected_refs,
            expanded_area_mm2,
            board_expanded_area_mm2,
            required_board_width_mm,
            required_board_height_mm,
        });
    }

    let passes_necessary_conditions = max_component_width_mm <= board_width_mm
        && max_component_height_mm <= board_height_mm
        && threshold_bounds.iter().all(|bound| {
            bound.expanded_area_mm2 <= bound.board_expanded_area_mm2
                && bound.required_board_width_mm <= board_width_mm
                && bound.required_board_height_mm <= board_height_mm
        });
    Ok(CreepageLowerBoundReport {
        component_count: dimensions.len(),
        requirement_count: normalized_cuts.len(),
        quotient_class_count: classes.len(),
        quotient_class_sizes: classes.iter().map(|class| class.refs.len()).collect(),
        max_component_width_mm,
        max_component_height_mm,
        board_width_mm,
        board_height_mm,
        threshold_bounds,
        passes_necessary_conditions,
    })
}

/// Thin Python boundary for the Rust-owned necessary-condition analysis.
#[cfg(feature = "python")]
#[pyfunction]
pub fn analyze_creepage_lower_bounds_py(
    component_dimensions: Vec<(String, f64, f64)>,
    cuts: Vec<(String, String, f64)>,
    board_width_mm: f64,
    board_height_mm: f64,
) -> PyResult<CreepageLowerBoundReportPy> {
    let report =
        analyze_creepage_lower_bounds(component_dimensions, cuts, board_width_mm, board_height_mm)
            .map_err(pyo3::exceptions::PyValueError::new_err)?;
    let threshold_bounds = report
        .threshold_bounds
        .into_iter()
        .map(|bound| {
            (
                bound.threshold_mm,
                bound.class_ids,
                bound.component_refs,
                bound.component_count,
                bound.expanded_area_mm2,
                bound.board_expanded_area_mm2,
                bound.required_board_width_mm,
                bound.required_board_height_mm,
            )
        })
        .collect();
    Ok((
        report.component_count,
        report.requirement_count,
        report.quotient_class_count,
        report.quotient_class_sizes,
        report.max_component_width_mm,
        report.max_component_height_mm,
        report.board_width_mm,
        report.board_height_mm,
        threshold_bounds,
        report.passes_necessary_conditions,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dims(names: &[&str], width: f64, height: f64) -> Vec<(String, f64, f64)> {
        names
            .iter()
            .map(|name| ((*name).into(), width, height))
            .collect()
    }

    #[test]
    fn threshold_clique_reports_sound_area_contradiction() {
        let report = analyze_creepage_lower_bounds(
            dims(&["A", "B", "C"], 10.0, 10.0),
            vec![
                ("A".into(), "B".into(), 10.0),
                ("A".into(), "C".into(), 10.0),
                ("B".into(), "C".into(), 10.0),
            ],
            20.0,
            20.0,
        )
        .unwrap();
        assert_eq!(report.quotient_class_count, 1);
        assert!(!report.passes_necessary_conditions);
        let bound = &report.threshold_bounds[0];
        assert_eq!(bound.component_count, 3);
        assert!(bound.expanded_area_mm2 > bound.board_expanded_area_mm2);
    }

    #[test]
    fn false_twin_class_contributes_one_member_and_keeps_bound_sound() {
        let report = analyze_creepage_lower_bounds(
            vec![
                ("A1".into(), 4.0, 4.0),
                ("A2".into(), 100.0, 100.0),
                ("B".into(), 4.0, 4.0),
            ],
            vec![
                ("A1".into(), "B".into(), 1.0),
                ("A2".into(), "B".into(), 1.0),
            ],
            20.0,
            20.0,
        )
        .unwrap();
        assert_eq!(report.quotient_class_sizes, vec![2, 1]);
        let bound = &report.threshold_bounds[0];
        assert_eq!(bound.component_count, 2);
        assert!(bound.component_refs.contains(&"A2".into()));
        assert!(!bound.component_refs.contains(&"A1".into()));
    }

    #[test]
    fn true_twin_class_contributes_all_members() {
        let report = analyze_creepage_lower_bounds(
            dims(&["A1", "A2", "B"], 4.0, 4.0),
            vec![
                ("A1".into(), "A2".into(), 2.0),
                ("A1".into(), "B".into(), 2.0),
                ("A2".into(), "B".into(), 2.0),
            ],
            20.0,
            20.0,
        )
        .unwrap();
        assert_eq!(report.quotient_class_sizes, vec![3]);
        assert_eq!(report.threshold_bounds[0].component_count, 3);
    }

    #[test]
    fn board_dimension_violation_is_reported_without_pair_requirements() {
        let report =
            analyze_creepage_lower_bounds(vec![("A".into(), 21.0, 2.0)], Vec::new(), 20.0, 20.0)
                .unwrap();
        assert!(!report.passes_necessary_conditions);
        assert!(report.threshold_bounds.is_empty());
    }

    #[test]
    fn malformed_input_fails_closed() {
        assert!(
            analyze_creepage_lower_bounds(
                vec![("A".into(), 1.0, 1.0)],
                vec![("A".into(), "X".into(), 1.0)],
                20.0,
                20.0,
            )
            .is_err()
        );
        assert!(analyze_creepage_lower_bounds(
            vec![("A".into(), 1.0, 1.0)],
            Vec::new(),
            f64::NAN,
            20.0,
        )
        .is_err());
    }

    #[test]
    fn passing_area_bound_is_not_a_feasibility_claim() {
        // Two 4.2 mm squares with a 1 mm L-infinity requirement cannot fit
        // in a 9x9 board: neither a horizontal stack (4.2+1+4.2 > 9) nor a
        // vertical stack is possible.  The expanded-area condition alone
        // misses this packing obstruction, as every necessary relaxation may.
        let report = analyze_creepage_lower_bounds(
            dims(&["A", "B"], 4.2, 4.2),
            vec![("A".into(), "B".into(), 1.0)],
            9.0,
            9.0,
        )
        .unwrap();
        assert!(report.passes_necessary_conditions);
        assert!(
            report.threshold_bounds[0].expanded_area_mm2
                <= report.threshold_bounds[0].board_expanded_area_mm2
        );
    }
}

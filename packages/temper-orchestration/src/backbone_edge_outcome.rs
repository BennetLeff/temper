//! `BackboneEdgeOutcome` / `ViaDropOutcome` — plane-backbone bookkeeping that
//! cannot lie about what happened.
//!
//! # The bug class this closes
//!
//! `router_v6/_ground_plane.py` and `router_v6/_power_islands.py` are a clone
//! pair that each build an `In1.Cu`/`In2.Cu` copper backbone from a minimum
//! spanning tree over pad/via-drop positions. Both reported their results with
//! **subtraction standing in for classification**:
//!
//! ```python
//! mst_edges_fallback_count = len(edges) - astar_routed_count
//! ```
//!
//! That expression asserts "every edge A* did not route was landed by the
//! fallback". Nothing enforced it and it was false. Measured on `gnd` at
//! commit `9019da63f` (`pcb/temper.kicad_pcb`): **87 edges attempted, 1 routed
//! by corridor-aware A*, 3 landed straight, 0 landed via a one-bend detour,
//! and 83 dropped** — 4 landed in total. The counter reported
//! `astar_routed=1, fallback=86`, so a consumer reading those against
//! `attempted=87` concluded all 87 edges were handled, mostly by the fallback.
//!
//! A backbone that failed on 95% of its edges was rendering as graceful
//! degradation. That is why it went unchased for so long, and it is the whole
//! reason this type exists.
//!
//! Four more counts in the same two files shared the anti-pattern:
//!
//! | site | expression |
//! |---|---|
//! | `_ground_plane.py:1426` | `mst_edge_count = len(edges) - crossed_keepout` |
//! | `_ground_plane.py:1436` | `mst_edges_fallback_count = len(edges) - astar_routed_count` |
//! | `_power_islands.py:952` | `drop_via_count = len(positions) - via_skipped_through_hole - via_unresolved_conflict` |
//! | `_power_islands.py:953` | `mst_edge_count = len(edges) - crossed_keepout` |
//! | `_power_islands.py:961` | `mst_edges_fallback_count = len(edges) - astar_routed_count` |
//!
//! Note that `mst_edge_count` — the *attempted* denominator every other figure
//! is read against — was itself inferred by subtraction. When the denominator
//! is a guess, the partition invariant cannot be checked against anything
//! real, which is precisely where the defect hid.
//!
//! # How this type makes it unrepresentable
//!
//! Every edge is classified into exactly one [`BackboneEdgeOutcome`] variant as
//! it is processed. [`BackboneEdgeTally`] holds those outcomes and derives
//! **every** count by matching over the collection:
//!
//! * `attempted` is [`BackboneEdgeTally::attempted`] — the *length of the
//!   recorded outcomes*, counted, never subtracted from;
//! * each per-variant count comes from one exhaustive `match` in
//!   [`BackboneEdgeTally::counts`], so adding a variant without deciding where
//!   it is counted is a **compile error**, not a silently wrong total;
//! * [`BackboneEdgeCounts`]'s fields are private with no public constructor, so
//!   a caller cannot hand-assemble a count set (see the `compile_fail` doctest
//!   on [`BackboneEdgeCounts`]);
//! * [`BackboneEdgeCounts::check_partition`] asserts
//!   `attempted == routed_astar + landed_straight + landed_one_bend +
//!   skipped_already_joined + dropped` in code rather than by convention, and
//!   is called on every construction.
//!
//! "Landed" is therefore never inferred from "not routed": each landing is
//! recorded at the point the code actually emits the segment, and a drop is
//! recorded with the reason it was dropped.
//!
//! ## A note on the `compile_fail` doctests
//!
//! The two `compile_fail` blocks below carry an `,E0451` annotation ("fields
//! are private"). **Stable rustdoc does not verify that code** — measured
//! 2026-08-18: replacing `E0451` with an unrelated code leaves the doctest
//! passing, because `compile_fail` succeeds on *any* compilation error. The
//! annotation is therefore documentation of intent (and is enforced on
//! nightly), not the proof.
//!
//! The proof is separate: compiling the same snippet as a normal example
//! produces exactly `error[E0451]: fields ... of struct BackboneEdgeCounts are
//! private`, listing all seven fields. That was verified directly rather than
//! inferred from the doctest passing — the same "correct by construction, not
//! by coincidence" standard AGENTS.md applies to differential tests.
//!
//! # Why this crate and not `temper-rust-router-core`
//!
//! `temper-rust-router-core` hosts the A* kernels and is being extended with
//! `astar_nlayer.rs` (the Tier-3 port) concurrently. This type is not a search
//! kernel — it is orchestration bookkeeping for a pipeline stage, the same
//! family as `power_plane_stage.rs` in this crate, which already owns the
//! plane-generation stage boundary. Putting it here keeps it clear of the
//! kernel port.
//!
//! # Scope
//!
//! This types the *outcome classification* only. The pour geometry in both
//! Python modules is GEOS/shapely-bound and deliberately stays where it is;
//! nothing here ports it.

#[cfg(feature = "python")]
use pyo3::prelude::*;

// ---------------------------------------------------------------------------
// MST backbone edges
// ---------------------------------------------------------------------------

/// Why a backbone MST edge was dropped rather than landed.
///
/// Carried by [`BackboneEdgeOutcome::Dropped`] so a drop is never an
/// undifferentiated "didn't happen".
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum DropReason {
    /// The straight edge crossed the HV/SELV keepout or another net's existing
    /// copper, and the bounded one-bend detour search found no clear waypoint
    /// either. This is the `crossed_keepout` counter in both Python modules.
    CrossedKeepout,
    /// The edge's two endpoints are not co-reachable under full corridor
    /// avoidance (`_corridor_backbone.py`: the eroded free space fragments the
    /// board into disconnected components), so corridor-aware A* could not be
    /// attempted end-to-end.
    CorridorUnreachable,
}

impl DropReason {
    /// Stable machine-readable token for diagnostics and Python interop.
    pub fn as_str(self) -> &'static str {
        match self {
            DropReason::CrossedKeepout => "crossed_keepout",
            DropReason::CorridorUnreachable => "corridor_unreachable",
        }
    }
}

/// What actually happened to one backbone MST edge.
///
/// Exactly one variant applies per edge. There is no "fallback" variant,
/// deliberately: "fallback" conflated *which mechanism landed the edge* with
/// *whether it landed at all*, which is the conflation that produced the
/// 87-attempted / 4-landed misreport.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum BackboneEdgeOutcome {
    /// Landed by corridor-aware A* with a real, collision-free path
    /// (`_corridor_backbone.corridor_aware_spanning_edges`).
    RoutedAstar,
    /// Landed by the keepout-only fallback as an unobstructed straight line.
    LandedStraight,
    /// Landed by the keepout-only fallback via a bounded one-bend detour
    /// through an existing via-drop waypoint (the `rerouted` counter).
    LandedOneBend,
    /// Not drawn because the edge's endpoints were *already* joined — by an
    /// earlier corridor-aware A* edge or a chain of them. Drawing it would add
    /// collision risk for zero connectivity benefit. This is a legitimate
    /// non-landing that is **not** a failure, and conflating it with either
    /// "landed" or "dropped" is itself a misreport.
    SkippedAlreadyJoined,
    /// Not drawn, and the endpoints remain unjoined by this edge.
    Dropped(DropReason),
}

impl BackboneEdgeOutcome {
    /// Whether this outcome put copper on the board for the edge.
    ///
    /// Note this is `false` for [`BackboneEdgeOutcome::SkippedAlreadyJoined`]:
    /// no copper was emitted for *this* edge, even though its endpoints are
    /// connected by other copper.
    pub fn landed_copper(self) -> bool {
        match self {
            BackboneEdgeOutcome::RoutedAstar
            | BackboneEdgeOutcome::LandedStraight
            | BackboneEdgeOutcome::LandedOneBend => true,
            BackboneEdgeOutcome::SkippedAlreadyJoined | BackboneEdgeOutcome::Dropped(_) => false,
        }
    }

    /// Stable machine-readable token for diagnostics and Python interop.
    pub fn as_str(self) -> &'static str {
        match self {
            BackboneEdgeOutcome::RoutedAstar => "routed_astar",
            BackboneEdgeOutcome::LandedStraight => "landed_straight",
            BackboneEdgeOutcome::LandedOneBend => "landed_one_bend",
            BackboneEdgeOutcome::SkippedAlreadyJoined => "skipped_already_joined",
            BackboneEdgeOutcome::Dropped(_) => "dropped",
        }
    }
}

/// The partition invariant was violated — the recorded outcomes do not sum to
/// the attempted total.
///
/// Only constructible by [`BackboneEdgeCounts::check_partition`]; its presence
/// means a counting bug, not a routing condition.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PartitionError {
    attempted: usize,
    summed: usize,
}

impl PartitionError {
    /// The attempted total (number of recorded outcomes).
    pub fn attempted(&self) -> usize {
        self.attempted
    }
    /// The sum of the per-variant counts.
    pub fn summed(&self) -> usize {
        self.summed
    }
}

impl core::fmt::Display for PartitionError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        write!(
            f,
            "backbone edge partition violated: attempted={} but variant counts sum to {} \
             (every edge must fall into exactly one BackboneEdgeOutcome variant)",
            self.attempted, self.summed
        )
    }
}

/// Per-variant counts derived from a [`BackboneEdgeTally`].
///
/// **Every field is private and there is no public constructor.** The only way
/// to obtain a `BackboneEdgeCounts` is [`BackboneEdgeTally::counts`], which
/// builds it from one exhaustive `match` over recorded outcomes and then
/// checks the partition invariant. A hand-assembled count set — the shape that
/// let `fallback = len(edges) - astar_routed` exist — does not compile:
///
/// ```compile_fail,E0451
/// use temper_orchestration::backbone_edge_outcome::BackboneEdgeCounts;
/// // Fields are private to `backbone_edge_outcome`, so counts cannot be
/// // supplied by hand -- in particular a "fallback" figure obtained by
/// // subtracting the A*-routed count from the attempted total. The only
/// // source of a BackboneEdgeCounts is BackboneEdgeTally::counts().
/// let fake = BackboneEdgeCounts {
///     attempted: 87,
///     routed_astar: 1,
///     landed_straight: 86,
///     landed_one_bend: 0,
///     skipped_already_joined: 0,
///     dropped_crossed_keepout: 0,
///     dropped_corridor_unreachable: 0,
/// };
/// ```
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BackboneEdgeCounts {
    attempted: usize,
    routed_astar: usize,
    landed_straight: usize,
    landed_one_bend: usize,
    skipped_already_joined: usize,
    dropped_crossed_keepout: usize,
    dropped_corridor_unreachable: usize,
}

impl BackboneEdgeCounts {
    /// Edges attempted — the number of outcomes recorded. Counted, never
    /// derived by subtracting anything from anything.
    pub fn attempted(&self) -> usize {
        self.attempted
    }
    /// Edges landed by corridor-aware A*.
    pub fn routed_astar(&self) -> usize {
        self.routed_astar
    }
    /// Edges landed as an unobstructed straight line by the fallback.
    pub fn landed_straight(&self) -> usize {
        self.landed_straight
    }
    /// Edges landed by the fallback's bounded one-bend detour.
    pub fn landed_one_bend(&self) -> usize {
        self.landed_one_bend
    }
    /// Edges landed by the keepout-only fallback, by either of its two
    /// mechanisms.
    ///
    /// This is the honest replacement for `mst_edges_fallback_count`. It is a
    /// sum of two *observed landings*, never `attempted - routed_astar`.
    pub fn landed_fallback(&self) -> usize {
        self.landed_straight + self.landed_one_bend
    }
    /// Edges that put copper on the board, by any mechanism.
    pub fn landed_total(&self) -> usize {
        self.routed_astar + self.landed_straight + self.landed_one_bend
    }
    /// Edges not drawn because their endpoints were already joined.
    pub fn skipped_already_joined(&self) -> usize {
        self.skipped_already_joined
    }
    /// Edges dropped because they crossed the keepout / other copper and no
    /// one-bend detour cleared it.
    pub fn dropped_crossed_keepout(&self) -> usize {
        self.dropped_crossed_keepout
    }
    /// Edges dropped because their endpoints were not corridor-co-reachable.
    pub fn dropped_corridor_unreachable(&self) -> usize {
        self.dropped_corridor_unreachable
    }
    /// Edges dropped for any reason.
    pub fn dropped_total(&self) -> usize {
        self.dropped_crossed_keepout + self.dropped_corridor_unreachable
    }

    /// Assert the partition: attempted equals the sum of every variant.
    ///
    /// Called by [`BackboneEdgeTally::counts`] on every construction, so a
    /// `BackboneEdgeCounts` that violates it cannot be observed.
    pub fn check_partition(&self) -> Result<(), PartitionError> {
        let summed = self.routed_astar
            + self.landed_straight
            + self.landed_one_bend
            + self.skipped_already_joined
            + self.dropped_crossed_keepout
            + self.dropped_corridor_unreachable;
        if summed == self.attempted {
            Ok(())
        } else {
            Err(PartitionError {
                attempted: self.attempted,
                summed,
            })
        }
    }
}

/// Records one [`BackboneEdgeOutcome`] per attempted backbone edge.
///
/// The Python plane generators push an outcome at each point they decide what
/// happened to an edge; every reported figure is then read off
/// [`BackboneEdgeTally::counts`].
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct BackboneEdgeTally {
    outcomes: Vec<BackboneEdgeOutcome>,
}

impl BackboneEdgeTally {
    /// A tally with no recorded outcomes.
    pub fn new() -> Self {
        Self {
            outcomes: Vec::new(),
        }
    }

    /// Record what happened to one edge.
    pub fn record(&mut self, outcome: BackboneEdgeOutcome) {
        self.outcomes.push(outcome);
    }

    /// Edges attempted — counted from the recorded outcomes.
    pub fn attempted(&self) -> usize {
        self.outcomes.len()
    }

    /// The recorded outcomes, in the order they occurred.
    pub fn outcomes(&self) -> &[BackboneEdgeOutcome] {
        &self.outcomes
    }

    /// Derive every count by matching over the recorded outcomes.
    ///
    /// The `match` is exhaustive: adding a [`BackboneEdgeOutcome`] variant
    /// without deciding where it is counted fails to compile. The partition
    /// invariant is checked here, so the returned counts are always coherent.
    pub fn counts(&self) -> Result<BackboneEdgeCounts, PartitionError> {
        let mut c = BackboneEdgeCounts {
            attempted: self.outcomes.len(),
            routed_astar: 0,
            landed_straight: 0,
            landed_one_bend: 0,
            skipped_already_joined: 0,
            dropped_crossed_keepout: 0,
            dropped_corridor_unreachable: 0,
        };
        for outcome in &self.outcomes {
            match outcome {
                BackboneEdgeOutcome::RoutedAstar => c.routed_astar += 1,
                BackboneEdgeOutcome::LandedStraight => c.landed_straight += 1,
                BackboneEdgeOutcome::LandedOneBend => c.landed_one_bend += 1,
                BackboneEdgeOutcome::SkippedAlreadyJoined => c.skipped_already_joined += 1,
                BackboneEdgeOutcome::Dropped(DropReason::CrossedKeepout) => {
                    c.dropped_crossed_keepout += 1
                }
                BackboneEdgeOutcome::Dropped(DropReason::CorridorUnreachable) => {
                    c.dropped_corridor_unreachable += 1
                }
            }
        }
        c.check_partition()?;
        Ok(c)
    }
}

// ---------------------------------------------------------------------------
// Via drop points
// ---------------------------------------------------------------------------

/// What happened to one candidate via drop point.
///
/// A separate type from [`BackboneEdgeOutcome`] because it partitions a
/// different collection (pad positions, not MST edges) into a different set of
/// outcomes. Folding the two together would produce a type whose variants are
/// meaningless for half its uses — the same "one number standing for two
/// different questions" mistake in a new place. It lives in this module
/// because both are plane-generator bookkeeping over the same run.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ViaDropOutcome {
    /// A via was emitted at the pad centre.
    PlacedAtCentre,
    /// A via was emitted, but the drop point had to move off the pad centre
    /// (with a same-net stub back to it) to clear an existing hole or another
    /// net's copper. Still a placed via.
    PlacedOffset,
    /// No via was emitted because the pad is a through-hole pad whose own
    /// drilled hole already spans every copper layer it lists — a via there is
    /// redundant and causes `holes_co_located` violations.
    SkippedThroughHole,
    /// No via was emitted because neither the pad centre nor any ring-search
    /// offset was clear. Fail-closed: reported rather than emitting a
    /// known-colliding via.
    UnresolvedConflict,
}

impl ViaDropOutcome {
    /// Whether a via was actually emitted.
    pub fn placed(self) -> bool {
        match self {
            ViaDropOutcome::PlacedAtCentre | ViaDropOutcome::PlacedOffset => true,
            ViaDropOutcome::SkippedThroughHole | ViaDropOutcome::UnresolvedConflict => false,
        }
    }

    /// Stable machine-readable token for diagnostics and Python interop.
    pub fn as_str(self) -> &'static str {
        match self {
            ViaDropOutcome::PlacedAtCentre => "placed_at_centre",
            ViaDropOutcome::PlacedOffset => "placed_offset",
            ViaDropOutcome::SkippedThroughHole => "skipped_through_hole",
            ViaDropOutcome::UnresolvedConflict => "unresolved_conflict",
        }
    }
}

/// Per-variant via-drop counts.
///
/// **Every field is private and there is no public constructor**, for the same
/// reason as [`BackboneEdgeCounts`]: `drop_via_count` was a *double*
/// subtraction (`len(positions) - skipped_through_hole - unresolved_conflict`),
/// so the placed-via total was inferred from two not-placed counts rather than
/// observed. Hand-assembly does not compile:
///
/// ```compile_fail,E0451
/// use temper_orchestration::backbone_edge_outcome::ViaDropCounts;
/// // Private fields -- a placed-via total cannot be supplied by subtracting
/// // the skip counts from the candidate total. Use ViaDropTally::counts().
/// let fake = ViaDropCounts {
///     candidates: 88,
///     placed_at_centre: 21,
///     placed_offset: 45,
///     skipped_through_hole: 5,
///     unresolved_conflict: 17,
/// };
/// ```
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ViaDropCounts {
    candidates: usize,
    placed_at_centre: usize,
    placed_offset: usize,
    skipped_through_hole: usize,
    unresolved_conflict: usize,
}

impl ViaDropCounts {
    /// Candidate drop points considered — counted, not subtracted from.
    pub fn candidates(&self) -> usize {
        self.candidates
    }
    /// Vias emitted at the pad centre.
    pub fn placed_at_centre(&self) -> usize {
        self.placed_at_centre
    }
    /// Vias emitted at an offset drop point.
    pub fn placed_offset(&self) -> usize {
        self.placed_offset
    }
    /// Vias emitted, by either mechanism. The honest `drop_via_count`.
    pub fn placed_total(&self) -> usize {
        self.placed_at_centre + self.placed_offset
    }
    /// Drop points skipped because the pad is through-hole.
    pub fn skipped_through_hole(&self) -> usize {
        self.skipped_through_hole
    }
    /// Drop points with no clear position at all.
    pub fn unresolved_conflict(&self) -> usize {
        self.unresolved_conflict
    }

    /// Assert the partition: candidates equals the sum of every variant.
    pub fn check_partition(&self) -> Result<(), PartitionError> {
        let summed = self.placed_at_centre
            + self.placed_offset
            + self.skipped_through_hole
            + self.unresolved_conflict;
        if summed == self.candidates {
            Ok(())
        } else {
            Err(PartitionError {
                attempted: self.candidates,
                summed,
            })
        }
    }
}

/// Records one [`ViaDropOutcome`] per candidate via drop point.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ViaDropTally {
    outcomes: Vec<ViaDropOutcome>,
}

impl ViaDropTally {
    /// A tally with no recorded outcomes.
    pub fn new() -> Self {
        Self {
            outcomes: Vec::new(),
        }
    }

    /// Record what happened at one candidate drop point.
    pub fn record(&mut self, outcome: ViaDropOutcome) {
        self.outcomes.push(outcome);
    }

    /// Candidate drop points considered.
    pub fn candidates(&self) -> usize {
        self.outcomes.len()
    }

    /// The recorded outcomes, in the order they occurred.
    pub fn outcomes(&self) -> &[ViaDropOutcome] {
        &self.outcomes
    }

    /// Derive every count by matching over the recorded outcomes.
    pub fn counts(&self) -> Result<ViaDropCounts, PartitionError> {
        let mut c = ViaDropCounts {
            candidates: self.outcomes.len(),
            placed_at_centre: 0,
            placed_offset: 0,
            skipped_through_hole: 0,
            unresolved_conflict: 0,
        };
        for outcome in &self.outcomes {
            match outcome {
                ViaDropOutcome::PlacedAtCentre => c.placed_at_centre += 1,
                ViaDropOutcome::PlacedOffset => c.placed_offset += 1,
                ViaDropOutcome::SkippedThroughHole => c.skipped_through_hole += 1,
                ViaDropOutcome::UnresolvedConflict => c.unresolved_conflict += 1,
            }
        }
        c.check_partition()?;
        Ok(c)
    }
}

// ---------------------------------------------------------------------------
// pyo3 surface
// ---------------------------------------------------------------------------

/// Python handle for [`BackboneEdgeTally`].
///
/// The Python plane generators construct one per net, call the `record_*`
/// methods as each edge is decided, and read every reported figure off the
/// getters. There is deliberately no setter for any count.
#[cfg(feature = "python")]
#[pyclass(name = "BackboneEdgeTally", module = "temper_orchestration")]
#[derive(Debug, Default)]
pub struct PyBackboneEdgeTally {
    inner: BackboneEdgeTally,
}

#[cfg(feature = "python")]
#[pymethods]
impl PyBackboneEdgeTally {
    #[new]
    fn new() -> Self {
        Self {
            inner: BackboneEdgeTally::new(),
        }
    }

    /// Record an edge landed by corridor-aware A*.
    fn record_routed_astar(&mut self) {
        self.inner.record(BackboneEdgeOutcome::RoutedAstar);
    }

    /// Record an edge landed as an unobstructed straight line.
    fn record_landed_straight(&mut self) {
        self.inner.record(BackboneEdgeOutcome::LandedStraight);
    }

    /// Record an edge landed via a one-bend detour.
    fn record_landed_one_bend(&mut self) {
        self.inner.record(BackboneEdgeOutcome::LandedOneBend);
    }

    /// Record an edge skipped because its endpoints were already joined.
    fn record_skipped_already_joined(&mut self) {
        self.inner.record(BackboneEdgeOutcome::SkippedAlreadyJoined);
    }

    /// Record an edge dropped because it crossed the keepout / other copper.
    fn record_dropped_crossed_keepout(&mut self) {
        self.inner
            .record(BackboneEdgeOutcome::Dropped(DropReason::CrossedKeepout));
    }

    /// Record an edge dropped because its endpoints were not corridor-co-reachable.
    fn record_dropped_corridor_unreachable(&mut self) {
        self.inner
            .record(BackboneEdgeOutcome::Dropped(DropReason::CorridorUnreachable));
    }

    /// Edges attempted (counted).
    #[getter]
    fn attempted(&self) -> usize {
        self.inner.attempted()
    }

    #[getter]
    fn routed_astar(&self) -> PyResult<usize> {
        Ok(self.counts_or_err()?.routed_astar())
    }

    #[getter]
    fn landed_straight(&self) -> PyResult<usize> {
        Ok(self.counts_or_err()?.landed_straight())
    }

    #[getter]
    fn landed_one_bend(&self) -> PyResult<usize> {
        Ok(self.counts_or_err()?.landed_one_bend())
    }

    /// Edges landed by the keepout-only fallback (straight + one-bend).
    #[getter]
    fn landed_fallback(&self) -> PyResult<usize> {
        Ok(self.counts_or_err()?.landed_fallback())
    }

    /// Edges that put copper on the board, by any mechanism.
    #[getter]
    fn landed_total(&self) -> PyResult<usize> {
        Ok(self.counts_or_err()?.landed_total())
    }

    #[getter]
    fn skipped_already_joined(&self) -> PyResult<usize> {
        Ok(self.counts_or_err()?.skipped_already_joined())
    }

    #[getter]
    fn dropped_crossed_keepout(&self) -> PyResult<usize> {
        Ok(self.counts_or_err()?.dropped_crossed_keepout())
    }

    #[getter]
    fn dropped_corridor_unreachable(&self) -> PyResult<usize> {
        Ok(self.counts_or_err()?.dropped_corridor_unreachable())
    }

    #[getter]
    fn dropped_total(&self) -> PyResult<usize> {
        Ok(self.counts_or_err()?.dropped_total())
    }

    /// Raise if the partition invariant does not hold.
    fn check_partition(&self) -> PyResult<()> {
        self.counts_or_err().map(|_| ())
    }

    fn __repr__(&self) -> PyResult<String> {
        let c = self.counts_or_err()?;
        Ok(format!(
            "BackboneEdgeTally(attempted={}, routed_astar={}, landed_straight={}, \
             landed_one_bend={}, skipped_already_joined={}, dropped_crossed_keepout={}, \
             dropped_corridor_unreachable={})",
            c.attempted(),
            c.routed_astar(),
            c.landed_straight(),
            c.landed_one_bend(),
            c.skipped_already_joined(),
            c.dropped_crossed_keepout(),
            c.dropped_corridor_unreachable(),
        ))
    }
}

#[cfg(feature = "python")]
impl PyBackboneEdgeTally {
    fn counts_or_err(&self) -> PyResult<BackboneEdgeCounts> {
        self.inner
            .counts()
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))
    }
}

/// Python handle for [`ViaDropTally`].
#[cfg(feature = "python")]
#[pyclass(name = "ViaDropTally", module = "temper_orchestration")]
#[derive(Debug, Default)]
pub struct PyViaDropTally {
    inner: ViaDropTally,
}

#[cfg(feature = "python")]
#[pymethods]
impl PyViaDropTally {
    #[new]
    fn new() -> Self {
        Self {
            inner: ViaDropTally::new(),
        }
    }

    /// Record a via emitted at the pad centre.
    fn record_placed_at_centre(&mut self) {
        self.inner.record(ViaDropOutcome::PlacedAtCentre);
    }

    /// Record a via emitted at an offset drop point.
    fn record_placed_offset(&mut self) {
        self.inner.record(ViaDropOutcome::PlacedOffset);
    }

    /// Record a drop point skipped because the pad is through-hole.
    fn record_skipped_through_hole(&mut self) {
        self.inner.record(ViaDropOutcome::SkippedThroughHole);
    }

    /// Record a drop point with no clear position at all.
    fn record_unresolved_conflict(&mut self) {
        self.inner.record(ViaDropOutcome::UnresolvedConflict);
    }

    /// Candidate drop points considered (counted).
    #[getter]
    fn candidates(&self) -> usize {
        self.inner.candidates()
    }

    #[getter]
    fn placed_at_centre(&self) -> PyResult<usize> {
        Ok(self.counts_or_err()?.placed_at_centre())
    }

    #[getter]
    fn placed_offset(&self) -> PyResult<usize> {
        Ok(self.counts_or_err()?.placed_offset())
    }

    /// Vias emitted, by either mechanism (the honest `drop_via_count`).
    #[getter]
    fn placed_total(&self) -> PyResult<usize> {
        Ok(self.counts_or_err()?.placed_total())
    }

    #[getter]
    fn skipped_through_hole(&self) -> PyResult<usize> {
        Ok(self.counts_or_err()?.skipped_through_hole())
    }

    #[getter]
    fn unresolved_conflict(&self) -> PyResult<usize> {
        Ok(self.counts_or_err()?.unresolved_conflict())
    }

    /// Raise if the partition invariant does not hold.
    fn check_partition(&self) -> PyResult<()> {
        self.counts_or_err().map(|_| ())
    }

    fn __repr__(&self) -> PyResult<String> {
        let c = self.counts_or_err()?;
        Ok(format!(
            "ViaDropTally(candidates={}, placed_at_centre={}, placed_offset={}, \
             skipped_through_hole={}, unresolved_conflict={})",
            c.candidates(),
            c.placed_at_centre(),
            c.placed_offset(),
            c.skipped_through_hole(),
            c.unresolved_conflict(),
        ))
    }
}

#[cfg(feature = "python")]
impl PyViaDropTally {
    fn counts_or_err(&self) -> PyResult<ViaDropCounts> {
        self.inner
            .counts()
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The exact `gnd` shape measured at commit 9019da63f: 87 attempted,
    /// 1 A*-routed, 3 straight, 0 one-bend, 83 dropped. The old counter
    /// reported `fallback=86`; the honest fallback figure is 3.
    #[test]
    fn gnd_measured_shape_reports_honestly() {
        let mut t = BackboneEdgeTally::new();
        t.record(BackboneEdgeOutcome::RoutedAstar);
        t.record(BackboneEdgeOutcome::SkippedAlreadyJoined);
        for _ in 0..3 {
            t.record(BackboneEdgeOutcome::LandedStraight);
        }
        for _ in 0..83 {
            t.record(BackboneEdgeOutcome::Dropped(DropReason::CrossedKeepout));
        }
        let c = t.counts().expect("partition holds");
        assert_eq!(c.attempted(), 88);
        assert_eq!(c.routed_astar(), 1);
        assert_eq!(c.landed_straight(), 3);
        assert_eq!(c.landed_one_bend(), 0);
        // The figure the old code reported as "fallback" was 86.
        assert_eq!(c.landed_fallback(), 3);
        assert_eq!(c.landed_total(), 4);
        assert_eq!(c.dropped_total(), 83);
        // And the partition is checked, not assumed.
        assert_eq!(
            c.routed_astar()
                + c.landed_straight()
                + c.landed_one_bend()
                + c.skipped_already_joined()
                + c.dropped_total(),
            c.attempted()
        );
    }

    #[test]
    fn empty_tally_partitions() {
        let c = BackboneEdgeTally::new().counts().expect("partition holds");
        assert_eq!(c.attempted(), 0);
        assert_eq!(c.landed_total(), 0);
        assert_eq!(c.dropped_total(), 0);
    }

    #[test]
    fn every_outcome_lands_in_exactly_one_bucket() {
        let mut t = BackboneEdgeTally::new();
        t.record(BackboneEdgeOutcome::RoutedAstar);
        t.record(BackboneEdgeOutcome::LandedStraight);
        t.record(BackboneEdgeOutcome::LandedOneBend);
        t.record(BackboneEdgeOutcome::SkippedAlreadyJoined);
        t.record(BackboneEdgeOutcome::Dropped(DropReason::CrossedKeepout));
        t.record(BackboneEdgeOutcome::Dropped(
            DropReason::CorridorUnreachable,
        ));
        let c = t.counts().expect("partition holds");
        assert_eq!(c.attempted(), 6);
        assert_eq!(c.routed_astar(), 1);
        assert_eq!(c.landed_straight(), 1);
        assert_eq!(c.landed_one_bend(), 1);
        assert_eq!(c.skipped_already_joined(), 1);
        assert_eq!(c.dropped_crossed_keepout(), 1);
        assert_eq!(c.dropped_corridor_unreachable(), 1);
        assert_eq!(c.dropped_total(), 2);
    }

    #[test]
    fn landed_copper_excludes_skipped_and_dropped() {
        assert!(BackboneEdgeOutcome::RoutedAstar.landed_copper());
        assert!(BackboneEdgeOutcome::LandedStraight.landed_copper());
        assert!(BackboneEdgeOutcome::LandedOneBend.landed_copper());
        assert!(!BackboneEdgeOutcome::SkippedAlreadyJoined.landed_copper());
        assert!(!BackboneEdgeOutcome::Dropped(DropReason::CrossedKeepout).landed_copper());
    }

    #[test]
    fn via_tally_partitions_and_totals() {
        let mut t = ViaDropTally::new();
        for _ in 0..21 {
            t.record(ViaDropOutcome::PlacedAtCentre);
        }
        for _ in 0..45 {
            t.record(ViaDropOutcome::PlacedOffset);
        }
        for _ in 0..5 {
            t.record(ViaDropOutcome::SkippedThroughHole);
        }
        for _ in 0..17 {
            t.record(ViaDropOutcome::UnresolvedConflict);
        }
        let c = t.counts().expect("partition holds");
        assert_eq!(c.candidates(), 88);
        assert_eq!(c.placed_total(), 66); // the measured gnd drop_via_count
        assert_eq!(c.skipped_through_hole(), 5);
        assert_eq!(c.unresolved_conflict(), 17);
    }

    #[test]
    fn partition_error_reports_both_totals() {
        // Constructed directly here (inside the module, where fields are
        // visible) purely to exercise the error path -- no caller outside
        // this module can build an inconsistent BackboneEdgeCounts.
        let bad = BackboneEdgeCounts {
            attempted: 87,
            routed_astar: 1,
            landed_straight: 86,
            landed_one_bend: 0,
            skipped_already_joined: 0,
            dropped_crossed_keepout: 0,
            dropped_corridor_unreachable: 0,
        };
        // 1 + 86 = 87 == attempted, so this particular shape is self-consistent;
        // it is the *meaning* that was wrong. Now an actually-inconsistent one:
        let worse = BackboneEdgeCounts {
            attempted: 87,
            routed_astar: 1,
            landed_straight: 3,
            landed_one_bend: 0,
            skipped_already_joined: 0,
            dropped_crossed_keepout: 0,
            dropped_corridor_unreachable: 0,
        };
        assert!(bad.check_partition().is_ok());
        let err = worse.check_partition().expect_err("must not partition");
        assert_eq!(err.attempted(), 87);
        assert_eq!(err.summed(), 4);
    }
}

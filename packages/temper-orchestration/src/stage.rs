// U0 scaffolding (`dead_code` note): the plan's U0 unit is pure scaffolding —
// "the engine (no migration, pure scaffolding)". The `Stage` trait, the
// contract types and `StageError` have no production consumer until Phase C
// lands the first real stage (preflight, U3) and Phase D the deterministic
// batches. Until then clippy's `-D warnings` (`dead_code`) fires on the lib
// target for these items; the allow below is the plan's explicit U0
// carve-out, to be removed as consumers land.
#![allow(dead_code)]

// The Rust `Stage` trait and its supporting contract/error types — the
// orchestration engine's migration interface (Rust Orchestration Engine
// plan 2026-08-09-001, U0 scaffolding).
//
// Mirror of Python `deterministic.stages.base.Stage(ABC)`. The trait is
// generic over `S` (defaulting to `BoardState`) so it can be tested against
// trivial state types (e.g. `u32` in the runner unit tests) before
// `BoardState`'s full type graph is typed. A stage receives an immutable
// `S` and returns a (possibly-copied) `S`, exactly like the Python pattern;
// `run` additionally surfaces failures explicitly as `Err(StageError)`
// (Python `run()` raised exceptions; the Rust form lets the
// `PipelineRunner` collect several errors into a report).

use std::borrow::Cow;
use std::fmt;

#[cfg(feature = "python")]
use crate::board_state::BoardState;

#[cfg(feature = "python")]
/// A single pipeline stage that transforms a typed state.
///
/// The migration endpoint for the Python `Stage(ABC).run(BoardState) ->
/// BoardState` pattern. Every deterministic stage and router_v6 check
/// becomes a Rust `Stage` implementation over time; `PipelineRunner`
/// sequences `Box<dyn Stage<S>>` instances.
pub trait Stage<S = BoardState> {
    /// Human-readable stage name (used in reports/traces).
    fn name(&self) -> Cow<'static, str>;

    /// Optional DRC invariants this stage must satisfy.
    /// Default empty — most stages have no invariants.
    fn invariants(&self) -> &[InvariantSpec] {
        &[]
    }

    /// Bounding boxes of regions this stage modified, if known.
    /// Used by incremental DRC to skip re-checking untouched areas.
    fn last_modified_regions(&self) -> Option<&[(f64, f64, f64, f64)]> {
        None
    }

    /// Artifacts this stage promises to produce.
    /// Used by the artifact-contract checker (bottleneck_report.py).
    fn declared_writes(&self) -> &[DeclaredArtifact] {
        &[]
    }

    /// Artifacts this stage requires from prior stages.
    fn declared_reads(&self) -> &[DeclaredArtifact] {
        &[]
    }

    /// Whether this stage runs in the current pipeline configuration.
    /// When `false`, the runner skips the stage AND its contract obligations.
    fn is_active(&self) -> bool {
        true
    }

    /// Execute the stage and return the new state.
    ///
    /// # Errors
    ///
    /// Returns `Err(StageError)` if the stage cannot complete — a hard
    /// failure that halts the pipeline unless the runner is configured to
    /// continue-on-error.
    fn run(&self, state: S) -> Result<S, StageError>;
}

// wasm32 tier (`--no-default-features`): `BoardState` requires pyo3's
// `Py<PyAny>` fields and is therefore not compiled, so `Stage` has no
// default type parameter in this configuration -- every implementor must
// specify `S` explicitly, exactly like the `#[cfg(test)] AddStage: Stage<u32>`
// unit test below already does. The trait body is otherwise identical to the
// `python`-feature definition above (kept as a second definition rather than
// a shared macro so the two stay trivially diffable).
#[cfg(not(feature = "python"))]
/// A single pipeline stage that transforms a typed state.
///
/// The migration endpoint for the Python `Stage(ABC).run(BoardState) ->
/// BoardState` pattern. Every deterministic stage and router_v6 check
/// becomes a Rust `Stage` implementation over time; `PipelineRunner`
/// sequences `Box<dyn Stage<S>>` instances.
pub trait Stage<S> {
    /// Human-readable stage name (used in reports/traces).
    fn name(&self) -> Cow<'static, str>;

    /// Optional DRC invariants this stage must satisfy.
    /// Default empty — most stages have no invariants.
    fn invariants(&self) -> &[InvariantSpec] {
        &[]
    }

    /// Bounding boxes of regions this stage modified, if known.
    /// Used by incremental DRC to skip re-checking untouched areas.
    fn last_modified_regions(&self) -> Option<&[(f64, f64, f64, f64)]> {
        None
    }

    /// Artifacts this stage promises to produce.
    /// Used by the artifact-contract checker (bottleneck_report.py).
    fn declared_writes(&self) -> &[DeclaredArtifact] {
        &[]
    }

    /// Artifacts this stage requires from prior stages.
    fn declared_reads(&self) -> &[DeclaredArtifact] {
        &[]
    }

    /// Whether this stage runs in the current pipeline configuration.
    /// When `false`, the runner skips the stage AND its contract obligations.
    fn is_active(&self) -> bool {
        true
    }

    /// Execute the stage and return the new state.
    ///
    /// # Errors
    ///
    /// Returns `Err(StageError)` if the stage cannot complete — a hard
    /// failure that halts the pipeline unless the runner is configured to
    /// continue-on-error.
    fn run(&self, state: S) -> Result<S, StageError>;
}

/// A named pipeline invariant (DRC fence contract).
///
/// Mirror of Python `validation.drc_fence.InvariantSpec`.
#[derive(Debug, Clone)]
pub struct InvariantSpec {
    pub name: String,
    pub description: String,
    pub severity: InvariantSeverity,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InvariantSeverity {
    Error,
    Warning,
}

/// A contract artifact: something a stage produces or consumes.
///
/// Mirror of Python `pipeline.bottleneck_report.DeclaredArtifact`.
#[derive(Debug, Clone)]
pub struct DeclaredArtifact {
    pub name: String,
    pub artifact_type: String,
}

/// A stage-level error.
///
/// Python `Stage.run()` raises exceptions; Rust surfaces them as
/// `Err(StageError)` so the `PipelineRunner` can collect multiple errors
/// into a report.
#[derive(Debug, Clone, PartialEq)]
pub struct StageError {
    pub stage_name: String,
    pub message: String,
    pub kind: StageErrorKind,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StageErrorKind {
    /// A recoverable warning — runner may continue.
    Warning,
    /// A hard failure — runner halts by default.
    Fatal,
    /// The stage detected an infeasible constraint set.
    Infeasible,
}

impl StageError {
    pub fn new(
        stage_name: impl Into<String>,
        message: impl Into<String>,
        kind: StageErrorKind,
    ) -> Self {
        Self {
            stage_name: stage_name.into(),
            message: message.into(),
            kind,
        }
    }
}

#[cfg(feature = "python")]
/// A Python error raised inside a stage body becomes a `Fatal` `StageError`
/// (the `stage_name` is filled in by the stage's own wrapper when the run()
/// result is observed; the FFI path only reads `message`). This lets stage
/// bodies use `?` on `PyResult` values directly while keeping the raise
/// DECISION (the `Infeasible` kind) explicit.
impl From<pyo3::PyErr> for StageError {
    fn from(e: pyo3::PyErr) -> Self {
        StageError::new("", e.to_string(), StageErrorKind::Fatal)
    }
}

impl fmt::Display for StageError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {:?}: {}", self.stage_name, self.kind, self.message)
    }
}

impl std::error::Error for StageError {}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    /// A trivial stage over `u32` used to pin the trait's shape.
    struct AddStage {
        name: &'static str,
        delta: u32,
        active: bool,
    }

    impl Stage<u32> for AddStage {
        fn name(&self) -> Cow<'static, str> {
            Cow::Borrowed(self.name)
        }
        fn is_active(&self) -> bool {
            self.active
        }
        fn run(&self, state: u32) -> Result<u32, StageError> {
            Ok(state + self.delta)
        }
    }

    #[cfg_attr(test, test)]
    fn stage_run_transforms_state() {
        let stage = AddStage {
            name: "add_one",
            delta: 1,
            active: true,
        };
        assert_eq!(stage.run(41), Ok(42));
        assert_eq!(stage.name(), Cow::Borrowed("add_one"));
        assert!(stage.is_active());
    }

    #[cfg_attr(test, test)]
    fn stage_defaults_are_empty() {
        let stage = AddStage {
            name: "minimal",
            delta: 0,
            active: true,
        };
        assert!(stage.invariants().is_empty());
        assert!(stage.last_modified_regions().is_none());
        assert!(stage.declared_writes().is_empty());
        assert!(stage.declared_reads().is_empty());
    }

    #[cfg_attr(test, test)]
    fn stage_error_roundtrip_and_display() {
        let err = StageError::new("convergence_check", "boom", StageErrorKind::Fatal);
        assert_eq!(err.stage_name, "convergence_check");
        assert_eq!(err.kind, StageErrorKind::Fatal);
        let text = err.to_string();
        assert!(text.contains("convergence_check"));
        assert!(text.contains("boom"));
    }

    #[cfg_attr(test, test)]
    fn stage_error_kind_semantics() {
        assert_ne!(StageErrorKind::Warning, StageErrorKind::Fatal);
        assert_ne!(StageErrorKind::Infeasible, StageErrorKind::Warning);
        // Reflexivity: a `StageErrorKind` equals a separately-constructed
        // value of the same variant. Bound through a variable (rather than
        // repeating `StageErrorKind::Fatal` literally on both sides) so this
        // reads as two independent values to both the reader and
        // `clippy::eq_op`, which otherwise flags identical-looking operands
        // as a likely copy-paste mistake.
        let fatal = StageErrorKind::Fatal;
        assert_eq!(fatal, StageErrorKind::Fatal);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("stage::tests::stage_run_transforms_state", stage_run_transforms_state),
        ("stage::tests::stage_defaults_are_empty", stage_defaults_are_empty),
        ("stage::tests::stage_error_roundtrip_and_display", stage_error_roundtrip_and_display),
        ("stage::tests::stage_error_kind_semantics", stage_error_kind_semantics),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

//! The `PipelineRunner<S>` sequencing loop — pyo3-free.
//!
//! Faithful copy of `temper-orchestration/src/pipeline.rs`'s runner/report/
//! observer surface, including the `ClockPoint` wasm32 degradation (the
//! `std::time::Instant::now()` panic on `wasm32-unknown-unknown`). A real
//! extraction MOVES this file into the core crate.

use crate::stage::{Stage, StageError, StageErrorKind};

/// A wall-clock instant for stage-timing instrumentation, degrading to a
/// constant zero on a target with no clock (`wasm32-unknown-unknown`).
#[cfg(not(target_arch = "wasm32"))]
#[derive(Clone, Copy)]
struct ClockPoint(std::time::Instant);

#[cfg(not(target_arch = "wasm32"))]
impl ClockPoint {
    fn now() -> Self {
        Self(std::time::Instant::now())
    }

    fn elapsed_ms(&self) -> f64 {
        self.0.elapsed().as_secs_f64() * 1000.0
    }
}

#[cfg(target_arch = "wasm32")]
#[derive(Clone, Copy)]
struct ClockPoint;

#[cfg(target_arch = "wasm32")]
impl ClockPoint {
    fn now() -> Self {
        Self
    }

    fn elapsed_ms(&self) -> f64 {
        0.0
    }
}

/// Observability hook called between stages.
pub trait PipelineObserver<S> {
    fn on_stage_start(&mut self, stage_name: &str, state: &S);
    fn on_stage_complete(&mut self, stage_name: &str, result: &Result<S, StageError>, elapsed_ms: f64);
}

/// Result of a full pipeline run.
#[derive(Debug)]
pub struct PipelineReport {
    pub stage_reports: Vec<StageReport>,
    pub total_elapsed_ms: f64,
    pub halted_early: bool,
}

#[derive(Debug)]
pub struct StageReport {
    pub name: String,
    pub elapsed_ms: f64,
    pub outcome: StageOutcome,
}

#[derive(Debug)]
pub enum StageOutcome {
    Completed,
    Skipped,
    Failed(StageError),
}

/// Configuration for pipeline execution.
#[derive(Debug, Clone)]
pub struct PipelineConfig {
    pub halt_on_error: bool,
}

impl Default for PipelineConfig {
    fn default() -> Self {
        Self { halt_on_error: true }
    }
}

/// Sequences stages and collects reports.
///
/// The concrete `S` is `CoreBoardState` in the pure-Rust pipeline (see
/// `board_state.rs`); the runner is generic so it can be tested with `u32`.
pub struct PipelineRunner<S> {
    stages: Vec<Box<dyn Stage<S>>>,
    observers: Vec<Box<dyn PipelineObserver<S>>>,
    config: PipelineConfig,
}

impl<S: Clone> PipelineRunner<S> {
    pub fn new(config: PipelineConfig) -> Self {
        Self {
            stages: Vec::new(),
            observers: Vec::new(),
            config,
        }
    }

    pub fn add_stage(&mut self, stage: Box<dyn Stage<S>>) {
        self.stages.push(stage);
    }

    pub fn add_observer(&mut self, observer: Box<dyn PipelineObserver<S>>) {
        self.observers.push(observer);
    }

    /// Run all stages in declaration order.
    pub fn run(&mut self, initial_state: S) -> (S, PipelineReport) {
        let mut state = initial_state;
        let mut reports = Vec::new();
        let start = ClockPoint::now();

        for stage in &self.stages {
            let name = stage.name().into_owned();
            if !stage.is_active() {
                reports.push(StageReport {
                    name,
                    elapsed_ms: 0.0,
                    outcome: StageOutcome::Skipped,
                });
                continue;
            }

            for obs in &mut self.observers {
                obs.on_stage_start(&name, &state);
            }

            let stage_start = ClockPoint::now();
            let result = stage.run(state.clone());
            let elapsed = stage_start.elapsed_ms();

            for obs in &mut self.observers {
                obs.on_stage_complete(&name, &result, elapsed);
            }

            match result {
                Ok(new_state) => {
                    reports.push(StageReport {
                        name,
                        elapsed_ms: elapsed,
                        outcome: StageOutcome::Completed,
                    });
                    state = new_state;
                }
                Err(e) => {
                    let is_fatal = matches!(
                        e.kind,
                        StageErrorKind::Fatal | StageErrorKind::Infeasible
                    );
                    reports.push(StageReport {
                        name,
                        elapsed_ms: elapsed,
                        outcome: StageOutcome::Failed(e.clone()),
                    });
                    if self.config.halt_on_error && is_fatal {
                        return (
                            state,
                            PipelineReport {
                                stage_reports: reports,
                                total_elapsed_ms: start.elapsed_ms(),
                                halted_early: true,
                            },
                        );
                    }
                }
            }
        }

        (
            state,
            PipelineReport {
                stage_reports: reports,
                total_elapsed_ms: start.elapsed_ms(),
                halted_early: false,
            },
        )
    }
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;
    use crate::stage::StageErrorKind;

    struct AddStage {
        name: &'static str,
        delta: u32,
        active: bool,
        failure: Option<StageErrorKind>,
    }

    impl AddStage {
        fn new(name: &'static str, delta: u32) -> Self {
            Self { name, delta, active: true, failure: None }
        }
        fn failing(name: &'static str, kind: StageErrorKind) -> Self {
            Self { name, delta: 0, active: true, failure: Some(kind) }
        }
    }

    impl Stage<u32> for AddStage {
        fn name(&self) -> std::borrow::Cow<'static, str> {
            std::borrow::Cow::Borrowed(self.name)
        }
        fn is_active(&self) -> bool {
            self.active
        }
        fn run(&self, state: u32) -> Result<u32, StageError> {
            match &self.failure {
                Some(kind) => Err(StageError::new(self.name, "intentional", kind.clone())),
                None => Ok(state + self.delta),
            }
        }
    }

    fn runner_with(stages: Vec<AddStage>) -> PipelineRunner<u32> {
        let mut runner = PipelineRunner::new(PipelineConfig::default());
        for s in stages {
            runner.add_stage(Box::new(s));
        }
        runner
    }

    #[cfg_attr(test, test)]
    fn run_sequences_stages_in_order() {
        let mut runner = runner_with(vec![
            AddStage::new("a", 1),
            AddStage::new("b", 2),
            AddStage::new("c", 3),
        ]);
        let (state, report) = runner.run(0);
        assert_eq!(state, 6);
        assert!(!report.halted_early);
        assert_eq!(report.stage_reports.len(), 3);
        let names: Vec<&str> = report
            .stage_reports
            .iter()
            .map(|r| r.name.as_str())
            .collect();
        assert_eq!(names, vec!["a", "b", "c"]);
    }

    #[cfg_attr(test, test)]
    fn fatal_error_halts_and_preserves_last_successful_state() {
        let mut runner = runner_with(vec![
            AddStage::new("a", 5),
            AddStage::failing("fatal", StageErrorKind::Fatal),
            AddStage::new("never_runs", 1),
        ]);
        let (state, report) = runner.run(0);
        assert_eq!(state, 5);
        assert!(report.halted_early);
        assert_eq!(report.stage_reports.len(), 2);
        assert!(matches!(
            report.stage_reports[1].outcome,
            StageOutcome::Failed(_)
        ));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("pipeline::tests::run_sequences_stages_in_order", run_sequences_stages_in_order),
        ("pipeline::tests::fatal_error_halts_and_preserves_last_successful_state", fatal_error_halts_and_preserves_last_successful_state),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

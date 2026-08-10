// U0 scaffolding (`dead_code` note): same rationale as `stage.rs` — the
// runner's first production consumer is Phase C's pipeline wiring; until
// then the lib target has no caller for the runner/report/observer surface
// (the unit tests below are the only exercisers).
#![allow(dead_code)]

// The `PipelineRunner` — sequences `Box<dyn Stage<S>>` instances in
// declaration order, respecting `is_active`, collecting stage errors into a
// report, and calling observer hooks between stages (Rust Orchestration
// Engine plan 2026-08-09-001, U0 scaffolding).
//
// Mirror of the Python `Pipeline.run()` sequencing loop; the runner itself
// is pure Rust (no pyo3, no unmigrated Python type — `S` is a generic
// parameter, `BoardState` in production).
//
// Error model: `StageErrorKind::Fatal` / `Infeasible` halt the pipeline
// when `halt_on_error` is set (the default); `Warning` and non-fatal
// failures are collected into the report and the run continues. On a halt,
// the state is left at the last-successful snapshot.

use crate::stage::{Stage, StageError, StageErrorKind};

/// Observability hook called between stages.
///
/// Mirror of Python `pipeline.metrics_observer.MetricsObserver`
/// and `pipeline.visualization.ProgressCallback`.
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
    /// If true, a `Fatal` or `Infeasible` error halts the pipeline.
    /// If false, errors are collected and the pipeline continues.
    pub halt_on_error: bool,
}

impl Default for PipelineConfig {
    fn default() -> Self {
        Self { halt_on_error: true }
    }
}

/// Sequences stages and collects reports.
///
/// The runner stores `Box<dyn Stage<S>>` trait objects. The concrete `S` is
/// `BoardState` for production use, but the runner can be tested with a
/// trivial `S = u32` in unit tests.
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
    ///
    /// Returns the final state and a report even on error (the
    /// last-successful state is preserved).
    pub fn run(&mut self, initial_state: S) -> (S, PipelineReport) {
        let mut state = initial_state;
        let mut reports = Vec::new();
        let start = std::time::Instant::now();

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

            let stage_start = std::time::Instant::now();
            let result = stage.run(state.clone());
            let elapsed = stage_start.elapsed().as_secs_f64() * 1000.0;

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
                                total_elapsed_ms: start.elapsed().as_secs_f64() * 1000.0,
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
                total_elapsed_ms: start.elapsed().as_secs_f64() * 1000.0,
                halted_early: false,
            },
        )
    }
}

#[cfg(test)]
mod tests {
    use std::sync::{Arc, Mutex};

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
            Self {
                name,
                delta,
                active: true,
                failure: None,
            }
        }
        fn failing(name: &'static str, kind: StageErrorKind) -> Self {
            Self {
                name,
                delta: 0,
                active: true,
                failure: Some(kind),
            }
        }
        fn inactive(name: &'static str, delta: u32) -> Self {
            Self {
                name,
                delta,
                active: false,
                failure: None,
            }
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

    struct RecordingObserver {
        log: Arc<Mutex<Vec<String>>>,
    }

    impl RecordingObserver {
        fn new(log: Arc<Mutex<Vec<String>>>) -> Self {
            Self { log }
        }
    }

    impl PipelineObserver<u32> for RecordingObserver {
        fn on_stage_start(&mut self, stage_name: &str, _state: &u32) {
            match self.log.lock() {
                Ok(mut g) => g.push(format!("start:{stage_name}")),
                Err(p) => panic!("observer log poisoned: {p}"),
            }
        }
        fn on_stage_complete(
            &mut self,
            stage_name: &str,
            result: &Result<u32, StageError>,
            _elapsed_ms: f64,
        ) {
            let ok = result.is_ok();
            match self.log.lock() {
                Ok(mut g) => g.push(format!("complete:{stage_name}:{ok}")),
                Err(p) => panic!("observer log poisoned: {p}"),
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

    #[test]
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
        for r in &report.stage_reports {
            assert!(matches!(r.outcome, StageOutcome::Completed));
        }
    }

    #[test]
    fn run_skips_inactive_stages() {
        let mut runner = runner_with(vec![
            AddStage::new("a", 1),
            AddStage::inactive("skipped", 100),
            AddStage::new("b", 1),
        ]);
        let (state, report) = runner.run(0);
        assert_eq!(state, 2);
        assert!(!report.halted_early);
        assert_eq!(report.stage_reports.len(), 3);
        assert!(matches!(
            report.stage_reports[1].outcome,
            StageOutcome::Skipped
        ));
        assert_eq!(report.stage_reports[1].elapsed_ms, 0.0);
    }

    #[test]
    fn fatal_error_halts_and_preserves_last_successful_state() {
        let mut runner = runner_with(vec![
            AddStage::new("a", 5),
            AddStage::failing("fatal", StageErrorKind::Fatal),
            AddStage::new("never_runs", 1),
        ]);
        let (state, report) = runner.run(0);
        assert_eq!(state, 5); // last-successful snapshot, not 6
        assert!(report.halted_early);
        assert_eq!(report.stage_reports.len(), 2);
        assert!(matches!(
            report.stage_reports[1].outcome,
            StageOutcome::Failed(_)
        ));
    }

    #[test]
    fn infeasible_halts_by_default() {
        let mut runner = runner_with(vec![
            AddStage::failing("infeasible", StageErrorKind::Infeasible),
            AddStage::new("b", 1),
        ]);
        let (_state, report) = runner.run(0);
        assert!(report.halted_early);
        assert_eq!(report.stage_reports.len(), 1);
    }

    #[test]
    fn continue_on_error_collects_and_continues() {
        let config = PipelineConfig {
            halt_on_error: false,
        };
        let mut runner = PipelineRunner::new(config);
        runner.add_stage(Box::new(AddStage::new("a", 1)));
        runner.add_stage(Box::new(AddStage::failing(
            "fatal",
            StageErrorKind::Fatal,
        )));
        runner.add_stage(Box::new(AddStage::new("b", 10)));
        let (state, report) = runner.run(0);
        assert_eq!(state, 11);
        assert!(!report.halted_early);
        assert_eq!(report.stage_reports.len(), 3);
        assert!(matches!(
            report.stage_reports[1].outcome,
            StageOutcome::Failed(_)
        ));
        assert!(matches!(
            report.stage_reports[2].outcome,
            StageOutcome::Completed
        ));
    }

    #[test]
    fn warning_does_not_halt_even_with_halt_on_error() {
        let mut runner = runner_with(vec![
            AddStage::failing("warn", StageErrorKind::Warning),
            AddStage::new("b", 1),
        ]);
        let (state, report) = runner.run(0);
        assert_eq!(state, 1);
        assert!(!report.halted_early);
        assert_eq!(report.stage_reports.len(), 2);
    }

    #[test]
    fn observers_are_called_between_stages() {
        let log = Arc::new(Mutex::new(Vec::new()));
        let mut runner = runner_with(vec![
            AddStage::new("a", 1),
            AddStage::failing("fatal", StageErrorKind::Fatal),
        ]);
        runner.add_observer(Box::new(RecordingObserver::new(log.clone())));
        let (_state, _report) = runner.run(0);
        let entries = match log.lock() {
            Ok(g) => g.clone(),
            Err(p) => panic!("observer log poisoned: {p}"),
        };
        assert_eq!(
            entries,
            vec![
                "start:a",
                "complete:a:true",
                "start:fatal",
                "complete:fatal:false",
            ]
        );
    }

    #[test]
    fn empty_runner_returns_initial_state() {
        let mut runner = PipelineRunner::new(PipelineConfig::default());
        let (state, report) = runner.run(42u32);
        assert_eq!(state, 42);
        assert!(report.stage_reports.is_empty());
        assert!(!report.halted_early);
    }

    #[test]
    fn stage_count_observable() {
        // A stage that is a `&dyn`-style object can still be counted by the
        // runner via `is_active` only; this pins that `add_stage` grows the
        // stage list.
        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(AddStage::new("a", 1)));
        runner.add_stage(Box::new(AddStage::new("b", 1)));
        let (_state, report) = runner.run(0);
        assert_eq!(report.stage_reports.len(), 2);
    }

    #[test]
    fn state_type_is_generic_not_boardstate() {
        // Cross-check: `S` can be any Clone type, not just BoardState or u32.
        struct LenStage {
            push: String,
        }
        impl Stage<Vec<String>> for LenStage {
            fn name(&self) -> std::borrow::Cow<'static, str> {
                std::borrow::Cow::Borrowed("push")
            }
            fn run(&self, mut state: Vec<String>) -> Result<Vec<String>, StageError> {
                state.push(self.push.clone());
                Ok(state)
            }
        }
        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(LenStage {
            push: "x".into(),
        }));
        runner.add_stage(Box::new(LenStage {
            push: "y".into(),
        }));
        let (state, report) = runner.run(vec!["seed".into()]);
        assert_eq!(state, vec!["seed", "x", "y"]);
        assert_eq!(report.stage_reports.len(), 2);
        assert!(matches!(
            report.stage_reports[0].outcome,
            StageOutcome::Completed
        ));
    }
}

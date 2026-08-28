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

/// A wall-clock instant for stage-timing instrumentation, degrading to a
/// constant zero on a target with no clock.
///
/// `std::time::Instant::now()` panics on `wasm32-unknown-unknown` ("time not
/// implemented on this platform") -- there is no host clock to read. This
/// runner is plain generic Rust (`S` is a type parameter; `BoardState` is
/// only the production instantiation), exercised directly by this module's
/// own `#[cfg(test)]` unit tests rather than gated behind `python`, so the
/// panic is not avoidable by cfg-ing the caller away -- unlike
/// `temper-geometry`'s `bottleneck_geometry` deadline check (see its module
/// doc), which reads the clock only when a caller opts in, `run()` always
/// times every stage. Timing degrades to a constant `0.0` ms on `wasm32`
/// instead: honest (0.0 is not a plausible wall-clock reading and is
/// documented here) rather than a trap. Every other target is unchanged.
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
///
/// Mirror of Python `pipeline.metrics_observer.MetricsObserver`
/// and `pipeline.visualization.ProgressCallback`.
pub trait PipelineObserver<S> {
    fn on_stage_start(&mut self, stage_name: &str, state: &S);
    fn on_stage_complete(
        &mut self,
        stage_name: &str,
        result: &Result<S, StageError>,
        elapsed_ms: f64,
    );
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
        Self {
            halt_on_error: true,
        }
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
                    let is_fatal =
                        matches!(e.kind, StageErrorKind::Fatal | StageErrorKind::Infeasible);
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
        for r in &report.stage_reports {
            assert!(matches!(r.outcome, StageOutcome::Completed));
        }
    }

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
    fn infeasible_halts_by_default() {
        let mut runner = runner_with(vec![
            AddStage::failing("infeasible", StageErrorKind::Infeasible),
            AddStage::new("b", 1),
        ]);
        let (_state, report) = runner.run(0);
        assert!(report.halted_early);
        assert_eq!(report.stage_reports.len(), 1);
    }

    #[cfg_attr(test, test)]
    fn continue_on_error_collects_and_continues() {
        let config = PipelineConfig {
            halt_on_error: false,
        };
        let mut runner = PipelineRunner::new(config);
        runner.add_stage(Box::new(AddStage::new("a", 1)));
        runner.add_stage(Box::new(AddStage::failing("fatal", StageErrorKind::Fatal)));
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

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
    fn empty_runner_returns_initial_state() {
        let mut runner = PipelineRunner::new(PipelineConfig::default());
        let (state, report) = runner.run(42u32);
        assert_eq!(state, 42);
        assert!(report.stage_reports.is_empty());
        assert!(!report.halted_early);
    }

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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
        runner.add_stage(Box::new(LenStage { push: "x".into() }));
        runner.add_stage(Box::new(LenStage { push: "y".into() }));
        let (state, report) = runner.run(vec!["seed".into()]);
        assert_eq!(state, vec!["seed", "x", "y"]);
        assert_eq!(report.stage_reports.len(), 2);
        assert!(matches!(
            report.stage_reports[0].outcome,
            StageOutcome::Completed
        ));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("pipeline::tests::run_sequences_stages_in_order", run_sequences_stages_in_order),
        ("pipeline::tests::run_skips_inactive_stages", run_skips_inactive_stages),
        ("pipeline::tests::fatal_error_halts_and_preserves_last_successful_state", fatal_error_halts_and_preserves_last_successful_state),
        ("pipeline::tests::infeasible_halts_by_default", infeasible_halts_by_default),
        ("pipeline::tests::continue_on_error_collects_and_continues", continue_on_error_collects_and_continues),
        ("pipeline::tests::warning_does_not_halt_even_with_halt_on_error", warning_does_not_halt_even_with_halt_on_error),
        ("pipeline::tests::observers_are_called_between_stages", observers_are_called_between_stages),
        ("pipeline::tests::empty_runner_returns_initial_state", empty_runner_returns_initial_state),
        ("pipeline::tests::stage_count_observable", stage_count_observable),
        ("pipeline::tests::state_type_is_generic_not_boardstate", state_type_is_generic_not_boardstate),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

// `proptest` is a dev-dependency (present under `cargo test`, absent from the
// ordinary non-test build `wasm_test_registry.rs` compiles into), so these
// runner properties live in their own `#[cfg(test)]` sibling module -- exactly
// the split `timing.rs`/`copper_length.rs`/`clearance.rs` already use -- so
// `gen_wasm_test_registry.py`'s per-module `proptest-dev-dependency` exclusion
// only drops these properties instead of the whole module's otherwise-pure
// unit tests.
//
// proptest: `PipelineRunner<u32>` -- the U-E sequencing loop's pure core (the
// `PythonStageShim` drives the SAME runner). These properties pin the loop's
// left-fold / halt / skip semantics over random stage lists: the loop must be
// a pure left fold in DECLARATION order (never a HashMap order), a fatal
// stage must halt the run and preserve the prefix's effects exactly, and an
// inactive stage must run nothing.
#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod proptests {
    use super::*;
    use proptest::prelude::*;
    use std::sync::{Arc, Mutex};

    /// A stage that adds `delta` to a `u32` state and records its name in a
    /// shared log (so "did this stage run?" is observable). `fatal` injects a
    /// `Fatal` error BEFORE the state is updated -- the run-loop's raise-now
    /// semantics (a failing stage must not update the state).
    struct LogStage {
        name: String,
        delta: u32,
        active: bool,
        fatal: bool,
        log: Arc<Mutex<Vec<String>>>,
    }

    impl LogStage {
        fn ok(name: &str, delta: u32, log: Arc<Mutex<Vec<String>>>) -> Self {
            Self {
                name: name.to_string(),
                delta,
                active: true,
                fatal: false,
                log,
            }
        }
        fn fatal(name: &str, log: Arc<Mutex<Vec<String>>>) -> Self {
            Self {
                name: name.to_string(),
                delta: 0,
                active: true,
                fatal: true,
                log,
            }
        }
        fn inactive(name: &str, delta: u32, log: Arc<Mutex<Vec<String>>>) -> Self {
            Self {
                name: name.to_string(),
                delta,
                active: false,
                fatal: false,
                log,
            }
        }
    }

    impl Stage<u32> for LogStage {
        fn name(&self) -> std::borrow::Cow<'static, str> {
            std::borrow::Cow::Owned(self.name.clone())
        }
        fn is_active(&self) -> bool {
            self.active
        }
        fn run(&self, state: u32) -> Result<u32, StageError> {
            self.log.lock().unwrap().push(self.name.clone());
            if self.fatal {
                Err(StageError::new(&self.name, "boom", StageErrorKind::Fatal))
            } else {
                Ok(state + self.delta)
            }
        }
    }

    fn runner_of(stages: Vec<LogStage>) -> PipelineRunner<u32> {
        let mut r = PipelineRunner::new(PipelineConfig::default());
        for s in stages {
            r.add_stage(Box::new(s));
        }
        r
    }

    proptest! {
        /// P1. The runner is a pure LEFT FOLD in declaration order: for every
        /// split of the stage list, run(all) == run(suffix, run(prefix, s0)).
        #[test]
        fn runner_is_a_pure_left_fold(
            prefix in prop::collection::vec(0u32..10, 0..6),
            suffix in prop::collection::vec(0u32..10, 0..6),
        ) {
            let all_log = Arc::new(Mutex::new(Vec::new()));
            let prefix_len = prefix.len();
            let total: Vec<u32> = prefix.iter().chain(suffix.iter()).cloned().collect();

            let mut all = PipelineRunner::new(PipelineConfig::default());
            for (i, d) in total.iter().enumerate() {
                all.add_stage(Box::new(LogStage::ok(&format!("s{i}"), *d, all_log.clone())));
            }
            let mut pref = PipelineRunner::new(PipelineConfig::default());
            for (i, d) in prefix.iter().enumerate() {
                pref.add_stage(Box::new(LogStage::ok(
                    &format!("s{i}"),
                    *d,
                    Arc::new(Mutex::new(Vec::new())),
                )));
            }
            let mut suff = PipelineRunner::new(PipelineConfig::default());
            for (i, d) in suffix.iter().enumerate() {
                suff.add_stage(Box::new(LogStage::ok(
                    &format!("s{}", prefix_len + i),
                    *d,
                    Arc::new(Mutex::new(Vec::new())),
                )));
            }

            let (direct, direct_rep) = all.run(0);
            let (mid, _) = pref.run(0);
            let (composed, _) = suff.run(mid);

            prop_assert!(!direct_rep.halted_early);
            prop_assert_eq!(direct, total.iter().sum::<u32>());
            prop_assert_eq!(direct, composed, "run(all) != run(suffix, run(prefix))");
            // The `all` runner ran every stage exactly once, in declaration
            // order.
            let expected_log: Vec<String> =
                (0..total.len()).map(|i| format!("s{i}")).collect();
            prop_assert_eq!(all_log.lock().unwrap().clone(), expected_log);
        }

        /// P2. The runner is deterministic: two identical runners over the
        /// same stage list produce the same state and the same report shape.
        #[test]
        fn runner_is_deterministic(deltas in prop::collection::vec(0u32..10, 0..8)) {
            let log1 = Arc::new(Mutex::new(Vec::new()));
            let log2 = Arc::new(Mutex::new(Vec::new()));
            let stages1: Vec<LogStage> = deltas.iter().enumerate()
                .map(|(i, d)| LogStage::ok(&format!("s{i}"), *d, log1.clone())).collect();
            let stages2: Vec<LogStage> = deltas.iter().enumerate()
                .map(|(i, d)| LogStage::ok(&format!("s{i}"), *d, log2.clone())).collect();

            let (s1, rep1) = runner_of(stages1).run(7);
            let (s2, rep2) = runner_of(stages2).run(7);

            prop_assert_eq!(s1, s2);
            prop_assert_eq!(rep1.halted_early, rep2.halted_early);
            let names1: Vec<String> = rep1.stage_reports.iter().map(|r| r.name.clone()).collect();
            let names2: Vec<String> = rep2.stage_reports.iter().map(|r| r.name.clone()).collect();
            prop_assert_eq!(names1, names2);
            prop_assert_eq!(log1.lock().unwrap().clone(), log2.lock().unwrap().clone());
        }

        /// P3. Exactly one stage (at a random position) is fatal. The run
        /// halts AT that stage: the final state is the initial state plus the
        /// deltas of the stages BEFORE the fatal one only; the fatal stage and
        /// every stage after it never contribute to the state; the report has
        /// exactly fail_index+1 entries, the last of which is Failed.
        #[test]
        fn single_fatal_halts_with_prefix_state(
            (deltas, fail_index) in (1usize..8).prop_flat_map(|n| (
                prop::collection::vec(0u32..10, n),
                0..n,
            )),
        ) {
            let log = Arc::new(Mutex::new(Vec::new()));
            let stages: Vec<LogStage> = deltas.iter().enumerate().map(|(i, d)| {
                if i == fail_index {
                    LogStage::fatal(&format!("s{i}"), log.clone())
                } else {
                    LogStage::ok(&format!("s{i}"), *d, log.clone())
                }
            }).collect();

            let (state, report) = runner_of(stages).run(0);

            let expected_sum: u32 = deltas[..fail_index].iter().sum();
            prop_assert_eq!(state, expected_sum,
                "state must be the prefix sum BEFORE the fatal stage");
            prop_assert!(report.halted_early);
            prop_assert_eq!(report.stage_reports.len(), fail_index + 1,
                "the run must halt at the fatal stage (index {})", fail_index);
            prop_assert!(matches!(
                report.stage_reports.last().unwrap().outcome,
                StageOutcome::Failed(_)
            ));
            // The log records stages up to AND INCLUDING the fatal one, and
            // nothing after it.
            let expected_log: Vec<String> =
                (0..=fail_index).map(|i| format!("s{i}")).collect();
            prop_assert_eq!(log.lock().unwrap().clone(), expected_log);
        }

        /// P4. Inactive stages are skipped in place: they run nothing (absent
        /// from the log), change no state, and are reported as Skipped at
        /// their declaration position (the report preserves order).
        #[test]
        fn inactive_stages_are_skipped(
            (deltas, active_mask) in (1usize..8).prop_flat_map(|n| (
                prop::collection::vec(0u32..10, n),
                prop::collection::vec(any::<bool>(), n),
            )),
        ) {
            let log = Arc::new(Mutex::new(Vec::new()));
            let stages: Vec<LogStage> = deltas.iter().enumerate().map(|(i, d)| {
                if active_mask[i] {
                    LogStage::ok(&format!("s{i}"), *d, log.clone())
                } else {
                    LogStage::inactive(&format!("s{i}"), *d, log.clone())
                }
            }).collect();

            let (state, report) = runner_of(stages).run(0);

            let expected_sum: u32 = deltas.iter().zip(active_mask.iter())
                .filter(|(_, active)| **active)
                .map(|(d, _)| *d)
                .sum();
            prop_assert_eq!(state, expected_sum);
            prop_assert!(!report.halted_early);
            prop_assert_eq!(report.stage_reports.len(), deltas.len());

            let expected_log: Vec<String> = (0..deltas.len()).filter(|i| active_mask[*i])
                .map(|i| format!("s{i}")).collect();
            prop_assert_eq!(log.lock().unwrap().clone(), expected_log);

            for (i, r) in report.stage_reports.iter().enumerate() {
                if active_mask[i] {
                    prop_assert!(matches!(r.outcome, StageOutcome::Completed),
                        "stage s{i} should be Completed");
                } else {
                    prop_assert!(matches!(r.outcome, StageOutcome::Skipped),
                        "stage s{i} should be Skipped");
                }
            }
        }
    }
}

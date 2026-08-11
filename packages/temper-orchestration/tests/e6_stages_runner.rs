// E6 runner test: sequence the Phase E batch E6 pipeline-route stage through
// PipelineRunner<BoardState> (Rust Orchestration Engine plan 2026-08-09-001,
// Phase E E6).
//
// The E6 stage is a READ-ONLY orchestration stage (the E3/E4 pattern): it
// carries a marshalled input payload (the `(routes, tstamp_counter)` pair the
// router_v6/_adapter_convert.py shim builds for the write-routes pyfunction)
// and executes the compute when a payload is present, returning the state
// unchanged. Constructed here with `None` payloads (the embedded test
// interpreter has no venv, so the CPython `str.format` rendering the emission
// core routes through is not the differential's concern here), the stage is a
// guarded identity: `stage_guard` + `Python::attach` + `Ok(state)`. What this
// suite proves is the SEQUENCING and the Stage<BoardState> contract: the
// stage implements the trait, the runner threads the state through, every
// run() returns Ok without panicking, and the final state object is the
// threaded one.

#![allow(clippy::unwrap_used, clippy::expect_used)] // tests-only integration target

use pyo3::prelude::*;

use temper_orchestration::{
    BoardState, PipelineConfig, PipelineRouteStage, PipelineRunner, StageOutcome,
};

fn build_runner() -> (PipelineRunner<BoardState>, Vec<&'static str>) {
    let mut runner = PipelineRunner::new(PipelineConfig::default());
    let mut names = Vec::new();
    runner.add_stage(Box::new(PipelineRouteStage { payload: None }));
    names.push("pipeline_route");
    (runner, names)
}

#[test]
fn e6_stages_sequence_in_declaration_order() {
    Python::initialize();
    Python::attach(|_py| {
        let (mut runner, names) = build_runner();
        let (state, report) = runner.run(BoardState::new());
        assert!(!report.halted_early);
        assert_eq!(report.stage_reports.len(), names.len());
        for (stage_report, expected) in report.stage_reports.iter().zip(names.iter()) {
            assert_eq!(&stage_report.name.as_str(), expected);
            assert!(
                matches!(stage_report.outcome, StageOutcome::Completed),
                "{} did not complete",
                expected
            );
        }
        // The orchestration stage is read-only: an empty BoardState is
        // returned unchanged (all fields still None).
        assert!(state.net_order.is_empty());
        assert!(state.routes.is_none());
        assert!(state.violations.is_none());
    });
}

#[test]
fn e6_stage_names_match_the_pipeline_surface() {
    Python::initialize();
    Python::attach(|_py| {
        let (mut runner, _) = build_runner();
        let (_, report) = runner.run(BoardState::new());
        let actual: Vec<&str> = report
            .stage_reports
            .iter()
            .map(|s| s.name.as_str())
            .collect();
        assert_eq!(actual, vec!["pipeline_route"]);
    });
}

#[test]
fn e6_stages_do_not_panic_on_empty_state() {
    Python::initialize();
    Python::attach(|_py| {
        let (mut runner, _) = build_runner();
        let (state, report) = runner.run(BoardState::new().with_net_order(vec!["a".to_string()]));
        assert!(!report.halted_early);
        assert_eq!(state.net_order, vec!["a"]);
    });
}

#[test]
fn e6_read_only_stage_preserves_net_order() {
    Python::initialize();
    Python::attach(|_py| {
        let (mut runner, _) = build_runner();
        let initial =
            BoardState::new().with_net_order(vec!["NET_A".to_string(), "NET_B".to_string()]);
        let (state, report) = runner.run(initial);
        assert!(!report.halted_early);
        assert_eq!(state.net_order, vec!["NET_A", "NET_B"]);
    });
}

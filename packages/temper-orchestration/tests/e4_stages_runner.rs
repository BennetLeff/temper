// E4 runner test: sequence the Phase E batch E4 channel-operation stages
// through PipelineRunner<BoardState> (Rust Orchestration Engine plan
// 2026-08-09-001, Phase E E4).
//
// The E4 stages are READ-ONLY check stages (the E3 pattern): they carry a
// marshalled input payload (the tuples the router_v6 shims build for the
// pyfunctions) and execute the compute when a payload is present, returning
// the state unchanged. Constructed here with `None` payloads (the embedded
// test interpreter has no venv, so the FFI kernels — temper_geometry's
// channel_path_length / is_near_skeleton / nearest_skeleton_node /
// nearest_terminal_order / edt_width_lookup_batch and the
// temper_placer.router_v6.net_classification call-backs — are
// unreachable), every stage is a guarded identity: `stage_guard` +
// `Python::attach` + `Ok(state)`. What this suite proves is the SEQUENCING
// and the Stage<BoardState> contract: the two stages implement the trait,
// the runner threads the state through in declaration order, every run()
// returns Ok without panicking, and the final state object is the threaded
// one.

#![allow(clippy::unwrap_used, clippy::expect_used)] // tests-only integration target

use pyo3::prelude::*;

use temper_orchestration::{
    BoardState, ChannelMappingStage, ChannelWidthsStage, PipelineConfig, PipelineRunner,
    StageOutcome,
};

const STAGE_NAMES: &[&str] = &["channel_mapping", "channel_widths"];

fn build_runner() -> (PipelineRunner<BoardState>, Vec<&'static str>) {
    let mut runner = PipelineRunner::new(PipelineConfig::default());
    let mut names = Vec::new();
    runner.add_stage(Box::new(ChannelMappingStage { payload: None }));
    names.push("channel_mapping");
    runner.add_stage(Box::new(ChannelWidthsStage { payload: None }));
    names.push("channel_widths");
    (runner, names)
}

#[test]
fn e4_stages_sequence_in_declaration_order() {
    Python::initialize();
    Python::attach(|_py| {
        let (mut runner, names) = build_runner();
        let (state, report) = runner.run(BoardState::new());
        assert!(!report.halted_early);
        assert_eq!(report.stage_reports.len(), STAGE_NAMES.len());
        for (stage_report, expected) in report.stage_reports.iter().zip(names.iter()) {
            assert_eq!(&stage_report.name.as_str(), expected);
            assert!(
                matches!(stage_report.outcome, StageOutcome::Completed),
                "{} did not complete",
                expected
            );
        }
        // The check stages are read-only: an empty BoardState is returned
        // unchanged (all fields still None).
        assert!(state.net_order.is_empty());
        assert!(state.routes.is_none());
        assert!(state.violations.is_none());
    });
}

#[test]
fn e4_stage_names_match_the_pipeline_surface() {
    Python::initialize();
    Python::attach(|_py| {
        let (mut runner, _) = build_runner();
        let (_, report) = runner.run(BoardState::new());
        let actual: Vec<&str> = report
            .stage_reports
            .iter()
            .map(|s| s.name.as_str())
            .collect();
        assert_eq!(actual, STAGE_NAMES);
    });
}

#[test]
fn e4_stages_do_not_panic_on_empty_state() {
    Python::initialize();
    Python::attach(|_py| {
        // The runner's own `run()` would unwind a panicking stage; a panic
        // here fails the test binary. The guarded identity path must hold
        // for every stage with a None payload.
        let (mut runner, _) = build_runner();
        let (state, report) = runner.run(BoardState::new().with_net_order(vec!["a".to_string()]));
        assert!(!report.halted_early);
        assert_eq!(state.net_order, vec!["a"]);
    });
}

#[test]
fn e4_read_only_stages_preserve_net_order() {
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

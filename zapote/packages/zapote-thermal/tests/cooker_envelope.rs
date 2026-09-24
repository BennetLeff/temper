use std::path::Path;
use zapote_thermal::cooker_envelope::{
    aux_loss_nc_discharge, interlock_pins, screen, verify_sources, AirEvidence, Candidate,
    DischargeFault, DischargeVerdict, DownstreamInputs, DownstreamLatch, FanInputs, FanMonitor,
    FanOutputs, FanState, HeatDestination, HeatTerm, Identity, ModelBoundary, Reason,
    ResistanceCase, Scope, Support, ThermalInput, VbFeedPath, Verdict,
};

fn sink_heat(watts: f64) -> Option<HeatTerm> {
    Some(HeatTerm {
        watts,
        destination: HeatDestination::SharedSink,
    })
}

fn baseline(candidate: Candidate) -> ThermalInput {
    ThermalInput {
        identity: Identity::for_candidate(candidate),
        scope: Scope::RetainedCandidate,
        inlet_c: 40.0,
        bridge: sink_heat(40.0),
        other_pfc: match candidate {
            Candidate::Gbu395 => None,
            Candidate::Gbu392 | Candidate::Gbj392 => sink_heat(65.0),
        },
        fan: (candidate == Candidate::Gbj392).then_some(HeatTerm {
            watts: 5.6,
            destination: HeatDestination::SharedSink,
        }),
        auxiliary: None,
        inverter: None,
        air: AirEvidence::CatalogPoint {
            flow_cfm: if candidate == Candidate::Gbu395 {
                43.4
            } else {
                100.0
            },
            fan_voltage_v: 12.0,
        },
        support: Support::ChassisSupported,
    }
}

fn good_fan() -> FanInputs {
    FanInputs {
        cooling_rail_good: true,
        sensing_rail_good: true,
        sensor_valid: true,
        all_tach_valid: true,
        airflow_or_thermal_valid: true,
        start_deadline_expired: false,
        reset_edge: false,
    }
}

fn gate_inputs() -> DownstreamInputs {
    DownstreamInputs {
        interlock_powered: true,
        heatsink_fault_wire_intact: true,
        sensor_live_wire_intact: true,
        other_interlock_faults_clear: true,
        fresh_deliberate_interlock_reset: false,
        rev38_authorized: true,
        inverter_requested: true,
    }
}

#[test]
fn source_manifest_and_fault_contracts_match_reviewed_bytes() {
    let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..");
    verify_sources(&repo).unwrap();
    // A changed manifest must not be rescued by editing all its expected hashes.
    let temp =
        std::env::temp_dir().join(format!("zapote-cooling-source-lock-{}", std::process::id()));
    let manifest = temp.join("zapote/thermal/cooker-envelope/sources.sha256");
    std::fs::create_dir_all(manifest.parent().unwrap()).unwrap();
    std::fs::write(&manifest, b"changed").unwrap();
    assert_eq!(
        verify_sources(&temp).unwrap_err(),
        "cooling source manifest changed"
    );
    std::fs::remove_dir_all(temp).unwrap();
}

#[test]
fn three_retained_models_replay_without_package_mixing() {
    let gbu395 = screen(&baseline(Candidate::Gbu395));
    assert_eq!(gbu395.verdict, Verdict::Conditional);
    assert!((gbu395.temperature_c.unwrap() - 120.0).abs() < 1e-9);
    assert_eq!(gbu395.installed_applicability, Verdict::Indeterminate);

    let gbu392 = screen(&baseline(Candidate::Gbu392));
    assert_eq!(gbu392.verdict, Verdict::Conditional);
    assert!((gbu392.temperature_c.unwrap() - 118.64).abs() < 0.01);

    let gbj392 = screen(&baseline(Candidate::Gbj392));
    assert_eq!(gbj392.verdict, Verdict::Conditional);
    assert!((gbj392.temperature_c.unwrap() - 59.63918514397842).abs() < 0.001);
    assert_eq!(gbj392.retained_gbj_boundary_consistent, Some(true));
}

#[test]
fn gbj_inlet_or_shared_heat_mutation_invalidates_the_fixed_fem_boundary() {
    let mut input = baseline(Candidate::Gbj392);
    input.inlet_c += 5.0;
    let hot_inlet = screen(&input);
    assert!((hot_inlet.temperature_c.unwrap() - 64.63918514397842).abs() < 0.001);
    assert_eq!(hot_inlet.verdict, Verdict::ScreenFail);
    assert_eq!(hot_inlet.retained_gbj_boundary_consistent, Some(false));
    input = baseline(Candidate::Gbj392);
    input.other_pfc = sink_heat(75.0);
    let extra_heat = screen(&input);
    assert!((extra_heat.temperature_c.unwrap() - 61.4149).abs() < 0.01);
    assert_eq!(extra_heat.reason, Reason::RetainedFemBoundaryExceeded);
}

#[test]
fn gbu_failed_fan_is_a_conditional_150c_stress_not_an_installed_trip_time() {
    let mut input = baseline(Candidate::Gbu395);
    input.air = AirEvidence::FanOff;
    let stress = screen(&input);
    assert_eq!(stress.verdict, Verdict::ScreenFail);
    assert!((stress.temperature_c.unwrap() - 150.0).abs() < 1e-9);
    assert_eq!(stress.installed_applicability, Verdict::Indeterminate);
    input = baseline(Candidate::Gbj392);
    input.air = AirEvidence::FanOff;
    assert_eq!(screen(&input).verdict, Verdict::Indeterminate);
}

#[test]
fn identity_airflow_support_and_loss_mutations_fail_closed() {
    let mut input = baseline(Candidate::Gbj392);
    input.identity.model = ModelBoundary::GbuWholeBridge;
    assert_eq!(screen(&input).reason, Reason::MixedCandidateIdentity);
    input = baseline(Candidate::Gbj392);
    input.air = AirEvidence::FreeAirEndpoint { flow_cfm: 120.0 };
    assert_eq!(screen(&input).reason, Reason::FreeAirIsNotInstalledFlow);
    input = baseline(Candidate::Gbj392);
    input.air = AirEvidence::CatalogPoint {
        flow_cfm: 100.0,
        fan_voltage_v: 7.0,
    };
    assert_eq!(screen(&input).reason, Reason::CatalogPointMismatch);
    input = baseline(Candidate::Gbj392);
    input.air = AirEvidence::Installed {
        flow_cfm: 100.0,
        pressure_pa: None,
    };
    assert_eq!(screen(&input).verdict, Verdict::Indeterminate);
    input = baseline(Candidate::Gbj392);
    input.support = Support::PcbOrLeadSupported;
    assert_eq!(screen(&input).reason, Reason::UnsupportedSink);
    input = baseline(Candidate::Gbj392);
    input.support = Support::Unknown;
    assert_eq!(screen(&input).verdict, Verdict::Indeterminate);
    input = baseline(Candidate::Gbj392);
    input.other_pfc = None;
    assert_eq!(screen(&input).reason, Reason::MissingHeat);
    input = baseline(Candidate::Gbj392);
    input.other_pfc = Some(HeatTerm {
        watts: 65.0,
        destination: HeatDestination::Unknown,
    });
    assert_eq!(screen(&input).reason, Reason::UnknownHeatDestination);
    input = baseline(Candidate::Gbj392);
    input.scope = Scope::WholeCooker;
    assert_eq!(screen(&input).reason, Reason::MissingHeat);
    input = baseline(Candidate::Gbj392);
    input.auxiliary = sink_heat(1.0);
    assert_eq!(screen(&input).reason, Reason::WholeCookerModelMissing);
}

#[test]
fn aux_loss_with_nc_discharge_and_no_fan_cannot_borrow_mounted_rating() {
    for (voltage, intact, shorted, survivor) in [
        (400.0, 21.3333333333, 32.0, 21.3333333333),
        (450.0, 27.0, 40.5, 27.0),
    ] {
        let normal = aux_loss_nc_discharge(
            voltage,
            DischargeFault::Intact,
            true,
            ResistanceCase::Nominal,
            VbFeedPath::F2Closed,
        );
        let fault = aux_loss_nc_discharge(
            voltage,
            DischargeFault::OneSeriesResistorShort,
            true,
            ResistanceCase::Nominal,
            VbFeedPath::F2Closed,
        );
        assert!((normal.total_w.unwrap() - intact).abs() < 1e-7);
        assert!((fault.total_w.unwrap() - shorted).abs() < 1e-7);
        assert!((fault.hottest_resistor_w.unwrap() - survivor).abs() < 1e-7);
        assert!(normal.mains_attached && fault.fan_off);
        assert!(normal.sustained_heat_possible && fault.sustained_heat_possible);
        assert_eq!(fault.verdict, DischargeVerdict::Indeterminate);
        assert_eq!(fault.rh50_mounted_fixture_cm2, 536.0);
        assert!(!fault.mounted_70c_rating_usable);
        assert!(fault.hottest_resistor_w.unwrap() > fault.rh50_unmounted_70c_rating_w);
        assert!(fault.hottest_resistor_w.unwrap() < fault.rh50_mounted_70c_rating_w);
    }
    assert_eq!(
        aux_loss_nc_discharge(
            f64::NAN,
            DischargeFault::Intact,
            true,
            ResistanceCase::Nominal,
            VbFeedPath::F2Closed
        )
        .verdict,
        DischargeVerdict::Invalid
    );
    let low = aux_loss_nc_discharge(
        450.0,
        DischargeFault::Intact,
        true,
        ResistanceCase::OnePercentLow,
        VbFeedPath::F2Closed,
    );
    let low_short = aux_loss_nc_discharge(
        450.0,
        DischargeFault::OneSeriesResistorShort,
        true,
        ResistanceCase::OnePercentLow,
        VbFeedPath::F2Closed,
    );
    assert!((low.total_w.unwrap() - 27.2727272727).abs() < 1e-7);
    assert!((low_short.total_w.unwrap() - 40.9090909091).abs() < 1e-7);
    assert_eq!(low_short.resistance_case, ResistanceCase::OnePercentLow);
    assert_eq!(low_short.verdict, DischargeVerdict::Indeterminate);
    let isolated_vb = aux_loss_nc_discharge(
        450.0,
        DischargeFault::Intact,
        true,
        ResistanceCase::OnePercentLow,
        VbFeedPath::F2OpenVbIsolated,
    );
    assert!(!isolated_vb.sustained_heat_possible);
    assert!(isolated_vb.total_w.is_some()); // instantaneous, finite-energy VB heat
    let other_feed = aux_loss_nc_discharge(
        450.0,
        DischargeFault::Intact,
        true,
        ResistanceCase::OnePercentLow,
        VbFeedPath::OtherVerifiedMainsFeedToVb,
    );
    assert!(other_feed.sustained_heat_possible);
    let mains_removed = aux_loss_nc_discharge(
        450.0,
        DischargeFault::Intact,
        false,
        ResistanceCase::OnePercentLow,
        VbFeedPath::F2Closed,
    );
    assert!(!mains_removed.sustained_heat_possible);
}

#[test]
fn startup_stall_auto_recovery_and_local_reset_keep_fault_asserted() {
    let mut fan = FanMonitor::new();
    let boot = fan.step(FanInputs {
        cooling_rail_good: false,
        ..good_fan()
    });
    assert!(!boot.heatsink_fault_sink_on);
    assert!(!boot.sensor_live_high);
    assert_eq!(fan.state, FanState::Unpowered);
    let starting = fan.step(FanInputs {
        all_tach_valid: false,
        ..good_fan()
    });
    assert!(!starting.heatsink_fault_sink_on);
    assert_eq!(fan.state, FanState::Starting);
    let ready = fan.step(good_fan());
    assert!(ready.heatsink_fault_sink_on);
    let stalled = fan.step(FanInputs {
        all_tach_valid: false,
        ..good_fan()
    });
    assert!(!stalled.heatsink_fault_sink_on);
    assert_eq!(fan.state, FanState::FaultLatched);
    assert!(!fan.step(good_fan()).heatsink_fault_sink_on); // motor auto-restarted
    assert!(
        !fan.step(FanInputs {
            reset_edge: true,
            ..good_fan()
        })
        .heatsink_fault_sink_on
    );
    assert_eq!(fan.state, FanState::Starting);
    assert!(fan.step(good_fan()).heatsink_fault_sink_on);
}

#[test]
fn sensing_faults_start_timeout_and_power_cycle_have_safe_logical_outputs() {
    let mut fan = FanMonitor::new();
    fan.step(good_fan()); // starting
    let timeout = fan.step(FanInputs {
        all_tach_valid: false,
        start_deadline_expired: true,
        ..good_fan()
    });
    assert!(!timeout.heatsink_fault_sink_on);
    assert_eq!(fan.state, FanState::FaultLatched);
    let lost_sensing = fan.step(FanInputs {
        sensing_rail_good: false,
        ..good_fan()
    });
    assert!(!lost_sensing.sensor_live_high && !lost_sensing.heatsink_fault_sink_on);
    let invalid_sensor = fan.step(FanInputs {
        sensor_valid: false,
        ..good_fan()
    });
    assert!(!invalid_sensor.sensor_live_high);
    let power_off = fan.step(FanInputs {
        cooling_rail_good: false,
        sensing_rail_good: false,
        ..good_fan()
    });
    assert!(!power_off.sensor_live_high && !power_off.heatsink_fault_sink_on);
    assert_eq!(fan.state, FanState::Unpowered);
    assert!(!fan.step(good_fan()).heatsink_fault_sink_on); // re-qualify on return
}

#[test]
fn downstream_permits_need_healthy_outputs_and_fresh_deliberate_reset() {
    let mut latch = DownstreamLatch::new();
    let ready = FanOutputs {
        heatsink_fault_sink_on: true,
        sensor_live_high: true,
    };
    let invalid = FanOutputs {
        heatsink_fault_sink_on: false,
        sensor_live_high: true,
    };
    assert!(!latch.step(ready, gate_inputs()).interlock_permit);
    assert!(
        !latch
            .step(
                invalid,
                DownstreamInputs {
                    fresh_deliberate_interlock_reset: true,
                    ..gate_inputs()
                }
            )
            .interlock_permit
    ); // reset during fault ignored
    let permitted = latch.step(
        ready,
        DownstreamInputs {
            fresh_deliberate_interlock_reset: true,
            ..gate_inputs()
        },
    );
    assert!(
        permitted.interlock_permit && permitted.pfc_run_allowed && permitted.inverter_gate_permit
    );
    let cooling_fault = latch.step(invalid, gate_inputs());
    assert!(!cooling_fault.pfc_run_allowed && !cooling_fault.inverter_gate_permit);
    assert!(!latch.step(ready, gate_inputs()).interlock_permit); // tach recovery alone
    let no_sensing = latch.step(
        FanOutputs {
            sensor_live_high: false,
            ..ready
        },
        gate_inputs(),
    );
    assert!(!no_sensing.interlock_permit);
    let no_power = latch.step(
        ready,
        DownstreamInputs {
            interlock_powered: false,
            ..gate_inputs()
        },
    );
    assert!(!no_power.interlock_permit);
    assert!(!latch.step(ready, gate_inputs()).interlock_permit); // complete cycle needs new edge
    let open_fault = DownstreamInputs {
        heatsink_fault_wire_intact: false,
        ..gate_inputs()
    };
    assert_eq!(
        interlock_pins(ready, open_fault).j1_4_heatsink_fault_high,
        Some(true)
    );
    assert!(!latch.step(ready, open_fault).interlock_permit);
    let open_live = DownstreamInputs {
        sensor_live_wire_intact: false,
        ..gate_inputs()
    };
    assert!(!interlock_pins(ready, open_live).j2_5_sensor_live_high);
    assert!(!latch.step(ready, open_live).interlock_permit);
    assert_eq!(
        interlock_pins(
            ready,
            DownstreamInputs {
                interlock_powered: false,
                ..gate_inputs()
            }
        )
        .j1_4_heatsink_fault_high,
        None
    );
    let pfc_only = latch.step(
        ready,
        DownstreamInputs {
            fresh_deliberate_interlock_reset: true,
            inverter_requested: false,
            ..gate_inputs()
        },
    );
    assert!(pfc_only.pfc_run_allowed && !pfc_only.inverter_gate_permit);
    let inverter_only = latch.step(
        ready,
        DownstreamInputs {
            rev38_authorized: false,
            ..gate_inputs()
        },
    );
    assert!(!inverter_only.pfc_run_allowed && inverter_only.inverter_gate_permit);
}

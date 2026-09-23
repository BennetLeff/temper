#[path = "model.rs"]
mod model;

use model::{InterruptedReservation, Model, Reject, State};

fn ready() -> (Model, u64) {
    let mut m = Model::new(0, 50, 10, 20);
    m.observe_disarm_low().unwrap();
    m.acknowledge_physical_disarm().unwrap();
    let id = m.reserve_session().unwrap();
    m.disarm_ack(id).unwrap();
    m.revalidation_level(true);
    assert_eq!(m.state(), State::Ready);
    (m, id)
}

fn start_pending() -> (Model, u64) {
    let (mut m, id) = ready();
    m.button_release();
    m.button_press().unwrap();
    m.raise_permit().unwrap();
    m.request(id, 7).unwrap();
    (m, id)
}

#[test]
fn permit_break_clears_both_latches_and_new_session_needs_disarm() {
    let (mut m, id) = start_pending();
    m.commit_start(id, 7).unwrap();
    m.deliver_start(id, 7).unwrap();
    assert!(m.running() && m.session_ok());
    m.physical_permit(false);
    assert_eq!(m.state(), State::Lockout);
    assert!(!m.source_permit() && !m.running() && !m.session_ok());
    assert_eq!(m.reserve_session(), Err(Reject::NotDisarmed));
    m.observe_disarm_low().unwrap();
    m.acknowledge_physical_disarm().unwrap();
    let next = m.reserve_session().unwrap();
    assert!(next > id);
    assert_eq!(m.disarm_ack(id), Err(Reject::WrongSession));
}

#[test]
fn stop_in_ready_clears_session_without_permit_ever_rising() {
    let (mut m, _) = ready();
    assert!(m.session_ok() && !m.source_permit());
    m.stop();
    assert!(m.abort_asserted() && !m.session_ok() && !m.running());
    assert_eq!(m.state(), State::Lockout);
}

#[test]
fn short_trip_during_preparation_cancels_even_with_session_q_already_low() {
    let mut m = Model::new(0, 50, 10, 20);
    m.observe_disarm_low().unwrap();
    m.acknowledge_physical_disarm().unwrap();
    let old = m.reserve_session().unwrap();
    assert!(!m.session_ok());
    m.external_trip();
    assert!(m.preparation_aborted());
    m.clear_external_fault();
    m.revalidation_level(true);
    assert!(!m.session_ok());
    assert_eq!(m.disarm_ack(old), Err(Reject::BadState));
    m.observe_disarm_low().unwrap();
    m.acknowledge_physical_disarm().unwrap();
    let new_id = m.reserve_session().unwrap();
    assert!(new_id > old);
    assert_eq!(m.highwater(), new_id);
}

#[test]
fn held_revalidation_request_cannot_clock_on_ack_or_fault_recovery() {
    let mut m = Model::new(0, 50, 10, 20);
    m.observe_disarm_low().unwrap();
    m.acknowledge_physical_disarm().unwrap();
    let id = m.reserve_session().unwrap();
    m.revalidation_level(true);
    m.disarm_ack(id).unwrap();
    m.revalidation_level(true);
    assert!(!m.session_ok());
    m.external_trip();
    m.clear_external_fault();
    m.revalidation_level(true);
    assert!(!m.session_ok());
}

#[test]
fn negative_control_held_request_gated_by_health_creates_a_late_clock() {
    // A naive clock = request && health generates a rising edge when health
    // recovers, even though the request was asserted before the fault.
    let held_request = true;
    let clock_during_fault = held_request && false;
    let clock_after_recovery = held_request && true;
    assert!(!clock_during_fault && clock_after_recovery);
    // The Rev38 model's revalidation_level test above instead requires a new
    // low-to-high request after the fault and a new durable session.
}

#[test]
fn trip_on_either_side_of_revalidation_edge_leaves_fault_memory_low() {
    let mut before = Model::new(0, 50, 10, 20);
    before.observe_disarm_low().unwrap();
    before.acknowledge_physical_disarm().unwrap();
    let id = before.reserve_session().unwrap();
    before.disarm_ack(id).unwrap();
    before.external_trip();
    before.revalidation_level(true);
    assert!(!before.session_ok());

    let mut after = Model::new(0, 50, 10, 20);
    after.observe_disarm_low().unwrap();
    after.acknowledge_physical_disarm().unwrap();
    let id = after.reserve_session().unwrap();
    after.disarm_ack(id).unwrap();
    after.revalidation_level(true);
    assert!(after.session_ok());
    after.external_trip();
    assert!(!after.session_ok() && !after.running());
}

#[test]
fn trip_after_revalidation_clears_session_and_old_start_cannot_repair_it() {
    let (mut m, id) = start_pending();
    m.commit_start(id, 7).unwrap();
    m.external_trip();
    m.clear_external_fault();
    assert!(!m.session_ok() && !m.running());
    assert!(m.deliver_start(id, 7).is_err());
}

#[test]
fn healthy_traffic_cannot_extend_fixed_start_deadline() {
    let (mut m, id) = start_pending();
    m.commit_start(id, 7).unwrap();
    m.at(9);
    assert_eq!(m.state(), State::StartPending);
    m.local_safety_cycle();
    m.fresh_link_exchange(1);
    m.feed_source_wdi().unwrap();
    m.at(10);
    assert_eq!(m.state(), State::Lockout);
    assert!(m.deliver_start(id, 7).is_err());
    assert!(!m.running());
}

#[test]
fn one_pre_reset_start_can_run_but_gets_no_second_watchdog_interval() {
    let (mut m, id) = start_pending();
    m.commit_start(id, 7).unwrap();
    m.at(5);
    m.unexpected_source_reset();
    m.source_boot();
    assert_eq!(m.feed_source_wdi(), Err(Reject::SourceReset));
    m.deliver_start(id, 7).unwrap();
    assert!(m.running());
    assert_eq!(m.source_wdi_last(), 0);
    assert_eq!(m.commit_start(id, 7), Err(Reject::SourceReset));
    m.at(20);
    assert!(!m.running() && !m.source_permit());
    assert_eq!(m.reserve_session(), Err(Reject::NotDisarmed));
    m.observe_disarm_low().unwrap();
    m.acknowledge_physical_disarm().unwrap();
    assert!(m.reserve_session().unwrap() > id);
}

#[test]
fn already_running_and_first_start_share_watchdog_deadline() {
    let (mut m, id) = start_pending();
    m.commit_start(id, 7).unwrap();
    m.deliver_start(id, 7).unwrap();
    m.at(5);
    m.unexpected_source_reset();
    m.source_boot();
    m.at(19);
    assert!(m.running());
    m.at(20);
    assert!(!m.running());
}

#[test]
fn reset_before_commit_does_not_create_or_retransmit_start() {
    let (mut m, id) = start_pending();
    m.unexpected_source_reset();
    m.source_boot();
    assert_eq!(m.commit_start(id, 7), Err(Reject::SourceReset));
    assert!(m.deliver_start(id, 7).is_err());
}

#[test]
fn receiver_reset_asserts_abort_with_latches_previously_powered() {
    let (mut m, _) = start_pending();
    assert!(m.session_ok());
    m.receiver_reset();
    assert!(m.abort_asserted() && !m.session_ok() && !m.running());
    assert!(!m.source_permit());
}

#[test]
fn source_readback_loss_is_retained_after_the_readback_recovers() {
    let (mut m, _) = start_pending();
    m.source_readback(false);
    m.source_readback(true);
    assert_eq!(m.state(), State::Lockout);
    assert!(!m.source_permit() && !m.session_ok() && !m.running());
}

#[test]
fn rail_loss_with_logic_unavailable_clears_retained_permission() {
    let (mut m, _) = ready();
    m.rail_good(false);
    assert!(m.abort_asserted() && !m.session_ok() && !m.running());
    m.rail_good(true);
    assert_eq!(m.state(), State::Lockout);
}

#[test]
fn watchdog_feed_needs_new_local_and_link_progress_in_ready() {
    let (mut m, _) = ready();
    assert_eq!(m.feed_source_wdi(), Err(Reject::NoProgress));
    m.local_safety_cycle();
    assert_eq!(m.feed_source_wdi(), Err(Reject::NoProgress));
    m.fresh_link_exchange(1);
    m.feed_source_wdi().unwrap();
    assert_eq!(m.feed_source_wdi(), Err(Reject::NoProgress));
    m.local_safety_cycle();
    m.fresh_link_exchange(1);
    assert_eq!(m.feed_source_wdi(), Err(Reject::NoProgress));
    m.fresh_link_exchange(2);
    m.feed_source_wdi().unwrap();
}

#[test]
fn interrupted_reservation_advances_or_locks_out_without_reusing_published_id() {
    let mut m = Model::new(7, 50, 10, 20);
    m.interrupt_reservation(InterruptedReservation::BeforeCommit);
    m.observe_disarm_low().unwrap();
    m.acknowledge_physical_disarm().unwrap();
    assert_eq!(m.reserve_session().unwrap(), 8);

    let mut advanced = Model::new(7, 50, 10, 20);
    advanced.interrupt_reservation(InterruptedReservation::AfterCommit);
    advanced.observe_disarm_low().unwrap();
    advanced.acknowledge_physical_disarm().unwrap();
    assert_eq!(advanced.reserve_session().unwrap(), 9);

    let mut corrupt = Model::new(7, 50, 10, 20);
    corrupt.interrupt_reservation(InterruptedReservation::Corrupt);
    corrupt.observe_disarm_low().unwrap();
    corrupt.acknowledge_physical_disarm().unwrap();
    assert_eq!(corrupt.reserve_session(), Err(Reject::StorageFault));
}

#[test]
fn deliberate_restart_requires_prior_physical_disarm_acknowledgement() {
    let (mut m, _) = ready();
    assert_eq!(m.deliberate_restart(), Err(Reject::NotDisarmed));
    m.stop();
    assert_eq!(m.deliberate_restart(), Err(Reject::NotDisarmed));
    m.observe_disarm_low().unwrap();
    m.acknowledge_physical_disarm().unwrap();
    m.deliberate_restart().unwrap();
    assert_eq!(m.feed_source_wdi(), Err(Reject::SourceReset));
}

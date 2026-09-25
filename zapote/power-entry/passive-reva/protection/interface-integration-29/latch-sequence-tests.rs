//! Logical startup/clear checks for the Rev29 SN74HCS74 second half.
//! The model starts Q2 unknown or high and only applies datasheet-qualified
//! clear behavior once logic5 is in the valid operating range. It is not an
//! analog ramp, metastability, or silicon power-up simulation.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Q {
    Unknown,
    Low,
    High,
}

struct LinkLatch {
    q: Q,
    previous_pulse: bool,
}

impl LinkLatch {
    fn step(
        &mut self,
        logic5_valid: bool,
        rails_ok: bool,
        watchdog_ok: bool,
        qualified_pulse: bool,
    ) {
        let fresh_edge = qualified_pulse && !self.previous_pulse;
        // In valid logic5, either low input forces the AND output low and
        // asserts asynchronous clear. Below the valid rail range no state is
        // claimed; the separate gate-driver default-off path owns that region.
        if logic5_valid && (!rails_ok || !watchdog_ok) {
            self.q = Q::Low;
        } else if logic5_valid && fresh_edge {
            self.q = Q::High; // D2 is tied high; only a fresh edge can set Q2.
        }
        self.previous_pulse = qualified_pulse;
    }
}

#[test]
fn valid_logic_rail_supervisor_clears_unknown_or_high_power_up_state() {
    for initial in [Q::Unknown, Q::High] {
        let mut latch = LinkLatch { q: initial, previous_pulse: false };
        // Once the 5 V logic rail is valid, TPS3890 keeps rails_ok low until
        // its monitored rail and release delay are satisfied. This clear is
        // independent of the TPS3431's below-POR ENOUT/WDO state.
        latch.step(true, false, true, false);
        assert_eq!(latch.q, Q::Low);
    }
}

#[test]
fn below_valid_logic_rail_range_is_explicitly_unmodeled() {
    let mut latch = LinkLatch { q: Q::High, previous_pulse: false };
    latch.step(false, false, false, false);
    assert_eq!(latch.q, Q::High);
}

#[test]
fn rail_release_alone_does_not_create_link_good() {
    let mut latch = LinkLatch { q: Q::Low, previous_pulse: false };
    latch.step(true, true, false, false); // watchdog not yet session-ready
    assert_eq!(latch.q, Q::Low);
    latch.step(true, true, true, false); // both clear inputs release
    assert_eq!(latch.q, Q::Low);
}

#[test]
fn one_new_qualified_pulse_sets_link_good_after_rails_and_watchdog_ready() {
    let mut latch = LinkLatch { q: Q::Low, previous_pulse: false };
    latch.step(true, true, true, true);
    assert_eq!(latch.q, Q::High);
}

#[test]
fn watchdog_timeout_clears_and_recovery_does_not_restore_link_good() {
    let mut latch = LinkLatch { q: Q::High, previous_pulse: false };
    latch.step(true, true, false, false); // WDO/ENOUT pulls clear qualifier low
    assert_eq!(latch.q, Q::Low);
    latch.step(true, true, true, false); // WDO returns high; Q2 stays cleared
    assert_eq!(latch.q, Q::Low);
    latch.step(true, true, true, true); // fresh qualified edge only
    assert_eq!(latch.q, Q::High);
}

#[test]
fn rail_loss_clears_and_requires_a_new_pulse_after_recovery() {
    let mut latch = LinkLatch { q: Q::High, previous_pulse: false };
    latch.step(true, false, true, false);
    assert_eq!(latch.q, Q::Low);
    latch.step(true, true, true, false);
    assert_eq!(latch.q, Q::Low);
    latch.step(true, true, true, true);
    assert_eq!(latch.q, Q::High);
}

#[test]
fn simultaneous_fault_and_pulse_is_clear_dominant() {
    let mut latch = LinkLatch { q: Q::High, previous_pulse: false };
    latch.step(true, true, false, true);
    assert_eq!(latch.q, Q::Low);
}

#[test]
fn held_high_session_pulse_during_clear_release_does_not_set_link_good() {
    let mut latch = LinkLatch { q: Q::High, previous_pulse: false };
    latch.step(true, false, false, true); // pulse rises while clear asserted
    assert_eq!(latch.q, Q::Low);
    latch.step(true, true, true, true); // clear releases with clock held high
    assert_eq!(latch.q, Q::Low);
    latch.step(true, true, true, false);
    latch.step(true, true, true, true); // a genuinely new rising edge
    assert_eq!(latch.q, Q::High);
}

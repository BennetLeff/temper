//! Adversarial contract model comparing the present one-bit hardware interface
//! with the Rev13 session receiver. This models state and event ordering only;
//! it is not SPICE, MCU firmware, or an analog timing model.

#[derive(Clone, Copy, Debug, Default)]
struct HardwareOnly {
    source_permit: bool,
    hot_run: bool,
    hot_ready: bool,
    hot_lockout_latch: bool,
    start_locked_out: bool,
    start_released: bool,
    hot_rails: bool,
    source_health: bool,
    watchdog_healthy: bool,
    arm: bool,
    button_level: bool,
    fresh_local_start: bool,
    arm_seen_low_since_hot_reset: bool,
    wdi_elapsed_ms: u16,
    hot_command: bool,
    hot_response: bool,
}

impl HardwareOnly {
    fn healthy() -> Self {
        Self {
            hot_rails: true,
            hot_ready: true,
            hot_lockout_latch: false,
            start_locked_out: true,
            start_released: false,
            source_health: true,
            watchdog_healthy: true,
            arm_seen_low_since_hot_reset: true,
            button_level: false,
            fresh_local_start: false,
            hot_command: false,
            hot_response: false,
            ..Self::default()
        }
    }

    fn clear_source(&mut self) {
        self.source_permit = false;
        self.hot_run = false;
        self.start_locked_out = true;
        self.start_released = false;
    }

    fn source_fault(&mut self) {
        self.source_health = false;
        self.clear_source();
        self.hot_permit_line(false);
    }

    fn source_health_recovers(&mut self) {
        self.source_health = true;
        // Source permit latch is deliberately retained cleared.
    }

    fn hot_fault_feedback(&mut self) {
        // This represents the *later* reverse-isolator observation, separate
        // from the HOT-side latch transition.
        self.source_observes_hot_ready_low();
    }

    fn source_observes_hot_ready_low(&mut self) {
        // SELV latch clears only after the HOT_READY low traverses ISO.
        self.clear_source();
    }

    fn hot_local_fault(&mut self) {
        // HOT-side async latch reacts before reverse isolation propagation.
        self.hot_ready = false;
        self.hot_lockout_latch = true;
        self.hot_run = false;
    }

    fn hot_fault_recovers(&mut self) {
        self.hot_rails = true;
        // HOT_READY remains low until a separately gated HOT_REARM pulse.
        self.hot_ready = !self.hot_lockout_latch;
    }

    fn hot_rearm_wire_edge(&mut self) {
        // Hardware receiver has no access to ESP-local user intent. Any
        // qualifying edge on this wire is physically identical.
        if self.hot_rails && self.source_health
            && self.watchdog_healthy {
            self.hot_lockout_latch = false;
            self.hot_ready = true;
        }
    }

    fn esp_issues_hot_rearm_after_fresh_start(&mut self) {
        if self.fresh_local_start {
            self.hot_rearm_wire_edge();
        }
    }

    fn hot_permit_line(&mut self, high: bool) {
        if !high {
            // Receiver-side asynchronous fault latch retains the low after a
            // fast open/reconnect of the maintained PERMIT conductor. Source
            // feedback is deliberately a separate later event.
            self.hot_run = false;
            self.hot_lockout_latch = true;
            self.hot_ready = false;
        }
    }

    fn local_start_level(&mut self, level: bool) {
        if !level {
            self.start_released = true;
        }
        let rising = !self.button_level && level;
        self.button_level = level;
        if rising && self.start_released && self.start_locked_out
            && self.hot_rails && self.source_health && self.watchdog_healthy {
            self.fresh_local_start = true;
        }
    }

    fn complete_fresh_start_sequence(&mut self) {
        // Stages: HOT_REARM pulse -> observe HOT_READY -> source latch rearm
        // -> a distinct HOT ARM edge. This avoids requiring HOT_READY high
        // before a fault-cleared HOT latch can be reset.
        self.esp_issues_hot_rearm_after_fresh_start();
        if self.fresh_local_start && self.hot_ready && self.start_locked_out {
            if self.source_rearm(true) {
                self.start_locked_out = false;
                self.arm_level(false);
                self.arm_level(true);
                self.fresh_local_start = false;
            }
        }
    }

    fn source_rearm(&mut self, fresh_edge: bool) -> bool {
        if fresh_edge && self.fresh_local_start && self.hot_ready
            && self.source_health && self.watchdog_healthy {
            self.source_permit = true;
            true
        } else { false }
    }

    fn hot_brownout(&mut self) {
        self.hot_rails = false;
        self.hot_local_fault();
        self.arm_seen_low_since_hot_reset = false;
    }

    fn hot_rails_recover(&mut self) {
        self.hot_fault_recovers();
        // An edge sampled during brownout is not accepted. A low must be
        // observed on the live receiver after reset before an ARM edge.
    }

    fn arm_level(&mut self, level: bool) {
        if !level {
            self.arm_seen_low_since_hot_reset = true;
        }
        let rising = !self.arm && level;
        self.arm = level;
        if rising
            && self.arm_seen_low_since_hot_reset
            && self.hot_rails
            && self.source_permit
            && self.hot_ready
            && !self.hot_lockout_latch
            && self.source_health
            && self.watchdog_healthy
        {
            self.hot_run = true;
        }
    }

    fn watchdog_tick_ms(&mut self, elapsed: u16, timeout: u16) {
        self.wdi_elapsed_ms = self.wdi_elapsed_ms.saturating_add(elapsed);
        if self.wdi_elapsed_ms >= timeout {
            self.watchdog_healthy = false;
            self.clear_source();
        }
    }

    fn accepted_wdi_edge(&mut self) {
        self.wdi_elapsed_ms = 0;
        self.watchdog_healthy = true;
        // WDO recovering does not set the cleared source permit latch.
    }

    fn raw_heartbeat_during_cpu_reset(&mut self) {
        // Hardware-only observer sees a valid-looking edge. It has no pin
        // that identifies the ESP32 CPU-only reset event.
        self.accepted_wdi_edge();
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Frame { epoch: u32, intent: u32 }

#[derive(Default)]
struct SessionReceiver {
    epoch: u32,
    session_valid: bool,
    expected_intent: Option<u32>,
    permit: bool,
    rails: bool,
    run: bool,
}

impl SessionReceiver {
    fn healthy(epoch: u32) -> Self {
        Self { epoch, session_valid: true, expected_intent: None, permit: true, rails: true, run: false }
    }
    fn fault(&mut self) { self.run = false; self.expected_intent = None; self.session_valid = false; }
    fn begin_new_session(&mut self, epoch: u32) {
        assert!(epoch > self.epoch, "session identifiers must not be reused");
        self.epoch = epoch;
        self.session_valid = true;
        self.expected_intent = None;
    }
    fn request(&mut self, f: Frame) -> bool {
        if self.session_valid && self.permit && self.rails && f.epoch == self.epoch && f.intent != 0 {
            self.expected_intent = Some(f.intent);
            true
        } else { false }
    }
    fn start(&mut self, f: Frame) -> bool {
        if self.session_valid && self.permit && self.rails && f.epoch == self.epoch
            && self.expected_intent == Some(f.intent) {
            self.run = true;
            true
        } else { false }
    }
}

/// Candidate HOT-local pulse-drain guard. Times are integer nanoseconds. The
/// `blank_min_ns` input is a design bound, not a measured value; the guard is
/// safe only if it exceeds the worst HOT_REARM path delay and any pulse that
/// can already be queued at the fault boundary.
#[derive(Clone, Copy, Debug)]
struct BlankedHot {
    now_ns: u64,
    blank_until_ns: u64,
    blank_min_ns: u64,
    hot_fault_active: bool,
    hot_rails: bool,
    lockout: bool,
    hot_ready: bool,
    rearm_level: bool,
    low_seen_after_blank: bool,
    source_permit: bool,
    hot_run: bool,
}

impl BlankedHot {
    fn fault_locked(blank_min_ns: u64) -> Self {
        Self {
            now_ns: 0,
            blank_until_ns: 0,
            blank_min_ns,
            hot_fault_active: false,
            hot_rails: true,
            lockout: true,
            hot_ready: false,
            rearm_level: false,
            low_seen_after_blank: true,
            source_permit: false,
            hot_run: false,
        }
    }

    fn at(&mut self, now_ns: u64) {
        assert!(now_ns >= self.now_ns, "events must be monotonic");
        self.now_ns = now_ns;
        if now_ns >= self.blank_until_ns && !self.rearm_level {
            self.low_seen_after_blank = true;
        }
    }

    fn hot_fault_assert(&mut self, now_ns: u64) {
        self.at(now_ns);
        // Fault is set-dominant: immediately remove RUN and READY, retain
        // lockout, and restart the drain timer even if already locked out.
        self.hot_fault_active = true;
        self.lockout = true;
        self.hot_ready = false;
        self.hot_run = false;
        self.blank_until_ns = now_ns + self.blank_min_ns;
        self.low_seen_after_blank = false;
    }

    fn hot_fault_recover(&mut self, now_ns: u64) {
        self.at(now_ns);
        self.hot_fault_active = false;
        // Fault recovery alone does not remove lockout or assert READY.
    }

    fn hot_brownout(&mut self, now_ns: u64) {
        self.hot_fault_assert(now_ns);
        self.hot_rails = false;
    }

    fn hot_rails_recover(&mut self, now_ns: u64) {
        self.at(now_ns);
        self.hot_rails = true;
        // A real circuit must also trigger/extend the drain interval from
        // rails-good. Model that by starting a new interval here.
        self.blank_until_ns = now_ns + self.blank_min_ns;
        self.low_seen_after_blank = false;
    }

    fn source_observes_ready_low(&mut self, now_ns: u64) {
        self.at(now_ns);
        self.source_permit = false;
        self.hot_run = false;
    }

    fn rearm_wire_level(&mut self, level: bool, now_ns: u64) {
        self.at(now_ns);
        let rising = !self.rearm_level && level;
        self.rearm_level = level;
        if !level && now_ns >= self.blank_until_ns {
            self.low_seen_after_blank = true;
        }
        if rising
            && now_ns >= self.blank_until_ns
            && self.low_seen_after_blank
            && !self.hot_fault_active
            && self.hot_rails
        {
            self.lockout = false;
            self.hot_ready = true;
        }
    }

    fn source_permit_and_arm(&mut self, now_ns: u64) {
        self.at(now_ns);
        if self.hot_ready && !self.lockout && !self.hot_fault_active && self.hot_rails {
            self.source_permit = true;
            self.hot_run = true;
        }
    }

    fn source_permit_set_after_health(&mut self, now_ns: u64) {
        self.at(now_ns);
        if now_ns >= self.blank_until_ns && !self.hot_fault_active && self.hot_rails {
            self.source_permit = true;
        }
    }

    fn source_permit_wire(&mut self, high: bool, now_ns: u64) {
        self.at(now_ns);
        self.source_permit = high;
        if !high {
            // PERMIT-low clears both RUN and the retained HOT_READY latch.
            self.hot_ready = false;
            self.lockout = true;
            self.hot_run = false;
        }
    }

    fn arm_rising_edge(&mut self, now_ns: u64) {
        self.at(now_ns);
        if self.source_permit && self.hot_ready && !self.lockout
            && !self.hot_fault_active && self.hot_rails {
            self.hot_run = true;
        }
    }
}

#[test]
fn source_fault_clears_both_latches_and_health_recovery_does_not_rearm() {
    let mut h = HardwareOnly { source_permit: true, hot_run: true, ..HardwareOnly::healthy() };
    h.source_fault();
    h.source_health_recovers();
    assert!(!h.source_permit && !h.hot_run);
}

#[test]
fn hardware_only_fault_feedback_holds_permit_low_until_released_then_fresh_local_start() {
    let mut h = HardwareOnly { source_permit: true, hot_run: true, arm: true, ..HardwareOnly::healthy() };
    h.hot_local_fault();
    h.hot_fault_feedback();
    h.hot_fault_recovers();
    assert!(!h.source_permit && !h.hot_run);
    h.local_start_level(true); // held/replayed level through recovery
    assert!(!h.source_permit && !h.hot_run);
    h.local_start_level(false);
    h.local_start_level(true); // fresh local action
    h.complete_fresh_start_sequence();
    assert!(h.source_permit && h.hot_run);
}

#[test]
fn dual_permit_arm_open_reconnect_is_held_off_by_latched_hot_ready_feedback() {
    let mut h = HardwareOnly { source_permit: true, hot_run: true, arm: true, ..HardwareOnly::healthy() };
    h.hot_permit_line(false);
    h.arm_level(false);
    h.arm_level(true); // ARM reconnects before reverse feedback propagates
    assert!(!h.hot_run && h.source_permit);
    h.hot_fault_feedback();
    h.hot_permit_line(true);
    h.hot_fault_recovers();
    h.arm_level(true);
    assert!(!h.hot_run && !h.source_permit && !h.hot_ready);
    // Firmware refuses to originate it without a fresh local edge.
    h.esp_issues_hot_rearm_after_fresh_start();
    assert!(!h.hot_ready && !h.source_permit && !h.hot_run);
    h.local_start_level(false);
    h.local_start_level(true);
    h.complete_fresh_start_sequence();
    assert!(h.hot_ready && h.source_permit && h.hot_run);
}

#[test]
fn pre_fault_rearm_pulse_can_authorize_post_fault_start() {
    let mut h = HardwareOnly {
        source_permit: false,
        hot_run: false,
        hot_ready: false,
        hot_lockout_latch: true,
        start_released: true,
        ..HardwareOnly::healthy()
    };
    // ESP observes a fresh local press and emits HOT_REARM while PERMIT is
    // still low. The pulse has not reached HOT yet.
    h.local_start_level(true);
    assert!(h.fresh_local_start && !h.source_permit && !h.hot_ready);
    // A HOT fault occurs while HOT_READY is already low from lockout. The
    // reverse status has no new edge that can invalidate the source intent.
    h.hot_local_fault();
    h.hot_fault_recovers();
    // The pre-fault pulse arrives after recovery. The one-bit receiver cannot
    // tell that the source's intent predates this fault.
    h.hot_rearm_wire_edge();
    assert!(h.hot_ready && !h.source_permit);
    // The source sees HOT_READY high, then completes the original sequence
    // without a new press after the HOT fault.
    assert!(h.source_rearm(true));
    h.arm_level(false);
    h.arm_level(true);
    assert!(h.hot_ready && h.hot_run && h.source_permit);
    // RUN after the intervening HOT fault violates fresh post-fault intent.
}

#[test]
fn arm_reconnect_high_while_source_latch_is_fault_locked_out_cannot_restart() {
    let mut h = HardwareOnly { source_permit: true, hot_run: true, arm: true, ..HardwareOnly::healthy() };
    h.source_fault();
    h.source_health_recovers();
    h.arm_level(false); // cable low/reconnect during lockout
    h.arm_level(true);  // reconnect high
    assert!(!h.source_permit && !h.hot_run);
    h.local_start_level(false);
    h.local_start_level(true);
    h.complete_fresh_start_sequence();
    assert!(h.source_permit && h.hot_run);
}

#[test]
fn hot_brownout_clears_run_and_held_arm_cannot_restart_on_ramp() {
    let mut h = HardwareOnly { source_permit: true, hot_run: true, arm: true, ..HardwareOnly::healthy() };
    h.hot_brownout();
    h.hot_rails_recover();
    assert!(!h.hot_run);
    h.arm_level(true);
    assert!(!h.hot_run);
    h.local_start_level(false);
    h.local_start_level(true);
    h.complete_fresh_start_sequence();
    assert!(h.hot_run);
}

#[test]
fn arm_reconnect_high_while_permit_is_high_is_indistinguishable_from_start() {
    let mut h = HardwareOnly { source_permit: true, ..HardwareOnly::healthy() };
    h.arm_level(false); // already healthy, no prior fault latch is present
    h.arm_level(true);  // cable reconnect sources a high level
    assert!(h.hot_run, "the hardware accepts the reconnect edge as ARM");
}

#[test]
fn held_start_during_reset_needs_release_then_new_edge() {
    let mut h = HardwareOnly { source_permit: true, ..HardwareOnly::healthy() };
    h.hot_brownout();
    h.hot_rails_recover();
    h.arm_level(true);
    assert!(!h.hot_run);
    h.local_start_level(false);
    h.local_start_level(true);
    h.complete_fresh_start_sequence();
    assert!(h.hot_run);
}

#[test]
fn stale_or_replayed_one_bit_start_has_same_waveform_as_fresh_start_while_armed() {
    let mut fresh = HardwareOnly { source_permit: true, ..HardwareOnly::healthy() };
    let mut replay = fresh;
    for (time_ms, level) in [(0, false), (10, true)] {
        let _ = time_ms;
        fresh.arm_level(level);
        replay.arm_level(level); // exact same wire waveform, old semantic intent
    }
    assert_eq!(fresh.hot_run, replay.hot_run);
    assert!(replay.hot_run, "no receiver state can infer intent from identical samples");
}

#[test]
fn source_cpu_only_reset_with_retained_wdi_is_not_captured_by_external_watchdog() {
    let mut h = HardwareOnly { source_permit: true, hot_run: true, ..HardwareOnly::healthy() };
    h.watchdog_tick_ms(80, 130);
    h.raw_heartbeat_during_cpu_reset();
    h.watchdog_tick_ms(80, 130);
    assert!(h.source_permit && h.hot_run);
}

#[test]
fn static_retained_wdi_times_out_and_both_latches_remain_off() {
    let mut h = HardwareOnly { source_permit: true, hot_run: true, ..HardwareOnly::healthy() };
    h.watchdog_tick_ms(130, 130); // no falling edge from a static retained GPIO
    assert!(!h.source_permit && !h.hot_run);
    h.watchdog_tick_ms(130, 130);
    assert!(!h.source_permit && !h.hot_run);
}

#[test]
fn actual_watchdog_timeout_clears_permit_and_valid_edge_alone_does_not_restore_it() {
    let mut h = HardwareOnly { source_permit: true, hot_run: true, ..HardwareOnly::healthy() };
    h.watchdog_tick_ms(130, 130);
    assert!(!h.source_permit && !h.hot_run);
    h.accepted_wdi_edge();
    assert!(!h.source_permit && !h.hot_run);
    h.source_health_recovers();
    h.local_start_level(false);
    h.local_start_level(true);
    h.source_rearm(true);
    assert!(h.source_permit);
}

#[test]
fn isolator_channels_are_directional_and_do_not_prove_session_freshness() {
    // ISO7741F is three SELV->HOT channels and one HOT->SELV channel.
    // The mapping permits request/response direction, but has no semantics.
    let selv_to_hot = [true, true, true, false];
    let hot_to_selv = [false, false, false, true];
    assert!(selv_to_hot[0] && !hot_to_selv[0]);
    assert!(hot_to_selv[3] && !selv_to_hot[3]);
    let mut h = HardwareOnly::healthy();
    h.hot_command = true;
    h.hot_response = true;
    assert!(h.hot_command && h.hot_response);
    assert!(!h.source_permit && !h.hot_run);
}

#[test]
fn session_receiver_rejects_old_epoch_and_old_intent_after_fault() {
    let mut r = SessionReceiver::healthy(9);
    assert!(r.request(Frame { epoch: 9, intent: 14 }));
    assert!(r.start(Frame { epoch: 9, intent: 14 }));
    r.fault();
    assert!(!r.request(Frame { epoch: 9, intent: 15 }));
    r.begin_new_session(10);
    assert!(!r.start(Frame { epoch: 9, intent: 14 }));
    assert!(!r.request(Frame { epoch: 9, intent: 15 }));
    assert!(!r.run);
}

#[test]
fn session_receiver_requires_new_request_after_hot_rail_reset() {
    let mut r = SessionReceiver::healthy(2);
    assert!(r.request(Frame { epoch: 2, intent: 7 }));
    r.fault();
    assert!(!r.start(Frame { epoch: 2, intent: 7 }));
    r.begin_new_session(3);
    assert!(r.request(Frame { epoch: 3, intent: 8 }));
    assert!(r.start(Frame { epoch: 3, intent: 8 }));
}

#[test]
fn blank_guard_rejects_pre_fault_pulse_then_accepts_only_a_new_post_blank_press() {
    const TBLANK_MIN_NS: u64 = 229_000_000; // provisional TPS3890 CT lower bound
    const ISO_DELAY_MAX_NS: u64 = 21; // TI ISO7741F at 2.5-V worst-case table value
    const MODEL_FAULT_TIME_NS: u64 = 400_000_000;
    let mut h = BlankedHot::fault_locked(TBLANK_MIN_NS);
    h.source_permit_set_after_health(MODEL_FAULT_TIME_NS - 1_000_000);
    assert!(h.source_permit && !h.hot_ready);

    // ESP emitted HOT_REARM before the HOT fault; its edge is still in the
    // isolator when local fault logic asserts. HOT_HEALTH falls and clears
    // source PERMIT independently of HOT_READY/Q2.
    h.hot_fault_assert(MODEL_FAULT_TIME_NS);
    h.source_observes_ready_low(MODEL_FAULT_TIME_NS + 1);
    h.hot_fault_recover(MODEL_FAULT_TIME_NS + 10_000);
    h.rearm_wire_level(true, MODEL_FAULT_TIME_NS + 10_000 + ISO_DELAY_MAX_NS);
    h.rearm_wire_level(false, MODEL_FAULT_TIME_NS + 1_000_000);
    h.at(MODEL_FAULT_TIME_NS + TBLANK_MIN_NS);
    assert!(!h.hot_ready && h.lockout && !h.source_permit && !h.hot_run);

    // The old source intent was canceled when HOT_HEALTH fell; it cannot
    // emit another pulse after the guard. A new local press first raises
    // PERMIT while Q2 lockout is still low, then emits a fresh rearm edge.
    h.source_permit_set_after_health(MODEL_FAULT_TIME_NS + TBLANK_MIN_NS + 1);
    h.rearm_wire_level(true, MODEL_FAULT_TIME_NS + TBLANK_MIN_NS + 1);
    assert!(h.hot_ready && h.source_permit && !h.hot_run);
    h.arm_rising_edge(MODEL_FAULT_TIME_NS + TBLANK_MIN_NS + 2);
    assert!(h.hot_ready && !h.lockout && h.source_permit && h.hot_run);
}

#[test]
fn permit_open_while_running_clears_hot_ready_and_arm_reconnect_cannot_restart() {
    let mut h = BlankedHot::fault_locked(100_000);
    h.hot_ready = true;
    h.lockout = false;
    h.source_permit = true;
    h.hot_run = true;
    h.source_permit_wire(false, 10); // conductor opens during RUN
    h.source_permit_wire(true, 20);  // reconnects high
    h.arm_rising_edge(21);           // ARM reconnect edge
    assert!(!h.hot_ready && h.lockout && !h.hot_run);
    h.rearm_wire_level(true, 100_022); // fresh HOT_REARM after blank
    h.arm_rising_edge(100_023);
    assert!(h.hot_ready && h.hot_run);
}

#[test]
fn held_rearm_high_through_blank_does_not_count_as_fresh_edge() {
    let mut h = BlankedHot::fault_locked(100_000);
    h.hot_fault_assert(10);
    h.hot_fault_recover(20);
    h.rearm_wire_level(true, 21); // stale pulse/high held across blank
    h.at(100_010);
    h.source_permit_and_arm(100_011);
    assert!(h.lockout && !h.hot_ready && !h.source_permit && !h.hot_run);
    h.rearm_wire_level(false, 100_020);
    h.rearm_wire_level(true, 100_030); // only post-blank edge can clear lockout
    assert!(h.hot_ready && !h.lockout);
}

#[test]
fn second_hot_fault_restarts_blank_and_dominates_rearm_clear() {
    let mut h = BlankedHot::fault_locked(100_000);
    h.hot_fault_assert(10);
    h.hot_fault_recover(20);
    h.rearm_wire_level(true, 30);
    h.rearm_wire_level(false, 40);
    h.hot_fault_assert(90_000); // a second fault while already locked out
    h.hot_fault_recover(90_010);
    h.at(100_010); // first interval elapsed, second has not
    h.rearm_wire_level(true, 100_011);
    assert!(h.lockout && !h.hot_ready && !h.hot_run);
    h.rearm_wire_level(false, 190_001);
    h.rearm_wire_level(true, 190_002);
    assert!(!h.lockout && h.hot_ready);
}

#[test]
fn brownout_requires_rails_good_blank_then_new_edge_even_with_arm_reconnected() {
    let mut h = BlankedHot::fault_locked(100_000);
    h.source_permit = true;
    h.hot_run = true;
    h.hot_brownout(10);
    h.source_observes_ready_low(11);
    h.hot_rails_recover(100);
    h.hot_fault_recover(101);
    h.rearm_wire_level(true, 102); // stale held ARM/rearm during startup blank
    h.source_permit_and_arm(200_101);
    assert!(!h.hot_ready && h.lockout && !h.source_permit && !h.hot_run);
    h.rearm_wire_level(false, 200_102);
    h.rearm_wire_level(true, 200_103);
    h.source_permit_and_arm(200_104);
    assert!(h.hot_ready && h.source_permit && h.hot_run);
}

#[test]
fn guard_fails_if_assumed_minimum_blank_is_shorter_than_stale_edge_latency() {
    // Negative control: no state machine can reject an edge that appears only
    // after its assumed blank has expired. This exposes the exact proof
    // obligation that must be discharged with the selected path and timer.
    let mut h = BlankedHot::fault_locked(10);
    h.hot_fault_assert(100);
    h.hot_fault_recover(101);
    h.at(111);
    h.rearm_wire_level(true, 112);
    assert!(h.hot_ready, "late edge is accepted when bound is violated");
}

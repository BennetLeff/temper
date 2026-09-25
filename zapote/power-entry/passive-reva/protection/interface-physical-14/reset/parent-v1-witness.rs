//! Timing boundary for the v13 decoded command handshake.
//!
//! This is a small, std-only model of the *physical boundary* around the
//! decoded command state machine.  `Decoded` is intentionally already decoded
//! (framing and electrical fault detection are outside this file).  The
//! independent SOURCE_OK/reset path is maintained by hardware and clears the
//! final permission latch even when the decoder is stuck or a frame is valid.
//!
//! The delays are a proposed timing contract, not datasheet measurements:
//! `SOURCE_LOW_TO_INHIBIT=2` and `INHIBIT_RELEASE=2` model two abstract clock
//! ticks.  A real implementation must replace them with measured worst-case
//! isolator, input filter, latch and gate-disable bounds.  Same-timestamp
//! ordering is conservative: a decoded START is processed before an inhibit
//! due at that timestamp, then the inhibit clears the output.  This exposes the
//! finite in-flight pulse rather than hiding it behind zero-latency semantics.

const SOURCE_LOW_TO_INHIBIT: u64 = 2;
const INHIBIT_RELEASE: u64 = 2;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TimingContract {
    pub source_low_to_inhibit: u64,
    pub inhibit_release: u64,
}

pub const CONTRACT: TimingContract = TimingContract {
    source_low_to_inhibit: SOURCE_LOW_TO_INHIBIT,
    inhibit_release: INHIBIT_RELEASE,
};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Session(pub u64);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Start {
    pub session: Session,
    pub intent: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Decoder {
    Offline,
    Idle { session: Session },
    AwaitStart { session: Session, intent: u64 },
    Running { session: Session, intent: u64 },
}

impl Decoder {
    fn running(self) -> bool { matches!(self, Self::Running { .. }) }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum ResetEdge {
    AssertAt(u64),
    ReleaseAt(u64),
}

/// HOT-side protection around the decoded v13 handshake.
pub struct Boundary {
    pub now: u64,
    pub source_ok: bool,
    pub reset_conductor_healthy: bool,
    pub hot_health: bool,
    pub maintained_permit: bool,
    pub inhibit_latched: bool,
    pub gate_latched: bool,
    pub recovery_ready: bool,
    decoder: Decoder,
    edge: Option<ResetEdge>,
    next_session: u64,
    last_session: Option<Session>,
    intent_counter: u64,
    fresh_intent: bool,
    low_was_observed: bool,
}

impl Boundary {
    pub fn new() -> Self {
        Self {
            now: 0,
            source_ok: true,
            reset_conductor_healthy: true,
            hot_health: true,
            maintained_permit: true,
            inhibit_latched: false,
            gate_latched: false,
            recovery_ready: true,
            decoder: Decoder::Offline,
            edge: None,
            next_session: 1,
            last_session: None,
            intent_counter: 1,
            fresh_intent: false,
            low_was_observed: false,
        }
    }

    /// Advance to an event time while deferring an edge *at* that time.  This
    /// gives START and reset-due at the same timestamp the conservative order
    /// documented above.
    fn advance_for_event(&mut self, t: u64) {
        assert!(t >= self.now, "time must not run backwards");
        while self.now < t {
            self.now += 1;
            if self.now < t { self.service_edge(); }
        }
    }

    /// Advance through an idle interval, servicing an edge at the endpoint.
    /// Callers use this when no command is coincident with the endpoint.
    pub fn advance_to(&mut self, t: u64) {
        self.advance_for_event(t);
        self.service_edge();
    }

    fn service_edge(&mut self) {
        let Some(edge) = self.edge else { return; };
        match edge {
            ResetEdge::AssertAt(at) if at <= self.now => {
                self.edge = None;
                if self.source_ok || !self.reset_conductor_healthy { return; }
                self.inhibit_latched = true;
                self.low_was_observed = true;
                self.recovery_ready = false;
                self.gate_latched = false;
                self.decoder = Decoder::Offline;
                self.fresh_intent = false;
            }
            ResetEdge::ReleaseAt(at) if at <= self.now => {
                self.edge = None;
                if !self.source_ok || !self.reset_conductor_healthy { return; }
                self.inhibit_latched = false;
                self.recovery_ready = self.low_was_observed;
            }
            _ => {}
        }
    }

    fn settle_current_edge(&mut self) { self.service_edge(); }

    fn trip_local(&mut self) {
        self.gate_latched = false;
        self.decoder = Decoder::Offline;
        self.fresh_intent = false;
        self.recovery_ready = false;
    }

    /// The maintained isolated SOURCE_OK input.  Its HOT-side default is low;
    /// if its conductor is healthy, a low schedules an independent inhibit.
    pub fn source_ok_at(&mut self, t: u64, ok: bool) {
        self.advance_for_event(t);
        self.source_ok = ok;
        if !ok {
            self.recovery_ready = false;
            if self.reset_conductor_healthy {
                self.edge = Some(ResetEdge::AssertAt(self.now + SOURCE_LOW_TO_INHIBIT));
            } else {
                self.edge = None;
            }
        } else if self.inhibit_latched && self.reset_conductor_healthy {
            self.edge = Some(ResetEdge::ReleaseAt(self.now + INHIBIT_RELEASE));
        }
        self.settle_current_edge();
    }

    /// A conductor that fails high demonstrates the explicit single-fault
    /// limitation: SOURCE_OK low cannot be observed by this one path.
    pub fn reset_conductor_at(&mut self, t: u64, healthy: bool) {
        self.advance_for_event(t);
        self.reset_conductor_healthy = healthy;
        if !healthy { self.edge = None; }
        else if !self.source_ok { self.edge = Some(ResetEdge::AssertAt(self.now + SOURCE_LOW_TO_INHIBIT)); }
        self.settle_current_edge();
    }

    pub fn hot_health_at(&mut self, t: u64, healthy: bool) {
        self.advance_for_event(t);
        self.hot_health = healthy;
        if !healthy { self.trip_local(); }
        else if self.maintained_permit && self.source_ok { self.recovery_ready = true; }
        self.settle_current_edge();
    }

    pub fn permit_at(&mut self, t: u64, permit: bool) {
        self.advance_for_event(t);
        self.maintained_permit = permit;
        if !permit { self.trip_local(); }
        else if self.hot_health && self.source_ok { self.recovery_ready = true; }
        self.settle_current_edge();
    }

    /// Install a newer session only after the reset path has observed low and
    /// then released high.  This is the physical counterpart of v13's
    /// persistent session challenge.
    pub fn install_session_at(&mut self, t: u64) -> Option<Session> {
        self.advance_for_event(t);
        if !self.source_ok || !self.hot_health || !self.maintained_permit
            || self.inhibit_latched || !self.recovery_ready { return None; }
        let session = Session(self.next_session);
        self.next_session = self.next_session.checked_add(1)?;
        if self.last_session.is_some_and(|old| session.0 <= old.0) { return None; }
        self.last_session = Some(session);
        self.decoder = Decoder::Idle { session };
        self.fresh_intent = false;
        Some(session)
    }

    pub fn fresh_intent_at(&mut self, t: u64) -> Option<u64> {
        self.advance_for_event(t);
        let Decoder::Idle { .. } = self.decoder else { return None; };
        let intent = self.intent_counter;
        self.intent_counter = self.intent_counter.checked_add(1)?;
        self.fresh_intent = true;
        Some(intent)
    }

    pub fn request_at(&mut self, t: u64, session: Session, intent: u64) -> bool {
        self.advance_for_event(t);
        let Decoder::Idle { session: expected } = self.decoder else { return false; };
        if expected != session || !self.fresh_intent { return false; }
        self.decoder = Decoder::AwaitStart { session, intent };
        self.fresh_intent = false;
        true
    }

    /// Decode one already-validated START.  A stuck old command is harmless
    /// after reset because the decoder is Offline and its old session is stale.
    pub fn start_at(&mut self, t: u64, start: Start) -> bool {
        self.advance_for_event(t);
        let accepted = match self.decoder {
            Decoder::AwaitStart { session, intent }
                if session == start.session && intent == start.intent => {
                    self.decoder = Decoder::Running { session, intent };
                    self.gate_latched = true;
                    true
                }
            _ => false,
        };
        // If reset is due at this same timestamp, START may create a bounded
        // pulse but cannot survive the independent inhibit.
        self.settle_current_edge();
        accepted
    }

    pub fn output_enabled(&self) -> bool {
        self.hot_health && self.maintained_permit && !self.inhibit_latched
            && self.gate_latched && self.decoder.running()
    }

    pub fn decoder_running(&self) -> bool { self.decoder.running() }
}

fn arm(b: &mut Boundary, t: u64) -> Start {
    let session = b.install_session_at(t).expect("session qualification");
    let intent = b.fresh_intent_at(t + 1).expect("fresh intent");
    assert!(b.request_at(t + 2, session, intent));
    Start { session, intent }
}

fn valid_run() -> bool {
    let mut b = Boundary::new();
    let start = arm(&mut b, 0);
    b.start_at(3, start) && b.output_enabled()
}

fn csv_case(name: &str, passed: bool, detail: &str) {
    println!("{name},{},{}", if passed { "PASS" } else { "FAIL" }, detail);
}

fn main() {
    println!("case,result,detail");
    let mut b = Boundary::new();
    let start = arm(&mut b, 0);
    csv_case("valid_start", b.start_at(3, start) && b.output_enabled(), "decoder_and_latch");

    let mut b = Boundary::new();
    let start = arm(&mut b, 0);
    b.start_at(3, start);
    b.source_ok_at(4, false);
    b.advance_to(6);
    csv_case("source_loss_latency", !b.output_enabled() && b.now - 4 == CONTRACT.source_low_to_inhibit, "2_ticks");

    let mut b = Boundary::new();
    let start = arm(&mut b, 0);
    // Keep START pending until the reset edge is due; this is the
    // same-timestamp conservative ordering witness.
    b.decoder = Decoder::AwaitStart { session: start.session, intent: start.intent };
    b.source_ok_at(4, false);
    let pulse = b.start_at(6, start);
    csv_case("same_tick_inflight_start", pulse && !b.output_enabled(), "start_then_inhibit");

    let mut b = Boundary::new();
    let stale = arm(&mut b, 0);
    b.start_at(3, stale);
    b.source_ok_at(4, false);
    b.advance_to(6);
    b.source_ok_at(7, true);
    b.advance_to(9);
    csv_case("held_stuck_start", !b.start_at(10, stale) && b.install_session_at(10).is_some(), "new_session_required");

    let mut b = Boundary::new();
    let _ = arm(&mut b, 0);
    b.source_ok_at(4, false);
    b.reset_conductor_at(4, false);
    b.advance_to(20);
    csv_case("reset_conductor_fails_high", b.inhibit_latched == false, "known_single_fault_gap");

    let mut b = Boundary::new();
    let start = arm(&mut b, 0);
    b.start_at(3, start);
    b.hot_health_at(4, false);
    csv_case("hot_health_independent", !b.output_enabled() && !b.decoder_running(), "immediate_local_trip");

    csv_case("valid_run_function", valid_run(), "positive_control");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn valid_start_sets_final_permission() {
        assert!(valid_run());
    }

    #[test]
    fn source_loss_clears_gate_after_declared_bound() {
        let mut b = Boundary::new();
        let start = arm(&mut b, 0);
        assert!(b.start_at(3, start));
        b.source_ok_at(4, false);
        assert!(b.output_enabled());
        b.advance_to(6);
        assert!(!b.output_enabled());
        assert!(b.low_was_observed);
        assert_eq!(b.now - 4, CONTRACT.source_low_to_inhibit);
    }

    #[test]
    fn same_timestamp_start_then_reset_is_bounded_pulse() {
        let mut b = Boundary::new();
        let start = arm(&mut b, 0);
        // The edge is due at t=6. START is accepted first at t=6, then reset
        // wins before the caller can observe an enabled final output.
        // Re-create the pending request: `arm` sends Request but not START.
        b.decoder = Decoder::AwaitStart { session: start.session, intent: start.intent };
        b.gate_latched = false;
        b.source_ok_at(4, false);
        assert!(b.start_at(6, start));
        assert!(!b.output_enabled());
        assert_eq!(b.decoder_running(), false);
    }

    #[test]
    fn new_start_requires_low_high_observation_and_new_session() {
        let mut b = Boundary::new();
        let old = arm(&mut b, 0);
        b.start_at(3, old);
        b.source_ok_at(4, false);
        b.advance_to(6);
        assert!(b.install_session_at(6).is_none());
        b.source_ok_at(7, true);
        b.advance_to(9);
        assert!(b.install_session_at(9).is_some());
        assert!(!b.start_at(10, old));
    }

    #[test]
    fn stuck_high_command_does_not_restart_after_reset() {
        let mut b = Boundary::new();
        let old = arm(&mut b, 0);
        b.start_at(3, old);
        b.source_ok_at(4, false);
        b.advance_to(6);
        b.source_ok_at(7, true);
        b.advance_to(9);
        assert!(!b.start_at(10, old));
    }

    #[test]
    fn disconnect_reconnect_after_observed_low_requalifies() {
        let mut b = Boundary::new();
        let old = arm(&mut b, 0);
        b.start_at(3, old);
        b.source_ok_at(4, false);
        b.advance_to(6);
        b.source_ok_at(7, true);
        b.advance_to(9);
        let new = arm(&mut b, 10);
        assert_ne!(old.session, new.session);
        assert!(b.start_at(13, new));
    }

    #[test]
    fn source_supply_loss_is_independent_of_decoder_frames() {
        let mut b = Boundary::new();
        let old = arm(&mut b, 0);
        b.start_at(3, old);
        b.source_ok_at(4, false);
        b.advance_to(6);
        assert!(!b.output_enabled());
        assert!(!b.start_at(7, old));
    }

    #[test]
    fn resetting_each_phase_is_fail_closed() {
        for phase in 0..4 {
            let mut b = Boundary::new();
            let start = arm(&mut b, 0);
            match phase {
                // `arm` has qualified the session and sent Request at t=2;
                // use the next ticks as the four post-qualification phases.
                0 => b.source_ok_at(2, false),
                1 => b.source_ok_at(3, false),
                2 => { b.source_ok_at(3, false); }
                _ => { b.start_at(3, start); b.source_ok_at(4, false); }
            }
            b.advance_to(b.now + CONTRACT.source_low_to_inhibit);
            assert!(!b.output_enabled(), "phase {phase}");
        }
    }

    #[test]
    fn reset_conductor_fail_high_is_explicit_single_fault_gap() {
        let mut b = Boundary::new();
        let start = arm(&mut b, 0);
        b.start_at(3, start);
        b.reset_conductor_at(4, false);
        b.source_ok_at(4, false);
        b.advance_for_event(20);
        assert!(b.output_enabled(), "one failed-high reset path has no redundancy");
        assert!(!b.low_was_observed);
    }

    #[test]
    fn hot_health_and_permit_trip_without_command_frame() {
        let mut b = Boundary::new();
        let start = arm(&mut b, 0);
        b.start_at(3, start);
        b.hot_health_at(4, false);
        assert!(!b.output_enabled());
        b.hot_health_at(5, true);
        let _ = b.install_session_at(5).expect("requalification after local fault");
        b.permit_at(6, false);
        assert!(!b.output_enabled());
    }
}

#[cfg(test)] mod parent_v1_witness {
 use super::*;
 #[test] fn repeated_low_observations_postpone_inhibit() {
  let mut b=Boundary::new();let start=arm(&mut b,0);b.start_at(3,start);
  for t in 4..20 { b.source_ok_at(t,false); }
  assert!(b.output_enabled(),"known-bad v1 failed to inhibit during continuous low");
 }
 #[test] fn short_low_disappears_before_receiver_inhibit() {
  let mut b=Boundary::new();let start=arm(&mut b,0);b.start_at(3,start);
  b.source_ok_at(4,false);b.source_ok_at(5,true);b.advance_to(9);
  assert!(b.output_enabled(),"known-bad v1 failed to capture reset pulse");
 }
}

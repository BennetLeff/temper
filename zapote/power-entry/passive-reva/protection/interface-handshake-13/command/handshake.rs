//! Logical two-endpoint command handshake.
//!
//! This model deliberately starts after a transport decoder.  A GPIO wire,
//! isolator, UART, or framing codec must provide the frame observations; this
//! file does not claim to model their voltage, timing, metastability, or loss.
use std::fmt;

const IDLE_SAMPLES: u8 = 2;
const HANDSHAKE_TICKS: u8 = 8;
const NONCE_SALT: u64 = 0x9e37_79b9_7f4a_7c15;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Session {
    number: u64,
    nonce: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct PersistentCounter {
    next: u64,
}

impl PersistentCounter {
    fn new(next: u64) -> Self { Self { next } }

    fn allocate(&mut self) -> Option<Session> {
        if self.next == 0 || self.next == u64::MAX {
            return None;
        }
        let number = self.next;
        self.next = self.next.checked_add(1)?;
        Some(Session { number, nonce: nonce(number) })
    }
}

fn nonce(number: u64) -> u64 {
    let mut x = number ^ NONCE_SALT;
    x ^= x >> 30;
    x = x.wrapping_mul(0xbf58_476d_1ce4_e5b9);
    x ^= x >> 27;
    x = x.wrapping_mul(0x94d0_49bb_1331_11eb);
    x ^ (x >> 31)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Frame {
    Challenge { session: Session },
    Request { session: Session, intent: u64 },
    Ack { session: Session, intent: u64 },
    Start { session: Session, intent: u64 },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum ReceiverState {
    Offline,
    Qualifying { samples: u8 },
    Idle,
    AwaitStart { intent: u64 },
    Running { intent: u64 },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum SourceState {
    Reset,
    ChallengeKnown { session: Session },
    IntentReady { session: Session, intent: u64 },
    Requested { session: Session, intent: u64 },
    StartSent { session: Session, intent: u64 },
    Running { session: Session, intent: u64 },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum BootError { CounterExhausted }

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Reject {
    Offline,
    PermitLow,
    Unhealthy,
    StaleSession,
    NotIdle,
    InvalidOrder,
    Duplicate,
    Deadline,
}

impl fmt::Display for Reject {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}

struct Receiver {
    state: ReceiverState,
    session: Option<Session>,
    counter: PersistentCounter,
    deadline: Option<u8>,
}

impl Receiver {
    fn new(counter: PersistentCounter) -> Self {
        Self { state: ReceiverState::Offline, session: None, counter, deadline: None }
    }

    fn invalidate(&mut self) {
        self.state = ReceiverState::Offline;
        self.session = None;
        self.deadline = None;
    }

    /// A decoder/link fault is an independent reset event; it does not wait for a frame.
    fn link_fault(&mut self) { self.invalidate(); }

    /// Hardware/health observers call this even when no transport frame arrives.
    fn observe_inputs(&mut self, permit: bool, healthy: bool) -> Result<(), Reject> {
        if !permit { self.invalidate(); return Err(Reject::PermitLow); }
        if !healthy { self.invalidate(); return Err(Reject::Unhealthy); }
        Ok(())
    }

    fn boot(&mut self) -> Result<Frame, BootError> {
        let session = match self.counter.allocate() {
            Some(session) => session,
            None => {
                self.invalidate();
                return Err(BootError::CounterExhausted);
            }
        };
        self.session = Some(session);
        self.state = ReceiverState::Qualifying { samples: 0 };
        self.deadline = Some(HANDSHAKE_TICKS);
        Ok(Frame::Challenge { session })
    }

    #[cfg(test)]
    fn replay_challenge(&self) -> Option<Frame> {
        self.session.map(|session| Frame::Challenge { session })
    }

    /// PERMIT is a separate maintained hardware permission and dominates all frames.
    #[cfg(test)]
    fn permit_reset(&mut self) -> Result<Frame, BootError> {
        self.invalidate();
        self.boot()
    }

    #[cfg(test)]
    fn health_reset(&mut self) -> Result<Frame, BootError> {
        self.invalidate();
        self.boot()
    }

    fn idle_sample(&mut self, permit: bool, healthy: bool) {
        if self.observe_inputs(permit, healthy).is_err() { return; }
        if let ReceiverState::Qualifying { samples } = self.state {
            let samples = samples.saturating_add(1);
            self.state = if samples >= IDLE_SAMPLES {
                ReceiverState::Idle
            } else {
                ReceiverState::Qualifying { samples }
            };
        }
    }

    fn tick(&mut self) -> Result<(), Reject> {
        if matches!(self.state, ReceiverState::Running { .. }) { return Ok(()); }
        let Some(deadline) = self.deadline else { return Err(Reject::Offline); };
        if deadline <= 1 { self.invalidate(); return Err(Reject::Deadline); }
        self.deadline = Some(deadline - 1);
        Ok(())
    }

    fn on_frame(&mut self, frame: Frame, permit: bool, healthy: bool) -> Result<Option<Frame>, Reject> {
        self.observe_inputs(permit, healthy)?;
        let current = self.session.ok_or(Reject::Offline)?;
        match frame {
            Frame::Request { session, intent } => {
                if session != current { return Err(Reject::StaleSession); }
                match self.state {
                    ReceiverState::Idle => {
                        self.state = ReceiverState::AwaitStart { intent };
                        Ok(Some(Frame::Ack { session: current, intent }))
                    }
                    ReceiverState::AwaitStart { intent: old } if old == intent => {
                        Ok(Some(Frame::Ack { session: current, intent }))
                    }
                    ReceiverState::AwaitStart { .. } | ReceiverState::Running { .. } => Err(Reject::Duplicate),
                    _ => Err(Reject::NotIdle),
                }
            }
            Frame::Start { session, intent } => {
                if session != current { return Err(Reject::StaleSession); }
                match self.state {
                    ReceiverState::AwaitStart { intent: expected } if expected == intent => {
                        self.state = ReceiverState::Running { intent };
                        self.deadline = None;
                        Ok(None)
                    }
                    ReceiverState::Running { intent: running } if running == intent => Err(Reject::Duplicate),
                    _ => Err(Reject::InvalidOrder),
                }
            }
            Frame::Ack { .. } | Frame::Challenge { .. } => Err(Reject::InvalidOrder),
        }
    }

    fn running(&self) -> bool { matches!(self.state, ReceiverState::Running { .. }) }
}

struct Source {
    state: SourceState,
    next_intent: u64,
    last_session: Option<Session>,
}

impl Source {
    fn new() -> Self { Self { state: SourceState::Reset, next_intent: 1, last_session: None } }

    /// A fresh local intent is an event; a held GPIO level is never accepted as one.
    fn fresh_start_intent(&mut self) -> bool {
        let SourceState::ChallengeKnown { session } = self.state else { return false; };
        let intent = self.next_intent;
        self.next_intent = match self.next_intent.checked_add(1) { Some(next) => next, None => return false };
        self.state = SourceState::IntentReady { session, intent };
        true
    }

    fn on_challenge(&mut self, frame: Frame) -> Option<Frame> {
        let Frame::Challenge { session } = frame else { return None; };
        if !matches!(self.state, SourceState::Reset) { return None; }
        if self.last_session.is_some_and(|old| session.number <= old.number) { return None; }
        self.last_session = Some(session);
        self.state = SourceState::ChallengeKnown { session };
        None
    }

    fn request_after_intent(&mut self) -> Option<Frame> {
        let SourceState::IntentReady { session, intent } = self.state else { return None; };
        self.state = SourceState::Requested { session, intent };
        Some(Frame::Request { session, intent })
    }

    #[cfg(test)]
    fn retry_request(&self) -> Option<Frame> {
        match self.state {
            SourceState::Requested { session, intent } => Some(Frame::Request { session, intent }),
            _ => None,
        }
    }

    fn on_ack(&mut self, frame: Frame) -> Option<Frame> {
        let Frame::Ack { session, intent } = frame else { return None; };
        let SourceState::Requested { session: expected, intent: wanted } = self.state else { return None; };
        if session != expected || intent != wanted { return None; }
        self.state = SourceState::StartSent { session, intent };
        Some(Frame::Start { session, intent })
    }

    fn mark_running(&mut self) {
        if let SourceState::StartSent { session, intent } = self.state { self.state = SourceState::Running { session, intent }; }
    }

    fn reset(&mut self) { self.state = SourceState::Reset; }

    fn timeout(&mut self) { self.reset(); }
}

fn run_valid() -> bool {
    let mut receiver = Receiver::new(PersistentCounter::new(1));
    let mut source = Source::new();
    let challenge = receiver.boot().expect("counter available");
    receiver.idle_sample(true, true);
    receiver.idle_sample(true, true);
    assert!(source.on_challenge(challenge).is_none());
    assert!(source.fresh_start_intent());
    let request = source.request_after_intent().expect("request");
    let ack = receiver.on_frame(request, true, true).expect("request accepted").expect("ack");
    let start = source.on_ack(ack).expect("ack accepted");
    assert!(receiver.on_frame(start, true, true).is_ok());
    source.mark_running();
    receiver.running() && matches!(source.state, SourceState::Running { .. })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn setup() -> (Receiver, Source, Frame) {
        let mut receiver = Receiver::new(PersistentCounter::new(1));
        let challenge = receiver.boot().unwrap();
        receiver.idle_sample(true, true);
        receiver.idle_sample(true, true);
        let source = Source::new();
        (receiver, source, challenge)
    }

    fn request(source: &mut Source, challenge: Frame) -> Frame {
        assert!(source.on_challenge(challenge).is_none());
        assert!(source.fresh_start_intent());
        source.request_after_intent().unwrap()
    }

    #[test]
    fn valid_run_requires_fresh_intent_and_challenge_ack() { assert!(run_valid()); }

    #[test]
    fn held_request_after_receiver_reset_is_stale() {
        let (mut receiver, mut source, challenge) = setup();
        let req = request(&mut source, challenge);
        let _ack = receiver.on_frame(req, true, true).unwrap().unwrap();
        let _new_challenge = receiver.permit_reset().unwrap();
        assert_eq!(receiver.on_frame(req, true, true), Err(Reject::StaleSession));
    }

    #[test]
    fn stale_frames_are_rejected_before_request_ack_and_start() {
        let (mut receiver, mut source, challenge) = setup();
        let request = request(&mut source, challenge);
        let old = receiver.session.unwrap();
        let stale = Frame::Request { session: Session { number: old.number - 1, nonce: nonce(old.number - 1) }, intent: 99 };
        assert_eq!(receiver.on_frame(stale, true, true), Err(Reject::StaleSession));
        let ack = receiver.on_frame(request, true, true).unwrap().unwrap();
        let forged = Frame::Start { session: old, intent: 999 };
        assert_eq!(receiver.on_frame(forged, true, true), Err(Reject::InvalidOrder));
        let start = source.on_ack(ack).unwrap();
        assert!(receiver.on_frame(start, true, true).is_ok());
    }

    #[test]
    fn lost_ack_can_be_retried_without_new_intent() {
        let (mut receiver, mut source, challenge) = setup();
        let request = request(&mut source, challenge);
        let _lost = receiver.on_frame(request, true, true).unwrap();
        let retry = source.retry_request().unwrap();
        let ack = receiver.on_frame(retry, true, true).unwrap().unwrap();
        let start = source.on_ack(ack).unwrap();
        assert!(receiver.on_frame(start, true, true).is_ok());
    }

    #[test]
    fn deadline_rejects_delayed_start_and_duplicate_does_not_refresh() {
        let (mut receiver, mut source, challenge) = setup();
        let req = request(&mut source, challenge);
        let ack = receiver.on_frame(req, true, true).unwrap().unwrap();
        let start = source.on_ack(ack).unwrap();
        for _ in 0..HANDSHAKE_TICKS - 1 { assert!(receiver.tick().is_ok()); }
        assert_eq!(receiver.tick(), Err(Reject::Deadline));
        assert_eq!(receiver.on_frame(start, true, true), Err(Reject::Offline));

        let (mut receiver, mut source, challenge) = setup();
        let req = request(&mut source, challenge);
        let _ack = receiver.on_frame(req, true, true).unwrap().unwrap();
        for _ in 0..HANDSHAKE_TICKS - 2 { assert!(receiver.tick().is_ok()); }
        assert!(receiver.on_frame(req, true, true).is_ok());
        assert!(receiver.tick().is_ok());
        assert_eq!(receiver.tick(), Err(Reject::Deadline));
    }

    #[test]
    fn lost_challenge_can_be_replayed_without_new_session() {
        let (receiver, mut source, _lost_challenge) = setup();
        let challenge = receiver.replay_challenge().unwrap();
        assert!(source.on_challenge(challenge).is_none());
        assert!(source.fresh_start_intent());
        assert!(source.request_after_intent().is_some());
    }

    #[test]
    fn invalid_orders_duplicates_and_fault_reset_fail_closed() {
        let (mut receiver, mut source, challenge) = setup();
        let old = receiver.session.unwrap();
        let start_first = Frame::Start { session: old, intent: 1 };
        assert_eq!(receiver.on_frame(start_first, true, true), Err(Reject::InvalidOrder));
        let request = request(&mut source, challenge);
        let ack = receiver.on_frame(request, true, true).unwrap().unwrap();
        assert_eq!(receiver.on_frame(request, true, true), Ok(Some(ack)));
        let start = source.on_ack(ack).unwrap();
        assert!(receiver.on_frame(start, true, true).is_ok());
        assert!(receiver.running());
        assert_eq!(receiver.on_frame(start, false, true), Err(Reject::PermitLow));
        assert!(!receiver.running());
    }

    #[test]
    fn stale_ack_and_start_cannot_cross_sessions() {
        let (mut receiver, mut source, challenge) = setup();
        let request = request(&mut source, challenge);
        let ack = receiver.on_frame(request, true, true).unwrap().unwrap();
        let _new = receiver.permit_reset().unwrap();
        assert!(source.on_ack(ack).is_some(), "source may emit old start; receiver must reject it");
        let old_start = source.on_ack(ack).unwrap_or(Frame::Start { session: Session { number: 1, nonce: nonce(1) }, intent: 1 });
        assert_eq!(receiver.on_frame(old_start, true, true), Err(Reject::StaleSession));
    }

    #[test]
    fn source_reset_requires_new_intent() {
        let (receiver, mut source, challenge) = setup();
        let _ = request(&mut source, challenge);
        source.reset();
        assert!(source.on_challenge(challenge).is_none());
        assert!(!receiver.running());
        assert!(!source.fresh_start_intent());
    }

    #[test]
    fn source_timeout_cancels_pending_start_without_reusing_intent() {
        let (mut receiver, mut source, challenge) = setup();
        let req = request(&mut source, challenge);
        let _ack = receiver.on_frame(req, true, true).unwrap().unwrap();
        source.timeout();
        assert!(source.retry_request().is_none());
        assert!(!source.fresh_start_intent());
    }

    #[test]
    fn health_reset_invalidates_request_and_requires_new_session() {
        let (mut receiver, mut source, challenge) = setup();
        let request = request(&mut source, challenge);
        assert_eq!(receiver.on_frame(request, true, false), Err(Reject::Unhealthy));
        let new_challenge = receiver.health_reset().unwrap();
        assert_ne!(challenge, new_challenge);
        assert_eq!(receiver.on_frame(request, true, true), Err(Reject::StaleSession));
    }

    #[test]
    fn stale_challenge_and_ack_are_ignored_without_fresh_intent() {
        let (mut receiver, mut source, challenge) = setup();
        let old_session = match challenge { Frame::Challenge { session } => session, _ => unreachable!() };
        assert!(source.on_challenge(challenge).is_none());
        let _new_challenge = receiver.permit_reset().unwrap();
        source.reset();
        assert!(source.on_challenge(challenge).is_none());
        assert!(source.on_challenge(_new_challenge).is_none());
        assert!(source.fresh_start_intent());
        let _fresh = source.request_after_intent().unwrap();
        let stale_ack = Frame::Ack { session: old_session, intent: 1 };
        assert!(source.on_ack(stale_ack).is_none());
    }

    #[test]
    fn counter_never_wraps_and_locks_closed() {
        let mut receiver = Receiver::new(PersistentCounter::new(u64::MAX - 1));
        assert!(receiver.boot().is_ok());
        assert_eq!(receiver.boot(), Err(BootError::CounterExhausted));
        let mut exhausted = Receiver::new(PersistentCounter::new(u64::MAX));
        assert_eq!(exhausted.boot(), Err(BootError::CounterExhausted));
    }

    #[test]
    fn permit_low_is_dominant_even_for_valid_frame() {
        let (mut receiver, mut source, challenge) = setup();
        let request = request(&mut source, challenge);
        assert_eq!(receiver.on_frame(request, false, true), Err(Reject::PermitLow));
        assert!(!receiver.running());
    }

    #[test]
    fn permit_fault_then_requalification_rejects_old_request_and_start() {
        let (mut receiver, mut source, challenge) = setup();
        let req = request(&mut source, challenge);
        let ack = receiver.on_frame(req, true, true).unwrap().unwrap();
        let start = source.on_ack(ack).unwrap();
        assert_eq!(receiver.on_frame(start, false, true), Err(Reject::PermitLow));
        let new_challenge = receiver.boot().unwrap();
        receiver.idle_sample(true, true);
        receiver.idle_sample(true, true);
        assert_eq!(receiver.on_frame(req, true, true), Err(Reject::StaleSession));
        assert_eq!(receiver.on_frame(start, true, true), Err(Reject::StaleSession));
        assert_ne!(new_challenge, challenge);
    }

    #[test]
    fn link_fault_event_invalidates_without_waiting_for_traffic() {
        let (mut receiver, mut source, challenge) = setup();
        let req = request(&mut source, challenge);
        assert!(receiver.on_frame(req, true, true).is_ok());
        receiver.link_fault();
        assert_eq!(receiver.on_frame(req, true, true), Err(Reject::Offline));
    }

    #[test]
    fn permit_or_health_observer_clears_running_without_a_frame() {
        let (mut receiver, mut source, challenge) = setup();
        let req = request(&mut source, challenge);
        let ack = receiver.on_frame(req, true, true).unwrap().unwrap();
        let start = source.on_ack(ack).unwrap();
        receiver.on_frame(start, true, true).unwrap();
        assert!(receiver.running());
        assert_eq!(receiver.observe_inputs(false, true), Err(Reject::PermitLow));
        assert!(!receiver.running());

        let new_challenge = receiver.boot().unwrap();
        receiver.idle_sample(true, true);
        receiver.idle_sample(true, true);
        source.reset();
        let req = request(&mut source, new_challenge);
        let ack = receiver.on_frame(req, true, true).unwrap().unwrap();
        let start = source.on_ack(ack).unwrap();
        receiver.on_frame(start, true, true).unwrap();
        assert_eq!(receiver.observe_inputs(true, false), Err(Reject::Unhealthy));
        assert!(!receiver.running());
    }
}

fn main() {
    println!("case,result");
    println!("valid_run,{}", run_valid());
}

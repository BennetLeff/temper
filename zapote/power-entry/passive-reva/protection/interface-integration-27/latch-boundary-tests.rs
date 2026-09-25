// Append this file to the frozen Rev13 handshake.rs before compiling with
// rustc --test. The fixture models only Rev11 U62's first DFF and U68's final
// RUN AND clear_ok gate; it is not an electrical or timing simulation.

#[derive(Default)]
struct Rev11LatchBoundary {
    run: bool,
}

impl Rev11LatchBoundary {
    fn observe(&mut self, clear_ok: bool, arm_rising_edge: bool) -> bool {
        if !clear_ok {
            self.run = false;
        } else if arm_rising_edge {
            self.run = true;
        }
        self.run && clear_ok
    }
}

fn accepted_start_receiver() -> Receiver {
    let mut receiver = Receiver::new(PersistentCounter::new(1));
    let mut source = Source::new();
    let challenge = receiver.boot().expect("fresh session");
    receiver.idle_sample(true, true);
    receiver.idle_sample(true, true);
    assert!(source.on_challenge(challenge).is_none());
    assert!(source.fresh_start_intent());
    let request = source.request_after_intent().expect("fresh request");
    let ack = receiver
        .on_frame(request, true, true)
        .expect("request accepted")
        .expect("acknowledgement");
    let start = source.on_ack(ack).expect("matching START");
    receiver
        .on_frame(start, true, true)
        .expect("START accepted");
    assert!(receiver.running());
    receiver
}

#[test]
fn link_fault_clears_receiver_state_but_not_an_ungated_rev11_latch() {
    let mut receiver = accepted_start_receiver();
    let mut latch = Rev11LatchBoundary::default();
    assert!(latch.observe(true, true), "validated ARM edge set RUN");

    receiver.link_fault();
    assert!(!receiver.running(), "Rev13 invalidates its logical RUN");
    assert!(
        latch.observe(true, false),
        "Rev11 still enables when clear_ok stays high and ARM simply goes low"
    );
}

#[test]
fn a_real_clear_ok_low_clears_the_rev11_latch() {
    let mut receiver = accepted_start_receiver();
    let mut latch = Rev11LatchBoundary::default();
    assert!(latch.observe(true, true));

    receiver.link_fault();
    assert!(!receiver.running());
    assert!(!latch.observe(false, false), "fault must reach clear_ok");
    assert!(
        !latch.observe(true, false),
        "recovery alone must not restart"
    );
}

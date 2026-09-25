// Append to frozen interface-handshake-13/command/handshake.rs and compile
// with rustc --test. This is a discrete logical boundary model only: it does
// not model electrical levels, propagation, analog behavior, or real timing.

#[derive(Debug, Clone, Copy)]
struct BoundaryInputs {
    permit_wire: bool,
    link_healthy: bool,
    source_healthy: bool,
}

impl BoundaryInputs {
    fn maintained_permission(self) -> bool {
        self.permit_wire && self.link_healthy && self.source_healthy
    }
}

#[derive(Default)]
struct Rev11LatchBoundary {
    run: bool,
    prior_arm: bool,
}

impl Rev11LatchBoundary {
    fn observe(&mut self, clear_ok: bool, arm: bool) -> bool {
        if !clear_ok {
            self.run = false;
        } else if arm && !self.prior_arm {
            self.run = true;
        }
        self.prior_arm = arm;
        self.run && clear_ok
    }
}

struct CommandAdapter {
    inputs: BoundaryInputs,
    arm_ticks_left: u8,
    arm_pulse_bound_ticks: u8,
    latch: Rev11LatchBoundary,
}

impl CommandAdapter {
    fn new(arm_pulse_bound_ticks: u8) -> Self {
        assert!(arm_pulse_bound_ticks > 0);
        Self {
            inputs: BoundaryInputs {
                permit_wire: false,
                link_healthy: false,
                source_healthy: false,
            },
            arm_ticks_left: 0,
            arm_pulse_bound_ticks,
            latch: Rev11LatchBoundary::default(),
        }
    }

    fn arm(&self) -> bool {
        self.arm_ticks_left > 0
    }

    fn permission(&self) -> bool {
        self.inputs.maintained_permission()
    }

    fn observe(&mut self) -> bool {
        self.latch.observe(self.permission(), self.arm())
    }

    fn set_inputs(&mut self, inputs: BoundaryInputs, receiver: &mut Receiver) {
        self.inputs = inputs;
        if !self.permission() {
            self.arm_ticks_left = 0;
            receiver.link_fault();
        }
        self.observe();
    }

    fn receiver_reset(&mut self, receiver: &mut Receiver) {
        // The reset indication is assumed to reach this logical boundary.
        // Physical detection and propagation time are outside this model.
        receiver.link_fault();
        self.inputs.source_healthy = false;
        self.arm_ticks_left = 0;
        self.observe();
    }

    fn source_reset(&mut self, receiver: &mut Receiver) {
        // Models the source-reset indication after it reaches the adapter.
        // It does not model when or how hardware detects that indication.
        receiver.link_fault();
        self.inputs.source_healthy = false;
        self.arm_ticks_left = 0;
        self.observe();
    }

    fn receive(&mut self, receiver: &mut Receiver, frame: Frame) -> Result<Option<Frame>, Reject> {
        let permission = self.permission();
        let result = receiver.on_frame(frame, permission, self.inputs.source_healthy);
        if !permission || !self.inputs.link_healthy || !self.inputs.source_healthy {
            self.arm_ticks_left = 0;
            self.observe();
            return result;
        }
        if matches!(frame, Frame::Start { .. }) && result.is_ok() {
            self.arm_ticks_left = self.arm_pulse_bound_ticks;
        }
        self.observe();
        result
    }

    fn tick(&mut self) {
        if self.arm_ticks_left > 0 {
            self.arm_ticks_left -= 1;
        }
        self.observe();
    }
}

fn adapter_ready_receiver() -> (CommandAdapter, Receiver, Source, Frame) {
    let mut receiver = Receiver::new(PersistentCounter::new(1));
    let mut adapter = CommandAdapter::new(1);
    adapter.set_inputs(
        BoundaryInputs {
            permit_wire: true,
            link_healthy: true,
            source_healthy: true,
        },
        &mut receiver,
    );
    let challenge = receiver.boot().expect("counter available");
    receiver.idle_sample(adapter.permission(), true);
    receiver.idle_sample(adapter.permission(), true);
    let source = Source::new();
    (adapter, receiver, source, challenge)
}

fn accepted_arm(
    adapter: &mut CommandAdapter,
    receiver: &mut Receiver,
    source: &mut Source,
    challenge: Frame,
) {
    assert!(source.on_challenge(challenge).is_none());
    assert!(source.fresh_start_intent());
    let request = source.request_after_intent().expect("fresh request");
    let ack = adapter
        .receive(receiver, request)
        .expect("request accepted")
        .expect("ack");
    let start = source.on_ack(ack).expect("matched ACK");
    adapter.receive(receiver, start).expect("START accepted");
}

#[test]
fn accepted_start_generates_one_bounded_low_idle_arm_pulse() {
    let (mut adapter, mut receiver, mut source, challenge) = adapter_ready_receiver();
    accepted_arm(&mut adapter, &mut receiver, &mut source, challenge);
    assert!(adapter.arm(), "accepted START asserts ARM");
    assert!(adapter.latch.run, "ARM edge sets the modeled RUN latch");
    adapter.tick();
    assert!(!adapter.arm(), "pulse returns low at its configured bound");
    assert!(
        adapter.latch.run,
        "latched RUN remains after ARM returns low"
    );
    adapter.tick();
    assert!(!adapter.arm(), "idle remains low on later ticks");
}

#[test]
fn link_fault_drops_permission_and_clears_latch_even_when_permit_wire_is_stuck_high() {
    let (mut adapter, mut receiver, mut source, challenge) = adapter_ready_receiver();
    accepted_arm(&mut adapter, &mut receiver, &mut source, challenge);
    assert!(adapter.latch.run);

    adapter.set_inputs(
        BoundaryInputs {
            permit_wire: true, // stuck-high conductor
            link_healthy: false,
            source_healthy: true,
        },
        &mut receiver,
    );
    assert!(
        !adapter.permission(),
        "independent link-health term dominates stuck-high PERMIT"
    );
    assert!(
        !adapter.latch.run,
        "maintained permission loss asserts modeled clear"
    );
    assert!(
        !receiver.running(),
        "fault invalidates the Rev13 logical session"
    );

    adapter.set_inputs(
        BoundaryInputs {
            permit_wire: true,
            link_healthy: true,
            source_healthy: true,
        },
        &mut receiver,
    );
    assert!(
        !adapter.latch.run,
        "permission recovery alone cannot restart RUN"
    );
}

#[test]
fn receiver_reset_drops_arm_and_permission_and_cannot_be_undone_by_permit_recovery() {
    let (mut adapter, mut receiver, mut source, challenge) = adapter_ready_receiver();
    accepted_arm(&mut adapter, &mut receiver, &mut source, challenge);
    assert!(adapter.arm());
    assert!(adapter.latch.run);

    adapter.receiver_reset(&mut receiver);
    assert!(!adapter.arm());
    assert!(!adapter.permission());
    assert!(!adapter.latch.run);
    assert!(!receiver.running());

    adapter.inputs.source_healthy = true;
    adapter.observe();
    assert!(adapter.permission());
    assert!(
        !adapter.latch.run,
        "reset recovery by itself is not a new START"
    );
}

#[test]
fn in_flight_start_after_source_reset_is_rejected_once_reset_reaches_boundary() {
    let (mut adapter, mut receiver, mut source, challenge) = adapter_ready_receiver();
    assert!(source.on_challenge(challenge).is_none());
    assert!(source.fresh_start_intent());
    let request = source.request_after_intent().unwrap();
    let ack = adapter.receive(&mut receiver, request).unwrap().unwrap();
    let in_flight_start = source.on_ack(ack).unwrap();
    assert!(matches!(receiver.state, ReceiverState::AwaitStart { .. }));

    adapter.source_reset(&mut receiver);
    assert_eq!(
        adapter.receive(&mut receiver, in_flight_start),
        Err(Reject::PermitLow)
    );
    assert!(!adapter.arm());
    assert!(!adapter.latch.run);
    assert!(!receiver.running());
}

#[test]
fn source_health_loss_blocks_a_start_even_with_a_valid_permit_wire() {
    let (mut adapter, mut receiver, mut source, challenge) = adapter_ready_receiver();
    assert!(source.on_challenge(challenge).is_none());
    assert!(source.fresh_start_intent());
    let request = source.request_after_intent().unwrap();
    let ack = adapter.receive(&mut receiver, request).unwrap().unwrap();
    let start = source.on_ack(ack).unwrap();

    adapter.set_inputs(
        BoundaryInputs {
            permit_wire: true,
            link_healthy: true,
            source_healthy: false,
        },
        &mut receiver,
    );
    assert_eq!(
        adapter.receive(&mut receiver, start),
        Err(Reject::PermitLow)
    );
    assert!(!adapter.permission());
    assert!(!adapter.arm());
    assert!(!adapter.latch.run);
}

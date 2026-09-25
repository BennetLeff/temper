//! Event model for a dedicated HOT permit-blanking supervisor.
//! The first test is a negative control without HOT permit readback; the
//! compiled Rev37 fixture has that readback. This checks authorization event
//! ordering, not analog timing or a PCB.

const BLANK_MS: u64 = 229;

#[derive(Debug)]
struct Receiver {
    now_ms: u64,
    blank_until_ms: u64,
    source_permit: bool,
    hot_permit: bool,
    raw_hot_health: bool,
    hot_ready: bool,
    run: bool,
    rearm_high: bool,
    arm_high: bool,
}

impl Receiver {
    fn running() -> Self {
        Self {
            now_ms: 0,
            blank_until_ms: 0,
            source_permit: true,
            hot_permit: true,
            raw_hot_health: true,
            hot_ready: true,
            run: true,
            rearm_high: false,
            arm_high: true,
        }
    }

    fn at(&mut self, now_ms: u64) {
        assert!(now_ms >= self.now_ms);
        self.now_ms = now_ms;
    }

    fn hot_permit_wire(&mut self, high: bool) {
        self.hot_permit = high;
        if !high {
            // MR stays low for the entire open interval. Q1/Q2 clear.
            self.blank_until_ms = self.now_ms + BLANK_MS;
            self.hot_ready = false;
            self.run = false;
        } else {
            // CT starts on MR release, regardless of source knowledge.
            self.blank_until_ms = self.now_ms + BLANK_MS;
        }
    }

    fn rearm_wire(&mut self, high: bool) {
        let rising = high && !self.rearm_high;
        self.rearm_high = high;
        if rising && self.hot_permit && self.now_ms >= self.blank_until_ms {
            self.hot_ready = true;
        }
    }

    fn arm_wire(&mut self, high: bool) {
        let rising = high && !self.arm_high;
        self.arm_high = high;
        if rising && self.hot_permit && self.hot_ready {
            self.run = true;
        }
    }

    fn source_observes_raw_health(&mut self) {
        if !self.raw_hot_health {
            self.source_permit = false;
        }
    }

    fn source_observes_latched_permit_loss(&mut self) {
        // Assumes the reverse-isolated low is captured by the SELV seen latch.
        // Its physical pulse width and POR behavior are outside this model.
        if !self.hot_permit {
            self.source_permit = false;
        }
    }

    fn hot_fault_shorter_than_timer_and_source_capture_guarantees(&mut self) {
        // Negative control: the HOT HCS74 catches the fault, but the TPS3890
        // MR-low minimum is not met and the reverse health pulse is not
        // guaranteed to clear the source latch. No retained inhibit exists.
        self.hot_ready = false;
        self.run = false;
    }
}

#[test]
fn raw_health_only_without_permit_readback_accepts_delayed_stale_rearm() {
    let mut r = Receiver::running();
    r.hot_permit_wire(false);
    r.source_observes_raw_health();
    assert!(r.source_permit && !r.hot_ready && !r.run);

    r.at(1);
    r.hot_permit_wire(true);
    r.arm_wire(false);
    r.at(1 + BLANK_MS);
    // No post-fault local press. This is an old command delayed in software.
    r.rearm_wire(true);
    r.arm_wire(true);
    assert!(r.run, "raw health plus finite blanking permits stale restart");
}

#[test]
fn held_permit_low_blocks_rearm_even_after_the_timer_duration() {
    let mut r = Receiver::running();
    r.hot_permit_wire(false);
    r.at(BLANK_MS + 1);
    r.rearm_wire(true);
    r.arm_wire(false);
    r.arm_wire(true);
    assert!(!r.hot_ready && !r.run);
}

#[test]
fn returned_permit_loss_forces_source_authorization_low() {
    let mut r = Receiver::running();
    r.hot_permit_wire(false);
    r.source_observes_latched_permit_loss();
    assert!(!r.source_permit);
    // A physical source latch must now hold the transmitted permit low.
    r.at(1);
    r.hot_permit_wire(r.source_permit);
    r.at(1 + BLANK_MS);
    r.rearm_wire(true);
    r.arm_wire(false);
    r.arm_wire(true);
    assert!(!r.hot_ready && !r.run);
}

#[test]
fn short_hot_fault_can_accept_old_rearm_without_retained_inhibit() {
    let mut r = Receiver::running();
    r.hot_fault_shorter_than_timer_and_source_capture_guarantees();
    assert!(r.source_permit && !r.hot_ready && !r.run);
    r.arm_wire(false);
    // These are delayed old commands, with no new local start. Because the
    // timer did not restart, its output can still be released immediately.
    r.rearm_wire(true);
    r.arm_wire(true);
    assert!(r.run);
}

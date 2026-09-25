//! Logical startup invariant for the compiled fixture's clear topology.
//! This is a discrete-event contract, not an analog timing simulation.

#[derive(Clone, Copy)]
struct Startup {
    rail_mv: u16,
    q1: bool, // start in the adverse unknown/high state
    supervisor_reset_n: bool,
    health: bool,
    rearm: bool,
    previous_rearm: bool,
}

impl Startup {
    fn clear_n(self) -> bool {
        // U4 is powered and its inputs are guaranteed only above its minimum
        // supply. The HCS74 is treated as valid at 2.0 V; the supervisor is
        // already within its specified range and asserts RESET below VITN.
        self.rail_mv >= 2_000 && self.health && self.supervisor_reset_n
    }

    fn step(&mut self) {
        let rising_rearm = self.rearm && !self.previous_rearm;
        if !self.clear_n() {
            self.q1 = false; // asynchronous /CLR1 dominates CLK1
        } else if rising_rearm {
            self.q1 = true; // D1 is tied high
        }
        self.previous_rearm = self.rearm;
    }
}

fn main() {
    let mut s = Startup {
        rail_mv: 0,
        q1: true,
        supervisor_reset_n: false,
        health: true,
        rearm: false,
        previous_rearm: false,
    };

    // Even with all three external health inputs stuck high, the rail
    // supervisor holds /CLR1 low through the HCS74's valid operating point.
    let mut ct_delay_elapsed = false;
    for rail_mv in (0..=3_300).step_by(10) {
        s.rail_mv = rail_mv;
        // TPS389001 RESET remains asserted until SENSE exceeds VITP and its
        // CT-programmed release delay has elapsed. Model that release only
        // after the monitored rail is above 3.0 V and a completed delay event.
        s.supervisor_reset_n = rail_mv >= 3_000 && ct_delay_elapsed;
        s.step();
        if rail_mv == 2_000 {
            assert!(!s.q1, "adverse initial Q1 must be cleared at valid HCS74 rail");
        }
    }

    assert!(!s.q1, "rail qualification ending must not re-arm the latch");
    // A pulse while clear is asserted cannot become a new edge when clear
    // releases, even if the source leaves the rearm conductor stuck high.
    s.rearm = true;
    s.step();
    assert!(!s.q1, "rearm while clear is asserted must be ignored");
    // The elapsed-delay event is abstract: the actual worst-case delay still
    // depends on selected CT capacitance, tolerance, leakage, and temperature.
    ct_delay_elapsed = true;
    s.supervisor_reset_n = s.rail_mv >= 3_000 && ct_delay_elapsed;
    s.step();
    assert!(!s.q1, "supervisor release with rearm held high must not set Q1");
    s.rearm = false;
    s.step();
    s.rearm = true;
    s.step();
    assert!(s.q1, "only a deliberate rearm edge may set Q1 after rail release");
    println!("PASS: initial-high Q1 is cleared before rail qualification; rearm is required");
}

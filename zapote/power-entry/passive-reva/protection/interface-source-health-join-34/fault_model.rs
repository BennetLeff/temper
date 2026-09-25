#[derive(Clone, Copy, Debug)]
struct PermitLatch {
    permit: bool,
    previous_rearm: bool,
}

impl PermitLatch {
    fn step(&mut self, reset_good: bool, watchdog_good: bool, interlock: bool,
            rail_qualified: bool, rearm: bool) {
        let healthy = reset_good && watchdog_good && interlock && rail_qualified;
        let rising_rearm = rearm && !self.previous_rearm;
        if !healthy {
            self.permit = false; // async clear dominates rearm clock
        } else if rising_rearm {
            self.permit = true;
        }
        self.previous_rearm = rearm;
    }
}

fn main() {
    // Start adverse-high, then valid rail supervisor clears before latch use.
    let mut startup = PermitLatch { permit: true, previous_rearm: false };
    startup.step(true, true, true, false, false);
    assert!(!startup.permit, "rail not qualified must clear permit");
    startup.step(true, true, true, true, false);
    assert!(!startup.permit, "rail recovery must not auto-arm");
    startup.step(true, true, true, true, true);
    assert!(startup.permit, "fresh re-arm edge sets permit");

    // CPU-only reset counterexample: retained reset-good and valid accepted
    // heartbeat mean no physical health input changes, so permit remains set.
    let mut cpu_only = PermitLatch { permit: true, previous_rearm: false };
    let retained_gpio_and_heartbeat = (true, true);
    cpu_only.step(retained_gpio_and_heartbeat.0, retained_gpio_and_heartbeat.1,
                  true, true, false);
    assert!(cpu_only.permit, "CPU-only reset may evade GPIO/watchdog capture");

    // When accepted-frame heartbeat stops long enough, watchdog-good falls and
    // latches permit off. Later watchdog recovery alone cannot re-arm it.
    let mut timeout = PermitLatch { permit: true, previous_rearm: false };
    timeout.step(true, false, true, true, false);
    assert!(!timeout.permit, "watchdog timeout must asynchronously clear permit");
    timeout.step(true, true, true, true, false);
    assert!(!timeout.permit, "watchdog recovery must not restore permit");
    timeout.step(true, true, true, true, true);
    assert!(timeout.permit, "only a fresh re-arm edge restores permit");

    // Held-high re-arm across fault clearance is not a fresh clock edge.
    let mut held = PermitLatch { permit: true, previous_rearm: false };
    held.step(true, false, true, true, true);
    assert!(!held.permit, "fault clear dominates simultaneous re-arm");
    held.step(true, true, true, true, true);
    assert!(!held.permit, "held-high re-arm must not set permit after recovery");
    held.step(true, true, true, true, false);
    held.step(true, true, true, true, true);
    assert!(held.permit, "subsequent deliberate edge sets permit");

    println!("PASS: boot clear, CPU-only reset counterexample, watchdog timeout capture, and fresh re-arm latch contract");
}

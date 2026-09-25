#[derive(Clone, Copy, Debug)]
struct SourceLatch {
    permit: bool,
}

impl SourceLatch {
    fn event(&mut self, healthy: bool, rearm_rising: bool) {
        if !healthy {
            self.permit = false;
        } else if rearm_rising {
            self.permit = true;
        }
    }
}

fn main() {
    let ideal_twd_min_ms = 119.82;
    let ideal_twd_max_ms = 144.98;

    // System/core reset deconfigures the digital GPIO. The board pulldown then
    // makes SOURCE_RESET_GOOD low and the source latch captures it.
    let mut system_reset = SourceLatch { permit: true };
    system_reset.event(false, false);
    assert!(!system_reset.permit);
    system_reset.event(true, false);
    assert!(!system_reset.permit, "health recovery must not auto-rearm");
    system_reset.event(true, true);
    assert!(system_reset.permit, "only a fresh rearm edge restores permit");

    // CPU-only reset is not guaranteed to touch GPIO registers or pads. An
    // allowed retained-high pad plus quick software restart can service WDI
    // before the 119.82 ms ideal-capacitor minimum timeout.
    let reset_restart_and_heartbeat_ms = 40.0;
    let no_wdi_timeout_ms = 145.0;
    let mut cpu_only_reset = SourceLatch { permit: true };
    assert!(reset_restart_and_heartbeat_ms < ideal_twd_min_ms);
    assert!(no_wdi_timeout_ms > ideal_twd_max_ms);
    cpu_only_reset.event(true, false); // no physical health transition
    assert!(cpu_only_reset.permit);

    // With a correct firmware contract, WDI remains quiet until fresh manual
    // rearm. External TPS3431 timeout then drops health and source latch holds.
    let mut contracted_cpu_reset = SourceLatch { permit: true };
    let watchdog_timed_out = no_wdi_timeout_ms > ideal_twd_max_ms;
    assert!(watchdog_timed_out);
    contracted_cpu_reset.event(false, false); // watchdog timeout to WDO low
    contracted_cpu_reset.event(true, false); // later WDO recovery is not rearm
    assert!(!contracted_cpu_reset.permit);
    contracted_cpu_reset.event(true, true);
    assert!(contracted_cpu_reset.permit);

    println!("PASS: reset capture and fresh-rearm contract; CPU-only auto-restart counterexample reproduced");
}

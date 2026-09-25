//! Logical counterexamples, not a silicon timing model.
//! Two healthy idle samples represent a chosen qualification interval.
use std::{error::Error, fs};

#[derive(Clone, Copy, Debug)]
enum State {
    WaitIdle,
    Qualify,
    Ready,
    Prepared(u8),
    Running,
}

fn step(state: State, healthy: bool, code: u8) -> State {
    if !healthy || code == 0 {
        return State::WaitIdle;
    }
    match (state, code) {
        (State::WaitIdle, 1) => State::Qualify,
        (State::Qualify, 1) => State::Ready,
        (State::Ready, 1) => State::Ready,
        (State::Ready, 3) => State::Prepared(0),
        (State::Prepared(age), 3) if age < 2 => State::Prepared(age + 1),
        (State::Prepared(_), 2) => State::Running,
        (State::Running, 2) => State::Running,
        _ => State::WaitIdle,
    }
}

#[derive(Clone, Copy)]
struct Sample {
    healthy: bool,
    source: u8,
    open_mask: u8,
}

fn run(name: &str, samples: &[Sample]) -> Result<bool, Box<dyn Error>> {
    let mut state = State::WaitIdle;
    let mut ever_run = false;
    let mut trace = String::from("sample\thealthy\tsource_ab\topen_mask\treceived_ab\tstate\trun\n");
    for (i, sample) in samples.iter().enumerate() {
        let received = sample.source & !sample.open_mask;
        state = step(state, sample.healthy, received);
        let running = matches!(state, State::Running);
        ever_run |= running;
        trace.push_str(&format!("{i}\t{}\t{:02b}\t{:02b}\t{received:02b}\t{state:?}\t{running}\n",
            sample.healthy, sample.source, sample.open_mask));
    }
    fs::write(format!("{name}.tsv"), trace)?;
    Ok(ever_run)
}

fn main() -> Result<(), Box<dyn Error>> {
    let sample = |healthy, source, open_mask| Sample { healthy, source, open_mask };
    let prefix = [sample(false, 0, 0), sample(true, 1, 0), sample(true, 1, 0), sample(true, 3, 0)];
    let mut valid = prefix.to_vec();
    valid.push(sample(true, 2, 0));
    valid.push(sample(false, 2, 0));
    let valid_starts = run("valid_sequence", &valid)?;
    let mut broken_b = prefix.to_vec();
    // The producer stays PREPARE=11. Only B's conductor opens; no request=10 was sent.
    broken_b.push(sample(true, 3, 1));
    let fault_starts = run("b_open_during_prepare", &broken_b)?;
    let held_reconnect = [sample(false, 2, 2), sample(true, 2, 2), sample(true, 2, 0), sample(true, 2, 0)];
    let held_starts = run("held_active_reconnect", &held_reconnect)?;
    let held_prepare = [sample(false, 3, 0), sample(true, 3, 0), sample(true, 3, 0), sample(true, 3, 0)];
    let prepare_starts = run("held_prepare_power_return", &held_prepare)?;

    // A one-bit low-before-high receiver sees the same trace in these two worlds.
    let intentional = [(false, false), (true, false), (true, true)];
    let disconnected = [(false, false), (true, false), (true, true)];
    let low_first_runs = |samples: &[(bool, bool)]| {
        let mut qualified = false;
        let mut running = false;
        for &(healthy, arm) in samples {
            if !healthy { qualified = false; running = false; }
            else if !arm { qualified = true; }
            else if qualified { running = true; }
        }
        running
    };
    let indistinguishable = intentional == disconnected
        && low_first_runs(&intentional) && low_first_runs(&disconnected);
    fs::write("one_bit_indistinguishability.tsv",
        "sample\thealthy\treceived_arm\tintentional_world\tfault_world\n0\tfalse\t0\tfault/reset\tfault/reset\n1\ttrue\t0\tproducer_commands_low\tproducer_high_wire_open\n2\ttrue\t1\tproducer_commands_high\tproducer_high_wire_reconnects\n")?;
    println!("case,observation,interpretation");
    println!("one_bit_low_first,{indistinguishable},REJECT_identical_receiver_history");
    println!("two_bit_valid,{valid_starts},positive_control_starts");
    println!("two_bit_b_open_prepare,{fault_starts},REJECT_single_wire_false_start");
    println!("two_bit_held_active_reconnect,{held_starts},specific_old_counterexample_blocked");
    println!("two_bit_held_prepare_return,{prepare_starts},static_prepare_does_not_start");
    if !indistinguishable || !valid_starts || !fault_starts || held_starts || prepare_starts {
        return Err("witness no longer reproduces expected logical behavior".into());
    }
    Ok(())
}

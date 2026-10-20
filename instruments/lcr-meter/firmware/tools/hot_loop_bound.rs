//! Static worst-case cycle bound for the boxcar hot loop (`feed_span`).
//! Input: `arm-none-eabi-objdump -d --no-show-raw-insn` of the firmware ELF.
//! The loop runs from the lowest backward-branch target to the last branch
//! back to it. One iteration executes each instruction in that range at most once
//! (no calls or inner loops are allowed), so summing all of them, with every
//! branch charged as taken, bounds any iteration. Cortex-M0+ timings with
//! zero-wait-state SRAM (ARM DDI 0484C, table 3-1); DMA bus-arbitration stalls
//! are not modelled. Code must run from SRAM, not XIP flash.
use std::{env, fs};
const BUDGET: u32 = 120; // sys clocks per 1 MSPS conversion at 120 MHz
/// bl/blx/bx; conditional branches such as ble/bls/blt are ordinary branches.
fn is_call(m: &str) -> bool {
    matches!(m.split('.').next(), Some("bl" | "blx" | "bx"))
}
fn cycles(mnemonic: &str, operands: &str) -> u32 {
    let registers = || {
        let list = operands.split('{').nth(1).unwrap_or("").split('}').next().unwrap_or("");
        list.split(',').filter(|r| !r.trim().is_empty()).count() as u32
    };
    match mnemonic {
        m if is_call(m) => panic!("call or return inside hot loop: {m}"),
        m if m.starts_with("bic") => 1,
        m if m.starts_with("b") => 2,
        "ldmia" | "stmia" | "ldm" | "stm" | "push" | "pop" => 1 + registers(),
        m if m.starts_with("ldr") || m.starts_with("str") => 2,
        m if m.starts_with("udiv") || m.starts_with("sdiv") => panic!("no hardware divide on M0+"),
        _ => 1,
    }
}
fn main() {
    let a: Vec<_> = env::args().collect();
    assert_eq!(a.len(), 2, "usage: hot_loop_bound OBJDUMP.txt");
    let text = fs::read_to_string(&a[1]).unwrap();
    let body: Vec<(u32, String, String)> = text
        .lines()
        .skip_while(|l| !l.ends_with("<feed_span>:"))
        .skip(1)
        .take_while(|l| !l.trim().is_empty())
        .filter_map(|l| {
            let (address, rest) = l.trim().split_once(':')?;
            let mut parts = rest.trim().splitn(2, char::is_whitespace);
            let mnemonic = parts.next()?.to_string();
            let operands = parts.next().unwrap_or("").trim().to_string();
            Some((u32::from_str_radix(address, 16).ok()?, mnemonic, operands))
        })
        .filter(|(_, m, _)| !m.starts_with('.'))
        .collect();
    assert!(!body.is_empty(), "feed_span not found");
    assert!(body[0].0 >= 0x2000_0000 && body[0].0 < 0x2004_2000, "feed_span is not in SRAM");
    let backward: Vec<(u32, u32)> = body
        .iter()
        .filter(|(_, m, _)| m.starts_with('b') && !m.starts_with("bic") && !is_call(m))
        .filter_map(|(at, _, ops)| {
            let target = u32::from_str_radix(ops.split_whitespace().next()?, 16).ok()?;
            (target < *at).then_some((target, *at))
        })
        .collect();
    // The loop head is the lowest backward-branch target; its latch is the last
    // branch back to it (epilogue jumps to other targets are not the loop).
    let head = backward.iter().map(|b| b.0).min().expect("no loop");
    let tail = backward.iter().filter(|b| b.0 == head).map(|b| b.1).max().unwrap();
    // Any other branch inside the loop must stay within it or leave forward.
    for (at, mnemonic, operands) in &body {
        if *at >= head && *at <= tail && mnemonic.starts_with('b') && !mnemonic.starts_with("bic") {
            let target = u32::from_str_radix(operands.split_whitespace().next().unwrap(), 16).unwrap();
            assert!(target >= head, "branch at {at:#x} leaves the loop backwards");
        }
    }
    let mut total = 0;
    let mut count = 0;
    for (at, mnemonic, operands) in &body {
        if *at >= head && *at <= tail {
            total += cycles(mnemonic, operands);
            count += 1;
        }
    }
    assert!(total < BUDGET, "hot loop bound {total} >= {BUDGET} cycles");
    println!(
        "PASS: feed_span loop {head:#010x}..{tail:#010x} in SRAM, {count} instructions, \
         worst-case bound {total} cycles per conversion (budget {BUDGET}, margin {})",
        BUDGET - total
    );
}

//! Static worst-case cycle bound for the synchronous-averaging hot loop (`syncavg_feed`).
//! Input: `arm-none-eabi-objdump -d --no-show-raw-insn` of the firmware ELF.
//! The function holds two loop bodies (averaging and raw) and a bin-wrap path. The bound
//! charges every instruction from the lowest backward-branch target to the highest
//! backward-branch source once, with every branch taken: one frame executes a subset of
//! that range at most once (no calls; the only backward branches are the loop latches), so
//! the sum bounds a frame in either mode. Cortex-M0+ timings with zero-wait-state SRAM
//! (ARM DDI 0484C, table 3-1); DMA bus-arbitration stalls are not modelled.
use std::{env, fs};
const BUDGET: u32 = 640; // sys clocks per 187.5 kHz frame at 120 MHz
fn is_call(m: &str) -> bool {
    matches!(m.split('.').next(), Some("bl" | "blx" | "bx"))
}
fn is_branch(m: &str) -> bool {
    m.starts_with('b') && !m.starts_with("bic")
}
fn cycles(mnemonic: &str, operands: &str) -> u32 {
    let registers = || {
        let list = operands.split('{').nth(1).unwrap_or("").split('}').next().unwrap_or("");
        list.split(',').filter(|r| !r.trim().is_empty()).count() as u32
    };
    match mnemonic {
        m if is_call(m) => panic!("call or return inside hot loop: {m}"),
        m if is_branch(m) => 2,
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
        .skip_while(|l| !l.ends_with("<syncavg_feed>:"))
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
    assert!(!body.is_empty(), "syncavg_feed not found");
    assert!(body[0].0 >= 0x2000_0000 && body[0].0 < 0x2004_2000, "syncavg_feed is not in SRAM");
    let target = |ops: &str| u32::from_str_radix(ops.split_whitespace().next().unwrap(), 16).unwrap();
    let backward: Vec<(u32, u32)> = body
        .iter()
        .filter(|(_, m, _)| is_branch(m) && !is_call(m))
        .map(|(at, _, ops)| (target(ops), *at))
        .filter(|(t, at)| t < at)
        .collect();
    let head = backward.iter().map(|b| b.0).min().expect("no loop");
    let tail = backward.iter().map(|b| b.1).max().unwrap();
    let (mut total, mut count) = (0, 0);
    for (at, mnemonic, operands) in &body {
        if *at >= head && *at <= tail {
            if is_branch(mnemonic) {
                assert!(target(operands) >= head, "branch at {at:#x} leaves the loops backwards");
            }
            total += cycles(mnemonic, operands);
            count += 1;
        }
    }
    assert!(total < BUDGET, "hot loop bound {total} >= {BUDGET} cycles");
    println!(
        "PASS: syncavg_feed loops {head:#010x}..{tail:#010x} in SRAM, {count} instructions, \
         worst-case bound {total} cycles per frame (budget {BUDGET}, {}% of core 0)",
        total * 100 / BUDGET
    );
}

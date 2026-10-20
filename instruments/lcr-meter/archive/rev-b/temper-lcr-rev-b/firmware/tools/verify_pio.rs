//! Limited instruction-level oracle for the assembled capture program.
//! Models instructions used here, no analog delay, DMA latency or silicon behavior.
use std::{env, fs};
fn main() {
    let a: Vec<_> = env::args().collect();
    assert_eq!(a.len(), 2);
    let s = fs::read_to_string(&a[1]).unwrap();
    let words: Vec<u16> = s
        .lines()
        .filter_map(|l| {
            l.trim()
                .strip_prefix("0x")
                .and_then(|t| t.split(',').next())
                .and_then(|x| u16::from_str_radix(x, 16).ok())
        })
        .collect();
    let wrap: usize = s
        .lines()
        .find_map(|l| l.strip_prefix("#define capture_wrap "))
        .unwrap()
        .parse()
        .unwrap();
    for count in [1, 2, 256, 16384, 32768] {
        simulate(&words, wrap, count, true);
    }
    simulate(&words, wrap, 256, false);
    println!("PASS: assembled PIO exact counts 1/2/256/16384/32768; 120 cycles/frame; 16 edges; dual-lane bit order; CS setup/hold; late READY fault");
}
fn simulate(program: &[u16], wrap: usize, count: u32, ready: bool) {
    let (mut pc, mut cycle, mut x, mut y, mut osr, mut isr, mut bits) =
        (0usize, 0u64, 0u32, 0u32, 0u32, 0u32, 0u32);
    let (mut prev_side, mut conv, mut cs, mut last_sample, mut frames, mut pushes, mut edges) =
        (1u16, 0u64, 0u64, 0u64, 0u32, 0u32, 0u32);
    loop {
        assert!(cycle < (count as u64 + 1) * 120 + 10);
        let instruction = program[pc];
        let side = (instruction >> 10) & 7;
        let delay = (instruction >> 8) & 3;
        if side & 4 != 0 && prev_side & 4 == 0 {
            if frames > 0 {
                assert_eq!(cycle - conv, 120);
            }
            conv = cycle;
            frames += 1;
            edges = 0;
        }
        if side & 1 == 0 && prev_side & 1 != 0 {
            cs = cycle;
            assert_eq!(cycle - conv, 45);
        }
        if side & 2 != 0 && prev_side & 2 == 0 {
            if edges == 0 {
                assert!(cycle - cs >= 2);
            }
            edges += 1;
        }
        if side & 1 != 0 && prev_side & 1 == 0 {
            assert!(cycle - last_sample >= 2);
            assert_eq!(edges, 16);
        }
        let mut next = if pc == wrap { 1 } else { pc + 1 };
        let op = instruction >> 13;
        let arg = (instruction & 31) as usize;
        let dest = (instruction >> 5) & 7;
        match op {
            0 => {
                let jump = match dest {
                    2 => {
                        let old = x;
                        x = x.wrapping_sub(1);
                        old != 0
                    }
                    4 => {
                        let old = y;
                        y = y.wrapping_sub(1);
                        old != 0
                    }
                    6 => {
                        assert_eq!(cycle - conv, 44);
                        ready
                    }
                    _ => panic!("unsupported jmp"),
                };
                if jump {
                    next = arg;
                }
            }
            2 => {
                assert_eq!(dest, 0);
                assert_eq!(arg, 2);
                assert!(side & 3 == 0);
                let bit = 15 - bits / 2;
                let av = (0xa55au32 ^ (frames - 1)) & 0xffff;
                let bv = (0x1234u32.wrapping_add(frames - 1)) & 0xffff;
                isr = (isr << 2) | (((av >> bit) & 1) | (((bv >> bit) & 1) << 1));
                bits += 2;
                last_sample = cycle;
                if bits == 32 {
                    let decode = |ch: u32| {
                        (0u32..16).fold(0u32, |v, b| v | (((isr >> (2 * b + ch)) & 1) << b))
                    };
                    assert_eq!(decode(0), av);
                    assert_eq!(decode(1), bv);
                    bits = 0;
                    isr = 0;
                    pushes += 1;
                }
            }
            4 => {
                assert_eq!(pc, 0);
                osr = count - 1;
            }
            5 => {
                let source = match arg {
                    1 => x,
                    2 => y,
                    7 => osr,
                    _ => panic!("unsupported mov source"),
                };
                match dest {
                    1 => x = source,
                    2 => y = source,
                    7 => osr = source,
                    _ => panic!("unsupported mov destination"),
                }
            }
            6 => {
                if ready {
                    assert_eq!(arg, 0);
                    assert_eq!(pushes, count);
                    assert_eq!(frames, count);
                } else {
                    assert_eq!(arg, 4);
                    assert_eq!(pushes, 0);
                    assert_eq!(frames, 1);
                }
                break;
            }
            7 => match dest {
                1 => x = arg as u32,
                2 => y = arg as u32,
                _ => panic!("unsupported set"),
            },
            _ => panic!("unsupported instruction"),
        }
        prev_side = side;
        cycle += 1 + u64::from(delay);
        pc = next;
    }
}

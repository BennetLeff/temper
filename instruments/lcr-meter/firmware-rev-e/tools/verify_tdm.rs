//! Instruction-level oracle for the assembled TDM programs (pioasm output headers): `tdm`
//! (187.5 kHz build: 120 MHz, 10 cycles per BCLK, 64 BCLK, 32-bit slots) and `tdm375`
//! (375 kHz build: 108 MHz, 6 cycles per BCLK, 48 BCLK, 24-bit slots). Usage:
//! `verify_tdm tdm.pio.h [tdm375.pio.h]`; each header is checked against its program's spec.
//! Models only the instructions used here, at clock divider 1, with DOUT's input synchronizer
//! bypassed (src/main.c): `in` sees the pad as it was before that cycle's edge. It also models
//! the TAC5112 side of the bus from SLASF24A 7.3.1.2.1: the codec latches DIN and FSYNC on
//! falling BCLK and launches DOUT on rising BCLK, slot 0 MSB on the FSYNC edge (TX_OFFSET 0),
//! after a delay of 0 up to one cycle short of the falling edge (tdm: 0-4 cycles, 33 ns;
//! tdm375: 0-2 cycles, 18.5 ns; td(DOUT-BCLK) <= 14 ns plus pad and rise time). Slots carry
//! `slot_bits`-bit words MSB first: the codec takes the top bits of each DAC word, and the
//! program left-justifies each ADC word in its 32-bit RX word.
//! The TX side is fed as src/main.c feeds it: a 4-word TX FIFO that the DMA tops up a fixed
//! latency after each pull, from a waveform of `period` words played in a loop. When the DMA
//! writes the waveform's last word the chain snapshots the RX word count; the firmware starts
//! a capture at that count + 1 and claims capture frame 0 meets DAC word (period - 5).
//! No analog delay, metastability or silicon behaviour beyond that.
use std::{collections::VecDeque, env, fs};

const FRAMES: usize = 400;

/// What one program must do on the bus.
struct Spec {
    name: &'static str,
    clock: &'static str,
    sys_hz: f64,
    /// System clocks per BCLK, and how many of them BCLK is high.
    bit: u64,
    high: u64,
    frame_bclks: u64,
    slot_bits: u32,
    /// Frame cycles of the two pushes and of the mid-frame pull.
    pushes: [u64; 2],
    pull: u64,
    /// TX DMA refill latencies that must keep every snapshot between the pushes, and one past
    /// the slot-1 push that must not.
    latencies: [u64; 4],
    late: u64,
}
const SPECS: [Spec; 2] = [
    Spec {
        name: "tdm",
        clock: "120 MHz: BCLK 12 MHz, 187.5 kHz",
        sys_hz: 120e6,
        bit: 10,
        high: 5,
        frame_bclks: 64,
        slot_bits: 32,
        pushes: [316, 636],
        pull: 476,
        latencies: [0, 1, 40, 150],
        late: 170,
    },
    Spec {
        name: "tdm375",
        clock: "108 MHz: BCLK 18 MHz, 375 kHz",
        sys_hz: 108e6,
        bit: 6,
        high: 3,
        frame_bclks: 48,
        slot_bits: 24,
        pushes: [143, 287],
        pull: 214,
        latencies: [0, 1, 40, 70],
        late: 80,
    },
];

struct Run {
    rx: Vec<u32>,            // words pushed to the RX FIFO
    snapshots: Vec<usize>,   // RX words pushed when the DMA wrote the waveform's last word
    codec_din: Vec<u32>,     // slot 0 / slot 1 words the codec latched from DIN
    push_phase: Vec<u64>,    // frame cycle of each push
    pull_phase: Vec<u64>,    // frame cycle of each pull after the first
}

fn main() {
    let a: Vec<_> = env::args().collect();
    assert!(a.len() >= 2, "usage: verify_tdm tdm.pio.h [tdm375.pio.h]");
    for path in &a[1..] {
        let s = fs::read_to_string(path).unwrap();
        let spec = SPECS
            .iter()
            .find(|p| s.contains(&format!("static const uint16_t {}_program_instructions[]", p.name)))
            .expect("no known TDM program in the header");
        verify(&s, spec);
    }
}

fn verify(s: &str, spec: &Spec) {
    let marker = format!("static const uint16_t {}_program_instructions[]", spec.name);
    let program: Vec<u16> = s[s.find(&marker).unwrap()..]
        .lines()
        .skip(1)
        .take_while(|l| !l.trim_start().starts_with("};"))
        .filter_map(|l| {
            l.trim()
                .strip_prefix("0x")
                .and_then(|t| t.split(',').next())
                .and_then(|x| u16::from_str_radix(x, 16).ok())
        })
        .collect();
    assert!(!program.is_empty() && program.len() <= 32, "program length {}", program.len());
    let define = |name: &str| -> usize {
        s.lines()
            .find_map(|l| l.strip_prefix(&format!("#define {}_{name} ", spec.name)))
            .unwrap()
            .trim()
            .parse()
            .unwrap()
    };
    let (wrap_target, wrap) = (define("wrap_target"), define("wrap"));
    let mut state = 0x1234_5678u32;
    let mut rnd = || {
        state ^= state << 13;
        state ^= state >> 17;
        state ^= state << 5;
        state
    };
    // Bits the codec sends of each ADC word, left-justified: what the RX words must hold.
    let keep = u32::MAX << (32 - spec.slot_bits);
    let adc: Vec<u32> = (0..2 * FRAMES + 8).map(|_| rnd()).collect();
    let max_delay = spec.high - 1;
    let mut snapshots = 0;
    for period in [16usize, 17, 61, 375] {
        let wave: Vec<u32> = (0..period).map(|_| rnd()).collect();
        for delay in 0..=max_delay {
            for latency in spec.latencies {
                let r = simulate(spec, &program, wrap_target, wrap, &wave, &adc, delay, latency);
                let frames = r.rx.len() / 2;
                assert!(frames >= FRAMES - 2, "too few frames: {frames}");
                for (i, &w) in r.rx.iter().enumerate() {
                    assert_eq!(w, adc[i] & keep, "DOUT word {i} (delay {delay})");
                }
                for f in 0..frames {
                    assert_eq!(r.codec_din[2 * f], wave[f % period] >> (32 - spec.slot_bits), "DAC slot 0, frame {f}");
                    assert_eq!(r.codec_din[2 * f + 1], 0, "DAC slot 1, frame {f}");
                }
                assert!(r.push_phase.iter().enumerate().all(|(i, &p)| p == spec.pushes[i % 2]));
                assert!(r.pull_phase.iter().all(|&p| p == spec.pull));
                assert!(r.snapshots.len() >= FRAMES / period - 1);
                for &snap in &r.snapshots {
                    let start = snap + 1;
                    assert_eq!(start % 2, 0, "capture start is not a slot 0 word");
                    let frame = start / 2;
                    if frame < frames {
                        assert_eq!(r.codec_din[2 * frame], wave[period - 5] >> (32 - spec.slot_bits), "capture frame 0 alignment");
                    }
                    snapshots += 1;
                }
            }
        }
    }
    // Negative control: a DOUT launched as late as the falling edge reaches the pad on the
    // sampling cycle itself, so the sample is the previous bit.
    let wave: Vec<u32> = (0..61).map(|_| rnd()).collect();
    let slow = simulate(spec, &program, wrap_target, wrap, &wave, &adc, spec.high, 0);
    assert!(
        slow.rx.iter().enumerate().any(|(i, &w)| w != adc[i] & keep),
        "slow DOUT not detected"
    );
    // Negative control: a refill later than the slot 1 push moves the snapshot past it, and
    // the start word lands on slot 1.
    let late = simulate(spec, &program, wrap_target, wrap, &wave, &adc, 0, spec.late);
    assert!(late.snapshots.iter().all(|&s| (s + 1) % 2 == 1), "late refill not detected");
    let ns = |cycles: u64| cycles as f64 * 1e9 / spec.sys_hz;
    println!(
        "PASS {}: assembled program ({} instructions), {FRAMES} frames x DOUT delay 0-{max_delay} cycles \
         ({:.1} ns, synchronizer bypassed); {}: BCLK {}+{} cycles, {} BCLK and one 1-BCLK FSYNC pulse per \
         frame, DIN/FSYNC change only on rising BCLK, slot 0 = DAC word's top {} bits MSB first, slot 1 = 0, \
         both ADC words bit-exact (left-justified) and in order, pushes at frame cycles {}/{}, pull at {}; \
         periods 16/17/61/375 with TX DMA latency {:?} cycles: {snapshots} snapshots, every capture \
         start on slot 0 and capture frame 0 = DAC word (period - 5); negative controls: a {}-cycle \
         DOUT delay and a {}-cycle refill both fail",
        spec.name,
        program.len(),
        ns(max_delay),
        spec.clock,
        spec.high,
        spec.bit - spec.high,
        spec.frame_bclks,
        spec.slot_bits,
        spec.pushes[0],
        spec.pushes[1],
        spec.pull,
        spec.latencies,
        spec.high,
        spec.late
    );
}

#[allow(clippy::too_many_arguments)]
fn simulate(spec: &Spec, program: &[u16], wrap_target: usize, wrap: usize, wave: &[u32], adc: &[u32],
            dout_delay: u64, dma_latency: u64) -> Run {
    // TX FIFO (4 deep) and its DMA: after each pull the DMA writes the next waveform word
    // `dma_latency` cycles later. Before the state machine starts the FIFO is full.
    let mut tx: VecDeque<u32> = VecDeque::new();
    let mut tx_issued = 0usize;
    let mut refills: VecDeque<u64> = VecDeque::new();
    let mut snapshots = vec![];
    while tx.len() < 4 {
        tx.push_back(wave[tx_issued % wave.len()]);
        tx_issued += 1;
    }
    let (mut pc, mut x, mut osr, mut isr, mut isr_count) = (0usize, 0u32, 0u32, 0u32, 0u32);
    let (mut bclk, mut fsync, mut din) = (false, false, false);
    let mut run = Run { rx: vec![], snapshots: vec![], codec_din: vec![], push_phase: vec![], pull_phase: vec![] };
    // Bus history, one entry per cycle: (bclk, fsync, din, dout).
    let mut history: Vec<(bool, bool, bool, bool)> = vec![];
    // Codec state.
    let (mut frame_start, mut last_rise, mut last_fall) = (None::<u64>, None::<u64>, None::<u64>);
    let (mut codec_bit, mut codec_word, mut dout_word_index) = (0u32, 0u32, 0usize);
    let mut dout_shift: u32 = 0; // word being transmitted
    let mut dout_pending: Option<(u64, bool)> = None;
    let mut dout = false;
    let mut first_pull = true;
    let mut cycle = 0u64;
    while run.rx.len() < 2 * FRAMES && cycle < 2_000_000 {
        while refills.front().map_or(false, |&t| t <= cycle) {
            refills.pop_front();
            tx.push_back(wave[tx_issued % wave.len()]);
            if tx_issued % wave.len() == wave.len() - 1 {
                snapshots.push(run.rx.len()); // RX DMA has taken every word pushed so far
            }
            tx_issued += 1;
        }
        let instruction = program[pc];
        let side = (instruction >> 11) & 3;
        let delay = ((instruction >> 8) & 7) as u64;
        let op = instruction >> 13;
        // Side-set and data outputs take effect at the start of the instruction's cycle.
        let new_bclk = side & 1 != 0;
        let new_fsync = side & 2 != 0;
        let mut new_din = din;
        let mut next = if pc == wrap { wrap_target } else { pc + 1 };
        // Synchronizer bypassed: the sample is the pad value before this cycle's edge.
        let sampled = dout;
        match op {
            0 => {
                assert_eq!((instruction >> 5) & 7, 2, "only jmp x-- is modelled");
                let old = x;
                x = x.wrapping_sub(1);
                if old != 0 {
                    next = (instruction & 31) as usize;
                }
            }
            2 => match instruction & 0xff {
                0x01 => {
                    // in pins, 1
                    isr = (isr << 1) | sampled as u32;
                    isr_count += 1;
                }
                0x68 => {
                    // in null, 8
                    isr <<= 8;
                    isr_count += 8;
                }
                _ => panic!("only in pins, 1 and in null, 8 are modelled"),
            },
            3 => {
                assert_eq!(instruction & 0xff, 0x01, "only out pins, 1 is modelled");
                new_din = osr >> 31 != 0;
                osr <<= 1;
            }
            4 => {
                if instruction & 0x80 == 0 {
                    assert_eq!(isr_count, 32, "push of a partial word");
                    run.rx.push(isr);
                    run.push_phase.push(cycle - frame_start.unwrap());
                    isr = 0;
                    isr_count = 0;
                } else {
                    osr = tx.pop_front().expect("TX underflow");
                    refills.push_back(cycle + dma_latency);
                    if !first_pull {
                        run.pull_phase.push(cycle - frame_start.unwrap());
                    }
                    first_pull = false;
                }
            }
            5 => {
                assert_eq!(instruction & 0xff, 0x03, "only mov pins, null is modelled");
                new_din = false;
            }
            7 => {
                assert_eq!((instruction >> 5) & 7, 1, "only set x is modelled");
                x = (instruction & 31) as u32;
            }
            _ => panic!("unmodelled opcode {op}"),
        }
        for step in 0..=delay {
            let (b, f, d) = if step == 0 { (new_bclk, new_fsync, new_din) } else { (bclk, fsync, din) };
            if step == 0 {
                // DIN and FSYNC may only change together with a rising BCLK edge.
                if (f != fsync || d != din) && !(b && !bclk) {
                    panic!("DIN/FSYNC changed off a rising edge at cycle {cycle}");
                }
            }
            let t = cycle + step;
            if b && !bclk {
                if let Some(r) = last_rise {
                    assert_eq!(t - r, spec.bit, "BCLK period");
                }
                if let Some(fl) = last_fall {
                    assert_eq!(t - fl, spec.bit - spec.high, "BCLK low time");
                }
                last_rise = Some(t);
                // Codec launches the next DOUT bit on this rising edge, after dout_delay.
                if f && !fsync {
                    if let Some(s) = frame_start {
                        assert_eq!(t - s, spec.bit * spec.frame_bclks, "frame length");
                    }
                    frame_start = Some(t);
                    codec_bit = 0;
                }
                if frame_start.is_some() {
                    if codec_bit % spec.slot_bits == 0 {
                        dout_shift = adc[dout_word_index];
                        dout_word_index += 1;
                    }
                    dout_pending = Some((t + dout_delay, dout_shift >> 31 != 0));
                    dout_shift <<= 1;
                }
            }
            if !b && bclk {
                if let Some(r) = last_rise {
                    assert_eq!(t - r, spec.high, "BCLK high time");
                }
                last_fall = Some(t);
                // Codec latches FSYNC and DIN on the falling edge.
                if frame_start.is_some() {
                    if codec_bit == 0 {
                        assert!(f, "FSYNC not high on the first bit");
                    } else {
                        assert!(!f, "FSYNC high past the first bit");
                    }
                    codec_word = (codec_word << 1) | d as u32;
                    codec_bit += 1;
                    if codec_bit % spec.slot_bits == 0 {
                        run.codec_din.push(codec_word);
                        codec_word = 0;
                    }
                }
            }
            if let Some((when, value)) = dout_pending {
                if t >= when {
                    dout = value;
                    dout_pending = None;
                }
            }
            bclk = b;
            fsync = f;
            din = d;
            history.push((bclk, fsync, din, dout));
        }
        cycle += 1 + delay;
        pc = next;
    }
    run.snapshots = snapshots;
    run
}

# Accepted-controller fixture binding audit

This is a file/receipt audit only. No ngspice run or raw-trace read was
performed here. The accepted campaign controller source is
`accepted-baseline-11/ucc28180-pwm-latch.inc`, SHA-256
`2e885755aad4d03fb9c06d7c556faf23ad0ae7922f581d56752db78933b97251`.

## What is already covered

`controller-finite-edge-safe/ucc28180.inc` has that exact SHA and every small
controller deck in that folder includes it by the local name `ucc28180.inc`.
`controller-finite-edge-safe/model-input.json` repeats the same SHA. Its
`parent` string points to the older finite-edge path, so the hash—not that
historical path—is the binding identity.

The retained `controller-finite-edge-safe/results.json` records simulator and
checker exit zero for all six fixtures, with the following recorded wall times:

| fixture | coverage receipt | wall time | retained TSV bytes |
| --- | --- | ---: | ---: |
| `current-loop` | TI-equation gain/pole, oscillator, ICOMP offset | 1.56 s | 9,664,000 |
| `functional` | 15 pin/function assertions, including ICOMP short and cycle-latched PCL | 1.20 s | 16,587,131 |
| `soft-start` | VCOMP charge, SOC discharge/recovery, standby/retry | 16.60 s | 138,336,040 |
| `pwm-hold` | PWM latch hold after comparator recrossing and reset | 0.42 s | 1,046,010 |
| `pwm-ramp` | three PWM crossings plus ICOMP-short gate inhibition | 1.56 s | 3,119,358 |
| `integrated` | F2/detector/latch timing and plant peaks | 8.68 s | 90,000,000+ |

The exact assertion text is retained in `functional-checks.txt`,
`current-loop-checks.txt`, `soft-start-checks.txt`, `pwm-hold-checks.txt`, and
`pwm-ramp-checks.txt`. Thus controller-only ICOMP/PCL behavior is already
covered against the exact accepted controller include. The older folders are
not equivalent: their controller hashes are `ad8338e2...` (controller-probes),
`7cd12ac4...` (controller-latched), `d98f3890...` (latched-explicit), and
`1aa5065f...` (finite-edge), all different from the accepted hash.

## What is not covered by those receipts

No retained fixture receipt cryptographically binds the **full accepted six-file
power closure**. In particular, `controller-finite-edge-safe/integrated.cir`
includes its local `protection.inc`, whose SHA is
`b57b854883ee992dad036fd49c5a249b457e200873a3408652186de59122ea1c`, versus
the accepted baseline `protection.inc` SHA
`61385002bc7c55313814b7ea606c1198129da20a1f76cd44fe197de0468a70e8`.
The diff replaces the authored `ucc28180-pwm-latch` driver include and
`Xdriver` path with a simpler local driver surrogate. Therefore the integrated
receipt is not evidence for the accepted normal power-stage closure, even
though its controller include is exact. The accepted closure also contains
`standby.inc`, `clamp.inc`, and `authored_logic_hysteretic.inc`; the isolated
controller decks do not exercise that closure.

The existing six-fixture results are therefore authoritative for the scoped
controller equations and ICOMP/PCL behavior, but not for controller-plus-
accepted-power-stage equivalence. They do not justify a generic corner sweep,
hardware claim, or normal operating-point claim.

## Smallest meaningful binding rerun if the parent requires a fresh receipt

There is no need to rerun controller-only behavior merely to change the
verdict: the exact accepted controller SHA is already present and all six
recorded fixture/checker exits are zero. If an explicit runtime binding is
needed, the smallest unchanged fixtures are the two complementary decks:

1. `controller-finite-edge-safe/pwm-hold.cir` with `hold_checks.rs` (PWM comparator latch hold;
   1,046,010-byte output).
2. `controller-finite-edge-safe/pwm-ramp.cir` with `pwm_checks.rs` (ICOMP-short
   inhibition and PWM timing; 3,119,358-byte output).

Copy the accepted controller file to the fixture-local `ucc28180.inc`, keep
both circuits/checkers byte-identical, run ngspice 45.2, then run the existing
Rust checkers. Their recorded wall times sum to about 2 seconds and each
individual output is below 5 MB. A new receipt must record the copied include
hash, circuit/checker hashes, ngspice version, simulator/checker exits, and
output hashes. This would prove only the controller include binding; it would
still not prove the full accepted six-file power closure.

No such rerun was launched by this audit.

## Parent review

The accepted and local controller bytes and recorded model-input hash match.
Parent verified the six zero-exit records, each local controller include,
retained assertion text, and the differing protection-source hash. The
`pwm-hold` fixture holds ISENSE at zero: it tests PWM comparator latch hold,
not PCL. PCL blanking/hold coverage comes from the separate functional fixture.
This review binds the retained small source and result files; it is not a new
trace replay or proof of full power-stage equivalence. No rerun is justified
solely to duplicate these nominal controller receipts.

# Timed-model ngspice cross-check (second path)

Date: 2026-09-19. **Illustrative numerical oracle, not a physical protection
result.** ngspice 45.2 checks the timed F2-open integrator
(`../../experiments/f2-open/f2_open_timed.rs`) the way
`../f2-open-oracle-01` checked the immediate-off algebra. This does not model
the UCC28180, fuse opening, MOSFET turn-off, saturation, tolerances, or an
actual surge. The switch is ideal (`Ron=1m`), the diode is the same synthetic
`IS=1e-12 N=1 RS=0.001 CJO=10p TT=0` device as oracle-01 — deliberately not a
STW65N65DM2AG or C3D20065D model. Raw traces are not retained (16–20 MB per
run at solver density); the comparison is by recorded peak, fully captured in
the retained logs. File hashes are in `result.json`.

Two cases, each at two maximum steps:

| Case | ngspice peak (5 ns) | ngspice peak (10 ns) | Rust model | Closed form |
|---|---|---|---|---|
| Freewheel from V0=425 V, I0=20 A, const crest Vin | 636.6334 V | 636.6334 V | 636.9936 V | 637.0029 V |
| Prescribed pattern (ON 0–4/8–12 us, then off), V0=389.615 V, I0=23.2318 A | 793.7040 V | 793.7035 V | 794.3178 V | — (no closed form) |

The Rust model is loss-free (ideal diode Vf=0, ideal switch), so it must read
slightly *higher* than ngspice — and does, by 0.36 V and 0.61 V (both <0.1%),
the same sign and mechanism as oracle-01's 0.45 V diode-loss difference.
Step refinement changes nothing to 4 decimals (freewheel) and 0.0005 V
(pattern): the comparison is converged, not step-limited.

Reproduce from this directory:

```sh
/opt/homebrew/bin/ngspice -b freewheel-5ns.cir > freewheel-5ns.log 2>&1
/opt/homebrew/bin/ngspice -b patt-5ns.cir > patt-5ns.log 2>&1
/tmp/f2_open_timed xcheck 425.0 20.0
/tmp/f2_open_timed patt
```

with `/tmp/f2_open_timed` built by `rustc -O
../../experiments/f2-open/f2_open_timed.rs -o /tmp/f2_open_timed`.
The Rust binary additionally asserts its own closed-form limit
(674.7309 V vs 674.7412 V, rel 1.5e-5) and the burst-period identity on every
sweep run, and closes per-run energy to ~1 nJ on ~100 mJ (see `raw/`).

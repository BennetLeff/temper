# F2-open claims ledger and fault-loop evidence (Package 2)

Date: 2026-09-19. Status: **machine-checked evidence ledger; no protection
qualification promoted.** This directory binds the F2-open package's claims
(`claims.json`, schema `f2-open-claims/v1`) to retained bytes and records the
`zapote-fault-loop` connectivity runs on the post-ECO netlist. A clean
`zapote-claims` run means no violations were detected by the implemented
checks — it does not establish derivation soundness in general, does not
establish that any claim is true, and does not replace tracing the actual
current path.

## Run identity

- Worktree `/private/tmp/temper-pkgs-1-4`, branch `codex/power-entry-pkgs-1-4`,
  base commit `a2536ee140c8bd368a4bb16a464e36620df2858f`
  (`codex/active-bridge-alternative`); `scripts/assert-base.sh` passed at
  session start. The working tree carries the uncommitted diode-side feedback
  ECO this package assesses:
  `elec/src/power_entry_active_unit.ato` SHA-256
  `2ce30c94b9aa7b1e39cc8d0966c386c862bc2e634c2fd437c97a28de1bf3f5fe`
  (r_vtop pin 1 on `BOOST_DIODE_POSITIVE`; bank/output/bleeders bank-side).
- Controller primary source: `TI-UCC28180.pdf` Rev D, SHA-256
  `e1e1588c6854b43742a667c76df26f06d9ac51231f0176c43d2a46b63c1b00be`
  (re-hashed this session; matches the retained pin in
  `../../experiments/f2-open/raw/input-sha256.txt`).
- Post-ECO connectivity input: `../vsense-diode-side-02/native.json`
  (167 pin-net connections, 45 nets), re-derived into
  `fault-loop/netlist.json` (duplicates deduplicated).
- Binaries (read-only): `zapote-claims` SHA-256 `56bf50adf7348607…`,
  `zapote-fault-loop` SHA-256 `c9ae782ea19e988c…`, at
  `/Users/bennet/Desktop/temper/target-shared/debug/`.
- Every evidence reference in `claims.json` carries the SHA-256 of the
  retained bytes at ledger-write time and is resolved and checked by the tool.

## Session re-verification (before any number was trusted)

1. `f2_open_timed.rs` rebuilt with `rustc -O` and re-run: `raw/timed-sweep.csv`
   and `raw/startup-bursts.csv` reproduced **byte-identically**; in-code
   closed-form assertions passed (immediate-off 674.7309 V vs formula
   674.7412 V, rel 1.5e-5; burst-period log formula vs numeric bleed, rel
   < 3e-5 both corners); energy-identity residuals ≈1e-9 J on the xcheck/patt
   runs (`xcheck 425.0 20.0` → 636.9936 V / closed 637.0029 V; `patt` →
   794.3178 V).
2. The four ngspice decks in `../f2-open-timed-02/` re-run with
   `/opt/homebrew/bin/ngspice` (45.2): peaks identical to the retained logs
   (freewheel 636.6334 V at both step sizes; pattern 793.7035/793.7040 V).
   Only ngspice "Reference value" truncation-statistics lines differ between
   runs — those are solver statistics, not measurements; the `vpeak` lines are
   unchanged.
3. Datasheet citations in `MODEL.md` §2 spot-checked against the retained PDF
   with `pdftotext`: EC table printed p.6 (OVP_H 107/109/111 %VREF, reset
   100/102/104, OLP 15.6/16.5/17.6, PCL −0.345/−0.400/−0.438 V, VREF
   4.93/5.00/5.07 V at 25 °C and 4.87/5.15 V over temperature, DMAX
   94.8/96.5/98 %, VCC UVLO off 9.1/9.5/10.3 V) and §8.3.1/8.3.3 (pp. 14–15),
   §8.3.4/8.3.5/8.3.9 (p. 15), §8.3.11/8.3.12 (p. 17) all confirmed.
4. Two numeric corrections applied to
   `../../decisions/f2-open/PROTECTION-SELECTION.md` from the re-checked CSV:
   the 1.5 µF corner range is 598–617 V (nominal row 598.0 V, five corner rows
   604.0–616.8 V), and the interpolated 630 V crossing is ≈14 µs
   (613.34 V at 10 µs → 657.56 V at 20 µs, slope ≈4.4 V/µs), not ≈13 µs.

## Fault-loop runs (`fault-loop/runs.txt`)

Connectivity-only checks on the post-ECO netlist; currents are illustrative
placeholders. Consistent ≠ conductive.

| # | Loop | Result |
|---|---|---|
| 1 | Line-fed drive loop, healthy U9, F2 open (bus_fuse = 0) | CONSISTENT — the pump path exists with the fuse out of it |
| 2 | Same loop, current credited through the open bus_fuse | INCONSISTENT (expected counterexample; retained) |
| 3 | Internal bank loop, U9+U10 failed-short, F2 closed | CONSISTENT — the loop runs through F2 only |
| 4 | Same loop, controller/q_inhibit credited as interrupters | INCONSISTENT (expected counterexample; retained) — no gate-disable element lies in the internal loop |
| 5 | Post-ECO sense + inhibit path (divider chain → vsense; q_inhibit at vsense) | CONSISTENT — the wired-OR node the proposed q_inhibit2 parallels |

## Ledger summary

53 claims (12 UCC28180 datasheet sources, 12 authored-source, 1 retained
operating-point source, 9 assumptions, 19 illustrative derivations), 5
protection claims — **`interrupts: false` in every fault case** — and one
promotion: `f2-open-protection-arrangement` `none → protection_identified`
only. No MPN is selected (all part fields in the proposed ECO are
criteria-valued `TBD-QR-*`), so `part_selected` is not claimed;
coordination-demonstrated and hardware-verified are not claimed.

Tool output retained in `zapote-claims-output.txt`:

```
No violations detected by implemented checks (53 claims, 5 protection claims,
1 promotions). This does not establish derivation soundness in general.
```

## Reproduce

```sh
rustc -O ../../experiments/f2-open/f2_open_timed.rs -o /tmp/f2_open_timed
/tmp/f2_open_timed  > /tmp/timed-sweep.csv      # diff vs raw/timed-sweep.csv
/tmp/f2_open_timed burst > /tmp/startup-bursts.csv
/Users/bennet/Desktop/temper/target-shared/debug/zapote-fault-loop \
  fault-loop/netlist.json --loop-nets PFC_BUS_PLUS_390V,BOOST_DIODE_POSITIVE,a1,PFC_BUS_MINUS \
  --assignments fault-loop/assign-internal-loop.json
/Users/bennet/Desktop/temper/target-shared/debug/zapote-claims claims.json
```

## Non-claims

No claim is made that F2 clears, that shutdown meets the budget in hardware,
or that the arrangement is qualified. Open inputs remain exactly as listed in
`PROTECTION-SELECTION.md` §7 and the QR table §5: inductor saturation curve,
capacitor and filter tolerances, AUX/HOT_PERMIT producer contracts,
VCOMP/EDR large-signal response, actual comparator/gate delays, fuse-opening
arcing, surge beyond mains inflow, and every failed-short destructive-fault
interruption (QR-F2A/QR-F2B/QR-F1).

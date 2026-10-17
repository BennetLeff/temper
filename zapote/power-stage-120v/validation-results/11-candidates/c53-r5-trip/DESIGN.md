# R5 hardware average-current trip: design record (desk, not built)

2026-10-16. Selv, s53 scope item 2 (`c53-stuck-on/S53-SCOPE.md`; study `c53-line-current-f1/README.md` A3/A4). Numbers come
from `scripts/r5_trip_budget.py` (`results-budget.json`). Datasheet limits used for the op amp and comparator are **not yet
audited** (they are the values the scope studies quote): confirm them in the ledger audit before any build.

## Circuit (HOT5 domain, ground = ocp_kelvin_p; nothing crosses the barrier, no J4 pin, no firmware)

| Block | Value | Note |
|---|---|---|
| Sense line | a dedicated trace from R5's ocp_kelvin_n pad to RIN | not the R33 tap; draws 1.25 µA at the trip point, so it cannot move the OCP Kelvin sense (1.25 nV per mΩ of shared trace) |
| Averager | OPA333 inverting; RIN 10 kΩ, RF 1 MΩ ∥ CF 1 µF; IN+ on ocp_kelvin_p | gain 100, τ = 1 s; VOUT = +100 × |V_R5| (the Kelvin signal is negative with respect to ocp_kelvin_p) |
| Threshold | ref25 divider 100 kΩ / 100 kΩ (0603WAF1003T5E) | 1.25 V = 12.5 mV mean at R5 = 12.5 A mean = **13.88 A RMS-equivalent** (mean = 0.9003 × RMS for a sine envelope); 12.5 µA from ref25 |
| Comparator | LMV331 (open collector, HOT5) | output pulls **HOT5_UV_RAW** low (R50 pull-up), the same wired-AND as U14's two outputs; no gate in the OCP path |
| Not fitted | the comparator, or the comparator and the averager | = today's board exactly; the nets are not used by anything else |

The scope's version put the comparator's output in an AND with OCP_OK ahead of U8 with a 0 Ω bypass. Wired onto HOT5_UV_RAW
it needs no bypass and does not touch the OCP timing path (so the OCP pickup 4.17 A, the OCP lock and the ≤ 1 µs chain are
unchanged by construction).

## Does a HOT5_UV_RAW trip latch the stage off?

By the schematic (`elec/src/power_stage_120v.ato`): HOT5_UV_RAW → u_hot5_schmitt (SN74LVC1G17) → HOT5_OK_HOT → the same
HOT-side OK chain as OCP_OK → U9 → BUS_FAULT_ISO → the controller's asynchronous permit-latch clear (comment at the `r_bf`
resistor: "the controller's asynchronous permit-latch CLR"; line 622 "hardware restart inhibit through the controller latch").
So it is as hardware as the existing HOT5-UV and REF25-watchdog trips. **The latch itself is on the controller, outside this
repo**: a bench check must confirm that PERMIT stays low after the averaged signal decays below the threshold (about 1 s after
the stage stops) until RESET_N.

## Trip window (true power-stage current; `r5_trip_budget.py`)

- Highest regulated true I_ps = 13.5 − I_aux = **13.24 A** (I_aux 0.26 A); the 15.0 A plug total is I_ps = 15 − I_aux =
  **14.11 A** at the highest aux (0.887 A).
- Nominal trip 13.88 A. Error terms (datasheet maxima, to confirm): R5 1 %, ref25 0.1 %, divider 0.2 %, RIN/RF 0.2 %,
  LMV331 offset 0.56 % (7 mV), **LMV331 bias × divider 1.0 %** (250 nA × 50 kΩ), OPA333 offset 0.08 %, OPA333 bias × RF 0.02 %.
- RSS 1.55 %: window 13.67–14.10 A, which is **+3.2 % over the highest regulated hold** and just under the 15 A cap. Worst-case
  sum 3.16 %: low corner 13.45 A (+1.6 % over the hold), high corner 14.32 A (**over the 14.11 A cap**).
- So the trip is a backstop with a narrow window, and the form factor (burst mode raises RMS/mean) is an open term on top. It
  needs a bench calibration (mean(R5) / true-RMS line current over the pan grid, ±3 %), and then a fitted threshold divider
  value per board if the spread is wide; otherwise the RMS-to-DC converter option of the study.

## Open before a build

1. Audit the OPA333 and LMV331 datasheets (input range with IN+ on the ground rail, offset, bias, output sink, supply 5 V HOT5)
   and the C30878 / C34731 stock; reduce the comparator-bias term if the audit shows it larger.
2. There is no DNP mechanism in this repo's BOM flow: a "not fitted" block needs one (BOM/CPL exclusion, the stock gate,
   the CPL audit and the ledger all count every placed line).
3. Placement: the scope found the largest free legal rectangle near U3/U8/R32–R35 to be 8 × 6 mm; the block (2 SOT-23-5
   ICs, about 9 passives, 1 µF and 1 MΩ parts) needs a real placement pass and D5 8.0 mm, HOT↔HOT 3.2 mm checks.
4. Gates to re-run after copper: OCP lock, OCP pickup 4.17 A, Kelvin band (69.18–114.57 A, floor 64.17 A), return_path19.
5. Bench rows: no nuisance trip at the 13.5 A hold; trip with the firmware limit defeated; mean / RMS ratio; PERMIT stays low
   after the decay (OPEN-ITEMS, a new row when built).

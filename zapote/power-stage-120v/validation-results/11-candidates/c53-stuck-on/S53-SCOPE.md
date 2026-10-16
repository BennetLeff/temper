# Stage 53 scope (layout stage on the s52 board of record)

Decided 2026-10-16 from the certifier pre-review checklist
(`08-manufacturing-package/native-21/owner-items/CERTIFIER-CHECKLIST.md`). The prototypes are bench
units, not certification samples. A provision goes on them only when it is cheap now and
costly later (an inlet or HOT-side re-layout after a lab "no"), or when it protects the bench
unit. s53 starts after s52 (BOM-only: B32643H bank, L1, C3/C4, BANK H/B silk) is integrated as
DECISIONS 74. It is recorded as its own DECISIONS entry when adopted.

## In scope

| # | Item | Source | Fit on proto | Size / cost (desk) | Gate to re-check |
|---|---|---|---|---|---|
| 1 | S10: 7 HOT-side return-path opens (bus_fault_hot ×3, ocp_ok_hot, ovp_ok_hot ×2, U45.1 GOOD) | OPEN-ITEMS S10 | n/a (copper) | reference copper at the vias on In1 / In2 | stage-28 OCP lock, OCP pickup 4.17 A, Kelvin band (≥ 44 A min, floor 64.17 A) |
| 2 | Hardware average-current trip on R5: zero-drift amp (OPA333-class) averaging the Kelvin signal over ~1 s, TLV3201 comparator, AND with OCP_OK into U8. Latches through BUS_FAULT → interlock → PERMIT. HOT5 domain only: no barrier crossing, no J4 pin, no firmware | Checklist 11 / 13; `c53-line-current-f1/README.md` §A | Fitted on ~half the lot; 0 Ω bypass on the rest (s51 behaviour exactly) | 3 ICs + ~9 × 0603, 50–70 mm², ~$3–4; largest free rectangle near U3/U8/R32–R35 is 8 × 6 mm, so it needs a real placement pass | Same as item 1 (shares the OCP area); trip ~14.1 A RMS-equivalent, power stage (6.5 % above the 13.5 A hold); D5 8.0 mm |
| 3 | Inlet series mains cut, DNP: 2 × Omron G2RL-1A-E (C231362, UL 41643, 16 A) in L and N between `l_filt` and BR1.2, downstream of the PS2 / PS3 / J3 / F2 / LINE_ZC taps. Coil from PS2 V24_RAW (so the TCO also opens the bus). HOT-side coil driver plus one SELV → HOT opto channel footprint | Checklist 14; `c53-stuck-on/README.md` §(a) | DNP; contact pads bridged with a hand-fitted 14 AWG link | ~1,000 mm² with 8 mm keepouts + ~100 mm² driver; ~$3–5 / board at 500 when fitted | 15 A copper L1 → BR1 re-cut and its cu_temp_basis row; RES_A / D5; enclosure fit; trigger source pin is a two-board question (J4 full), so the opto input lands on a DNP header for now |
| 4 | F1 wire-out tabs: two ≥ 25 A tab holes under the fuse body in the 17.8 mm strip, so F1 can move to an off-board Class CC holder if clips are refused | Checklist 9; `c53-line-current-f1/README.md` §B | Unfitted (clips stay) | strip already exists; tab rating to confirm | ≥ 3.2 mm clip-to-`l_f` air gap; F1-RECOMMENDATION |

Priority if space forces a cut: 1, 2, 3, 4. A provision that doesn't fit is dropped with the
reason in the stage DECISIONS entry.

## Not in scope (decided)

- **Heartbeat watchdog (stuck-on option b):** redundant with the controller TPS3823 (GPIO18 →
  interlock, 0.9–2.5 s), covers no stuck driver, no shorted FET, no "running but wrong"
  firmware; no free GPIO or J4 pin. `c53-stuck-on/README.md`.
- **R130 → AC05-CS:** no 0.15 Ω value exists (1–100 Ω only); a 1 Ω swap moves the fault case
  (980 → ~170 A, 0.3 → ~2 W, D10 body). Answer the lab on paper; revisit only on a "no".
- **AMC1301 / CT / Hall line-current measurement:** measurement only (firmware still limits),
  no HOT5-facing barrier spot, J4 full, no free controller ADC, AMC1301 / AMC1300B out of stock
  until 2027, ACS773 7.2 mm creepage < 8.0 mm. An external power analyser checks e_est on the bench.
- **Class CC PCB holder:** none exists single-pole PCB-mount; LPSC / CHCC are DIN-rail.
- **S6 CMTI:** closed with no BOM / layout change (`s6-cmti-2026-10-16/README.md`).
- Lab-dependent items (crest-RMS re-layout, inner pull-backs, laminate, reinforced isolators,
  supply modules, Class B, H6 self-test): wait for the lab answer.

## Bench items these provisions add

- Stuck-on injection: DIS jumpered off, run to the ceiling, time the TCO opening (also sets S15's
  trip temperature). Bench units run behind an external, hand-operable series mains cut until
  item 3 is fitted.
- Item 2: no nuisance trips at the 13.5 A hold; abnormal-test dry run with the firmware limit
  defeated; mean(R5) / true-RMS line-current ratio over the pan grid (needs ±3 %; otherwise an RMS
  converter replaces the averager).
- Item 3 (if fitted later): contact temperature at 15 A, closing into the 18.4 µF bus (weld risk,
  no inrush limiter), open-under-load.
- Item 4 / F1: clip temperature at 15 / 16 A in the 61 °C bay; rejection-tip retention in the clip.

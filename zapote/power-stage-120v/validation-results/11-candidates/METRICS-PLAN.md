# Metric-by-metric improvement plan (2026-10-13, after stage 22)

QUEUE.md is organised by candidate. This file is the same work seen per scorecard metric: what moves each metric, by
how much, and what blocks it. Every move must also pass the datasheet-ratings ledger
(`native-21/verification/datasheet-ledger/`, in progress): a candidate that improves a card metric but breaks a part's
rated limit or its approval basis is rejected.

"Ceiling" means the next gain needs a different architecture or a metric restatement, not more layout work.

| Metric | 19c → now | Next moves (source) | Expected | Blocked on |
|---|---|---|---|---|
| Fault-copper ratio | 0.208 → 0.993 | Ceiling. The narrowest row is the TO-247 drain tongue, a device terminal, not board copper (QUEUE 21 note). Restate the metric to exclude device-terminal-limited rows; the board copper itself is then above 1. | Restated ≥ 1 | Nothing (metric definition) |
| OCP pickup (limit 6.5 A) | 8.71 → 4.17 A | Near its floor: KELVIN_N runs under its pour and ocp_thresh is on one layer. The remaining loop is the R5 sense-finger fan-out; little left for the effort. | about 3.5–4 A | — |
| Return-path open changes | 39 → 37 | The rest are PERMIT / BUS_FAULT / BIAS lines crossing the U32/U33 isolation void, reported but not asserted (DECISIONS 19c). A reference-transfer cap at each crossing (as C153–C156) could take some; low value, since these lines only disable. | 37 → about 30 | — |
| B3 hot spot (28 A, h25) | 136.0 → 135.1 °C | FET bond line ≤ 50 µm (r2-thermal); R5.4 MOT margin; F12 (L1 at 15 A, a B3 input change); BR1 MDD GBJ2510 at 0.05 V lower VF (−0.5 W). | −1 to −4 °C | Bond line is an M11 assembly spec; MDD drawing (body thickness in the sink stack) |
| BUS_P current span (3 %) | 4.13 → 2.92 % | Thin margin. Widen the BUS_P neck nearest BR1 when the BR1 / J11 corner is next re-laid (candidate 28 touches it). | about 2.5 % | Rides on candidate 28 |
| Bank margin at 28 A | 1.105 → 1.022 | A 6th bank cap brings it to about 0.85 but costs a placement and $; or a 120 nF member. Hold unless F12 / the tank basis changes. | — | Not worth it now |
| Kelvin trip band | 67.72 → 67.77–116.44 A | Set by hardware tolerances (R5 75 ppm, divider 0.1 %); layout leakage term already 2 A. | — | — |
| Parts cost at 500 | $231.94 → $223.10 (stage 26: about −$0.82) | Delete PS1 −$6.4 to −8.4 (candidate 23). ISO6721FB −$1.80 (candidate 24). U10+U11 → TLV3202 −$0.63. Samsung 1210 10 µF −$1.47 (needs its DC-bias curve). Quote-dependent: C5/C6 at LCSC reference up to −$9.9, L1 up to −$7.8 (owner quotes). Owner decisions: F1 6.3×32 fast fuse −$26 to −30; DC-link clamp 2 J target −$19.64. | −$10 now; −$27 with quotes; −$75 with owner decisions | Owner and certifier for the big items |
| Placements | 357 → 349 | Candidate 24 −12; candidate 23 −1 or more; TLV3202 −1. | about 335 | Candidate 24 needs FMEA |
| BOM lines | 92 → 91 | Candidate 24 −1 or 2; candidate 23 −1; TLV3202 0 (+1 −1). | 88–89 | as above |
| Hand / consign lines | 23 → 22 | Metric counts every THT line, so it moves only by deleting lines. Use `consign_lines` (below) for the procurement side. | — | — |
| Lines with no LCSC code (new) | 10 → 8 | F2 → Littelfuse 0215 (C142723) −1 (candidate 28). D3/D17: Brightking C522439 exists (stock 0). U1/U2: CMTI driver 2EDR8259H (candidate 25). J3/J11: a stocked VH-family header. | 8 → 5 | Stock at LCSC for two of them |
| Zero-stock lines | 10 → 9 | UCC21550 (candidate 25); ISO7710 ×4 (candidate 24); L1 (candidate 23 with SC-20-201). | 9 → 6 | as above |
| JLC Extended lines | 61 → 62 | The cheap Extended → Basic work was done on 2026-10-09; JLC Basic has no LVC1G, TL431 or LM339 parts (research/bom-simplification.md). Each Extended line is $3 per order, so it matters for prototypes only. C49678 is Basic in JLC's live record but labelled Extended: fix the label (−4 lines on the card). | 62 → 58 (label) | — |

## New candidates from the outside review (13-external-review-2026-10-13)

- **27: J1 to a terminal with ≥ 20 A UL use-group B** (FINDINGS #4 and #11). Today's 1711725 is 15 A cULus / 10 A
  CSA against 13.5–15 A in normal use. This is a safety and approval item, so it ranks ahead of cost work. The
  F1-overload coordination note follows it.
- **28: F2 → Littelfuse 0215 3.15 A (1.5 kA) in a 646 holder with a 648 cover, plus a 0.15 Ω cemented
  wirewound limiter** (F4, `g06-g08-g10-supplies-sense-io/f2/PARTS-2026-10-13.md`). The bound is
  784 A, with a 1.91× margin. Littelfuse publishes no clearing I²t, so the limiter's pulse survival is open: AC05 holds
  about 125 A²s against an estimated 130 A²s; AC07 (220 A²s) has no LCSC stock. Installed height is about 14.5 mm, so the
  enclosure fit gate must pass. A bench short at J11 with the resistor fitted settles it.

## Order

1. Stage 26 (BOM only, polymer cap): in the chain now.
2. Candidate 27 (J1), then 28 (F2): both are safety deficits with board-only fixes.
3. The C49678 label fix and the metric restatements: free.
4. Candidates 23, 24 and 25 when their external inputs arrive (controller, FMEA, D2 grid).

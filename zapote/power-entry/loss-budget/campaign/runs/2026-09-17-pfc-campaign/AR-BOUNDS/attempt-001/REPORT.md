# AR-BOUNDS attempt-001 — bounds for the internal discharge loop R and L

Task **AR-BOUNDS** · Attempt **attempt-001** · Campaign 2026-09-17-pfc-campaign · engineering_verification.
Contract C1.1 `0accd9bc…a825d6`. Dispatch `source_revision` `8781fc51…` **equals** worktree HEAD.
Source-only; no bench, no procurement, no CAD/BOM edit, no solver, no commits.
Output directory: `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-BOUNDS/attempt-001/`.

**Hypothesis / changed variable.** The AR-MERSEN screened region `{400·L ≤ R ≤ 0.64013 Ω}`
(142 of 400 cells) is located on the *real* loop rather than on a sweep. Changed variable:
the loop's component R/L decomposition, derived per term with an explicit bound direction.
The circuit and the frozen envelope are unchanged.

**Headline.** Every term that can be sourced is bounded and *points inside*; the two
semiconductor failed-short residuals and the bank-ESR minimum are **null**, so neither region
boundary is closed. Verdict: **INDETERMINATE** — inside is plausible on all sourced evidence,
but not established. No promotion; this is a screen, not coordination, melting or clearing.

## 1. The loop, and an input substitution that had to be recorded

`bank+ (PFC_BUS_PLUS_390V) → shorted U10 (C3D20065D) → a1 → U9 (STW65N65DM2AG) → bank− (PFC_BUS_MINUS)`
(AR-FAULT netlist; U10 failed short, U9 healthy/on in case (a) or itself failed short in case (b)).

**The dispatch's board is not the loop board.** `pcb/temper.kicad_pcb` (00a27419…) contains
**zero** occurrences of `PFC_BUS_PLUS_390V`/`a1`/`PFC_BUS_MINUS`; it is the 6-layer product board
(`+170V_BUS`, `DC_BUS_RTN`, `GATE_HS/LS`, no boost stage). Geometry was therefore taken from
`zapote/power-entry/shunt-repair/candidate/section.kicad_pcb` (34e6fba9…), the board the delivered
AR-FAULT netlist was extracted from (its `source-manifest.json` records `board_sha256 = 34e6fba9…`).
Recorded in `raw/capture_failures.json` and `inputs.json`. F2 (`A70QS50-14F`) is the AR-PROTCKT
bus-side candidate, not present on this board; it is treated as a series candidate insertion.

## 2. Component decomposition — every term with a source and a direction

| Term | Value | Source | Direction |
|---|---|---|---|
| Bank ESR (4×LGX2W561MELC50) | **≤ 0.11842 Ω** | Nichicon LGX: tan δ max 0.20 @120 Hz; `ESR = tanδ/(2πfC) = 0.4737 Ω`, ÷4 | **upper bound** (ESR falls with f) |
| Bank ESR minimum | **null** | no minimum / HF ESR published | unsourced — no lower bound |
| Fuse R (A70QS50-14F) | **4.64 mΩ** | Mersen: 11.6 W @50 A → `R = P/I²` | **HOT figure**; upper bound on the cold onset R (PTC) |
| U9 Rds_on, healthy/on | **0.042 typ / 0.05 max Ω @25 °C** | ST datasheet Table 5 | upper bound **at 25 °C only**; hot value not published |
| U9 Rds_on, hot | **null** | Fig. 10 only, no numeric value | unsourced (WORKER.md forbids 25 °C→hot promotion) |
| U9 failed-short residual | **null** | not published | unsourced |
| U10 failed-short residual | **null** | not published | unsourced |
| U10 forward model (context only) | RT = 0.055 Ω/leg @25 °C | C3D20065D `VfT = VT+If·RT` | forward model, **not** a short residual |
| Copper R | **10.29 – 20.49 mΩ** | `raw/compute_bounds.py` over the board | lower @20 °C/nearest cap, upper @100 °C/farthest |
| Copper L | **75.8 – 2815.5 nH** | same script, current-sheet model | lower/upper by return-path assumption |
| Bank/fuse/package internal L | **null** | not published | unsourced, additive ≥ 0 |

The fuse's own resistance is the catalogue's **hot** (thermal-equilibrium at 50 A) value; because
the element's resistivity rises with temperature, the cold resistance at fault onset is lower, so
4.64 mΩ is an upper bound at onset and a typical value while hot.

## 3. Copper geometry and the return-path assumption

`raw/compute_bounds.py` planarises the three loop nets' ≥3 mm power copper on
`section.kicad_pcb` (0.07 mm Cu on both layers, 1.44 mm core), snaps the loop pads
(U9/U10/U36–U39/U40/U12) onto it, and extracts the least-resistance path
cap+→U10→U9→cap− for each of the four bank capacitors. Per-cap path lengths are 194–358 mm at
an area-weighted effective width of 4.6–5.7 mm. Excluded: <3 mm sense/control routing (it cannot
carry the kA discharge) and the off-path `PFC_BUS_MINUS` B.Cu zone.

Copper **L = µ₀·h_eff·length/w_eff**, with the **return-path assumption stated**:
* lower — return directly beneath the forward path, `h_eff = 1.44 mm` (core);
* upper — return horizontally offset by the measured worst-case separation (34.5 mm, cap U37).
The assumption dominates: 75.8 nH (tight) to 2815.5 nH (spread), a 37× range.

## 4. Frequency basis

The discharge is broadband: `1/(2π·L/R)` ≈ **0.5–300 kHz** over the bounded (L,R). The only
published bank figure is tan δ at **120 Hz** (its lowest-frequency, highest-ESR point), so that
ESR is an **upper bound** at the discharge frequency. For copper, skin depth at 100 kHz is
0.209 mm > 0.07 mm copper, so the DC copper R is a **lower bound** on AC copper R; proximity/edge
effects over 8 mm traces are not modelled. Each direction is stated per term above, so the DC
figures are bounds in the safe direction for their respective uses.

## 5. Location against the screened region

Region `{400·L ≤ R ≤ 0.64013 Ω}`; `0.64013 = E/280 A²s` (pre-arcing action screen, E = 179.2376 J).
* Sourced sub-total `R ≤ 0.1936 Ω` (bank 118.42 + fuse 4.64 + U9 25 °C max 50.0 + copper 20.49 mΩ)
  and copper `L ≤ 2.82 µH` → the sourced box sits **inside** the region.
* **Lower boundary** `R ≥ 400·L` requires total `L ≤ R_lower/400 = 25.72 µH`; the copper L is
  ≤ 2.82 µH (≈9× margin), but the unpublished internal inductances keep this from being closed by
  sourced data alone.
* **Upper boundary** `R ≤ 0.64013 Ω` is not closed: the two failed-short residuals are null and
  could add > 0.4466 Ω.

## 6. Controls, case census, evidence

* Controls reproduced: model constants `C = 2240.47 µF`, `V = 400 V`, `E = 179.2376 J`; the 400-cell
  grid/R-max `0.640134 Ω`; the AR-FAULT netlist node set. Source-only → solver cases expected/
  attempted/valid/failed/unsupported/unrun = **0/0/0/0/0/0**; candidate parts 1; primary sources 6.
* `zapote-claims claims.json` → **exit 0**, "No violations detected by implemented checks
  (26 claims, 4 protection claims, 0 promotions)" (`raw/checker/out_claims.txt`). No promotions:
  completion is deliberately **not** advanced.
* `check_fault_loop.py --netlist raw/sources/netlist_fault_loop.json --loop-nets
  PFC_BUS_PLUS_390V,PFC_BUS_MINUS,a1 --assignments raw/assignments.json` → **exit 0
  FAULT LOOP CONSISTENT**; the U12 negative control is rejected (exit 1) because U12 has only one
  terminal on the loop nets. Assignment magnitudes are illustrative connectivity fixtures, not bounds.
* Unresolved: U9/U10 short residuals; hot U9 Rds_on; bank-ESR minimum; component internal L; the
  fuse/copper withstand I²t and the A70QS DC let-through (not this task). A clean checker run means
  no implemented check fired — it is not proof of correctness.

## 7. Recommended next observation

One kA-scale pulsed measurement (or a qualified shock-test record) of the failed-short residual of
a U9 and a U10, which closes the only term that can move R across 0.64013 Ω. Paired second: the
bank's 1–100 kHz ESR, needed to close `R ≥ 400·L`.

## 8. Budget, provenance, files

Wall ≈ 50 min; solver invocations 0; model/CAD/BOM edits 0; bench work none; web searches 4;
primary sources 6 (Nichicon LGX, Mersen catalogue, ST STW65N65DM2AG, Wolfspeed C3D20065D, the
delivered a70qs-conditions.json, the delivered netlist). Files and SHA-256s: `manifest.json`;
capture failures: `raw/capture_failures.json`. Deadline 2026-09-18T19:49:50Z — met.

---

**R range (internal discharge loop).** Lower bound **10.29 mΩ** (geometry-derived copper; every
other term ≥ 0). Sourced sub-total of the *known* terms **≤ 193.6 mΩ** (bank ESR max 118.42 +
fuse 4.64 + U9 Rds_on 25 °C max 50.0 + copper 100 °C 20.49 mΩ). **No closed upper bound**: the
U9 and U10 failed-short residuals are `null`, so the true R is bounded only below by sourced data.

**L range (internal discharge loop).** Copper **75.8 nH – 2815.5 nH** (geometry-derived, the range
being the stated return-path assumption); the unpublished bank/fuse/package internal inductances
are `null` and add ≥ 0, so no closed upper bound exists either.

**Verdict against `{400·L ≤ R ≤ 0.64013 Ω}`: INDETERMINATE.** The sourced box lies inside the
region (R ≤ 0.194 Ω; L ≤ 2.82 µH; `R ≥ 400·L` needs only L ≤ 25.7 µH), so inside is plausible on
all sourced evidence — but the null failed-short residuals and bank-ESR minimum mean the bounds
straddle the region and neither condition is closed. No conclusion is forced.

**Single most important missing input:** the **failed-short residual resistance of U9
(STW65N65DM2AG) and U10 (C3D20065D)** — it is the only term that can move R across the
0.64013 Ω action screen, and no datasheet publishes it.

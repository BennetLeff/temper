---
title: "MIN_BARRIER_WIDTH_MM = 12.6 was one scalar for a 27-net domain boundary — simultaneously too generous and too small"
date: "2026-08-20"
category: architecture-patterns
module: pcb-hardware-design
problem_type: architecture
component: isolation-barrier
severity: critical
applies_when:
  - "a single scalar creepage/clearance constant is enforced across a multi-net domain boundary with a wide voltage spread"
  - "a working-voltage figure is derived from a peak calculation rather than checked against the standard's own basis (r.m.s.)"
  - "a barrier crosses a switching node above 30 kHz and the applicable standard's frequency scope needs checking"
  - "a low-voltage domain is earthed (gnd tied to PE) and someone is deciding whether it is SELV or PELV"
  - "a standard clause is recorded as 'paywalled/unobtainable' — check whether a national adoption (BIS, CSA, UL) republishes it"
tags:
  - iec-60664-1
  - iec-60335-1
  - creepage
  - table-17
  - pelv
  - selv
  - per-pairing-derivation
  - working-voltage
  - rms-vs-peak
  - annex-l
  - standards-recovery
---

# `MIN_BARRIER_WIDTH_MM = 12.6` was one scalar for a 27-net domain boundary — simultaneously too generous and too small

## Verdict, up front

**`MIN_BARRIER_WIDTH_MM` is unchanged at 12.6 mm.** This document, like the
evidence it draws from, changes no design value, threshold, DRC rule, DRU,
ratchet, oracle, or config. `pcb/temper.kicad_pcb` sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` is
unchanged.

The finding is that **the single scalar was never the right shape for the
question.** The HV↔SELV(PELV) barrier is not one pairing; it is (at least) a
27-net HV domain against a 35-net LV domain, spanning a working-voltage range
from 120 V to 570.5 V r.m.s. Measured per-pairing instead of as one number,
the 12.6 mm figure is **~1.6× too generous** for the DC-bus crossing that
prompted it and **at least ~1.6× too small** for the resonant-tank crossing
that turns out to be the barrier's actual worst case.

| Pairing | Required (per-pairing) | Basis |
|---|---:|---|
| `PWR_RTN` / `ac_l` ↔ SELV/PE | 4.8 mm | Table 17 row ii (>50–125 V), reinforced |
| `+170V_BUS` / `DC_BUS_RTN` ↔ SELV/PE | 8.0 mm | Table 17 row iii (>125–250 V), reinforced |
| `+170V_BUS` ↔ `DC_BUS_RTN` (rail-to-rail) | 5.0 mm | Table 18 row iii (functional, not reinforced) |
| `SW_NODE`/`GATE_HS`/`GATE_LS`/`+15V_LS` ↔ SELV/PE | **not determinable** | 47 kHz is outside IEC 60664-1's ≤30 kHz scope; routes to IEC 60664-4, paywalled |
| `tank-out` / `tank.c_tank1-p2` ↔ SELV/PE | **≥20.0 mm, not determinable** | Table 17 row vi (>500–800 V) proven as a floor; true figure needs IEC 60664-4 |

Of 15 enumerated netclass pairings in the actual implementation
(`feat/per-pairing-creepage-derivation`), **9 are indeterminate** — every
pairing that touches the 47 kHz switching/tank domain.

## What was believed vs. what was measured

**Believed** (the state this session started from): `MIN_BARRIER_WIDTH_MM =
12.6` is the reinforced-insulation figure for this board's mains/DC-bus↔SELV
boundary, derived from IEC 60335-1 Table 17. The number's correctness had
never been checked against which Table 17 *row* it actually corresponds to,
or against whether a single row can represent a boundary this wide.

**Measured, this session:**

1. **12.6 mm is Table 17 row iv (>250–400 V)** — a row that fits a 230 V
   design, not this 120 V one. Commit `0cbc04248`
   (`docs/evidence/2026-08-19-table-17-row-determination-hv-selv.md`), primary
   text: IS 302-1:2008 (the BIS/RTI-Act adoption of IEC 60335-1) and IS 15382
   (Part 1):2003 (the BIS adoption of IEC 60664-1), both retrieved and
   page-verified this session.
2. **The doubler midpoint is Y-capacitor coupled to PE, not PE-bonded.**
   `elec/src/modules.ato:932-936`: *"Y-capacitor: PE bonding from doubler
   midpoint to protective earth. Class I appliance pattern: provides EMI
   return path from the power return net to PE without a DC short."* The
   Y-cap is a ~MΩ-at-60Hz impedance, not a hard bond — so `+170V_BUS` is a
   **±170 V half-bus** referenced through that impedance, not a 340 V rail
   referenced to earth. Independent, naming-independent proof:
   `elec/src/modules.ato:877`, `assert c_bus1.voltage_rating >= v_bus_half *
   1.25` with `c_bus1.voltage_rating = 250V` and `v_bus_half = 170V` —
   250 ≥ 212.5 passes; 250 ≥ 425 would not. Verified live in this worktree.
3. **IEC 60664-1 cl. 3.2.1.1** (as IS 15382 Part 1, embedded text layer, not
   OCR): *"The basis for the determination of a creepage distance is the
   long-term r.m.s. value of the voltage existing across it."* Creepage is
   dimensioned on r.m.s., not peak. Corroborated inside IEC 60335-1 itself:
   cl. 29.1.5 says "peak" explicitly when it means peak, and is a
   *clearance* clause, not a creepage one; Table 17 NOTE 3 floors working
   voltage at the *rated* (r.m.s.) voltage, which would be incoherent on a
   peak basis.
4. **Per-pairing figures, both readings of the neutral NOTE considered:**
   narrow reading (midpoint at neutral potential) gives 170.0 V r.m.s.;
   propagating reading (midpoint treated as at phase potential, 170 V DC +
   120 V r.m.s. superimposed) gives √(170²+120²) = 208.1 V r.m.s. **Both land
   in Table 17 row iii** (>125–250 V, 42 V of headroom to the row boundary at
   250 V) → 8.0 mm reinforced. Only a peak basis (170+169.7=339.7 V) reaches
   row iv, and cl. 3.2.1.1 rules the peak basis out for creepage in terms.
5. **The tank crossing is the barrier's real worst case, and it is above the
   applicable standard's frequency scope.** `tank-out`/`tank.c_tank1-p2` are
   measured in this repository at **570.5 V r.m.s.** (carried forward from
   `docs/evidence/2026-08-12-hv-clearance-adequacy.md`) — Table 17 row vi
   (>500–800 V) → **20.0 mm reinforced**, already 1.6× the enforced 12.6 mm.
   But this board switches at **47 kHz** (`elec/src/main.ato:134`, asserted
   20–100 kHz), and IEC 60664-1 cl. 1.1.1 scopes the document to *"rated
   frequencies up to 30 kHz"*; cl. 2.3: *"Information on the dimensioning for
   frequencies above 30 kHz is given in IEC 60664-4."* **IEC 60664-4 is
   paywalled and was not obtained.** The 20.0 mm figure is therefore a
   proven **floor**, not the answer — the true requirement is not
   determinable from anything obtained this session, and there is no reason
   to expect it to be more permissive than the ≤30 kHz figure.
6. **9 of 15 net-class pairings are indeterminate for the same reason** —
   every pairing touching `SW_NODE`, `GATE_HS`, `GATE_LS`, `+15V_LS`, or the
   tank nets. `scripts/check_insulation_pairings.py` is red in CI pending
   the standard (`b1e4adc0c`, `feat/per-pairing-creepage-derivation`).
7. **Annex L, previously recorded as unobtainable, was recovered** in the
   BIS adoption (IS 302-1:2008). It is IEC 60335-1's own complete procedure
   for arriving at a creepage figure: working voltage → pollution degree →
   material group → measure → compare against Table 17 (or ×2 for
   reinforced). Significant for what it does **not** contain: no fault
   condition, no open-neutral case, no loss-of-earth case — closing the
   argument that row iv might be reachable via a single-fault (open-PE)
   scenario. cl. 3.1.3 (*"...supplied at its rated voltage and operating
   under normal operation"*) and cl. 3.1.9 independently confirm working
   voltage is a normal-operation quantity.
8. **The ×2 (reinforced vs. basic) applies unconditionally — a separate
   question from the row, and it was also checked.** `elec/src/main.ato:753`,
   `gnd ~ pe` — the LV domain's ground is hard-bonded to protective earth.
   Under IEC 60335-1 cl. 3.4.4 an *earthed* extra-low-voltage circuit is
   **PELV, not SELV** (the repo's own naming — `SELV_LV`,
   `elec/domain_manifest.yaml`'s `SELV` label — is a naming inaccuracy under
   this reading; cl. 27.1 makes earthing an SELV circuit non-compliant
   unless it is PELV, so PELV is the only available classification once
   `gnd ~ pe` exists). cl. 3.4.4 permits three separations: (i) basic
   insulation *and* an earthed protective screen, (ii) double insulation,
   (iii) reinforced insulation. Branch (i) is foreclosed here because the
   barrier is enforced as a copper-free keepout region
   (`scripts/check_isolation_keepout.py`) spanning every layer — a region
   with no tracks, vias, pads, pour, or footprints by construction contains
   no earthed screen. Independently, and more durably: **cl. 22.27**,
   *"parts connected by protective impedance shall be separated by double
   insulation or reinforced insulation"*, has no protective-screening
   branch at all, and this board declares exactly such protective-impedance
   chains bridging `+170V_BUS` into LV-domain nets
   (`elec/domain_manifest.yaml:1054-1073`, the OVP-01 comparator and
   ADC-sense dividers). cl. 22.27 closes the door cl. 3.4.4 leaves open.

## Confidence and what remains open

| Claim | Confidence | What would raise it |
|---|---|---|
| Table 17 row iii = 4.0 mm basic / 8.0 mm reinforced for the DC-bus crossing | Medium-high | The r.m.s.-composition step (√(V_dc²+V_ac,rms²)) is this session's arithmetic, not quoted standards text — though it has 42 V of margin to the row boundary |
| Working voltage is a normal-operation quantity (no single-fault inflation) | High | Four independent primary-text supports (cl. 3.1.3, 3.1.9, Annex L, cl. 3.3.2/3.3.4) |
| Tank crossing needs ≥20.0 mm and the true figure is not determinable | High for the floor; the true value is an open gap | **IEC 60664-4** — paywalled, not obtained by any route tried (direct purchase page, national adoptions searched) |
| The ×2 applies unconditionally (PELV forecloses the cheaper branch) | High | IEC 60335-1:2020 Ed. 6 was not obtained; this determination rests on IS 302-1:2008 (adopts the 2004-based edition). A CSA/UL bulletin cited in the evidence confirms Table 17 is not frozen across editions (NOTE 1 modified, NOTE 4 added in Ed. 6) |
| Tank↔SELV (rather than tank↔bus-rail) working voltage | Medium | Never directly measured in this repository; the 570.5 V figure is against the bus rails and the tank↔earth number used here is this session's inferred bound, not a direct measurement — cheap to close |

## Re-running the determination

```
git show 0cbc04248:docs/evidence/2026-08-19-table-17-row-determination-hv-selv.md
git show 37636debc:docs/evidence/2026-08-20-reinforced-insulation-determination-hv-pelv.md
git show b1e4adc0c   # feat/per-pairing-creepage-derivation implementation + 9/15 indeterminate count
sed -n '925,940p' elec/src/modules.ato   # Y-cap / doubler-midpoint comment
sed -n '750,756p' elec/src/main.ato      # gnd ~ pe
grep -n MIN_BARRIER_WIDTH_MM packages/temper-placer/src/temper_placer/core/isolation_constants.py
```

## What was not done

- No design value, threshold, DRC rule, DRU, ratchet, oracle, or config was
  changed. `MIN_BARRIER_WIDTH_MM` = 12.6 remains enforced.
- No certification body, laboratory, or manufacturer was contacted. Both BIS
  documents were retrieved from a public RTI-Act mirror.
- No standards value was reconstructed or inferred where a document could
  not be obtained; IEC 60664-4 and IEC 60335-1 Ed. 6 are marked
  not-determinable/unverified, not estimated.
- No recommendation on what `MIN_BARRIER_WIDTH_MM` should become is made by
  this document — deciding whether it stays a single scalar, or is replaced
  by the per-pairing table, is an owner decision. The per-pairing
  implementation exists on `feat/per-pairing-creepage-derivation` and is not
  merged.

## Related

- `docs/solutions/architecture-patterns/physical-isolation-barrier-requires-domain-first-floorplan-2026-07-30.md` — the prior determination that selected PD3 and the 12.6 mm figure; this document does not revisit the PD2-vs-PD3 pollution-degree question, only the row within Table 17.
- `docs/solutions/architecture-patterns/stale-backbone-layer-workaround-2026-08-20.md` — the placement/routing consequences of the barrier once expressed per-pairing.
- Branches: `0cbc04248` / `research/table-17-row-determination`, `feat/per-pairing-creepage-derivation` (`b1e4adc0c`, `30edd0a93`), `research/reinforced-insulation-determination` (`37636debc`). None of these branches has an open PR as of this writing (evidence-only, unmerged).
- `docs/evidence/2026-08-12-hv-clearance-adequacy.md` — source of the 570.5 V r.m.s. tank working-voltage figure.
- `docs/hardware/IEC60335_CRITICAL_COMPONENTS.md`, `docs/CONNECTORS_AND_WIRING.md` — related PELV/chassis-earthing context (the chassis is a repurposed steel tube-amplifier enclosure, user-accessible on every side, bonded to the same `gnd ~ pe` net); not authoritative for this document's verdict, which does not depend on touchability.

## Verification notes

All figures above were checked read-only against `origin/` branches (`git
show`, `git log`) and against this worktree's live files
(`isolation_constants.py`, `main.ato`, `modules.ato`) by two independent
passes — this document's own direct reads and a separate verification agent
— and cross-checked a third time against a correction relayed by the task
coordinator, who had independently verified the same branches. All three
passes agree on every figure in the table above. The one minor
inconsistency found (whether the Y-cap comment starts at `modules.ato:932`
or `:934`) is a line-numbering artifact of which exact line within a
multi-line comment block is cited, not a figure discrepancy — the comment
block spans 932–936.

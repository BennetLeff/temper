# TEA determination: SUPERSEDED by external review — see tea-dossier.md §§3, 8

> Status 2026-09-19: the 408 V RMS / 560 V peak stress model below is
> withdrawn (pin 16 sits on the pre-boost `RECTIFIER_POSITIVE` node, not the
> bulk bus — proven from the compiled manifest), as is the 0.78 mm complete-
> creepage verdict and the 6.3 mm requirement for pair 14–16. Retained only
> for the analysis trail. The live record is `tea-dossier.md`.

# TEA determination: creepage governs, clearance passes, footprint fails

Answers the oracle question with retained texts + declared 120 V mains
(user, 2026-09-19). Authorities: Table 18 transcribed CITED-PRIMARY in
`docs/evidence/2026-08-12-hv-hv-creepage-determination.md` (§3.1); Tables
15/16 + 29.1/29.1.5 in `docs/evidence/2026-07-28-creepage-determination-brainstorm.md`
(§3.1–3.2); TEA2209T §7.2/§9/§12–13 pin data; PD3 cooking-appliance default
and Table-18≡Table-17-above-500 V holdings from the hv-hv determination;
29.2.4 functional-creepage clause with its clause-19-test exemption (unrun).

Classification (recorded judgment): all three pairs are intra-HOT
functional insulation — no SELV barrier is claimed on this board
(`CLOSEOUT.md` §2). Table 18 therefore governs creepage via 29.2.4.

## Working voltages at declared 120 V mains, 390 V nominal bus

| Pair | Differential | RMS | Table 18 band (PD3/IIIa-IIIb) | Required |
|---|---|---|---|---|
| 3–5 GATEHL/GATELL | mains sine ±14 V offsets | ~120 V | >50–125 | **2.2 mm** |
| 10–12 GATELR/R | mirror | ~120 V | >50–125 | **2.2 mm** |
| 14–16 GATEHR/VR | 120 V sine vs 390 VDC → √(390²+120²) | ~408 V | >400–500 | **6.3 mm** |

Available pin-to-pin surface path ≈ pitch − max lead width ≈ 1.27 − 0.49 ≈
**0.78 mm** (TEA §13 `bp` 0.36–0.49; solder mask uncredited).

## Clearance cross-check (29.1.5, illustrative)

Peak differentials ~184 V (pairs 1–2) and ~560 V (pair 3) give
V_det ≈ 1514 / 1890 V → Table 16 ≈ 0.5–0.9 + 0.5 solder ≈ **1.0–1.4 mm
basic**, below the 1.94 mm copper. Clearance likely passes — *if* Table 16
is applied to functional separations, which remains unestablished, and *if*
the 1500 V Table 15 rating survives Note 2 (transients above it need the
still-unverified MOV clamp, Q3). Moot either way: creepage dominates.

## Determined verdict

The 1.94-vs-2.0 mm copper-clearance debate was the wrong problem. The
determining requirement is **Table 18 functional creepage at PD3**: 2.2 mm
and 6.3 mm required vs ~0.78 mm available — short by ~3× and ~8×. The
footprint cannot satisfy it at these working voltages in this environment.

## Assumptions that could move this (all currently defaults, none measured)

- PD3 + material group IIIa/IIIb (cited class defaults; no CTI or enclosure
  record for this unit earns PD2 or better material).
- 120 V mains (declared) and 390 V nominal bus (tolerance/Vmax unincluded;
  higher credible bus voltage only hardens the pair-3 band).
- 29.2.4's clause-19-test exemption is available and unrun — the single
  retained path that could relieve creepage without changing copper.
- No product-standard-applicability challenge is raised here: the analysis
  takes 60335-1 as governing per the repo's retained determinations.

Design consequence: no trace move fixes this (package-surface geometry), no
pad narrowing is credited, and no numerical waiver applies. The honest tracks
are a different controller/package with compliant pin spacing, reclaiming
creepage by layout (slots/coating — each needing its own clause basis), or
the clause-19 exemption test. Which track is pursued is a design decision
outside this determination.

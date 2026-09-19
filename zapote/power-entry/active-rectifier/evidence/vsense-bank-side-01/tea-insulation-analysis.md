# TEA package-spacing insulation analysis (plan R1–R3)

Closes the plan's "which insulation standard/clause governs" question with
retained texts only. No standard text beyond what is cited by path below is
used; nothing here is stated from memory.

## Retained authorities

- IEC 60335-1 Tables 15/16 and clauses 29.1/29.1.3/29.1.5, transcribed
  CITED-PRIMARY in `docs/evidence/2026-07-28-creepage-determination-brainstorm.md`
  (§3.1–3.2): Table 15 maps rated voltage + OVC to rated impulse; Table 16
  maps impulse (330…10000 V) to minimum clearance {0.5, 1.5, 3.0, 5.5, 8.0,
  11.0} mm with interpolation (Note 1); 29.1.5 raises the determining voltage
  for higher-than-rated working voltages (`V_det = impulse + (Vpk_work −
  Vpk_rated)`); 29.1 adds 0.5 mm for soldered construction at ≥1500 V;
  Table 15 Note 2 requires raising clearances where the appliance generates
  higher overvoltages.
- NXP TEA2209T Rev 1.1: HV pins (L/R/VR/GATEHL/GATEHR/VCCHx) −5…+440 V
  operating, −5…+700 V mains transient (§9); transients must be held below
  700 V (§12, p.12). No PCB-layout clearance figure anywhere in the 19 pages.
- Campaign surge note (`AR-VERIFY/REPORT.md` §4): 1 kV L–L / 2 kV L–PE test
  levels assumed; MOV clamp ~400 V assumed with the LA-series curve UNVERIFIED
  (HTTP 403 capture failure retained).
- HVS pins (U1.4/11/15) are "high-voltage spacer; not to be connected"
  (TEA §7.2) — the manufacturer treats each failing gap as HV-relevant.

## Per-pair electrical facts (from contract + datasheet)

| Pair | Pins | Differential across 1.94 mm |
|---|---|---|
| 3–5 | GATEHL (440 V-class, floats with L) / GATELL (14 V-class, rectifier-negative) | mains-class common-mode, ≤14 V local on one side |
| 10–12 | GATELR (14 V-class) / R (440 V mains input, 700 V transient class) | same, mirrored |
| 14–16 | GATEHR (rides R) / VR (rectified bus ≈390 V + transients) | hv–hv, diverge every half-cycle |

All three sit entirely on the HOT side; no SELV barrier is claimed on this
board (`CLOSEOUT.md` §2). Any relief would have to come from the
functional-insulation (intra-circuit) class, not from a protective separation.

## Why narrowing fails on retained evidence

1. Table 16 as transcribed binds basic/supplementary/reinforced insulation.
   The transcribed corpus contains no functional-insulation clearance clause,
   so Table 16 cannot be cited to relieve these pairs — applying a
   protective-separation table to intra-circuit spacings is exactly the
   category error the repo's own audit history rejects.
2. The 29.1.5 arithmetic is illustrative only and forks on missing inputs:
   at 120 V rated / OVC II it suggests ~1.27 mm basic (1500 + (440−169.7) →
   interpolate → +0.5 solder), but the candidate declares no mains nominal,
   no OVC, no pollution/material inputs; at 230 V rated it suggests ~2.1 mm,
   sustaining the floor. A fork is not a disposition (R2 demands one outcome
   per pair with written justification).
3. Table 15 Note 2 cuts against relief: the boost/bus generates voltages
   above mains, and the transient environment above 700 V rests on an
   unverified MOV clamp assumption — the condition a relief would rest on is
   itself open (Q3).
4. NXP offers no PCB figure and affirmatively marks each gap with an HVS
   spacer pin; no manufacturer relief exists to cite.

## Disposition (R2/AE2)

The 2 mm construction floor stands for all three pairs on current evidence.
The candidate is recorded as failing the screen (wrong-build-vs-screen),
not as physically unsafe and not as qualified. Revisit only with: (a) the
product standard and insulation class for these pairs stated with clause;
(b) declared mains/OVC/pollution/material inputs; (c) a bounded transient
environment with a verified clamp; (d) the 29.1.5 computation re-run on
those inputs showing required clearance ≤1.94 mm with the justification
written into the rule.

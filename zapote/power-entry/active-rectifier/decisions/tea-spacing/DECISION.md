# TEA2209T/1 intra-package spacing decision

> **Coordinator review, 2026-09-19:** insulation acceptance remains withheld.
> [The reviewed disposition](../review/README.md) corrects the full-line-RMS
> assignment for pairs 3–5 and 10–12 and identifies a manufacturer explanation
> of the floating-conductor rule. The next action is the exact-package review
> request there; a same-package daughterboard is not an established remedy.
> The following is the original worker draft, not a qualified stress record.

**Date:** 2026-09-19  
**Board:** active-rectifier candidate, SHA `e274d8ad1181f426f731f170e46202e16f969bb751538837a45ee221c3b09ceb`  
**Scope:** U1 pairs 3–5, 10–12 and 14–16.  
**Status:** **WITHHELD — do not call the 2 mm screen a compliance pass.**

This record resolves what the retained evidence can resolve and names the
inputs that still control the construction decision. It does not waive the
Rust `1.94 mm < 2.00 mm` finding, certify the assembly, or authorize powered
operation.

## The physical finding

U1 is NXP TEA2209T/1 in the retained SOIC-16 land pattern: 1.27 mm pitch and
1.95 × 0.60 mm pads. The endpoint-copper separation for each reported pair is

```
2 × 1.27 mm − 0.60 mm = 1.94 mm
```

The three pairs are separated by HVS pins 4, 11 and 15, respectively. The
reported 1.94 mm is an endpoint copper distance. It is not automatically the
assembled air clearance or the surface creepage: lead width, solder fillet,
mask registration, package body and the treatment of the intervening HVS
metal are not measured in the retained CAD.

## Per-pair disposition

| Pair | Nets and function | Stress established by retained evidence | Clearance disposition | Creepage / construction disposition |
|---|---|---|---|---|
| **3–5** | GATEHL / GATELL; gate-drive outputs referenced to the left switching path | Nominal analysis is about 120 V RMS at 120 V mains. The 132 V RMS product maximum and gate-output offsets have not been combined into a retained worst-case waveform. | Conditional only. The recovered functional-clearance route gives a lower conditional requirement than 1.94 mm for the nominal analysis, but it depends on the adopted impulse, altitude and assembly path. The TEA datasheet gives no layout rule. | **WITHHELD.** At 125 V, recovered Table 4 reports 1.5 mm for PD2/group III and 2.4 mm for PD3/group III. The open board has no verified PD2 enclosure, and the HVS spacer path is not defined. Keep the 2 mm screen FAIL; do not waive it. |
| **10–12** | GATELR / R; gate output versus the right-side mains reference | Same nominal ~120 V RMS class; product maximum and gate waveform combination remain unclosed. | Same conditional result and limits as pair 3–5. | **WITHHELD.** Same PD/material/spacer-path hinge. The pair is not independently cleared by the fact that both pins are in one controller package. |
| **14–16** | GATEHR / VR; VR is on `RECTIFIER_POSITIVE`, the pre-boost rectified-mains node | The earlier 390–400 V bus assignment is withdrawn. At declared 120 V, the retained derivation gives a half-wave of about 84.9 V RMS (about 169.7 V peak) before the gate waveform; at 132 V it is about 93.3 V RMS. This is not a 408 V bus differential. The final waveform still needs an explicit gate-output/max condition. | Conditional only. Do not use the withdrawn 408 V/560 V stress or its clearance row. The applicable impulse and assembly path still require adoption. | **WITHHELD.** The pair does not receive a special bus-based creepage verdict. Its result is governed by the actual working-voltage waveform, PD/material group and spacer-metal path; all are not closed for this assembly. |

The pair 14–16 correction is material: pin 16 is on `RECTIFIER_POSITIVE`, not
`PFC_BUS_PLUS_390V`. The 390 V bank energy and the 408 V differential therefore
cannot be transferred to this intra-package pair.

## What governs, and what does not

The 2.00 mm value in `elec/src/constraints.ato` is a **construction screen**.
It is a useful fail-closed floor, but neither the NXP datasheet nor the
recovered standards say “2 mm for every TEA2209T HVS-separated pair.”

The NXP source identifies the HVS pins as “high-voltage spacer; not to be
connected” and gives terminal voltage limits. It supplies no PCB clearance,
creepage, pollution-degree, CTI or spacer-metal rule. Terminal absolute
maximums are not insulation-coordination requirements and must not be used as
pair differential stress.

The recovered IS 302-1 text gives the functional-insulation route: functional
clearance is handled by its clearance table and creepage measurement is
delegated to IS 15382 (Part 1). The recovered IS 15382 text uses the highest
RMS working voltage for functional insulation, uses the expected impulse for
clearance, and uses its Table 4 for functional creepage. It does not, in the
retained running text, state how a floating/intervening conductive HVS pin is
counted in a creepage path. The endpoint 1.94 mm therefore cannot be promoted
to either a complete clearance or a complete creepage measurement.

At the recovered 125 V boundary, the reported group-III values are 1.5 mm for
PD2 and 2.4 mm for PD3. Those numbers are conditional table entries, not a
decision for this assembly. The current open board has no verified gasketed
compartment, so the production environment cannot claim PD2 yet. The product
documents also need one authoritative market scope: the active unit is written
for 120 V RMS ±10% US operation, while older project documents still mention a
230 V variant. If 230 V operation remains in scope, this footprint cannot be
dispositioned from the 120 V rows.

## Engineering decision

The current standard SOIC-16 layout is **not ready to be accepted as the final
insulation construction**. The evidence does not justify a numerical waiver,
but it also does not justify claiming a precise creepage deficit until the
following are fixed:

1. Product owner: freeze this unit as US-only 120 V RMS ±10%, or reopen it for
   the 230 V environment. The latter requires a new stress and spacing review.
2. Safety/mechanical owner: adopt the production enclosure and pollution
   degree. Until a PD2 enclosure is built and inspected, use PD3 for the open
   board.
3. Safety reviewer: provide the applicable current product standard/edition
   and the IS 15382 measurement rule for the intervening HVS metal, including
   the force, solder/mask and package-surface treatment.
4. Electrical owner: retain a waveform bound for each pair at the product
   maximum, including gate-drive offsets and the actual transient assumption;
   do not reuse the withdrawn 408 V claim.

If those inputs cannot be closed promptly, the bounded fallback is a controller
package/land pattern or daughterboard layout with a directly measured creepage
path that meets the PD3 requirement at the chosen material group, with a slot
or molded/package geometry where needed. Do not narrow pads, and do not add a
numeric waiver to turn the 1.94 mm result green. A specialist insulation review
is the correct alternative if the HVS spacer rule cannot be sourced.

## Qualification boundary

This decision is a construction disposition only. It does not establish
surge-clamp behavior, F2 coordination, bootstrap/startup behavior, thermal
performance, surface creepage of the complete board, or hardware safety. The
existing suite should continue to report the three TEA screen failures and the
current/thermal indeterminates until the declared environment and physical path
are resolved. A future pass requires fresh source/native/board bytes and a
retained assembly measurement or an applicable standard-based decision.

## Evidence index

- Geometry, nets, corrected pin-16 rail and limits: `evidence/vsense-bank-side-01/tea-dossier.md` §§1–6.
- Primary-source recovery and the unresolved spacer rule: dossier §§10–11.
- TEA source identity and standard/source hashes: `sources/README.md` and `sources/excerpts.md` in this directory.
- Current product environment: `docs/ENVIRONMENTAL_SPEC.md`, `docs/specs/SURGE_CONTRACT.md`, and the 120 V-only lab inquiry; their differing PD/market statements are intentionally not silently reconciled here.
- Current screen result and final bytes: `FREEZE.md` and `evidence/vsense-bank-side-01/common/power-entry.json`.

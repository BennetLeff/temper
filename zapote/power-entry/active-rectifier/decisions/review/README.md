# Coordinator review: feedback and TEA construction

This is the retained **pre-ECO review** of the bank-side board. Its recommended
feedback move is now implemented; see [current construction](../../FREEZE.md)
and the [transient result](../../experiments/f2-open/README.md). Statements
below about the saved board describe this review's identified input bytes.

Date: 2026-09-19. Status: **architecture recommendation and review handoff;
no protection or insulation qualification promoted**.

This review supersedes the recommendations in the two Luna decision drafts.
The assessed PCB remains `e274d8ad1181f426f731f170e46202e16f969bb751538837a45ee221c3b09ceb`.
No source, CAD, BOM, harness rule, or acceptance threshold changed.

## Decision 1: prefer diode-side regulation for the next ECO

Move U20.1 / the top of the UCC28180 feedback divider to
`BOOST_DIODE_POSITIVE` in the next candidate. Keep the bank, output and bleeder
on `PFC_BUS_PLUS_390V`. Preserve F2 as the only power connection between those
positive nets. This is a recommended revision, not a description of the saved
board: the saved U20.1 is still bank-side.

Why: the healthy boost switch controls energy arriving at the diode-side
output. F2 opening must not disconnect its feedback from that output. TI's
OVP observes VSENSE; bank-side VSENSE observes a different node after opening.
The fuse-open event does not itself trigger open-divider detection in either
arrangement. See TI UCC28180 Rev D, sections 8.3.4–8.3.5, retained at
`../../../shunt-repair/sources/TI-UCC28180.pdf`.

| Arrangement | F2 closed | F2 open, healthy U9 | Assessment |
|---|---|---|---|
| Bank feedback only, current CAD | Regulates bank voltage | Loses observation of the energized diode side | Do not use as the completed control architecture. |
| Bank feedback + independent diode-side supervisor | Regulates bank; new supervisor normally dormant | New circuit must detect and inhibit within a validated budget | Viable alternative, but requires another protection loop to restore observation lost by the selected feedback location. No evidence makes it the minimum solution. |
| Diode-side feedback + separate bank status | Regulates upstream of the fuse; bank voltage differs by fuse/wiring drop | Existing controller continues observing the diode side | Preferred next ECO. Bank monitoring remains a system function; dynamic protection remains unqualified. |

This comparison is an engineering judgment based on connectivity, not a claim
that an OVP response has been simulated or measured. The worker's assertion
that the last option necessarily adds more functions is unsupported. Bank
monitoring may be needed by either architecture for downstream enable and stored
energy status. Moving regulation upstream does not by itself require a second
bank OVP circuit; that depends on all other possible bank energy sources,
including the future inverter. That system assessment is not closed here.

In normal forward power flow, bank voltage is diode-side voltage minus the
instantaneous fuse/interconnect drop. Assess ripple, drop and compensation with
F2 closed; do not silently assume equal voltages or retune the setpoint upward
to compensate for an unmeasured drop. A cold fuse resistance alone is not a hot
or fault resistance model.

## The protection work that this decision does not remove

- Opening F2 removes the bulk capacitance from the controlled output. The
  remaining nominal 470 nF is not the controller's qualified output network.
  OVP delay, the existing divider filter, inductor current and continued input
  energy can produce overshoot even after a gate-off command.
- Do not select a clamp merely because the first report required one. First
  evaluate the local voltage limit against energy delivered during detection,
  turn-off and current decay, using actual component corners. If it exceeds
  the allowed excursion, select an absorber, more local capacitance, a faster
  independent inhibit, or a revised fuse/control arrangement on that result.
  Added local capacitance increases energy outside F2 and must be re-assessed.
- F2 open before startup and F2 opening while running are distinct cases.
  A controller regulating an unloaded diode side does not prove F2 continuity
  and must not issue a bank-ready signal. Local OVP is not a latched fuse alarm.
- Separate bank status must remain bank-side. Define its HOT-domain producer,
  isolated communication if required, startup sequencing, loss-of-bias state,
  and downstream permit behavior. A connector called HOT_PERMIT is not that
  implementation. Voltage difference alone cannot always prove fuse continuity
  when the disconnected bank happens to remain charged.
- Healthy U9 can potentially stop switching; failed-short U9 cannot. F1 still
  governs its line-fed short. U10 short + U9 short still requires coordinated
  F2 interruption of the internal bank loop. Neither feedback choice proves it.
- A passive rectifier does not cure a feedback problem caused by the same
  downstream boost/F2 split. It remains a bridge comparison baseline, not an
  automatic fallback for this control defect.

### Bounded next implementation

1. Make one isolated diode-side-feedback candidate: U20.1 and its route,
   authored connection, schematic, Rust connectivity expectation, source
   manifest and affected fixtures together. Keep bank/output/bleeder and F2
   boundaries fixed. Do not amend old receipts.
2. Re-run source/native parity, existing Rust checks, native ERC/DRC and the
   saved-board physical checks. Expected TEA findings stay visible.
3. Complete a single F2-open transient assessment: cold start with F2 absent,
   opening under load across line phase, and resulting no-load/restart behavior.
   Include minimum effective local capacitance, divider filtering, controller
   and gate delay, inductor current/energy and mains energy during decay. Compare
   terminal stresses against exact component limits. Missing delay evidence
   remains a qualification input, not zero delay.
4. Size additional limiting hardware only if that assessment calls for it.
   Bank supervisor implementation and fault coordination remain explicit
   dependencies before an integrated powered prototype.

## Decision 2: TEA stays a candidate; insulation acceptance withheld

The numerical 2 mm screen remains unchanged. Neither replacing the controller
nor waiving its footprint is supported by the present evidence. The specific
review request is [TEA-INSULATION-REQUEST.md](TEA-INSULATION-REQUEST.md).

Two corrections narrow that request:

1. **The line component is half-wave for all three pairs in the ideal
   conducting-bridge model.** With `v = L - R` and bridge negative as reference,
   `L=max(v,0)`, `R=max(-v,0)`, `VR=abs(v)`. If `g` denotes each gate voltage
   relative to its own source, the differentials are:

   - 3–5: `max(v,0) + gHL - gLL`;
   - 10–12: `gLR - max(-v,0)`;
   - 14–16: `gHR - max(v,0)`.

   For a sinusoidal 132 V RMS input the line component alone is
   `132/sqrt(2) = 93.338 V RMS` for each pair. This corrects the earlier
   full-line-RMS assignment to 3–5 and 10–12. It does **not** establish the
   complete working voltage: device drops, gate waveforms, commutation,
   startup/no-conduction states and tolerances still need inclusion. Do not
   assign a table band solely from this ideal calculation or from terminal
   absolute maximum ratings. No real waveform bound is claimed.
2. **There is a specific floating-conductor rule to review.** The captured
   Bourns paper, p.2 Figure 2, reproduces IEC 60664-1:2007 Example 11 and shows
   the two insulating gaps added without counting the intervening metal.
   Its drawing also conditions the individual gaps on dimension X. This is
   useful manufacturer-authored interpretation, not the applicable appliance
   standard or an NXP package approval. For the current flat-pad construction,
   the candidate gap sum is 1.34 mm, not the 1.94 mm endpoint span. Confirm the
   governing rule and assembled paths before assigning either as the verdict.

NXP UM11493 Rev 1.1 Figure 26, p.26, shows the SO16 on its demonstration PCB.
The figure is a layout precedent, not a dimensioned land-pattern or an appliance
insulation certificate. The guide does not provide a creepage acceptance rule.
Its surge results belong to the documented NXP test arrangement and do not
qualify this board. Changing to a daughterboard with the same unmodified
package and local environment does not remove the package path.

## Stop condition and work that can proceed

The next TEA input is a written, clause-specific disposition from NXP plus the
product insulation reviewer, using the prepared request. It is **not sent**:
external correspondence requires the user's authorization. No further generic
search, standards reinterpretation loop, or harness extension is scheduled.

The feedback ECO and work on other cooker units can proceed separately from
this external review. Power-entry release cannot. Retained status remains:
three TEA construction-screen failures, current/thermal indeterminates,
protection coordination unestablished, hardware qualification not performed.

## Verification and evidence

This was a circuit/document review. Source and native endpoint checks, hashes,
and an independent numerical quadrature of the ideal half-wave relation are
recorded in `verification.txt`; the latter checks the algebra only. Primary
PDF captures and their identities are in `sources/manifest.json`. No simulation,
DRC, thermal or hardware result was newly claimed. The two agent drafts are
marked superseded and retained for traceability. No claim was promoted to
qualified protection or accepted insulation.

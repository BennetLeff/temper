# Switching-model review lessons

The independent review of 9866759df found a numerical model that converged to
the wrong waveform. Corrected implementation and anchors live in
`zapote-erc::pfc_switching`; the production adapter is
`zapote-harness::pfc_loss_budget`. These are repository procedures, not new
frozen memory entries or proof of delivery to a later agent.

1. **Choose an external physical reference before a convergence target.**
   Clamped-inductive switching has current-transfer and voltage-transfer
   stages. A self-derived integral of simultaneous opposite ramps is internally
   consistent but describes different physics. The Miller-only regression was
   actually run red against the original model; the retained log is in
   `evidence/correction-02/red.log`.
2. **Use each waveform moment for its own quantity.** Mean turn-on and turn-off
   current feed this linear event-energy model. Duty-weighted MOSFET RMS feeds
   conduction. The larger mean event current is neither RMS nor a peak bound.
3. **Expose unknowns.** Qg−Qgd is not Qgs, and total Qgs is not current-transfer
   charge. Gate bias, plateau, transfer charge and loop inductance must carry
   their assumed/measured status. A peak driver-current rating is not its I–V
   curve. Mesh/timestep convergence does not remove these uncertainties.
4. **Keep loss terms disjoint and named.** Overlap excludes Eoss; switching
   includes it once. Gate network power is not all die heating. Loaded driver
   ICC cannot be summed with full Qg·V·f as independent quiescent loss.
5. **Bind curves to the exact retained source and labelled axes.** A hash for
   Rev 1 does not bind a Rev 2 extraction. Re-digitization of retained Rev 1
   Figure 12 uses its 600 V tick, not the right grid boundary (700 V).
6. **Preserve history when identities change.** The thermal replay must still
   prove its original decks, meshes and native input. The new local-thermal
   transfer validates both board-byte hashes, requires exactly the two reviewed
   Value/MPN edits, and checks all remaining native fields including extractor
   identity. It does not transfer MOSFET thermal data or certify assembly heat.
   Hash-only, extractor-only, extra-field, trace, stackup, identity and tampered
   retained-input mutations fail. Existing topology/current tests can use the
   explicitly reviewed old non-AG variant; the exact loss-source gate rejects
   it, so historical readability does not become current part acceptance.

The new nominal sensitivity exceeds the old electronics allowance. Preserve
that result as a warning about assumptions and gate-drive suitability; do not
convert it to either a measured temperature or permission to order a new part.
The common suite continues to report unresolved electrical/thermal coverage.

The common run also exposed stale GBJ native/manufacturing identities. The
shared transfer proof is in `thermal_identity.rs`. GBJ reuse additionally
requires manufacturing geometry equality after the proven board-identity
change and the existing path/envelope normalization. It passes the CURRENT
production waveform unchanged into strict replay; retained waveform and raw
solver results must match. It transfers neither boost heat nor installed
cooling applicability. The new manufacturing mutation test rejects hash,
geometry and extra-field changes. Earlier claims that the bridge replay was
unaffected were disproved by the actual common run.

## Follow-through: assurance gates and replacement research

The [four-work-package follow-through](options/RESULTS.md) separates numerical
verification, physical applicability and qualification in the common runner.
The fixed 100 µJ anchor checks one analytical waveform case; it is not a
measurement of this MOSFET. All 54 production sensitivity cases also check
waveform moments, scenario labels and disjoint term accounting. Unsupported
physical inputs keep applicability and qualification INDETERMINATE even when
numerical verification passes.

- Reject non-finite values before tolerance comparisons: `abs(NaN) > tol` is
  false. The production adapter has explicit nominal and non-nominal mutation
  regressions.
- A `Measured` enum and a `stale: false` flag are not evidence importers. This
  adapter rejects measured claims and has no route to physical qualification.
- A hash can faithfully identify an access-denied HTML page. Verify file type,
  parse the source, match exact part/revision/test conditions, then retain the
  digest. The Rust datasheet gate checks the PDF header as well as the pin;
  review still has to establish what the document actually supports.
- Turn-off gate current depends on plateau-to-low voltage; do not copy the
  high-to-plateau turn-on expression. The option arithmetic has an asymmetric
  regression for this exact draft error.
- Double-pulse current is an instantaneous switching current, not duty-weighted
  RMS. A nominal 15 V supply is neither an actual gate-high measurement nor the
  Miller plateau. The source conditions must remain attached to every screen.

These protections target the observed failure classes; they do not certify all
future models. Research arithmetic receipts remain outside production acceptance
until a candidate is integrated through the maintained source-bound model.

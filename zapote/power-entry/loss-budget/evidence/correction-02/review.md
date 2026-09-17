# Review and dispositions

Scope: correction of 9866759df in the isolated worktree, plus integration
repairs exposed by the full suite. No CAD geometry or historical FEM records
were edited. Root implemented; two native Luna review passes examined the
physical reference and shunt evidence boundary independently.

Resolved findings:

- Complementary voltage/current ramps understated hard-switch overlap.
  Replaced with separate transfer/Miller stages; an actual pre-fix red test and
  hand-calculated triangle anchors are retained.
- Mean event current was used as RMS. The adapter now supplies two distinct
  event means and duty-weighted MOSFET RMS. Production-shaped adapter tests
  enforce those connections.
- Quadrature was described as energy balance. The result now names its limited
  numerical claim. No circuit-energy or peak-voltage guarantee is implied.
- Eoss was included in a value labelled overlap, then listed separately in
  prose. Separate output fields and accounting tests prevent that ambiguity.
- The Eoss table cited an unretained revision. It was re-digitized from the
  hash-pinned Rev 1 PDF and its labelled vector axes; old evidence stays intact.
- Historical shunt replay became stale when the boost identity changed.
  A constrained transfer verifies full board bytes after exactly one Value
  and one MPN edit, complete remaining native equality and both board hashes.
  Reviewed historical board and extractor identities are checked BEFORE the
  identical-input return. Hash-only, extractor-only and identical tampered
  retained-input tests cover the review findings. Applicability stays open.
- Legacy topology/current tests used the old non-AG order code. The generic
  topology model explicitly supports that previous pin-compatible variant;
  the exact-part loss gate still rejects it. This is not shared loss data.

One reviewer raised negative individual gate resistance as a concern. Inspection
showed the new implementation already validates each input independently and
has a negative-external-resistance counterexample; no relaxation was made.

Simplification: three rubric passes (reuse, quality, efficiency) were applied
inline to the two model files under the repository's sequential-task mapping.
No extra abstraction or behavior-changing cleanup was justified. Rustfmt was
scoped to changed implementations. Independent review used native Luna
fallback; no successful external CE cross-model review is claimed. The prior
external review route was rejected by automatic approval review and was not
retried or bypassed.

Residual engineering limits are explicit in PFC-SWITCHING-MODEL.md: assumed
gate waveform/charge, operating-point Qgd, diode/inductor/capacitor losses,
startup/fault response, and installed thermal conditions. Neither the loss
budget nor this review qualifies hardware.

The common run also exposed stale GBJ native/manufacturing identities. The
shared transfer proof is in `thermal_identity.rs`. GBJ reuse additionally
requires manufacturing geometry equality after the proven board-identity
change and the existing path/envelope normalization. It passes the CURRENT
production waveform unchanged into strict replay; retained waveform and raw
solver results must match. It transfers neither boost heat nor installed
cooling applicability. The new manufacturing mutation test rejects hash,
geometry and extra-field changes. Earlier claims that the bridge replay was
unaffected were disproved by the actual common run.

Final Luna read-only review of the shared transfer and bridge adapter found no
remaining binding gap. See `thermal-transfer-review.md`. The equal-board path
continues to use the original strict replay, so earlier GBJ fixtures remain
valid without an identity waiver; its six integration tests pass.

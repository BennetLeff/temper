# Integration verification

Research baseline: `07a066e86251c13b0aec95b3d6f4ce958459db39`.
Three isolated Luna handbacks were read and integrated. The coordinator made
final corrections; integrated artifacts are not claimed byte-identical to the
worker handbacks. Requested model identity is recorded, not an inferred provider
execution receipt.

## Review corrections

- Standardized the comparison on the experiment-02 400 V bus and its
  1796.310 W nominal input, avoiding an older 389.615 V calculation.
- Distinguished real-power `P/V` from true RMS including ripple. The nominal
  retained current is 15 A; high-line matched-power RMS still needs solving.
- Removed double counting of ripple in inductor RMS. Separated thermal RMS
  ratings from saturation peak ratings. The conservative ideal-CCM peak bound
  combines noncoincident maxima and is not an exact waveform peak.
- Corrected report rounding/transcription of SiC conduction and fixed-inductor
  65 kHz ripple. L/frequency scaling is a sensitivity, not a fresh simulation.
- Rejected direct transfer of SiC -5/+18 V switching energies to 0/+15 V.
  Gate-charge energy at a different bias is explicitly an approximate scale.
- Distinguished recommended driver supply range from absolute maximum.
- Excluded a TI table row with Pout greater than Pin. Recorded the reference
  board's device-population ambiguity before per-device comparisons.
- Kept web-only Infineon material without fabricated PDF hashes. Its source
  capture limitation is explicit; the TI and SiC/driver/controller PDFs are
  retained with full SHA-256 identity.

## Checks performed

The integration check parsed all research JSON; verified the retained
experiment-02 report hash and all four captured PDF hashes; independently
recomputed L*f, conditional frequency-scaled loss, ripple, peak/energy bounds,
and SiC conduction; and checked local Markdown links. A final artifact manifest
covers all files in this research directory except itself. Git whitespace and
scope checks cover the committed research and its index link. Retained PDFs
are explicitly marked binary to preserve their source bytes.

Repository import-boundary enforcement passed (5 contracts kept, 0 broken)
after supplying the existing temper-placer source path. `make regen` and
`make regen-check` passed without tracked derived-artifact changes.

No production model, CAD or acceptance code changed, so no production Rust suite,
KiCad ERC/DRC, SPICE or FEM rerun is claimed. Existing passing receipts are not
new evidence for these candidates. These checks establish research consistency
and provenance, not physical accuracy or manufacturing readiness.

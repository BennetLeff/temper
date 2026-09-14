# Power-entry bridge redesign candidates

This is a bounded, source-bound comparison of the four U1 bridge necks. KiCad
files are complete candidate bundles; an agent made the explicit route-width
edits and the native KiCad tools are the geometry oracle. The maintained
power-entry candidate is unchanged.

## Candidates

- `baseline/` — frozen board, four 2.5 mm necks.
- `variants/same-package/` — four 6 mm necks. Native ERC/DRC are clean, but
  Zapote's 2 mm voltage-domain clearance profile rejects it (0.58 mm minimum
  pad clearance). It is retained as a rejected experiment.
- `variants/same-package-3mm/` — four 3 mm necks. Native ERC/DRC and the Rust
  construction/clearance checks pass, but the 15 A current screen remains
  unresolved. It is a constrained comparison input, not a release.

Every bundle includes the schematic, board, project, local libraries, source
manifest, exact saved-byte native export, manufacturing extraction, ERC/DRC
reports and top/bottom 3-D renders. Board hashes and check results are listed
in `variants.json`.

## Recommendation at this checkpoint

Do not promote either constant-width same-package candidate. The 6 mm result
proves that package pitch and voltage spacing, rather than downstream copper,
are the immediate geometry limit. The 3 mm result is a useful thermal-model
input, but it cannot be called 15 A capable without the current-screen and
source-bound thermal evidence. Continue with a reviewed alternate-pitch bridge
package or a shaped/pad-entry geometry that preserves the 2 mm profile; the
cooling and physical-model owners must rank those options under the shared
15 A, 40 °C-inlet assumptions.

## Evidence and limitations

Native checks are construction checks. Rust result `indeterminate` is an honest
coverage result, not a pass: external bias/precharge, waveform, semiconductor
and insulation thermal limits, EMC and powered hardware qualification remain
outside this unit. The bundle intentionally retains the failed 6 mm evidence
so a future change cannot silently repeat or waive the clearance finding.

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
- `variants/shaped-pad-entry/` — the same GBU2510A footprint with a shaped
  3 mm pad-entry section and a 4.2 mm transition into the existing 6/8 mm
  copper. Native KiCad ERC/DRC and parity are clean; the 3 mm entry remains
  the electrical bottleneck, so this is a model input, not a 15 A claim.
- `variants/alternate-gbj/` — an exact Diodes GBJ2510-F package
  (`Diode_THT:Diode_Bridge_GBJ2510`) with the datasheet and 10/7.5/7.5 mm
  nominal pin spacing retained under `sources/`. The board uses the datasheet
  polarity (pin 1 = PLUS, 2/3 = AC, 4 = MINUS), an owned KiCad-matched
  footprint library, and rerouted local copper. Fresh native KiCad DRC is
  0 violations / 0 unconnected / 0 schematic-parity; the Rust source-bound
  construction checks pass. PFC branch copper and pad-contact thermal checks
  remain intentionally indeterminate until the coupled thermal model runs.

Every bundle includes the schematic, board, project, local libraries, source
manifest, exact saved-byte native export, manufacturing extraction, ERC/DRC
reports and top/bottom 3-D renders. Board hashes and check results are listed
in `variants.json`.

## Recommendation at this checkpoint

Do not promote either constant-width same-package candidate. The 6 mm result
proves that package pitch and voltage spacing, rather than downstream copper,
are the immediate geometry limit. The 3 mm result is a useful thermal-model
input, but it cannot be called 15 A capable without the current-screen and
source-bound thermal evidence. Continue with the shaped candidate as the
immediate thermal-model input while the alternate-pitch package is re-extracted
through the native toolchain. The cooling and physical-model owners must rank
both under the shared 15 A, 40 °C-inlet assumptions.

## Evidence and limitations

Native checks are construction checks. Rust result `indeterminate` is an honest
coverage result, not a pass: external bias/precharge, waveform, semiconductor
and insulation thermal limits, EMC and powered hardware qualification remain
outside this unit. The bundle intentionally retains the failed 6 mm evidence
so a future change cannot silently repeat or waive the clearance finding.

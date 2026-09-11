# Engineering Git checkpoint — 2026-09-11

This checkpoint records the accumulated buck harness/release work and the Zapote Rust harness, RTD section, current-sense/OCP section, related RTD firmware, plans and learned procedures. It is a local Git checkpoint, not a fabrication or physical qualification release.

Included are authored sources, native CAD and libraries, model inputs, regression fixtures, procurement/release documents, reports, and retained evidence snapshots/executables. Historical source snapshots retain their original bytes, including source backup files if those bytes were part of a frozen compilation input.

Local KiCad `.history` repositories, active `.kicad_prl` UI state, Python/build caches, the working `elec/src/modules.ato.orig` backup and ignored bulk `.raw` simulation waveforms remain on disk. The selected audit directories contain approximately 2.08 GB of ignored raw waveforms; they are not in Git. Replaying a raw-waveform audit on another machine requires regenerating or separately transferring its recorded raw files. This checkpoint does not claim those large audits are self-contained in a fresh clone.

The current-sense stackup-v2 manifest originally included active UI state. KiCad later saved `.kicad_prl` and expanded `.kicad_pro` defaults. The prior 541 bound files are preserved byte-for-byte at `artifacts/current-sense-stackup-v2-frozen/`; the earlier 442-file snapshot remains at `artifacts/current-sense-before-stackup-fix/`. The new `current-sense/evidence/git-checkpoint/manifest.json` binds the current engineering state, excluding mutable UI state. Native checks were repeated for the current saved project.

Validation performed for this checkpoint:

- Zapote Rust workspace: 116 tests pass.
- Buck harness Rust workspace: 69 tests pass.
- Focused Python suites: 79 tests pass. Eleven telemetry tests require a local loopback server and pass outside the socket-restricted sandbox; their sandbox-only failures are not code regressions.
- MAX31865 firmware: 12 tests pass. State machine/transition table: 60 tests pass.
- Full firmware build is not green on this compiler: unchanged `firmware/test/test_profiles.c:24` passes pointers to an integer assertion macro. Its sources and Unity assertion definition are unchanged from HEAD. This unrelated existing failure is retained as a limitation, not silently fixed or claimed passing.
- No full repository CI, remote push, hardware test, purchase or fabrication order is part of this checkpoint.

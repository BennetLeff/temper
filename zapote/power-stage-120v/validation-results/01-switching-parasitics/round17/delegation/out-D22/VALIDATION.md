# Evidence validation

- Original D-19 settled cases reproduced before numerical changes; `reproduction.json` records the two complex-spectrum comparisons.
- Seven focused evidence tests pass (`tests.log`): raw truncation, endpoint truncation, independently known Fourier amplitude/phase/DC power, complex interference, PE reference, unchanged original fixture, and incomplete/duplicate convergence coverage.
- Repository import-boundary gate: **PASS**, five contracts kept, zero broken (`import-gate.log`). The first sandboxed attempt could not access its cache; the normal worktree-permitted run passed. No Rust/native build was performed.
- Read-only `scripts/regen_derived.py --check`: **PASS**. Repository state, seven WASM registries, 163 oracle hashes, hash-order inventory, script manifest, unwired kernels and wire formats were consistent. No derived artifact required changes.
- The final raw replay, AC-deck replay and SHA-256 manifest verification are recorded separately in `replay-results.json` and `provenance.json`.

These checks establish evidence plumbing and repeatability. They do not turn an aborted or materially step-sensitive source into a qualified emissions result.

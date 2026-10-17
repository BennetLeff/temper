# Memory read and application record

Read source: `zapote/current-sense/memory/selected-context/prepared-context.json` (2026-09-11).
Selected entry actually read: `rtd-mem-001`, “Qualify model meaning before accepting model output”; selection status `pass`, entry hash `850c1a22af0dc1a4fed5f78c94a4070c788abcd71837ff2c3e7aacba74851d80`, evidence hash `a2944b95210f8b438a616cb03339e48b873b12ec8d65ce17298599a8e3cb5158`.

Applied decisions:

1. Inspect the post-fault graph before accepting inherited claims. I traced the 10 kΩ/10 kΩ bias divider and found it is placed in parallel with the 4.99 Ω burden, so it cannot establish a 1.65 V DC bias; the standalone source therefore places the burden across the CT's floating secondary and a separately bypassed biased midpoint.
2. Keep model meaning bounded to the declared topology. The Rust model reports quasi-static peak trip and polarity symmetry only; TLV3201 propagation is a datasheet input, not a simulated timing PASS.
3. Use independent derivation and retain applicability gaps. The Rust model independently derives the trip and corners; CT frequency, volt-time, thermal rise, PCB primary connection, clamp parasitics, and physical response remain conditional or NOT RUN.
4. Preserve post-fault/current paths. The model explicitly includes both positive and negative comparator branches, rail clamps, the burden return bypass, and the threshold/bias divider paths.
5. Keep source/model identities reviewable. The deliverable records exact source references, MPNs, equations, and SHA-256 identities after artifacts are written.

Preparation was advisory only; this file records the actual read and decisions applied to this construction.

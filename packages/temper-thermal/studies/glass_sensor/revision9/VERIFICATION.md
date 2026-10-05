# R9 verification and limits

This revision adds CadQuery geometry inspection/experimental exports and a Rust process-sensitivity adapter. It changes no firmware, no historical CAD or thermal inputs, and no current-R7 CAD pointer. Base: `c4f66c38dc0180a935750767ad5b9dcb9c880d5c`.

## Thermal checks executed

- The latest standalone Rust run passes **47 tests**, including exact R7 matrix/capacity parity, analytical checks of both half-bond resistance paths, actual-versus-equivalent bond capacity, invalid/overflow inputs and equilibrium conservation.
- Rust formatting and warning-denied Clippy production/test compilations pass. No Cargo/shared extension build was used.
- **168** scenario rows are generated from two inherited package geometries, seven thicknesses, four assumed conductivities and three contact cases. All are labeled parametric/unapproved and physical `NOT_RUN`.
- Nominal R7 output parity remains M222 100 µm: 2.91 s / 2.474231°C; M222 75 µm: 2.78 s / 2.440587°C; IST308 75 µm: 2.05 s / 2.576544°C.
- Eight endpoint refinement rows show a maximum observed t90 change of 0.110 s and steady underread change of about 0.0345°C. This is numerical sensitivity, not a physical uncertainty interval.
- Four failure probes pass: incorrect source pin, incorrect geometry pin, deliberately failing Rust test and corrupted consumed source snapshot. Each fails without new physics results and removes the seeded old success receipt.
- The independent reviewer identified a source-copy/receipt race. The runner now verifies isolated consumed snapshots and attributes results to those verified snapshot identities, rather than later live-source hashes.

## Mechanical and process evidence

The mechanical README, machine-readable checks and output receipts define the exact scope of capture, joint-direction, witness and any separate bracket-candidate checks. Numerical tolerances are CAD tolerances, not manufacturing limits. Nominal contact geometry cannot establish tensile attachment or strength. The inherited upper fingers' missing upward attachment is deliberately recorded as a finding even when collision checks pass.

The separate bolted candidate has three nominal poses and STEP reimports, 18 individual bracket-insertion samples and six housing-lowering samples, plus nine minimum fastener/key-shaft checks. A further 18 bracket-insertion samples include the other two installed brackets and their fasteners, addressing the independent review's insertion-scope finding. Its positive fastener interface is an ideal matching-thread connection; no preload, thread-strength or locking qualification follows. The old finger joint remains open in the unchanged baseline. Changed candidate metal/carrier paths do not inherit the thermal outputs.

The open 100/150 µm material witnesses have valid STEP reimports, measured gaps, volumes and interface areas. Neither includes an RTD or external holding fixture. No response is attributed to a named alternate adhesive: its cured thermal properties remain unknown.

Primary sources are linked in the process decision and mechanical candidate documentation. Exact product identities and published processing information were distinguished from received-lot directions, supplier compatibility confirmation and hot installed material properties. No supplier communication occurred.

## Packaging and preservation

The final content manifest records R9 files and inherited inputs. Local Markdown/HTML links, output receipts, source hashes and `git diff --check` are checked before saving. R7's verifier still passes for historical R5/R6/R7 identities. R8's artifact/source identities are preserved. Independent findings and their dispositions are in `final-review.md`; `review.md` preserves the earlier checkpoint.

No browser rendering/accessibility verification is claimed for the static report. No hardware was purchased, fabricated, tested or qualified. No physical retention, seal, contact, induction, endurance or insulation acceptance is supplied by this work. Product loads, duty, leakage and maximum physical cut latency still need requirements and evidence. All physical results are **NOT_RUN**.

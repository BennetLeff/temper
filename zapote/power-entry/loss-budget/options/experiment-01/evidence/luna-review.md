# MOSFET experiment bounded review

Read-only review of the frozen worker files against `experiment-01/PLAN.md`,
`SOURCE-AUDIT.md`, and the independent arithmetic audit. No build or cache
mutation was performed. I found no concrete correctness blocker in the
experiment module, CLI, or registration.

Coverage confirmed:

- source manifest SHA is pinned and the incumbent part is checked;
- all three retained PDFs require `%PDF-` and exact SHA-256, with revision,
  page, and test-condition metadata;
- the 4,374-case Cartesian grid is checked for exact dimensions, valid inputs,
  duplicate/incomplete rows, finite values, model version, fixed 400 V/
  180 µH/15 A/configuration, moments, gate timings, overlap, Eoss, conduction,
  gate, and disjoint totals;
- nominal comparison is explicitly 120 V, 10 V, multiplier 1, 10 nC, zero
  added resistance, Qgd multiplier 1, and zero plateau offset;
- source/grid/NaN/config mutation tests are present;
- driver-resistance and independent Qgd/plateau envelopes are reported, with
  physical applicability and qualification remaining indeterminate;
- the standalone audit reconstructs branch moments and triangle energy without
  importing the production moment or switching functions, and rejects altered
  values/NaN and asymmetric gate-current mistakes.

Physical limitations are intentional contract behavior: datasheet charge
conditions differ, Qgd/plateau and Rds sweeps are hypothetical sensitivities,
and there is no measured waveform, thermal transfer, or hardware qualification.

## Frozen hashes

```
e8380242fdaca4a8ea09a2c1215538905689cd53211600a8f6178f0748a2c3e4  zapote/packages/zapote-harness/src/pfc_mosfet_experiment.rs
bc1b7efc07734bc4ccac16dfc805a91d7a447edcad87e85dcd469663cbf7db31  zapote/packages/zapote-harness/src/bin/zapote-pfc-mosfet-experiment.rs
72212901700a38fc740be7433500fd2972d5cb270e603ba30279963d4d131e62  zapote/packages/zapote-harness/src/lib.rs
81cb76a2328572d65e60bdd14613846a76c55b9222f0fe5455be9f3e52f80205  zapote/power-entry/loss-budget/options/experiment-01/PLAN.md
b840d242888e762744f071b241ef0d32fe02f65de8cd44e18ffcd713e8396864  zapote/power-entry/loss-budget/options/experiment-01/SOURCE-AUDIT.md
267b2d2416e5d0c41095ee84be1ee64aabc25f47f2b3b9314a52bad9c577c1a1  zapote/power-entry/loss-budget/options/experiment-01/independent-audit.rs
```

# Outstanding Zapote Rust work

This is the bounded follow-up list after the current RTD validator snapshot.
The Rust unit corpus is green, but it does not establish board acceptance or
complete coverage of the 20-rule family.

* Bind authored net domains, sensitive nets, aggressor instances, and
  prohibited pairs from a serialized contract with source instance identity;
  keep extraction as transport only. Correct the source-02 aggressor mapping
  (`U5` is `hb.power_loop.q_low`; the high-side driver is `U6`).
* Re-run the validator against the frozen source-02 native export after the
  paired 1 MΩ pullups and 1 nF C0G are physically present. Preserve native
  exporter board hash and reject stale or missing-hash snapshots.
* Add real-board mutation receipts for MPN, numbered pad/net connection,
  copper cluster, trace width, and geometry. Keep source contract unchanged
  for these mutations.
* Replace unresolved RTD fault-model cases with independently observed model
  results. An unsupported SENSE+/SENSE− case remains indeterminate until the
  circuit/model produces a result; expected labels must never manufacture
  observed findings.
* Complete direct regression reuse for the buck and MCU checks, including
  source-derived pin maps and exact firmware macro bytes. Do not report the
  full 20-rule family as covered until those checks have real inputs.
* Keep the RTD BOM discrepancy visible: `RC0603FR-0733RL` is ±1% by the exact
  YAGEO MPN sheet while `modules.ato` says ±5%.

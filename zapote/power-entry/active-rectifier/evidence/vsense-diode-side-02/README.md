# VSENSE diode-side ECO

This evidence records the bounded F2 feedback change. `r_vtop.1` (U20.1)
connects to `BOOST_DIODE_POSITIVE`, the node on the diode side of F2. The two
old F.Cu segments from U20.1 to the bank-positive trunk were removed. A new
F.Cu-to-B.Cu route connects U20.1 to the existing diode-side copper trunk;
the bank-positive copper and all other routed geometry are unchanged.

The full source-to-native replay was run first and retained separately because
its integration recipe produced unrelated baseline net/route errors. The
final board was then made by applying the explicit ECO to the clean routed
candidate. This is a construction edit, not a waiver: ERC and DRC/parity are
zero on the final bytes, while the three TEA spacing findings remain reported
by the native contract.

Final native extraction: `native.json`.
Final KiCad reports: `erc.json`, `drc.json`.
Schematic render: `section.pdf`.

## Independent coordinator verification

The exact PCB patch was replayed from commit
`a2536ee140c8bd368a4bb16a464e36620df2858f` and produced the final
`a725929a65e1756b0ad36c39373b6ab993335818344a19721cdc4b7c07ef7ab7` hash.
`routes.json` was also corrected to include the actual new two-layer path and
via: the worker initially changed its net name without changing the bank-side
coordinates. The old `evidence/routes-receipt.json` is preserved as history.

The first coordinator common-suite run failed because sandboxed pcbnew could
not initialize the macOS display runtime. It is retained in
`failed-sandbox-common`; no electrical conclusion is drawn from it. The fresh
run in `common` completed outside the sandbox: six units indeterminate and
power-entry failing on the three unchanged TEA gaps only, 70 required rule IDs,
with `suite_changed_during_run=false`. Its native ERC and DRC/parity are clean.

The fresh generated six-layer skeleton manifest remains byte-exact in
`generation-manifest.json`. `candidate/source-manifest.json` retains those
generation facts and adds a distinct `final_construction` record derived from
the final two-layer board and native extraction, plus freshly hashed inputs.
No old receipt is represented as a check of new bytes.

Tests: 99 ERC library, 5 active ERC (including incorrect bank-side feedback),
11 active harness, 7 native-report and 5 runner tests passed. Raw logs and
coordinator verification are retained here. These checks do not qualify the
F2-open transient, fuse clearing, TEA insulation or hardware.

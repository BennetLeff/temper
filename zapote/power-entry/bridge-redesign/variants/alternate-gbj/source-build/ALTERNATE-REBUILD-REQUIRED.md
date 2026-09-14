# GBJ alternate source build — completed

This directory is a source-build input copy of canonical `source-build-22` with
the bridge identity changed to Diodes GBJ2510-F. The authoritative pin map is
1=plus, 2=ac1, 3=ac2, 4=minus and the footprint is
`Diode_THT:Diode_Bridge_GBJ2510`.

The pinned Atopile 0.2.69 build and resolved export were rerun on 2026-09-14:

```text
uv tool run --offline --from atopile==0.2.69 ato --non-interactive build \
  elec/src/power_entry_unit.ato:PowerEntryUnit
uv tool run --offline --from atopile==0.2.69 python \
  /private/tmp/zapote-bridge-connections-20260914/harness-lab/circuit_export.py \
  /private/tmp/zapote-bridge-connections-20260914/zapote/power-entry/bridge-redesign/variants/alternate-gbj/source-build \
  /private/tmp/zapote-bridge-connections-20260914/zapote/power-entry/bridge-redesign/variants/alternate-gbj/source-build/resolved-components.json \
  --entry-file elec/src/power_entry_unit.ato --entry PowerEntryUnit
```

Both commands returned 0. `build-receipt.json` records the current source,
compiler-output, and resolved-export hashes; `resolved-components.json` is the
fresh export (SHA-256
`e3afc20a58548ec679b5e0015b46f94bc489fbfbe64307850e3aae2550718dff`). The
strict native bundle was then generated from this source directory and its
manifest is retained under `../native-generated/`.

The source-generated PCB is intentionally an unrouted placement artifact and
therefore has different geometry from the routed candidate. The contract is
the compiler-derived component/net graph and exact MPN/footprint identities;
those are checked against the routed board in `../source-manifest.json`.
The routed board rotates the package 180 degrees and binds local pin 1 to
`plus` and local pin 4 to `minus`, matching the Diodes drawing.

# Rev38 flat-schematic grid diagnostic

**Status: diagnostic only, 2026-09-24. U7 native acceptance OPEN.** This
repeats the temporary `source-build-05` native generation from
`NATIVE-DIAGNOSTIC-05.md` with only the strict-candidate flat-schematic
placement changed. The unreviewed 360 × 250 mm board shelf poses and frozen
Atopile source are the same. No routed Rev38 section board is released.

The prior generator used 40.0 mm columns and 30.0 mm rows, leaving many
symbol pin endpoints off KiCad's 1.27 mm connection grid and allowing tall
synthesized symbols in adjacent rows to overlap. The flat generator now uses
40.64 mm columns and sets each row center from the maximum symbol half-height
in neighboring rows with a 20.32 mm gap. These changes affect only the
diagnostic schematic placement, not source pins, nets or board poses.

| Check | Previous diagnostic | Current diagnostic |
| --- | ---: | ---: |
| KiCad ERC total | 677 | 383 |
| `endpoint_off_grid` | 294 | 0 |
| `multiple_net_names` | 0 | 0 |
| `lib_symbol_issues` | 295 | 295 |
| `isolated_pin_label` | 63 | 63 |
| `footprint_link_issues` | 25 | 25 |

KiCad 10.0.4 `sch erc --format json --severity-all` completed on the current
temporary schematic. The remaining **383 warnings** are not an ERC pass.
All 63 isolated labels were checked against the frozen netlist and correspond
to single-node compiled nets retained for board/netlist parity; they need
individual source review. The 295 symbol warnings report an empty symbol
library nickname on generated numeric-pin symbols. The 25 footprint-link
warnings report missing footprint-library registrations in the temporary
schematic environment. Both need native-library disposition before release.
A focused synthetic test covers grid alignment across columns and
rows, and a 32-pin symbol test checks that adjacent row bodies are separated.

| Artifact | SHA-256 / scope |
| --- | --- |
| Frozen source receipt | `4f07f1177fbe39eef940e665892c40285e77925ce4f4622ddbf21cd38672a7f5` |
| Temporary poses | `46d114daca00f24e90a2362ae6ef9ff2b5ac65452d31afde73842fbddf73419b` |
| Current temporary board | `0a6888909828f51b407452f4e513ce7771fe97c1d35118f6b58d8b9c353f64c7` |
| Current temporary schematic | `037944bb62e75e3522c8a415bd16fab095be7f5971b2ad2ce4f064a3dafe7252` |
| Current source manifest | `48d16962855c0096e878049e0dbea7c1c0487307c3cf7069de41257ca446f060` |

The current temporary files are under `/tmp/temper-rev38-native-05-gridfit-final`.
The unchanged board still has the 36 DRC violations and capped 499
unconnected items recorded in `NATIVE-DIAGNOSTIC-05.md`; those results are
not closed by this schematic-only change.

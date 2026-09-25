# Rev38 review-footprint and singleton-net native diagnostic

**Status: diagnostic only, 2026-09-24. U7 native acceptance OPEN.** The
current frozen source is `source-build-06`, compiled and exported with pinned
Atopile 0.2.69. It selects two review-only TPS3431 no-via DRB footprints and
one review-only LTC4368 narrow-pad MSOP footprint. Its 16-contact connector
still passes the receipt-bound audit against `cooker-source-02`. This test
uses the same **unreviewed** shelf poses and 360 × 250 mm planning outline;
it does not release the section schematic or PCB.

| Frozen or generated artifact | SHA-256 / scope |
| --- | --- |
| `source-build-06/build-receipt.json` | `a164f33463b42748eefd4474be5f225077e191eae2378448eccad69b932b3d36` |
| Compiled netlist | `913a0bf51726cb756af2384aea3ac2c949c405f612b345aedbae7ef4c0d79796` |
| Resolved export | `b75d376c9cf2eb5a14619d200f89600b6e93c72a963044cd0048f6a8ce1bf3c0` |
| TPS3431 no-via review footprint | `b3288d1d40ce1495380c84259a06266b406cf3bb1368fcb3968915f332efa2ec` |
| LTC4368 narrow-pad review footprint | `83cd146ae979c5e9e665050e8759c8dca0a6433bdf021ce0a51044443f2274ee` |
| Temporary poses | `46d114daca00f24e90a2362ae6ef9ff2b5ac65452d31afde73842fbddf73419b` |
| Temporary board | `0857361f1bdf6b92e62f47718c9dd44b04e563bae74d819b2c98e41800e79f18` |
| Temporary schematic | `339154c9e3809782da312c8d85053ee9cfea2d87196b3b20652d25be9261201c` |
| Native source manifest | `344b6ec622cebfa7a0677030f9efa801697d303c4fbf37bf7400f2cc914359a0` |

The generator's flat schematic retains a named global label and adds a
co-located no-connect marker for each of the **63 source-confirmed singleton
nets**. KiCad 10.0.4 ERC with all severities reports **zero violations**.
KiCad's exported schematic netlist matches the frozen source projection:
**295 board references, 246 named nets and 1,052 numeric
`(net, reference, pin)` edges**, with no missing or extra edges. Off-board
F2 remains the one declared assembly-only reference. `kicad-cli pcb drc
--schematic-parity --severity-all` reports **zero schematic parity issues**.
KiCad `FootprintNeedsUpdate` reports **0 of 295** placed footprints out of
date against their vendored libraries. These checks do not verify functional
pin names, operating voltages or physical insulation.

The temporary board has **7 DRC violations**: three 0.15 mm U2/U246
clearances caused by the shelf poses, three silkscreen-over-copper findings
and one silkscreen overlap. The previous eight TPS3431 0.20 mm drill
violations and seven LTC4368 0.15 mm adjacent-pad clearances are absent.
KiCad reports **499 unconnected items**, its cap on this unrouted board; it
is not a route-completion count. No tracks, independent vias, zones or
safety slots have been authored. The footprint variants remain subject to
manufacturer, fabricator, thermal, stencil and assembly review. In
particular, the 0.29 mm MSOP pad width creates a 0.21 mm **nominal** gap
against the provisional 0.20 mm copper rule, with no accepted process
margin. [TI's TPS3431 land pattern](https://www.ti.com/lit/ds/symlink/tps3431.pdf)
shows its 0.20 mm thermal vias as optional; [ADI's LTC4368 land pattern](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc4368.pdf)
gives the dimensional basis for the narrow-pad proposal. Neither source
qualifies this assembled Rev38 construction.

The temporary files are under `/tmp/temper-rev38-native-06-singletons`.
Reviewed placement, routing, full stackup/rule and insulation decisions,
native unit gate, and physical measurements remain open.

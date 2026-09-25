# Source, graph and simulation boundary

The circuit authority is `elec/src/power_entry_f2_shutdown_revb.ato`, entry
`PowerEntryF2ShutdownRevB`, SHA256
`050818ac162a1aa93ecd63325588adb2102504c8148ecbcbf0898abce2377f68`.
The accepted Atopile export is `source-07/`; `compiled-bridge.json` is the
physical-pin graph derived from that export. It contains79 components.
`f2_shutdown_revb.rs` checks source identity and compiled physical connections.
Earlier source attempts are diagnostics, not alternative accepted designs.

| Circuit element | Simulation representation | Scope |
|---|---|---|
| VD/VB987k/200Ω/5620Ω tapped dividers | Actual resistor networks and47pF high-tap filters | Nominal values; no temperature or full tolerance sweep |
| Comparator inputs | Actual22kΩ isolation and assumed2pF input capacitance | Clamp behavior and tiny-overdrive delay are not qualified |
| LM4040A25 from logic5 | Supply-qualified ideal2.5V reference | Real startup, minimum bias and reference dynamics omitted |
| Four TLV3202 detector channels | Correct polarity,55ns nominal response equivalent | Authored model; not a manufacturer worst-case timing model |
| TPS389001DSER pair | Actual sense dividers,47kΩ isolation,100pF-equivalent retriggerable132µs release,8µs falling propagation | Nominal authored supervisor model, hysteresis/tolerance omitted |
| Fast auxiliary TLV3202 channel |430kΩ/100kΩ,22kΩ isolation,13.25V nominal trip | Clears latch independently of slow supervisor fall delay |
| HCS21/HCS74 | Qualified health gate and edge-triggered retained latch | Active-low hardware CLR inverted to active-high XSPICE reset |
| Ioff input buffers and enable AND | Supply-qualified ARM/PERMIT and RUN AND clear_ok | Behavior below minimum operating voltage is an assumption |
| BSS138/driver disable | Small-MOS surrogate,1kΩ gate drive,100kΩ gate pulldown,1kΩ IN− pullup | Discrete capacitances are authored, not exact BSS138 model |
| UCC27511A split outputs | Loaded functional equivalent; independent unchanged TI model fixture | TI driver oracle does not qualify external MOSFETs |
| Power stage | Finite level-1 MOS channel, explicit capacitances, two parallel SiC diode legs | Declared physical surrogate; exact ST macro-model unavailable |

The fault fixture independently drives VD and VB. It exercises four **running**
fault channels, supply sequences/dropouts, held ARM and fresh-edge recovery.
The plant instead includes the boost inductor, local19.8µF capacitance, F2 and
2240µF bulk bank. Plant energy rows initialize a prequalified controller and
observe an armed interval before F2 opens; they do not replace startup tests.

The source's separate10Ω turn-on/turn-off resistors become one10Ω equivalent
in the functional controller because its output is already selected by the
driver state. Both physical paths remain explicit in the TI driver fixture.
The fault fixture uses12nF gate load. The power plant includes explicit Miller
capacitance in addition to that load; this deliberately heavy gate is not an
exact reconstruction of the ST total-charge curve.

`vendor/` retains the unchanged official TI UCC27511A model, its archive,
reproducer and strict measured-state checks. `device-checks/` independently
runs the actual ngspice MOS/diode DC equations against device anchors; it also
checks that the intrinsic MOS body diode is suppressed so the external body
diode owns that current. The model provenance and current/energy definitions
are in `plant/models.md` and its extractor.

## What is still unknown

The physical maximum fault current, inductor L(I,T) envelope, complete
worst-case turnoff delay, parasitic layout inductance, fuse arc/restrike and
assembly temperature bounds remain unknown. The nominal2µs/500V screens are
engineering experiment targets, not established protection limits.

In particular, **Ioff at VCC=0 does not guarantee arbitrary brownout behavior**.
The functional model forces logic off below1.65V; neither that rule nor a passing
simulation establishes the HCS/LVC analog behavior throughout partial power.
Rail-off injection calculations and the vendor driver startup tests give
specific evidence, but do not remove this device characterization boundary.

No result promotes the experiment into a hardware protection claim. The
retained54-component power board and all earlier hashed evidence stay intact.

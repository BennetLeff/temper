# Rev38 SELV supply decision inputs

**Status: U4 engineering input; supply, harness, startup and fail-low acceptance OPEN.**
This records the current source topology and the evidence needed to choose a
physical SELV 3.3 V producer. It does not select a new circuit or change the
approved [source-to-PFC section-board scope](../../../../../docs/plans/2026-09-23-001-feat-power-entry-hot-receiver-plan.md).
The source identities are the frozen Rev38 `source-build-06` receipt
`a164f33463b42748eefd4474be5f225077e191eae2378448eccad69b932b3d36`
and cooker `cooker-source-02` receipt
`21d303f769dccaaaf25049e87cd948d55de8ab19be478c9aab277f535d45baa4`.
The two-board audit proves the control-contact mapping, not a physical cable
or supply capacity; see [COOKER-ASSEMBLY-SOURCE.md](COOKER-ASSEMBLY-SOURCE.md).

## Exact source and return path

1. The selected **command source** is the existing cooker ESP32-S3. The
   [Rev38 source](source-build-06/elec/src/source_mcu.ato) has no second ESP
   and no SELV 3.3 V regulator. Its `SourceMcu38.controller_port` receives
   `SELV3V3` on header pads **1 and 9**, and `SELV_GND` on **8, 13 and 16**.
   Those are parallel contacts of one rail and one return, not redundant
   producers. The same rail powers the Rev38 source logic, expander, watchdog,
   supervisors and the SELV `VCC1` sides of the two isolators.
2. The [cooker-mate source](cooker-source-02/zapote/power-entry/passive-reva/protection/interface-integration-38/cooker-mate/elec/src/cooker_mate.ato)
   joins those five contacts to the existing `Top.vcc_3v3` and `Top.gnd`.
   Its exact 16-contact control map is in
   [SELV-CONTROLLER-CONNECTOR.md](SELV-CONTROLLER-CONNECTOR.md): GPIO13 STOP,
   GPIO21 heartbeat request, GPIO48 permit-set request, GPIO18 prewatchdog
   input, GPIO40/41 UART, GPIO42 START input, shared GPIO38/39 I²C, plus
   candidate reset-good and interlock producers on pads 14/15.
3. In that **legacy cooker snapshot**, `Top.aux_supply` takes its input from
   the old doubler positive half-bus and midpoint, produces isolated 15 V
   through IRM-10-15, and `Top.power_mgmt` uses LMR51430XDDCR to derive
   3.3 V. The cooker SELV `gnd` has a direct PE reference and is distinct
   from the doubler midpoint and Rev38 `HOT0`; see
   [main.ato](cooker-source-02/elec/src/main.ato) and
   [modules.ato](cooker-source-02/elec/src/modules.ato).
   Rev38's single PFC bank has no doubler midpoint. Replacing the old front
   end therefore removes the **input source** assumed by this IRM placement.
   Retaining the ESP or even the LMR buck does not prove a valid 15 V input
   in a one-front-end product. This is the separate
   [power-assembly boundary](POWER-ASSEMBLY-BOUNDARY.md), not a blocker on
   the Rev38 section-board port itself.

The screened physical connection is a 16-position Molex Micro-Fit 3.0
43045-1612 header with 43025-1608 cable receptacle and 43030-0007 contacts.
Its proposed cable is straight through, pad *n* to pad *n*. Cable length,
wire, derating, contact resistance, retention, strain relief and prevention
of mating with another accessible 16-way Micro-Fit assembly are unselected.
The family rating is not a completed harness rating, and the design may not
assume equal current sharing among its two supply or three return contacts.

## Quantified evidence already available

| Input | Current evidence and limit of that evidence |
| --- | --- |
| Voltage | [SELV-PORT-CONTRACT.md](SELV-PORT-CONTRACT.md) proposes **3.0–3.6 V at Rev38 device pins**, including source and harness loss, ripple, transients and temperature. This is a candidate operating envelope, not measured regulation or proof that authorization stays low outside it. |
| Rev38 port current | **100 mA** is a Rev38-only running and logic-transition design allocation. It is not a measured maximum, startup peak or demonstrated spare current on the cooker rail. The cooker ESP's separate **at least 0.5 A supply-capability requirement** remains upstream of this header; adding 0.5 A and 100 mA does not produce a total cooker budget. |
| Selected isolator examples | The two SELV `VCC1` sides have specified maxima totaling **9.6 mA** at the cited TI 1 Mbps/15 pF fixtures, or **10.8 mA** at 10 Mbps fixtures. Real input states, channel rates, output loading and partial-power behavior need a matching sum. The ISO6742-Q1 is rated to 50 Mbps, so a 100 Mbps two-device sum is invalid. |
| Other Rev38 load screens | TCA6408A-Q1 VCCI+VCCP is specified at **36 µA maximum** under a 400 kHz/no-P-port-load fixture. TPS3431 and TPS3890 list **19 µA** and **5.8 µA** maximum supply currents under their cited fixtures. Seven HCS packages have a **14 µA** static-only sum under rail-level, unloaded-input conditions. The frozen netlist's 29 × 10 kΩ, 1 × 100 kΩ and 1 × 16 kΩ direct-rail resistor census gives an intentionally overcounted **11.89 mA** screen at 3.6 V and −10% R; it is neither a whole-port maximum nor all header-supply current. Details and sources are in [SELV-SUPPLY-LOAD.md](SELV-SUPPLY-LOAD.md). |
| Rev38 startup capacitance | **1.4 µF nominal** is directly across SELV3V3/SELV_GND in Rev38; cooker-mate adds **0.5 µF nominal** to the shared rail. The combined **1.9 µF nominal** excludes effective-value corners, existing cooker decoupling, cable and other native-board capacitance. The illustrative 1.4 µF/3.3 V/1 ms linear ramp gives about **4.6 mA average capacitive current**, not a startup-current bound. |
| Existing cooker producer | The legacy IRM-10-15 nameplate is **15 V, 0.67 A, 10.05 W** before installed line/ambient derating. The LMR51430's **up to 3 A output** rating does not increase that upstream power. The source includes **2 × 22 µF nominal** buck output capacitors and a **10 µF nominal** input capacitor; effective charge and simultaneous load remain unmeasured. The 15 V rail also feeds cooker controls, driver/fan/thermal and discharge circuits. |
| Mate increment | The cooker-mate derivative adds one supervisor, four LVC gates and five 100 nF bypass capacitors. Its nominal 16 kΩ/10 kΩ sense divider draws about **0.127 mA** at 3.3 V; reset pull-up and GPIO15 pull-down each reach about **0.33 mA** in their asserted states. These state-dependent figures cannot be summed without the actual switching and output-load states. |

`source-build-06` changes only two footprint identities from `source-build-05`
and keeps all 1,054 named source pin edges, so the earlier Rev38 electrical
load census still applies to the current source. None of the figures above
is a coincident, installed-temperature whole-system current bound.

## Decisions and measurements that discriminate the supply options

| Decision or test | Required output |
| --- | --- |
| Reuse a qualified cooker rail or specify a separate SELV producer | For reuse, show a one-front-end source with an actual isolated 15 V producer feeding the retained buck, its return and PE bond, and no surviving obsolete doubler input. For a separate producer, specify its mains/HOT isolation, output protection, return and PE-reference scheme. Compare both at the Rev38 device pins under the same 3.0–3.6 V contract. Do not use the cooker-mate control-only fixture as a product power join. |
| Full cooker and Rev38 load worksheet | Inventory each cooker 3.3 V load, Rev38 port load, and direct 15 V load by startup, idle, RF transmit, cooking, fan/relay/gate-drive, fault and recovery state. Use selected-part voltage/temperature limits, output loads, measured buck efficiency and IRM installation derating. Record a coincident maximum and available margin; revise the 100 mA allocation if evidence exceeds it. |
| Startup and overlap capture | Measure 15 V source, buck input/output, both Rev38 supply contacts, far-end device pins and series port current through cold start, brownout/recovery, RF bursts, relay/fan/gate-drive overlap, I²C and watchdog/one-shot activity. Determine effective capacitance, `dV/dt`, peak and sustained current, buck current-limit/retry and any permissive pulse. |
| Harness and partial connection | Select cable length, gauge and routing; calculate and measure worst-case drop and temperature with one supply or return contact open, all supply/return contacts open, partial insertion, and powered signal pins into an unpowered end. Bound back-powering through ESP, expander, isolator and watchdog I/O. Confirm the physical pin-one orientation and prevention of wrong-assembly mating. |
| Rail order and physical fail-low | Capture SELV3V3, ESP EN, expander VCCI/VCCP and RESET_N, watchdog/supervisor release, both isolators' VCC1/VCC2, source reset-good/interlock, HOT PERMIT, HOT session, RUN and loaded gate. Include source-first/HOT-first ramps, EN reset, CPU-only reset with retained expander power, WDO trip, I²C stall, fault-latch assertion and cable opens/shorts. Required result is **physical low authorization** through every invalid or partial-power state, measured at the consuming nodes. |

The TCA6408A-Q1 has both supply pins on the same named net, but its pin ramps
and POR behavior still need native measurement. Its RESET_N is pulled high,
so an ESP-only reset need not clear retained P0–P2 outputs. The cooker-mate
`SOURCE_RESET_GOOD` producer reports supervised rail/EN release, not an
internal CPU reset; the independent source watchdog and proven finite WDI
feed tail remain necessary. The reset/interlock producer's threshold and
startup state are still only a screen in
[SOURCE-RESET-INTERLOCK.md](SOURCE-RESET-INTERLOCK.md). For either producer
choice, no source power loss or harness fault may be credited as a safe clear
until the physical HOT-side low state and loaded gate response are captured.

**Next decision:** first establish a viable isolated 15 V input in the
single-front-end product source, or select a distinct qualified SELV supply.
Then use the measured load, startup and partial-power results to decide
whether the existing LMR51430 rail and proposed connector satisfy this port.
The section-board native candidate can retain its defined external SELV
port while these product-supply measurements remain open.

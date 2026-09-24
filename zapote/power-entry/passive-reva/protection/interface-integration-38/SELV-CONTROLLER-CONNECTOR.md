# Shared cooker ESP connector screen

Status: **Rev38-side 16-contact header joined; product harness not released**.
The selected product architecture uses the existing cooker ESP and its SELV
3.3 V rail. `source_mcu.ato` now instantiates the Rev38-side header in place
of a second ESP. `cooker-mate/elec/src/cooker_mate.ato` now joins a second
header to the existing cooker source as a separate Atopile derivative. Its
native board, rail capacity, harness and physical reset/interlock producers
remain to be checked before claiming one joined product assembly.

The screened wire-to-board family is Molex Micro-Fit 3.0:

| Item | Candidate | Evidence |
| --- | --- | --- |
| PCB header, each board | [43045-1612](https://www.molex.com/en-us/products/part-detail/430451612) | 16 loaded contacts, vertical shrouded THT, 3.00 mm pitch, PCB locators and retention; Molex lists 8.5 A/contact maximum, 30 mating cycles and −40 to +105 °C. |
| Cable receptacle, each end | [43025-1608](https://www.molex.com/en-us/products/part-detail/430251608) | 16 positions, latch and polarization. |
| Female contact | [43030-0007](https://www.molex.com/en-us/products/part-detail/430300007), 32 per two-ended harness | Tin crimp, 20–24 AWG stranded wire; use the specified tooling and pull-test process. |
| Native footprint | `Connector_Molex:Molex_Micro-Fit_3.0_43045-1612_2x08_P3.00mm_Vertical` | Installed KiCad footprint has 16 numbered pads and two non-plated locator holes; compare its drill, outline and pin-one mark with a current controlled Molex drawing before release. |

The [Molex Micro-Fit product specification](https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/productspecificationpdf/430/43045/PS-43045-001.pdf)
governs mating and application derating. The listed contact maximum is not
the allowable assembled-harness current. The production 3.3 V load, cable
loss, connector temperature and concurrent startup need measurement.
The cooker ESP itself stays on the cooker board; these power contacts feed
the Rev38 SELV logic, expander and isolator sides, so the separate-fixture
0.5 A ESP allocation must not be counted as current through this connector.

## Proposed straight-through pin contract

The proposed harness connects the same pad number on both headers. The
Rev38 header has these exact Atopile joins; the cooker derivative joins the
same map to its existing ESP, while the canonical PCB lacks the mate.
Returns at pins 8 and 13 sit beside the UART and I²C pairs in the
installed two-row footprint.

| Pad | Conductor | Owner / default at Rev38 end |
| ---: | --- | --- |
| 1, 9 | `+3V3` | Existing cooker SELV rail; no HOT connection. |
| 2 | `SOURCE_STOP_N` | Cooker ESP GPIO13; Rev38 pull-down asserts STOP on an open contact. |
| 3 | `SOURCE_VALIDATED_HEARTBEAT` | GPIO21; local pull-down suppresses an open-contact request. |
| 4 | `SOURCE_PERMIT_SET_REQUEST` | GPIO48; local pull-down suppresses an open-contact clock. |
| 5 | `SOURCE_PREWATCHDOG_OK` | GPIO18 physical input to ESP. |
| 6 | `SOURCE_COMMAND_TX` | GPIO40 to forward isolator. |
| 7 | `SOURCE_RESPONSE_RX` | Reverse isolator to GPIO41. |
| 8, 13, 16 | `SELV_GND` | Return only; keep separate from `HOT0`. |
| 10 | `SOURCE_START_N` | Normally-open Rev38 switch to GPIO42; startup pull-up is on the receiving rail. |
| 11, 12 | `SOURCE_I2C_SDA`, `SOURCE_I2C_SCL` | GPIO38/39 shared with the existing UI header; one bus contract required. |
| 14 | `SOURCE_RESET_GOOD` | Reserved until an actual CPU/reset-valid producer is selected. |
| 15 | `SOURCE_INTERLOCK_N` | Reserved until a fail-low, polarity-correct producer is selected. |

Pins 14 and 15 are reservations, not permission to tie unproven signals to
the cooker circuit. Molex lists no first-mate/last-break contact on this
header, and the housing is polarized but has no unique mating-part key.
Verify safe-off during every single-open and partial-insertion case, and
prevent mating this harness to another accessible 16-way Micro-Fit. Powered
signals with an open 3.3 V or return can back-power an unpowered device;
qualify those cases at the actual ESP, expander, isolator and watchdog pins.
Determine the cable length, routing, I²C capacitance/pull-ups, UART edge
integrity, strain relief, vibration, contact temperature and mis-mate test
before selecting the connector for the joined native boards.

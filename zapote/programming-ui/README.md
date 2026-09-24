# Programming/UI service interface screen

Status: **source conflict verified; service hardware blocked**. The source
revision is `afb8b9e31cf03ef12b1cb246a89803f333dee6e0`. `sources.sha256`
binds the six files used by the ledger. The Rust gate checks their bytes and
key pin claims before it emits the deterministic matrix.

Run from the repository root:

```sh
rustc --edition=2021 --test zapote/programming-ui/service_gate_tests.rs -o /tmp/zapote-ui-tests
/tmp/zapote-ui-tests
rustc --edition=2021 zapote/programming-ui/service_gate.rs -o /tmp/zapote-ui-gate
/tmp/zapote-ui-gate .
```

The gate deliberately exits **2** after a successful source and scenario
check: the current cooker MCU mapping conflicts and the physical interface is
unselected. A scenario's `Indeterminate` verdict is a request for evidence,
not conditional acceptance. `Rejected` identifies a known incompatible
connection or reset state. The matrix's positive-looking discharge and
both-stage-stop cases remain indeterminate because a boolean claim does not
identify an independently reviewed waveform, article or service criterion.

## Source-bound findings

`elec/src/components.ato` maps UART0 TXD0/RXD0 to module pads 37/36 and
EN/IO0 to pads 3/27. `elec/src/modules.ato` connects those to the MCU's UART
interface and existing pull-up/buttons. Firmware declares UART0 GPIO43/44.
This supports a **logical SELV TX, RX, EN and IO0 candidate only**. A service
connection also needs the target 3V3 reference and SELV return; a programmer
must not drive unpowered ESP I/O. The ESP ROM may own UART0 during boot, so
product protocol sharing needs a separate decision.

The current cooker electrical source uses IO19/20 for native USB but firmware
uses those pins for bypass relay and fault status. Electrical IO17 fault input
conflicts with firmware's fault LED; electrical IO16 relay conflicts with a
reserved second RTD chip select. Firmware calls GPIO0 a reset button while
electrical source uses it as the download strap. Both buttons pull low, but
their intended actions cannot be conflated. The top-level USB and I²C signal
names in `elec/src/main.ato` are not a connector implementation. Firmware's
ADUM1250 isolation comment has no instantiated isolator in current
`elec/src`; neither I²C nor the UART port gains isolation from that comment.

The Rev38 `ESP-PIN-FIT.md` is an **unadopted allocation screen**. Its local
I²C expander can remain powered and hold a prior output through CPU-only
reset. A programmer-triggered EN reset is a power-stage event: the service
interface needs either independently verified energy isolation/discharge
before access, or measured reset-to-PFC-and-inverter-stop plus no automatic
rearm. Direct STOP timing and a retained expander output must be captured
together. None of those physical records exists in this candidate.

## Construction gate

There is no selected service connector, pin order, ESD/off-state I/O circuit,
mounting/access boundary or owner. `elec/src/components.ato` supplies a
two-pin fan header and a four-pin RTD connector, not a selected programming
connector for TX/RX/EN/IO0/3V3/return. Repurposing them or stitching several
headers together would invent a service interface. No Atopile fixture or
netlist was built for this milestone. An accepted MCU pin contract, connector,
backfeed protection, service access criterion and physical reset/stop record
are prerequisites to native construction and product UI design.

# OPTIONAL_BENCH_RESEARCH — TFC1 logic-edge capture

**Stopped by user direction. This is optional bench research, not a required
cooker-control or protection dependency. Current functional tests pass; routed
timing is79.63MHz and FAILS the80MHz target. See STATUS.md. No further FPGA
integration is authorized.**

This implements the missing FPGA transmitter for the round5 firmware's existing
92-byte receiver. It is a **prototype timing monitor**, not an independent safety
trip, an analog tank acquisition board, or a physical Vgs/ZVS instrument. No board
has been built, no bitstream programmed, and no waveform measured on hardware.

## What is implemented

`rtl/edge_capture.v` synchronizes AH, AL, BH and BL into one nominal 80 MHz domain.
The epoch starts on AL's falling edge; AH therefore rises at its measured deadtime,
matching `firmware/components/power/fullbridge_adapter.c`. It collects the first
rise of every channel after that epoch, each subsequent falling edge, and the next
rise. Only after all four complete does one atomic measurement snapshot publish.
This includes phase endpoints 0/1 and the near-endpoint case in which BL rises one
tick before AH. An AH-rise epoch would silently lose that case.

The four nonoverlap fields are AL-fall→AH-rise, AH-fall→AL-rise,
BL-fall→BH-rise and BH-fall→BL-rise. Period, high time and phase refer to the
same acquisition window. A snapshot takes up to two periods after its epoch;
this monitor does not promise one packet per switching cycle. Invalid periods,
widths or gaps invalidate a capture; observed same-leg overlap latches a fault.

`rtl/tfc1_spi.v` freezes a complete packet at chip-select, while capture and CRC
construction continue separately. A byte-per-clock CRC engine builds the next
bank; the current transmission cannot tear when another capture publishes.
Sequence advances once at the 736th sampled SPI rising edge, never on waveform
cycles. An aborted or overlong transaction latches a transport fault. Invalid,
not-ready and stale requests return zeros, which the real receiver rejects.

The unchanged TFC1 layout is big-endian: magic/version/valid-mask/length; read
sequence; nominal clock Hz; snapshot counter; age; four periods; four high times;
four rise positions; four nonoverlaps; CRC32/ISO-HDLC over bytes 0–87.
The snapshot counter is packet-build time. Age is a deliberately conservative
40,000 nominal ticks (500 us), **not a measured variable latency**. A valid bank
is selectable only while its oldest epoch is at most39,990 actual ticks old.
The 10-tick margin covers the selected oscillator's ±50 ppm plus first-year
±5 ppm aging at the slow-clock end:39990/79,995,600=499.9025us.
Saturating16-bit age counters propagate through capture, packet construction
and publication; they cannot wrap an expired sample into freshness. Validity
also clears on expiry. The absolute32-bit counter is diagnostic only. The receiver's500us estimate is therefore no newer than
any edge in the accepted acquisition window under that clock assumption.

## Selected interface and startup

Use the Lattice ICE40HX8K-B-EVN, with its CT256 FPGA. The board's existing12MHz
oscillator is not used by this design. `candidate.pcf` and `interface.csv` assign
an external80MHz clock to J2.25/H16/GBIN2 and all other signals to verified J2
pins. The assignments were checked against FigureA.3 in the [official guide](https://www.latticesemi.com/view_document?document_id=50373), including the ground
and3.3V taps. Do not connect J2.3: it is the module's1.2V rail. No pin is assigned
to configuration SPI or USB. The guide identifies the board IO as3.3V.

The historical bench SPI target is **mode0,5MHz**, with at least200ns CS setup,
100ns clock high/low, and2us CS-high idle. ESP pins are CS10/SCLK11/MISO12;
MOSI13 is unused. Each736-bit transfer takes147.2us plus driver overhead and must
still satisfy the receiver's measured200us deadline. Poll every250us; the500us
reported age plus a200us maximum transaction fits the bridge's1ms age ceiling.
The RTL also passes10MHz ideal-pin simulation, but that is not an external
10MHz timing qualification. Three-stage sampled SPI plus real buffer and IO
delays motivated the5MHz selection.

External reset is active low and defaults low through10k. Reset release is
synchronized inside the FPGA; assertion is asynchronous at the synchronizer.
The controller must hold request/PERMIT inhibited, establish stable zero-phase
PWM, hold FPGA reset through oscillator startup (allocate10ms), release reset,
then wait at least200us before the first SPI read. Otherwise the receiver
correctly latches the deliberately invalid startup packet. The previously proposed GPIO14 reset and GPIO38 diagnostic-fault assignments
are withdrawn as product recommendations. Any future optional bench experiment
needs its own independently agreed controller wiring.

The92-byte protocol has no boot epoch. A reset from sequenceUINT_MAX to0 cannot
be distinguished from legitimate sequence wrap using these bytes alone.
Reset/configuration must be coupled to host inhibit and fresh qualification;
do not claim that sequence checking alone proves reset detection. Nor can a
clock measure its own absolute frequency. Its nominal80MHz field is an interface
constant; oscillator frequency, startup, drift and clock-loss response require
independent bench verification. Stopped FPGA clock cannot serialize a valid
packet in this oversampled architecture; this is covered by a host-side invalid
frame response, not a hardware trip credit.

## Concrete conditioning circuit, still unrouted

`conditioning-netlist.csv` supplies component-pin connections, with an explicit
BOM and J2 mapping. U1 buffers all four PWM logic inputs together; U2 buffers CS,
SCLK and reset into the FPGA rail; U3 buffers MISO/fault into the controller rail.
All grounds are the same CTRL logic domain. **These inputs connect to the3.3V
pre-isolation PWM logic, never to15V gate drive, switch nodes or a mains domain.**

Nexperia74LVC125APW is selected for its documented partial-power-down behavior,
Schmitt action and same-package output skew. At3.0–3.6V and up to125°C, the data
sheet specifies6ns maximum propagation and1.5ns same-direction output skew.
Power-off leakage is bounded at20uA;10k pulls bound the corresponding node
error to0.2V, subject to the completed circuit's leakage sum.
These are component limits, not a measured assembled-channel delay guarantee.
See [Nexperia74LVC125A rev12](https://assets.nexperia.com/documents/data-sheet/74LVC125A.pdf).

Y1 is the candidate ASV-80.000MHZ-LC-T:3.3V,−40…85°C,±50ppm,15pF load option.
The [Abracon ASV data sheet](https://abracon.com/Oscillators/ASV.pdf) gives45mA
maximum supply current and5ms maximum startup at80MHz; first-year aging is
additional±5ppm. The order code follows its option table; stock and procurement
are unverified. Keep Y1, its decoupling,33ohm source resistor and clock return
immediately beside J2.25. Long flying oscillator wires are not this design.

The module remains USB powered; FPGA_3V3 is a module-rail tap, not a second power
input. U3 uses the controller's own3.3V to avoid powering its GPIO from USB when
it is off. The three buffers, oscillator and pull currents must be added to the
module's actual rail budget; module regulator headroom, USB grounding, rail
sequencing and transient leakage remain unmeasured. Intermediate supply-ramp
behavior is not established by a VCC=0 power-off specification. No claim of a
safe complete power tree or enclosure fit is made here.

The netlist has no native PCB, connector retention design, mating harness or
manufacturing release. These are concrete digital implementation tasks still
open. Buffer/oscillator placement, channel skew, source termination, signal
integrity and connector cable length must be reviewed together; the35–60kHz
pulse rate does not make the logic edges slow. Analog acquisition is separate.

## Reproducible verification

Run `replay.sh` with Icarus Verilog12.0 and a C11 clang compiler. It emits actual
wire-order frames and compiles the **unchanged** firmware receiver plus bridge
planner with address/undefined-behavior sanitizers. Tests cover SPI phase offset,
5MHz and10MHz ideal pin timing,0/1/near-wrap phase,35–60kHz boundary periods,
coherent capture during transmission, counter/sequence wrap, startup, stale
expiry, abort and overlap. The C oracle checks18 genuine RTL packets, all92
single-byte corruption locations, invalid fields, deadline, repeated sequence
and fault latching. It does not simulate analog metastability or physical wiring.

`synth.ys` uses Yosys0.69's iCE40 flow. Its `-noabc` mapper leaves ORNOT/ANDNOT
gates, so `rtl/gate_map.v` maps their explicit four-row truth tables to SB_LUT4.
`tests/tb_gate_map.sv` checks them using Yosys's actual iCE40 simulation primitive.
`timing.sdc` specifies12.5ns without hiding asynchronous IO under a blanket
false-path. Post-route timing and pin checks have their own output receipts. Local acquisition
timers are bounded at13bits and complementary-fall ages saturate, and validity checks are registered to keep arithmetic
out of the wide snapshot enable path.

See `output/temper-prototype-closure/round5/fast-capture/` for logs and vectors.
Task-local tools were installed under`/private/tmp`; no shared packages changed.
Simulation/synthesis evidence does not establish board-level timing, metastability
MTBF, input threshold margins, EMC, thermal performance or protection integrity.

# T02: HOT5 brownout correction and protection closure

## Source and correction

The circuit source is the 120 V full-bridge Atopile unit at
`zapote/power-stage-120v/elec/src/`, selectively copied from the
`ps-oracle` commit `fda5ab9ece24ef1ee6f2317604c5ca73367d5201` into the
MIT guidance worktree. The incoming frozen export had **135 components and
83 nets**. Its existing Rust connectivity audit passed 53 tests, but a new
audit that required an independent HOT5 monitor failed on the incoming
export because the monitor was absent. The corrected source compiles with
Atopile 0.2.69 and exports **142 components and 88 nets**. No native PCB or
controller hardware was changed by this circuit-source edit.

The seven new parts are declared after the existing source components.
Comparing the incoming `ps-oracle` frozen netlist with the new export by
source path and designator found **all 135 original designators unchanged**:
135 retained, zero changed, seven added. This preserves reference identity
for the pending native18 PCB integration. The incoming `default.net` hash
was `32f40a8f08f04278619300b9e1df985d378008c3ce18b13626c91e57d606df5f`.

The correction covers the specific case in which the HOT5 regulator falls
while V15_LS still supplies the gate drivers. TPS3700DDCR is powered by
V15_LS and senses HOT5 with a 105 kΩ / 10 kΩ divider. Its active-low OUTA
pulls a 10 kΩ HOT5 pullup low on undervoltage. A SN74LVC1G17 Schmitt buffer
turns that slow open-drain signal into `HOT5_OK_HOT`. The
SN74LVC1G10 three-input NAND computes
`BUS_FAULT_HOT = !(OCP_OK_HOT & OVP_OK_HOT & HOT5_OK_HOT)`. The existing
ISO7710 then sends the fault-high result to the controller-side OR gate and
J4.10. OUTA never shares a node with either push-pull comparator output.

| Quantity | Calculation / basis | Result |
| --- | --- | --- |
| HOT5 divider | `10/(105+10)` | 0.08696 |
| Rising release | TPS3700 INA+ threshold 400 mV typical | 4.60 V nominal |
| Falling trip | TPS3700 INA+ falling threshold 394.5 mV typical | 4.54 V nominal |
| Conservative falling trip range | 387–400 mV and ±0.5% *independent* resistor ratio allowance, which exceeds the 0.1% initial tolerance and allows temperature drift | about 4.41–4.64 V |
| Pullup sink current | 5 V / 10 kΩ | 0.5 mA, below TPS3700's 5 mA low-output test |

The TPS3700's [datasheet, pp. 4–7](https://www.ti.com/lit/ds/symlink/tps3700.pdf)
specifies the DDC pinout, 1.8–18 V supply range, input thresholds, output
limits, and the 450 µs maximum startup delay. The
[SN74LVC1G17 datasheet, pp. 3–6](https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf)
specifies the SOT-23-5 pins and Schmitt input; the
[SN74LVC1G10 datasheet, pp. 1–3](https://www.ti.com/lit/ds/symlink/sn74lvc1g10.pdf)
specifies its six-pin NAND truth table and pinout. Exact manufacturer parts
were checked in the JLC parts index as TPS3700DDCR (C33002),
SN74LVC1G17DBVR (C7836), SN74LVC1G10DBVR (C403721), and 105 kΩ Yageo
RT0603BRD07105KL (C861072). Index stock was a search result, not an order
reservation. The Atopile source and frozen export are authoritative for
selected circuit part identity.

## What this proves

The corrected frozen export and Rust audit prove *source connectivity and
selected MPNs*: the detector is supplied from V15_LS; its divider and
pullup use HOT5; the Schmitt output is the third NAND input; the isolator
and controller header retain fault-high polarity. Mutation tests reject a
missing detector, detector powered from HOT5, a bypassed third input, direct
slow open-drain drive to the NAND, and an OUTA tie into the push-pull OCP
output. The older 53 source tests still run. This is not a timing, SOA,
thermal, insulation, or physical fault-survival result.

## Remaining protection closure

1. **Power-on inhibit:** TPS3700 output is only specified correct after VDD
   exceeds 1.8 V for up to 450 µs. The independent controller/interlock must
   hold both bridge `DIS` pins asserted and PERMIT off through startup, rail
   sequencing, fault-latch reset and HOT5 monitor validity. Prove this at the
   actual controller, harness, and power board pins.
2. **Collapse delay and latch:** The datasheet's 18 µs output delay is under
   a 5 V supply and 10 mV overdrive test; it is not a worst-case bound for
   HOT5 falling through the whole chain. Inject fast and slow HOT5 collapse
   with V15_LS held up, at temperature and load corners. Capture HOT5,
   TPS3700 OUTA, Schmitt output, NAND output, isolated J4.10, interlock
   latch, both `DIS` pins, and device-pin `Vgs`/current. Establish a measured
   worst-case sensing-to-current-extinction and residual bus/tank energy
   budget. The latch must preserve the trip after HOT5 leaves logic and
   isolator operating ranges.
3. **Other rails and faults:** Test V15_LS decay, TCO opening, V3V3/interlock
   loss, open return or fault conductor, stuck-low/high detector, comparator
   faults, pan and coil corners, and restart policy. Check the selected
   driver/isolator UVLO truth at every intermediate rail voltage. A shorted
   MOSFET needs input fuse and upstream interruption coordination; gate
   disable alone cannot clear it.
4. **Physical release:** Integrate the added parts in the native schematic
   and board, confirm footprint/pin mapping, physical creepage and return
   routing, ERC/DRC, thermal environment, and supplier assembly data. Build
   and test a controlled prototype before treating this protection path as
   qualified. The previous native18 board export does not include this
   source change.

The full T02 item remains open until these circuit, controller and powered
tests establish a complete safe-state path. This edit closes one demonstrable
gap: the missing HOT5 detection input while V15_LS remains available.

# Rev38 SELV controller-port supply contract

**Status: candidate interface limits; electrical and physical acceptance OPEN.**
The existing cooker ESP32-S3 owns the Rev38 command protocol. That choice does
not qualify the cooker's present 3.3 V regulator. The Rev38 section has no
on-board SELV 3.3 V source: power enters at `source_mcu.controller_port`.
`source-build-05` is the frozen Rev38 circuit identity for this contract. A later
product may use a different qualified SELV source while preserving the same
command owner and port requirements.

## Port and allocation

| Requirement at the Rev38 board | Candidate contract / evidence still needed |
| --- | --- |
| Supply and return | Header pads **1 and 9** are `SELV3V3`; pads **8, 13 and 16** are `SELV_GND`. The return is PE-referenced on the cooker candidate and must remain separate from `HOT0`. No conductor may use chassis or the HOT domain as its normal return. The two supply and three return contacts are redundant connections to single nets, not independent supplies. |
| Operating voltage | Design for **3.0–3.6 V at the Rev38 device pins**, including harness drop, source tolerance, ripple, load steps and temperature. This is a proposed board-input envelope, using the ESP module's 3.0–3.6 V operating range and the TCA6408A-Q1's 1.65–3.6 V VCCI/VCCP range as constraints; verify every connected part and logic threshold over the same envelope. Outside the qualified range, authorization must be low. The present source-side TPS3890 threshold calculation does not by itself prove that condition. [Espressif module datasheet](https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf); [TI TCA6408A-Q1 datasheet](https://www.ti.com/lit/ds/symlink/tca6408a-q1.pdf). |
| Current | Reserve **100 mA for the Rev38 port's running and logic-transition load as a design allocation**, subject to a measured coincident-load maximum and source derating. Size startup and capacitive surges separately. This number is a sizing target, **not** a measured draw or an accepted ceiling. The cooker ESP's separately required **at least 0.5 A source capability** stays on the cooker board and is not current through the Rev38 header. The 3.3 V rail also carries existing cooker sensors and controls; its upstream 15 V source separately carries other cooker loads. A 0.6 A sum is not a completed cooker supply budget. [Espressif module datasheet](https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf). |
| Startup charge | The frozen Rev38 source has **1.4 µF nominal** directly across this rail. The cooker-mate candidate adds **0.5 µF nominal** to the cooker rail. Determine effective capacitance, any additional native-board capacitance, cable capacitance and source ramp; use `I_C = C_effective × dV/dt` with concurrent active and pull loads. Prove the source starts without current-limit cycling or a permissive glitch. |
| Connector and harness | The screened 43045-1612 board header, 43025-1608 receptacles and 43030-0007 crimp contacts are identified in `SELV-CONTROLLER-CONNECTOR.md`. Define length, wire gauge, current/temperature derating, contact resistance, retention, strain relief and mis-mate prevention. Do not infer equal current sharing between the parallel supply or return contacts. Measure the case with one contact open as well as the case with both supply or all return contacts open. |

The **100 mA allocation** gives a concrete design target without promoting a
partial data-sheet sum to a maximum. `SELV-SUPPLY-LOAD.md` identifies 9.6 mA
for both selected isolator VCC1 sides at their TI 1 Mbps/15 pF examples
(4.8 mA each), and separately lists the expander, watchdog, supervisors,
logic, pulls and startup capacitors. ISO6742-Q1 is rated only to 50 Mbps;
there is no applicable 100 Mbps two-device example. The frozen netlist's 31 direct SELV
resistors now have an intentionally overcounted **11.89 mA valid-rail screen**
in `SELV-SUPPLY-LOAD.md`; it is not a whole-port bound. Neither isolator
example covers every operating state or coincident transient. Complete an
output-load and switching-current sum, and physical current capture; if
the measured, temperature-corrected maximum exceeds the allocation, revise
the source, connector and allocation before release. Evaluate the existing
IRM-10-15 and LMR51430 **with** all cooker loads and 15 V consumers under
their installed ambient and line conditions. Their nameplate ratings alone
do not establish headroom.

## Sequencing and fail-low conditions

1. Before 3.3 V is valid, during every ramp/drop/brownout, and after loss of
   either source or return, the physical HOT PERMIT, HOT SESSION and RUN paths
   must be low. Observe those nodes at the receivers, not only ESP GPIO or
   software state. Check the two isolators with VCC1 absent and VCC2 present,
   and the reverse rail order; their F variants specify a low default when
   input power or signal is lost, but the actual partial-power circuit still
   needs measurement. [TI ISO774x-Q1 datasheet](https://www.ti.com/lit/ds/symlink/iso7742-q1.pdf); [TI ISO674x-Q1 datasheet](https://www.ti.com/lit/ds/symlink/iso6742-q1.pdf).
2. The TCA6408A-Q1 has both VCCI and VCCP connected to this same rail, but
   equal net names do not guarantee identical pin ramps. TI recommends VCCP
   ramp before VCCI to avoid SDA remaining low. Verify rail order and POR on
   the native board and cable. RESET_N is presently pulled high; an ESP-only
   reset does **not** reset retained P0–P2 output latches. The source may
   resume authorization only after a fresh physical disarm sample and the
   ordered latch-low/readback/direction sequence. [TI TCA6408A-Q1 datasheet,
   sections 8.4 and 9.3](https://www.ti.com/lit/ds/symlink/tca6408a-q1.pdf).
3. Test powered signal lines with missing Rev38 supply, one or all returns
   open, cooker rail off while HOT rails remain on, and HOT rails off while
   SELV remains on. Bound back-powering and intermediate logic levels at
   expander, isolator, watchdog, rail supervisor, retained latches and ESP.
   A pull-down is not an accepted fail-low result under an unpowered or
   back-powered state.
4. Capture ESP cold boot, EN reset, CPU-only reset with retained expander
   power, independent cooker-fault latch, WDO trip, I²C stall and cable
   partial insertion. `SOURCE_RESET_GOOD` may remain high through CPU-only
   reset; the independent watchdog and bounded feed tail must cover it.
   Check the last possible post-reset WDI edge and its *finite* tail against
   the accepted reset-to-off limit. No zero-tail assumption is required.

Record the rail at both header supply pads, each device supply pin, the cooker
buck output, 15 V source and a series Rev38-port current measurement point.
For each state report minimum/maximum voltage, peak and sustained current,
rail order, contact/harness temperature, HOT clear time and instrument setup.
The source/native audit must preserve all five power/return pad assignments
and the SELV/HOT boundary. This contract makes the port reviewable; it does
not mark a 3.3 V supply, harness or physical fail-low behavior PASS.

# Revision 16 — isolated interface schematics

The active AUX clamp and hardware reset proposal now have native KiCad review
fixtures: [clamp PDF](clamp.pdf), [reset PDF](reset.pdf), and their editable
[clamp](clamp.kicad_sch) / [reset](reset.kicad_sch) sources. The clamp has 14
component instances; the reset fixture has 28, including existing circuits
shown for context. **These are not 42 additions to the full design.** Revision11
remains the latest compiled full candidate at 136 components. No production
Atopile source, PCB, manufacturing output or hardware was changed by this unit.

Use KiCad10 with the adjacent project files, `sym-lib-table`, `fp-lib-table`,
and `Temper16.kicad_sym`. Standard KiCad symbols and footprints must be installed.
IC pin layouts are custom drawing symbols; manufacturer pin functions remain
those in revision15's parent-corrected pin tables. Passive footprints are
placeholders, not selected assembly parts. Local fixture references do not map
directly to the full candidate references.

## What changed during capture

The clamp preserves revision15's LT4363HMS-1#PBF / FDB33N25 topology, 59.0kR /
4.99kR feedback divider, 0.22R sense resistor, 100nF timer, and service-only
shutdown input. Its static voltage/current calculations remain conditional as
recorded in [revision15](../interface-active-15/clamp/design.md).

The [LT4363 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/4363fb.pdf),
Applications Information, “Output Capacitance”, requires low-ESR bulk near the
pass-MOSFET source, at least22uF and at least10 times the downstream converter's
ceramic input bypass capacitance. This requirement was missing from revision15.
The output bulk C4 is on AUX_PROTECTED, adjacent to the pass-device output and
sense resistor; upstream LDO bulk cannot satisfy this requirement.

C4 is now a **220uF/50V target**, subject to exact-part ESR, temperature,
tolerance, aging and placement review. Require
`Cbulk,min >= max(22uF, 10 * Cceramic,max)`. A hypothetical 12uF maximum ceramic
load requires at least120uF effective bulk; that ceramic maximum is an example,
not a qualified board measurement. Total downstream capacitance must be no
more than300uF for this revision's startup screen. This includes the bulk and
all downstream decoupling.

To preserve the ramp-current allocation with larger bulk, C3 changes from470nF
to a **1.5uF/63V target with ±10% total effective error**. The corresponding
capacitive ramp screen is14.444mA; the previous conditional operating load plus
support and ramp totals129.700mA. This is below the conditional202.520mA
non-foldback current minimum, but above the67.507mA minimum foldback screen.
Full operating load must not be assumed during startup below3V. Exact buck
startup, source impedance, added decoder loads and gate-current conditions
remain unresolved. `capture-screen.rs` calculates these figures and tests the
bulk floor/ratio, gate-cap effect and foldback distinction. It is arithmetic,
not a dynamic surge-stopper simulation. The larger gate capacitor requires
fresh fault-peak, turn-off, stability and SOA measurements.

The reset fixture captures the independent source-health AND gates, source
permission latch, ISO7741FDWR channel assignment, HOT watchdog clear gate and
reuse of both halves of the existing HOT latch. U6 pin2 takes authorization
from pin9; it is not tied high. U6 pins1/13 clear together with the final enable
AND. SELV_GND and HOT_GND remain separate. Eight bypass capacitors are drawn
as two rail banks with explicit IC mapping; physical layout must place them
at their respective supply pins. Biases are explicit10kR pulldowns.

## Verification and its limits

`capture.rs` is a standalone Rust authoring fixture. `auditor.rs` reads KiCad's
native exported netlists, compares all145 component pins with the declared
pin/net tables, and independently checks critical sense/gate, isolation and
latch connections. The generated expected TSVs alone are not independent
proof; the auditor's separately written contracts and deliberate wiring
mutations are additional checks. The auditor also checks81 selected IC/FET/diode pin functions against separately transcribed
manufacturer mappings, with a deliberately wrong-function rejection. Pin numbers
were reviewed against the manufacturer tables before capture, not inferred from ERC.

The native ERC reports remain deliberately nonzero: **clamp7 findings and
reset10 findings**. `erc-review.json` lists every finding. There are no remaining
off-grid endpoints, unknown libraries, footprint lookup failures or conflicting
output drivers. These findings are not waived in project settings:

| Fixture | ERC findings | Meaning |
| --- | --- | --- |
| Clamp | 1 undriven input | /SHDN's internal pullup and external service contact are not active-output symbols |
| Clamp | 3 undriven power nets | External AUX_RAW/HOT_GND and the passive pass-device output have no ERC power-output symbols |
| Clamp | 3 one-pin labels | Service reset and two observation interfaces |
| Reset | 2 undriven inputs | External existing-health result and HOT response producer |
| Reset | 4 undriven power nets | Two external supply/reference pairs |
| Reset | 4 one-pin labels | Existing-health input, command output, response input and final enable output |

A pulldown can suppress an ERC “undriven” report without implementing a producer.
Therefore the zero count for other input nets is **not** evidence that their
supervisor/watchdog/decoder producers exist. No fictitious power-output flags
or broad ERC exclusions were added to make this fixture appear complete.
`FLT_TP` and `ENOUT_TP` are observation-net names, not fitted test-point parts.

Two additional controls mutate actual schematic labels and re-export them through
KiCad: a sense/input short and a fixed-high RUN-latch data input. Both exports
succeed and both audits reject the resulting wiring. See `negative-controls.json`.
Run `sh verify.sh` from this directory to reproduce the checks; it regenerates
exports and therefore changes timestamped evidence. Final renders can be refreshed
with `kicad-cli sch export pdf` / `sch export svg`. Existing hashes identify the
recorded run, not the timestamps of a later reproduction.

Native SVG/PDF plots were rendered and visually iterated. Parent review fixed
label/field collisions, off-grid endpoints, library resolution, crowded power
symbols and a temporary output/gate wire crossing. The final exported graph
must pass the auditor after any drawing regeneration. This does not validate
PCB clearance, creepage, thermal behavior, isolation assembly or electrical
behavior under fault.

## Remaining integration and physical work

1. Select exact capacitors and verify all effective capacitance/ESR limits;
   finalize source fault impedance/rise time and complete the load/startup
   envelope, including HOT decoder and level translation.
2. Implement independent source reset-good/watchdog-good and HOT watchdog-good
   producers, their power-on behavior and a valid source-rearm producer.
   Keep rearm low at boot. Establish that the previous low reached the HOT
   clear path before rearming; this is **HOT latch-clear evidence**, not an
   LT4363 reset acknowledgement. Then execute a fresh challenge protocol.
3. Implement HOT decoding, framing, persistent session state and validated5V
   SESSION_ARM/START pulses. The1us separation remains a bench stimulus choice;
   actual setup/hold and clear-recovery limits need checking.
4. Execute [revision15's bench worksheet](../interface-active-15/bench-plan.md)
   with the [revision16 addendum](bench-addendum.md). Source faults must disable
   driver/PFC permission; AUX shutdown is a separate service/protection path.
   No transient, restart-timing or hot-case SOA qualification is claimed here.

The Luna review handback is retained as `review-handback-unaccepted.md` for
traceability. Its suggested AUX_RAW bulk location and LT4363 rearm-ack wording
were rejected; `review-resolution.md` records the accepted corrections.
See `receipt.json` for checks and scope, `input-identity.json` for frozen inputs,
and `artifact-hashes.json` for the finished local evidence.

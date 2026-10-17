# Integration verification

2026-10-04. This record concerns the engineering-prototype work following
`80e716110fb7ff05d5cc4011c1ac370f70498fad`. It is not fabrication or energization
approval. Physical measurements and the first-unit build remain `NOT_RUN`.

## Completed independent checks

- Power preflight reproduced the pinned ngspice 45.2 baseline. The parent
  independently checked the 332 archive-member hashes and accepted all 81
  conditional results through the guarded result validator. These are imposed
  commutation experiments, not measured protection latency or fault survival.
- EMI verification reused the separately published D22 branch. The final
  memory simplifications preserve the prior scientific results: 32 recorded
  nonlinear captures replayed, 12 AC cases freshly simulated, ten upstream
  tests passed. The parent independently checked the final runner identity and
  exercised the failed-input/stale-PASS guards before the memory-only changes.
- Cooling source/artifact hashes and zero-intersection receipts were checked
  independently. The source agent reimported 539 valid assembly solids and
  proved that the sink base and fins form one connected solid. This is the
  135-component native18 study; it does not verify the native19 population.
- Manufacturing intake contains 13 current matching hashes, 21 unique picklist
  items and nine unreleased holds. The initial intake is retained separately;
  the current manifest identifies native19 and its142-part/89-net source.
  A successful identity check never releases a hold.
- Repository import boundaries passed: five contracts kept, zero broken.
  `make regen` and `make regen-check` passed all derived-artifact checks without
  additional changes. The local commands used
  a writable temporary UV cache and the checkout's placer source path; no
  shared Rust extension rebuild was needed for those checks.
- Authored code/configuration whitespace checks and scoped Ruff checks pass.
  The full staged whitespace scan reports generator formatting in SVG, STEP,
  compiled CSV and captured logs/text. Those captured bytes were preserved
  rather than reformatted and disconnected from their recorded hashes.
- The 36 inherited footprint-library warnings were examined on the saved HOT5
  milestone. KiCad's own footprint-relative APIs found matching pad position,
  size, drill, shape, layers, offset and rotation for all 36; 22 had different
  model paths. This limited comparison does not establish full footprint
  equivalence or manufacturer conformity and does not waive the warnings.
  R5 demonstrates why matching a library alone is insufficient: its former
  library variant itself was inappropriate for the selected resistance.

## Review findings addressed during implementation

- Power reproduction now checks authored and external input hashes before
  executing the external runner, rejects a different simulator version and
  rejects a measured gate crossing before the imposed shutdown command.
- EMI verification rejects optimized Python, checks external code hashes before
  importing it and invalidates an old success receipt before input checks.
  Negative controls cover altered inputs/provenance, a wrong source HEAD and
  forbidden output into the source checkout.
- The first sink relief severed its base. The revised shallow recess preserves
  a continuous base; a deliberate failing input verifies the new continuity
  check. Actual cooling performance remains unmeasured.
- Independent Astra inspection of the actual package drawings found the wrong
  sign on both half-lead-thickness corrections. The parent confirmed the near
  lead-edge datums visually. Correct conditional rear-plane ranges are MOS
  1.170–1.825 mm and BR1 1.300–1.800 mm in board coordinates. The earlier
  unconditional MOS-model mismatch claim is withdrawn: the nominal 1.515 mm
  position lies inside its interval. The fixed interface can still have a gap
  or interference, and the proposed BR1 land is not established by the drawing.
  Corrected limits remain conditional on straight, centered leads and exclude
  assembly/lead-forming tolerances; they are not physical measurements.
- Concatenating schematic reference and pin number produced UUID collisions
  such as `U1.11` and `U11.1`. The PCB agent replaced those keys with delimited
  identifiers and added a uniqueness check.

Three Astra simplification reviews covered the settled power, EMI and cooling
scripts. Reuse found no worthwhile replacement. Two quality fixes share fixture
dimensions with its receipt and derive plot labels from geometry; the fixture
geometry and PNG remained unchanged. Two efficiency fixes stream artifact
hashing and release replay arrays between captures; all EMI checks passed
again. No safety or identity check was removed.

## Shunt correction identified by the parent

The [Vishay WSK2512 drawing](https://www.vishay.com/docs/30108/wsk2512.pdf),
document 30108 revision 11-Dec-2023, pages 2–3, was inspected visually. The
1 mΩ part requires the T2.21 terminal variant. The former T1.19 land pattern
belongs to the 5–200 mΩ range. Vishay's
[ordering-code list](https://www.vishay.com/en/product/30108/tab/quality/)
identifies `WSK25121L000FEA`; the former `WSK2512R0010FEA` intake string is not
the manufacturer-listed code.

The drawing labels current and sense terminals, not KiCad pin numbers. The
numeric mapping is the library convention: current pads 1/4 and same-end sense
pads 2/3. A valid Kelvin correction must separate the power return from the
sense reference in source and layout. Merely renaming the existing island
would leave gate-supply return current flowing through a sense terminal.
Native19's final source audit, routing and verification records determine the
implemented disposition; the discovery itself is not evidence of a finished
correction.

An independent Astra power review supports keeping PS2.VN and the 15 V bulk
capacitor on `LEG_RET`, with the LDO and analog/isolator hot-side returns on
`OCP_KELVIN_P`. OCP, OVP and shutdown polarity are preserved. The sense
reference remains loaded by those analog/logic currents; the shared 15 V rail
can also couple gate pulses through the analog bypass capacitors. Route the
analog supply branch and return paths deliberately and measure the resulting
sense error. Approximately 1 mV of positive reference rise lowers the nominal
1 mΩ trip by 1 A. This sensitivity is not a measured offset or a released trip
limit. OVP retains its leg-side reference and therefore does not directly
measure across both bus-capacitor terminals during shunt current.

## Release limits

The final native19 candidate has142 components/89 nets. Three native DRC runs
report zero errors, opens and schematic-parity findings, retaining36 library
mismatches and3 silkscreen warnings. Typed ERC reports zero errors and16
documented warnings. The parent independently reran all62 Rust audit tests.
The STEP imports with216 valid solids and all142 component references, including
24 provisional envelopes. Both FEM leg regions are changed; native18 extraction
cannot be carried forward without re-extraction. Probe points are candidates;
full tip/copper and actual mask-aperture containment remain unchecked.

The [completed code review](review/code-review.json), run
`temper-prototype-20261004-132238`, returned three P2 reproduction findings.
An independent validator confirmed them; the parent applied all three inline:
use committed footprints, reject divergent copied source exports before either
builder writes, and replace obsolete native09 model instructions. No actionable
code-review findings remain unapplied. The
[fix verification](../native-19/verification/review-fix-verification.json) records
four test methods with13 negative cases, unchanged footprint hashes, exact
schematic reproduction and byte-identical pre-refill PCB output before/after
the fixes. Saved board, schematic and STEP identities remain unchanged.

Seven Astra review lenses ran. Automatic approval review rejected the proposed
Claude transfer before launch; the adversarial lens ran on Astra instead.
There was no cross-provider review. Earlier three-lens PCB simplification also
preserved output while caching repeated model hashes and removing a singleton
canonicalization loop.

The first-unit packet carries the remaining physical and supplier evidence.
Neither a clean electrical-rule report nor a collision-free nominal model
establishes a supported operating current, heat-sink performance, clamp force,
insulation construction, button overtravel or fault survival. Changed shunt
copper and the new coil/board/sink/chassis relationship also require explicit
reconciliation with the earlier simulation inputs.

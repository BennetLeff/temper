# Rev38 bus-monitor interface: selection gate 01

**Status: design input only; no PCB, hookup permission, or safety function.** The
legacy voltage-sense candidate measures a 170 V nominal positive half-bus over
an assumed 0–250 V envelope and joins its measurement return to host ground.
Its J1/J2 interface cannot be connected to Rev38 `VB_BANK`/`HOT0`. Rev38's
existing four-channel `VD_LOCAL`/`VB_BANK` detector is HOT-local and remains the
candidate trip producer; this proposed monitor would only report bus voltage
to the SELV controller. It cannot replace the Rev38 detector or prove F2
continuity.

## Evidence snapshot and applicability

| Evidence | Snapshot identity | Consequence |
| --- | --- | --- |
| `zapote/voltage-sense/INTERFACES.md` | SHA-256 `c98dbb1afd7620f5f806864ec38c4692d65c94601f9b4d3caf264dcd25e7b756` on coordinator commit `7fdd994e6` | J1.1 `BUS_PLUS` is half-bus; J1.2/J2.2 `BUS_RETURN` are common with host ground. |
| `zapote/voltage-sense/MODEL.md` | SHA-256 `c432b1e5b1c095296440af730c7a0852593cb9e7a4e747417c7972802c752bda` | 250 V is the old analytical ceiling, not a transferable Rev38 rating. |
| Rev38 `interface-integration-38/PFC-POWER.md` | SHA-256 `f776b6bfccf138cf5d5c3e81216374233182ebf36e67d0f27a2c64fb180a434d`, power-entry commit `210929bce` | `VD_LOCAL` and `VB_BANK` are separated by F2; both reference HOT0. Four 450 V bank capacitors do not authorize a 500 V waveform. |
| Rev38 `interface-integration-38/PIN-INTERFACE-CONTRACT.md` | SHA-256 `f7772e2e9bffcd34a9facca5bde12771edc6662221eed3c9dc3bc8d0e50c6e91`, power-entry commit `210929bce` | HOT0 and SELV ground are separate; HOT logic5 and SELV3V3 have unclosed source/load/rail gates. |
| Rev38 `interface-integration-38/F2-DETECTOR.md` | SHA-256 `12979fa3c68be41fc82c9f5e1af7be3a2450bb0c2eb2ebeab98cedb161a8ed3c`, power-entry commit `210929bce` | Local HOT detector thresholds and response are still open; host telemetry is not its substitute. |
| `docs/cert-lab-inquiry-final-2026-08-16.md` | SHA-256 `d691016faacc8e64a2dcb610f2f3a2fae71efc7d2a5da7b63bdb7a4c7d8d7721` | Current vented construction uses a 12.6 mm PD3 reinforced-creepage target for its stated >250–400 V row; the governing row must be revisited when the Rev38 maximum is adopted. |

The Rev38 hashes above identify the **committed blobs at `210929bce`**;
uncommitted changes in its active worktree may already differ. These hashes
identify inputs, not a review of their physical validity. Regenerate this
snapshot before selecting parts or joining a board. The named Rev38 files live under
`zapote/power-entry/passive-reva/protection/` in that separate worktree.

## Approaches reviewed

1. **Directly rescale the legacy divider. Rejected.** It leaves HOT0 tied to
   the host's common ground through J2, defeating the declared SELV boundary.
   More top resistance does not fix the return path.
2. **Use an isolator with an internal high-side supply. Deferred.** TI's
   [AMC3330](https://www.ti.com/lit/ds/symlink/amc3330.pdf) offers a ±1 V
   differential input and an integrated isolated DC/DC supply, but its
   specified external package creepage and clearance are at least 8 mm. Its
   package geometry does not itself meet the project's current 12.6 mm
   reinforced-creepage target. A slot or alternative insulation construction
   would require a separate assembly and standards decision.
3. **HOT-referenced divider plus a stretched-package isolated amplifier.
   Preferred architecture for further selection, not a selected circuit.**
   TI's [AMC1411DWLR](https://www.ti.com/product/AMC1411/part-details/AMC1411DWLR)
   has a 0–2 V specified linear input, separate 3.0–5.5 V supplies on each
   side, differential SELV output, and at least 15.7 mm package creepage and
   14.7 mm package clearance. This clears the *current* 12.6 mm numerical
   creepage screen at the package, subject to the eventual voltage/standards
   row and board/connector geometry. It requires qualified HOT and SELV
   supplies and a selected receiver. [TI's datasheet](https://www.ti.com/lit/ds/symlink/amc1411.pdf)
   is the pin and electrical authority, not this note.

## Proposed functional boundary

```text
VB_BANK -- rated series divider -- sense resistor -- HOT0
                                  |                 |
                           AMC1411 INP/2       GND1/4
HOT_LOGIC5 ---------------- AMC1411 VDD1/1
HOT0 ---------------------- AMC1411 SHTDN/3 (candidate enabled state)
                         || reinforced barrier ||
SELV3V3 ------------------ AMC1411 VDD2/8
SELV_GND ----------------- AMC1411 GND2/5
SELV receiver <----------- AMC1411 OUTP/7, OUTN/6
```

This is a **net relationship**, not connector numbering, schematic source,
or a reviewed package footprint. `HOT_LOGIC5` is local to Rev38; the receiver
must not connect its ground to HOT0. The SHTDN connection, decoupling,
filter, clamping, input transient behavior, and differential receiver must
be designed from actual part and supply corners. The AMC1411's negative
differential failsafe output applies to missing/undervoltage high-side supply
or asserted shutdown with a powered low side; it does not detect every
divider fault or guarantee a valid indication when the SELV side is off.
Bus-monitor validity must therefore include fresh sample and both supply
health signals, not voltage plausibility alone. A missing/invalid monitor
must inhibit *both* PFC and inverter permission in the integrated design.

## Divider design gate

Set the adopted continuous, startup, surge, and credible fault maxima for
both `VB_BANK`–`HOT0` and each conductor's voltage to accessible/SELV/PE
structures. For a top string `R_T = ΣR_i` and sense resistor `R_S`, check
`V_IN = V_B × R_S / (R_T + R_S)` with resistance/tolerance/temperature and
input-bias corners. At every adopted maximum, verify `V_IN ≤ 2 V` for the
specified linear range, each resistor's *working* voltage and power, total
dissipation, pulse energy, divider leakage, open/short faults, partial power,
and fault injection into the amplifier input. The TI datasheet's 1200 V
example divides among sixteen resistors because its **example** limits each
unit to 75 V; those values are not a Zapote selection. No adopted `V_B,max`
or resistor/order code exists here, so no divider values or footprint are
selected.

## Conditions before native PCB work

| Gate | Needed result | Current disposition |
| --- | --- | --- |
| Voltage envelope | Adopted VB and VD continuous, startup, overshoot, surge and fault maxima, plus governing insulation row | OPEN |
| Measurement role | Decide whether VB alone is enough or independent VD telemetry is required; preserve local F2 detector authority | OPEN |
| Supply and return | Qualified HOT logic5 and SELV3V3 source/load/startup, partial-power behavior, and no HOT0–SELV connection | OPEN |
| Divider and input | Exact resistor MPN/package, tolerance, voltage, power and fault/pulse calculation; AMC1411 pin-level circuit | OPEN |
| Host output | Differential receiver/ADC channels, common-mode, filter, acquisition, calibration, sample age and invalid behavior | OPEN |
| Interconnect/insulation | Exact HOT/SELV connector MPNs, harness and pad map, board stackup, creepage/clearance/courtyard rules and enclosure | OPEN |
| Safety response | Trace invalid/absent telemetry and local OVP into both PFC inhibit and inverter permit under reset and partial power | OPEN |

Once those inputs are adopted, create a **new** Atopile unit, generate and
visually review native schematic/PCB, run ERC/DRC with the adopted rules,
audit every connector pad/net and domain crossing, and perform standalone
physical qualification. Do not modify or repurpose the accepted legacy
half-bus board.

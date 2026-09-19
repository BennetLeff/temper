# F2-open control architecture decision

> **Superseded coordinator recommendation, 2026-09-19:** see
> [the reviewed comparison](../review/README.md). The bank-side preference,
> mandatory extra clamp and claim that diode-side feedback necessarily adds
> more functions were not established. This worker draft is retained as review
> input, not the next-ECO authority. The current CAD is now diode-side; see
> [current construction](../../FREEZE.md). The bank-side claims below describe
> the superseded worker proposal only.

Date: 2026-09-19  
Status: **DESIGN DECISION — implementation and protection qualification open**  
Scope: the active-rectifier construction candidate only. This record does not
authorize fabrication, procurement, powered testing, or a protection claim.

## Decision

Keep the bank-side `VSENSE` divider as the construction baseline, but do not
accept the board as F2-open safe. The next revision must add an **independent
diode-side overvoltage detector and hard inhibit path**, with a separately
qualified diode-side clamp or energy-absorption path. The detector shall sense
`BOOST_DIODE_POSITIVE` relative to `CONTROL_GND` and, on an overvoltage or
invalid F2 state, remove `HOT_PERMIT_EXTERNAL` so the existing inhibit path
forces `pfc.VSENSE` low. The detector must be specified as a real
fail-safe/open-collector or equivalent circuit; the existing external permit
input is not credited as a supervisor until its source, polarity, default state,
latency, and fault behavior are documented and tested.

This is a topology decision, not a qualification result. The clamp, detector
threshold, detection latency, diode-side energy, and behavior with a failed-short
boost switch remain unclosed.

## What the current circuit actually does

The authored source connects the proposed fuse between the diode-side output and
the bank:

```text
U10.K -> BOOST_DIODE_POSITIVE -> U66/F2 -> PFC_BUS_PLUS_390V -> bulk bank
```

The retained native netlist independently records `U10.2` and `U66.1` on
`BOOST_DIODE_POSITIVE`, and `U66.2`, the four bulk capacitors, U20.1 and the
bleeder on `PFC_BUS_PLUS_390V`:

* `candidate/section.kicad_pcb` SHA-256:
  `e274d8ad1181f426f731f170e46202e16f969bb751538837a45ee221c3b09ceb`
* `evidence/vsense-bank-side-01/native.json`
* `evidence/vsense-bank-side-01/fault-loop/netlist.json`

The source of authority is the authored/native pair, not the prose in an older
closeout. In `elec/src/power_entry_active_unit.ato:375-376`,
`boost_output` is connected to `bus_fuse.diode` and `bus_fuse.bank` to
`hv_plus`. The same source connects the bank capacitors, output connector,
bleeders, and the voltage-divider top to `hv_plus` at lines 483-506 and
551-556. The local 470 nF high-frequency capacitor remains diode-side at
lines 500-501.

Therefore, when F2 opens:

* the bulk bank and its bleeder remain connected to `PFC_BUS_PLUS_390V`;
* U20 and the UCC28180 divider continue to sense that bank through `VSENSE`;
* `BOOST_DIODE_POSITIVE` is disconnected from the bank but can still be
  energized from mains through the boost inductor, switch and diode;
* only the local diode-side HF capacitor and parasitic/load paths remain on
  that output in the current model;
* the bank-side measurement does **not** measure the diode-side voltage.

The earlier statement that opening F2 makes the controller blind to the bank is
wrong for the current source and is withdrawn. The opposite statement—bank
sense proves diode-side safety—is also wrong.

## Controller behavior and credited paths

The retained primary source is
`zapote/power-entry/shunt-repair/sources/TI-UCC28180.pdf`, Rev D, SHA-256
`e1e1588c6854b43742a667c76df26f06d9ac51231f0176c43b2a46b63c1b00be`.
Page numbers below are the printed datasheet pages.

* Pin-function text on printed p. 4 says `VSENSE` uses an external divider
  from the PFC output, enters standby when it falls below the OLP threshold,
  and has OVP behavior when it rises above the OVP thresholds.
* The electrical-characteristics table on printed p. 6 gives OLP as
  15.6/16.5/17.6 % of the 5 V reference (about 0.78/0.825/0.88 V), and
  OVP-low/high nominal thresholds of 107%/109% of VREF. These are controller
  input thresholds, not a guarantee that an external F2 detector will drive
  `VSENSE` below OLP.
* Section 8.3.4, printed p. 14, says OVP-low discharges VCOMP through 4 kΩ
  and OVP-high disables GATE until the reset threshold. That protection acts
  only on the voltage actually present at `VSENSE`.
* Section 8.3.5, printed p. 14, says OLP/standby pulls VCOMP low when VSENSE
  is below its threshold. It does not say that opening an arbitrary series
  fuse asserts OLP.
* Sections 8.3.11–8.3.12, printed pp. 17–18, describe SOC and cycle-by-cycle
  PCL from `ISENSE`. They do not sense the internal F2/U10/U9 discharge loop.

The source's existing inhibit circuit is real connectivity, not yet a safety
claim: `q_inhibit.D` is on `pfc.VSENSE`; `q_inhibit.S` is on `CONTROL_GND`;
the pull-up defaults its gate toward inhibit; and `HOT_PERMIT_EXTERNAL` drives
`q_permit`, which releases that clamp (`elec/src/power_entry_active_unit.ato:
508-523`). The source comment calls HOT permit the sequencing authority, but
no external supervisor, threshold, or response time is authored. Consequently
the proposed detector may use this path only after those missing properties are
specified and verified.

Fault-state distinction remains mandatory:

| State | F2-open consequence | Credit today |
|---|---|---|
| U9 healthy and controllable | A detector could command the controller off, subject to detection and gate latency; diode-side energy and voltage still need a clamp/absorber. | None until timing and stress are measured or bounded. |
| U9 failed short | Gate commands cannot open the switch. The diode-side detector cannot interrupt the conducting semiconductor. | F2 is the only proposed element in the internal bank discharge path; coordination is unestablished. |
| U10 failed short, U9 healthy | The bank-side F2 path can drive the internal loop; bank sensing is not a loop-current sensor. | No shutdown or U12 credit. |
| U10 and U9 failed short | The internal bank loop remains conductive. | F2 candidate only; clearing and withstand are unqualified. |

Gate disable is therefore a control response for a healthy switch, not an
interrupter for a failed-short device and not a substitute for F2 or F1.

## Required next-revision topology

Retain these existing connections:

1. F2 remains the sole intentional series element between
   `BOOST_DIODE_POSITIVE` and `PFC_BUS_PLUS_390V`; audit every copper, zone,
   capacitor and connector branch for bypasses.
2. U20/bank `VSENSE` remains the bank monitor and normal output-regulation
   feedback.
3. `HOT_PERMIT_EXTERNAL` remains the external sequencing input, but its
   default and fault state must be made explicit.

Add two independent functions on the diode side:

1. **Diode-side overvoltage sensing.** A resistor-rated, creepage-reviewed
   divider from `BOOST_DIODE_POSITIVE` to `CONTROL_GND` feeds a comparator or
   supervisor whose threshold is selected from the permitted diode-side voltage
   and transient contract. The divider must withstand F2-open voltage and
   discharge safely after input removal. Its output must assert a fault for an
   open, short, missing bias supply, or out-of-range diode-side voltage; a
   single healthy-high `HOT_PERMIT_EXTERNAL` is not sufficient evidence.
2. **Hard inhibit plus independent voltage/energy limiting.** The detector
   must remove the permit through a defined wired-OR/open-drain fault path that
   leaves `q_inhibit` on and pulls `VSENSE` below the controller's OLP threshold.
   In parallel, a selected diode-side clamp, dump, or other energy absorber must
   limit `BOOST_DIODE_POSITIVE` while the detector responds. Its pulse energy,
   repetitive duty, capacitance, and failure mode must be qualified. A detector
   alone cannot claim to prevent the first overvoltage excursion.

This is the minimum implementation delta. It is deliberately not a named part
or a guessed threshold: those depend on the declared diode-side maximum,
surge contract, local C40/C_HF energy, and detector response. If the required
clamp cannot be selected for the diode-side fault energy, the active rectifier
must not advance and the passive baseline remains the fallback.

## Alternatives considered

### A — retained bank feedback plus independent diode-side protection (chosen)

This preserves bank monitoring after F2 opens and keeps the normal regulation
reference on the intended bulk output. It explicitly adds the missing sensing
and protection for the side that remains line-fed. It has a finite ECO: one
diode-side divider/supervisor, a fault-combine path into permit, and a qualified
clamp/absorber. Its main unknowns are measurable: threshold, latency, clamp
stress, and fault-state coordination.

### B — move VSENSE back to diode-side regulation and add separate bank monitoring

This lets the UCC28180 observe the side that can remain energized after F2
opens, but it makes the bank voltage invisible to the controller and leaves
the bank as a separately supervised energy store. It therefore requires both a
bank OVP/undervoltage monitor and a diode-side protection path anyway. It also
changes the normal feedback loop and compensation behavior. It adds more
functions while not removing the failed-short/F2 coordination requirement, so
it is inferior unless a control-loop test shows that option A cannot regulate
the diode-side transient.

### C — rely on the existing bank divider, HOT permit, or gate disable

Rejected. Bank feedback cannot see `BOOST_DIODE_POSITIVE` after F2 opens;
HOT permit has no retained supervisor contract; and UCC28180 gate disable is
not an interrupter for failed-short U9. This option has no explicit topology
that limits the diode-side voltage.

## Qualification gates

The next revision cannot be called protected until all of these are retained on
the exact source/native/PCB bytes:

1. **F2 state matrix:** normal, F2 open before startup, F2 opens while running,
   and F2 welded/shorted. Record both bank and diode-side voltages, VSENSE,
   VCOMP, GATE, HOT permit, and auxiliary bias.
2. **Healthy-U9 response:** establish detector threshold, propagation delay,
   gate turn-off delay, remaining inductor current, diode-side peak voltage and
   clamp energy. Repeat at low/high line, minimum/maximum bulk capacitance,
   temperature and tolerances.
3. **Failed-short U9/U10 cases:** use the selected F2 and holder application
   data for the 400 V capacitor bank with maximum credible capacitance/voltage;
   establish prospective current, let-through, arc clearing and copper/device
   withstand. Do not transfer passive GBJ ratings or normal RDS(on).
4. **Permit fault injection:** open/short the detector output, remove its bias,
   open the divider, and force `HOT_PERMIT_EXTERNAL` high. The safe state must
   be inhibit, and a missing detector must not appear healthy.
5. **Surge/EMI:** verify the diode-side clamp and detector insulation against
   the adopted differential/common-mode contract and the actual connected
   assembly. The current board's bank-side MOV and Y-cap record does not close
   this.
6. **Construction:** rerun source/native parity, Rust suite, ERC/DRC and the
   physical stackup/spacing checks after the ECO. A clean DRC is not a
   protection result.

## Decision blockers and finite escalation

The decision is defensible at architecture level, but the board cannot advance
to a protected prototype until these finite inputs exist:

* a declared maximum `BOOST_DIODE_POSITIVE` voltage and transient waveform;
* a selected diode-side clamp/absorber with pulse-energy and failure data;
* detector threshold, bias-failure behavior and measured/bounded response time;
* F2 capacitor-discharge let-through/clearing data for the exact candidate and
  holder; and
* the maximum bank capacitance/voltage and U9/U10 failed-short residuals.

If the component application engineer or test lab cannot supply those inputs,
stop at this construction checkpoint, retain the passive bridge baseline, and
do not spend another harness or optimization campaign trying to infer them.

## Evidence map

* Authored connectivity: `elec/src/power_entry_active_unit.ato:375-376`,
  `:483-506`, `:508-556`.
* Native connectivity: `evidence/vsense-bank-side-01/native.json` and
  `evidence/vsense-bank-side-01/fault-loop/netlist.json`.
* Board identity: `candidate/section.kicad_pcb` SHA-256 above; current freeze
  record in `FREEZE.md`.
* Controller primary source: retained TI PDF and hash above; printed pp. 4,
  6, 14, 17–18.
* Existing protection handoff and open Q1–Q5 work:
  `zapote/power-entry/CLOSEOUT.md`.

## Boundary

This document decides the next circuit architecture only. It does not claim
that F2 clears, that the controller shuts down within a safe time, that the
diode-side clamp is selected, or that the active rectifier is safe to power.

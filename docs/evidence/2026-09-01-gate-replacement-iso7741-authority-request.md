<!-- provenance: commit=85b4e400572a77d18f0ee6c644a532ab0a55dd8e dirty=true (authority-request packet; docs-only, no production PCB or baseline changed) -->

# Gate-drive replacement `gate-replacement-iso7741fqdwwrq1` — authority request packet

**Date:** 2026-09-01
**Status:** REQUEST FOR EXTERNAL/OWNER RULINGS — not a qualification, approval, or
part-selection record.
**Candidate:** two `ISO7741FQDWWRQ1` automotive digital isolators, one per
half-bridge switch, with one local non-isolated secondary-side gate driver per
switch.
**Governing barrier:** 12.6 mm PD3 reinforced creepage/straight-corridor
requirement.
**Campaign result:** `stopped-indeterminate`; the current qualification package
records `geometry.approved_replacement_footprint_missing`,
`package.local_driver_footprints_missing`,
`gate.two_local_drivers_redesign_required`,
`gate.timing_shutdown_uvlo_reverification_required`, and
`gate.integration_bom_looparea_thermal_missing`.

This packet asks named owners to close those bounded gaps. It deliberately leaves
all ruling fields blank. No agent, document, distributor listing, or promising
package number may self-approve a safety, certification, electrical, or sourcing
decision.

## 1. Proposed architecture requiring a ruling

The proposal is a mechanism study, not a board edit:

1. Use two separately powered/barriered `ISO7741FQDWWRQ1` DWW-16 devices: one
   for the high-side floating switch domain and one for the low-side floating
   switch domain. The two switch domains cannot be collapsed merely because
   `ISO7741` has four channels.
2. Use one local, non-isolated gate-driver IC in each corresponding floating
   domain. The digital isolator output is logic-level; it is not a substitute
   for the peak-current gate-drive stage.
3. Re-derive the two complete channels, including the isolation-side channel
   allocation, local-driver supply/UVLO, gate resistors, gate-source return,
   shutdown path, bootstrap power, and all unused-channel terminations.
4. Reuse of the current `power_15v_ls`/bootstrap concept is a hypothesis only.
   It may be retained only after the new topology's supply references and
   transient behavior are shown in the schematic, netlist, and bench evidence.

The candidate is attractive because the cited TI DWW-16 package has a published
external clearance/creepage figure above 14.5 mm, but that fact does not qualify
the complete assembly. The two local driver packages, their land patterns,
routing, and board-level insulation construction remain part of the acceptance
boundary.

## 2. Frozen incumbent contracts to preserve unless an owner explicitly approves a change

The following are the current design contracts against which the replacement
must be compared. They are not permission to alter the production design during
this packet or the qualification campaign.

| Contract | Current value or behavior | Authority |
|---|---|---|
| Half-bridge channels | Two complementary channels: high side and low side; `pwm_h`/`pwm_l` | `elec/src/modules.ato` (`8f0691418`), `elec/src/components.ato` (`044114459`) |
| Control supply | UCC control-side `VCCI` is 3.0–5.5 V; current design uses the 3.3 V control rail | `docs/hardware/UCC21550_INTERFACE_CONTRACT.md` (`219136e05`) |
| Gate supply | 15 V gate-side supply; low-side supply floats on `hv_minus`; high-side bootstrap is on the secondary side | `elec/src/modules.ato` (`8f0691418`) |
| Power devices | Two `IKW40N120H3` IGBTs, 1200 V/40 A component declaration | `elec/src/components.ato` (`044114459`) |
| Gate network | 2.2 ohm turn-on resistor, 2.2 kΩ gate-source pulldown; both require an actual replacement-driver review | `elec/src/modules.ato` (`8f0691418`) |
| Dead time | Firmware/system requirement 300 ns; incumbent IGBT turn-off figure 245 ns; the existing assertion requires the 50 ns margin | `elec/src/modules.ato` (`8f0691418`), `docs/evidence/2026-07-30-pd3-isolation-mechanism-alternatives.md` (`57f0c7550`) |
| Shutdown | Active-high disable semantics with a set-dominant latched fault path; clearing a fault does not auto-resume | `docs/hardware/UCC21550_INTERFACE_CONTRACT.md` (`219136e05`), `docs/hardware/SAFETY_INTERLOCK_DESIGN.md` (`07da91302`) |
| Safety inputs | OCP, OVP, thermal, watchdog, firmware runaway-cut, and independent RTD hardware path feed the safety decision | `docs/hardware/UCC21550_INTERFACE_CONTRACT.md` (`219136e05`) |
| UVLO requirement | Functional criterion says gate-drive rail falling `<12.0 V`, rising `>13.0 V`; logic rail falling `<2.9 V`, rising `>3.0 V` | `docs/FUNCTIONAL_TEST_CRITERIA.md` (`c1f7025d3`), `docs/evidence/2026-07-25-uvl01-gate-drive-uvlo-unmeasured.json` (`464bd0589`) |
| Isolation bar | 12.6 mm PD3 creepage/straight corridor; no downward reclassification is in scope | `elec/src/constraints.ato` (`1213c3e50`), `docs/evidence/2026-09-01-isolation-component-architecture-qualification.md` (campaign base `85b4e400`) |

The UVLO line is intentionally called out as an ambiguity to resolve, not
silently inherited. The existing criterion names a 15 V gate-drive rail while
the incumbent evidence describes internal UCC21550 thresholds on `VCC` and
`VCCI`; the replacement must identify exactly which local-driver and supply
rail is being gated and demonstrate the required falling/rising behavior.

## 3. Known manufacturer-primary TI facts (reference facts, not approvals)

These are the facts that may be used as inputs to an owner review. They do not
prove board-level suitability, IEC 60335-1 credit, or the proposed local-driver
contract.

### ISO7741-Q1 / `ISO7741FQDWWRQ1`

The manufacturer source is TI's **ISO774x-Q1 Automotive, High-Speed,
Reinforced Quad-Channel Digital Isolators** data sheet, `SLLSEU0G`, Rev. G
(revised October 2024):
[`www.ti.com/lit/ds/symlink/iso7741-q1.pdf`](https://www.ti.com/lit/ds/symlink/iso7741-q1.pdf).
The reviewer must verify the current revision and ordering suffix against the
actual procurement record before selection.

The data sheet reports, for the DWW-16 option:

- 3 forward and 1 reverse channel for `ISO7741-Q1`; 100 Mbps maximum data rate;
- 2.25–5.5 V supply/logic range for the family;
- typical propagation delay 10.7 ns, maximum 17 ns at the stated test
  conditions; maximum part-to-part skew 4.4 ns and channel-to-channel skew
  4 ns as listed by TI;
- external clearance and creepage both `>14.5 mm` for DWW-16 (the DW-16 and
  DBQ-16 options are different packages and must not be substituted by name);
- DWW-16 isolation ratings including 5700 V RMS UL 1577 withstand, 8000 V peak
  transient isolation, and 12.8 kV peak surge isolation under the specified
  tests; and
- TI-listed certification records including VDE certificate `40040142`, UL
  file `E181974`, CQC certificate `CQC15001121716`, and the published
  reinforced-insulation working-voltage limits for the applicable standard and
  pollution-degree conditions.

The `F` suffix's default-output behavior, channel direction, supply sequencing,
input/output fail-safe behavior, unused-channel treatment, and exact package
drawing must be checked against the ordered device and the current data sheet.
The data-sheet spacing is a component fact; it is not a ruling that this board's
construction earns PD3 credit.

### Candidate local driver: TI UCC27517 / UCC27517-Q1

TI's product and data-sheet pages identify the UCC27517 family as a single-
channel low-side gate driver with 4 A source and 4 A sink peak capability,
approximately 13 ns typical propagation delay, 4.5–18 V VDD operating range,
5 V UVLO, and a `-40 °C` to `140 °C` operating-temperature range. TI also
describes output-low behavior in UVLO and floating-input output-low behavior.
Primary references:
[`www.ti.com/product/UCC27517`](https://www.ti.com/product/UCC27517) and
[`www.ti.com/lit/ds/symlink/ucc27517.pdf`](https://www.ti.com/lit/ds/symlink/ucc27517.pdf).

`UCC27517` is a **candidate to investigate, not a selected part**. Its 5 V
UVLO must not be represented as satisfying the project's 12/13 V gate-drive
UVLO criterion. The electrical owner must either select a local driver/supervisor
combination that meets that criterion or explicitly approve a changed,
re-derived requirement. The cited repository study also found no published
cross-device propagation-delay matching number for this candidate; the full
two-channel skew budget therefore remains open.

## 4. Required authority artifacts and local-driver contract

The following artifacts are required before this candidate can leave
`stopped-indeterminate`. A product page, package photograph, or un-dated search
result is not an accepted substitute.

### 4.1 Identity, footprint, and insulation package

- Exact orderable MPN, suffix, package code, manufacturer data-sheet revision,
  and current lifecycle/approved-distributor evidence for both isolators and
  both local drivers.
- TI package drawing and recommended land pattern for DWW-16, plus the selected
  local driver package drawing and recommended land pattern. Produce reviewed
  KiCad `.kicad_mod` files with pad numbers, pin names, courtyard, assembly
  outline, polarity, and thermal pad treatment where applicable.
- A pin-by-pin schematic/netlist contract for each of the four ICs. It must
  name every used and unused ISO7741 channel, every supply/reference pin, and
  every no-connect or tie-off. No pin-count or package similarity inference is
  accepted.
- Rotation-resolved straight-corridor evidence for the complete replacement
  assembly, including the local-driver footprints and both floating secondary
  domains. The evidence must be digest-bound to the reviewed footprint files
  and must be measured by the repository's sanctioned geometry authority or a
  named external authority. A package headline such as `>14.5 mm`, or a
  modeled aperture/slot detour, is not a complete board measurement.
- Certification/mechanical ruling on whether the DWW-16 plus local-driver
  construction earns the claimed PD3 insulation path under the product's
  pollution degree, material group, altitude, enclosure, assembly, service,
  and conductor-retention conditions.

### 4.2 Required local-driver electrical contract

For the selected local driver (or explicitly approved two-part driver/supervisor
set), provide a versioned contract covering:

- input threshold and 3.3 V compatibility over temperature and supply;
- VDD range, quiescent and switching current, local decoupling, supply
  sequencing, and the physical reference for each floating domain;
- peak source/sink current, output impedance, negative gate-bias tolerance,
  gate-charge capability, and the approved gate resistor/pulldown values;
- propagation-delay min/typ/max, output rise/fall behavior, device-to-device or
  channel matching if published, and the test conditions used in the skew
  budget;
- explicit disable/shutdown implementation. If the part has no enable pin,
  document how active-high `SHUTDOWN` forces both gates safe under every supply,
  isolator, reset, and input-float condition;
- UVLO falling/rising thresholds, hysteresis, output state during UVLO, and how
  those values satisfy or intentionally revise UVL-01; and
- common-mode transient, negative-input, output-short, thermal-shutdown, and
  absolute-maximum behavior relevant to the `SW_NODE`-referenced channel.

The contract must include a schematic fragment, generated netlist, simulation or
equivalent calculation inputs, bench probe points, and a change owner. It must
not claim that the current UCC21550 contract transfers automatically to two
independent local drivers.

## 5. Acceptance criteria for the authority review

All rows are gates, not weighted scores. A missing artifact is `pending`; a
failed criterion is `fail`; only an independently signed complete set may be
`pass`.

| Area | Acceptance criterion and required evidence |
|---|---|
| Channels and domains | Exactly two independently traceable HS/LS channels. Each ISO7741 barrier and local driver has one named floating reference; no shared `VSSA`/`VSSB` or accidental `gnd`/`hv_minus` bridge. Channel direction, unused-channel tie-offs, input polarity, and 3.3 V logic behavior are checked in the generated netlist and by fault injection. |
| Timing/dead time | Re-derive the complete HS-vs-LS timing budget using measured or manufacturer-bounded ISO delay/skew, local-driver delay/skew, gate resistors, IGBT turn-off, supply corners, temperature, and representative bus/load. The minimum measured effective non-overlap must be at least the incumbent 300 ns requirement and preserve the 50 ns margin over the 245 ns turn-off figure. Scope both driver outputs and both transistor VGS waveforms; test startup, steady state, shutdown, and worst corners. A nominal 13 ns local-driver delay is not sufficient evidence. |
| Shutdown | `SHUTDOWN` remains active-high and set-dominant. Assert OCP, OVP, both thermal paths, watchdog/reset, firmware runaway-cut, and the independent RTD hardware path individually and in combinations. Both local outputs must reach and remain in the safe state; clearing a source must not resume PWM; only the qualified explicit reset may resume. Capture propagation time and prove no single ISO/local-driver fault can create shoot-through without a separately detected fault. |
| UVLO | Identify the exact 15 V gate-drive rail and the 3.3 V logic rail being protected. Demonstrate falling trip `<12.0 V` and rising recovery `>13.0 V` for the gate-drive contract, plus logic `<2.9 V`/`>3.0 V` where applicable, including tolerance, temperature, ramp rate, and output state. If the local driver's 5 V UVLO is retained, document the additional supervisor/architecture that closes the 12/13 V requirement; otherwise record an owner-approved requirement change. |
| Isolation/geometry | Use the actual approved DWW and local-driver footprints, exact pad geometry, rotation, courtyard/keepout, and final candidate net map. Both complete HS and LS paths must meet the 12.6 mm governing corridor. Slot/aperture detours require a separate certification ruling and cannot replace straight evidence. |
| Gate-loop area/inductance | Measure the routed, not merely placed, gate and source-return loops for HS and LS. The existing critical-loop checklist calls for each loop `<2 cm²` (200 mm²), gate resistor `<5 mm` from the driver, differential gate/source routing, no driver-to-resistor via where avoidable, and total gate trace `<30 mm`; the physics workstream also records a 500 mm² gate-loop ceiling. The electrical/layout owner must explicitly resolve this source-threshold difference before sign-off; until then, do not use the looser 500 mm² value as evidence of the stricter checklist pass. Record any inductance/overshoot simulation and scope result, including bootstrap-loop geometry. |
| BOM and sourcing | Reconcile the complete four-IC architecture and all support parts against source and schematic: ISO7741 ×2, local drivers ×2, decouplers, gate resistors, pulldowns, any supervisor/logic, bootstrap components, tie-offs, and test points. Every line has an exact MPN, approved package/footprint, lifecycle status, approved source, quantity, and owner. No distributor stock observation alone is permanent lifecycle or certification evidence. |
| Thermal | Calculate each ISO and local-driver dissipation from worst-case supply, frequency, gate charge, quiescent current, and switching load; use the selected package's thermal data, copper area, vias, airflow, and ambient envelope. Demonstrate junction/case temperatures over the stated `0–70 °C` ambient/derating envelope and shutdown behavior. The existing system document estimates 1.5 W total for the incumbent UCC21550 and `<100 °C` expected junction under good airflow; the replacement must provide a new four-IC budget, not reuse that number. |
| Failure modes | Deliver an FMEA and executable bench/simulation cases for: ISO output stuck high/low, channel direction/configuration error, local-driver input float/stuck high, each supply open/short/UVLO, isolator barrier/common-mode transient, local-driver output short/open, gate resistor open/short, gate-source pulldown open, bootstrap loss, thermal shutdown, reset sequencing, and one-channel-vs-other-channel mismatch. Every case names the safe state, detection path, time to disable, latent fault, and recovery authorization. |
| Board-level safety/certification | Mechanical/certification authority signs the construction, creepage/clearance, retention, vibration, assembly, service, enclosure, and pollution-degree interpretation. Electrical evidence and TI component certifications are supporting inputs only; neither the agent nor the repository may self-issue the IEC 60335-1/PD3 ruling. |

## 6. Required evidence package format

Submit a versioned packet with:

- signed decision matrix for every row in §5;
- data-sheet PDFs or immutable manufacturer revision/publication identities,
  SHA-256 digests, and retrieval dates;
- selected MPN and package/land-pattern files, with footprint-source digests;
- schematic fragment, generated netlist, pin/channel allocation, and BOM
  reconciliation report;
- timing/UVLO calculations plus calibrated scope captures and test conditions;
- routed HS/LS loop-area/inductance evidence and bootstrap-loop evidence;
- thermal calculation/model and measured temperature evidence;
- FMEA with fault-injection results; and
- a final statement that the production PCB, DRC ceiling, electrical domain
  manifest, environmental specification, and isolation constants were not
  modified by the authority review.

The packet must preserve unresolved items as `pending` and identify the next
owner. It must not repin the current qualification evidence or rewrite the
candidate verdict without a separately reviewed, digest-bound artifact.

## 7. Sign-off fields — intentionally blank

Each authority should write `APPROVE`, `APPROVE WITH CONDITIONS`, `REJECT`, or
`PENDING`, cite the exact artifacts reviewed, and record any condition as a
blocking requirement. A blank field is not approval.

| Authority | Required ruling | Artifacts reviewed / conditions | Verdict | Name and role | Signature/initials | Date |
|---|---|---|---|---|---|---|
| Board owner | Approve/reject the two-isolator/two-local-driver architecture as a candidate for a separate refloorplan; explicitly approve any protection-coverage change |  |  |  |  |  |
| Electrical/power owner | Approve channel, supply, timing, shutdown, UVLO, gate resistor, loop-area, thermal, and failure-mode contracts |  |  |  |  |  |
| Safety owner | Approve fault-latch integration, safe-state behavior, and recovery/reset semantics |  |  |  |  |  |
| PCB/layout owner | Approve actual footprints, pin maps, rotations, keepouts, routing/loop measurements, and manufacturability |  |  |  |  |  |
| Mechanical/assembly owner | Approve retention, vibration, clearance/creepage construction, assembly, service, and thermal/mechanical constraints |  |  |  |  |  |
| Certification/compliance authority | Rule on PD3/IEC 60335-1 applicability and whether the complete construction earns the claimed insulation path |  |  |  |  |  |
| Sourcing/manufacturer authority | Confirm current lifecycle, exact orderability, approved distributors, alternates, and change-control policy |  |  |  |  |  |
| Verification owner | Accept reproducibility, immutable source identities, calibrated measurements, and fault-injection coverage |  |  |  |  |  |

## 8. Repository source record

The following repository records were read for this request and are cited by
the commit at which each source currently resolves. They are evidence inputs,
not approvals of the replacement architecture.

| Source | Commit | Use in this packet |
|---|---|---|
| `docs/evidence/2026-07-30-pd3-isolation-mechanism-alternatives.md` | `57f0c7550a312bafd69d14f7ae8c0ace16fa12eb` | ISO7741 DWW-16 mechanism study; two floating domains; local-driver and skew gaps |
| `docs/evidence/2026-09-01-isolation-component-architecture-qualification.md` | campaign tree `85b4e400572a77d18f0ee6c644a532ab0a55dd8e` | Current candidate identity, stopped-indeterminate reason codes, protected baseline rule |
| `power_pcb_dataset/isolation_architecture_candidates.json` | campaign tree `85b4e400572a77d18f0ee6c644a532ab0a55dd8e` | Candidate manifest and required qualification axes |
| `docs/hardware/UCC21550_INTERFACE_CONTRACT.md` | `219136e056ee73c008aaee1e7f7e461a753b9ce2` | Incumbent supply, disable, latch, safety-pin, and domain contracts |
| `elec/src/components.ato` | `044114459c466bce67f6932c5046921279fdd3d9` | Incumbent UCC21550/IGBT identity and pin contract |
| `elec/src/modules.ato` | `8f0691418ff1f8455685d26be8164726bd2e51c6` | Two channels, 15 V floating supply, bootstrap, gate resistors, and 300 ns declaration |
| `elec/src/constraints.ato` | `1213c3e50974e5f3eb2e8efb63e0d1e6d837358e` | 400 V, 25 A, 12.6 mm PD3 and domain constraints |
| `docs/FUNCTIONAL_TEST_CRITERIA.md` | `c1f7025d37b32be9bb6ad2ac732dc43d399b9f18` | UVLO, thermal, and safety acceptance values |
| `docs/evidence/2026-07-25-uvl01-gate-drive-uvlo-unmeasured.json` | `464bd0589af740152b737d921116018aba968f12` | Existing UVL-01 ambiguity and no-fabricated-measurement status |
| `elec/validation/ucc21550_dt_sim.py` | `f98060fdc77951f831edb1b4393df87a1af18828` | Incumbent dead-time model and limits of datasheet-only simulation |
| `docs/hardware/CRITICAL_LOOP_DESIGN.md` | `07da91302daf49bb9b9a7b7d29de283d201f99b8` | Gate-loop geometry and 20 nH / 2 cm² checklist inputs |
| `docs/brainstorms/2026-07-08-physics-as-routing-constraints-requirements.md` | `67987177eecf571d213480781226beb1fe7e959f` | Separate 500 mm² physics ceiling, recorded here as a threshold requiring owner reconciliation |
| `docs/hardware/SYSTEM_THERMAL_BUDGET.md` | `07da91302daf49bb9b9a7b7d29de283d201f99b8` | Incumbent gate-driver thermal budget |
| `docs/hardware/BOM.md` | `29b338abb868b217dc95fdae6b7ab191b623a194` | BOM/source reconciliation and incumbent gate-drive support parts |
| `docs/hardware/PROTECTION_CHAIN_REVIEW.md` | `41d73a90bd02338397389c567853a3b4592376a4` | OCP/thermal/UVL/DESAT status and residual fault risks |

## 9. Current decision

**No authority ruling is recorded here.** Until the artifacts and independent
sign-offs above exist, retain the candidate as `stopped-indeterminate` under the
qualification engine. Do not edit `pcb/temper.kicad_pcb`,
`power_pcb_dataset/drc_ceiling.json`, `elec/domain_manifest.yaml`,
`docs/ENVIRONMENTAL_SPEC.md`, or the isolation constants as part of this
request. A later refloorplan is a separate, gated unit that may consume this
packet only after the required owners close the blockers.

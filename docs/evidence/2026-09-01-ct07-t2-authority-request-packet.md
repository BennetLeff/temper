<!-- provenance: commit=85b4e400572a77d18f0ee6c644a532ab0a55dd8e dirty=true (documentation-only request packet; no production design, board, DRC ceiling, or safety baseline changed) -->

# CT07 / T2 authority request packet

**Date:** 2026-09-01
**Candidate:** `sensing-hybrid-aperture-ct07-t2`
**Part:** ICE Components CT07-1000
**Purpose:** Request the external, electrical, mechanical, sourcing, and board-owner decisions needed before this candidate can be reconsidered for an OCP-02 refloorplan.

## Status and use

This is a request packet, not a certification, design approval, or qualification
record. **No external ruling is recorded here.** CT07 remains
`stopped-indeterminate` in the campaign decision package:
`docs/evidence/2026-09-01-isolation-component-architecture-qualification.md`.

The packet is intentionally bounded to the CT07/T2 aperture-primary mechanism.
It does not reopen the already-decided production board, change the PD3
requirement, or reinstate OCP-02. A recipient may return `rejected` or
`stopped-indeterminate`; only complete signed evidence may return `approved`.

## 1. Decision being requested

Please determine whether a CT07-1000, installed as a discrete primary
conductor through its aperture and with a redesigned OCP-02 burden network, can
be approved for a future single-board PD3 layout.

The requested decision must address all of these independently:

1. Does the actual CT07 construction have recognized reinforced-insulation
   authority applicable to this appliance and its as-built environment?
2. Can the installed primary conductor, aperture, secondary pins, PCB, and
   fixture produce at least **12.6 mm reinforced creepage** under the governing
   PD3 condition, including tolerances and the shortest real surface path?
3. Can the conductor and CT survive assembly, service, vibration, thermal
   cycling, fault current, and normal manufacturing variation without losing
   that path?
4. Can the revised circuit meet the OCP-02 electrical contract without
   weakening OCP-01 or silently changing the protection-coverage decision?
5. Is the exact part currently orderable from an approved source, with a
   traceable manufacturer identity and current documentation?

An answer to only one of these questions is not an approval.

## 2. Repository baseline and non-negotiable constraints

The current repository qualification campaign pins these production inputs:

| Input | Campaign-base SHA-256 |
|---|---|
| `pcb/temper.kicad_pcb` | `00a27419b82101e3518ddbf9d174f8359d76940c495ca1e5bd3d9cc32d7ac4d9` |
| `power_pcb_dataset/drc_ceiling.json` | `c6b2198e62ca5b15878884b1e2822a8b3bbd7372ace8f6198aeccffe83189fb2` |
| `elec/domain_manifest.yaml` | `f1899c87a61f579e2a92dbd673c1ad29036aed463b2f3fcc4ff7cca7f034bae3` |
| `docs/ENVIRONMENTAL_SPEC.md` | `afa367890d4872cce0033455ded49ea9b5826b9ba3a25229f4ec336d34cbaccf` |
| `packages/temper-placer/src/temper_placer/core/isolation_constants.py` | `486d54267087b467b4148e7eb3c91106f3950fc3784e527d786cf3f346aeae21` |

These values are copied from the campaign manifest at base commit
`85b4e400572a77d18f0ee6c644a532ab0a55dd8e`. They are identity pins, not
permission to modify the files.

The applicable project constraints are:

- PD3 is the honest as-built condition until a sealed, gasketed compartment is
  built and verified. The governing reinforced-creepage requirement for the
  relevant >250 V to 400 V band is **12.6 mm**, per
  `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` (last committed in
  `fe41fb78a4a2092af9663925d6156da5d4191c40`) and the pollution-degree
  determination at `991295c8dbfed7aa30a6206bbfd5949a89580ed8`.
- OCP-02's internal acceptance target is 60 A peak, 55–65 A, response under
  5 µs, in `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.1 (current board lineage
  includes commit `c1f7025d37b32be9bb6ad2ac732dc43d399b9f18`). That row is
  explicitly unmet and de-scoped/DNF today.
- T2, C37, and R65 remain off-board staging. Reinstating the channel requires
  an owner decision; it is not a consequence of this request.
- No answer may lower PD3 to PD2, count a manufacturer Hi-Pot number as a
  creepage path, or treat an unapproved model/footprint as a production
  artifact.

## 3. Known CT07 facts — transcribed, not yet approval evidence

The following are the bounded facts currently recorded by repository research.
They must be rechecked against a controlled, current manufacturer document in
the response package. They are not assertions that the candidate is safe.

| Topic | Repository record | Status for approval |
|---|---|---|
| Identity | ICE Components `CT07-1000` | Manufacturer must confirm exact revision and marking. |
| Mechanism | Single-turn primary: the primary is a customer-supplied wire or bus bar through the core aperture; there is no primary PCB pin. | Must be confirmed on the controlled drawing and installation instruction. |
| Secondary | Three pins (1, 2, 3), all secondary. | Must be confirmed, including pin numbering and allowable solder process. |
| Aperture | Drawing reports a Ø9.20 mm bore. | Confirm tolerance, finish, edge radius, and minimum usable opening. |
| Secondary layout | Pins are recorded as a 7.62 mm × 7.62 mm cluster in the recommended layout. | Confirm land-pattern dimensions and tolerances. |
| Ratio | `1:1000` nominal, single-turn primary. | Confirm tolerance, frequency dependence, and production test method. |
| Current | A 200 A reference rating is recorded as limited by the customer-supplied primary conductor. | Confirm continuous, peak, short-duration, RMS, and thermal conditions separately. |
| Manufacturer test | “Isolation Voltage (Hi-Pot) 3750 VAC” and a 60 Hz, 1 mA test are transcribed. | A manufacturer test is not an agency certificate and does not establish the 12.6 mm path. |
| Material | UL94-V-0 and “Material Group UL CTI 3” are transcribed. | Confirm the exact material, CTI test basis, and applicability to insulation coordination. |
| Agency status | No VDE/ENEC/CB/UL certificate number for the CT part was found in the bounded search. | Must be supplied or explicitly declared unavailable. |

### 3.1 Current manufacturer-primary references

On 2026-09-01 the following ICE Components sources were retrieved directly:

- Official product page: <https://www.icecomponents.com/product/ct07-series/>.
- Official one-page PDF: <https://www.icecomponents.com/wp-content/uploads/2023/10/CT07-Series-Datasheet.pdf>.

The PDF displays an **October 31, 2024** revision/date. The official page and
PDF identify `CT07-1000` as a 1:1000 single-turn-primary current transformer.
The PDF's table records the following manufacturer-primary facts: secondary
inductance **8 H minimum**, secondary DCR **26 ohm maximum**, current rating
**200 A RMS reference** (limited by the customer-supplied primary conductor),
typical SRF **3.2 kHz**, maximum ET product **6000 V-us**, and Hi-Pot **3750
VAC**. The stated operating-temperature range is **-40 °C to +105 °C**. Its
notes state UL94-V-0 flammability and UL Class A temperature-rating criteria.

These are manufacturer datasheet facts, not a certification-lab ruling. The
live page and PDF URL are not controlled signed authority evidence for this
project; the future submission bundle still requires a controlled document,
scope, and sign-off. **No digest is recorded for these live references**, and
no digest is inferred from the URL or retrieval date. Adding these references
does not change any qualification axis, candidate verdict, protected-input
pin, or pending reason code.

Primary research records:

- `docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md`, sourced from
  base `8d1884031462fb2f5d41811c4165469067057f13`, §3.3 and §3.5. Its CT07
  PDF was a session scratchpad source, not a committed vendor attachment.
- `docs/evidence/2026-08-13-t2-ct-replacement-creepage-and-placement-search.md`,
  whose original evidence lineage is `e3d28671a82d6cef29ecdb72a34e4871f6481ace`,
  §§1, 2.1, 4, and 5. It records the absence of a verified third-party
  reinforced-insulation certificate and the aperture mechanism's open status.
- `power_pcb_dataset/isolation_architecture_candidates.json` at campaign base
  `85b4e400572a77d18f0ee6c644a532ab0a55dd8e` records the candidate's stable
  identity, evidence references, and pending reason codes.

## 4. Questions for certification or insulation authority

Please answer each item with `yes`, `no`, or `not determinable`, and cite the
standard edition, clause, certificate/file number, and exact drawing or test
evidence. “The datasheet says reinforced” is not a sufficient response.

### 4.1 Component and installation scope

1. Is CT07-1000 recognized for reinforced insulation between the customer
   primary conductor and the secondary pins? Identify the legal manufacturer,
   exact variant, revision, agency, file/certificate number, and scope.
2. Does the recognition apply to a customer-supplied insulated wire or formed
   bus bar threaded through the aperture, or only to a factory test fixture?
3. Does the recognition apply at this appliance's OVC II, working-voltage
   range (>250–400 V), PD3 condition, altitude ≤2000 m, and 60 °C maximum
   ambient? If not, state the applicable derating or exclusion.
4. Does any claimed CTI/material-group rating establish insulation coordination
   for the installed path? If yes, identify the exact clause and boundary; if
   no, state what additional evidence is required.
5. Does the reported 3750 VAC Hi-Pot test provide any credit toward the
   creepage requirement? If yes, cite the exact rule. If no, state explicitly
   that it is only a dielectric withstand test.

### 4.2 Creepage path and aperture construction

6. For the supplied cross-section and 3-D installation drawing, what is the
   governing shortest creepage path from every accessible primary-conductor
   surface to every secondary pin and secondary PCB copper surface?
7. May the aperture path be credited as a board-layout-controlled path, and
   what surfaces must be included: conductor insulation, bore wall, component
   body, solder mask, bare FR4, and secondary solder fillets?
8. What minimum nominal and worst-case distance must be maintained so that the
   measured installed path is at least 12.6 mm after CT07, PCB, conductor,
   fixture, solder, and assembly tolerances?
9. Does any exposed conductor, stripped end, crimp, terminal, washer, mounting
   feature, or service access create a shorter path than the proposed route?
10. Is a discrete wire acceptable, or is a formed bus bar required? State the
    insulation system, material, thickness, voltage rating, bend radius, and
    permitted contact with the bore.
11. Does the authority accept the proposed conductor passing through the bore
    while remaining mechanically retained, or must the part/conductor assembly
    be certified as a combined construction?
12. Does a future PCB slot, keepout, coating, barrier, or enclosure change the
    answer? Do not assume credit: identify the construction and rule that
    grants it.

### 4.3 Required certification response

The authority response must include either:

- a signed approval with the exact CT07 variant, installation drawing,
  applicable conditions, path construction, and limitations; or
- a signed rejection/indeterminate response naming the missing evidence.

An unsigned email, a marketing page, or an agency logo without scope is not a
closed item.

## 5. Questions for the electrical owner

The following must be answered against the actual OCP-02 schematic and the
customer-conductor arrangement. Calculations must show tolerances, frequency,
temperature, waveform, and component ratings.

1. Confirm whether OCP-02 remains an approved requirement or remains DNF. If
   re-enabled, identify the independent fault that it covers beyond OCP-01 and
   the firmware safety layer.
2. Re-derive the CT07 transfer function for the real current waveform,
   including the nominal 1:1000 ratio, ratio tolerance, magnetizing current,
   burden loading, 35 kHz tank content, harmonics, and transient conditions.
3. For the 60 A nominal OCP-02 target, document the chosen burden value. The
   repository's preliminary arithmetic is **not an approval calculation**:
   `R = 2.5 V / (60 A / 1000) = 41.67 ohm`; E96 examples are 41.2 ohm →
   60.55 A and 42.2 ohm → 59.24 A. Recompute with the actual reference,
   tolerances, temperature coefficient, and comparator limits.
4. Show the full 55–65 A worst-case trip band and response under 5 µs,
   including filter delay, comparator overdrive, latch propagation, and the
   primary conductor's transfer behavior.
5. Demonstrate that OCP-01 still trips first over all declared tolerances and
   that the CT07 channel cannot create a new unsafe race, false trip, or missed
   trip.
6. Verify CT core volt-time/saturation margin at the actual peak current,
   duty cycle, frequency, asymmetry, startup, and fault duration. Do not use
   the 200 A headline rating as a saturation proof.
7. Verify continuous conductor heating, CT secondary heating, burden pulse
   energy, resistor power rating, comparator input range, and PCB temperature
   rise at 15 A RMS and the specified fault envelope.
8. Document the required supply, grounding, filtering, creepage/clearance at
   the secondary, and common-mode transient behavior after the T2 redesign.
9. Supply a schematic/netlist delta and a test plan. The production schematic,
   BOM, and board remain unchanged until the board owner accepts the complete
   packet.

## 6. Questions for mechanical, assembly, and PCB authorities

1. Supply an approved CT07 land pattern with revision, origin, pin-1 marking,
   courtyard, solder mask, paste, fab tolerances, and a 3-D model or verified
   body envelope.
2. Supply a dimensioned conductor-through-aperture fixture: conductor type,
   insulation, bend/strain relief, minimum radius, insertion direction,
   retention, service replacement, and maximum allowed movement.
3. Prove the conductor cannot drift toward the secondary pins under vibration,
   shock, cable pull, thermal expansion, reflow, wave/rework, or enclosure
   assembly. Give test method, sample count, acceptance limit, and result.
4. Prove the conductor and CT remain below their temperature ratings at
   continuous and fault current, including adjacent hot components and
   forced-air conditions.
5. Define the shortest as-built surface path in a released 2-D/3-D drawing,
   including all tolerances. The path must be ≥12.6 mm in the worst case; the
   modeled 13.2655 mm aperture path in prior research is not sufficient by
   itself.
6. Show every neighboring copper, via, pad, mounting hole, shield, chassis,
   fastener, and service opening that could create a shorter primary-secondary
   path.
7. Provide assembly inspection points and a production measurement method that
   can detect conductor displacement, wrong CT variant, wrong orientation, or
   insufficient insulation.
8. Confirm that the construction fits the current board envelope and routing
   without editing `pcb/temper.kicad_pcb`. If it does not, state the required
   board change as a separate future unit of work.

## 7. Questions for manufacturer and sourcing authority

Please attach controlled copies, not only URLs:

1. Current CT07-1000 datasheet revision and date, with document hash.
2. Manufacturer confirmation that CT07-1000 is active, orderable, and exactly
   the variant evaluated here; include lifecycle/PCN status and marking.
3. Approved distributor quotation or stock record, date checked, traceability,
   minimum order, lead time, and date-code restrictions.
4. Complete agency certificates/listings and scope statements, or written
   confirmation that no such certificate exists.
5. Written manufacturer limits for primary conductor construction, aperture
   loading, insulation, current, temperature, vibration, soldering, cleaning,
   and service.
6. Any application note that defines the primary conductor as part of the
   safety insulation system; identify what remains the integrator's duty.

## 8. Required submission bundle

The packet is complete only when the response includes all applicable rows:

| ID | Required artifact | Owner | Required identity / acceptance |
|---|---|---|---|
| A1 | Current CT07 datasheet and mechanical drawing | Manufacturer | Exact variant/revision; SHA-256; matches delivered marking. |
| A2 | Agency certificate/listing and scope | Certification authority/manufacturer | File number, edition, boundary, PD/OVC/voltage/temperature scope. |
| A3 | Certified or authority-approved installation cross-section | Certification/mechanical | Defines all credited surfaces and shortest path. |
| A4 | CT07 land pattern and 3-D envelope | PCB/mechanical | Released revision with tolerances and pin mapping. |
| A5 | Primary conductor/fixture drawing | Mechanical/assembly | Insulation, retention, strain relief, movement and service limits. |
| A6 | Worst-case creepage report | PCB/certification | Installed path ≥12.6 mm; method and all tolerances shown. |
| A7 | Vibration/thermal/reflow evidence | Mechanical/assembly | Samples, profile, limits, results, and post-test path inspection. |
| A8 | OCP-02 electrical re-derivation | Electrical owner | 55–65 A, <5 µs, saturation/thermal/HF margins, all corners. |
| A9 | Fault-coverage disposition | Board/safety owner | Explicit retain-DNF or re-enable decision and rationale. |
| A10 | Lifecycle and approved-source record | Sourcing | Current, traceable source and exact MPN. |
| A11 | Reproducible design inputs | Project owner | Hashes of drawings, calculations, test data, and tool versions. |

Missing, stale, unsigned, or scope-mismatched artifacts leave the candidate
pending; they must not be replaced with assumptions or a favorable headline
number.

## 9. Acceptance criteria for a future qualification rerun

CT07 may move from `stopped-indeterminate` to `qualified` only if all of the
following are true:

- identity, lifecycle, and approved sourcing are confirmed for the exact part;
- an agency/certification authority explicitly accepts the CT07 plus the
  customer-primary installation for the governing conditions, or provides a
  documented engineering basis accepted by the board safety authority;
- the approved installation and released footprint prove a worst-case,
  shortest real creepage path of at least 12.6 mm; the modeled 13.2655 mm
  result may be supporting evidence only;
- conductor retention, strain relief, vibration, thermal, assembly, and service
  evidence pass their declared limits;
- the electrical owner signs the complete OCP-02 transfer, burden, timing,
  saturation, thermal, and high-frequency derivation;
- OCP-01 ordering and fault coverage are preserved, and the board owner
  explicitly decides whether OCP-02 is re-enabled;
- all source documents and measurements are hash-pinned and replayable; and
- the qualification gate reruns successfully without changing any protected
  production input.

If any hard criterion fails, the outcome is `rejected`. If no hard criterion
fails but evidence is missing or an authority will not decide, the outcome is
`stopped-indeterminate`. Neither outcome authorizes a refloorplan.

## 10. Sign-off record — intentionally blank

Each signer must complete the decision, scope, conditions, evidence IDs, date,
and signature. Blank fields mean no approval has been granted.

| Role | Name / organization | Decision (`approve` / `reject` / `indeterminate`) | Conditions / deviations | Evidence IDs | Date | Signature |
|---|---|---|---|---|---|---|
| CT07 manufacturer |  |  |  |  |  |  |
| Certification laboratory / NRTL |  |  |  |  |  |  |
| Insulation-coordination authority |  |  |  |  |  |  |
| Electrical owner |  |  |  |  |  |  |
| Mechanical / assembly owner |  |  |  |  |  |  |
| PCB / fabrication owner |  |  |  |  |  |  |
| Sourcing owner |  |  |  |  |  |  |
| Board / product safety owner |  |  |  |  |  |  |

## 11. Change-control boundary

This document adds only a request packet. It does not alter
`pcb/temper.kicad_pcb`, `power_pcb_dataset/drc_ceiling.json`,
`elec/domain_manifest.yaml`, `docs/ENVIRONMENTAL_SPEC.md`, or the isolation
constants. Any future approved architecture must be implemented in a separate
plan and change set with fresh board geometry, DRC measurement/provenance,
electrical review, and qualification replay.

The current qualification result remains the authority until that work is
complete:
`docs/evidence/2026-09-01-isolation-component-architecture-qualification.json`
records CT07 as `stopped-indeterminate` with stable reason codes including
`aperture.certification_ruling_missing`,
`geometry.approved_aperture_footprint_missing`, and
`aperture.conductor_retention_authority_missing`.

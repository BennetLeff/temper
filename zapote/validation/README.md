# Rust validator coverage and next ports

Audit date: 2026-09-12. Historical inventory baseline: `6226537c9`.

**Current integration:** [coordinator checkpoint](integration-2026-09-12.md).
The historical inventory below remains evidence of the earlier state; P0 now
runs all seven maintained unit suites, native ERC/DRC, and the adopted P1–P3
subsets. The full P1–P3 plan is **not complete**.

Zapote uses selected copied Temper kernels and new unit-specific contracts. It
does **not** run the complete Temper Rust DRC/ERC engine. This inventory records
what is available, what has been copied, what the maintained units reported,
and what to connect next. It adds no engineering rules and changes no PCB.

## Evidence and counting

- [Dated machine-readable inventory](inventory-2026-09-12.json): source hashes,
  all 28 donor rule types, ten recorded port entries, 16 supplementary donor
  surfaces, seven unit report censuses, owners, test locations and gaps.
- [Temper donor table](temper-donors.md): the actual meaning and proposed
  disposition of every default-registry rule and the unregistered ERC stub.
- [Per-unit rule IDs](unit-rules.md): recorded rules and current Rust owners.
- [Fresh common-board run](common-board-checks-2026-09-12.json): seven current
  PCB hashes, command, binary hash and results. [Raw output](common-board-checks-2026-09-12.txt).

The Temper registry has **27 registered implementations**, plus one deliberately
unregistered placeholder. Registration was checked in source; the donor engine
was not run against the cooker during this audit. The supplementary module
census is discovery, not another count of engineering rules. Firmware checks,
every legacy Python check, all CI callers, and optimizer/router internals are
outside this inventory's complete scope.

The seven unit reports below were read from their retained evidence, not rerun.
Their hashes identify exactly which historical claims were inventoried. Their
source/board/suite bindings were not all requalified in this audit. Only the
common stackup gate was freshly executed on all seven current boards. A reported
rule ID is evidence of the report's declared check scope; it is not a measurement
of the number of objects evaluated or proof that the population was nonempty.
An absent success finding can mean a check reports only violations.

The prior **228 passing workspace tests** count regression cases across the
workspace, including policy and transport tests. They are not 228 independent
PCB checks. Physical qualification remains separate from all these counts.

## What executes today

`make -C zapote check` runs workspace tests followed by `check-units`.
`check-units` invokes the maintained [seven-unit manifest](units.json), calls
current unit truth functions, extracts current manufacturing geometry through
pcbnew, captures new native ERC/DRC, and preserves all outcomes. See the
[run command and limits](integration-2026-09-12.md).

`check-boards` remains an explicitly narrow stackup-only diagnostic. It is no
longer the complete-board step called by `check`.

The following table describes the historical inventory, before integration:

| Unit | Distinct rule IDs in retained unit report | Examples of recorded scope | Fresh shared gate |
|---|---:|---|---|
| RTD | 27 | Physical package/net binding, force/sense wiring, firmware correspondence, fault models, local decoupling and return geometry | Stackup PASS |
| Current sense | 12 | Component roles, source/model/interface checks, native connectivity, required copper, spacing and locality | Stackup PASS |
| Voltage sense | 13 | Exact topology/parts, ADC range, stress/OVP model, native binding, copper clearance and bypass locality | Stackup PASS |
| Thermal sense Rev B | 21 | Pin maps, threshold corners, open-sensor margin/settling, fault behavior, native binding, clearance and locality | Stackup PASS |
| Interlock | 14 | Pin maps, stateful digital model, input margins, interface assumptions, native binding, clearance and locality | Stackup PASS |
| Gate drive | 7 | Package graph, saved-byte/native binding, copper clearance, domain separation and bypass locality | Stackup PASS |
| PFC power entry | 7 | Source graph, saved-byte/native binding, physical connectivity, voltage-dependent copper spacing and nominal model | Stackup PASS |

Every retained unit report has overall **INDETERMINATE**, with reasons preserved
in the inventory. Empty `coverage_gaps` arrays on some reports do not mean full
qualification: those reports carry indeterminate findings instead. Gate drive
lists its domain-separation ID twice because the check is applied twice; that
is seven distinct IDs, not eight different rule types. RTD's historical report
predates the common stackup gate; the fresh stackup result is separate evidence.

Buck remains a delegated legacy experiment command. Neither buck nor a
standalone MCU appears in `UNIT_BOARDS`; this inventory establishes no current
Zapote full-unit run for either. They must be explicitly included or deferred
when defining the integrated cooker acceptance suite.

## What we reused

The [port ledger](../ports.toml) records independent copies, not runtime links
or automatic synchronization with Temper. The main physical kernels are:

| Donor | Zapote owner | Where it contributes |
|---|---|---|
| `temper-geometry/clearance_geometry.rs` | `zapote-drc/donor_clearance.rs` | Current-sense copper checks, reusable native clearance, gate-drive separation and PFC voltage profile |
| `temper-geometry/geometry_kernels.rs` | `zapote-drc/donor_geometry.rs` | RTD trace/region crossing geometry |
| `temper-drc-rs/ipc.rs` | `zapote-drc/ipc.rs` | Bounded RTD local-escape eligibility; not a full PFC ampacity gate |
| `temper-design-bundle/sexpr.rs` | `zapote-drc/donor_sexpr.rs` | Saved KiCad document parsing for stackup and document binding |

Other ledger entries cover memory policy/tests, RTD source contracts and
threshold derivation. New unit contracts are not retroactively counted as ports
of similarly named donor checks. Source lineage in this table follows
`ports.toml`; its historical hashes are preserved, not repinned by this audit.

## Transfer hazards found

1. `PowerDomainCheck` is an unregistered empty-result stub. It supplies no
   voltage-compatibility coverage to copy.
2. `FloatingPinsCheck` checks component membership, not every package pin.
   `NetConnectivityCheck` counts components, not connected physical copper.
3. `CreepageCheck` measures an isolation component's package dimensions, not
   the surface path between conductors. Rust clearance is not creepage proof.
4. `PadEntryWidthCheck` and `PowerPadTeardropCheck` use component dimensions
   and edges as pad proxies. The former selects nets rated at least 20 A,
   so a 15 A-class PFC input can be outside its selected population.
5. Several rules select by names or optional constraints. Missing barriers,
   current annotations, noise domains or stitching vias can yield no findings.
   Such an empty result must not become acceptance of a required property.
6. Loop-area, thermal-via and ground-plane rules include screening heuristics.
   Copy their useful fault cases while keeping their claims bounded.
7. Physical spacing, stackup, body collision, ampacity and electrical intent
   have different authorities. None substitutes for the others.

These are findings about the inspected code. Historical vacuity investigations
provided leads, but their old statements about CI or production-board status
are not asserted as current facts here.

## Next-port sequence

These are the approved implementation batches. Their current completion and
remaining implementation gaps are tracked in the coordinator checkpoint. Keep engineering
logic in Rust, retain the working KiCad adapter, and let agents choose edits.
Do not port placer/router search, auto-repair logic, or the entire donor graph.

### P0 — Connect existing checks into one complete unit run

**Deliverable:** one Rust composition entrypoint for each maintained unit,
dispatched by a common command, with explicit required-check coverage.

- Bind current PCB bytes, compiled source, native export, unit contract and
  suite revision. Reuse the existing unit functions and native-report validator.
- Run native ERC/DRC through the current transport with their command receipts;
  keep native results separate from independent Rust calculations.
- Distinguish required, applicable, executed and not-applicable checks. Record
  candidate/evaluated object counts, skipped objects and input gaps. A declared
  required rule that does not run must prevent complete acceptance.
- Return construction and qualification results separately. An allowed,
  specifically documented hardware deferral must not conceal a new missing
  input. Preserve each unit's current qualification gaps.
- Include or explicitly defer buck and MCU using their actual legacy owners;
  never relabel a delegated command as a Zapote suite pass.

**Verification:** execute all seven actual saved candidates; preserve the first
baseline and every failure. Inject stale export, omitted required rule, missing
report, empty required population and split-copper cases. Each must reach a
failing or explicitly incomplete final verdict. Prove the common command calls
the unit truth functions rather than merely validating old report summaries.

### P1 — Power paths, domains and insulation obligations

**First target:** the routed PFC and gate-drive candidates, then current sense
and the unit interfaces. There is no current full-power ampacity or insulation
qualification claim to preserve.

- Copy applicable `ipc.rs` numerical calculations, with tests, into the existing
  Zapote owner. Supply per-path RMS/peak current, minimum finished copper,
  permissible rise, actual trace necks, plated-via geometry and sharing
  assumptions. Do not infer currents from stale legacy net-name tables.
- Extract the useful isolation-barrier geometry and evidence-policy code.
  Cover actual pads, traces, vias and filled zones, all required layers,
  deliberate isolation devices and any missing barrier population.
- Define voltage/pin-role compatibility and permitted domain crossings from
  reviewed source contracts. Use exact pin IDs and intentional NCs. Do not
  register the donor power-domain stub or claim coarse membership is pin ERC.
- Audit `req_safe_01`, `creepage_check` and the voltage-spacing table as
  candidates. Preserve native creepage evidence where applicable. An actual
  surface-path requirement needs supported cutouts/material assumptions and
  an independent oracle; a package-size or Euclidean-gap proxy is insufficient.

**Verification:** passing baseline plus a narrow real PFC neck, removed via,
15 A annotated path, incorrectly classified intermediate feedback tap, missing
barrier, cross-layer bridge and intentional-NC mutation. Use independent
calculation/native geometry oracles. Missing physical/current assumptions remain
INDETERMINATE, never guessed into a pass. Record actual findings on both boards
before assigning agents any repairs.

### P2 — Mechanical and manufacturing geometry

**Donors:** `body_collision`, `dfm::check_annular_ring`, hole-clearance kernels,
and the `FabricationEnvelope` shape. Port exact geometry selectively; generic
bbox courtyard and pad proxies need correction before becoming authorities.

Bind native body/courtyard/Edge.Cuts polygons, drills, via spans, mask apertures,
assembly method and a selected fabricator's actual limits. Check all copper
against the real outline and cutouts. Missing heatsink/body geometry stays an
explicit gap. The donor body-pose API supports quadrants; unsupported angles
must be reported or deliberately extended with independent KiCad oracles.

**Verification:** body collision, undersized annular ring, drill conflict,
copper crossing an outline/cutout, missing body and unsupported-angle cases.
Replay all seven boards with object-level findings. No fabrication release
until applicable inputs and checks exist.

### P3 — Switching, return paths, thermal models and shutdown timing

**Donors:** loop/noise/parallel-run/return rules and selected
`temper-thermal` loss, temperature, finite-difference and fault-timing kernels.

Supply actual commutation paths, paired returns, aggressor/victim declarations,
device losses, heat-removal geometry, ambient bounds and component delay bounds.
Use placement heuristics as labeled screens. Do not describe bounding-box loop
area as loop inductance, via count as temperature, or nominal delay as a
guaranteed shutdown response. Keep thermal-sense circuit checking distinct from
thermal performance of the power PCB.

**Verification:** enlarged switching loop, disconnected return, missing required
stitching, thermally stressed neck/device and excessive shutdown latency. Keep
positive, boundary and violating cases; validate numerical models against an
independent calculation or measurement within their declared applicability.

## Definition of a completed port

A port is complete only when its needed donor code and meaningful tests are
copied, extraction changes and hashes are in `ports.toml`, the rule is wired
into applicable unit runs, and a real saved-board execution plus a discriminating
fault proves the wiring. Record units, threshold authority, applicability,
evaluated populations and unresolved assumptions. Donor/Python equality alone
is not correctness, and tests run against synthetic fixtures alone do not
establish current-board coverage.

Freeze a new inventory revision after each batch. Keep this snapshot and its
historical reports unchanged; update the README to point at the next snapshot.
Do not widen board acceptance or change thresholds merely to clear new findings.

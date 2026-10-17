# Round 2 electrical/mechanical integration

This packet controls the next **engineering prototype** revision after native19. It
joins the D17 commutation/protection work, D22 inlet work, and cooling/enclosure
work only when each has a traceable interface handoff. Native19 is the frozen
comparison article; its routed board and verification receipts remain unchanged.
As of the first two round2 electrical handoffs, no selected circuit/part/placement
change justifies creating a `native-20` PCB: D17 keeps the power-board circuit
and offers an off-board conditional interlock, while D22 rejects release and
reserves a precharge function without selecting its implementation. The next
native design should incorporate an actual approved ECO, not just a revision
number. The misleading source timing comment has been corrected and its
netlist-equivalence evidence is [recorded here](source-comment-verification.json).

## Baseline at intake

| Artifact | Identity | Meaning |
| --- | --- | --- |
| Native19 board | `native-19/section.kicad_pcb`, SHA-256 `3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b` | 240 × 160 mm, 142 parts / 89 nets, 0 DRC errors or opens and 0 parity findings in three final runs. Both FEM leg regions changed from native18. |
| Native19 schematic | `native-19/section.kicad_sch`, SHA-256 `29c4781b62930f03a067fc363fb36f5084a1eb454242812fb5d13ebc4e0ae22d` | Typed ERC had 0 errors and 16 documented warnings. |
| Atopile entry | `elec/src/power_stage_120v.ato`, SHA-256 `5af1c357dbb3da65aa878f581e4ab4fc98f67b9ab981375e2ddca8a97fd642e8` | Electrical source for native19 at intake; any D17/D22 circuit addition must be made here or in its imported source, compiled, audited, and projected anew. |
| R4 cooker | `output/temper-flush-front-r4/STEP/assembly.step`, SHA-256 `2e89923f65e466831395a10a2ac7e307ded48fbb8b49e5c19e87b4da1df21291` | Front packaging study with an imported older PCB. Its nominal front-to-board distance is not clearance or new-board fit evidence. |
| R4 front check | `output/temper-flush-front-r4/evidence/front-panel-validation.json`, SHA-256 `3ca63b8f368996f70576a38ce95f5f4962501f1e4c61b997007bcc66b0ac60e8` | Local front checks pass, but the full R4 assembly still collides with the retained protected PCB tray/lid. |
| Earlier cooling mockup | `prototype-closure/cooling/interface.json`, native18 SHA-256 `fb113d95819f1ea7cd8c27f929f7e88308eff44b663af85f71cd6f2bca5a0002` | Historical contact-bearing cold CAD for 135 parts. It omits the native19 HOT5 population; the new 142-part round2 study supersedes its fit claims. |

## Binding interface decisions

1. **Board/source identity.** A successor board gets a new `native-20/` directory
   only if a supported D17 or D22 electrical/layout ECO, or a supported cooling
   fit change, actually changes the design. Compile Atopile source first; pin
   all three exports and audit them before editing a native board. Preserve
   component MPN, footprint, pad/net, and schematic-instance parity. Report
   changes against native19 by UUID and by copper/net membership; a zero-error
   DRC alone cannot show that the new protection path was implemented.
2. **D17 power and protection.** The handoff must pin native19 extraction inputs
   and actual leg A **and B** results to this board hash, state copper/port
   locations, and separate simulated commutation from measured shutdown.
   Earlier native18 curves cannot validate native19's changed copper. A
   controller-side interlock proposal may live on a separate board; whether
   it belongs on the power board is an explicit circuit/interface decision.
   Document connector pin, fault polarity, fail-safe supply loss, latch reset,
   startup, and worst-case command-to-current-extinction budget before routing.
   The [D17 round2 ECO](../d17/ECO.md) calls the 74AHC30 interlock conditional
   and warrants no new power-board pad by itself. Both leg meshes pass topology
   checks, but their field matrices remain unsolved on this host.
3. **D22 inlet.** The handoff must state whether the selected filter/fuse/inrush
   elements are on the main board, a separate protected module, or the harness.
   Provide exact part identities and voltage/current/thermal limits, terminal
   pinout, line/neutral/PE path, mechanical envelope, attachment, required
   insulation construction, and the simulation-to-product evidence boundary.
   A nominal RF filter curve or a 110 × 80 × 50 mm allocated box is not an
   approved fit or supply-disconnect scheme.
   Its two-way diagnostic finds passive startup bus peaks above the earlier
   normal rectified-bus assumption while gate drive is disabled. Before
   treating existing PCB spacing or component ratings as accepted, the
   electrical and safety owners must disposition the actual startup/surge
   waveform, MOV energy, insulation voltage basis and precharge implementation.
   The [D22 round2 result](../d22/README.md) keeps powered filter/PCB release
   on HOLD and has not selected a precharge component or board footprint.
4. **Cooling and retention.** The [round2 cooling revision](../cooling/README.md)
   imports all 142 native19 references and adds a contact-bearing sink,
   independent measured-shim process, board carrier, airflow passages, and
   inlet allocation. The existing edge shoes are only a zero-added-
   margin outer-copper screen. The revised cold assembly must include all
   source-matched component bodies, selected device lead/contact geometry,
   insulating interfaces, clamp force path, fan/duct/guard, board restraint,
   conductor routes, PE sink/chassis path, and the R4 compartment barrier.
   Its fit result must report both intended contacts and unintended collisions.
   The round2 cooling interface omits R4's old covered tray and lid allocations
   from its collision import. A passing new-to-native check on that reduced
   set cannot close full-cooker fit; a replacement protective chamber and
   serviceable cover must be modeled and checked in the same revision.
   The routed PE braid was moved clear of the filter, fan and cradle in the
   final nominal cold check. Its 16 remaining new-to-new intersections are
   accounted for as intended thread engagements; physical fit and bond
   performance still need qualification.
5. **Test access.** Native19 has 19 candidate pad-derived signals and no new
   testpoints or mounting holes. The probe study explicitly leaves full copper
   tip containment, actual mask aperture, fixture fit, and instrument ratings
   unverified. Preserve access to current-sense/Kelvin, gate, bus, fault, HOT5,
   and controller signals after mechanical integration. If an added circuit
   removes a probe path, identify an actual replacement and its safe fixture
   state. No handheld live probing is justified by a CAD toe coordinate.
   The [native19 measurement access inventory](measurement-access.md) names
   raw bus, input, feedback, fault and Kelvin contacts for the D17/D22 handoffs.

## Promotion gates

| Gate | Required record | Current status |
| --- | --- | --- |
| G1 electrical source | Exact compiled component/net counts; source, CSV, netlist and resolved-part hashes; source audit and negative controls | Native19 source-comment correction recompiled and audited as circuit-equivalent; no selected round2 circuit ECO to promote |
| G2 native parity | Typed ERC; three all-track DRC/zone-refill runs; zero errors/opens/parity findings; all warnings enumerated; footprints and 3D models pinned; rule voltages revisited after D22 startup/stress disposition | Native19 baseline only |
| G3 new physics | Native19-or-successor leg A and B extraction, Kelvin-error/fault-budget disposition; D22 nonlinear inlet/inrush/burst bounds tied to final circuit | Native19 copper and both-leg meshes verified, but field matrices not solved; D22 averaged-load diagnostics completed, final controller/line/tank coupling and measured fault/thermal evidence pending |
| G4 installed assembly | Populated board, sink/fan/coil/harness and R4 protective compartment in one coordinate frame; collision/contact/tolerance/insulation review | Native19 cold STEP has zero unexpected nominal intersections; protected chamber/cover, connector exits, service access, contact/thermal/wiring and tolerance evidence remain pending |
| G5 first article | Supplier drawing/stackup/critical materials, build and inspection traveler, probe/fixture review, controlled low-energy plan | Pending actual part/process selection |
| G6 powered release | Qualified station, component-rating/insulation/earthing basis, measured faults/thermal/EMI and signed disposition | NOT RUN; outside this digital candidate |

The evidence-based [round2 disposition](disposition.md) records what the
completed D17 and D22 investigations actually close, the native19 equivalence
check, and the remaining design decisions that control the next PCB revision.

The round1 [integration packet](../../../../../docs/research/mit-product-design/resolution/integration/README.md)
contains supplier, market, interface, and user-trial templates. Its native18
part count, board geometry, and thermal table are historical. Refresh its
revision-specific claims rather than treating those checks as native19 results.

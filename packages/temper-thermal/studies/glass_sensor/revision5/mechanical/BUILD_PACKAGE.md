# R5 cartridge geometry and assembly candidate

**Stage: dry controlled engineering prototype preparation. Physical outcomes are NOT_RUN.**

Two complete CAD comparison assemblies share the same main carrier, local flexure, RTD, bond, moving joins and formed lead route. D8 retains the 8 mm sensing face. D6 has a 6 mm sensing face and six recessed ears; its exposed face is 0.15 mm above the ears. The 6 mm face is not a gimbal: the existing local flexure supplies independent axial compliance. A 4 mm face was rejected because the 2.7 × 2.5 mm bond, 2.3 × 2.1 mm RTD and protected moving joins cannot be fitted with the current arrangement. D6 is a comparison candidate, not a thermal winner selected on mass alone.

## Coordinate and movement contract

Units mm. Glass top z=0. Rest face top z=0.60; roof thickness 0.15. The common carrier moves 0–1.2 downward. The sensing island moves locally to the 0.25 stop or 0.10 upward capture. The cap, RTD, anchor, both native-terminal joins, insulating covers and the entire upper formed lead route move together; the cap has 0.20 additional lift before its three hooks capture the island. Only the lower service loops bridge this moving group to the stationary outlet. Loaded pose uses common0.490909/local0.109091, inherited from the coupled spring solution. These positions are geometry inputs, not newly solved equilibrium.

D8 has three 2.0 mm zirconia posts. D6 posts shorten to1.85 mm under recessed support ears. The three retained hook toes retain0.20 mm nominal clearance. CAD establishes nominal fit and contact/capture positions, not strength, tolerances, fatigue or glass safety. Ceramic upper fingers complete the downstream retention path; strength qualification remains open.

## Moving join and lead detail

Each native nickel terminal is represented by a1 mm ×Ø0.20 segment ending under an insulating cover. Two copper conductors branch at each terminal. Four finite Cu/Ni weld-bead **process envelopes** connect each stripped copper end to its terminal. Their overlap is intentional; bead shapes are clearance and thermal-mass allowances, not an approved weld process. Supplier received-terminal dimensions, Kelvin datum, welding process/sections, pull strength and temperature drift still require measurement.

Each copper wire has60 mm developed cut length, including0.5 mm proposed stripped hot end; jacket length59.5 mm. CoreØ0.08 and PFA outsideØ0.232 are inherited candidate dimensions. The four smooth routes have explicit0.5 mm minimum static forming radius and2 mm dynamic service-loop radius. The hot route, joins and anchor move as one rigid assembly; cyclic deflection is reserved below the stem near z−30…−47. Neither radius is a supplier-approved limit. In particular the0.5 mm static bend implies substantial conductor forming strain; the coupon must qualify forming, jacket integrity and springback. A valid solid does not establish those properties.

The cap anchor is1.3 ×1.5 ×0.72 mm before subtraction, top z0.45, with two wire elevations±0.15. Exact routed channels are subtracted, avoiding the crossed fanout and unsupported spline volumes found during iteration. Effective thermal anchor length is a **1.0 mm modeling allocation within a1.5 mm pad**, not a measured wetted length or guaranteed conductance. `wire_hot_length_mm` includes this1.0 mm allocation; subtract it to obtain the disjoint hot-before-anchor segment. Geometry JSON gives every wire separately. Mean disjoint hot/anchor/cold lengths are for model comparison; all individual lengths remain available.

Each insulating join cover starts from1 ×1.4 ×0.8 mm, with a hollow cavity and explicit wire/weld relief. The top0.075 mm of its remaining feet is Resbond attachment film; only the remaining material is counted as ceramic. This avoids a massless or zero-thickness attachment. The exact bond area/volume and ceramic volume are exported. Dense insulating ceramic is a process candidate; attachment strength, coverage, pinholes, creepage in contamination and exposed-joint protection are not qualified. Slot reliefs are not a hermetic seal.

## Prototype sequence and inspection

1. Inspect the glass reference fixture, fixed housing, carrier and positive local stops. Record actual datums, aperture and free travels. Do not infer glass strength from the mock ring.
2. Form and inspect the three cap hooks and, for D6, the recessed ears. Inspect each hook independently for gap and weld quality. Control face flatness before/after attachment; no process capability or drawing tolerance is invented here.
3. Attach the RTD with a measured0.10 mm bond coupon. Inspect cured thickness, coverage and voids on sacrificial sections. Follow the supplier's received-current cure instructions.
4. Weld the two current/sense wire pairs at the native terminals, using stripped0.5 mm sections and a qualified process coupon before any full cartridge build. Inspect both terminal groups remain electrically isolated.
5. Install the cap-moving insulating covers on their finite0.075 mm attachment films. Form the static routes, install the two-level hot anchor with intact PFA, and inspect all channels before closing the assembly.
6. Assemble the three support posts, island, local blades, clamps and catches. Thread the four wires through the open bore; set the lower service loops. The cold outlet remains a fixture interface rather than a qualified connector/feedthrough.
7. Inspect all six motion states and measure the combined harness/witness reaction hot and cold. Record each loop, springback and any rubbing. Then conduct the independent thermal/force/retention/fault tests in the R5 validation package.

Welds, cured bond thicknesses, formed leads and membrane interfaces require inspectable prototype fixtures. There are no approved production tolerances, cycle counts or service loads in this package. Every physical measurement remains NOT_RUN.

## Sealing and diagnostic limits

The inherited Kalrez6375 membrane/gasket remain explicit **envelopes**, and witness/lead passages remain open. The stationary pressure-equalization tube and cold plenum studied by the safety workstream are interfaces for a dry bench fixture, not installed or qualified liquid barriers in these STEP assemblies. No closed spill boundary, food-contact approval or250°C seal assembly qualification is claimed. A seal supplier's complete geometry and force data will require a new CAD revision and thermal/force rerun.

The optical witness geometry is inherited. It does not solve seized-island, frozen-sample or insulating-debris observability. No production backend is enabled.

## Evidence and files

`build.py` imports the exact SHA256-pinned R2 CAD generator from `../../revision2/mechanical/build.py`; scratch execution can use `r2_pinned.py`. This is dimensional CAD only. Rust owns physics. Run with the prepared CadQuery2.6.1 interpreter, then run `audit_routes.py`.

`thermal_geometry.csv` is the scalar contract; `geometry.json` records part volumes, per-wire lengths and pose checks. `route_audit.json` reports wire-vs-rigid and wire-vs-wire intersections separately. Flexible seal envelopes and witness parts are omitted from the rigid fit census; welded overlaps are deliberate and excluded. All reported positive-fit results concern nominal geometry only.

For STEP, the jacket envelope includes the copper interior and is one physical outside solid, with its first0.5 mm reduced to copper diameter. Material volumes are separately computed from the actual core and jacket lengths, so thermal mass never uses an inflated bend envelope. Earlier unconstrained spline routes had an incorrect swept volume and were replaced by tangent circular-arc routes. The final swept volume agrees with analytical material volume; this is a geometry check, not evidence of manufactured bend quality.

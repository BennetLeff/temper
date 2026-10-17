# Preserved-exterior packaging decisions

The studies use R4 world coordinates: X left/right, Y front/rear, Z up, in millimetres. These are dimensioned **allocations**, not a populated native-18 ECAD export. A bare 240 × 160 × 1.653 mm board is placed at min corner (-110.5, 70, 30.25); its thickness comes from the saved KiCad stack. No electrical clearance is inferred from its fit inside the old chamber.

## Four tested placements

| Study | Sink min XYZ; body XYZ size | Result against retained R4 |
| --- | --- | --- |
| Initial rear bay | (-152.5, 350, 12); 305 × 60 × 68 | Four intersections with rear foot bolts/nuts. Reject this placement. |
| Shifted rear bay | (-152.5, 338, 12); 305 × 60 × 68 | Zero volume intersections, including the two end-fan boxes. A disconnected space candidate only. |
| Direct rear edge | (-152.5, 236, 12); 305 × 60 × 68 | Twenty intersections: chamber, sensor, spring cap, gland and service-hatch hardware. Reject this placement. |
| Direct front edge | (-152.5, 4, 12); 305 × 60 × 68 | Ninety-three intersections, predominantly front structure and controls. Reject this placement. |

All four have zero box-to-box volume intersections. The shifted candidate contains 285 reimported valid solids, including 252 retained R4 named parts and five new boxes. The other rejected cases remain available to inspect the actual conflict list; no collision count represents a tolerance or insulation test.

The transverse rear candidate comprises a 305 mm body and two 25 mm fan depths: 355 mm total. R4 side-wall inner planes at x=±183 leave **5.5 mm nominal per end** before brackets, guards, duct walls, inlet/exit turns and tolerances. At y=338..398, the sink ends 2 mm behind the nominal y=336 rear-support-tube extremity and 6 mm before the rear-foot bolt centerline y=404; compare actual bolt/nut bounds, not just centers. Sink top z=80 is 5 mm below nominal coil-support underside z=85. These small remaining spaces are procurement constraints, not approved margins. The existing exterior has rear intake/exhaust features; end fans pointing at side walls do not create an airflow path through them.

The additional 110 × 80 × 50 mm box at (-140,250,15) only asks whether the **previously discussed D22 volume** fits. It is not an approved EMI module. It omits terminals, cord strain relief, line/PE routing, isolation and heat. No volume has yet been assigned to the dedicated fan supply, complete controller, production harness or additional protection components.

## Why a rear box is not an integrated cooling solution

Native-18 locates Q5/Q6/Q3/Q2 at footprint origins (92.55,4.215), (110.55,4.215), (132.55,4.215), (150.55,4.215) and BR1 at (16.3,4.6), on the **y≈0 edge**. Origins are pad/footprint datums, not thermal-contact centers. In the unrotated allocation that edge is at world y=70; the rear sink starts at y=338. No contact, spreader or heat transport path bridges this arrangement. Turning the board moves connectors and changes its mains/coil routing; the rear-edge probe illustrates obstruction, not an accepted transform. A narrow heat-pipe or remote-sink proposal would require its own transport/contact/insulation proof and is not authorized by D18.

The defensible next option is **joint compact-sink and PCB packaging work**, with the current five-device contact pattern, clamp service access and insulation modeled together. The previously documented Fischer LA6 200 mm class is a screening lead, not a selected substitute. Its actual curve, mounting sites, fan depth and insulated interfaces must meet D18 before it displaces the 305 mm example. Repositioning power devices changes lead and switching geometry and belongs in the PCB/power review. Do not stretch leads or silently remove the protective chamber to recover fit.

## Supplier drawing request, ready to send by the owner

Provide the selected package-controlled mating faces for four IPW65R018CFD7 devices and GBJ2510-F, proposed sink plane and orientation, individual/worst combined heat-source map, 50 °C inlet, ≥20 CFM delivered, RθSA≤0.15 °C/W and each MOSFET interface RθCS≤1.0 °C/W. Request:

1. Dimensioned complete sink/fan/bracket/guard assembly and mounting-hole pattern; maximum material envelope, flatness and tolerances; contact-face machining and finish.
2. A mounting-specific thermal curve at actual operating pressure/flow, including nonuniform heat-source positions; fan pressure/flow curves and allowable inlet restriction. Identify what was simulated versus tested.
3. Insulator, compound and clamp specification including isolation rating, maximum pressure/force, torque method, flatness, creep/relaxation and replacement procedure. Sink is PE bonded; a thermal pad alone is not an accepted insulation system.
4. An assembly drawing showing exposed fasteners and tool access without loading device leads, plus fan cable exit and guards. Include the dedicated 12 V supply as an independent selection.

Dimensions for the illustrated body and fans were checked against [Wakefield's 2026 rev1.0 catalog, pp3–4](https://wakefieldthermal.com/content/catalogs/Catalog-SkivedFinHeatsinkAssembly.pdf): 305 × 60 mm body with 60 mm fins and 8 mm base; 60 × 60 × 25 mm fan class. The SFA2B1L catalog thermal value is simulated for full ducting. This input is not an installed-performance guarantee or complete assembly envelope.

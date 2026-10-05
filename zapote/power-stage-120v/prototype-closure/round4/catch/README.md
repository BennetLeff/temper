# Catch carrier and native bleed PCB — round 4

**A real routed bleed PCB and a detailed catch-carrier design now replace the
36 × 20 mm allocation. This is an engineering design, not a fabrication or power
release.** Native19 is unchanged. The isolated AMC3330 card remains the supervisor
owner's unrouted 60 × 35 mm allocation; it is not included in the bleed PCB's ERC
or DRC result.

## What is implemented

- [Native KiCad project](native/catch-bleed.kicad_pro), schematic, board, local
  symbols/footprints and explicit 8 mm copper-clearance design screen. The
  **80 × 34 × 1.6 mm** board has eight actual VR37 footprints, 15 mm lead pitch,
  1 mm drill / 2.4 mm pads, 0.6 mm traces, two mounting holes and four separately
  identified wire terminals. Its two 400 kΩ chains have no shared board copper.
  Schematic-export connectivity verification includes three rejecting mutations.
- [Assembly STEP](../../../../../output/temper-prototype-closure/round4/catch/r4-catch-carrier-routed-design.step)
  includes capacitor leads, a vertical pin carrier, 8 × 1 mm copper terminal
  straps, body cradle and retention straps, the bleed board and resistor bodies,
  mounting posts/support deck, a stepped removable guard, nominal diode body,
  floating cathode spreader, diode interconnect, DIN rail, lug/boot envelopes,
  real circular wire bends and split collars. These are authored engineering
  models; the diode and terminal shapes are not vendor-certified solid models.
- Three explicit maximum-diameter conductor routes, with 401 sampled centerline
  points each, in [route geometry](../../../../../output/temper-prototype-closure/round4/catch/route-geometry.json).
  This replaces the unsupported 150–220 mm route reservation. The layout is not
  uniformly paired: C5 obstructs convergence from the two bus studs.
- [Dimensioned assembly sheet](../../../../../output/temper-prototype-closure/round4/catch/catch-dimensioned-review.svg) and [candidate/custom BOM](bom.csv).
- A source-backed resistor/wire/pin-capture calculation, exact input hashes,
  reproducible adapters and recorded open interfaces.

## Circuit and assembly identity

```text
native19 J8 BUS_P -- FC1 FWP-10A14F / US141 -- DC1 pin3 ANODE
                                                  |
                                      DC1 pin2 CATHODE/CASE -- CC1 positive pair
                                                                |       |
                                                          J1-R1..R4-J2  |
                                                          J3-R5..R8-J4  |
                                                                |       |
native19 J10 HV_RET -------------------------------------- CC1 negative pair
```

DC1 pin 1 is **NC**. Its exposed case and proposed spreader are **CATCH_P**, not
PE or an insulated heatsink. CC1 is the 47 µF / 700 V `B32778H8476K000` candidate;
the manufacturer's four-lead grid is 52.5 × 20.3 mm with 1.2 ± 0.05 mm leads.
Both same-polarity pins share a supported copper strap. The 2.8 mm capture holes
allow a stated conservative two-axis ±0.4 mm lead-grid / ±0.1 mm machining
allocation and −0.05 mm hole-size allowance: only **0.043 mm radial residual**
remains. This is a tolerance screen, not solder-joint qualification. Coupon the
large-hole joint, pin centering and solder fill before accepting that process.

J1 and J3 each connect independently to the positive capacitor strap; J2 and J4
each independently to the negative strap. They are `CATCH_P_A/B` and
`HV_RET_A/B` on the PCB so no fictitious on-board connection is implied. Do not
bridge the intermediate nodes or use them for sensing. Preserve both local
bleeds when unplugging the supervisor. The AMC3330 input is a separate
1,994,490 Ω divider across the capacitor; it receives AUX **3.3 V**, not the
superseded 5 V proposal. Remote/pod six-pin contract: 1 POD_3V3, 2 AUX_0V,
3 VCATCH_P, 4 VCATCH_N, 5 VCATCH_DIAG_N, 6 AUX_0V. The candidate
Amphenol 20021121-00006T4LF still needs its mating cable and footprint review.
Do not credit that monitor as a redundant safety bleed.

Only native19 J8 and J10 are used. No current returns through `LEG_RET`,
`OCP_KELVIN_P` or `OCP_KELVIN_N`. The retained native19 board identity is
`3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b`.

## Mechanical decisions and actual changes

The bleed board is at world **[25, 369, 81] mm**. Resistor tops reach 87.1 mm;
the rear guard reaches 90.5 mm. The forward guard is lower to clear the coil
support and ferrite. The sensor-card allocation stays at X103..117, Y348..408,
Z43..78. It is deliberately separate from the passive board.

US141 moves **6 mm forward**, to X17..124, Y342..418.5, Z12..38.5. Including a
real 7.5 mm DIN-rail depth exposed the old rear-channel conflict: the previous
pose would extend to Y432, inside the Y428..433 mains corridor. The new rail ends
at Y426. This changes service access: the conservative opening projection starts
at **Y324.5**, intersecting the installed PCB-hood rear wall at Y325.5..327.
After unplugging and verifying every stored node discharged, remove the PCB
hood rear service panel and the catch front panel before opening FC1. The
public holder drawing does not establish an actual hinge sweep or permission
for sideways mounting; those remain supplier-interface holds.

The pin carrier is retained by four M2 locations into cradle walls; capacitor
mass rests on the cradle, not its soldered leads. The bleed PCB has its own
crossbar/posts. The upper guard uses four M3 bosses on the carrier deck.
Carrier base holes are Ø3.4 at [23,334], [118,334], [23,424], [118,424] mm; the
matching chassis drilling, fastener/earthing stack and full load qualification
remain to be incorporated into a released mechanical package.

The paired-wire saddle uses the rigid left carrier rail, with proposed M3 pilot
locations X−119 / Y285 and Y293; the floating PCB shoes and native board gain
no new holes. The STEP applies those rail holes and the rear-hood wire ports.
PEEK saddle/post and guard material choices, thread creep, clamp retention,
edge/bushing tolerances, and repeated assembly have not been physically tested.

Alpha 3080 12 AWG has a current primary-source OD of **3.8354 ± 0.1016 mm** and
5×OD bend radius. The model uses **3.937 mm OD and 22 mm circular bends**, exceeding
the 19.685 mm maximum-OD minimum. TE160163-2 is the candidate M4 lug. Its catalog
insulation window starts at 3.81 mm; the wire's minimum OD is 3.7338 mm, so the
combination's insulation support is **not tolerance-qualified**. Confirm the
actual crimp/tool/insulation support or select a compatible lug before harness
release. The boot/lug solids are envelopes, not a resolved crimp drawing.

## Electrical and geometry evidence

KiCad 10.0.4: **ERC 0 violations**; three final DRC samples each report **0
violations, 0 opens, 0 schematic-parity discrepancies**. The 8 mm rule is an
internal live-node engineering screen; it is not an appliance insulation
standard determination. The completed board has no SELV, accessible metal or PE
copper. The diagram export was visually inspected for independent chain routing.

The 663-solid STEP was reimported and all 5,151 unique pairs of new parts
were screened. No unclassified internal intersection remains. The retained
contacts explicitly include nominal thread interference and unresolved insulated
wire sweeps through lug, diode and capacitor termination envelopes. Carrier and
sensor geometry clear the retained context; one fuse-holder wire landing remains
provisional. This is not a worst-case tolerance or supplier-fit pass.

The three wire centerlines total **842.186 mm**, excluding internal fuse path,
lug metal and copper-link/terminal contributions. Manufacturer nominal wire DCR
gives **4.835 mΩ at 20°C** and an illustrative copper-temperature screen gives
**6.451 mΩ at 105°C**. These are wire-only values. The historical 0.155225 A²s
diagnostic pulse would dissipate 1.001 mJ in those wires at that resistance; this
does not prove fuse, joint, diode or cable fault survival. The coupled-model owner
uses separate assumed contact/fuse losses and 1/3 µH sensitivity cases.

**No loop inductance has been extracted here.** Sampled routes are provided for
the field owner. The holder's internal path and public-drawing terminal locations,
native bus closure, diode leads, distributed capacitor current and nearby metal
must be included in an installed loop solution. 0.2/1/3 µH are sensitivity inputs,
not measured bounds.

Bleed dissipation is 0.196 W at 198 V, 0.613 W at 350 V and 1.8 W at 600 V.
With a deliberately asymmetric ±7% resistance allocation, one resistor sees
0.259 W at 600 V and **0.352 W at 700 V**. The linear P70→155°C screen gives only
0.294 W at 105°C: **the capacitor's 700 V nameplate is not a continuous 105°C
bleed operating rating**. No 700 V operating envelope is released. The actual
enclosed temperature and waveform remain to be correlated.

One remaining bleed branch, +10% C and +7% R, takes 54.36 s for 350→30 V and
**66.29 s for 600→30 V**. The supervisor's 60 s lockout is a minimum delay;
measured valid voltage below threshold remains mandatory. Never infer discharge
from elapsed time, a dark display, contact position or an unpowered ADC.

## Remaining digital work, separately from physical validation

1. Resolve the exact US141 terminal/hinge/rail seating drawing and fuse pairing;
   fit its terminal boots and final tool access. One recorded route-to-holder
   envelope overlap is a provisional terminal landing, **not a clean fit result**.
2. Finish the supervisor owner's isolated card placement/routing and bring that
   native geometry into this assembly. Its reservation does not count as a PCB.
3. Release the diode mounting/lead plane, local carrier copper and pulse-rated
   joints. The current nominal body/link/spreader is a reviewable layout, not a
   completed power-copper board or a selected thermal joint.
4. Solve the complete catch loop, qualify the crimp/boot and bushing interfaces,
   finish matched chassis fasteners/PE details and do the worst-case tolerance
   review. Preserve the listed geometric/supplier uncertainties in that work.

Supplier drawings and circuit/mechanical decisions can close much of this work;
it must not be described as blocked solely by absent hardware. Physical gates
then include cold assembly/pull/service trials, solder coupons, thermal and
dielectric checks, installed current/voltage capture, hot DC fuse coordination
and first-unit fault testing. There is no assembled or energized article here.

## Primary sources and replay

- [Vishay VR25/VR37/VR68, document28907, 03-Jun-2025](https://www.vishay.com/docs/28907/vr25vr37vr68.pdf), pp.1–2,4,8: dimensions, ordering and power/temperature limits.
- [TDK B3277*H, June2026](https://www.tdk-electronics.tdk.com/inf/20/20/ds/MKP_B32774H_778H.pdf), pp.3,15: four-pin geometry and selected row. Browser read succeeded; direct download returned403; no fetched-PDF hash is claimed.
- [Infineon IDW40G65C5, Rev2.2](https://www.infineon.com/assets/row/public/documents/24/49/infineon-idw40g65c5-ds-en.pdf), p.2: NC/C/A pin assignment and exposed cathode case.
- [Mersen US141](https://www.mersen.com/en/products/ultrasafe-us14-modular-fuse-holders/z331153-us141) and [US14 drawing](https://www.mersen.com/sites/default/files/medias/PIM/files/DS-Semiconductor-Modular-Fuse-Holders-UltraSafe-US14-EN.pdf), p.4; retained local primary PDF SHA256`776c47a6781b1d82d762a827d2ceed9d7e17b15439217b9fb5dc259aa9884562`.
- [Alpha 3080](https://www.alphawire.com/products/wire/hook-up-wire/premium/3080): current conductor, OD, bend, DCR and insulation figures.
- [TE160163-2](https://www.te.com/en/product-160163-2.html): M4,12–10AWG lug and insulation-support window; a drawing/tooling qualification is still required.

Run [replay.sh](replay.sh) from this worktree. It recreates only this catch
packet, then runs real KiCad/ERC/netlist/DRC checks, the calculation tests and CAD
adapter. KiCad macOS DRC may require execution outside the sandbox: the recorded
sandbox failure was `RegisterApplication` abort before board checking. No
fabrication outputs or purchase approval are implied by a successful replay.

# C1 cartridge quote list (sensor-r3)

Each part, its supplier class, and what the request for quote must state. Dimensions and
tolerances are in `DRAWINGS.md`. Part names match `cartridge_r3.py` (prefix `sensor_r3_`).
Quantity basis: 20 cartridges for bench builds, plus 10 % spares on purchased parts.

## Custom parts

| Part | Material | Process | Supplier class | The RFQ must state |
|---|---|---|---|---|
| `disc_Si3N4` | Si3N4 power-module substrate, 0.32 mm | Laser-cut Ø8.0, 0.2 × 45° top chamfer, top lapped | Substrate makers: Toshiba Materials, Kyocera, Rogers curamik (Si3N4 bare substrates), bought through their distributors. Laser cutting and lapping at a ceramic job shop (Precision Ceramics or Ortech class) when the maker won't do it. | Flatness ≤ 1 µm and Ra ≤ 0.1 µm on the lapped face. Thickness 0.32 ± 0.015 after lapping. No metallisation. The flexural strength certificate (≥ 700 MPa class). Edge chips ≤ 0.05. |
| `post_polyimide` | DuPont Vespel SP-1 rod | CNC turned | Vespel stock-shape converters / machinists: DuPont Vespel parts, Boedeker, Par Group, Curbell | The neck wall is 0.25: one setup, finish-turned on a mandrel. Shoulder face to neck top 6.270 ± 0.015. Neck OD Ra ≤ 0.4 µm (the wiper runs on it). Dry and bake after machining. |
| `body_PI` | Vespel SP-1 rod (Ø44 stock) | CNC turned + 3-axis milled (lugs, rib, slots, key) | As the post; large-diameter SP-1 is costly, so also quote a Ø44 SP-21 or Meldin 7001 blank as an alternate, with the published continuous rating (≥ 260 °C) | Rim datum face is datum A. Pad ID, collar, wiper counterbore and gland tolerances are referenced to A. |
| `stop_collar_PI` | Vespel SP-1 | Turned | As the post | OD Ø12.2 −0.02/−0.04 (bond gap). Face flatness 0.01. |
| `wiper_FFKM` | Kalrez 6230 (FDA 21 CFR 177.2600) | Compression-moulded lip seal, custom tool | DuPont Kalrez authorised distributors (custom shapes), Greene Tweed (Chemraz FDA grade as alternate), Precision Polymer Engineering (Perlast FDA grade as alternate) | Lip ID 7.80 ± 0.04, lip thickness 0.30 ± 0.03, flash-free lip. Hardness certificate (75 A assumed in `tilt_follow.py`). FDA compliance letter. |
| `seat_cup_PEEK` | Victrex PEEK 450G (unfilled) | Turned | Any PEEK machinist (Boedeker, Curbell, Professional Plastics) | 90° cone, Ra ≤ 0.8 µm. Cone-apex to pilot face 1.079 ± 0.02. Material certificate stating 450G. |
| `spring_washer_bayonet_PEEK` | PEEK 450G | Turned + milled | As the cup | Thickness 1.00 −0.02/−0.04. Stop-tube top 12.60 ± 0.02 above the seat face. |
| `cable_strain_relief_PEEK` | PEEK 450G | Turned | As the cup | Ø3.4 bore, slip fit on the pigtail bundle (measure the real bundle first) |
| `spring_A286` | A-286 spring wire, AMS 5731 class, aged after coiling | Custom compression spring | Lee Spring custom, Century Spring custom, Smalley (they publish the A-286 538 °C limit) | Two-point load spec, 100 % tested: P1 1.30 ± 0.08 N at 15.60 mm; P2 1.70 ± 0.08 N at 13.40 mm. Ends **open, not closed, not ground**: no end turn may touch its neighbour (a closed turn costs 2.1 W in the eye; `field-screen.json`). d 0.50, D 8.0 mean, L0 ≈ 22.75, ~6.0 active coils. Aged and passivated. Certificate of conformance for the alloy. |
| `fibre_plug_annulus`, `fibre_plug_core` | Alumina-silica fibre paper or felt (Fiberfrax 970 class) | Die-cut rings and discs, packed before the disc bond | Alkegen (Unifrax) distributors, McMaster-Carr class | Binder-free or low-binder grade (burns off at 260 °C otherwise). Density ≤ 0.2 g/cm³. |

## Purchased parts

| Part | Description | Supplier class | Note |
|---|---|---|---|
| `Pt100_chip_IST_P0K1202` | IST P0K1.202.6W.A.007 Pt100 chip, −200…+600 °C | IST AG (Innovative Sensor Technology) or a distributor | Pt film toward the disc (PCB item). |
| `lead_capillary_fused_silica` | Fused silica 4-bore capillary, OD 1.0, bores Ø0.15–0.18 on a 0.30 pitch, cut to 10.28 mm | Multi-bore quartz tubing makers: Friedrich & Dimmock, Vitrocom, Heraeus; or high-purity alumina 4-bore (CoorsTek, Omega TRA class) as the alternate | **Supplier to confirm** the 4-bore OD 1.0 geometry in quartz. Ask for the volume resistivity at 300 °C (≥ 1e7 Ω·cm needed). If quartz isn't offered, 99.7 % alumina 4-bore OD 1.2 fits the Ø1.2 lead bore line-to-line. |
| Manganin leads | Bare manganin Ø0.08 inside the capillary; polyimide-enamelled (MW 16-C) manganin below it | California Fine Wire, Isabellenhütte (alloy) | Four wires, ~20 mm each. |
| `chip_bond` | EPO-TEK 930-4 (BN-filled epoxy). Alternate: Cotronics Duralco 128 | Epoxy Technology, Cotronics | **OPEN:** a written continuous ≥ 260 °C statement from Epoxy Technology. Otherwise the alternate, which has no margin. |
| `foot_potting`, `splice_potting` | Cotronics Duralco 128 | Cotronics | 260 °C maximum. The modelled maximum is 210.7 °C at the foot. |
| Lead sleeve | PTFE thin-wall tube, AWG 24 class, ID ≥ 0.5 | Zeus, Parker Texloc | |
| `static_gasket_FFKM` | O-ring 20 × 1.5, Kalrez 6230 | Kalrez distributors (standard size) | |
| `wave_spring_A286` | Unchanged from R16/R32 | Smalley custom | Same part as R43. |
| `rim_NTC_Semitec_104GT2` | Semitec 104GT-2 | Semitec / ATC Semitec distributors | Unchanged. |
| Pigtail | 6 × M22759/12-26 (PTFE, nickel-plated Cu, 260 °C, 600 V), three twisted pairs, ~180 mm | MIL-wire distributors (Allied, Consolidated Electronic Wire) | **Confirm the OD.** The Ø3.4 strain-relief bore takes six wires up to Ø1.13 each. |
| Inline connector | Molex Micro-Fit 3.0 43020-0600 plug + 43025-0600 receptacle, −40…+105 °C | Molex distributors | At (135, 285, 62), in the air under the carrier. |
| Adhesive for the stop collar | High-temperature epoxy, same choice as the chip bond | as `chip_bond` | 236.8 °C modelled at the collar. |

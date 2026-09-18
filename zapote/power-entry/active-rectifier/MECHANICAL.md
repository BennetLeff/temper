# Fuse assembly — provisional mechanical implementation

U66 is the A70QS50-14F cartridge, with two ETI 006710340 CH14-PCB clips.
The extra clips and F1 consumable are explicit non-footprint BOM rows.

ETI's retained Green Protect catalogue, PDF page 34 / printed page 36,
identifies CH14-PCB and dimensions A=16, B=14, C=15.5, D=5, E=3.5,
F=0.75, G=10.7, H=3.5 mm. This is a clip drawing, **not an approved
PCB land pattern or an ETI endorsement of this Mersen cartridge**.
The official product page describes 63 A / 1000 V DC for its listed CH gPV
application; no equivalent assembly rating is claimed here.

The experimental footprint uses 38 mm between clip centres, two pad centres
10.7 mm apart per clip, 1.2 × 5.4 mm plated slots and 3 × 7 mm lands.
The 38 mm assembly spacing and fabrication allowances are selected assumptions.
Confirm the interpretation of the leg dimensions, slot tolerances, cartridge
engagement/stops and combined thermal rating before manufacture. The fuse
and clips have no 3D model in this checkpoint; their absence in the preview
must not be interpreted as an empty production board or verified fit.

Each clip's two pads share one electrical number. Both physical pads are
connected by PCB copper; native DRC reports zero unconnected pads. No claim
of a built-in jumper or unseen conductive path was needed to achieve that.

Generator: `tools/generate_fuse_footprint.py`, using the official KiCad Library
Tools KicadModTree serializer. All dimensions/assumptions above are retained
in the generator and footprint description. Neither a clean DRC nor Rust's
stackup check resolves the mechanical assumptions.

Sources:
- https://files.eti.si/levels/en-GB/4309_TD.pdf (retained as sources/ETI-Green-Protect.pdf)
- https://www.etigroup.eu/products-and-solutions/fuse-links-d-d0-c/fuse-holders-for-ch-dc-fuse-links/006710340-ch14-pcb
- Mersen exact fuse selection and unresolved clearing application: ../CLOSEOUT.md Q1/Q2.

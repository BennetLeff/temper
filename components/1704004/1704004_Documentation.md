# Phoenix Contact 1704004 — PCB PE branch

**Selected part:** Phoenix Contact KDS 3, one electrical potential with two solder pins. J6 pins 1 and 2 are both PE. Cord PE bonds directly to a chassis/heatsink stud; a separate branch wire from that stud feeds J6. Neither J6, its PCB copper nor R38 is in series with the primary protective-earth bond. R38 makes only the removable functional controller-ground connection.

The unit footprint `temper:Phoenix_KDS3_1704004_1Pos_2Pin_ReviewOnly` maps pad 1 to `(0,0)` and pad 2 to `(0,15.24)` mm. Both are PE. Each has Ø2.6 mm copper and Ø1.4 mm drill for the manufacturer's 1.1 × 0.8 mm solder pin. The product is 5.08 mm wide, 27 mm long and 25 mm installed height; placement must include its wire and housing envelope. This is a transcribed review footprint, pending fit against received hardware.

Keep PE pads, trace, exposed terminal hardware and branch wiring at least 8.0 mm from HOT under the conditional D5 placement basis; final insulation and fault-current qualification remain open. The chassis stud's retention, continuity and fault-current path require enclosure assembly review. No physical continuity or hipot test has run.

Sources: [Phoenix product page](https://www.phoenixcontact.com/en-us/products/printed-circuit-board-terminal-kds-3-1704004), [manufacturer drilling drawing in archived product sheet](https://www.micro-semiconductor.kr/datasheet/fb-1704004.pdf), [unit footprint notes](../../zapote/power-stage-120v/RADIAL-FOOTPRINTS.md), [D5 basis](../../zapote/power-stage-120v/D5-BASIS.md).

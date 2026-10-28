# Lab mill decisions

| ID | Date | Decision | Why |
|---|---|---|---|
| D1 | 2026-10-28 | PrintNC V4, Desktop preset, about 450 × 350 mm | The largest milled Temper part is the 110 × 80 mm coupon. A shorter frame is cheaper and stiffer. The PrintNC Mini is unfinished and uses NEMA17 motors. |
| D2 | 2026-10-28 | Knob shell indexing fixture (B5) instead of a rotary axis | The only 4th-axis job is three key pockets at 120° plus radial holes, and three dowel positions cover it. A rotary costs $240–450; the fixture costs about $20. |
| D3 | 2026-10-28 | grblHAL on an agent-designed board, not LinuxCNC + Mesa | Saves about $150–200 (no Mesa, no PC). grblHAL still supports two Y motors with auto-squaring, an A axis, probing, and network streaming (R6). |
| D4 | 2026-10-28 | Makita RT0701C first, spindle later | Saves about $150. Acceptable for small tools in aluminum and bronze; the spindle is a drop-in upgrade with a machined clamp. |
| D5 | 2026-10-28 | HGR15 on Z, HGR20 on X/Y, two blocks per rail on Y | HGR15 on Z is a PrintNC option and saves a little. One block per rail on Y would save more but loses stiffness against twisting, which aluminum work needs. |
| D6 | 2026-10-28 | Never machine C17200; stand-in springs are C51000 | C17200 is about 2 % beryllium and its dust is a health hazard without extraction. Stand-ins test rate and feel only; fatigue parts come from an etch vendor. |
| D7 | 2026-10-28 | Clone-grade rails and rolled screws, inspected on arrival; never used | Rolled screws (about ±0.05 mm per 300 mm) meet ISO 2768-m. Worn rails cost accuracy that can't be recovered. |
| D8 | 2026-10-28 | Stay rotary-ready at no cost: spare A output on the board, second spindle position 40 mm higher | A 100 mm rotary puts the part's centreline about 80–90 mm above the table, which needs more clearance than R2's 150 mm. |
| D9 | 2026-10-28 | The rotary is bought, not built | A CSF-17 50:1 harmonic gearbox alone is listed at about $360–375 (minimum order 2), more than a complete Chinese rotary unit. |

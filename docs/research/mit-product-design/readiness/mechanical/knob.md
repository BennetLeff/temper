# Knob click: conditional correction and supplier gate

R4 `src/baseline_engine.py::knob` models **C&K PTS645SH43SMTR92 LFS**, not an unspecified generic switch. Its manufacturer alias is Y97HT23B4EAFP. The [current PTS645 datasheet, rev VL 01/29/26, pp3,8–9](https://www.ckswitches.com/media/1471/pts645.pdf), confirms 4.3 ±0.1 mm installed height for the corresponding SMT geometry, 0.15–0.40 mm electrical travel, 1.5–2.5 N operating force and 100,000 listed operations. It does **not** provide a reviewed maximum allowable actuator displacement/overtravel or abuse-force limit. Operating force is not a damage threshold; actuator projection is not permissible travel. The manufacturer's height tolerance also cannot be ignored in an assembled gap budget.

## Two required inequalities

For effective stop travel S, effective rest gap G, maximum electrical trip T, positive actuation margin M and manufacturer safe displacement D:

`S_min - G_max >= T_max + M`

`S_max - G_min <= D_safe_min`

Also prove the corresponding maximum transmitted-force limit, return/open contact, lateral alignment and wear across temperature, load, life and reassembly. Put the user hard-stop load through the carriage/frame, not the switch solder joints. Include switch height and solder stand-off, PCB seating, cartridge fasteners, pusher/washer heights, guide play, sheet deformation and any seal/spring deflection in **effective** S and G; they are not additional unbudgeted errors.

| Configuration | S interval | G interval | Delivered displacement | Margin to 0.40 mm max trip | Minimum supplier-safe displacement needed |
| --- | --- | --- | --- | --- | --- |
| Existing R4 assumptions | 0.50..0.60 | 0.10..0.30 | 0.20..0.50 | -0.20 | 0.50, but actuation already fails |
| Move only nominal stop +0.20 | 0.70..0.80 | 0.10..0.30 | 0.40..0.70 | 0.00 | 0.70 before any positive trip margin |
| Conditional gauged cartridge target | 0.56..0.60 | 0.08..0.12 | 0.44..0.52 | +0.04 | 0.52 plus any unbudgeted dynamic displacement |

These are endpoint calculations, not measured tolerances. The conditional target is a concrete proposal for discussion with the mechanism supplier; **R4 geometry is unchanged**. A ±0.02 mm *assembled* gap cannot follow from a switch with ±0.1 mm height simply by machining a nominal spacer. It would require individually gauging and adjusting the removable cartridge or an appropriately controlled local datum scheme, then including thermal/reassembly drift inside the declared interval. Supplier process evidence must decide whether this is repeatable and economical.

The existing delivered interval is 0.30 mm wide. Therefore satisfying 0.40 mm trip at the lower corner necessarily exposes the upper corner to at least `0.40 + 0.30 = 0.70 mm`, even before positive margin. This proves why moving the stop alone is not a closure. The conditional narrower interval is 0.08 mm wide and its nominal 0.48 mm yields 0.44..0.52 mm. Neither solution can be released while safe stroke/force is unknown.

## Precise next decision and inspection

Request a written application limit for **this exact part**, temperature and axial actuation arrangement: maximum permissible total stroke, continuous/repeated overtravel force, side-load/alignment allowance, safe preload, bounce/release conditions and environmental suitability. Supply the conditional 0.44..0.52 mm interval and mechanism loading; ask the manufacturer to accept or reject it. If it cannot be supported, select a switch with a documented usable trip-to-safe-stroke window and redo the stack. A compliant plunger may limit force, but needs its own calibrated spring curve and supplier limits; it is not permission to bottom the switch.

Before integrated powered testing, assemble an unpowered cartridge coupon with the real switch/PCB, guide, pusher, return spring and stop. Use a force/displacement fixture and electrical continuity logging referenced to the local cartridge seat. Record released height, closure/release displacement, stop position, force curve, hysteresis and rest-open state. Vary actual allowed component corners and reassembly, then hot/cold conditions established by the material and product requirements. Record measurement uncertainty and part/lot identity. Pass only against both supplier-backed inequalities and the approved product force/feel target. A successful nominal click is insufficient.

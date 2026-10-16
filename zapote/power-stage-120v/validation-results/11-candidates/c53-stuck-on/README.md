# Stuck-on stage (UL 858 25.3.1, checklist 14 / OPEN-ITEMS S15): second independent means, and the R130 swap

Read-only study, 2026-10-16. PS = `zapote/power-stage-120v`; board of record s51; netlist `PS/frozen/default.net` + `default.csv`;
placements `PS/validation-results/08-manufacturing-package/native-21/fab/positions-kicad.csv`.
JLC stock/price pulls: `scripts/jlc.py` (public JLC search endpoint), raw JSON in `raw/`. Stock is a 2026-10-16 snapshot.
Tags: [G] datasheet read, [C] computed, [E] estimate/needs bench, [U] not verified.

## 0. What exists today (so the options are judged against the right baseline)

* **PERMIT is a static level.** U37 (controller) = interlock latch AND RUN_EN (GPIO14, 4.7 k pull-down) -> J4.9 -> R6/R14 100 ohm -> U22.1/U23.1
  (`permit` net, `default.net`). DIS = NAND(PERMIT_gate, BIAS_GOOD) (DECISIONS 27). A firmware that sits at RUN_EN = 1 keeps PERMIT high forever.
* **The "heartbeat" is a bias-rail heartbeat, not a firmware heartbeat.** U45 RC oscillator (gated by the LS monitors' good node) -> U32 isolator -> U46 -> pump -> U40 -> BIAS_GOOD.
  S50 (DECISIONS 71) made U46.A = PERMIT through R135 (100 k) so BIAS_GOOD is low whenever PERMIT is low. That proves the pump chain on every idle tick;
  it does not watch firmware liveness. A stuck-high PERMIT with healthy rails passes it.
* **A firmware-liveness hardware path already exists on the controller:** TPS3823-33 (WDI = GPIO18, `watchdog_hardware_feed()` called at the top of
  `state_machine_update`, `firmware/main/state_machine.c:245`; timeout 0.9-2.5 s, 1.6 s typ [G, interlock MODEL.md]). Its output is the
  watchdog-good term of the interlock NAND -> latch -> PERMIT low (zapote/interlock/MODEL.md; CTRL README interlock table). So "MCU locked up with MCPWM still running" is
  already covered firmware-independently. What it cannot see: firmware that is running and wrong (the feed is at the loop top, before any state logic, so a wedged state still feeds it).
* **Pin budget is zero.** `firmware/test/test_controller_pins.c` asserts every module GPIO is used ("there is no spare pin"); GPIO35 is the one proposed re-allocation (BIAS_GOOD read-back).
  TCA9555 has P06 (reserved input for a 2nd MAX31865 CS) free-ish, but is slow (I2C poll) and P15 is the only output.
  **J4 is a full 16-pos Micro-Fit** (`default.net`: 1 BIAS_GOOD, 2/4/15 GND, 3 v3v3, 5-8 PWM, 9 PERMIT, 10 BUS_FAULT, 11/12 VBUS, 13 CT_ZC, 14 CT_MON, 16 LINE_ZC).
  Any new controller-driven signal needs a new connector pin, so it is a two-board change.
* **TCO:** J3 (2-pin VH) in series with PS2's AC feed (`l_filt` -> J3.1 .. J3.2 `tco_l` -> PS2.1). Opening it kills PS2 -> V24_RAW -> gate-drive bias, HOT5, OCP_OK. The bridge BR1 stays on the line (`l_filt`/`n_filt` -> BR1.2/.3).
* **Inlet topology** (`default.net`): J1 -> F1 (`l_f`) -> L1 -> `l_filt`/`n_filt` (C2, C3/C4 Y caps, BR1.2/.3, J3, F2, PS2, LINE_ZC resistors). No NTC/inrush limiter; bus film 18.4 uF (C5/C6, DECISIONS 70 area).
  Placements (mm, board frame): J1 (274.6,-9.2), F1 (246.4,-7.3), L1 (232,-31), C1 (238,-20), J3 (217.7,-11.8), PS2 (163.7,-3.6), BR1 (81.7,-4.6). The line-current path from L1 to BR1 is ~150 mm of 2 oz copper.
  L1 is already scheduled to change (OPEN-ITEMS B15: B82726S2203A020 -> B82726S2243A020, "the only prototype blocker"), so the inlet area is going to be touched regardless.

## 1. Option (a): series mains cut (relay / contactor)

### 1.1 Parts (15 A rms at 120 VAC, UL, board mount), JLC stock for 20 boards

| Part | LCSC | Stock | Price @10 / @30-50 | Body | Rating [G unless noted] | Notes |
|---|---|---|---|---|---|---|
| Omron G2RL-1A-E DC24 | C231362 | 2,256 | $1.35 / $1.20 (@40) | 28.8 x 12.5 x 15.7 | UL file 41643: 16 A 250 VAC **General Use at 40 C**, 100k ops; resistive 16 A 250 VAC 30k ops; 8 mm / 8 mm clearance/creepage coil-contact, 5 kVAC; "micro disconnection" (1 pole); contact res. 100 mOhm max; coil 400 mW, 1.44 kOhm | best fit: stock, size, UL 41643 read from the Omron datasheet |
| Omron G2RL-1A-E DC12 | C1564126 | 3,085 | $1.45 / $1.24 | same | same | 12 V coil, 33 mA |
| Hongfa HF115F-I/012-1HS3A | C165909 | 1 | $2.36 / $2.07 | 29 x 12.7 | 16 A 250 VAC [U, listing only] | no stock |
| Hongfa HF152F-T/012-1HST | C2976802 | 111 | $1.75 / $1.53 | smaller | listing: 20 A, 7 A @ 400 VAC [U] | 12 V only; low stock |
| TE T9AS1D12-24 | C1524521 | 1,025 | $1.96 / $1.75 | 32.5 x 27.4 | listing: 25 A 277 VAC, 30 A 277 VAC variants; UL 508 / 873 spacing per Farnell snippet [U: UL file and 120 VAC rating not read] | 2x margin on current/arc; 85 C rated; bigger |
| TE T9AS1D12-12 | C1524541 | 901 | $2.18 / $1.96 | same | 30 A 277 VAC, 1 W coil, 144 ohm | |

For 20 boards: 1-pole = 20 relays, 2-pole (two series relays) = 40 relays. Stock is not a constraint for G2RL or T9A. Cost: 2 x G2RL = ~$2.7-2.9/board at JLC pricing; 1 x T9A = ~$1.75-2.2. Add a new Extended-part fee per distinct part (~$3 each, [E]).
**No 2-pole 15 A relay at JLC.** The 2-pole G2RL-2A is 8 A 277 VAC [G]; HF115F 2Z are 8 A. Two-pole means two 1-pole relays in series (line and neutral).

### 1.2 Where it goes and what drives the coil

* **Placement:** between `l_filt` and BR1.2 (and `n_filt` and BR1.3 for 2-pole). It must be *after* the PS2/PS3/J3/F2/LINE_ZC taps. If it sat at the inlet (between J1 and F1), PS2 would die when it opens and the coil would lose its supply and could never re-close. Putting it downstream keeps PS2, PS3 and the monitors alive when the relay opens. It also means LINE_ZC does not see relay state; VBUS_ADC (J4.11/12) does (bus rises to ~170 V on close, bleeds when open), which gives free closed/open feedback. [C]
* **Coil source: PS2 (V24_RAW), not HOT5.** G2RL-1A-E DC24: 16.7 mA, 400 mW [G]. HOT5 is a 5 V logic rail (U3/U38/U39 LDO area) and 80 mA at 5 V on it is the wrong rail. With the coil on V24_RAW the **TCO also opens the relay** (PS2 dead -> coil dead), which turns the TCO into a real series mains cut instead of a gate-drive cut. That is the single biggest benefit of the HOT-side choice, and it directly answers the "bus stays live" caveat in checklist 14.
* **The trigger needs a SELV->HOT channel that does not exist.** The relay command (PERMIT / interlock OK, SELV) has to cross the Nomex SELV/HOT barrier to a HOT-side low-side NFET. Today the only SELV->HOT paths are the PWM gate-driver inputs. Add one opto (VOL628A family, 5 kV, already used as U36; **JLC stock for VOL628A is 0**, so Mouser/DigiKey or an ISO6721/CA-IS37xx channel [U]) plus a N-FET, flyback diode, 2-3 resistors. A SELV-side coil instead would make the relay itself the reinforced barrier (G2RL 8 mm coil-contact is the same figure as D5 8.0 mm, so footprint pad spacing would need a copper audit vs 8.047/8.507 mm) but then the TCO does not open it. HOT-side coil is the recommendation.
* **What the hardware path should be** so that it is not just PERMIT again: RELAY_EN = (opto output of "interlock OK", i.e. PERMIT low > ~100 ms drops it) AND HOT-side monitor good (the `monitor_ls-good` node) AND PS2 alive (implicit: V24_RAW). Opening delayed >= ~10 ms after PERMIT falls, so DIS has already removed bus current (DIS <= 13.6 us, bias stop <= 90-123 us, DECISIONS 71) and the contacts break nearly zero current in every case except the stuck one. Re-close only through firmware (RUN_EN rise), with a >= 20 ms settle before PWM, and with the PS2 ramp considered.

### 1.3 Opens under load? Arcing

* The stuck-on case opens at up to 15 A rms, peak ~21 A, near-resistive (18.4 uF film bus; L1 and the X/Y caps stay upstream of the relay). G2RL: 16 A 250 VAC general use, 100k ops (UL) and 30k ops resistive 16 A 250 VAC [G]. At 120 VAC the arc voltage/energy is roughly half of the rated 250 V case. **Within rating on paper, but the UL general-use rating is at 40 C ambient**; the box interior will be warmer, and 15 A continuous is 94 % of a 16 A relay [C]. T9A (30 A) has 2x headroom.
* **Larger risk is closing, not opening.** There is no inrush limiter. Closing at a random phase into BR1 + 18.4 uF: peak ~ 170 V / (cord + L1 DCR + BR + film ESR). With ~0.3-0.5 ohm total that is ~350-570 A for tens of us [E], energy 1/2 C V^2 = 0.27 J, plus contact bounce. G2RL's datasheet gives no inrush rating [G, read the whole table], so welding on close is the top technical unknown. Fixes: close at a line zero crossing (firmware has LINE_ZC; the relay needs ~15 ms operate time, so close with a predicted crossing), or a series NTC bypassed by the relay (area), or T9A (rated for inrush loads per TE marketing text, [U]). The plug-in event already does this inrush through F1/BR1 (DECISIONS 70: inrush I2t <= 1.8 % of F1); the relay contacts are far weaker than F1/BR1, so this needs a bench count.
* **Contact heating:** datasheet "100 mOhm max" at 5 VDC 1 A is an initial max, not a typical. 15 A rms through 4 / 30 / 100 mOhm = 0.9 / 6.8 / 22.5 W [C]. Typical 16 A relays measure at the low end, but this is [E] and would add to the inlet budget (D-27 inlet module is already 8 W/15 A screening). T9A listing says 75 mOhm max.
* **Trip into a shoot-through** (hundreds of A): DIS ends the drive in <= 90 us and F1/BR1 clear the rest; the delayed relay opens afterwards. If DIS itself is the failed element the contacts break whatever the stage draws; welded contacts then defeat the cut: that is why a second series pole (line + neutral) is not redundancy for welding but for polarity; true redundancy would be a second relay in series on the same conductor ([E] pick if the lab asks).

### 1.4 Touch current, EMI, area, cost, layout

* **Touch current:** no change. C3/C4 (2 x 2.2 nF Y1) stay on `l_filt`/`n_filt` upstream of the relay, so leakage is as today (~0.1 mA per cap at 120 V/60 Hz, C). A HOT coil adds no SELV coupling. A SELV coil would add pF-level contact-coil capacitance across the barrier [E].
* **EMI:** none continuous. An opening arc is a single event. The coil driver adds a flyback diode and 16.7 mA of PS2 load (PS2 MPM-20-24 is 20 W).
* **Area:** 2 x G2RL = 2 x 28.8 x 12.5 = 720 mm2 body, ~1,000 mm2 with 8 mm HOT keepouts [C]; T9A 890 mm2 body. Plus ~100 mm2 for opto/FET/diode. Plus rerouting 15 A on 2 oz copper out of the l_filt/n_filt to BR1 run.
* **BOM cost:** ~$3-5 per board at 500 incl. opto/FET [E]. Prototype: ~$60-120 for 20 boards in parts + Extended fees.
* **Clearances:** coil on HOT side crosses no barrier: relay sits in the HOT core. The 8.0 mm HOT-SELV floor (D5) only constrains placement vs the SELV tongue (x 0-91, y 140-190), far from any plausible spot. Keep 8 mm from PE copper per the existing D5 rules.
* **Layout stage?** **Yes** (power board): new nets (`l_filt` split into `l_filt`/`l_br`), new opto channel across the barrier, 15 A copper re-cut, new J-less hardware only; spine lock, audit.rs, D5, CPL audit all re-run. Size: a normal stage. **Not BOM-only.**

## 2. Option (b): hardware heartbeat watchdog on PERMIT

* **Does the existing PERMIT gate already do this?** No (section 0). PERMIT is static; S50 gated the *bias heartbeat* by PERMIT, not PERMIT by a heartbeat.
* **What the existing TPS3823 already gives:** MCU lockup, loop not called, or reset: PERMIT drops within 0.9-2.5 s. So adding a second liveness watchdog on PERMIT adds almost nothing for "firmware hang". The one thing it would add is a *different task* (or ISR-independent) toggle, which is a firmware change inside the same MCU.
* **As an add-on next to U46** (U46 at (94.5,-132); DIS NAND U22/U23 at (77.1,-60.7)/(30.1,-60.7)): the domain is SELV v3v3. Candidates at JLC: SN74LVC1G123 retriggerable monostable (C123302 13,234 stock, $0.54 @10, VSSOP-8) + RC; STWD100 watchdog (C46043 19,218, $0.30 @10, SOT-23-5); TPS3430WDRCR (C2870545 1,021, $1.40 @10, VSON-10); TPS3431SDRBR (C702145) stock 0. Output gates `permit_gate` for both legs (a series AND in front of U22.1/U23.1 or into the U22.2 input as another term) and R6/R14/R7/R15 (100 ohm / 100 k) change role. ~40 mm2 + ~$0.5-1.6.
* **What it needs from outside the board:** a toggling input. **No free GPIO, no free J4 pin.** Options: (i) re-purpose a J4 ground pin (no; return paths), (ii) a bigger connector (controller board + harness + power board change), (iii) encode on PERMIT/RUN_EN itself: RUN_EN would have to toggle at kHz from firmware so that U37 -> PERMIT carries an AC heartbeat, and the power board must then convert PERMIT-AC to a level (a new AC-coupled detector, like the U46 pump) and AND it with a static enable. That keeps J4 as is but needs a controller-board change (RUN_EN is an ESP32 GPIO into U37; toggling it is allowed in the pin map, GPIO14 is not a strap) and **breaks the S50/C39 sequencing**: PERMIT low is a "fresh start" (check 2 runs at each RUN_EN rise). Rate: firmware toggles each control tick (>= 10 Hz) and watchdog window ~ 100-300 ms [E].
* **Firmware change:** toggle in `state_machine_update` or a separate task; re-key BIAS_GOOD checks (they are keyed to PERMIT_RB, c50 section 5). Medium risk, nothing tested.
* **Layout stage?** **Yes, on both boards** (power board for the detector and a modified permit_gate; controller board or connector for the signal). Not BOM-only.

## 3. Option (c): second TCO

BOM + enclosure + harness only: a second TCO in the PS2 feed in series with the first (J3 pins, or a second VH loop) or one on the coil/glass in series with the sink TCO. Parts ~$1-3 each plus wiring; no board layout (J3 is a 3-pos VH with pin 2 omitted, 5.22 mm gap, 250 V 10 A; a series TCO goes into the harness, not the board). It does not add a different *kind* of independence (still thermal, still gate-drive-only, bus still live), so it answers a "two TCOs" objection but not "series mains cut".

## 4. What each option covers (plainly)

| Fault | Today | (a) relay (HOT coil on V24_RAW) | (b) PERMIT heartbeat | (c) 2nd TCO |
|---|---|---|---|---|
| Firmware hang / MCU lockup (PWM peripheral keeps running) | TPS3823 -> interlock -> PERMIT low (0.9-2.5 s) | Yes, if relay follows PERMIT/interlock; same time | Redundant with TPS3823; adds only a second timer | no (thermal only) |
| Firmware running but commanding on (logic bug) | nothing; TCO after a temperature rise | Only the TCO leg; no | No (the heartbeat is fed by the same loop) | thermal only |
| Stuck gate driver (2EDR8259X out stuck high, or DIS ignored), U22/U23 Y stuck low | TCO (thermal, minutes) | **Yes** (power path opened, independent of the stage) | **No** (it acts through DIS) | thermal only |
| Shorted FET | shoot-through: F1 / BR1 sacrificial; a single shorted FET with the series tank cap keeps driving | **Yes** (opens at <= 15 A; contacts could weld at high current) | **No** | thermal only |
| PERMIT stuck high (U37 / short) | PERMIT_RB firmware check + bias gate | Yes if the relay command is taken from the interlock side ahead of U37 | Adds nothing | no |
| TCO opens | gate drive only; bus live | **bus dead** (coil on PS2) | n/a | n/a |

So: (a) is the only option that covers "solid-state control stuck" in the 25.3.1 sense (a stage that will not stop). (b) covers a narrower set that TPS3823 already covers and cannot cover stuck driver or shorted FET. (c) is the same single point as today in a different place.

## 5. Recommendation

1. **Do not populate a relay on the first 10-20 units, and do not build (b).** (b) is largely redundant with the TPS3823, needs a pin that does not exist, and cannot see the faults the lab will actually ask about. (a) has two unmeasured risks (close-in welding, contact heating at 15 A) that the lab answer should not be allowed to hide.
2. **Provision (a) as a footprint/DNP option in the same layout stage that already has to touch the inlet** (L1 B15 swap): two G2RL-1A-E (or one T9AS1D12) footprints in the `l_filt`->BR1.2 / `n_filt`->BR1.3 run, bridged on the prototype by a hand-fitted 14 AWG link across the contact pads (so DNP means "wire", not "open"); a HOT-side NFET + flyback + opto footprints DNP; V24_RAW coil tap. Cost on a no-relay unit: ~$0; area ~1,000 mm2. If the lab says "no", the relay is a solder job rather than an inlet re-layout. **This is a layout stage (not BOM-only);** it should ride with the L1 change, not as a separate s52.
3. **For the bench now (no board change):** run units behind an external series mains cut (a contactor/relay box with a bench e-stop, TCO-fed if convenient) and do the stuck-on injection: bypass DIS with a jumper at U22/U23 output, run to ceiling, see when the TCO opens (also settles S15 item 2: TCO trip temperature vs glass/sink).
4. (c): do it in the BOM/harness if the lab wants "two", it is cheap; it does not replace (a).

## 6. What the bench learns from each

* **(a):** measured contact dissipation/temperature at 15 A (the 4 vs 100 mOhm question); inrush weld count on close (n = 100 closes at random phase vs zero-cross); open-under-load at 12-15 A (arc duration, contact condition, conducted burst); relay open time vs stuck-driver injection; whether the TCO now opens the bus.
* **(b):** only toggle margin/nuisance rate; no new hazard data.
* **(c):** the thermal stuck-on case (time-to-trip at the ceiling), which S15 needs anyway.

## 7. R130 (checklist 10): Vishay AC05-CS swap

* Current part: AC05000001507JAC00 = 0.15 ohm, 5 W, D7.5 x L18 mm, axial mounted vertical (`R_Axial_Vishay_AC05_D7.5mm_P5.08mm_Vertical`); JLC **C1382388**, stock **225**, $0.92 @1, $0.74 @10, $0.66 @30 (enough for 20 boards).
* **AC05-CS (UL 1412, file E362452) is 1 ohm to 100 ohm only, +/-5 %, 10 mm dia x 17 mm** [G, Vishay AC-CS sheet doc 28909/MS7440]. **No 0.15 ohm AC05-CS exists.** At JLC the CS part number family is `AC050000B...J6BCS` / `AC050000A1009J6BCS` (D10): stocked values are 10 ohm (C1365141, 529), 22 (C499587, 59), 39 (1), 47 (10), 56 (20), 100 (6); no 1 ohm CS found at JLC; Mouser/DigiKey availability of `AC050000B1008J6BCS` not confirmed [U].
* Sub-ohm fusible alternatives: Welwyn ULW starts at 1 ohm, WHS-UL at 10 ohm, Yageo FKN/ TT FAW 1 ohm up; the closest 0.15 ohm "safety wirewound" is Ohmite TWW5JR15E (DigiKey; flame-proof radial; UL not confirmed) [U]; JLC has only a metal-oxide MOF5WS 0.15 ohm (C121909, 1,002 stock, $0.15) which is not a safety-fusible part.
* **Verdict: not a drop-in and not BOM-only.** (i) the value does not exist in the UL fusible family; (ii) body is D10 vs D7.5 (new footprint, R130 is already a 24 mm envelope); (iii) the closest value, 1 ohm, changes the electrical case: fault bound 170 V peak /1 ohm = ~170 A vs the current 980 A bound (good for F2 selectivity) [C], but it dissipates ~2.0 W at the 1.41 A rms that gives 0.30 W at 0.15 ohm [C], drops ~1.4 V in the PS3 feed, and the F2 3.15 A T selectivity, PS3 start-up, and the R130 PARTIAL ledger row would all need re-running. That is a small layout stage (footprint) plus a re-run of c28-f2, not BOM-only. If the lab accepts a non-recognised limiter whose fusing behaviour is documented, leave R130 and answer on paper; if it insists on UL-recognised, it is the 1 ohm AC05-CS plus a footprint edit, to be batched with the inlet change.

## Not verified

T9A UL file/120 VAC rating; HF152F and HF115F ratings (distributor text only); relay contact resistance typicals; opto/isolator stock; the exact copper free area near BR1.2 on s51 (no geometry pulled); TPS3431 pin details; VBUS as a relay-state indicator (derived from the netlist, not simulated).

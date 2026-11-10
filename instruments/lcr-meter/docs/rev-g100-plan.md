# Rev G100 plan: Rev G on 100 × 100 mm

Rev G100 is Rev G (protected jacks, [rev-g-plan.md](rev-g-plan.md)) laid out again on Rev F's 100 × 100 mm outline. The circuit is the same. The only netlist change is that J5 is gone: it was a 2-pin GND / VTREF header for the debugger, and TP8 / TP9 now provide those two pins.

The feasibility study (`../validation/rev-g/shrink-100-feasibility.json`) found that the protection band could not be squeezed. The 10 mm therefore comes out of the digital and power south of U1.

**Status (2026-11-09): laid out, hand-routed, datasheet-audited, the audit's fixes applied, every board gate clean.**
- **Second independent review** (frozen export `build/rev-g100-review2/`, `../validation/rev-g100/independent-review-2-2026-11-09.md`): **orderable, no blockers.** Its two MAJOR findings are dispositioned at the end of that file: M2 fixed (In2 corner widened to 1.6 mm), M1 accepted. An independent re-check of the M2 fix (`../validation/rev-g100/independent-recheck-2026-11-09.md`) found it clean: only the corner changed, 5 °C rise at 1.17 A, DRC 0 on the board's rules and on JLC's, Gerbers byte-identical to a fresh export. For the next spin: widen the 0.4 mm B.Cu neck at (54.46, 116.4–117.75) and U16.6's 0.5 mm F.Cu exit to 0.6 mm (1.23 / 1.45 A by IPC-2221 external, both above 1.17 A).
- The datasheet audit and the first review are in `../validation/datasheet-audit-rev-g100/FINDINGS.md`; §6 lists what they changed.

These steps remain before an order:
- JLC's placement preview (the CPL rotations, review m1);
- Rev G's own open items, which G100 inherits unchanged (Rev F bring-up on the shared analog nodes; [bring-up-rev-g.md](bring-up-rev-g.md)).

Branch `study/lcr-rev-g100`. Rev G (100 × 110) stays intact on `study/lcr-rev-g`, and Rev F stays orderable on `study/lcr-in-box`. On this branch, `cad/` is G100, while `manufacturing/` and `previews/` stay Rev F, as on the Rev G branch. The evidence is in `../validation/rev-g100/`, and every row below is rerun by `sh validation/rev-g100/gates.sh`.

## 1. What changed against Rev G

`cad/tools/rev_g100.py` runs `rev_g.py` up to its craft pass (so it uses Rev G's parts, routes and analog core as they are), then makes four changes.

**1. Two rigid moves.** Each body's parts, tracks and vias move together, and tracks crossing the body outline stretch or are dropped:
- **west, −24 mm:** the power entry (U16, R110, C113, R121, C16) and the 3V3 LDO (U3, C17) go north, into the strip between the I2S test pads and J1;
- **east, −10 mm:** the switcher block (U13, L1 / L2, D2 / D3, its capacitors and dividers, U17, C116–C118) goes north.

**2. Re-placed parts (`PLACE_G100`):**
- U2 flash and its capacitors C11 / C8 go west of U1's south side;
- SW1 / SW2 take J5's old spot east of U1;
- the debug LEDs move: FLT (D20 / R118) north of J4, HB (D19 / R117) in the pocket west of U1;
- R95 moves north of the switcher's new top row;
- R1, R7 / R8 / R9 / R13, C14 and C18 move.

**3. The board:**
- outline x 50–150, y 45–145;
- Rev F's holes (54, 54), (146, 54), (54, 141), (146, 141);
- fiducials at (53, 69), (147, 48) and (147, 136);
- zones clipped at y 144.5.

**4. Hand routes.** `cad/tools/rev_g100_routes.py` places copper by coordinates only. There is no autorouter and no path search. The script:
- clears and prunes the south copper;
- re-lays the west-edge jack senses around the moved power entry;
- fans out the QSPI flash;
- takes RUN / MON12 / MON_N12 round the flash on In2 (a west corridor under U2's pads, then along the south edge);
- runs the 5V trunk and the VBUS feed;
- ties the 3V3 LDO to the codec run;
- connects the debug LEDs;
- re-lays the switcher's RAW_P / RAW_N / −12V / 3V3 hookups.

**Analog copper:** all 403 analog-net items are identical to Rev G's (`copper-delta-vs-g.json`, no transform). Every GND-fill change lies at y ≥ 115.8, at least 11.6 mm from any analog copper and 16.7 mm from the extracted nets. Rev G's parasitic extraction (`run_reve.sh revg`) and its stability on the extracted board (`revgxcng100`) therefore carry over unchanged, as do the drive budget and the protection screens. None of them were rerun.

## 2. Gates (2026-11-09)

| Check | Result | Evidence (`../validation/rev-g100/`) |
|---|---|---|
| Pre-DRC (`rev_g100.py --check`) | 0 violations, 0 unconnected (772 pads, 1941 segments, 435 vias) | `../build/rev-g100-predrc.json` |
| KiCad ERC / DRC / unconnected / parity | 0 / 0 / 0 / 0 (silk warnings included) | `erc.json`, `drc.json` |
| JLC fab pass (`jlcpcb-4layer-1oz`) | PASS | `fab-check.json` |
| DFM via audit | 33 exposed-pad thermal vias only | `via-in-pad-process.json` |
| Gerber netlist (Gerbers + drill + IPC-D-356) | 0 shorts, 0 opens; the self-test catches a planted short, open and floating island | `gerber-netlist-check.json` |
| Independent audit (`independent_check.py g100`) | 744 pins (Rev G 744, less J5, plus D29), 12 relief pins, 0 findings; the Rev G jack → switch → series-R topology holds | `../independent-verification-rev-g100.json` |
| Pinout ledger (`ledger-rev-g100.json`: Rev G's, without J5, with D29) | 25 PASS, 6 NOTE, 0 FINDING, nothing uncovered | `../pinout-ledger/ledger-rev-g100.check.json` |
| Firmware pins | 81 pass, 0 findings | `firmware-pins-check.json` |
| Supply copper (IPC-2152, 10 °C) | 0 FAIL | `current_check.json` |
| Passive ratings | 0 findings (R121's hot-plug note as on Rev F / G) | `passive-ratings-check.json` |
| USB FS, paste | 0 findings each; D+ / D− 36.98 / 43.38 mm, skew 48.2 ps (as Rev G) | `usb-fs-check.json`, `paste-check.json` |
| Edge copper | front 0.40 (D4, as Rev F), back 0.40 (RUN on In2), left / right 0.50 mm | `edge-clearance.json` |
| Regulators | 51 PASS / 2 FLAG (the same two information flags as Rev F). The 5V trunk is 110.6 mΩ (Rev F 49.8 mΩ); U13 VIN min is 4.266 V (Rev F 4.294) | `regulator-check.json` |
| Drive budget (`drive_budget.py`, rail from the routed copper) | 17 / 17 PASS. Relay coil in the four-coil RESET at VBUS 4.40 V: 4.149 V, against 3.75 V at 20 °C and 4.125 V at a 45 °C relay. TLP172AM LED 5.40 mA minimum, 12.2 mA maximum. Guard constants: the open-jack float (1.65 V) lies inside the close window | `drive-budget.json` |
| USB hot-plug (`hotplug_spice.py`, ngspice 45.2), with 30 nH of board copper added to the cable | worst as-built corner 6.251 V, 0 of 96 over the 6.5 V recommended maximum. The 0 nH baseline reproduces Rev F's 6.24 V on this ngspice. Not rerun after the audit: the model already puts C15 at U16 IN behind the board inductance, where C15 now is, and the J1 → U16 feed is unchanged | `hotplug-spice.json`, `hotplug-spice-l0.json` |
| Switcher near-field pickup vs Rev E (relative, not a bound) | see §3 | `switcher-pickup.json` |
| Board envelope | 100.05 × 100.05 mm; BNCs 13.75 mm tall, 18.48 mm past the front; J1 at y 127.5–136.5 | `board-envelope.json` |
| Cost, 5 boards (Rev G's 2026-11-09 price snapshot, plus the four audit codes added that day) | **$400.38 economic** (before the audit $387.22; the audit's three new extended parts add $9.21 in feeder fees). Rev G $411.22, Rev F $358.17. The board is back under JLC's 100 × 100 special offer ($25.70 vs $49.70) | `order-estimate-5.json`, `fab-quote.json` |

**Hot-plug allowance:** 30 nH covers the J1 → U16 copper. That is about 25 mm of track at 1.2 nH/mm, above any microstrip over a plane at this width.

**Start-up surge (`startup_surge.py`):** the model has a single 5 V node and no trunk resistance, so it was not rerun. Its worst as-built node is 3.86 V. That node sits at U16 / U3, which are upstream of the trunk, so the 3V3 LDO sees it unchanged. U13 is downstream of the trunk, with C117 beside it. Even if the whole 2.2 A switch limit flowed through the 110.5 mΩ trunk, U13 would see at least 3.62 V, against a UVLO of 2.7 V maximum.

## 3. Costs of the shrink

- **Switcher pickup (`switcher-pickup.json`).** The switcher block moved 10 mm toward the analog core, so D3 to U7 is now 54.6 mm (Rev F 63.6). Relative near-field pickup is higher than Rev F (`switcher_pickup-rev-f.json`) by:
  - +4.0 dB into the TIA C104 loop and +4.4 dB into the RF100K loop;
  - +1.8 / +1.9 dB into the codec inputs;
  - +3.1 to +4.1 dB into the EXCITE and HPOT inputs.

  The LPOT input is 8 dB lower, because of Rev G's band layout. The absolute level is unknown, as it was on Rev F. A pickup matters only if a switcher harmonic collides with a tone. That chance depends on the frequency plan alone and is unchanged (0.01–0.18 % per tone). The source-off check sees a collided line and fails the capture rather than biasing it.
- **5V trunk:**
  - 0.6 mm B.Cu down the west edge and along the south, then 1.0 mm east of x 92;
  - an In2 riser at x 99, 0.9 mm wide;
  - 110.5 mΩ in total, 51 mV at the 0.46 A estimate (§2).
- **Silk:** 205 references are placed by search and 4 by hand. 43 are on F.Fab only (Rev G 31), among them U13, U16 and SW2; all are on the assembly drawing.
- **Debug LEDs split:** FLT is north of J4, HB west of U1.
- **Buttons:** RESET is 0.62 mm from the back edge. Both buttons stay reachable from above with the lid off.

## 4. Enclosure

The board is Rev F's size again, so the box returns to Rev F's **110 × 110 × 36 mm** with Rev F's **92 × 87 mm** hole pattern (y 54 / 141).
- The front face (BNC holes, D4 lens) is unchanged.
- The one change from Rev F's box is the USB-C cut-out. It stays at Rev G's **87 mm** behind the front edge (J1 at y 132; Rev F 77 mm), on the same left wall.
- H3 / H4 keep the 1.8 mm to the B.Cu GND pour that Rev F and Rev G have, so insulating standoffs are still needed. This is a carry-over, not a G100 change.

## 5. Decisions

| Date | Decision | Basis |
|---|---|---|
| 2026-11-09 | **Try 100 × 100 (owner: "try")** on a new branch; Rev G stays on its own | The feasibility study found room in the digital and power south, not in the band |
| 2026-11-09 | **Rigid moves for the power entry (−24 mm) and switcher (−10 mm); the analog core untouched** | It keeps every analog route and the extraction. `copper-delta-vs-g.json`: 403 / 403 identical |
| 2026-11-09 | **J5 dropped; the debugger takes VTREF / GND from TP8 / TP9** | J5 was a DNP 2-pin header carrying only those two nets; its spot takes the buttons |
| 2026-11-09 | **RUN / MON12 / MON_N12 round the flash on In2, west under U2 and then along the south edge** | The QSPI fan-out closes U1's south side on all three signal layers. Their order is fixed by where they leave U1 |
| 2026-11-09 | **VBUS feed: J1's south pins → C15's 0.4 mm exit → via → 0.5 mm B.Cu to U16**, not In2 | `current_check.py`: 1.17 A needs 0.875 mm on In2 (0.5 oz) and 0.38 mm outer. A first In2 route failed 9 rows; this one passes them all |
| 2026-11-09 | **5V riser on In2 at x 99 widened to 0.9 mm** | Same check (inner layer) |
| 2026-11-09 | **RUN 0.15 mm wide along the back edge (In2 y 144.525)** | It holds the fab note's ≥ 0.4 mm copper to edge with the 0.15 mm spacing to MON12. RUN is a slow, low-current reset line |
| 2026-11-09 | **Rail labels in two staggered rows of 1.0 mm text** | JLC's 1.0 mm minimum (the fab pass rejected 0.8 mm) |
| 2026-11-09 | **TP7 (RAW−) moved beside R96's RAW_N end** | A 1.0 mm label did not fit between C92, L2 and the edge |
| 2026-11-09 | **Apply the datasheet audit's must-fix and cheap fixes (§6)**; firmware first, since without the guard fix the meter cannot measure | `FINDINGS.md`; every gate rerun |
| 2026-11-09 | **R101 0.33 Ω, not 0 Ω** | 4.149 V at the coils (≥ 4.125 V at a 45 °C relay), and the RC filter on VRLY stays (corner about 37 kHz with C112 at bias, 30 dB at 1.25 MHz) |
| 2026-11-09 | **MD-6 (RUN cap at U1), MD-1 / MD-2 (RP2040 decoupling) and SL-2…4 (switcher GND vias) not done** | No spot reaches a GND via within reach; each is recorded with a bring-up check in `FINDINGS.md` |
| 2026-11-09 | **Second review: In2 corner 0.9 → 1.6 mm (M2); J1 A4/B9's 0.2 mm exit accepted (M1)** | M2: 0.9 mm of 0.5 oz carried 0.67–0.8 A at 10 °C by the reviewer's IPC fits, against 1.17 A; 1.6 mm uses all the room between the edge rule and H3's hole. M1: no room (0.52 mm channel to CC1; B.Cu taken by the feed), and 1.17 A there needs two faults at once (`independent-review-2-2026-11-09.md`) |
| 2026-11-09 | **Relay RESET margin: a host relay state check now (`temper-lcr relaycheck`), not a board change** | 4.149 V against 4.125 V needs a hot relay at minimum VBUS, and typical relays reset at 35–70 % of rated, so a miss is unlikely. But a miss is silent: two range relays closed (+1.6 % to 42× wrong), or K4 leaving 1 kΩ across the DUT. `relaycheck` takes each range's reference after every other range was held, plus an open-terminal capture, and names the relay that did not release. Bring-up G6a runs it at VBUS 4.40 V on a warm board ([host README](../host/README.md), [bring-up-rev-g.md](bring-up-rev-g.md)) |
| 2026-11-09 | **Later revision: 4.5 V-coil relays (TQ2SA-L2-4.5V-Z, JLC C7402021) for K1–K4** | Panasonic's note for 5 V transistor drive (RCG-02, `../validation/datasheet-audit-rev-g100/relays-connectors.md`). The set voltage is 3.38 V and the maximum allowable is 6.75 V, so the coil sees 90–121 % of rated, with about 0.35 V of set margin at 50 °C, and the 6.25 V hot-plug stays under its maximum. Not now: 0 stock at JLC (2026-11-09). Take it at the next spin if it is stocked, or if G6a still fails after its R101 → 0 Ω rework. Same footprint; rerun `drive_budget.py` with 145 Ω coils and check D5 at about 4 × 31 mA |
| 2026-11-09 | **Accept the switcher pickup increase (§3)** | The pickup is relative and unbounded, and it matters only on a collision, which the source-off check catches. The alternative is 100 × 110 (Rev G), at $24 more for five boards and 10 mm more box depth |

## 6. Datasheet audit and first review (2026-11-09)

Seven datasheet audits and an independent layout review: `../validation/datasheet-audit-rev-g100/FINDINGS.md` (every finding, checked, with its disposition).

**Firmware (both Rev G boards):**
- the jack guard closes on uncharged jacks, not "near 0 V" (it never closed: an open jack floats at +1.65 V);
- LCUR trips at 0.5 V once closed;
- the codec's ADC wakes before the rail wait;
- REFCAPTURE re-checks the jacks before K4.

**Board:**

| Change | Finding |
|---|---|
| D29 SS14 north of C100, cathode GND, anode −12V | SL-1: −12 V went positive at every power-up |
| C15 beside U16 IN (TP20 VB to C15's old land at J1) | G-PE-1 |
| 5V corner at H3 on In2 (1.6 mm, two vias each end); B.Cu ≥ 3.5 mm from H3 | review M1; second review M2 widened it from 0.9 mm |
| TP22 GND 3.1 mm east of J4 | MD-10 |
| VBUS loop under J1's shell deleted; the north pair's exit kept | G-PE-7 |
| Second via where 5V leaves U16 | G-PE-6 |
| Second GND via at each jack TVS | PROT-04 |
| LDO pin 4 bridged to the PowerPAD | SL-7 |
| R101 1 → 0.33 Ω; R132 / R133 300 → 270 Ω | RCG-01, PROT-05 (`drive-budget.json`) |
| C85 to C0G; op-amp rail caps 1 → 2.2 µF | SL-11, G-AFE-05 |

**Analog copper is still 403 / 403 identical to Rev G** (`copper-delta-vs-g.json`), so the extraction and stability carry over.

## 7. Rerun

```sh
python3 cad/tools/rev_g100.py --check          # pre-DRC; also writes cad/design.json, cad/routing.json
sh validation/rev-g100/gates.sh                # KiCad pipeline and every screen -> validation/rev-g100/
```

`gates.sh` restores `manufacturing/`, `previews/` and the shared validation reports when it exits. The hot-plug sweep (about 3 min) is listed at the end of the script.

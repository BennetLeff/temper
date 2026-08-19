# Temper Induction Cooker - Bill of Materials (BOM)

**Project:** Temper - Production-grade Induction Cooker
**Version:** 1.7
**Date:** 2026-08-07
**Status:** Reconciled against `elec/src/*.ato` via `scripts/check_bom_source_reconciliation.py` (R14) — see `docs/hardware/BOM_RECONCILIATION_PROPOSAL.md` for the 49-finding evidence base this pass applied. Three procurement blockers resolved 2026-07-26 — see `docs/evidence/2026-07-26-bom-blocker-resolution.md`.

---

## 1. Power Stage Components

### 1.1 IGBTs and Gate Driver

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| Q1, Q2 | 1200V 40A IGBT | IKW40N120H3 | Infineon | 2 | TO-247 | Half-bridge |
| U_GD | Isolated Gate Driver | UCC21550BDWKR | Texas Instruments | 1 | SOIC-14 (DWK) | Dual channel — see note |
| D_BOOT | Bootstrap Diode | ES1J | onsemi | 1 | SMA | 600V 1A ultrafast — see note |
| C_BOOT | Bootstrap Capacitor | GRM32ER71H106KA12L | Murata | 1 | 1210 | 10µF 50V X7R |
| RG_ON | Gate Turn-On Resistor | RC1206FR-072R2L | Yageo | 2 | 1206 | 2.2Ω 5% 0.5W |
| RGS | Gate-Source Pull-Down | RC0603FR-072K2L | Yageo | 2 | 0603 | 2.2kΩ 5% |
| D_ZENER | Negative-Bias Zener | BZT52C5V1-7-F | - | 1 | SOD-123 | 5.1V — sets VSSA negative gate off-bias |
| R_DT | Dead-Time Resistor | RC0603FR-0734KL | Yageo | 1 | 0603 | 34kΩ 1% — sets ~305ns nominal dead time on UCC21550's DT pin |
| C_VCCI1 | Driver VCCI Bypass | C0603C104K5RACTU | KEMET | 1 | 0603 | 100nF 10% X7R 50V — MPN fixed 2026-07-26, see note |
| C_VCCI2 | Driver VCCI Bypass (bulk) | GRM188R71C105KA12D | Murata | 1 | 0603 | 1µF 10% X7R 16V |
| C_VDDA | Driver VDDA (HS) Bypass | C0603C104K5RACTU | KEMET | 1 | 0603 | 100nF 10% X7R 50V — 15V rail, DC-bias derating flag, see note |
| C_VDDB | Driver VDDB (LS) Bypass | C0603C104K5RACTU | KEMET | 1 | 0603 | 100nF 10% X7R 50V — 15V rail, DC-bias derating flag, see note |
| C_DC_HF | DC Bus HF Decoupling | B32671L6474K000 | TDK/EPCOS | 1 | THT Film 18x11mm | 470nF 10% 630V PP — at the bridge, across HV+/HV- |

> **`D_BOOT` corrected 2026-07-26.** Previously `UJ3D1210TS` (SiC Schottky, TO-220, 1200V/10A) — a different device class entirely for what is a small bootstrap-recharge diode. Source (`components.ato:262-273`) uses `ES1J`, a 600V/1A SMA ultrafast rectifier sized to the boot-cap recharge pulse, not the main power path.
>
> **`U_GD` corrected again 2026-07-28: `UCC21550BDWKR`.** The previous value `UCC21550BDW` is not a TI orderable part number — TI SLUSE89C's PACKAGING INFORMATION addendum lists exactly five orderables, all tape-and-reel: `UCC21550ADWKR`, `UCC21550ADWR`, `UCC21550BDWKR`, `UCC21550BDWR`, `UCC21550CDWKR`. The prior note's claim that the board wanted the "correct 16-pin DW package" was also wrong in the other direction: the board footprint (`pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod`, and the placed U7 instance) has **14 pads, numbered 1–11 and 14–16** — the DWK land pattern. SLUSE89C Figure 4-2 confirms the DWK package skips pin numbers 12 and 13 entirely. `UCC21550BDWKR` is Active/Production, SOIC (DWK) | 14 pins, part marking `21550B`, and keeps the "B" grade (rec. VDD supply min 9.2 V) the +15 V secondary rail needs.
>
> `D_ZENER`, `R_DT`, `C_VCCI1/2`, `C_VDDA/B`, `C_DC_HF` were wired in source but not costed here (Class B, 2026-07-25 audit). The two PWM-input EMI filter R/C pairs that also live inside the gate-drive module (`r_filt_a/b`, `c_filt_a/b`) are listed once, in §8, to avoid double-counting.
>
> **`C_VCCI1`/`C_VDDA`/`C_VDDB` MPN corrected 2026-07-26 (Blocker 1).** `GRM188R71E104KA01D` (Murata) is Obsolete with 0 stock per DigiKey's own product page — confirmed 2026-07-26. It was the single most-instantiated part in the design (16 refs across the board, all now corrected the same way — see §2.1, §2.3, §3.1, §4.1, §5.3, §5.6). Replaced everywhere with `C0603C104K5RACTU` (KEMET, 100nF ±10% X7R 50V, 0603) — Active, 6,707,514 units at DigiKey, confirmed 2026-07-26. Full evidence: `docs/evidence/2026-07-26-bom-blocker-resolution.md`.
>
> **DC-bias derating flag (new, 2026-07-26).** `C_VDDA` and `C_VDDB` decouple the 15V gate-drive rail, ~60% of the *old* part's 25V rating — a bias point where 0603 X7R MLCCs are known to lose a large fraction of nominal capacitance (industry rule of thumb: 40–60% loss of nominal C near 50% of rated voltage is typical for this case size/dielectric). The replacement's 50V rating drops that ratio to ~30%, which should retain materially more capacitance, but no part-specific DC-bias curve has been pulled for either the old or new part — treat the retained capacitance as UNVERIFIED, not as still-100nF.

### 1.2 AC Input, EMI Filter & Voltage Doubler

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| F1 | AC Mains Fuse LINK (not an assembly) | 0034.3129 | Schurter | 1 | 5x20mm THT | 16A 250V time-lag — see note, holder is a separate line below |
| F1_HOLDER | AC Mains Fuseholder, PCB-mount | 0031.2510 | Schurter | 1 | THT, FUP series | 16A(VDE)/30A(UL,CSA), 250/500VAC(VDE) — added 2026-07-26, see note |
| RV1 | MOV Surge Suppressor | V150LA10AP | Littelfuse | 1 | Radial Disc 15.5mm | 150VAC clamp, L-N after fuse |
| C_X2 | EMI Cap (differential-mode) | B32922C3224M289 | EPCOS/TDK | 1 | THT Radial Box, 15mm pitch | 0.22µF 20% X2 305VAC (max cont. 310VAC)/630VDC — MPN fixed 2026-07-26, see note |
| L_EMI | Common-Mode Choke | B82726S2163N030 | TDK (EPCOS) | 1 | THT, 4-pin | 2.2mH/winding ±30% @10kHz, 16A, ~7.1mΩ/winding — ONE physical part, no polarity |
| NTC_INRUSH | Inrush Limiter | SL32 10015 | Ametherm | 1 | Radial 15mm | 10Ω 15A |
| K_BYPASS | Bypass Relay | RT33K012 | TE Connectivity / Schrack | 1 | THT, SPST (RT1 family) | 12V coil, 20A UL508/16A IEC contact (SPST-NO) — PD3 swap 2026-08-13, see note |
| Q_RLY_DRV | Bypass Relay Driver MOSFET | AO3400A | Alpha & Omega Semi | 1 | SOT-23 | Low-side switch for K_BYPASS coil |
| R_RLY_DROP | Relay Coil Dropper | RSF100JB-73-91R | Yageo | 1 | Axial DIN0207 | 91Ω 5% 1W — retuned 2026-08-13 for K_BYPASS coil swap, see note |
| R_RLY_GATE | Relay Driver Gate R | CRCW08051K00FKEA | Vishay | 1 | 0805 | 1kΩ 5% 0.125W |
| R_RLY_GATE_PD | Relay Driver Gate Pulldown | CRCW0805100KFKEA | Vishay | 1 | 0805 | 100kΩ 5% 0.125W |
| D_RLY_FLYBACK | Relay Coil Flyback Diode | SS14 | - | 1 | SMA | 40V 1A Schottky |
| D1, D2 | Ultrafast Rectifier | MUR1560G | ON Semiconductor | 2 | TO-220 | 15A 600V 35ns |
| C_BUS1, C_BUS1B, C_BUS2, C_BUS2B | Bus Capacitors | LGW2E182MELC50 | Nichicon | 4 | Radial Snap-In 35mm | 1800µF 250V 105°C — 2 in parallel per half-bus (3600µF/half). **Reselected 2026-08-19** from EKMQ251VSN182MA50S: identical D35×50 snap-in footprint and value, so no PCB change, but **4050 mA** rms @105°C/120 Hz vs 2700 mA and 3000 h vs 2000 h endurance. Ratings read from Nichicon CAT.8100N. The incumbent fails its own ripple rating; see `docs/evidence/2026-08-19-bus-capacitance-selection.md`. Zero-board-change move, not the full fix — the recommended 6×`LGW2E471MELB25`/half bank needs placement rework and is NOT applied. |
| R_BLEED1, R_BLEED2 | Bleeder Resistors | CRGP2512F22K | TE Connectivity | 2 | 2512 | 22kΩ 1% 2W — τ≈79s per half-bus, backstop for the active discharge in §1.3 |
| Y_CAP_PE | PE Bonding Cap (Y1) | B81123C1562M000 | TDK | 1 | THT Radial Box, **22.5mm lead spacing** (L26.5×W7.0×H16.0mm) | 5.6nF 20% Y1 500VAC — doubler midpoint to PE. PD3 value/MPN swap 2026-08-13, see note |

> **`J_IN` (AC mains inlet connector, Schurter 4798.9000) removed.** No inlet-connector component exists anywhere in `elec/src/*.ato` — `ac_l`/`ac_n`/`pe` are declared only as abstract external `signal`s on `PowerInput` (`modules.ato:432-437`), never instantiated as a physical connector part. `grep -rn "4798\|Schurter" elec/src/*.ato` returns nothing.
>
> **`K_BYPASS` corrected**: source MPN is `G4A-1A-E DC12` (Omron), not `G5LE-1-E`. The `G5LE-1-E` this BOM previously listed is actually the MPN for `K_DIS1`/`K_DIS2`, the *discharge* relays in §1.3 — a different physical relay under the wrong designator.
>
> **`K_BYPASS` swapped 2026-08-13 (PD3 creepage) — `G4A-1A-E DC12` → `RT33K012`.** `docs/evidence/2026-08-13-hv-creepage-pd3-gap-measurement-and-plan.md` (PR #1152) measured the incumbent Omron part's coil↔contact copper gap at exactly **8.000mm**, first-hand, with this repo's canonical rotation-and-side-aware pad-geometry kernel — fails the 12.6mm PD3 reinforced-creepage target the board's own PD2→PD3 correction requires (the incumbent's contact pins are actually Faston tabs with zero PCB copper on this variant, per `temper:Relay_SPST_Omron-G4A-E`'s own `descr`; the 8.000mm figure is the geometric distance the safety analysis must use regardless). TE Schrack `RT33K012` (`2-1393240-3`, DigiKey `PB2347-ND`) — same RT1/RT3 case family as `K_DIS1`/`K_DIS2`'s already-verified `RT314012` — was independently re-confirmed this session as Active/orderable (1,197 units at DigiKey) and re-measured, with the same canonical kernel against its actual footprint geometry (not a datasheet-drawing hand computation): governing coil↔contact separation **17.8000mm**, clears 12.6mm by **+5.2mm**. Contact rating (20A UL508 K-version/16A IEC, 277VAC) matches or exceeds the outgoing part; VDE Cert. 40007571 is the same certificate class already accepted for `RT314012`. **Real placement blocker, reported not forced**: this footprint's true THT copper contact pads (the incumbent's equivalent pins carry zero copper) do not fit at K_BYPASS's current board site — verified via real `kicad-cli` DRC on a scratch-resynced candidate board, all 4 cardinal rotations tested, every one produces genuine new electrical shorts against existing routed copper (`safety.fault_or-b2`/`power_in.ntc-no` and `rtd_pan.high_window-out`/`w1_2` at the resync's chosen 180° orientation; different net pairs at 0°/90°/270°), plus a courtyard collision with `C27`. `pcb/temper.kicad_pcb` is deliberately NOT resynced by this change — needs a reroute or a placement pass beyond this task's scope before this part can be physically realized (same class of problem as T2, PR #1144/`docs/evidence/`). Coil is electrically different (360Ω/400mW vs. the outgoing part's 160Ω/900mW) — see `R_RLY_DROP` note below.
>
> **`R_RLY_DROP` retuned 2026-08-13 for the `K_BYPASS` swap above** — was `RSF100JB-73-39R` (39Ω), sized for the outgoing G4A-1A-E's 160Ω coil (`15V/(160+39Ω)=75.4mA`, `75.4mA×160Ω=12.06V`, ~100.5% of the 12V rated coil voltage). `RT33K012`'s coil is 360Ω/400mW; unchanged, 39Ω overdrives it to 112.7% of rated (`15V/(360+39Ω)=37.6mA`, `37.6mA×360Ω=13.5V`) — above IEC 61810-1's typical 110% continuous-operation ceiling, flagged as an open compatibility question in `docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md` §1.5 and resolved here. `RSF100JB-73-91R` (91Ω, nearest E24 value to the exact 90.0Ω solve, same 1W axial family, confirmed orderable at DigiKey) restores correct drive: `15V/(360+91Ω)=33.26mA`, `33.26mA×360Ω=11.97V`, 99.8% of rated.
>
> **`L_EMI` corrected**: source is `B82726S2163N030` (2.2mH/winding, 16A), not `B82725S2183N040` (2×4.7mH, 18A).
>
> **`C_BUS1`/`C_BUS2` corrected**: `EKZE251ELL332MM40S` (3300µF) does not exist as an orderable part — source comment: "replace the fictional 3300uF/250V EKZE part." Source uses 4× `EKMQ251VSN182MA50S` (1800µF each, 2 in parallel per half-bus = 3600µF/half), not 2× 3300µF.
>
> **`R_BLEED1/2` corrected**: 22kΩ, not 100kΩ — a 4.5× error in the passive bus-discharge time constant. MPN/manufacturer were previously blank; source comment identifies `CRGP2512F22K` as TE Connectivity, "2W@70°C pulse-withstanding."
>
> **`F1`/`F1_HOLDER` split 2026-07-26 (Blocker 3).** `0034.3129` is real and stocked (DigiKey, in stock, confirmed 2026-07-26) but it is a bare Schurter FST 5x20mm fuse **link**, not a "holder+fuse" assembly as this BOM previously described it — Schurter's `0034.xxxx` numbering is the FST link family; fuseholders are a separate part family. No PCB-mount fuseholder existed anywhere in the 155-part count. Added `F1_HOLDER` = Schurter `0031.2510` (FUP series), confirmed via Schurter's own FUP datasheet: 5x20mm fuse-link acceptance (order-code table explicitly lists `0031.2510` = 5x20mm variant), PCB/THT solder-pin mount, rated 16A (VDE)/30A (UL,CSA) at 250/500VAC (VDE)/600V (UL,CSA) — meets/exceeds this circuit's 16A/250V. Approved to IEC 60127-6 (fuseholders for miniature fuse-links), UL 4248-1/CSA C22.2 no.4248.1, VDE cert 40045336, UL File E39328, and suitable per IEC 60335-1 (household appliances, unattended use — matches this product). Confirmed Active, 83 units at DigiKey, 2026-07-26. **Not separately modeled in `elec/src`**: mechanically it occupies the same two electrical nodes as `F1` (no new net), matching this BOM's existing treatment of other mechanical-only lines (heatsink, TIM pads, mounting hardware — §11). **New footprint required, not yet drawn**: the current PCB footprint stub (`Fuse:Fuse_Holder_5x20mm`, 2-pin THT, 22.5mm pitch, `temper.kicad_pcb`'s own comment calls it a "stub") does not match the FUP's real drilling diagram (~30.48mm primary pin spacing plus a third orientation pin, per Schurter's FUP datasheet).
>
> **Fuse rating / I²t coordination — open question, not resolved by this pass.** 16A/250V on a 15A continuous branch load (1800W/120V, `constraints.i_max` in `elec/src/constraints.ato`) is only ~7% headroom above full-load current for a time-lag fuse expected to ride through NTC-limited inrush without nuisance-tripping at legitimate steady-state load. No I²t/time-current coordination analysis between `F1`, `NTC_INRUSH`, and `K_BYPASS`'s switch-in timing was found anywhere in this repo. Flagging for follow-up, not fixing here.
>
> **`C_X2` corrected 2026-07-26 (Blocker 2).** `DE2E3KH221MA3B` was not found at any distributor, and Murata's own DE2-series "221" suffix convention decodes to 220**pF** (confirmed against sibling `DE2B3SA221KA3BT02F` = 220pF) — 1000× off the 0.22µF/220nF this circuit actually needs; Murata's DE2 leaded safety-disc line tops out around 10nF and cannot make this value in that family at all. The 220nF **value** was correct (standard X2 line-EMI value for this position); only the MPN was fictional. Replaced with EPCOS/TDK `B32922C3224M289` — confirmed Active, 28,179 units at DigiKey, 2026-07-26. Approvals read directly from EPCOS's own B32921...B32926 X2/305VAC datasheet: EN132400/IEC 60384-14 (cert 40005536/40010694), UL 1414/UL 1283 (E97863/E157153), CSA C22.2 No.1/No.8 (E97863/E157153, approved by UL), CQC GB/T14472-1998 (CQC001007-14859). Rated 305VAC per IEC 60384-14 with 310VAC maximum continuous — matches this design's original 310V spec exactly. **New footprint required, not yet drawn**: the disc footprint this BOM/source previously carried matched the fictional disc-style part, not the real MKP box-style replacement (2-pin THT radial box, 15mm lead pitch, body ~7.0×12.5×18.0mm). Full evidence and falsifier: `docs/evidence/2026-07-26-bom-blocker-resolution.md`.
>
> **`Y_CAP_PE` corrected 2026-07-28 (fabricated MPN).** `DE1E3KX222MA4BA01` does not exist: it pairs Murata's current lead-style code `A4B` with the legacy individual-specification suffix `A01`, a combination that appears in no Murata document and at no distributor. Murata's own datasheets pair `A4B` with `N01F`/`Q01F` and `A01` with `A5B`. Both real spellings are dead ends for new design: `DE1E3KX222MA4BN01F` is "Obsolete — no longer manufactured", 0 stock (DigiKey 4421160, fetched 2026-07-28; its listed substitute `DE1E3RA222MA4BN01F` is also 0 stock), and Mouser redirects `DE1E3KX222MA5BA01` to that same obsolete part. Replaced with Vishay BCcomponents **`VY1222M47Y5UQ6TV0`** — Active, 365 in stock at DigiKey (2824499, fetched 2026-07-28), 2200pF ±20%, X1/Y1 per IEC 60384-14, **Y1 at 500VAC** (X1 760VAC) vs the 250VAC this node requires, lead spacing 0.394" (10.00mm), body 12.0mm dia. Ordering code decoded against Vishay datasheet 28537 (`VY1222#47Y5UQ6###` is the datasheet's own 2200pF Y5U row; `M`=±20%, `T`=tape and reel, `V`=inline kinked leads, `0`=10.0mm spacing). Safety class is preserved and its voltage margin increased; capacitance and tolerance are unchanged.
>
> **`Y_CAP_PE` footprint corrected in source 2026-07-28; the board still needs the edit.** Every 2.2nF Y1 disc, including both real Murata spellings and the Vishay part above, has 10mm lead spacing, but the land on the board is a 5.00mm-pitch stub whose own `descr` says "Created to resolve netlist reference" (and says Y2, a different safety class). `elec/src/modules.ato` now assigns `Capacitor_THT:C_Disc_D12.5mm_W5.0mm_P10.00mm` (stock KiCad; its own `descr` cites Vishay's sibling VY2 datasheet 28535; D12.5 ≥ the 12.0mm body, W5.0 ≥ the 5.0mm thickness), which takes C6's HV↔SELV pad separation from **3.200mm to 8.000mm** — clearing the 8.0mm gate exactly, but not the CP-SAT placer's 8.5mm working corridor. `pcb/temper.kicad_pcb` still carries the 5.00mm stub. See `docs/evidence/2026-07-28-tank-cap-and-isolator-footprints.md` and `2026-07-28-isolator-sourcing-brief.md`.
>
> **`Y_CAP_PE` swapped again 2026-08-13 (PD3 creepage) — `VY1222M47Y5UQ6TV0` (2.2nF, 10mm) → `B81123C1562M000` (5.6nF, 22.5mm).** The same PR #1152 gap-measurement doc that found `K_BYPASS` failing (above) also measured the current 10mm-pitch Vishay disc part at exactly **8.000mm** HV↔SELV — fails 12.6mm PD3. No ceramic Y1 capacitor at any manufacturer checked (TDK, Vishay ×3, KEMET — `docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md` §2) clears 12.6mm at any capacitance: ceramic-disc Y1 lead spacing is flat at a 12.5mm industry-wide ceiling. TDK's own B81123 **film**-Y1 family reaches a genuinely larger 22.5mm lead spacing, but only starting at 5.6nF — a real 2.5× value change from the 2.2nF±20% spec window, reported plainly, not smoothed over. `B81123C1562M000` re-confirmed this session as a real, orderable, Active TDK part (DigiKey `495-1653-ND`; lead spacing 22.50mm per DigiKey's own listing, matching the datasheet's ordering table). MEASURED this session with the canonical pad-geometry kernel against the exact stock KiCad footprint (`Capacitor_THT:C_Rect_L26.5mm_W7.0mm_P22.50mm_MKS4`, whose own dimensions — 26.5×7.0×16.0mm — match this ordering code's datasheet row exactly): **20.1000mm**, clears 12.6mm by **+7.5mm**. Touch-current re-checked against the corrected, complete IEC 60335-1 Clause 13/16 leakage budget in `docs/evidence/2026-07-30-c6-touch-current-budget-and-part2-routes.md`: 5.6nF clears even the strictest reading found (no protective-impedance exemption, no filter-doubling credit) with 8–15% headroom (1153.7–1241.7µA against the 1.35mA heating-appliance limit) — thinner margin than this design's other solved PD3 crossings, reported as-is. **Placement, verified clean**: unlike `K_BYPASS`, this footprint swap alone (`kicad-cli` DRC on a scratch-resynced candidate board, isolated from the `K_BYPASS` change) reproduces the baseline board's DRC category counts **exactly** — zero new violations of any kind. `pcb/temper.kicad_pcb` is deliberately NOT resynced by this change, same as the still-open 2026-07-28 note above, but the resync is expected to be clean when it happens. (Landing `K_BYPASS` and `Y_CAP_PE` together does introduce one new courtyard collision between the two new footprints specifically — see the `K_BYPASS` note.)
>
> `RV1`, `C_X2`, `Y_CAP_PE`, `F1`, the `K_BYPASS` driver (`Q_RLY_DRV`/`R_RLY_DROP`/`R_RLY_GATE`/`R_RLY_GATE_PD`/`D_RLY_FLYBACK`), and the ZCD divider+clamp were wired in source but not costed (Class B, 2026-07-25 audit).
>
> **`U_ZCD_OPTO`/`R_ZCD_OPTO`/`R_ZCD_PULLUP`/`R_ZCD_TOP1`/`R_ZCD_TOP2`/`R_ZCD_BOT`/`D_ZCD_CLAMP` removed 2026-08-14, pruned per this section's own prior note.** `5842767c2` deleted the entire mains-ZCD circuit from `elec/src/*.ato` (no firmware consumer — `PIN_ZCD_INPUT` was never read past its own `#define`; no architectural role in this time-delayed, non-zero-cross-synchronised soft-start). This BOM subsection is pruned in the same change, as the prior version of this note required. See `docs/evidence/2026-07-30-zcd-optocoupler-removal.md` for the original circuit/net inventory.

### 1.3 Active Bus Discharge (Fail-Safe)

**Added 2026-07-26 — was entirely uncosted.** `BusDischarge` (`modules.ato:692-938`) is the sole fail-safe mechanism that discharges the ~340V bus to <34V within ~60s on any loss of power (unplug, fuse, aux-supply fault, or MCU death — `IO47` boots Hi-Z, which engages discharge by default). It runs in parallel with, not instead of, the passive `R_BLEED1/2` bleeders in §1.2.

> **`K_DIS1`/`K_DIS2` corrected 2026-08-07 — swapped to `RT314012`.** `G5LE-1 DC12` was TRIED-AND-REVERTED 2026-07-28 (`docs/evidence/2026-07-28-relay-replacement-implementation.md` → `docs/evidence/2026-07-28-pd3-retarget-relay.md` → `docs/evidence/2026-07-28-relay-board-resync-decision.md`): a Finder `40.52.7.012.0000` attempt was retracted when its claimed 9.2mm edge-to-edge coil↔contact creepage figure turned out to be an invented footprint layout, not measured from the real part's fixed pinout (the manufacturer's real pitch caps achievable creepage at 5.3mm, failing both the 8.0mm and 12.6mm PD3 targets). The `G5LE-1` reverted to at that point genuinely failed reinforced coil↔contact isolation (6.32mm pad gap / 3.50mm edge-to-edge against the 8.0mm requirement). **That gap is now resolved**: source (`modules.ato:1227-1253`) swapped both relays to TE Connectivity/Schrack `RT314012` (RT1 family, `Relay_SPDT`, footprint `temper:Relay_SPDT_Schrack-RT314012`) — K2 on 2026-07-31 (`23f103c9`), K3 on 2026-08-02 (`0f0a1341` interim revert for a placement blocker, `de59c045`/PR #602 final) — with a 12.76mm coil-to-contact copper gap, clearing the 8.0mm reinforced-creepage bar (1.6×) and the 6.0mm clearance minimum (2.1×). Coil/contact ratings (12V/10A, 360Ω±10%/400mW coil, 8.4V must-operate) match the outgoing G5LE-1 exactly, so `R_COIL1/2` and the driver circuit are unaffected.

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| K_DIS1, K_DIS2 | Discharge Relay | RT314012 | TE Connectivity / Schrack | 2 | THT, 5-pin SPDT | 12V coil, 10A contact — NC contact engages discharge fail-safe. 12.76mm coil↔contact copper gap clears the 8.0mm reinforced-creepage bar (1.6×) and 6.0mm clearance minimum (2.1×) — see corrected note above. |
| R_DIS1A, R_DIS1B, R_DIS2A, R_DIS2B | Discharge Resistor | AC05000003901JAC00 | Vishay | 4 | Axial DIN0918 | 3.9kΩ 5% 5W — 2 in series per half-bus (7.8kΩ/half). RESIZED 2026-07-27 from 4.7kΩ (9.4kΩ/half) — at 4.7kΩ the bus discharges in 65.4s against the <60s requirement (fails on the bus capacitor's own +20% rated tolerance alone); 3.9kΩ gives 56.9s under stacked worst-case tolerance (+5% R, +20% C), ~3.1s margin. See `docs/evidence/2026-07-27-busdischarge-tolerance-retune.md`. |
| R_COIL1, R_COIL2 | Relay Coil Dropper | RC1206FR-07100RL | Yageo | 2 | 1206 | 100Ω 1% 0.25W 200V |
| Q_DIS_DRV | Discharge Relay Driver MOSFET | AO3400A | Alpha & Omega Semi | 1 | SOT-23 | Low-side switch, both coils |
| R_DIS_GATE | Discharge Driver Gate R | CRCW08051K00FKEA | Vishay | 1 | 0805 | 1kΩ 5% 0.125W |
| R_DIS_GATE_PD | Discharge Driver Gate Pulldown | CRCW0805100KFKEA | Vishay | 1 | 0805 | 100kΩ 5% 0.125W |
| D_FLY1, D_FLY2 | Coil Flyback Diode | SS14 | - | 2 | SMA | 40V 1A Schottky |
| R_SNUB1, R_SNUB2 | Contact Snubber R | CRGP2512F100R | TE Connectivity | 2 | 2512 | 100Ω 1% 2W 500V |
| C_SNUB1, C_SNUB2 | Contact Snubber C | B32671L6474K000 | TDK/EPCOS | 2 | THT Film 18x11mm | 470nF 10% 630V PP |

17 parts total. Sizing: τ = 7.8kΩ × 3600µF ≈ 28.1s per half-bus; worst-case stacked tolerance (R+5%, C+20%) gives 56.9s to <34V, against the <60s target (~3.1s margin) — see the `R_DIS1A/1B/2A/2B` note above and `docs/evidence/2026-07-27-busdischarge-tolerance-retune.md`. See the module docstring (`modules.ato:692-723`) for the full contact-stress and snubber derivation, and `docs/plans/2026-07-16-001-feat-active-bus-discharge-and-thermal-bom-plan.md` for the option analysis.

### 1.4 Resonant Tank

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| L_TANK | Tank Inductor | CUSTOM_LITZ_COIL | — (custom-wound) | 1 | Flat spiral, ferrite-backed, OD ≤ 200mm, 2 leads to `LitzPad_15A` pads | **88µH ±10% @ 40kHz**, DCR ≤ 0.12Ω, R_ac ≤ 0.40Ω @ 40kHz, 25A rms — **must pass the incoming acceptance test** in `docs/hardware/TANK_COIL_SPECIFICATION.md` §2 |
| C_TANK1, C_TANK2, C_TANK3 | Tank Capacitor | 942C16P1K-F | Cornell Dubilier (CDE) | 3 | Axial, D22.5×L34.0mm, **P40.00mm** | 100nF 1600VDC PP, ±10% — wired in parallel (300nF combined), 11.4A rms/cap. Re-sourced 2026-07-29, see note |

> **`C_TANK1/2` re-sourced again 2026-07-29 (WIMA → CDE, 2→3 physical caps).** Source (`modules.ato:513-532`, `docs/evidence/2026-07-29-tank-cap-cde-942c-verification.md`) replaced the 2× WIMA `FKP1T031507G00JSSD` (150nF each) with 3× CDE `942C16P1K-F` (100nF each, same 300nF combined) because the WIMA part's AC-current rating undershot the 10.37A required at 47kHz switching — CDE's 11.4A rating clears with 1.38× margin (PR #410, `3ae26dfe`). This adds a third physical capacitor (`C_TANK3`, `c_tank3` at `modules.ato:527`, previously entirely uncosted) and loosens tolerance from ±5% to ±10% (MPN's "K" suffix). Package changes from WIMA's 41.5×20mm radial box (37.5mm pitch) to CDE's 22.5mm-diameter, 34.0mm-long axial can (40.00mm pitch, footprint `temper:C_Axial_L34.0mm_D22.5mm_P40.00mm_Horizontal`).
>
> **`C_TANK1/2` MPN corrected 2026-07-28 (10× value error, superseded by the 2026-07-29 re-source above).** The previous value `FKP1U021507E00JSSD` decodes, against WIMA's own 18-digit part-number system (FKP 1 datasheet rev. 03.26, p.136), as `FKP1` | `U0` = **2000 VDC** | `2150` = **0.015 µF** | size `7E` | `00JSSD` — a tenth of the declared 150nF, at the wrong voltage. `scripts/mpn_fabrication_gate.py`'s WIMA decoder (PR #397) flags exactly this. The 2000 VDC table has no 0.015 µF row in a size-7 (PCM 37.5) case at all — its only 0.015 µF row is `FKP1U021506D` (13 × 24 × 31.5, PCM 27.5) — and the land pattern the board carried, `C_Rect_L31.5mm_W13.0mm_P27.50mm_MKS4`, is precisely that case, i.e. the board was drawn for the mis-decoded part rather than for the declared value. Corrected to **`FKP1T031507G00JSSD`**, read off WIMA's 1600 VDC ordering table: "0.15 µF | W 20 | H 39.5 | L 41.5 | PCM 37.5 | `FKP1T031507G_ _ _ _ _ _`". The six trailing digits are the datasheet's own "Part number completion" box and are carried over unchanged (`00` 2-pin, `J` ±5 %, `S` bulk, `SD` 6-2 pin length). **Capacitance is unchanged at 150nF each / 300nF combined** — that value was never in doubt; it is what `RESONANT_TANK_DESIGN.md`, every ZVS/inductance sweep in `simulation/harness/`, and `main.ato`'s 47kHz switching point are all built on. The KEMET R76-series "(alt)" second-source line from an earlier revision remains dropped.
>
> **⚠ `C_TANK1/2/3` board layout status superseded, needs re-verification.** The 2026-07-28 note below describes board-rework needs against the now-superseded WIMA 41.5×20mm/37.5mm-pitch part; the 2026-07-29 re-source to CDE's 22.5mm-diameter/34.0mm-long/40.00mm-pitch axial can (and the addition of a third physical capacitor, `C_TANK3`) means the PCB placement question must be re-checked against the current footprint (`temper:C_Axial_L34.0mm_D22.5mm_P40.00mm_Horizontal`), not assumed resolved or unresolved from the WIMA-era findings. Not verified against `pcb/temper.kicad_pcb`'s current state by this pass (BOM-vs-source reconciliation only; PCB layout out of scope). See `docs/evidence/2026-07-28-tank-cap-and-isolator-footprints.md` for the WIMA-era findings and `docs/evidence/2026-07-29-tank-cap-cde-942c-verification.md` for the CDE re-source.
>
> **`L_TANK` is now specified — 88µH ±10% @ 40kHz (2026-07-29).** It was
> undetermined until then (`elec/src/*.ato` contained no inductance value at
> all; `inductor_conn` was a valueless `new Resistor` placeholder, and the
> "80µH, 50A, ferrite" note carried over from earlier BOM revisions was never
> source-verified). It is now `new Inductor`, `88uH +/- 10%`, and
> `scripts/check_pll_range_consistency.py` check 7 fails the build if that
> declaration and `main.ato`'s `l_tank_assumed` disagree. See
> `docs/evidence/2026-07-29-tank-coil-specification.md`.
>
> **⚠ There is still no part number, and this coil cannot be ordered from a
> catalogue.** No orderable coil in this class publishes an inductance
> (`docs/evidence/2026-07-28-coil-selection-research.md` §2 searched Infineon,
> Würth, OEM appliance spares and the custom-wind channel). `CUSTOM_LITZ_COIL`
> is a placeholder identifier, not an MPN. The route is: specify to a magnetics
> house against `docs/hardware/TANK_COIL_SPECIFICATION.md` §1, then **accept on
> measurement**.
>
> **⚠ Acceptance is on LOADED inductance, and the ratio test alone is not
> enough.** Accept if **`L_loaded ≥ 53.00µH`** measured at 40 kHz with a
> ferromagnetic reference pan at the production gap (target 59.8µH). This
> threshold was raised from 52.8µH on 2026-07-29 to also worst-case
> `c_tank1`/`c_tank2`'s own +/-5% tolerance (previously the derivation used
> nominal 300nF capacitance while worst-casing only the coil) --
> `scripts/check_pll_range_consistency.py` check 8 derives it and fails the
> build if spec doc §2's stated number ever disagrees. A coil that is −10%
> on unloaded inductance *and* only meets the commonly-quoted
> `L_loaded ≥ 0.60 × L_unloaded` screen resonates at 42.15 kHz — above
> `PLL_MIN_FREQ_HZ` (now 43kHz) — which puts a hard-switching regime inside
> the firmware's legal range. Full procedure and derivation: spec doc §2.
>
> **⚠ Coil thermal design does not exist.** ~150–200 W of the coil's own copper
> loss at 1800 W, and `LitzPad_15A` declares a 15 A pad against a 20.7–22.5 A
> rms tank current. Neither is resolved — spec doc §3 and §8.

---

## 2. Power Management

### 2.1 Buck Converter (15V → 3.3V)

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| U_BUCK | Synchronous Buck | LMR51430XDDCR | Texas Instruments | 1 | SOT-23-6 | 4.5-36V in, 3A |
| L_BUCK | Buck Inductor | SRP1265A-5R6M | Bourns | 1 | SMD 12.5x12.5mm | 5.6µH 12.5A |
| C_IN | Input Capacitor | GRM32ER71E106KA12L | Murata | 1 | 1210 | 10µF 20% X7R 25V |
| C_OUT1, C_OUT2 | Output Capacitor | GRM32ER71E226KE15L | Murata | 2 | 1210 | 22µF 20% X7R 25V |
| C_OUT_HF | Output HF Decoupling | C0603C104K5RACTU | KEMET | 1 | 0603 | 100nF 10% X7R 50V — MPN fixed 2026-07-26 |
| C_BOOT | Bootstrap Capacitor | C0603C104K5RACTU | KEMET | 1 | 0603 | 100nF X7R 50V — MPN fixed 2026-07-26; ~5V nominal across it (bootstrap flying cap), not the 15V SW-node swing |
| R_FB_TOP | Feedback Divider High | RC0603FR-07100KL | Yageo | 1 | 0603 | 100kΩ 1% |
| R_FB_BOT | Feedback Divider Low | RC0603FR-0722K1L | Yageo | 1 | 0603 | 22.1kΩ 1% |

> **Section retitled and corrected.** This is a 15V→3.3V converter (`power_out.voltage = 3.3V`, `modules.ato:959`), not "24V/12V→5V" — the previous title and several values described a different converter entirely. `L_BUCK` (was 6.8µH `SRP1038A-6R8M`), `C_IN` (was 2.2µF/100V `GRM32ER72A225KA35L`), `C_OUT1/2` MPN (was `GRM31CR61E226KE15L`), `C_BOOT` (was 10nF/50V `GRM188R71H103KA01D` — a materially different value, not a typo), and `R_FB_BOT` (was 32.4kΩ, which combined with the correct `R_FB_TOP` computes the wrong output voltage) are all corrected against `modules.ato:963-1017`. `C_OUT_HF` was wired but uncosted (Class B).

### 2.2 LDO (5V → 3.3V) — REPLACED BY BUCK CONVERTER

**No parts.** `components.ato:46`: "XC6220 removed: LDO3V3 replaced by BuckConverter3V3 (plan 005)." The 3.3V rail is produced by the synchronous buck converter in §2.1, not a linear regulator. Removed: `U_LDO` (XC6220B331MR-G), `C_IN_LDO`, `C_OUT_LDO`.

### 2.3 Isolated Auxiliary 15V Supply

**Added 2026-07-26 — entirely uncosted (Class B, Critical).** `AuxSupply` (`modules.ato:1075-1139`) takes ~170VDC off the half-bus and produces the isolated 15V SELV rail that feeds the gate driver, relays, and (via §2.1) the 3.3V rail. **This module IS the galvanic isolation barrier** between the HV power domain and the SELV control domain — the RTD probe, MCU, and all logic-side sensing depend on it for user safety.

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| PS1 | Isolated AC/DC Module | IRM-10-15 | Mean Well | 1 | THT Module | 15V 0.67A 10W; 4.2kVac I/O withstand, Class II, IEC/EN 61558/62368-1 |
| C_IN_BULK | Input Bulk Capacitor | GRM55DR72E106KW01L | Murata | 1 | 2220 | 10µF 20% X7R 250V |
| C_OUT | Output Filter Capacitor | GRM32ER71E107ME15L | Murata | 1 | 1210 | 100µF 20% X7R 25V |
| C_OUT_HF | Output HF Decoupling | C0603C104K5RACTU | KEMET | 1 | 0603 | 100nF 10% X7R 50V — MPN fixed 2026-07-26; 15V rail, DC-bias derating flag (see §1.1 note) |

---

## 3. Microcontroller

### 3.1 ESP32-S3 Module

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| U_MCU | WiFi+BLE SoC Module | ESP32-S3-WROOM-1-N8R8 | Espressif | 1 | Module | 8MB Flash + 8MB PSRAM |
| C_VCC1 | Decoupling | C0603C104K5RACTU | KEMET | 1 | 0603 | 100nF 50V X7R — MPN fixed 2026-07-26 |
| C_VCC2 | Bulk Capacitor | GRM21BR71A106KE51L | Murata | 1 | 0805 | 10µF 10V X5R |
| R_EN | EN Pull-Up | RC0603FR-0710KL | Yageo | 1 | 0603 | 10kΩ 2% — boot-timing RC with C_EN |
| C_EN | EN Timing Cap | GRM188R71A105KA61D | Murata | 1 | 0603 | 1µF 2% 10V |
| R_BOOT | IO0 Boot Pull-Up | RC0603FR-0710KL | Yageo | 1 | 0603 | 10kΩ |
| R_SDA_PULLUP, R_SCL_PULLUP | I2C Pull-Ups | RC0603FR-074K7L | Yageo | 2 | 0603 | 4.7kΩ — direct MCU pull-ups, no isolator (see §4.2) |

> **`U_MCU` corrected**: source uses the N8R8 variant (8MB flash + 8MB PSRAM), not N4 (4MB, no PSRAM) — cost/lead-time material, not electrical.
>
> **Decoupling restructured.** The previous "`C_DEC_MCU` ×4 100nF" / "`C_BULK_MCU` ×1 10µF" rows used MPNs (`GRM188R71H104KA93D`, `GRM188R61E106MA73D`) that do not appear anywhere in source, and the quantities did not match the real instance count. `MCU` (`modules.ato:2219-2372`) has exactly one 100nF cap (`c_vcc1`) and one 10µF cap (`c_vcc2`, different MPN/package than previously listed), plus a separate 1µF EN-timing cap (`c_en`) that was missing entirely.
>
> `R_EN`, `C_EN`, `R_BOOT` were wired but uncosted (Class B — boot/reset RC network, part of the audit's "Fan header + dropper, MCU EN/BOOT RC + boot button" group). `BTN_RESET`/`BTN_BOOT` are listed under §7.2 Controls. `R_SDA_PULLUP`/`R_SCL_PULLUP` MPN was already correct; quantity corrected from 4 to 2 (see §4.2).

---

## 4. Sensing and Interfaces

### 4.1 Temperature Sensing (RTD)

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| U_RTD | RTD-to-Digital | MAX31865AAP+ | Analog Devices | 1 | SSOP-20 | SPI, PT100/PT1000 |
| R_REF | Reference Resistor | ERA-6AEB431V | Panasonic | 1 | 0805 | 430Ω 0.1% (PT100) |
| C_DEC_RTD | Decoupling (IC/rail) | C0603C104K5RACTU | KEMET | 7 | 0603 | 100nF 50V X7R — MPN fixed 2026-07-26; one per: VDD (post-ferrite), reference, low/high-window comparators, window-AND, rail monitor, fault-NAND |
| R_SCLK, R_MOSI, R_CS, R_MISO | SPI EMI Filter | RC0603FR-0733RL | Yageo | 4 | 0603 | 33Ω 5% |
| FB_POWER | Power Ferrite Bead | BLM18AG121SN1D | Murata | 1 | 0603 | ~120Ω @ 100MHz |

> **`U_RTD` corrected**: 1 instance, not 2 — only `rtd_pan` (pan RTD) is wired (`main.ato:135`); there is no second `RTDSensing` instance for a second channel. MPN corrected to `MAX31865AAP+` (SSOP-20) — the `MAX31865ATP+` (TQFN-20) this BOM listed was a deliberate fix in source to match the actual footprint (`components.ato:358-361`: "SSOP-20 package, matches footprint (TQFN→SSOP fix)").
>
> **`R_REF` corrected**: 1 instance (there is only one RTD channel), package is 0805 (`ERA-6AEB431V`), not 0603.
>
> **`C_DEC_RTD` corrected**: 7 instances at 100nF/0603/`GRM188R71E104KA01D`, not 2 at an MPN (`GRM188R71H104KA93D`) that doesn't exist in source.
>
> `R_SCLK/MOSI/CS/MISO` and `FB_POWER` were wired (SPI EMI filtering + ferrite noise rejection, `modules.ato:1302-1330`) but entirely uncosted (Class B).

### 4.2 I2C Isolator — NOT IN SOURCE

**No parts.** `components.ato:51-54`: "ADUM1250 I2C isolator no longer needed for RTD isolation; the isolation barrier is between the HV power domain and the SELV control domain (Option A, plan 003)." Isolation is provided by the `AuxSupply` transformer (§2.3), not an I2C isolator. Removed: `U_ISO` (ADUM1250ARZ). The I2C pull-ups this section carried are retained at the corrected quantity of 2 (not 4 — one side, not an isolator's two) under §3.1, matching `MCU.r_sda_pullup`/`r_scl_pullup`.

### 4.3 Current Transformer

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| CT1 | Current Transformer | CST3015-100ED | Coilcraft | 1 | SMD | 1:100, senses to 88A, 5000Vrms reinforced, ≥8mm creepage |
| R_BURDEN | Burden Resistor | RC1206FR-074R99L | Yageo | 1 | 1206 | 4.99Ω 1% 1/4W — OCP trip 50.1A |

> **OCP-01 resolved 2026-07-25.** Trip is 50.121 A simulated (worst case
> 49.4–50.9 A over ±1% parts), inside the 45–55 A requirement.
>
> This needed a transformer change, not just a burden change. The previous
> `CST2010-100L` senses only to 47 A, so no burden value satisfied both the
> spec and the part — above 47 A the core saturates and the secondary
> under-reads, meaning the comparator could trip late or not at all.
> `CST3015-100ED` keeps the 1:100 ratio (so the burden math carries over) and
> raises the sensed rating to 88 A, leaving 1.73× worst-case headroom.
> Verified against Coilcraft Document 1608-1; volt-time margin at the trip is
> 18×. Isolation also improves from 1500 Vrms to 5000 Vrms reinforced with
> ≥8 mm creepage, which helps the IEC 60335-1 position.
>
> **Footprint drawn 2026-07-26.** `temper:CST3015` built from the official
> Recommended Land Pattern (Coilcraft Document 1608-2): primary pads
> 9.0 × 4.8 mm on 15.36 mm centres, secondary 3.0 × 4.6 mm on 13.76 mm centres.
> Dimensionally cross-verified — the secondary geometry reproduces the
> component drawing's independent 13.76 mm span exactly.
>
> **⚠ Still requires board re-layout.** The CST3015 body is 23.0 × 30.0 mm
> against the CST2010's 13.0 × 14.55 mm, so T1's surroundings must be
> re-placed. **Open the footprint in KiCad and check it against the datasheet
> before fabrication** — it has not been visually confirmed in the KiCad
> footprint editor.
>
> Earlier entries here specified `CST-1005` (1:1000) with a 66.5 Ω burden — the
> superseded design point. `CST-1005` was retired in commit `5a58b397`
> (5 A, 50/60 Hz only, 65 °C max).

### 4.4 Redundant Overcurrent Protection (OCP-02) — **DE-SCOPED 2026-08-16 (DNF)**

**No parts costed, deliberately.** OCP-02 is **de-scoped** as of 2026-08-16 (decision record:
`docs/evidence/2026-08-16-ocp02-descope-implementation.md`; recommendation:
`docs/evidence/2026-08-16-cert-lab-and-ocp02-spike.md` Part 2, on main). Its three parts —
**T2** (Coilcraft CST3015-100ED CT, `safety.ocp2.ct`), **R65** (4.12Ω burden, RC1206),
**C37** (0603 filter) — remain **staged off-board at (100.0, 300.0) / (44.0, 272.12) /
(20.0, 272.12)** on `pcb/temper.kicad_pcb` and are **DNF (do not fit): do not populate, do not
place, do not cost**. The design is instantiated and wired in `elec/src/modules.ato`
(`SecondaryOCPComparator`, Option A second CT, 2026-08-07) and is deliberately kept there so the
interface survives for the aperture-CT reinstatement path — but nothing on the board or in this
BOM is to be built from it.

**Why (one line):** the CST3015's 9.100mm intrinsic primary↔secondary creepage cannot reach the
12.6mm PD3 reinforced bar in any placement (the same defect already sits on the board in T1), and
every alternative sensing mechanism (Hall ICs 4.0–4.2mm, AMC1301 isolated amp 8.5mm, other CTs
≤9.1mm) fails it too with datasheet-verified figures. OCP-02 is not IEC 60335-1 clause-mandated;
OCP-01 (50.1A hardware comparator + 40A firmware layer) remains the primary protection.

**History, so this section reads correctly:** the original OCP-02 design (shunt + INA240 + LM393,
`docs/hardware/OCP02_DESIGN.md`) was superseded 2026-08-07 by Option A — a second current
transformer — because `DC_BUS_RTN` sits ~170V below signal ground (`power_return`/`gnd` are the
doubler midpoint, `main.ato:247,283`), putting ~170V common-mode across the INA240's −4V to +80V
absolute rating. `R_SHUNT` (WSLP25122L000FEA), `U_DIFF` (INA240A1QPWRQ1) and `U_COMP2` (LM393DR)
are removed from this BOM and **must not be added back** — the CT design they belonged to was
superseded before the parts were ever placed. Reinstatement triggers (all conditions in the
decision record): a verified reinforced-insulation certificate for an aperture/donut CT, a
cert-lab "yes" on slot closed-end creepage credit, or a real sealed PD2 compartment.

### 4.5 CT Signal Conditioning (Bias + Filter)

**Added 2026-07-26 — uncosted.** Sets the CT output's 1.65V mid-rail bias for its bipolar secondary signal and filters the sense line (`modules.ato:1222-1254`).

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| C_CT_FILT | CT Signal Filter Cap | GRM1885C1H104JA01D | Murata | 1 | 0603 | 100nF C0G 16V |
| R_BIAS_TOP, R_BIAS_BOT | CT Bias Divider | RC0603FR-0710KL | Yageo | 2 | 0603 | 10kΩ 1% — sets the 1.65V mid-rail for the bipolar CT output |

### 4.6 RTD Hardware-Window Fault Chain

**Added 2026-07-26 — 15 parts, entirely uncosted (Class B, High).** `RTDSensing` (`modules.ato:1413-1511`) includes an independent hardware comparator window that faults if the RTD sense voltage falls outside a defined band, or if the post-ferrite `RTD_AVDD` rail browns out. This is separate from, and does not depend on, the MCU's firmware-side RTD fault handling. (Combined with the RTD decoupling/SPI-filter/ferrite additions in §4.1, this and §4.5 together add ~24 previously-uncosted RTD/CT-side components, in line with the audit's "~25 parts" estimate.)

> **Corrected 2026-08-07: this is NOT UVL-02.** This section was previously titled "UVL-02 candidate" — an earlier, since-rejected identification. `RTDSensing.rail_monitor` (the `TPS3700` in this chain) trips at a simulated 2.825V with no added hysteresis resistor and monitors `RTD_AVDD` (a downstream RTD-subsystem rail), not the board's own 3.3V logic supply — its own module docstring states plainly it is "Not UVL-02." The real UVL-02 gate is `LogicUVLOComparator`, a wholly separate, previously entirely-uncosted circuit — see the new §5.9 below.

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| U_RTD_REF | Precision Reference | REF2025AIDDCR | Texas Instruments | 1 | SOT-23-5 | 2.5V/1.25V — runs off upstream 3.3V so it stays defined through an RTD_AVDD brownout |
| U_RTD_LOW_WIN | Low-Window Comparator | TLV3201AIDBVR | Texas Instruments | 1 | SOT-23-5 | |
| U_RTD_HIGH_WIN | High-Window Comparator | TLV3201AIDBVR | Texas Instruments | 1 | SOT-23-5 | |
| U_RTD_WIN_AND | Window AND Gate | SN74LVC1G08DBVR | Texas Instruments | 1 | SOT-23-5 | Combines low/high window outputs |
| U_RTD_RAIL_MON | RTD_AVDD Rail Monitor | TPS3700DDCR | Texas Instruments | 1 | SOT-23-6 | Dual window supervisor; OUTA low on undervoltage |
| U_RTD_FAULT_NAND | Fault-Combining NAND | SN74LVC1G38DBVR | Texas Instruments | 1 | SOT-23-5 | Open-drain, Ioff-rated — only device allowed to hold RTD_HW_FAULT low |
| R_RTD_LOW_TOP | Low-Window Divider High | ERA-3AEB6192V | Panasonic | 1 | 0603 | 61.9kΩ 0.1% (2026-07-27: corrected from fabricated 61.3kΩ/ERA-3AEB6132V, not an E96/E192 value and MPN not real) |
| R_RTD_LOW_BOT, R_RTD_HIGH_BOT | Window Divider Low (both) | ERA-3AEB103V | Panasonic | 2 | 0603 | 10kΩ 0.1% |
| R_RTD_HIGH_TOP | High-Window Divider High | ERA-3AEB5901V | Panasonic | 1 | 0603 | 5.9kΩ 0.1% (2026-07-27: corrected from fabricated 5.93kΩ/ERA-3AEB5931V, not an E96/E192 value and MPN not real; out of stock at DigiKey, 33wk lead time, see evidence doc) |
| R_RTD_WIN_PULLDOWN | Window-AND Output Pulldown | RC0603FR-07100KL | Yageo | 1 | 0603 | 100kΩ 1% |
| R_RTD_AVDD_TOP | Rail-Monitor Divider High | ERA-6AEB6193V | Panasonic | 1 | 0805 | 619kΩ 0.1% (2026-07-27: corrected from fabricated 616kΩ/ERA-3AEB6163V, not an E96/E192 value, MPN not real, and above ERA-3A/0603's stocked range; package changed 0603→0805 to match the real ERA-6A part) |
| R_RTD_AVDD_BOT | Rail-Monitor Divider Low | ERA-3AEB104V | Panasonic | 1 | 0603 | 100kΩ 0.1% |
| R_RTD_RAIL_PULLUP, R_RTD_FAULT_PULLUP | Open-Drain Pull-Ups | RC0603FR-0710KL | Yageo | 2 | 0603 | 10kΩ 1% |

---

## 5. Safety Interlock System

### 5.1 Comparators

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| U_OCP | OCP Comparator | TLV3201AIDBVR | Texas Instruments | 1 | SOT-23-5 | 40ns prop delay — OCP-01 |
| U_OVP | OVP Comparator | TLV3201AIDBVR | Texas Instruments | 1 | SOT-23-5 | 40ns prop delay — OVP-01 |
| U_THERMAL | Thermal Comparator | TLV3201AIDBVR | Texas Instruments | 1 | SOT-23-5 | With hysteresis — THM-01 (heatsink), see §5.7 |
| U_THERMAL2 | Coil Thermal Comparator | TLV3201AIDBVR | Texas Instruments | 1 | SOT-23-5 | With hysteresis — THM-02 (coil), see §5.8 |

> Two further `TLV3201AIDBVR` instances (`U_RTD_LOW_WIN`, `U_RTD_HIGH_WIN`) live in the RTD hardware-window chain, §4.6. Source instantiates 6 total (`grep -c "new TLV3201" elec/src/modules.ato`); this BOM now accounts for all 6, up from the 3 previously costed.

### 5.2 Logic ICs

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| U_OR1, U_OR2, U_OR3 | Triple 3-Input OR | SN74HC4075DR | Texas Instruments | 3 | SOIC-14 | Base fault combining (`fault_or`) + fault-any aggregation (`fault_any_or`) + UVLO-02 fan-in capacity (`fault_or3`, added 2026-07-27, see note) |
| U_NAND | Quad 2-Input NAND | SN74HC00DR | Texas Instruments | 1 | SOIC-14 | SR latch (`latch`) |

> **MPN/manufacturer corrected.** Source uses TI `SN74HC4075DR`/`SN74HC00DR`, not the Nexperia `74HC4075D`/`74HC00D` this BOM previously listed — different manufacturer and different exact part number (reel suffix).
>
> **Quantity corrected 2026-07-26**: source instantiates *two* `SN74HC4075` packages (`fault_or` and `fault_any_or`, `modules.ato:2089-2090`), not one — the second combines the RTD hardware fault and reset-qualification logic.
>
> **Quantity corrected again 2026-08-07 — `U_OR3` added.** Source instantiates a *third* `SN74HC4075` package, `fault_or3` (`modules.ato:3073`), added 2026-07-27 for UVLO-02's fault fan-in: by the time `LogicUVLOComparator` was designed, THM-02 already occupied the one spare input in `fault_any_or`, and no other input reached `fault_any_or.Y1 → latch.A1` without a further OR stage. This row had no BOM entry at all before this pass. See `docs/hardware/UVL02_DESIGN.md` §7.1 and `docs/evidence/2026-07-27-fault-tree-capacity-expansion.md`.
>
> **`U_AND` (74HC08D) and `U_INV` (74HC04D) removed** — zero hits for `74HC08\|74HC04` anywhere in `elec/src/*.ato`. The latch is built entirely from the OR packages above plus the one NAND package.

### 5.3 Hardware Watchdog

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| U_WDT | Watchdog Timer | TPS3823-33DBVR | Texas Instruments | 1 | SOT-23-5 | 1.6s timeout |
| C_WDT | Decoupling | C0603C104K5RACTU | KEMET | 1 | 0603 | 100nF 50V X7R — MPN fixed 2026-07-26 |

> **`C_WDT` corrected**: source (`modules.ato:2001-2005`) uses the same 0603/10V/X7R part as the board's other 100nF rails, not the 0402/50V `GRM155R71H104KE14D` this BOM previously listed.

### 5.4 IGBT Desaturation Protection — DE-SCOPED 2026-07-26

**No parts. This section previously costed 19 line items for a circuit that
was never designed** — `grep -ni desat elec/src/*.ato` returns nothing.
Removed: `D_DESAT_HS/LS`, `R_DESAT1_HS/LS`, `C_BLANK_HS/LS`, `R_DIV1_HS/LS`,
`R_DIV2_HS/LS`, `D_TVS_HS/LS`, `C_FILT_HS/LS`, `U_DESAT`, `R_REF1`, `R_REF2`,
`R_PULL_HS/LS`.

**Why it cannot simply be built:** the `UCC21550` gate driver in use has no
DESAT pin, and neither does the `UCC21551` that
`docs/hardware/IGBT_DESATURATION_PROTECTION.md` proposes as an upgrade path.
(The `UCC21553` that document also names is not a real TI part.) DESAT-capable
TI drivers are a different single-channel architecture, so adopting one is a
gate-drive redesign, not a part swap. Full analysis:
`docs/hardware/DESAT_DECISION_BRIEF.md`.

**Accepted residual risk.** OCP-01 (50.1 A, tank CT) and OCP-02 (60 A, bus
shunt, designed) cover most of the same fault space. They do **not** cover:

| Uncovered fault | Why current sensing misses it |
|---|---|
| Shoot-through | Both switches on together shorts the bus through the devices; current may never reach the sense element |
| Gate-drive failure | A sagging gate partially turns the IGBT on and it dissipates enormously while current still reads normal |
| Short at the device | May bypass where current is measured |
| Response speed | A hard short can destroy an IGBT faster than shunt → amp → comparator → logic responds |

This is a **deliberate scope decision recorded as risk**, not an oversight. A
redesign spike is open. If DESAT is reinstated, restore these parts from
git history rather than re-deriving them.

### 5.5 OCP Reference Divider

**Added 2026-07-26 — uncosted.** Sets the OCP-01 comparator's 2.5V trip reference (`modules.ato:1526-1541`), corresponding to the 50.1A trip point derived in §4.3.

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| R_OCP_REF_T | OCP Reference Divider High | RC0603FR-073K24L | Yageo | 1 | 0603 | 3.24kΩ 1% — corrected 2026-08-07, see note |
| R_OCP_REF_B | OCP Reference Divider Low | RC0603FR-0710KL | Yageo | 1 | 0603 | 10kΩ 1% |

> **`R_OCP_REF_T` corrected 2026-08-07 (fabricated MPN).** `RC0603FR-073K2L` (3.2kΩ) was never a real part: 3.2kΩ is not an E24 or E96 value (nearest E96 neighbours 3.16k/3.24k), the MPN encodes the same invented "3K2" figure, and it returns zero DigiKey hits. Source (`modules.ato:2113-2116`) uses the real E96 neighbour 3.24kΩ, `RC0603FR-073K24L` — DigiKey-confirmed, chosen over the other E96 neighbour (3.16k) because it centres the nominal trip closer to the 45-55A window's 50.0A midpoint. Nominal trip: `V_ref = 3.3 × 10000/13240 = 2.492V`; `I_trip = V_ref × 100 / r_burden = 2.492 × 100 / 4.99Ω ≈ 49.95A`, inside the 45-55A window. Worst-case (±1% tol + ±100ppm/°C tempco, ΔT=60°C) on `r_ref_top`/`r_ref_bot`/`r_burden`: 48.77-51.16A. See `docs/evidence/2026-07-27-ocp01-uvl02-part-resolution.md`.

### 5.6 OVP Voltage Divider

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| R_OVP1, R_OVP2, R_OVP3 | HV Sense Divider High | RC1206FR-07430KL | Yageo | 3 | 1206 | 430kΩ 1% 0.25W — protective-impedance chain, 3 in series (matches source `r_div_top1/2/3`) |
| R_OVP_DIV_BOT | HV Sense Divider Low | RT0603BRD0716K9L | Yageo | 1 | 0603 | 16.9kΩ 0.1% — re-derived 2026-07-27 for the fixed REF2025 reference, replaces the previous R_OVP4/10kΩ divider-referenced design, see note |
| R_OVP_HYST | OVP-01 Hysteresis Feedback | RT0603BRD07487KL | Yageo | 1 | 0603 | 487kΩ 0.1% — positive feedback from comp.OUT to the bus-sense node, sets ~8.7V hysteresis (5-10V window). New row 2026-08-07 — this resistor previously had no BOM entry at all, see note |
| R_OVP_ADC_T1, R_OVP_ADC_T2, R_OVP_ADC_T3 | MCU ADC Tap Divider High | RC1206FR-07169KL | Yageo | 3 | 1206 | 169kΩ 1% 0.25W 200V — split from a single 510kΩ resistor 2026-07-26 for protective-impedance fault tolerance, replaces R_OVP_ADC_T, see note |
| R_OVP_ADC_B | MCU ADC Tap Divider Low | RC0603FR-0710KL | Yageo | 1 | 0603 | 10kΩ 1% 0.1W |
| C_OVP_ADC | ADC Tap Filter Cap | C0603C104K5RACTU | KEMET | 1 | 0603 | 100nF 50V X7R — MPN fixed 2026-07-26 |

> **Divider values corrected 2026-07-26.** `R_OVP1-3` previously read 1MΩ (ratio ≈1/101, implying a ~195V bus-half trip). Source (`modules.ato:2251-2270`) uses 430kΩ×3 (ratio corrected against the divider bottom leg below), matching the comparator reference to trip at ~200V (195-205V window, OVP-01). This was flagged Critical/material in the 2026-07-25 audit and had not yet been applied to this BOM — it is fixed in this pass. `R_OVP1/2/3` alias `elec/src/modules.ato`'s `r_div_top1/r_div_top2/r_div_top3` — same value/MPN, different label; see `bom-reconciliation-allowlist.yaml`.
>
> **`R_OVP4`/`R_OVP_REF_T`/`R_OVP_REF_B`/`R_OVP_ADC_T` corrected 2026-08-07 (Option C re-reference, `docs/evidence/2026-07-27-ovp01-ref2025-implementation.md`).** The divider-referenced design (a `r_ref_top`/`r_ref_bot` divider off `power.vcc`, corresponding to the old `R_OVP_REF_T`/`R_OVP_REF_B` rows) failed worst-case-tolerance-only analysis (193.9-206.2V against the 195-205V window) before tempco was even considered — see `docs/evidence/2026-07-27-ovp01-half-bus-retune.md`. It was **deleted outright**: `comp.INN` is now driven directly by `RTDSensing`'s REF2025 fixed 2.5V reference (already costed as `U_RTD_REF`, §4.6) via `vref_ext`, an unpopulated signal net, not a new part. `R_OVP4` (10kΩ) is replaced by `R_OVP_DIV_BOT` (16.9kΩ, `r_div_bot` in source), re-derived for the new 2.5V reference: `V_trip = Vref × (1 + Rtop/r_div_bot + Rtop/r_hyst) = 2.5 × (77.331 + 1290000/487000) ≈ 199.95V`, centred in the 195-205V window. `R_OVP_ADC_T` (a single 510kΩ resistor) is replaced by `R_OVP_ADC_T1/2/3` (3× 169kΩ, source `r_adc_top1/2/3`): a single top resistor is not a valid IEC 60335-1 protective-impedance construction — shorting the one resistor dumps the full +170V bus across `R_OVP_ADC_B` alone (~29× its power rating, ~13× the touch-current limit); losing any one of three 169kΩ resistors still leaves 338k or 169k of top-side impedance. `R_OVP_ADC_B`/`C_OVP_ADC` are unchanged (the ADC tap's bottom leg was not touched by the top-leg split).
>
> **`R_OVP_HYST` added 2026-08-07 — new gap, not previously flagged.** Source's `r_hyst` (487kΩ, `modules.ato:2366-2371`) provides OVP-01's hysteresis feedback (comp.OUT → the bus-sense node) and had **no BOM.md row at all**, old or new — a genuine uncosted gap this pass found, distinct from the R_OVP_REF_T/B deletion above. Worst-case corner sweep (64 corners over all 6 error sources, tolerance + tempco at ΔT=60°C): trip 196.11-203.81V, hysteresis 8.58-8.90V, both clearing the 195-205V/5-10V windows with margin.

### 5.7 Thermal Protection (THM-01, Heatsink)

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| NTC_HS | NTC Thermistor (heatsink) | NTCALUG01A104GA | Vishay BCcomponents | 1 | M3 lug | 100kΩ @ 25°C, B25/85=4190K, 1500VAC isolation |
| R_NTC_PU | NTC Divider Fixed | RC0603FR-0710KL | Yageo | 1 | 0603 | 10kΩ 1% — matches R_NTC at the 85°C trip |
| R_THM_REF_T | Thermal Ref Divider High | RC0603FR-079K09L | Yageo | 1 | 0603 | 9.09kΩ 1% |
| R_THM_REF_B | Thermal Ref Divider Low | RC0603FR-0711K5L | Yageo | 1 | 0603 | 11.5kΩ 1% |
| R_THM_HYST | Thermal Hysteresis | RC0603FR-0734K8L | Yageo | 1 | 0603 | 34.8kΩ 1% — 15.2°C hysteresis |

> **Divider values corrected 2026-08-07.** This BOM's costed values (9.53k/10k/100k) were byte-for-byte the divider superseded by commit `a4fb15dc` (2026-07-26, "add the hysteresis three gates actually specify") — a functional deficiency, not a naming lag: at those values the trip/release pair gives only **5.6°C** of hysteresis against the FUNCTIONAL_TEST_CRITERIA §2.3 requirement of **15°C**, a real risk of chatter right at the 85°C trip threshold instead of a clean latch-until-cooldown. Source's current divider (9.09k/11.5k/34.8k) gives 85.0°C trip / 69.8°C release, i.e. 15.2°C of hysteresis — independently re-derived here from the divider equations and the NTC's own R-T curve (R25=100k, B25/85=4190K), confirming the module docstring's figures. See commit `a4fb15dc` for the full E96 two-constraint derivation (no separate evidence doc exists for this commit).
>
> **THM-01 trip point corrected 2026-07-25.** Trips at 84.91 °C (simulated), against the
> 85 °C requirement. Previously 99.47 °C.
>
> The thermistor entry was wrong: this listed `NCU18XH103F6SRB` (10 kΩ, B=3950)
> while the source has used `NTCALUG01A104GA` (100 kΩ, B=4190, marked
> "VERIFIED 2026-07-16") — a different resistance decade *and* a different beta.
> The three divider resistors were absent from this BOM entirely.
>
> Re-verified 2026-07-26 (predates commit `a4fb15dc`'s same-day hysteresis fix, and was never re-checked against it — see the divider-values note above): this subsection's parts and values matched source at the time, but the reference/hysteresis divider drifted stale again the same day and has now been corrected. **THM-02 (coil NTC, 120°C) now has a circuit** — see §5.8. It did not when this note was first written.

### 5.8 Coil Thermal Protection (THM-02)

**Designed and added to source 2026-07-26** (`CoilThermalComparator`, `modules.ato:1759-1849`) — this gate previously had no circuit at all, as recorded in the §5.7 note above at the time it was written.

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| NTC_COIL | NTC Thermistor (coil) | NTCALUG01A104GA | Vishay BCcomponents | 1 | Axial DIN0207 | 100kΩ @ 25°C, B25/85=4190K — same part family as NTC_HS; source gives this instance a plain axial footprint, not the M3-lug pattern used for NTC_HS |
| R_NTC2_PU | NTC Divider Fixed | RC0603FR-073K32L | Yageo | 1 | 0603 | 3.32kΩ 1% — matches R_NTC at the 120°C trip |
| R_THM2_REF_T | Thermal Ref Divider High | RC0603FR-073K16L | Yageo | 1 | 0603 | 3.16kΩ 1% |
| R_THM2_REF_B | Thermal Ref Divider Low | RC0603FR-074K42L | Yageo | 1 | 0603 | 4.42kΩ 1% |
| R_THM2_HYST | Thermal Hysteresis | RC0603FR-0711K5L | Yageo | 1 | 0603 | 11.5kΩ 1% — 19.9°C hysteresis |

> **Divider values corrected 2026-08-07.** This BOM's costed values (9.09k/10k/100k, THM-02's own first-revision values) were superseded by commit `a4fb15dc` (2026-07-26): only 6.6°C of hysteresis against the FUNCTIONAL_TEST_CRITERIA §2.3 requirement of 20°C. Source's current divider (3.16k/4.42k/11.5k) gives 120.0°C trip / 100.1°C release, i.e. 19.9°C of hysteresis — independently re-derived here from the divider equations and the NTC's own R-T curve (R_ntc_fixed=3.32k, R25=100k, B25/85=4190K), confirming the module docstring's figures exactly. See commit `a4fb15dc`.

Trips at 120.3°C (simulated), releasing at 100.1°C (was 113.7°C against the pre-`a4fb15dc` divider — the trip point was already correct; only the release/hysteresis value changes with this correction). Comparator is `U_THERMAL2` (§5.1). The fault feeds `fault_any_or` on a previously-spare gate input, so THM-02 costs no additional logic IC.

> **Sensor rating caveat, from source's own docstring:** `NTCALUG01A104GA` is rated to +125°C and this gate trips at 120.3°C — within 5°C of the sensor's maximum. Confirm the part is acceptable for sustained coil-adjacent service, or select a higher-temperature variant, before fabrication.

### 5.9 Logic UVLO (UVLO-02)

**Added 2026-08-07 — 6 parts, entirely uncosted until now.** `LogicUVLOComparator` (`modules.ato:2815-2985`) is the actual UVL-02 gate (logic-rail/3.3V under-voltage lockout, FUNCTIONAL_TEST_CRITERIA §2.4: trip <2.9V falling, recover >3.0V rising, >100mV hysteresis). Two pre-existing candidates were checked and rejected before this module was designed: the watchdog's `TPS3823-33` brownout comparator (fixed silicon, cannot deliver the required hysteresis) and `RTDSensing.rail_monitor` (monitors `RTD_AVDD`, not the logic rail — see the corrected §4.6 note above). This module had **zero BOM rows** before this pass, despite being wired into the fault interlock since 2026-07-27 (`fault_or3` below).

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| U_UVLO2 | Logic UVLO Supervisor | TPS3700DDCR | Texas Instruments | 1 | SOT-23-6 | `mon` — VDD wired directly across power_3v3, external divider sets an absolute trip point off the internal ~394.5mV bandgap reference |
| R_UVLO2_DIV_TOP | UVLO Divider High | RC0603FR-07698KL | Yageo | 1 | 0603 | 698kΩ 1% |
| R_UVLO2_DIV_BOT | UVLO Divider Low | RC0603FR-07100KL | Yageo | 1 | 0603 | 100kΩ 1% |
| R_UVLO2_HYST | UVLO Hysteresis | RC0603FR-073M74L | Yageo | 1 | 0603 | 3.74MΩ 1% — positive feedback from OUTA to the sense node |
| R_UVLO2_OUTA_PULLUP | OUTA Open-Drain Pull-Up | RC0603FR-0710KL | Yageo | 1 | 0603 | 10kΩ 1% |
| U_UVLO2_INV | Active-Low-to-High Inverter | SN74LVC1G38DBVR | Texas Instruments | 1 | SOT-23-5 | Open-drain (`inv`); its own pull-up is a 10kΩ `r_fault_pullup` instance at `modules.ato:2979`, same reused variable name as (but a physically separate part from) the RTD chain's `R_RTD_FAULT_PULLUP` (§4.6). Not one of the 49 gate findings this pass fixes (confirmed against a live gate run — see `docs/hardware/BOM_RECONCILIATION_PROPOSAL.md` §3's `r_fault_pullup` correction note); left as a documentation gap for a follow-up, not added as a numbered row here. |

Nominal (698k/100k/3.74M): trip 2.715V, recover 3.222V, 0.507V (15.4%) hysteresis. Worst-case (each resistor ±1%, VIT_A over its full datasheet range): trip ≤2.800V (100mV margin under the 2.9V ceiling), recover ≥3.106V (106mV margin over the 3.0V floor). See `docs/hardware/UVL02_DESIGN.md` and `docs/evidence/2026-07-27-ocp01-uvl02-part-resolution.md`.

`fault_or3` (the third `SN74HC4075` triple-OR package that fans this fault into the interlock, added 2026-07-27) is costed as `U_OR3` in §5.2. `tp_uvlo2_fault` (bench probe point) is costed as `TP3` in §10.2.

---

## 6. Precision Rectifier (OCP) — NOT IN SOURCE

**No parts.** No `LM358` or `1N4148` appears anywhere in `elec/src/*.ato` (`grep -rn "LM358\|1N4148" elec/src/*.ato` returns nothing). There is no precision-rectifier stage feeding either OCP path in the current design. Removed: `U_RECT` (LM358DR), `D_RECT1-4` (1N4148WS).

---

## 7. User Interface

### 7.1 Indicators — NOT IN SOURCE

**No parts.** `modules.ato` declares `ocp_led`/`ovp_led`/`thermal_led`/`wdt_led` signals in `SafetyInterlock` but they terminate nowhere: "LED indicators remain unassigned until their current-limiting circuits are specified; they must not be used as safety logic" (`modules.ato:2216-2217`). No `LED` component type exists in `components.ato` at all. Removed: `LED_OCP`, `LED_OVP`, `LED_THERMAL`, `LED_WDT`, `LED_MASTER`, `R_LED`.

### 7.2 Controls

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| BTN_RESET | EN Reset Button | EVQ-P7A01P | Panasonic | 1 | 0603 footprint (placeholder) | Parallel to EN RC; pulls EN low to reset |
| BTN_BOOT | Boot/Download Button | EVQ-P7A01P | Panasonic | 1 | 0603 footprint (placeholder) | Pulls IO0 low for download mode |

> **`S_RESET` replaced.** The previous "Momentary NO / Panel mount" placeholder didn't match any source part. Source (`components.ato:683-696`) wires two board-mount tactile buttons (`EVQ-P7A01P`) directly to MCU pins, on a placeholder 0603 footprint pending a real tactile-switch footprint in the fp-lib-table (source's own comment: swap to something like `SW_SPST_B3U-1000P` once available). These are board-mount buttons, not panel-mount user controls.

---

## 8. PWM Interface Filter

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| R_PWM_A, R_PWM_B | Series Resistor | RC0603FR-0751RL | Yageo | 2 | 0603 | 51Ω 5% |
| C_PWM_A, C_PWM_B | Filter Capacitor | GRM1885C1H221JA01D | Murata | 2 | 0603 | 220pF 5% C0G 50V |

> **`C_PWM_A/B` corrected**: 220pF, not 33pF — a 6.7× value change (`modules.ato:115-125`). `R_PWM_A/B` was already correct. This filter sits on the two `UCC21550` input channels (`INA`/`INB`, i.e. `PWM_H` and `PWM_L`) inside `GateDriveHS` — the driver's only instance of each — not a separate ADC-side filter. (These are `r_filt_a/b`/`c_filt_a/b` referenced from §1.1; listed here only, to avoid double-counting.)

---

## 9. Anti-Aliasing Filter (ADC) — NOT IN SOURCE

**No parts.** None of the three ADC inputs (`mcu.adc_i_sense`/`adc_v_bus`/`adc_ntc`, fed respectively by `ct_sense.i_sense`, `safety.ovp.adc_v_bus`, `safety.ntc_sense`) has a dedicated anti-aliasing stage in `elec/src/*.ato` — no `1.6nF` value and no `R_AA`/`C_AA`-equivalent pair exists on any of them. (The CT path has its own, unrelated `C_CT_FILT` 100nF C0G filter — §4.5 — a different filter with a different purpose and value.) Removed: `R_AA`, `C_AA`.

---

## 10. Miscellaneous

### 10.1 Decoupling and Bypass — ITEMIZED ELSEWHERE

**No generic bucket.** Every 100nF/0603 (`C0603C104K5RACTU` since 2026-07-26, was `GRM188R71E104KA01D` — Obsolete/0-stock, see §1.1; 16 instances) and 10µF-class decoupling/bulk capacitor in source is now listed against its actual instance under the relevant functional section (§1.1, §2.1, §2.3, §3.1, §4.1, §5.3, §5.6) rather than as a generic quantity bucket. The previous `C_DEC ×20` / `C_BULK ×5` rows used MPNs (`GRM188R71H104KA93D`, `GRM188R61E106MA73D`) that do not appear anywhere in `elec/src/*.ato`, and their quantities did not match the real per-instance count (16 × 100nF; three distinct 10µF-class parts with three different MPNs/ratings — see §2.1 `C_IN`, §2.3 `C_OUT`, §3.1 `C_VCC2`).

### 10.2 Test Points

`components.ato:717` marks `TestPoint.bom_exclude = true` — these are not meant to be procured as BOM line items; listed here for rework/bring-up reference only, not for ordering. Source instantiates exactly 3 (`SafetyInterlock.tp_shutdown`, `SafetyInterlock.tp_fault`, `SafetyInterlock.tp_uvlo2_fault`), not the 5 originally listed nor the 2 counted 2026-07-25.

| Ref | Description | Part Number | Manufacturer | Qty | Notes |
|-----|-------------|-------------|--------------|-----|-------|
| TP1 | SHUTDOWN test point | GENERIC_TEST_POINT | - | 1 | `safety.tp_shutdown` — latched shutdown output to gate-driver DIS |
| TP2 | FAULT_STATUS test point | GENERIC_TEST_POINT | - | 1 | `safety.tp_fault` — latch Q output to MCU |
| TP3 | UVLO2_FAULT test point | GENERIC_TEST_POINT | - | 1 | `safety.tp_uvlo2_fault` (`modules.ato:3227`) — UVLO-02 bench probe point, added 2026-08-07. A different, newer instance than the originally-removed `TP3` (`GATE_DISABLE`) below, which reuses the same ref label for an unrelated net. |

Removed: the original `TP3` (`GATE_DISABLE`), `TP4` (`V_BOOT`), `TP5` (`SW_NODE`) — no corresponding `TestPoint` instances exist in source for these nets.

---

## 11. Mechanical & Thermal

**PCB-side fan interface** (these two ARE in `elec/src`, unlike the rest of this section — they're part of the 155-component count):

| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |
|-----|-------------|-------------|--------------|-----|---------|-------|
| J_FAN | Fan Power Header | 61300211121 | Würth Elektronik | 1 | 1x2 THT 2.54mm | Fan is off-board; leadwires to this header |
| R_FAN_DROP | Fan Series Dropper | RSF100JB-73-39R | Yageo | 1 | Axial DIN0207 | 39Ω 5% 1W — brings 15V into the fan's 4.5-13.8V operating range |

**Chassis BOM** (not modeled in `elec/src` — these are mechanical/thermal assembly parts, out of the atopile design's scope by its own convention; see `ThermalSystem`'s docstring, `modules.ato:1141-1155`):

| Ref | Description | Part Number | Manufacturer | Qty | Notes |
|-----|-------------|-------------|--------------|-----|-------|
| HS1 | Shared Heatsink (2×TO-247 + 2×TO-220) | 392-120AB | Wakefield-Vette | 1 | Extruded, 120x125x135.8mm, 0.5°C/W natural / 0.2°C/W forced convection |
| FAN1 | Cooling Fan | MF60251V1-1000U-A99 | Sunon | 1 | 60x60x25mm, 12V, 23.5CFM, non-PWM — driven via R_FAN_DROP series dropper above, not PWM |
| TIM_HV | TIM/Isolator, TO-247 (IGBTs) | SP400-0.009-00-58 | Bergquist | 2 | Sil-Pad 400, 0.009", TO-247 die-cut |
| TIM_LV | TIM/Isolator, TO-220 (rectifiers) | SP400-0.007-00-54 | Bergquist | 2 | Sil-Pad 400, 0.007", TO-220 die-cut |
| HW_MOUNT | Mounting Hardware | M3x10 pan-head + insulating shoulder washers + Belleville washers | - | 4 sets | Verify exact shoulder-washer part fits the TO-247 3.6mm mounting hole before ordering |
| FUSE1 | Thermal Fuse | SF152E | NEC/Schott | 1 | 157°C 15A 250V |

> **`HS1`, `FAN1`, `TIM1` corrected against `docs/plans/2026-07-16-001-feat-active-bus-discharge-and-thermal-bom-plan.md`**, which `ThermalSystem`'s own docstring points to for verified chassis MPNs. `HS1` was `AVID 62960` (Aavid); `FAN1` was Noctua `NF-A8 PWM` (80mm, PWM) — source uses a non-PWM 60mm Sunon fan run through the on-PCB `R_FAN_DROP` series resistor, so there is no PWM conductor to the fan at all. `TIM1` (a single Panasonic graphite-pad line) is replaced by the two Bergquist Sil-Pad part numbers actually sized to the TO-247/TO-220 outlines used here.
>
> `FUSE1` (thermal cutoff) is left unchanged — no source evidence either way; not covered by the plan doc above, and chassis-level/out of `elec/src` scope by design like the rest of this table.

---

## BOM Summary

### By Category (component count, not BOM line-item count)

| Category | Component Count |
|----------|----------------|
| Power Stage (IGBT, gate drive, EMI/doubler, bus discharge, tank) | 45 |
| Power Management (buck, aux supply) | 13 |
| Microcontroller | 10 |
| Sensing (RTD chain, CT, CT bias) | 34 |
| Safety Interlock (comparators, logic, watchdog, OVP/OCP dividers, thermal ×2, UVLO-02) | 43 |
| User Interface (buttons) | 2 |
| PWM Filter | 4 |
| Thermal (PCB-side fan interface) | 2 |
| **TOTAL** | **~165 (not re-verified against `elec/build/default.net` in this pass — see 2026-08-07 revision note)** |

Chassis BOM (§11, not in the 155): heatsink, fan, TIM ×2, mounting hardware, thermal fuse — 6 additional lines, mechanical/off-`elec/src` by design. `F1_HOLDER` (§1.2, added 2026-07-26) is the same kind of exception: a real orderable part and BOM line that is not a separate `elec/src` component (mechanical carrier, same two electrical nodes as `F1`) — 1 additional line, not in the 155.

### Critical Long-Lead Items

| Component | Lead Time | Alternative |
|-----------|-----------|-------------|
| IKW40N120H3 | In stock | - |
| ESP32-S3-WROOM-1-N8R8 | 4-8 weeks | N4 variant (loses PSRAM) |
| UCC21550BDWKR | 4-8 weeks | - |
| CST3015-100ED | Verify stock | CST3015 family variants — board re-layout already required regardless, see §4.3 |
| EKMQ251VSN182MA50S (×4) | Verify stock | Physically large snap-in electrolytics; confirm before layout freeze |
| 0031.2510 (F1_HOLDER) | 12-week mfr. lead time (DigiKey), 83 units on hand | New line 2026-07-26 — order early; footprint not yet drawn, see §1.2 |
| B32922C3224M289 (C_X2) | Not flagged long-lead (28,179 units at DigiKey) | New footprint required before fab (box-style MKP, 15mm pitch) — not a stock risk, a layout task, see §1.2 |

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-14 | Initial release |
| 1.1 | 2025-12-17 | Updated for 1.8kW redesign: CST-1005 CT, 66.5Ω burden, 300nF FKP1 caps |
| 1.2 | 2026-07-25 | Reconciled OCP/thermal entries with `elec/src/modules.ato`: CT1 → CST2010-100L (1:100; CST-1005 retired in `5a58b397`), R_BURDEN → 6.65Ω (was a decade off), NTC_HS → NTCALUG01A104GA (was wrong decade *and* beta), added the three thermal divider resistors. THM-01 corrected to 84.9°C. Flagged inline: OCP-01's spec/CT conflict, THM-02 having no circuit. **This BOM is not yet orderable** — see `docs/evidence/2026-07-25-bom-source-audit.md` for ~35 costed-but-absent and ~75 wired-but-uncosted items. |
| 1.3 | 2026-07-25 | **CT1 → CST3015-100ED** (88A sensed, was CST2010-100L at 47A) resolving the OCP-01 spec/transformer conflict; R_BURDEN → 4.99Ω, trip 50.1A. Footprint `temper:CST3015` still to be drawn — not fabricable until then. |
| 1.4 | 2026-07-26 | **De-scoped IGBT desaturation protection** — removed 19 costed line items for a circuit that was never designed. The UCC21550 in use has no DESAT pin, so this is a gate-drive redesign rather than a part swap. Shoot-through, gate-drive failure and device-local shorts are recorded as accepted residual risk; see `docs/hardware/DESAT_DECISION_BRIEF.md`. A redesign spike is open. |
| 1.5 | 2026-07-26 | **Full BOM-vs-source reconciliation**, working the `docs/evidence/2026-07-25-bom-source-audit.md` findings class by class against `elec/src/*.ato` (verified via `elec/build/default.net`/`default.csv`, 155 components). Class C (16 value/MPN disagreements): fixed OVP divider (1MΩ/30kΩ → 430kΩ/10kΩ — this was still wrong going into this pass despite the OCP/thermal fixes in 1.2-1.3), bootstrap diode (UJ3D1210TS → ES1J), bus caps (fictional 3300µF → 4×1800µF), bleeder resistors (100kΩ → 22kΩ), CMC, bypass relay, buck converter (wrong topology entirely — was described as 24V/12V→5V, corrected to 15V→3.3V with all real values), gate driver MPN, RTD MPN/package/channel-count, PWM filter cap, ESP32 variant, watchdog decoupling cap, logic-IC manufacturer/MPN/quantity, fan, heatsink, TIM. Class A (removed, absence proven by grep against `elec/src/*.ato`): OCP-02 shunt/amp/comparator (still not instantiated — topology decision pending, see §4.4), precision rectifier, I2C isolator, fault LEDs, AND/INV logic gates, anti-aliasing filter, LDO section (replaced by buck), plus a newly-found `J_IN` connector line with no source component and a generic decoupling bucket superseded by exact itemization. Class B (added from source, ~95 previously-uncosted components): active bus discharge (17 parts), isolated auxiliary 15V supply (4 parts — the isolation barrier itself), RTD hardware-window fault chain (15 parts) plus RTD SPI/ferrite/decoupling (12 parts), CT bias+filter (3 parts), OCP/OVP reference and ADC-tap dividers (9 parts), gate-drive bypass/filter/dead-time/zener network (10 parts), AC-input protection (fuse, MOV, X2/Y1 caps, ZCD network, bypass-relay driver — 11 parts), MCU boot/reset RC + buttons (4 parts), plus THM-02 coil-thermal protection (5 parts, designed in source on this same date — previously had no circuit at all, not merely uncosted). Component count now matches source exactly at 155. See full per-line detail inline above; `docs/evidence/2026-07-25-bom-source-audit.md` records the original findings this pass resolves. |
| 1.6 | 2026-07-26 | **Resolved the three confirmed procurement blockers from `docs/evidence/2026-07-26-bom-availability-sweep.md`** (full resolution detail: `docs/evidence/2026-07-26-bom-blocker-resolution.md`). (1) `GRM188R71E104KA01D` (100nF/0603/X7R decoupling, Obsolete/0-stock at DigiKey, 16 instances across §1.1/2.1/2.3/3.1/4.1/5.3/5.6) → `C0603C104K5RACTU` (KEMET, 100nF ±10% X7R 50V) — Active, 6.7M units at DigiKey; flagged DC-bias derating on the three 15V-rail instances (`C_VDDA`, `C_VDDB`, §2.3 `C_OUT_HF`). (2) `C_X2` MPN `DE2E3KH221MA3B` (not found at any distributor; Murata's own DE2 "221" suffix convention decodes to 220pF, 1000× off the 220nF this circuit needs, and the DE2 family tops out ~10nF regardless) → `B32922C3224M289` (EPCOS/TDK X2/305VAC film cap) — Active, 28,179 units at DigiKey; approvals read directly from EPCOS's own datasheet (IEC 60384-14/EN132400, UL 1414/1283, CSA C22.2, CQC); new box-style footprint required, not yet drawn. (3) `F1` (`0034.3129`) confirmed to be a bare Schurter FST fuse **link**, not a holder+fuse assembly — added `F1_HOLDER` = Schurter `0031.2510` (FUP series, 16A/250-500VAC, matches the fuse's rating) as a new BOM line; not separately modeled in `elec/src` (mechanical carrier, same two nodes as `F1`); new footprint required. Also flagged, unresolved: no I²t/inrush coordination analysis exists anywhere in this repo for `F1`/`NTC_INRUSH`/`K_BYPASS`, and the 16A fuse has only ~7% headroom over the 15A continuous branch load. |
| 1.7 | 2026-08-07 | **Full BOM<->source reconciliation against the R14 gate's 49 seeded findings** — applied `docs/hardware/BOM_RECONCILIATION_PROPOSAL.md`'s verdicts (41 BOM-stale edits, 7 designator-normalization allowlist mappings, 1 already-correct design decision, 0 source-stale, 0 ambiguous). **Safety-relevant (3):** `R_DIS1A/1B/2A/2B` 4.7kΩ→3.9kΩ (BOM's 4.7kΩ fails the <60s bus-discharge requirement at 65.4s on the capacitor's own tolerance alone; 3.9kΩ gives 56.9s worst-case); THM-01/THM-02 reference/hysteresis dividers corrected to restore 15°C/20°C hysteresis (BOM's stale, pre-`a4fb15dc` values gave only 5.6°C/6.6°C, risking chatter at the trip threshold); `R_OCP_REF_T` 3.2kΩ (fabricated, non-orderable MPN)→3.24kΩ (real E96 value, 49.95A trip). **Misleading-documentation fixes (2):** removed the stale "does not meet reinforced isolation, unresolved" warning on `K_DIS1/K_DIS2` (source fixed this 2026-07-31/08-02, swapping to `RT314012`, 12.76mm gap vs the 8.0mm requirement); corrected §4.6's mislabeling of the RTD hardware-window chain as "UVL-02 candidate" (its own module docstring says "Not UVL-02") and added the real, previously zero-row `LogicUVLOComparator` (UVLO-02) gate as new §5.9 (8 items total: 6 in §5.9, `U_OR3` in §5.2, `TP3` in §10.2). **Other BOM-stale corrections:** `C_TANK1/2` WIMA→CDE re-source plus a third physical capacitor (`C_TANK3`, 2→3 caps); OVP-01's Option C re-reference (`R_OVP4`→`R_OVP_DIV_BOT`, `R_OVP_REF_T/B` deleted — resistor no longer in circuit, `R_OVP_ADC_T` split into 3 protective-impedance-compliant resistors, new `R_OVP_HYST` row for a previously entirely-uncosted hysteresis resistor). **Designator-normalization-only (7, allowlist mapping added, no BOM.md value change):** `R_OVP1/2/3` (alias of source's `r_div_top1/2/3`, value was already correct) and `boot_cap` (gate-driver bootstrap cap, distinct from the buck converter's same-labeled `C_BOOT`). See `docs/hardware/BOM_RECONCILIATION_PROPOSAL.md` for full per-item evidence and re-derivations. |
| 1.8 | 2026-08-14 | **Pruned the mains-ZCD circuit (R14 BOM<->source reconciliation, 6 `costed_no_circuit` findings)** — `5842767c2` deleted `R_ZCD_TOP1`, `R_ZCD_TOP2`, `R_ZCD_BOT`, `D_ZCD_CLAMP`, `U_ZCD_OPTO`, `R_ZCD_OPTO`, `R_ZCD_PULLUP` from `elec/src/*.ato` (no firmware consumer — `PIN_ZCD_INPUT` was never read past its own `#define` — and no architectural role, since soft-start is time-delayed, not zero-cross-synchronised); this pass removes the corresponding §1.2 BOM rows, which this section's own prior note had flagged as required "in the same change." Companion change: removed the seven now-orphaned `pcb/temper.kicad_pcb` footprints (D2, R6-R10, U3) and the stale `PIN_ZCD_INPUT` assertion in `elec/validation/test_ucc21550_contract.py`. |

---

## References

- SAFETY_INTERLOCK_DESIGN.md
- CT_SENSING_DESIGN.md
- VOLTAGE_DOUBLER_DESIGN.md
- SPLIT_RAIL_BOOTSTRAP_DESIGN.md
- COMPONENT_COMPATIBILITY_VERIFICATION.md
- sim_15_ldo_selection_verification.md
- sim_17-20 verification reports
- docs/evidence/2026-07-25-bom-source-audit.md
- docs/hardware/OCP02_DESIGN.md
- docs/hardware/DESAT_DECISION_BRIEF.md
- docs/hardware/TANK_COIL_SPECIFICATION.md
- docs/plans/2026-07-16-001-feat-active-bus-discharge-and-thermal-bom-plan.md

---

**END OF BOM**

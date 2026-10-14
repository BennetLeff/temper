# Integration queue (2026-10-13)

Proposals from the group folders, grouped into candidate boards. The lead integrates one candidate at a time; each is chained and scored against the benchmark (`../10-benchmark/`). The ranking puts safety deficits first, then low-risk simplifications, then items that need other boards, the owner or the certifier.

| Candidate | Contents (source) | Effort / risk | Why it is next | Needs |
|---|---|---|---|---|
| **20: BOM-only bundle** (running) | T1 → CST3015-200ED with R39 3.0 Ω (g04-g09 P1); U36 → VOL628A-2X001T (g04-g09 P2); bank K → J (g04-g09 P3); C49678 label to Basic (research A1) | Schematic values only, no copper; med (T1 is a protection input) | Stock and hand-assembly gains with zero layout risk; the 28 A bank margin goes 1.105 → 1.022 | Bench: CT trip injection (D4 condition 2, as for any T1) and the ZC pulse width |
| **21: power-path copper** | BR1 feeds BUS_P / HV_RET directly and J7–J10 leave the mains build (g02-g03 A); R5.4 via field (g02-g03 C); KELVIN_N under the KELVIN_P pour plus C30/C31 at U6 (g06-g08-g10 P4, which fixes F8); D5 via nudge (g05-g07 P5) | Re-layout of the BR1 zone and the R5 / U6 corridor; med; SAFETY (fault containment, bench mode) | Closes F2's copper half and F8, cuts DC loss about 2 W, shortens the bulk path; all in one region | Restate `fuse_copper_fusing_ratio` to exclude device-terminal-limited rows (the TO-247 drain tongue caps it at about 0.99); the bench mode becomes BR1 DNP plus leads on J8 / J10; G08 Kelvin band rerun; B3 |
| **22: drive-disable simplification** | PERMIT/DIS through a NAND, Q1/Q4 and R8/R16 deleted (g05-g07 P3) | Schematic plus local rewire; low–med; SAFETY (truth table identical) | −4 placements and −21 mA of V3V3 load | Controller: PERMIT drives a CMOS input (VIH 2.0 V). Bench: DIS rise time |
| **23: supply and filter topology** | Delete PS1 and feed the logic from PS3 over J13 (g06-g08-g10 P1); F2 → 1.5 kA 5×20 plus a 0.15 Ω limiter (g06-g08-g10 P2, fixes F4); filter re-balance with SC-20-201 as L1 and the module choke, module Y pair removed (g01 P1) | Re-layout of the J11 / PS1 / L1 areas; med–high; SAFETY | Fixes F4. Leakage 0.974 → about 0.55 mA, or about 0.41 mA with the PS2 argument. EMI improves. L1's zero-stock line goes | **Controller** (J13 rail merge, J4.1). **Enclosure** (PS3 bay air ≤ 58 °C, J13 2.97 A, fuse height). **Certifier** (leakage limit class; whether PS2's leakage counts, g06-g08-g10 P3). Measure the SC-20-201 leakage inductance on a sample first |
| **24: monitor consolidation** | High-side monitors cross to the LS domain through ISO6721FB, with one reinforced crossing instead of three (g05-g07 P2) | Re-layout of G07; med–high; SAFETY (one stuck isolator then masks three rails) | −12 placements and two zero-stock ISO7710s gone | FMEA and the certifier |
| **25: CMTI driver** (DONE: stage 29, DECISIONS 31; 2EDR8259X + 8.2 Ω gates) | 2EDR8259H (research), Rg about 8.2 Ω | BOM plus Rg; high | F6 margin 1.32 → 1.58 | The D2 decision grid rerun over a wider dead-time band (the audit window allows ±12 %, and 2EDR8259H spreads ±15 %); F6 decks on the remote box |
| **26: polymer-cap MPN** | C126–C129 6SVPC220M → 6SVPC220MV (r2-cost R2-05): same OS-CON SVPC can, 15 vs 27 mΩ ESR behind the 0.68 Ω damping resistor | BOM only; low | Stock 13 → 845; −$0.82 at 500 | — |
| **27: J1 approval rating** (DONE: stage 27, DECISIONS 29) | J1 Phoenix 1711725 is 24 A IEC but 15 A cULus group B / 10 A CSA against 13.5–15 A in normal use (`../13-external-review-2026-10-13/FINDINGS.md` #4, #11). Fit a mains terminal rated ≥ 20 A under UL group B | Footprint + J1 corner re-layout; med; SAFETY / approval | Proven rating defect; ranks ahead of cost work | A part with LCSC stock and a UL file; the enclosure fit gate |
| **28: F2 breaking capacity** (DONE: stage 28, DECISIONS 30; UMT-H + upright AC05 instead of the 646 holder) | Littelfuse 0215 3.15 A 1.5 kA in a 646 holder with a 648 cover, plus 0.15 Ω cemented wirewound (`g06-g08-g10-supplies-sense-io/f2/PARTS-2026-10-13.md`) | J11 corner re-layout; med; SAFETY | Fixes F4 (784 A bound, 1.91×); −1 no-LCSC line | Fuse clearing I²t unpublished: the resistor's pulse survival needs a bench short at J11 (AC05 125 A²s vs about 130 A²s estimated; AC07 has no stock). Holder about 14.5 mm tall: fit gate |

## Study results, 2026-10-13 (after stage 27)

- **Candidate 24 FMEA** (`c24-monitor-fmea/FMEA.md`): **GO only with mitigation M1**, a toggling heartbeat through U32.
  - P2 as written adds a single-point latent failure that hides all three rails: about 10 FIT, ×2.7 today's 3.65. Nothing
    ever reads BIAS_GOOD, so a stuck-low isolator or NAND would go unnoticed.
  - With M1 the hidden-fault exposure falls 62 % below today's. M1 is an LVC1G132 oscillator through U32 into a charge
    pump on U40, swapped G14 → G17.
  - Net: −6 placements, +1 BOM line, about −$1.75 to −$3.95. The two zero-stock ISO7710s go, and 3 reinforced crossings
    become 1.
  - Before layout: SPICE the pump and oscillator, rerun B4 timing for a ≤ 90 µs response, update audit.rs, and answer
    7 certifier questions (FMEA §7).
- **Candidate 29: inlet filter on board** (`c29-inlet-filter/README.md`): **conditional GO, only together with candidate 23**
  (PS1 deleted).
  - Touch current goes 0.974 → 0.419 mA on Test A (pass), with EMI 10.8 / 6.6 dB. With PS1 still fitted it's 0.562 mA, a fail.
  - Score it on system cost: −$6.74 at 500, about −$14.6 with labour. Board-only parts rise $29.7 because the module's
    parts move onto the board.
  - The parts do not fit the current outline: the mains edge would grow 50–95 mm. That needs enclosure input.
- **New finding, outside the board: the D-22 inlet module as specified has no DM inductors.** DECISIONS item 20 requires
  ≥ 100 µH DM (18 µH choke leakage + 2 × 41 µH), and the 41 µH parts have no MPN. As specified, the EMI model gives −5.1 dB.
  The scorecard's 10.5 dB assumes the inductors. Owner and enclosure item: pick a 41 µH / 20 A DM inductor, or raise the
  switching-frequency floor to 40–45 kHz (F10).
- **Ledger findings:**
  - **U9 BUS_FAULT has no filter** anywhere between the isolator and the controller's interlock. A CMTI upset can only trip
    the drive off (latched, safe direction): a nuisance-trip risk. Bench-probe BUS_FAULT at hard S4/S5 edges; the re-spin
    option is 1 kΩ / 47 pF at U13.A.
  - **L1 at 15 A** meets the 80 % derating rule only up to 67.7 °C local air.
  - **The RECOM U41/U42 reinforced isolation claim is confirmed.** The current /R datasheet (Rev. 1-2024) gives 5 kVAC; the
    earlier "functional only" reading came from a different series.

## Owner or certifier decisions surfaced (not candidates)

- **F1 to a 6.3×32 fast-acting fuse** (g01 P2) saves about $26–30 per board and lowers clearing I²t. It reverses the Class CC decision, though, so it needs the lab's acceptance and the Littelfuse clearing I²t first.
- **Leakage basis:** limit class (UL 1026 portable 0.5 mA vs stationary 0.75 mA), whether supply-module leakage is measured or taken at datasheet maximum, and the 50 % design budget. These set how far candidate 23 must go.
- **F10:** raising the fs floor to 40–45 kHz would let the inlet module drop its DM inductors (g01 P3). That is a firmware and tank-yield trade, owned with the controller and G04.
- **DC-link clamp 2 J target** (r2-cost R2-01, -$19.64 and -1 consign line per board): deleting D3/D17 is safe in every
  modelled event (<= 0.46 J returned, bus <= 379 V and <= 451 V with 500 uH line inductance), but the bus alone takes the
  requested 2 J only at 547-592 V, over the 520 V screen (`r2-cost/scripts/clamp_2j_check.py`). Keep the clamp unless the
  owner restates the absorption target as the modelled return energy plus margin; a bench no-clamp surge test then decides.
- **C5/C6 ripple at the commissioned ceiling** (datasheet ledger, B32676G1905K000). ALT-C5C6 put self-heating at 80 % of TDK's
  permitted ΔT at 22 A and an 85 °C cap ambient. Since ΔT ∝ I², that is about 112 % at 26 A and 130 % at 28 A, against 54 % at
  26 A with a 70 °C ambient. Bench condition before running above 22 A: either the B3 / enclosure cap ambient is ≤ 75 °C, or
  a C5 case-temperature measurement at the ceiling.
- **Ordering, not design:** UCC21550 and ISO7710 are stocked at TI.com, and UCC21550ADWR/BDWR at JLC. R5, PS1 and PS2 are stocked at LCSC.

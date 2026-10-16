# Certifier pre-review checklist: Temper 120 V induction cooktop power board (native-21, board of record s51)

Date 2026-10-16. Desk compilation from the repo, read-only. Nothing was sent, no one was contacted, no calculation was rerun.
PS = `zapote/power-stage-120v` in the ps-integrate worktree. FW = `firmware/` at the ps-integrate worktree root.
CTRL = `zapote/controller`. "Clause to confirm" means the repo does not cite a clause number for that point.

How to read an entry. STRICT = the design already meets the conservative reading. RELIANT = the design depends on a favourable reading.
Priority: HIGH = a "no" forces a layout or architecture change. MED = BOM or firmware. LOW = documentation.
Size: BOM-only / layout stage / new board / enclosure. Board: power (PS), controller (CTRL), enclosure.

Caveat on the packet. `PS/validation-results/08-manufacturing-package/native-21/owner-items/CERTIFIER-PACKET.md` (draft 2026-10-14, not sent)
predates s38 to s51. Items to refresh before anything is sent: touch current is now 0.2412 mA (packet says 0.419); PS1 is deleted;
PS2 is now MEAN WELL MPM-20-24 and PS3 (off-board, controller side) MPM-65-15ST, not IRM-20/IRM-60 (packet item 14);
the CA-IS3720 on U44 became a second ISO6721FB (DECISIONS stage 40); the bank is now MMK104J3DF1KN208G2 (DECISIONS 73).
The packet's standard is "UL 1026 appliance"; S15 cites UL 858 25.3.1. Which standard governs is itself the first question (entry 0).

---------------------------------------------------------------------------------------------------------------------

## 0. Which standard, which route (ask first, it frames everything)

- **Topic / clause:** UL 1026 (household electric cooking and food-serving appliances, per packet heading) vs UL 858 (cited only in OPEN-ITEMS S15
  and FMEA section 7 as "UL 1026 / UL 858"); CSA C22.2 No. 64; NOM route NMX-J-521/1 and NMX-J-521-2-6 (modified IEC 60335-2-6), IEC 60335-1:2020
  as the clause source for insulation (Tables 16-18, 29.x) and PEC (19.11, 19.13). Which UL standard applies to a countertop cord-and-plug induction
  hob and which clause numbers: clause to confirm. Nameplate: 120-127 V~ 60 Hz, 15 A NEMA 5-15P, US / Canada / Mexico (DECISIONS 2026-10-08).
- **Design now:** designed against a union of the IEC 60335-1 clauses and the UL limits found in secondary sources. No primary UL text has been read
  (paywalled; F5-LEAKAGE-DECISION.md section 1 marks it [UNVERIFIED]).
- **Assumed:** the IEC 60335-1 numbering the repo quotes maps onto the UL standard the lab applies. RELIANT.
- **If the lab disagrees:** the clause table in every entry below needs re-keying; limits may move (leakage 0.5 vs 0.75 mA, entry 4). No hardware change by itself.
- **Priority:** LOW (documentation), but answer it first because it changes which of the other answers apply.

---------------------------------------------------------------------------------------------------------------------

## A. Insulation, creepage, laminate

### 1. RES_A / coil to SELV and PE: 12.6 mm creepage (reinforced, PD3 / IIIa), outer layers
- **Topic / clause:** reinforced creepage, IEC 60335-1 Table 17 (PD3, material group IIIa) at 297 V rms working; Table 17 footnote limits IIIb to <= 50 V.
  UL 1026 equivalent: clause to confirm. (DECISIONS 7 / stage 18; D5-BASIS.md.)
- **Design now:** RES_A is 297 V rms / 656 V pk to earth at 28 A normal use, 362 V rms / 791 V pk at the 29.4 A trip envelope. Outer-layer RES_A to SELV/PE:
  F.Cu min 20.393 mm, B.Cu 13.375 mm (rerouted from 8.145 / 9.400 in stage 18). Enforced by `rules21.RES_A_CREEPAGE` 12.6 mm and a DRU rule on outer layers.
  Evidence: DECISIONS stage 18 (line ~744-760); `owner-items/m6m10/coil-selv-28a/`.
- **Assumed:** PD3 / IIIa governs and 12.6 mm is the right row for the 250-400 V band. STRICT for PD3 (we already use the worse of PD2 8.0 / PD3 12.6 mm).
  The coil winding is potted and treated as PD2 in one place (DECISIONS 489): RELIANT on PD2 for the potted winding system.
- **If the lab disagrees:** a larger working-voltage row (the crest-RMS reading, entry 3: RES_A to HV_RET / N_LS / BUS_P would need 6.3 mm) or a worse pollution degree on
  the outer-surface paths means a re-layout of the RES_A lanes (F.Cu is already >= 20 mm, B.Cu 13.375 mm, so the exposure is the inner/outer transitions and the
  lanes near other HOT nets). Layout stage, power board.
- **Priority:** HIGH (re-layout if the lab uses a larger row).

### 2. D5 8.0 mm HOT / SELV / PE floor and "same-layer inner paths are solid insulation"
- **Topic / clause:** functional vs reinforced insulation HOT to controller (earthed ELV via R38); IEC 60335-1 29.3 (solid insulation, 2 mm reinforced, as cited at
  DECISIONS stage 18 line ~756 and packet item 10); 29.2.1 plus IEC 60664-4 above 30 kHz. D5-BASIS.md (8.0 mm provisional PCB floor).
- **Design now:** 8.0 mm floor everywhere HOT to SELV/PE for nets <= 250 V rms; measured D5 8.047 / 8.507 mm (DECISIONS stage 18-19 gate lines). All inner
  RES_A copper is >= 8.0 mm in plan view on every layer and is treated as solid insulation. The controller ground is an "earthed ELV" tied to PE by one removable
  0 ohm R38; HOT to controller reinforced insulation must hold with PE open (D5-BASIS.md). No physical insulation testing has been done.
- **Assumed:** (a) the 8.0 mm floor is enough for the <= 250 V nets (STRICT on the repo's own table); (b) a same-layer inner path counts as a cemented joint /
  solid insulation, not as a creepage path. RELIANT on (b). Open follow-up: if (b) is refused, C152.1's inner rings are 9.694 mm from In1 v3v3 / In2 selv_gnd
  islands and need a ~3 mm pull-back or ring removal (DECISIONS stage 18 line ~756); the same argument is the basis for any 6-layer build.
- **If the lab disagrees:** inner-layer pull-backs and possibly a re-cut of inner pours. Layout stage, power board. A "yes" with a minimum solid thickness also
  constrains the prepreg choice (entry 5).
- **Priority:** HIGH.

### 3. Working voltage on the coil lanes: line-cycle RMS or carrier-crest RMS; stud spacing
- **Topic / clause:** IEC 60335-1 29.2.4 / Table 18 (PD3 IIIa) and Table 16 clearance; IEC 60664-4 Table 2 (high frequency). Decided at DECISIONS 2026-10-08
  (coil-stud spacing, owner decision) with the 28 A update of 2026-10-12.
- **Design now:** J2/J5 15.0 mm centres with insulated ring terminals; tank rule 5.0 mm. Coil voltage with a pan: 345-362 V rms (needs 4.3-4.6 mm, PASS).
  No-pan at 28 A: 409 V rms / 818 V pk needs 5.16 mm, fails by 0.16 mm; accepted because firmware holds a 22 A no-pan clamp (`TANK_CEILING_DEFAULT_A`),
  with an `N21_FAULT_TANK_RMS` overrun latch. Note this makes a creepage argument depend on firmware (see entry 14).
- **Assumed:** line-cycle RMS (normal use) is the working voltage; the no-pan 28 A point is a clause-19 fault on functional insulation between two HOT nets.
  RELIANT.
- **If the lab disagrees:** (i) lab ties voltage to the no-pan case: raise the firmware floor to >= 36.2 kHz or the bank to >= 0.465 uF (firmware + BOM);
  (ii) lab uses carrier-crest RMS: coil lanes need ~7.4 mm and RES_A to HV_RET / N_LS / BUS_P 6.3 mm, a board-wide re-layout (DECISIONS 2026-10-08).
  Layout stage, power board; stud spacing also touches the enclosure (terminal lugs).
- **Priority:** HIGH (crest-RMS answer); MED for the no-pan case.

### 4. Pollution degree and CTI of components used as isolation evidence
- **Topic / clause:** PD2 vs PD3 per component; CTI / material group. Clause to confirm per component.
- **Design now:** gate drivers 2EDR8259X: material group II, PD2, CPG/CLR 8 mm (exactly the 8.0 mm floor, not above it). AMC1311: 8.5 mm, VIORM 2120 V,
  UL 1577 5 kVrms. CA-IS3720HW: 8 mm, CTI > 600, group I, UL 1577 E511334, VDE 40057278. VOL628A (U36): CTI 275 (IIIa), PD2, UL 1577 E76222. T1 CST3015:
  Coilcraft states reinforced, >= 8 mm, 5 kVrms but gives no CTI, working voltage or HF/PD rating at 198 V pk, 35-60 kHz. D5-BASIS.md: package distances are
  "evidence about those packages, not blanket PD3 appliance approval".
- **Assumed:** package creepage printed by the maker is acceptable in the end product at PD2 (RELIANT, conformal board / enclosure sealing is not claimed);
  T1 acceptable as a component without UL/CSA recognition (RELIANT).
- **If the lab disagrees:** isolator swap to a wider-body package or a slot (layout stage), T1 swap (BOM + layout), or an enclosure-level PD2 argument
  (enclosure). Power board.
- **Priority:** MED to HIGH (HIGH only if the 2EDR8259X 8 mm is judged short of the PD3 row for its working voltage).

### 5. Laminate UL listing and CTI (S12)
- **Topic / clause:** UL recognised laminate, CTI >= 175 V (PLC 3, group IIIa) per IEC 60112 / 60664-1; MOT. OPEN-ITEMS S12; DECISIONS 41, 51.
- **Design now:** order names Kingboard KB-6164 core + KB-6064 prepreg, stack JLC041622-7628, "TG135" option (+$0.28 per board at 500). UL E123995: KB-616(X)
  CTI PLC 3 at 1.40 mm; TDS CTI >= 175 V. **Gap (S12):** the KB-6164 (35 um) and KB-6165 (54 um) multilayer rows do not cover 61 um (2 oz) inner copper; KB-6164F / 6165F / 6167F
  list 102 um and JLC's "TG155" option links KB-6165F. `stackup.json` still says Nan Ya NP-155F. No JLC laminate has public PLC <= 2. JLC gives no per-order material certificate.
  DECISIONS 46: the board does not meet the laminate's MOT everywhere without the hot-copper release case (thermal basis in OPEN-ITEMS header).
- **Assumed:** PLC 3 = group IIIa meets the requirement with no margin (STRICT at CTI 175, zero margin); the certifier accepts a UL Product iQ reprint for 35/54 um
  rows as covering 61 um inner copper (RELIANT). Owner to ask JLC which recognised construction covers 4 L, 2 oz inner, CTI >= 175 V.
- **If the lab disagrees:** a different recognised construction (BOM / order remark; fix remark and `stackup.json` together), re-run of the thickness-dependent chain
  if the stack changes. Group II (CTI >= 400) is not available from JLC, so a PLC 2 demand means a different fab (new board build). Power board.
- **Priority:** MED (HIGH if the lab demands PLC <= 2).

---------------------------------------------------------------------------------------------------------------------

## B. Touch current, Y capacitors, leakage

### 6. Touch current limit class and measurement (A1 items 1, 2, 4; S1)
- **Topic / clause:** UL "portable" 0.5 mA / "stationary" 0.75 mA, open ground, both polarities (IAEI secondary source); NOM / IEC 60335-1 Class I portable 0.75 mA.
  Clause in UL 1026 / UL 858: clause to confirm. Test voltage: model uses 132 V (F5 record: 127 / 132 / 134.6 V change the older recommended-set result only from 0.392 to 0.416 mA);
  cl. 13.2 for IEC is the repo author's recollection, [UNVERIFIED].
- **Design now (S1):** DESIGN 0.2412 mA against a 0.25 mA budget (= 50 % of 0.5 mA), **margin 8.8 uA** (DECISIONS 50). Built in s38: D-22 inlet module Y removed
  (off-board), SCF31X choke, PS2 -> MPM-20-24 (< 80 uA at 264 V), PS3 -> MPM-65-15ST (< 100 uA), PS1 deleted. Board Y = C3 / C4 2.2 nF per line. The ledger notes
  the pass **fails with +0.15 nF Y per line**. Records: `c23-supply-topology/README.md`, `12-decisions/F5-LEAKAGE-DECISION.md`.
- **Assumed:** 0.5 mA applies (STRICT against the tighter limit, i.e. we design to the portable value with a 50 % margin rule). RELIANT on: (a) module leakage evaluated at the
  stated datasheet value for the MPMs, not a larger number; (b) the off-board module Y removal being real in the delivered product (an enclosure / inlet-module item);
  (c) whether PS2 counts in the PE path (A1 item 3, "P3": PS2's output is HOT-referenced, no PE bond; 0.419 -> 0.276 mA in the old model). Confirm in the c23 record whether 0.2412 already claims P3.
  The HF weighting of the coil-to-PE term is not credited.
- **If the lab disagrees:** if the lab requires 0.25 mA absolute or measures higher, the next lever is the robust variant (L1 -> SCF31X, needs an L1-slot re-layout, 11.51 dB EMI),
  or a smaller C3 / C4 (BOM; EMI margin falls; EMI min 8.19 dB at s38). Layout stage plus BOM, power board; the inlet module (off-board) is a vendor change.
  If the lab says "measure on the product", a first-article bench test decides; keep the 8.8 uA margin out of any claim.
- **Priority:** HIGH (the margin is smaller than the part tolerance; a single reading of the lab's meter could break it).

### 7. Y capacitors C3 / C4 (DE1E3RA222MA4BP01F, Murata, 2.2 nF Y1)
- **Topic / clause:** IEC 60384-14 / UL 60384-14 / CAN/CSA E60384-14 Y1; UL file E37921, ENEC VDE 40043033, CQC. (Ledger entry.)
- **Design now:** Y1 AC300 V, impulse 8 kV; board-level Y = 2.2 nF per line (4.4 nF total); no DC-bus Y to PE (CM resonance, DECISIONS item ~812). Leakage per entry 6.
  Stock: C3/C4 Mouser 773, 6 / 40 at JLC (DECISIONS 2026-10-16); the spec was Murata's Jun 2023 reference spec via a distributor and approval sheet not yet read.
- **Assumed:** Y1 (not Y2) is acceptable for line-to-PE (STRICT, Y1 is the conservative class); approvals stand as listed (RELIANT until the approval sheet is read).
- **If the lab disagrees:** value change (BOM) with leakage / EMI rerun; capacitor swap (BOM). Power board. Surface temp 125 C limit not evidenced (B3 has no C3/C4 row).
- **Priority:** LOW (documentation) unless the lab wants a lower Y, which moves to entry 6.

### 8. X2 capacitors C1 / C2, bleed R1 / R2, varistor RV1 (supporting)
- **Topic / clause:** UL 60384-14 X2 (KEMET R463N410050N1K, E97797, 310 VAC); X-cap discharge requirement (finding #10 in external review, clause to confirm);
  RV1 TMOV20RP175E UL 1449 component recognition E320116.
- **Design now:** R1 / R2 are 2 x 100 k in series (UniOhm 1206, no pulse rating published). RV1 thermal disconnect behaviour in the end-product abnormal overvoltage test is a
  certifier item (ledger gap). Packet item 17 asks about removing R1 / R2 (small).
- **Assumed:** component-level recognitions suffice. RELIANT on RV1's thermal disconnect behaving in the lab's surge / abnormal test.
- **If the lab disagrees:** varistor or bleed swap. BOM-only, power board.
- **Priority:** LOW.

---------------------------------------------------------------------------------------------------------------------

## C. Fusing and overcurrent

### 9. F1: Class CC KLDR025.TXP vs UL Recognized supplemental fuse (A2 items 5-7)
- **Topic / clause:** UL 248-4 (Class CC) vs UL 248-14 (supplemental); end-product short-circuit clause and available-current level in UL 1026 / UL 858 / CSA C22.2 No. 64 /
  NMX-J-521: clause to confirm (paywalled, not read; DECISIONS ~871). Branch breaker plus Class CC F1, no inlet fuse (DECISIONS 335).
- **Design now:** F1 = Littelfuse KLDR025.TXP, 25 A time-delay, 600 Vac / 200 kA, UL Listed E81895, CSA LR29862, $18.516 at 500; in 2 x Littelfuse 01250003H open clips (UL
  Recognized E14721, 30 A, **no voltage rating, no CSA file printed**). Continuous capacity 16.0 A at the 61 C release bay. KLDR025 clears 1,710 A^2s; copper margin 0.99 (fails copper by 0.7 % at
  105 C per DECISIONS 1088). Fault-current bound 4.7-8.4 kA at 127 V + 10 %; 200 kA rating makes it moot (23.8x).
- **Assumed:** STRICT on interrupting rating (Listed Class CC). RELIANT on (a) open PCB clips accepted for a Class CC fuse and their temperature rise at 15 A, and (b) F1 never
  interrupting 15-25 A overloads: the 15 A plug and cord rest on the branch breaker plus a firmware current estimate (finding #11; entry 11).
- **If the lab disagrees:** clips: swap to a Class CC holder / block (layout stage, power board; enclosure fit). Opposite direction: if the lab accepts a UL 248-14 Recognized
  fuse (Bel 0ADEC9250-BE) the gain is -$18.86 per board and copper margin 0.99 -> 3.61 (BOM + clip footprint, layout stage). A 6.3 x 32 fast-acting F1 would save $26-30 and
  reverses Class CC (needs this answer first). F1-CERTIFIER.md is stale (names MDA-25-R); rewrite before sending.
- **Priority:** MED, HIGH if clips are refused (footprint change at the mains inlet).

### 10. F2 (blower tap fuse) and R130
- **Topic / clause:** UL 248-14 Recognized supplemental fuse, Schurter UMT-H 3403.0279.23, 3.15 A T, 1500 A at 277 VAC (cURus E41599). Clause to confirm.
- **Design now:** F2 sits on J11 behind F1 for PS3 (blower supply). R130 AC05000001507JAC00 limits fault current; not UL-recognised, overload / fail-open behaviour unstated
  (Vishay's AC05-CS is the UL variant). Pulse stress 0.54 (current-limiting estimate) to 0.94 (3x melting) of capacity, chart read by eye +/- 25 %.
- **Assumed:** a supplemental fuse behind F1 and an unrecognised limiter are acceptable given the abnormal test. RELIANT.
- **If the lab disagrees:** swap R130 to AC05-CS or a fusible resistor (BOM-only), power board.
- **Priority:** MED.

### 11. Abnormal operation with the firmware current limit defeated (A2 item 9)
- **Topic / clause:** UL 1026 / UL 858 abnormal-operation test; clause to confirm. IEC analog: clause 19 (not cited by number for this case).
- **Design now:** no hardware line-current sensing; the <= 15 A input limit is a firmware estimate (`firmware/components/power/input_limits.{c,h}`): hold 11.1 A power-stage,
  trip 12.45 A, e_est 10 % provisional (DECISIONS 2026-10-08; aux allowance B11 applied, bench RMS check open: `output/temper-aux-load-r1/BENCH-RMS.md`). F1 never opens at 15-25 A.
  External review finding #11: "If it fails, add hardware line-current sensing or fit a larger J1".
- **Assumed:** the lab will accept the branch breaker plus a firmware estimate, or will not defeat the firmware limit. RELIANT.
- **If the lab disagrees:** a line-current sensor (new sense channel, layout stage on the power board, and an interface change to the controller) or, as the review noted, a
  protection that works without firmware. This links to entry 13.
- **Priority:** HIGH (the only item here that is plausibly an architecture change).

---------------------------------------------------------------------------------------------------------------------

## D. Protective electronic circuits, firmware, and stuck-on

### 12. Protective electronic circuit (PEC) status, dormant faults, shoot-through (A4, FMEA section 7 Q1-Q7)
- **Topic / clause:** IEC 60335-1 19.11 (PEC), 19.11.2 (fault conditions), 19.11.3 (PEC component faults), 19.13 (outcome after fault); UL 1026 / UL 858 equivalent: clause to confirm.
  `PS/validation-results/11-candidates/c24-monitor-fmea/FMEA.md` section 7; stage-47 and S16-B refreshes (`fmea-s47-2026-10-15`, `s16-fmea-b-2026-10-15`).
- **Design now:** the F6 rail-window monitors (TL431B + LM2901B per rail, 3 domains) feed ISO6721FB / CA-IS3720 isolators, BIAS_GOOD, DIS = NAND(PERMIT, BIAS_GOOD) per leg. One dormant
  chain exposure of 13.0 FIT-rails (chain) plus a front end of 6.3; S47 total 19.29 FIT-rails. Dormant single faults that hide all rails exist (U40 stuck high; U22/U23 stuck low
  also defeats PERMIT). U5 (REF25) has undetected fail-dangerous modes (open pin moves OVP 280 -> 341-375 V, OCP to 113-124 A), mitigated by B13 H1 (REF25 watchdog, built)
  and H2 (BIAS_GOOD read-back with a firmware POST, inert until the controller routes J4.1 to GPIO35), plus EOL pads. Shoot-through "cleared by F1, BR1 sacrificial" (DECISIONS 839-848).
- **Assumed:** one-fault-at-a-time (19.11) is enough and the dormant-fault exposure is acceptable (RELIANT); the ISO6721FB barrier short may be excluded as functional insulation
  (RELIANT, FMEA Q4); shoot-through ending at F1 / BR1 failing is a 19.13 pass (RELIANT, Q5); a <= 90 us response is fine (Q6). Field detection of dormant faults is partial: H3-H5 EOL
  tests screen ~91-94 % of dormant FIT present at manufacture and 0 % of random field failures (S47).
- **If the lab disagrees:** a "detect dormant faults" expectation means a periodic self-test of the monitor front end (H6: isolator swap and switches in three islands, 45 % coverage,
  layout stage across three isolation islands, power board) and firmware POST work. A "no" on shoot-through containment means a catch circuit / FC1 (D-31 named one; the build has none): new board stage.
- **Priority:** HIGH.

### 13. Software in safety functions: does any protection rely on firmware? (UL 60730-1 Annex H / UL 1998 Class B?)
- **Topic / clause:** UL 60730-1 Annex H (software for safety-related controls, Class B) and UL 1998 (software in programmable components). **Neither is cited anywhere in the PS records; the only
  related citation is FMEA section 7 Q2 ("IEC/UL 60730-1 Annex H class-B-style periodic test"). Applicability to this appliance: clause to confirm.**
- **Design now:** hardware-only vs firmware-involved, from the records:

  | Protection | Hardware-only? | Evidence |
  |---|---|---|
  | R5 Kelvin OCP (OCP_OK), OVP U7 280 V, HOT5 UV (U14), tank-CT +/-55 A (u_ct_pos / u_ct_neg) -> BUS_FAULT -> J4.10 -> interlock latch -> PERMIT low | Yes (comparators, isolator, latch) | FAULT-INTERFACE.md truth table; CTRL README interlock table |
  | Gate drive disable: DIS = NAND(PERMIT, BIAS_GOOD); rail-window monitors; default-high isolators | Yes | FMEA.md sections 1, 6; DECISIONS 71 |
  | Heatsink HS_FAULT, coil COIL_FAULT, RTD window, runaway band 296.6-319.1 C, RAIL_OK -> interlock | Yes (comparators and glue; MAX31865 supplies the RTD reading) | CTRL README table; CTRL DECISIONS C6 ("hardware is the backstop") |
  | Host supervisor TPS3823 (WDI not toggled within 0.9 s min) -> interlock | Hardware supervisor of the MCU, but WDI is toggled by firmware | CTRL README table; interlock INTERFACES.md |
  | PERMIT = interlock latch AND RUN_EN (GPIO14, 4.7 k pull-down) | Firmware can only remove permission; reset needs a host RESET_N edge | firmware/README.md line ~48 |
  | 15 A line current limit (estimate, e_est 10 % provisional) | **Firmware only** | DECISIONS 2026-10-08; finding #11 |
  | 22 A tank ceiling, no-pan clamp, `N21_FAULT_TANK_RMS` latch | **Firmware only** (and a creepage argument leans on it, entry 3) | DECISIONS coil-voltage 28 A update |
  | Pan overtemp / thermal runaway first line (300 C, 15 C/s), fan failure, probe faults, pan detection | Firmware first line; hardware backstop for runaway, heatsink, coil | CTRL DECISIONS C6; firmware/README.md Safety Features |
  | Bias read-back POST (BIAS_GOOD low with PERMIT low, high 2 ms after RUN_EN) | Firmware | firmware/README.md "BIAS_GOOD read-back" |
  | TCO loop J3 removes PS2 (all gate drive, HOT5, OCP_OK) | Hardware (thermal switch) | S15; DECISIONS 103 |

- **Assumed:** the safety-critical cut (overcurrent, overvoltage, shoot-through, over-temp backstops, stuck-on via TCO) is independent of firmware, so software is "not relied on for safety"
  and no Class B evaluation is needed for the MCU. STRICT for the faults the hardware list covers. RELIANT for the two firmware-only rows: the line-current limit and the tank ceiling,
  which are protections of cord / J1 and of insulation working voltage, respectively. The HW list is also not the S15 stuck-on case (entry 14).
- **If the lab disagrees:** if a firmware-only protection is deemed safety-related software: Class B treatment of the ESP32-S3 firmware (process, tool and library evidence, possibly a
  certified MCU or a second independent hardware cut) is a controller-board and process change. For the line-current limit, a hardware sensor (power board, entry 11); for the tank ceiling, the
  >= 36.2 kHz floor / >= 0.465 uF bank fallback (firmware / BOM, entry 3).
- **Priority:** HIGH (an MCU or firmware-process change is the most expensive possible answer; ask early).

### 14. Stuck-on stage: UL 858 25.3.1 (S15)
- **Topic / clause:** UL 858 25.3.1, "safe with the solid-state control dead or stuck" (OPEN-ITEMS S15). UL 1026 equivalent: clause to confirm.
- **Design now:** the firmware-independent trips (R5 Kelvin OCP, U7 OVP 280 V, BIAS_GOOD heartbeat, BUS_FAULT -> interlock -> DIS) all act on faults. **A stage stuck on at normal current trips none of them.**
  The only firmware-independent cut for that case is the TCO loop (J3): opening it removes PS2, and with it all gate drive, HOT5 and OCP_OK (DECISIONS 103; external review #6). The TCO removes
  gate drive, not the power path: the bus stays live while plugged in. The TCO rating and mounting are provisional (S15), "set from measured glass and sink temperatures"; J3 is a JST VH
  unshrouded 3-pin with post 2 omitted (5.22 mm copper gap, 250 V 10 A; use VHR-3M, line voltage across the pins when the TCO opens).
- **Assumed:** a single TCO, in series with PS2's AC feed, counts as the independent backstop. RELIANT (the TCO is one means; it is a thermal, not a current or logic, protection and acts after
  a temperature rise). Whether PERMIT needs an MCU watchdog is listed as open in S15 (owner column "controller").
- **If the lab disagrees:** what a lab would plausibly want, none of which is decided in the repo (my inference, flagged as such): a **second independent means**, e.g. (a) a series
  mains cut that a hardware path can open (relay / contactor driven from the interlock, new power-board parts and layout at the inlet), (b) a gate-drive hardware watchdog that opens on a stuck-on
  duty (e.g. a second heartbeat), or (c) a second TCO in the PS2 path or one on the coil as well as the sink (BOM + enclosure mounting). Variants (a) and (b) are layout stage on the power
  board; (c) is BOM plus enclosure.
- **Priority:** HIGH (a true architecture question with no design margin today).

### 15. TCO rating and mounting
- **Topic / clause:** thermal cut-out (non-resettable?) rating and position for the 25.3.1 backstop; clause to confirm.
- **Design now:** rating and mounting provisional (OPEN-ITEMS S15, item 2 of the next-steps list); the TCOs sit on the sink (SELV sink NTC and TCOs "fine because the sink is
  PE/controller", `owner-items/m11/RECOMMENDATION.md`); wire class: 105 C harness. Owner: choose TCO so it opens before the pan or glass is damaged with the stage stuck on at the ceiling.
- **Assumed:** it opens early enough (not demonstrated; needs the measured stuck-on thermal case). RELIANT.
- **If the lab disagrees:** a different trip temperature or a position change on the sink / coil: enclosure and wiring (J3 harness), no board layout change unless J3 moves.
- **Priority:** MED.

---------------------------------------------------------------------------------------------------------------------

## E. Isolators, supplies and other approvals

### 16. Isolator approvals and CMTI (S6)
- **Topic / clause:** UL 1577 (component isolation, "single protection" vs reinforced), VDE 0884-17 / IEC 60747-17; CMTI rule 1.5 x dv/dt (the repo's own, `06-controller-interface/cmti/README.md`);
  no standard cited for CMTI itself. Clause to confirm.
- **Design now:**
  - 2EDR8259X U1/U2: VIORM 1767 V reinforced, cert 40055138; CMTI 150 V/ns (characterisation, not production-tested); 3.0x the s42 49.7 V/ns edge; **no channel-to-channel rating** (3.3 mm creepage).
  - CA-IS3720HW U9/U32 (reinforced, VIORM 1414, UL 1577 E511334, VDE 40057278, TUV CB; **no CSA certificate listed**; single source Chipanalog).
  - ISO6721FBDR U43/U44: basic only, VIORM 637 V, UL 1577 E181974 single protection, CSA 220991; used as the HS-LS functional crossing. 100 V/ns min = 2.0x.
  - AMC1311B U4: reinforced, 100 V/ns min = 2.0x. VOL628A U36: CTI 275, UL 1577 E76222, no published CMTI.
  - RECOM R24C2T25 U41/U42: "reinforced" 5 kVAC, but the table cites no standard; UL file for RECOM E542996 not yet looked up (packet item 15).
  - S6: CMTI 1.5x rule not met on FILTERED / OPEN rows (1.05x). At the maximum-Qrr basis the nearest tested network reads 106 V/ns, giving 1.41x (2EDR), ~1.06x (CA-IS / ISO6721FB). That maximum-Qrr
    measurement is an open D-8 bench item. NSi822xW was rejected (no open-input state).
- **Assumed:** the repo's 1.5x CMTI rule is a design preference not a certification requirement (RELIANT); UL 1577 plus VDE 0884-17 certificates substitute for appliance-standard
  approval at component level; basic ISO6721FB is acceptable as functional (RELIANT, FMEA Q4).
- **If the lab disagrees:** basic-only isolator rejected: swap to reinforced (BOM + pin-compatible, layout stage if footprints differ), power board; CMTI: filter change or isolator swap (BOM, layout stage).
- **Priority:** MED.

### 17. Supply module approvals: UL, not IEC-only (A3 items 14-15)
- **Topic / clause:** UL 62368-1 / IEC 61558 / IEC 60601-1 modules in a UL 1026 end product: acceptance as components. Clause to confirm.
- **Design now:** PS2 (on board, TCO-switched) MPM-20-24: approvals verbatim "IEC 60601-1:2005+A1, TUV EN 60601-1, ANSI/AAMI ES60601-1, CAN/CSA C22.2 No. 60601-1 and IEC 60335-1 (Dekra)";
  2 x MOPP; **prints no UL/CSA file**. PS3 (off-board, controller side, J13) MPM-65-15ST: IEC / ES / CSA 60601-1 per DECISIONS 1526; no UL file (S1 row: "no UL file"). The old
  IRM-20 / IRM-60 carried UL 62368-1 (OVC II). Datasheet leakage maxima, not measurements (A1 item 2). Other files not yet looked up: Chipanalog E511334 (U9/U32), RECOM E542996 (U41/U42).
  PS2 ledger gap: an older distributor copy lists a UL mark (truncated in the ledger); verify on a primary sheet. Product surge: the module is tested alone to 1 kV L-L; a 2 kV product test
  relies on RV1 / L1 ahead of it.
- **Assumed:** a UL-compliant lab accepts IEC / 60601-1-approved modules under a component evaluation (RELIANT; this was the explicit "Reverses if" of DECISIONS 50: "the certifier rejects the MPM approval basis").
- **If the lab disagrees:** revert to UL-listed supplies (IRM-20 / IRM-60): +leakage (0.653 mA with module Y kept; 0.324 mA with an IRM-60 in PS3) which breaks the 0.25 mA budget and re-opens entry 6,
  plus a PS1-type footprint and EMI rerun. BOM + layout stage for PS2 (footprint compatible: case 219A), controller / harness change for PS3.
- **Priority:** HIGH (it can undo the S1 fix).

### 18. PS1 / PS3 SELV controller powered from a chassis Class II module through a 292 mm harness (A3 item 16)
- **Topic / clause:** SELV classification and double / reinforced insulation of the supply chain; clause to confirm. D5-BASIS.md calls the domain "earthed ELV, final classification by the lab".
- **Design now:** PS1 deleted at s38; the controller merges J13 into its logic rail (CONTROLLER-REQUEST addendum 2). PS3 is off-board (MPM-65-15ST, Class II).
- **Assumed:** acceptable (RELIANT).
- **If the lab disagrees:** supply relocation: controller board and enclosure; the power board is unaffected apart from J4.1.
- **Priority:** MED.

### 19. Mains terminals, connectors and PE bond
- **Topic / clause:** J1 Phoenix MKDS 5/2-9,5 (UL/cUL Recognized E60425, 30 A, 300 V; "UL Product iQ returned 403"); J3 JST VH (E60389 / LR20812, recognised current not read); J6 Phoenix 1704004 (verified);
  R38 functional bond; chassis PE direct to the stud. Earth continuity (E1b <= 0.1 ohm at 25 A) is a test, clause to confirm.
- **Design now:** J1 is rated 30 A UL, which protects F1's 25 A. Cord PE bonds to the chassis, J6 carries Y-cap leakage only (DECISIONS M14).
- **Assumed:** recognised components accepted (RELIANT on file lookups not yet done).
- **If the lab disagrees:** connector swap (BOM, layout stage if footprints change).
- **Priority:** LOW.

---------------------------------------------------------------------------------------------------------------------

## Ranked: the questions most worth paying the lab to answer first

1. **Stuck-on / 25.3.1 (entries 14, 15):** is the TCO alone an acceptable independent cut, or is a second independent means required? Biggest architecture risk, no margin today, and a "no" adds parts and an inlet-area layout change.
2. **Software in safety functions (entry 13):** does the lab consider the firmware-only protections (15 A line-current estimate, 22 A tank ceiling) safety-related, and does UL 60730-1 Annex H / UL 1998 Class B apply to the controller? A "yes" drives the MCU and the firmware process.
3. **Supply module acceptance (entry 17):** are IEC 60601-1-approved MPM-20-24 / MPM-65-15ST acceptable as components with no UL file? A "no" returns the leakage budget to over-limit and re-opens the S1 fix.
4. **Touch-current basis (entry 6):** limit class (portable 0.5 vs stationary 0.75 mA), test voltage and meter network, datasheet-max vs measured module leakage, PS2 in the PE path. The design has an 8.8 uA margin to its own budget.
5. **Working voltage on the coil lanes and RES_A (entries 1, 3):** line-cycle RMS vs carrier-crest RMS, PD2 for the potted winding; a crest-RMS answer is a board-wide re-layout.
6. **PEC status and dormant faults (entry 12):** is the F6 monitor plus DIS path a PEC; is one-fault-at-a-time enough; may the ISO6721FB barrier short be excluded; is shoot-through ending at F1 / BR1 acceptable (19.13)?
7. **Inner-layer solid insulation and laminate (entries 2, 5):** do same-layer inner paths count as solid insulation (2 mm, 29.3), and is KB-6164 / PLC 3 with 2 oz inner copper accepted as the laminate evidence (S12)?
8. **F1 and abnormal overload (entries 9, 11):** Class CC F1 in open PCB clips, "branch breaker plus F1, no inlet fuse", and the abnormal test with the firmware limit defeated.

Not listed but cheap to add to the same email: Y1 approval sheets (7), RV1 and X-cap bleed (8), connector files (19).

---------------------------------------------------------------------------------------------------------------------

## Email-ready summary (placeholders; no recipient address)

Subject: Quote request for a preliminary design review: 120 V countertop induction cooktop

Hello [NAME], I am [YOUR NAME] at [COMPANY] ([PHONE / EMAIL]). We are developing a cord-and-plug (NEMA 5-15P, 120-127 V~ 60 Hz, 15 A) countertop induction cooktop for the US, Canada and Mexico,
and intend to certify it to [UL 1026 / UL 858 / CSA C22.2 No. 64 / NOM, to be confirmed with you]. Before we release production boards, we would like a quote for a paper-based preliminary design
review of the power board (a 4-layer PCB with a full-bridge resonant inverter, mains front end with a Class CC fuse, TCO-switched gate-drive supply, rail-window monitors and a hardware interlock)
and its schematic, BOM and datasheet ledger, with a written answer to a short question list. The list covers the applicable standard and clause for each point; the thermal cut-out as the independent
backstop for a stuck-on power stage; whether any firmware-based protection (a line-current estimate and a coil-current ceiling) triggers UL 60730-1 Annex H or UL 1998 treatment; acceptance of
IEC 60601-1-approved supply modules as components; touch-current limit class and measurement basis (our design is at about 0.24 mA against 0.5 mA); creepage and working-voltage basis for the coil and
resonant-bank nets; solid-insulation treatment of inner PCB layers and the laminate's UL recognition and CTI; protective-electronic-circuit status of our gate-bias monitor; and acceptance of a
Class CC fuse in open PCB clips. Please tell us your fees and lead time, what documents you need from us, whether you can review before a physical sample exists, and whether a follow-on evaluation
could build on this review. A written scope and a call with [ENGINEER / CONTACT, if available] would be welcome. Thank you, [YOUR NAME], [COMPANY], [PHONE / EMAIL].

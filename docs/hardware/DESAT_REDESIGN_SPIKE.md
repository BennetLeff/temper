# DESAT Redesign Spike

**Date:** 2026-07-26. **Status:** feasibility spike — no `elec/`, `pcb/`, or
BOM files touched. Answers the question `DESAT_DECISION_BRIEF.md` left open:
what would closing the DESAT gap actually take, and is it worth it.

**Read against this doc's own claims, not assumed:** `IGBT_DESATURATION_PROTECTION.md`
now has **four** confirmed errors, not the two the decision brief found —
UCC21551 has no DESAT pin, UCC21553 is not a real TI part, its blanking-time
algebra self-contradicts, and **its recommended blocking diode, STTH1R06, is
a 600V part** (ST datasheet, `stth1r06-y.pdf`), not the 1200V part the doc
claims. It also draws the high-side DESAT comparator sharing a ground with
the ESP32 — impossible, since the high-side sense node floats on the
switching node up to +340V. Nothing from that document is reused below.

## The four uncovered faults (from the decision brief)

1. Shoot-through (both IGBTs conducting)
2. Gate-drive failure (lost bootstrap/negative bias, partial enhancement)
3. Device-local shorts (a fault at one switch, not the tank/bus)
4. Speed: a hard short outrunning OCP-01/02's shunt→amp→comparator→logic chain

## Route A — DESAT-capable isolated driver

### Candidates (datasheets read directly, PDFs fetched and parsed)

| Part | DESAT pin | Threshold | Isolation | Package | Response | Notes |
|---|---|---|---|---|---|---|
| TI **UCC21710** | `OC` (shared w/ SenseFET, shunt) | programmable, not separately named | 1.5 kVRMS working / 5.7 kVRMS UL1577 | SOIC-16 DW, 10.3×7.5mm | not separately tabled | Older gen; DESAT is one mode of a generic OC pin |
| TI **UCC21732** | `OC` (same style as 21710) | programmable | 1.5 kVRMS working, SiO2 isolation | SOIC-16 DW | not separately tabled | Newer isolation tech, same OC-pin limitation |
| TI **UCC21750 / -Q1** | `DESAT`, dedicated pin | **8.5–9.8V, 9.15V typ** | 1.5 kVRMS working, 5.7 kVRMS UL1577 withstand, reinforced per DIN EN IEC 60747-17 | SOIC-16 DW, 10.3×7.5mm, ≥8mm creepage/clearance | **t_DESATOFF 150–300ns (200 typ)** to 90% OUTL; t_DESATFLT 400–750ns to report FLT | Strongest candidate — see below |
| Infineon **1ED020I12-F2** | confirmed has DESAT (Infineon community KB + product listing) | ~9V typ (industry-standard IGBT DESAT ref, per Infineon KB text) | not independently re-verified | not independently re-verified | not independently re-verified | Real part, but I did not get a readable datasheet PDF — figures here are **UNVERIFIED** beyond "has DESAT" |
| Broadcom **ACPL-333J** | `DESAT` pin, dedicated | **6.5V** (datasheet text, via Broadcom's own doc page) | 3.75 kV isolation | 16-pin SOIC | FAULT within 0.5µs of DESAT threshold crossing | Optocoupler-based — needs LED drive current per channel from primary side, unlike capacitive-isolation TI/Infineon parts. Numbers sourced from search-surfaced Broadcom text, not a directly-read PDF table — treat as **medium confidence** |
| Broadcom **ACPL-339J** | ruled out | — | — | — | — | Not a fit: it's a dual-*output* buffer interface for one switch (drives external N/PMOS with one shared DESAT sense), not two independently-sensed IGBTs |

All are **single-channel** — two required per half-bridge, confirming the
prompt's premise.

### Strongest candidate: TI UCC21750 (industrial) / UCC21750-Q1

Full electrical table from `ucc21750-q1.pdf` (SLUSDH9D, Sep 2019, rev Nov
2023) §6.8–6.10:

| Parameter | Value | Source |
|---|---|---|
| V_DESAT threshold | 8.5 / 9.15 / 9.8 V (min/typ/max) | §6.8 DESAT PROTECTION |
| Leading-edge blank (t_DESATLEB) | 200 ns typ | §6.8 |
| DESAT deglitch filter | 50/140/230 ns | §6.8 |
| DESAT → OUT(L) 90% (soft turn-off start) | 150/200/300 ns | §6.8 |
| DESAT → FLT pin low (report to primary) | 400/580/750 ns | §6.8 |
| Soft turn-off current | 250/400/570 mA | §6.8 |
| VDD–COM (output bias) range | 13–33 V, bipolar allowed | §6.3 |
| VCC (primary logic) | 3–5.5 V | §6.3 |
| CMTI | 150 V/ns min | Features |
| Isolation | 1.5 kVRMS working (VIOWM), 5.7 kVRMS UL1577, 2121 Vpk repetitive, reinforced per DIN EN IEC 60747-17 | §6.6–6.7 |
| Package | SOIC-16 DW, 10.3×7.5mm, >8mm creepage/clearance | §5, §6.6 |
| PWM interlock | Output forced low if both IN+ and IN− high (hardware, Fig 9-2) | §9.2.2.2 |
| Bonus | Isolated AIN→APWM analog channel for temp/DC-bus sensing | §9.2.2.7 |

### Analysis

| | Finding |
|---|---|
| Parts added | 2× UCC21750 replace 1× UCC21550BDW (net **+1 driver IC**). Each channel still needs its own external DESAT front end — **HV blocking diode + current-limit R + blanking cap per switch** (TI's own app note, §9.2.2.6: "a standard desaturation circuit can be applied to the DESAT pin"). Route A does **not** eliminate that discrete network — it eliminates the external comparator, reference, and latch, replacing them with what's inside the driver. Net: ~2 diodes, 2 R, 2 C added; 1 driver IC added; external comparator/latch/reference removed relative to Route B. |
| Board area | Both packages are the same family (SOIC-16W, ~10.3×7.5mm) as the existing `UCC21550BDW` (`SOIC16W_Isolated` footprint, `components.ato:29`). Going from 1 to 2 of the same-size IC, each needing its own bypass network and isolation clearance, in the HV-adjacent region that already regressed on the CST3015 swap (completion 0.7857→0.7738, shorts 120→142 for one transformer footprint change) is a **larger** layout disturbance, not a smaller one. No routing simulation was run — this is a qualitative estimate, **UNVERIFIED** as a number. |
| Isolated 15V bias | **Survives for the high side, unresolved-either-way for the low side.** HS today: bootstrap cap (`GateDriveHS.boot_cap`, 10µF/50V) plus a 5.1V zener creating a negative VSSA offset — the resulting VDD−VEE ≈ 15V−(−5.1V) ≈ 20.1V fits UCC21750's 13–33V VDD−COM range without changing the topology. LS today: `power_15v_ls` is already an **unresolved placeholder** (`main.ato:296-300`, "vcc_15v_ls must come from an isolated aux winding... until the transformer winding is specified, plan 005") — Route A needs exactly the same isolated LS supply the board already owes regardless of DESAT. **Correction to the prompt's premise: `UCC14140` is not the current bias arrangement.** `GATE_DRIVER_POWER_ARCHITECTURE_DECISION.md` explicitly evaluated and **rejected** it in favor of bootstrap (cost, size, duty cycle <90% doesn't need it). UCC21750's 13–33V VDD−COM input range is electrically compatible with UCC14140's 15–25V adjustable output if it were ever reinstated, but adopting Route A does not require reopening that decision. |
| Detection speed vs OCP-02 (~1µs) | **Faster, genuinely.** t_DESATOFF is 200ns typ (300ns max) to gate soft-turn-off, entirely on the secondary side — it does not wait for a round trip to the primary-side latch. FLT reporting to the MCU/logic latch (400-750ns) happens in parallel, not in series with the gate action. This is materially faster than OCP-02's ~0.92µs comparator-through-shunt chain, and it's sensing VCE at the device, not current that has propagated through the tank/bus. |
| Faults closed | **All four.** 1 (shoot-through) and 3 (device-local shorts): direct VCE sensing per device, independent of what OCP-01/02 see. 2 (gate-drive loss): textbook DESAT use case — a partially-enhanced device sits in the linear region and trips on VCE, not current. 4 (speed): the ~200-300ns on-device soft turn-off is the one thing in this repo that actually beats OCP-02's chain on the failure-origin case. |
| Effort | **Gate-drive respin, not a part swap or a day/week task.** New IC family, doubled driver count, HV re-layout in the tightest region of the board, dead-time/interlock scheme moves from `UCC21550`'s internal DT-resistor timing to firmware-timed PWM edges plus the UCC21750's hardware IN+/IN− interlock (Fig 9-2) — a different mechanism requiring re-verification, not obviously worse but not free. Estimate: **multiple weeks**, matching the decision brief's original judgment, now with parts/specs to back it instead of a guess. |
| Cert (IEC 60335-1) | Same finding as the decision brief: no specific 60335-1 clause naming DESAT was found or verified. UCC21750 carries its own reinforced-insulation certifications (DIN EN IEC 60747-17 / VDE 0884-17, UL1577) independent of the cooker's own cert — a cleaner story for a single-fault/abnormal-operation argument than Route B's discrete parts, which carry no isolation certification of their own. Still a strengthening argument, not a compliance requirement. |

## Route B — discrete DESAT front end around UCC21550

Derived independently below; the existing doc's arithmetic (§3-5 of
`IGBT_DESATURATION_PROTECTION.md`) is not reused anywhere in this section.

### Threshold

Verified IGBT data (`Infineon-IKW40N120H3-DataSheet-v01_10-EN.pdf`, rev 1.20,
Table 3): VCE(sat) typ **2.05V @ 25°C, 2.5V @ 125°C, 2.7V @ 175°C** (max only
given at 25°C: 2.4V). Note `components.ato:21` records `v_ce_sat = 1.8V`,
which does not match this datasheet at any listed temperature — worth fixing
independent of DESAT, since it undersizes any threshold margin calculation
built on it.

Using the worst-case 175°C typ (2.7V) plus a blocking-diode forward drop
(≈1–1.7V for a fast-recovery part in this class — **UNVERIFIED**, no specific
1200V/1A part was confirmed; the existing doc's own choice, STTH1R06, is
wrong per above) plus margin: a **7–9V threshold at the sense node** is
defensible and lands in the same range TI and Broadcom's integrated parts
actually use (9.15V, 6.5V respectively) — convergent evidence this is the
right ballpark, not a novel number.

### Blanking time — derived, not copied

A passive R-diode-C front end (current-limit resistor from a housekeeping
rail, HV diode to the collector, cap to emitter) has to blank the interval
between commanded turn-on and the diode discharging the blanking cap down
through the threshold. That discharge is set by `τ ≈ R_LIM × C_BLANK`, and it
trades directly against fault-condition dissipation in `R_LIM` at 340V:

| R_LIM | τ (C=100pF) | P at 340V fault | Blanking (t=τ·ln(15V/7V)) |
|---|---|---|---|
| 1MΩ (existing doc's value) | 100µs | 0.116W | ~76µs — unusable, exceeds a full 35kHz half-period (14.3µs) |
| 100kΩ | 10µs | 1.16W (transient) | ~7.6µs — still eats most of a half-cycle |
| 10kΩ | 1µs | 11.6W (transient) | ~0.76µs, but a 10kΩ resistor dissipating over 11W during a sustained fault is not something a 1206 part survives even transiently |

**A plain resistor cannot hit a fast, controlled blanking time without an
unacceptable fault-condition power tradeoff at 340V.** This is exactly why
every integrated part checked above uses a **current source**, not a
resistor, to charge/discharge the blanking node — TI's own DESAT PROTECTION
table gives `I_CHG = 500µA typ` for this reason (`ucc21750-q1.pdf` §6.8).

A discrete equivalent needs the same fix: a small JFET/depletion-mode
current-source (1-2 extra parts per switch, not in the original 19-line BOM)
instead of `R_LIM`. With `I≈300µA`, `C_BLANK=100pF`, `ΔV=7V`:
`t = C·ΔV/I ≈ 2.3µs`. This is:
- comfortably inside the 35kHz half-period (14.3µs) and the 305ns dead-time window doesn't apply here (blanking gates the *fault check*, not the switching edge)
- well inside the IGBT's own 10µs short-circuit withstand time (`t_SC`, IKW40N120H3 datasheet Table 2 — the device survives a bolted short for 10µs at VGE=15V)
- ~25× the IGBT's actual turn-on transient (t_d(on)+t_r ≈ 87ns worst-case at 25°C, IKW40N120H3 datasheet Table 3) — comfortable margin against false-tripping on the real switching edge
- **~2.5× slower than OCP-02's ~0.92µs chain**, not faster. This undercuts Route B's speed case specifically.

### A gap the existing doc missed entirely

The high-side DESAT front end is referenced to the **switching node**, which
swings 0–340V — it cannot share a ground with the ESP32/logic domain the way
the existing doc's schematic draws it. `main.ato`'s ground architecture
(`power_return ~ gnd`, single star point, `dc_bus_minus` on the same net)
means the **low-side** front end can share logic ground safely, but the
**high-side** comparator's fault output needs its own isolated crossing back
to the primary side — an isolator or opto per HS channel, not priced in the
original 19 lines, and not needed by Route A (whose isolation is already
built into the driver IC).

### Analysis

| | Finding |
|---|---|
| Parts added | Per switch: 1 HV diode, 1 current-source (JFET or small transistor pair, not just a resistor), 1 blanking cap, plus (HS only) 1 isolator for the fault signal. Comparator: 1 dual comparator (e.g. `TLV3202`) or reuse `TLV3201` instances, feeding the existing `fault_any_or`/latch chain if a spare input exists (per `OCP02_DESIGN.md`, spare-input capacity is already tight). Rough count: **~10-12 new parts**, similar order to the original 19-line estimate once the current-source and HS isolator are added, not fewer. |
| Board area | Smaller IC footprint delta than Route A (no new SOIC-16), but still 2× HV-referenced diode/current-source/cap networks placed near the 340V switching nodes, plus a new isolator for the HS fault signal — non-trivial in the already-tight HV region, but likely less disruptive than doubling the driver ICs. **UNVERIFIED** as a number; no layout was attempted. |
| Isolated 15V bias | Unaffected — Route B does not touch the gate-drive bias architecture at all, only adds sensing. This is Route B's one clean advantage over Route A. |
| Detection speed vs OCP-02 | With an honest current-source blanking design, ~2.3µs blanking + TLV3201 (40ns) + existing OR/latch chain ≈ **~2.4µs total — slower than OCP-02's ~0.92µs**, not faster. Sensing location (at the device) is still independent of OCP-01/02, which has value, but the speed argument that motivates DESAT in the first place is largely lost once the blanking time is derived honestly instead of assumed away. |
| Faults closed | Shoot-through (1), gate-drive loss (2), and device-local shorts (3): **yes**, same as Route A — sensing location, not speed, closes these. Speed case (4): **only partially** — it adds a sensing path OCP-01/02 don't have (useful if a fault never crosses the CT/shunt threshold), but does not deliver the sub-microsecond, ahead-of-OCP-02 protection that was the stated reason to want DESAT. |
| Effort | Not a day. Doing it correctly (current source, not a resistor; an isolator for the HS fault path; bench verification of blanking time against real dv/dt) is **on the order of a week or more** — smaller than Route A's respin, but not the "add 19 cheap parts" scope the original doc implied. |
| Cert (IEC 60335-1) | Same general-strengthening argument as Route A, weaker: the discrete parts carry no isolation/safety certification of their own, so the single-fault story rests entirely on board-level clearance/creepage design rather than a certified barrier. |

## Comparison and recommendation

| | Route A (UCC21750 ×2) | Route B (discrete, corrected) | De-scope (status quo) |
|---|---|---|---|
| Faults closed (of 4) | 4 | 3 full + 1 partial | 0 (accepted residual risk) |
| Detection speed | ~200-300ns on-device, beats OCP-02 | ~2.4µs, slower than OCP-02 | n/a |
| New parts | +1 driver IC, ~4-6 passives/diodes | ~10-12 parts, no new IC family | 0 |
| Board impact | Large — doubles driver footprint in tightest HV region | Moderate — new HV-referenced networks + 1 isolator | none |
| Bias supply | HS survives unchanged; LS already owed regardless | Untouched | n/a |
| Effort | Gate-drive respin (weeks) | ~1 week+, done correctly | none |

**Recommendation: keep the de-scope.** Neither route is a small addition —
the "add 19 cheap parts" framing in the original doc was wrong for Route B
(current-source front end + HS isolator push it past a week, and even done
right it doesn't beat OCP-02 on speed) and was never true for Route A (a
driver-family respin). Against that cost, OCP-01 is fixed and OCP-02 is
designed and blocked on one specific, resolvable item (INA240 pinout) — that
is the higher-value use of this project's one-track WIP limit right now.

**If DESAT is revisited, do Route A, not Route B.** Route B's only advantage
— leaving the gate-drive architecture alone — is bought by giving up the
speed advantage that is DESAT's actual reason to exist; a discrete front end
done honestly is not meaningfully better than OCP-02 and costs real board
area and parts to get there. Route A is more expensive but is the only
option that delivers sub-microsecond, on-device protection ahead of the
existing OCP chain.

**Conditions that would change this answer:** (1) OCP-02 stays blocked for
an extended period with no path to resolving the INA240 pinout — then the
"two independent OCP paths" story doesn't exist yet and the calculus shifts;
(2) bench or field data surfaces an actual shoot-through or gate-drive-loss
event, converting an accepted residual risk into an observed one; (3) a
certification reviewer specifically requires device-level protection for
this power class, which was not found in this session but wasn't
exhaustively searched either; (4) the board is respun for an unrelated
reason (e.g. the LS aux-winding magnetics from plan 005) — in that case
bundling Route A avoids a second HV re-layout pass later.

## UNVERIFIED

- Infineon 1ED020I12-F2 DESAT threshold, blanking, isolation, package — confirmed to exist and have DESAT via secondary sources, not a directly-read datasheet PDF.
- Broadcom ACPL-333J numeric specs — sourced from search-surfaced Broadcom datasheet text, not a fully re-read PDF table (two direct PDF fetch attempts timed out).
- A specific 1200V/1A fast-recovery diode part number and its Vf for the DESAT blocking diode (STTH1R06, the existing doc's choice, is confirmed wrong at 600V).
- Board-area/routing-completion deltas for either route — no layout or DRC run was attempted; comparisons to the CST3015 regression are qualitative.
- Any specific IEC 60335-1 clause requiring device-level (DESAT-class) protection — not found in this repo or externally in this session.

---

## Review record (2026-07-26)

**Accepted.** The recommendation — keep the de-scope, and if ever revisited do
Route A only — is well supported, and the spike corrected two things it was
given rather than accepting them.

**It corrected the reviewer's premise.** The task brief asserted `UCC14140` was
the current isolated bias supply. It is not:
`GATE_DRIVER_POWER_ARCHITECTURE_DECISION.md:19` records it as evaluated and
explicitly rejected in favour of bootstrap for the high side, with the low-side
supply still owed regardless of DESAT. Verified.

**The finding that decides the question** is that Route B, derived honestly, is
**slower than OCP-02**: a workable blanking time lands the discrete chain near
2.4 µs against OCP-02's ~0.92 µs. DESAT's entire justification is beating the
current-sense chain on speed, so a discrete implementation that loses that race
has no reason to exist. That reasoning is what makes "Route A or nothing" the
right shape of answer, rather than a preference.

**Three further errors in `IGBT_DESATURATION_PROTECTION.md`**, on top of the
two already known (UCC21551 has no DESAT pin; UCC21553 is not a real part):

1. Its recommended blocking diode `STTH1R06` is a **600 V** part, not 1200 V as
   claimed. Worth noting that this diode was among the 19 lines removed from
   the BOM — a 600 V device on a 340 V bus with switching transients was
   marginal at best, so those lines were wrong twice over.
2. Its blanking-time algebra is unworkable at 340 V with a plain resistor.
3. Its high-side DESAT comparator shares a ground with the ESP32, which cannot
   work — that node floats on the switching node to 340 V.

That document should now be treated as unreliable throughout, or retired.

**Open, and correctly flagged:** board-area and routing deltas for either route
(no layout attempted), and whether any IEC 60335-1 clause specifically requires
device-level protection. The second is the one that could still overturn the
recommendation, and it needs a standards reading rather than a datasheet.

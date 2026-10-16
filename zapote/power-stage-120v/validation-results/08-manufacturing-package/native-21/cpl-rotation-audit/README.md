# native-21 CPL rotation audit (JLCPCB assembly)

Offline audit of `fab/cpl-jlcpcb.csv`. `PROTOTYPE-LOT.md` says "check every CPL rotation in JLC's preview";
this makes that check a confirmation rather than a discovery. Nothing here was uploaded to JLC or LCSC; `fab/`,
the board and `pcb/` are untouched.

**Pass criterion: every line JLC places is classified OK / CORRECTED / NEEDS-PREVIEW with a reason**
(`audit.csv`, column `reason`). Stage 45: 347 of the 358 CPL lines are placed by JLC (BOM `Assembly` starts with `JLC` and
has an LCSC number); the other 11 are consigned or hand-assembled and are listed under `excluded` in `audit.json`.

| Class | Lines | Meaning |
|---|---|---|
| OK | 284 | KiCad rotation is what JLC needs |
| CORRECTED | 11 | non-zero offset, two independent sources agree, or a unique EasyEDA fit with datasheet-confirmed pin numbering (`sources/pin-evidence.json`); applied in `cpl-jlcpcb.corrected.csv` |
| NEEDS-PREVIEW | 52 | sources disagree, a source is missing, or polarity cannot be settled offline; not changed |

## Datasheet pin evidence (2026-10-15): U17 / U19 / U21 settled at 180

The SOT-23 conflict below (EasyEDA fit +180, DB `^SOT-23` −90) is settled per LCSC part when the datasheet confirms the
pin numbering. `sources/pin-evidence.json` holds one entry per part. The audit trusts the EasyEDA fit over the DB rule
only if three conditions hold:
1. The EasyEDA symbol's pin names equal the datasheet's pin functions, by number.
2. KiCad pad n is datasheet pin n. This is checked against the frozen netlist and recorded in the entry.
3. The fit is unique.

A TL432-numbered part (1 REF, 2 CATHODE) does not settle, and the selftest checks this.

- **C41283 TL431BIDBZR (U17 / U19 / U21):** TI SLVS543S p.4, DBZ top view: 1 CATHODE, 2 REF, 3 ANODE. That equals
  the EasyEDA pins. Pads 1 and 2 are on `<rail>.monitor-ref` and pad 3 is on the island ground.
  - At JLC rotation 180 all three pins land within 0.06 mm on their pads.
  - At 270 (the DB value), ANODE lands on the ref net and REF on ground, with about 1.0 mm pad misses. At 0 every pad
    misses by 0.95 mm.
  - **Before this, the corrected CPL carried 0 for these three lines:** the part would have been placed on the wrong
    pads unless the preview caught it.
- **The other SOT-23-family groups below can be settled the same way** once their datasheet pinouts are entered.

## Stage 31 isolators (2026-10-14)

U9 / U32 / U44 changed to Chipanalog CA-IS3720HW (C428883) / CA-IS3720LW (C2890049) at stage 31 (DECISIONS 34).
- C428883's EasyEDA footprint was fetched (lceda.cn component API, GET; `fetch_easyeda.py`'s `distill`, merged into
  `sources/easyeda-footprints.json`). The fit agrees with the DB rule (+270), so **U9 / U32 are CORRECTED 270 -> 180**.
- C2890049 returns 404 from the EasyEDA library, so **U44 stays NEEDS-PREVIEW** with the DB's 270. The LW is the same
  SOIC-16W package as the HW (datasheet s.11.3), whose footprint gives the same +270 offset, so 270 is expected; confirm
  pin 1 in JLC's preview.
- The rest of the counts in this README date from stage 19b; `audit.json` is current.

## CORRECTED (old -> new rotation)

| Designators | Footprint / LCSC | Old -> new | Why |
|---|---|---|---|
| U29, U30, U31 | SOIC-14 LM339B, C22416291 | 0 -> 270 | DB `^SOIC-` +270 and LCSC footprint fit +270 |
| U33, U34 | SOIC16W_DW0016B_HV ISO7710, C2859830 | 0 -> 270 | DB (`^SOIC-` via alias) +270, LCSC fit +270 |
| U9, U32 | same | -90 -> 180 | same offset on a -90 placement |
| U4 | SOIC-8_7.5x5.85 AMC1311, C783598 | -90 -> 180 | DB `^SOIC-` +270, LCSC fit +270 |
| U8 | SOT-23-6 SN74LVC1G10, C403721 | 0 -> 270 | DB `^SOT-23` -90, LCSC fit +270 |
| U14 | SOT-23-6 TPS3700, C33002 | 0 -> 270 | DB `^SOT-23` -90, LCSC fit +270 |

Note the SOT-23-6 sign agreement between the DB and the fit is what validates the sign convention used by the fit.

## NEEDS-PREVIEW (47 lines, 24 groups): what to look at in JLC's preview

**SOT-23 family, 28 lines, the main risk.** For these the DB (`^SOT-23` = -90 for every SOT-23-n) and the LCSC
footprint fit disagree by 90 degrees: the LCSC footprint for the part matches KiCad's pad 1 after +180, the DB says
+270 (-90). Proposed value in `audit.csv` is the LCSC one (180); the DB alternative is in column `db_rot` (270) and
drawn as a dotted green pad 1 in the render. In the preview, check one designator per LCSC; every line of that LCSC
at that KiCad rotation (0) is wrong or right together. If 180 is wrong try 270.

| LCSC | Footprint | Designators |
|---|---|---|
| C20917 AO3400A | SOT-23 | Q1, Q4 |
| C20526 MMBT3904 | SOT-23 | Q7, Q8, Q9 |
| C9421 LM4040 | SOT-23 | U5 |
| C545172 TLVH431B | SOT-23 | U16, U18, U20 |
| C10096 SN74LVC1G32 | SOT-23-5 | U22, U23 |
| C105188 TLV3201 | SOT-23-5 | U6, U7, U10, U11, U12 |
| C7836 SN74LVC1G17 | SOT-23-5 | U15, U24, U40 |
| C96028 TPS70950 | SOT-23-5 | U3, U37, U38, U39 |
| C43368 SN74LVC1G332 | SOT-23-6 | U13, U25 |

(Note C43368's LCSC footprint is +180 while the other two SOT-23-6 parts, C33002 and C403721, are +270.
Different LCSC parts carry different footprint orientations, so a per-footprint-name rule cannot be trusted here.)

**Other lines (19), no usable evidence offline:**
- No LCSC/EasyEDA footprint in the library: C126-C129 (C2162098, polarised cap, check the + marking), C3/C4 (C907949), J6 (C5481600).
- Project footprint differs from the LCSC one (pad layouts do not fit): L1, PS1, PS2, R5 (WSK2512), RV1, J2/J5/J7-J10 (Wuerth REDCUBE).
- J4 (Molex Micro-Fit, THT): LCSC footprint fits only after +180, no DB rule; proposed 180.

THT lines with an LCSC number (BR1, J1, Q2/Q3/Q5/Q6, C38-C41, J4, ...) are included because the BOM says JLC;
JLC's THT handling is separate from the SMT rotation DB, so their evidence is the LCSC footprint fit only.

## Not a rotation, but check it first: CPL Y sign

`cpl-jlcpcb.csv` has Mid Y **positive** for all 353 lines (board y-down), while the Gerbers (`Edge_Cuts` spans
Y 0 to -190) and `fab/positions-kicad.csv` (0 positive of 353) are Y **negative**. The JLC KiCad plugins write
negative Y so the CPL lies on the Gerber frame. If JLC does not auto-fix it, the whole CPL previews mirrored
top-to-bottom, and no rotation check is meaningful until that is settled. `cpl-jlcpcb.corrected-ynegated.csv`
is the corrected file with Y negated; confirm in the preview which of the two files lands parts on their pads.
This is a flag, not verified against JLC.

## Method

For each placed line, JLC rotation = KiCad rotation + offset (mod 360), top side only (there are no bottom parts).
Two sources:
1. **JLC rotation DB**: `cpl_rotations_db.csv` from matthewlai/JLCKicadTools at 500a9fff (the table the
   Bouni/kicad-jlcpcb-tools plugin also uses). Last matching pattern wins, `re.match` on the footprint name.
   `SOIC16W_...` (no hyphen) is matched through a `SOIC-` alias, reported in the `db_rule` column.
2. **LCSC/EasyEDA footprint** for each LCSC number (the JLC assembly package has the EasyEDA footprint's
   orientation at rotation 0). The KiCad pads (at rotation 0, read from the board) are fitted onto the EasyEDA pads by
   pad number, trying 0/90/180/270; the winning angle is the offset. Non-polar two-pad chips are fitted on pad axis
   only (180-degree symmetric). Polarised diodes are fitted by function (EasyEDA symbol pin names K/A against the
   KiCad library convention, pad 1 = cathode); SOD-128 (D6-D9) has only "1"/"2" symbol pins and falls back to pad numbers.
   A fit is conclusive only if rms <= 0.6 mm and the next angle is 0.35 mm worse.

Decision: both sources agree on a non-zero offset -> CORRECTED; footprint fits unrotated and the DB is silent or zero ->
OK; any disagreement, missing source or non-matching footprint -> NEEDS-PREVIEW. Standard chip footprints with no
EasyEDA entry (C728510, 1206) are OK on the no-rule/pads-along-X convention (4 lines). 255 of the 276 OK lines are
non-polar chips confirmed by pad axis.

**Controls** (asserted at every run, the run aborts if one fails): R7 (0603 resistor, 0 deg) must be OK with no
change; U14 (SOT-23-6, known -90 offset) and U29 (SOIC-14, known -90) must be CORRECTED to old-90; plus a synthetic
self-test that recovers 0/90/180/270 on a SOT-23-5 pad set, handles a vertical chip and a polarity swap, and pins DB
semantics. The audit also asserts that the board dump reproduces every CPL centre to < 0.01 mm.

## Files

- `audit.py`: regenerates everything below from `sources/` (no network, no board needed)
- `audit.csv` / `audit.json`: designator, footprint, LCSC, KiCad rot, proposed JLC rot, DB rule/offset, EasyEDA
  offset/rot, pin-1 evidence, class, reason (json also has controls, counts, the 20 excluded lines)
- `cpl-jlcpcb.corrected.csv`: fab CPL with only the 10 CORRECTED rotations changed (NEEDS-PREVIEW untouched);
  `cpl-jlcpcb.corrected-ynegated.csv`: same with Y negated (see above). `fab/cpl-jlcpcb.csv` is not modified
- `renders/<CLASS>_<ref>.png`: one per CORRECTED/NEEDS-PREVIEW line (57): KiCad pads on the board (solid, pad 1 red) and
  the EasyEDA package at the proposed JLC rotation (dashed, pad 1 blue), DB alternative pad 1 dotted green
- `extract_kicad.py` (board -> `sources/kicad-footprints.json`), `fetch_easyeda.py` (public library -> `sources/easyeda-footprints.json`):
  only needed to refresh sources
- `sources/`: `cpl_rotations_db.csv` (JLCKicadTools, MIT; data only), `easyeda-footprints.json` (pad geometry distilled from the
  JLCEDA/EasyEDA Official Library, https://easyeda.com, https://lceda.cn), `kicad-footprints.json`

Source board: `zapote/power-stage-120v/native-21/section.kicad_pcb` (untracked, generated; read from the ps-integrate
worktree, 353 footprints, rotations and centres identical to the CPL).

## Rerun

    cd zapote/power-stage-120v/validation-results/08-manufacturing-package/native-21/cpl-rotation-audit
    python3 -I audit.py            # needs matplotlib; --no-render skips the PNGs

Refresh sources (optional): `python3 -I extract_kicad.py <section.kicad_pcb>` and `python3 -I fetch_easyeda.py <raw-cache-dir>`.

## Limits

The EasyEDA footprint is a proxy for JLC's placement model; the SOT-23 disagreement shows the proxy and the DB are
not always the same, which is why those lines stay NEEDS-PREVIEW. Pin-1 for the SOD-128 diodes and every polarity
claim should be confirmed in the preview's pin-1 / polarity markers anyway. Four LCSC numbers
(C2162098, C5481600, C728510, C907949) are not in the EasyEDA library.

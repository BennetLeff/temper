<!-- provenance: commit=a0743083b4c63de43af20b8574f21cd24836686f dirty=true -->

# Independent verification of the three MPN/footprint defects reported in the isolator sourcing brief

Branch `fix/suspect-mpns`, from `origin/main` at `a0743083`. `dirty=true`
because this document is committed together with the fixes it describes; every
"before" measurement below was taken on the clean `a0743083` tree, and every
"after" measurement on the working tree that becomes this branch's commit.

`docs/evidence/2026-07-28-isolator-sourcing-brief.md` reported four incidental
defects. This pass re-derives three of them from primary sources rather than
taking that brief's word for anything, then fixes the two that are real and
the one that is real in a different way than the brief's summary table
implied.

**`pcb/temper.kicad_pcb` was not modified.**

---

## Verdicts

| # | Reported defect | Verdict | Action |
|---|---|---|---|
| 1 | `modules.ato:748` `y_cap_pe.mpn = "DE1E3KX222MA4BA01"` does not exist | **Confirmed fabricated** | Replaced with `VY1222M47Y5UQ6TV0` (Vishay VY1, Active, verified) |
| 2 | `components.ato:30` `mpn = "UCC21550BDW"` is not a TI orderable | **Confirmed** — and the inline comment that introduced it was wrong in *both* directions | Replaced with `UCC21550BDWKR` (14-pin DWK) |
| 3 | `components.ato:56-57` declare pins 12/13 that the footprint does not have | **Confirmed** | Declarations deleted; `elec/domain_manifest.yaml` updated to match |

Nothing was pattern-matched. Every replacement string was read off a
manufacturer datasheet table or a distributor product page fetched in this
session, and both are cited inline in the `.ato` source.

---

## Defect 1 — `DE1E3KX222MA4BA01` (C6, Y-capacitor, mains-referenced node to PE)

### The declared string is fabricated

Murata's DE1 part numbers carry a lead-style code followed by an
individual-specification suffix. Two Murata-authored documents, read directly:

- **`DE1E3KX222MA5BA01`** — Murata-generated datasheet
  (`https://www.farnell.com/datasheets/1694675.pdf`, footer "This datasheet is
  downloaded from the website of Murata Manufacturing Co., Ltd.", last updated
  2013-03-08). Verbatim: capacitance `2200pF ±20%`, rated voltage `250Vac`,
  notes `X1/Y1 Class Certified Products`, `Lead spacing F` = `10 ±1.0mm`,
  `L size or outer diameter D` = `10.0 mm max.`, `Product thickness T` =
  `8.0mm max.`, `Lead diameter d` = `0.6 +0.1/-0.05mm`, packing in bulk, 100
  minimum. So the `A01` suffix pairs with lead style **`A5B`**.
- Murata's current DE1/Type-KX documentation and every distributor listing use
  **`A4B` + `N01F`** (`DE1E3KX222MA4BN01F`).

The declared `A4B` + `A01` is a splice of the two. Targeted searches for
`"DE1E3KX222MA4BA01"` and `"DE1E3KX222MA4B"` return no exact orderable at any
distributor — the closest hits are the `A5BA01` and `A4BN01F` parts above.
This is the `ERA-3AEB6132V` signature: internally plausible, externally
absent.

### Both real spellings are dead ends

- `DE1E3KX222MA4BN01F` — DigiKey product page 4421160, fetched 2026-07-28:
  **"Obsolete — This product is no longer manufactured", 0 in stock.** Listed
  substitute `DE1E3RA222MA4BN01F`: also 0 available.
- `DE1E3KX222MA5BA01` — Mouser's own listing for it names
  `81-DE1E3KX222MA4BN1F` as the recommended alternative, i.e. it points at the
  part DigiKey calls obsolete.

Correcting the spelling was therefore not an option; a different part was
required.

### Replacement, verified

**`VY1222M47Y5UQ6TV0`** — Vishay BCcomponents VY1 series.

Vishay datasheet **28537** (`https://www.vishay.com/docs/28537/vy1series.pdf`,
fetched and text-extracted):

- Title line: `Class X1, 760 VAC, Class Y1, 500 VAC`; features: `X1, Y1
  according to IEC 60384-14`.
- Technical-data table, 2200 pF Y5U row: part-number pattern
  `VY1222#47Y5UQ6###`, `Dmax. 12.0` mm, `Tmax. 5.0` mm, lead spacing
  `F (mm) ± 1 mm` = `10.0 or 12.5`.
- Ordering-code table: `222` = capacitance value, `M` = ±20 %, `47` = size
  code, `Y5U` = temperature coefficient, `Q` = X1/Y1 500 V (AC), `6` = lead
  wire diameter, then digits 15–17: `T` = tape and reel, `V` = inline kinked,
  `0` = 10.0 mm lead spacing.
- Approvals table (this is what the IEC 60335-1 critical-components list
  needed): Y1-capacitor CB test certificate `US-26561-UL`, VDE marks approval
  `40012673`, CSA `E183844`, CQC `CQC05001015032` — each `10 pF to 4.7 nF`
  at `500 VAC`, so 2200 pF is inside the certified range.

DigiKey product page 2824499, fetched 2026-07-28: `VY1222M47Y5UQ6TV0`,
**Active**, **365 in stock**, 2200 pF ±20 %, 760 VAC, X1/Y1, lead spacing
`0.394" (10.00mm)`, body `0.472" (12.00mm)`, through hole, Y5U.

### Electrical impact — stated explicitly, because this part is safety-critical

- Capacitance and tolerance **unchanged**: 2.2 nF ±20 %.
- Safety class **unchanged and its margin increased**: Y1 (line-to-ground,
  reinforced) at **500 VAC** where the design requires Y1 at 250 VAC. There is
  no downgrade to Y2 anywhere in this change, regardless of what the stub
  footprint's `descr` claims.
- Dielectric is Y5U (Vishay) vs E(JIS) (Murata) — both class-2 dielectrics
  with comparable capacitance-vs-temperature behaviour. For a Y-cap on an EMI
  return path this is not a functional change.
- `voltage_rating` in source is left at `250V`: it states the design
  requirement for this node, and the selected part exceeds it. This field is
  read by no script in `scripts/` (checked).

### What is NOT fixed (needs a human and a PCB edit)

The board land is `Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm`, a **5.00 mm**
pitch stub. Every 2.2 nF Y1 disc — including both real Murata spellings — has
**10 mm** lead spacing. The part does not fit the board as drawn. This is
pre-existing (the fabricated MPN's nearest real counterparts have the same
10 mm spacing), it is unchanged by this commit, and it is the same 5 mm pitch
that makes C6 measure 3.200 mm against the 8.0 mm barrier gate. Fixing it
means editing `pcb/temper.kicad_pcb`, which this task forbids. Flagged in the
source comment, in `docs/hardware/BOM.md`, and in
`docs/hardware/IEC60335_CRITICAL_COMPONENTS.md`.

---

## Defect 2 — `UCC21550BDW`, and the contradiction about which package the board is

### The declared string is not orderable

TI **SLUSE89C** (UCC21550, May 2023, rev. Aug 2024,
`https://www.ti.com/lit/ds/symlink/ucc21550.pdf`), fetched and text-extracted.
PACKAGING INFORMATION addendum, verbatim rows:

```
UCC21550ADWKR   Active  Production  SOIC (DWK) | 14  2000 | LARGE T&R  ...  21550A
UCC21550ADWR    Active  Production  SOIC (DW)  | 16  2000 | LARGE T&R  ...  UCC21550A
UCC21550BDWKR   Active  Production  SOIC (DWK) | 14  2000 | LARGE T&R  ...  21550B
UCC21550BDWR    Active  Production  SOIC (DW)  | 16  2000 | LARGE T&R  ...  UCC21550B
UCC21550CDWKR   Active  Production  SOIC (DWK) | 14  2000 | LARGE T&R  ...  21550C
```

Five orderables, all tape-and-reel. `UCC21550BDW` appears in neither this
addendum nor the §"Device Information" table (which lists the same five with
`...R`). **Confirmed: not a TI orderable part number.**

### Resolving the DW-vs-DWK contradiction — the comment was wrong, not the brief

The inline comment removed by this commit read:

> `# Fixed: was UCC21550BDWK (14-pin), now correct 16-pin DW package (temper-3q4)`

Its history is not informative: `elec/src/components.ato` enters git history
already containing that line, in `b29b4432`, a bulk file-import commit
(`git log -S'UCC21550BDW"' -- elec/src/components.ato` returns exactly that
one commit). There is no separate change that can be read for intent.

So the question was settled by counting pads, not by reading intent:

- `pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod` declares pads
  `1,2,3,4,5,6,7,8,9,10,11,14,15,16` — **14 pads, no 12 or 13**. Its own
  `descr` opens `"TI UCC21550BDWK, 14-pin DWK package (SLUSE89C, Aug 2024)"`
  and its `(footprint ...)` name and Value property are both `UCC21550BDWK`.
- The placed U7 instance in `pcb/temper.kicad_pcb` has the same 14 pads and no
  others (extracted programmatically from the footprint s-expression block).

And SLUSE89C §4 settles which package that is. Figure 4-1, "DW Package 16-Pin
SOIC Top View", shows `13 NC` and `12 NC`. Figure 4-2, "DWK Package 14-Pin
SOIC Top View", shows the identical pin list with **positions 12 and 13 simply
absent** — the numbering runs 1–11 then 14–16. Table 4-1 lists `NC 12` and
`NC 13` as DW-only pins.

The board is a **DWK** land pattern. The comment's claim that the board wanted
the "correct 16-pin DW package" is the error; the pre-existing value it
replaced (`UCC21550BDWK`) was closer to the truth but was itself not an
orderable string.

Grade and land-pattern notes:

- `UCC21550BDWKR` preserves the **B** grade — Device Information gives
  rec. VDD supply min 9.2 V for B (vs 6.5 V for A, 13.5 V for C), which is
  what the +15 V secondary rail requires. The isolation ratings (5000 Vrms
  V_ISO, reinforced) are shared across packages.
- DWK carries one rating DW does not: Absolute Maximum Ratings,
  `|VSSA-VSSB| in DWK package  1850 V` (channel-to-channel).
- SLUSE89C publishes the `DWK0014A` land pattern in two variants on the same
  drawing: `14X (2)` pads on a `(9.3)` span, "IPC-7351 NOMINAL, 7.3 mm
  CLEARANCE/CREEPAGE", and `14X (1.65)` pads on a `(9.75)` span, "HV /
  ISOLATION OPTION, 8.1 mm CLEARANCE/CREEPAGE". The board is on the first.
  Moving it to the second is a `pcb/temper.kicad_pcb` edit — out of scope
  here, and unchanged by this commit.

---

## Defect 3 — pins 12/13 declared on a footprint that has no such pads

Confirmed by the pad extraction above: `signal NC_12 ~ pin 12` and
`signal NC_13 ~ pin 13` in `components.ato` had no corresponding pads on
either the library footprint or the placed instance, and the DWK package has
no such pin numbers at all. Before this change they compiled into two real
nets: `elec/build/default.net` carried `(net (code "53") (name "nc_12"))` and
`(net (code "54") (name "nc_13"))`, each with zero pads.

Both declarations are deleted. Because `elec/domain_manifest.yaml` listed
`"12"` and `"13"` in the `hb.gate_hs.driver` isolator's `secondary` pin group,
that manifest entry had to be corrected in the same commit — see the gate
transcript below, where the domain-partition gate caught exactly that and
refused to run until it was fixed.

---

## Gate results (before → after)

| Gate | Before (clean `a0743083`) | After | Verdict change |
|---|---|---|---|
| `make netlist` | succeeds, digest `a86a8b2fd183…`, 164 compiled nets | succeeds, digest `721bc88fe42f…`, 162 compiled nets | none (the 2-net delta is `nc_12`/`nc_13`) |
| `scripts/mpn_fabrication_gate.py` | PASSED, 118 parts, 0 new violations | PASSED, 118 parts, 0 new violations | none. Allowlist **not modified**; nothing added |
| `scripts/check_domain_partition.py` | PASSED, 0 crossings / 0 barrier breaches | PASSED, 0 crossings / 0 barrier breaches | none — but see below |
| `pytest elec/validation` | 30 passed | 30 passed | none (includes the 12 UCC21550 contract tests) |
| `scripts/check_isolation_keepout.py` | FAILED, 1 violation: no `MAINS_SELV_ISOLATION_BARRIER` keepout zone on the board | FAILED, same 1 violation | none — pre-existing, reads only the PCB, untouched here |
| `pytest packages/temper-placer/tests/requirements/safety` + `.../cp_sat/test_isolation_barrier.py` | 66 passed, 1 failed: `test_temper_board_clearance_compliance`, "9 REQ-SAFE-01 clearance/creepage violations on the real board (components matched: 158)" | identical: 66 passed, same 1 failure, same 9 violations, same 158 components | none |

The last row was **explicitly confirmed pre-existing**, not assumed: the three
source files were reverted to `a0743083` (`git checkout --`, no `git stash`),
`make netlist` was re-run to the baseline digest `a86a8b2fd183…`, and the test
reproduced the identical failure — 9 violations, 158 components matched, first
violation `measured_creepage_mm=7.910025284409649` against
`required_creepage_mm=8.0`. The working changes were then re-applied from a
saved diff and the netlist rebuilt to `721bc88fe42f…`. That failure is a board
geometry problem, unrelated to any MPN string.

**One intermediate verdict change worth recording**, because it is the gate
doing its job: with pins 12/13 removed from `components.ato` but the manifest
not yet updated, `check_domain_partition.py` returned

```
=== DOMAIN-PARTITION GATE ERROR ===
Reason: isolator 'hb.gate_hs.driver' (ref U7) declares pin(s) ['12', '13'] that are not wired in the netlist at all -- stale manifest
GATE RESULT: ERROR -- not PASSED, not a violation.
```

i.e. it refused to report a pass on a manifest it could no longer trust. After
correcting `elec/domain_manifest.yaml` it returns PASSED again. Final state is
the same verdict as the baseline, reached honestly.

---

## What I did not verify

- **The isolation-barrier geometry claims** in the sourcing brief (C6 at
  3.200 mm, U7 at 7.250 mm, the 8.1 mm HV land option) were not re-measured
  here. This task changed no geometry, and `check_isolation_keepout.py`'s
  verdict is unchanged.
- **Whether the C6 land or the U7 land should be re-drawn**, and to what.
  Both are `pcb/temper.kicad_pcb` edits, explicitly out of scope, and both are
  now flagged in source comments and in `docs/hardware/BOM.md`.
- **Vishay VY1 bulk / straight-lead ordering codes.** The datasheet's ordering
  table makes them constructible; constructing one is the exact move the MPN
  gate exists to prevent, so only the code confirmed on a distributor page is
  written down.
- **`DE1E3RA222MA4BN01F` lifecycle at first party.** Reported 0-stock by
  DigiKey as the substitute for the obsolete part; Murata's own lifecycle page
  is a JavaScript application that WebFetch cannot render. Moot — it was not
  selected.
- **Receiving-inspection confirmation of the delivered part marking**
  (`21550B` for `UCC21550BDWKR`). That is a procurement step, unchanged in
  kind by this commit; `docs/hardware/UVLO_TRACEABILITY.md` was corrected to
  name the right marking string, since it previously told the inspector to
  look for `UCC21550BDW`.

---

## Files changed

- `elec/src/modules.ato` — `y_cap_pe.mpn`, with the full citation chain inline.
- `elec/src/components.ato` — `mpn`, docstring, and removal of the pin 12/13
  declarations.
- `elec/domain_manifest.yaml` — `hb.gate_hs.driver` secondary pin group.
- `docs/hardware/BOM.md` — `U_GD` and `Y_CAP_PE` rows, their correction notes,
  the long-lead-items row.
- `docs/hardware/IEC60335_CRITICAL_COMPONENTS.md` — Y-cap row (now carries
  real certificate numbers), gate-driver row, gap-list item 2.
- `docs/hardware/UCC21550_INTERFACE_CONTRACT.md` — device/package row.
- `docs/hardware/UVLO_TRACEABILITY.md` — UVL-01 part identification and the
  receiving-inspection instruction.
- `mpn-fabrication-allowlist.yaml` — **not modified.**
- `pcb/temper.kicad_pcb` — **not modified.**

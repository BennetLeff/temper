# UVLO Traceability — UVL-01 and UVL-02

**Date:** 2026-07-26
**Status:** closes UVL-01 as vendor-guaranteed. Identifies UVL-02's circuit and
flags a margin problem the source cannot see.

Both gates are fixed silicon thresholds set by internal references inside a
comparator/supervisor IC. Neither has an external divider to tune and neither
has an SPICE model in `simulation/models/`, so "UNMEASURED" was the wrong
label — it implied a gap that bench work could close. It cannot: the number
is whatever TI trimmed at the factory. The right question is "does the
datasheet number satisfy the gate," not "when do we simulate it."

All figures below were read directly from the TI datasheet PDFs (not search
summaries, not this repo's own prior citations of them), sections 5.3/5.8 of
each part's electrical characteristics table.

---

## UVL-01 — gate-drive UVLO, spec **<12.0 V**

**Part:** `UCC21550BDWKR` (**corrected 2026-07-28** — this section previously
asserted `UCC21550BDW`). TI's device table (`UCC21550`, SLUSE89C, May 2023,
rev. Aug 2024, §"Device Information") lists `UCC21550BDWR` = **DW package,
16-pin SOIC** and `UCC21550BDWKR` = **DWK package, 14-pin SOIC**. `...BDW`
with no trailing `R` is in neither that table nor the PACKAGING INFORMATION
addendum, which lists only five orderables, all tape-and-reel. Two things this
section previously got wrong: (1) `UCC21550BDW` is not orderable at all, and
(2) the board footprint is **not** 16-pin — `pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod`
and the placed U7 instance have 14 pads numbered 1–11, 14–16, i.e. the DWK
land pattern (SLUSE89C Figure 4-2 numbers DWK pins 1–11, 14–16; positions 12
and 13 do not exist on that package). The UVLO grade argument below is
unaffected: grade **B** is preserved, and SLUSE89C's Electrical
Characteristics do not split VDD UVLO by package.

The "B" in the MPN is a UVLO-threshold grade, not a package option — TI sells
A/B/C grades of this family at 5 V/8 V/12 V secondary-side UVLO. This BOM
mismatch matters again below: whichever grade is actually ordered sets the
real threshold.

**Datasheet thresholds (§5.8 Electrical Characteristics, grade B, the ordered
part):**

| Supply | Parameter | Min | Typ | Max | Unit |
|---|---|---|---|---|---|
| VCCI (primary, logic side) | UVLO rising | 2.55 | 2.7 | 2.85 | V |
| VCCI (primary, logic side) | UVLO falling | 2.35 | 2.5 | 2.65 | V |
| VDDx (secondary, output side), 8 V option = grade B | UVLO rising | 7.7 | 8.5 | 8.9 | V |
| VDDx (secondary, output side), 8 V option = grade B | UVLO falling | 7.2 | 7.9 | 8.4 | V |

**Verdict: satisfies UVL-01 with large margin at every process corner.** The
worst-case (max) threshold across both supplies is 8.9 V, comfortably under
the 12.0 V ceiling. No external circuit is needed or possible — this is a
vendor-guaranteed closure, not a gap.

**This repo's own prior citation is wrong and should not be reused.**
`docs/hardware/SAFETY_INTERLOCK_DESIGN.md` §6.1 states "VCC (low-side
supply): 7.6 V falling, 8.1 V rising" and "VCCI (isolated supply): 10.5 V
falling, 11.5 V rising." Neither pair matches any row in the verified table
above, for any grade (A/5V, B/8V, or C/12V) — the closest is grade C's typ
falling (11.5 V) mislabeled as "rising," which suggests the two numbers were
transcribed from the wrong grade and swapped. Since the gate is satisfied
regardless of which real grade is populated (worst case for grade C is 13.3 V
max, still under... actually grade C's 12.5 V typ rising / 13.3 V max would
put VDDx UVLO **above** the 12.0 V gate), **confirming the assembled part is
actually grade B, not C, is the one thing this closure depends on** — it is
a BOM/procurement check, not a bench test.

**What remains:** confirm at receiving inspection that the ordered part
marking reads `21550B` — SLUSE89C's PACKAGING INFORMATION addendum gives the
part marking for `UCC21550BDWKR` as `21550B` (the 16-pin DW parts mark as
`UCC21550B`) — and not the `A` or `C` grade; grade C's secondary
UVLO (11.7–13.3 V rising) would fail this gate outright. Everything else is
vendor-guaranteed.

---

## UVL-02 — logic UVLO, spec **<2.9 V**

### Which circuit the gate refers to

Two candidates exist in `elec/src/modules.ato`. Traced by following power-rail
connections, not naming:

- **`TPS3700` rail monitor** (`modules.ato:1469`, inside `RTDSensing`): its
  `VDD` pin ties to `RTDSensing.power`, a **locally declared 3.3 V rail**
  (`modules.ato:1267-1268`, `power.voltage = 3.3V`, asserted `+/- 10%`) that is
  filtered through a dedicated ferrite bead for the RTD instrumentation
  (`modules.ato:1324` area, "post-ferrite RTD_AVDD rail"). Its comparator
  inputs (`INA_P`/`INB_N`) are driven by a divider off `RTD_AVDD`, not off VDD
  directly — it monitors the **RTD analog supply**, a subsystem-local rail,
  not the board's general logic rail. This is the STRATEGY.md-cited 2.825 V
  candidate.
- **`TPS3823` watchdog supervisor** (`modules.ato:1862`, inside `Watchdog`):
  its `VDD` pin ties to `Watchdog.power`, and at the instantiation site
  (`modules.ato:1937,1956`) `wdt.power ~ power_3v3` — **`power_3v3` is
  `SafetyInterlock`'s own rail**, the same 3.3 V logic supply the rest of the
  fault-latch/reset chain runs on. This is the board's actual logic rail.

**The `TPS3823-33` is the intended UVL-02 circuit.** The `TPS3700` belongs to
the RTD subsystem, as STRATEGY.md already suspected; this traces it rather
than leaving it a guess.

### Datasheet threshold

TI `TPS3820/3823/3824/3825/3828` (SLVS165O, Apr 1998, rev. Mar 2025),
§6.5 Electrical Characteristics, `TPS3823-33` row, −40 °C to 85 °C column
(the ordered `TPS3823-33DBVR` is the non-extended-temperature grade):

| Parameter | Min | Typ | Max | Unit |
|---|---|---|---|---|
| V_IT− (negative-going threshold) | 2.86 | **2.93** | 3.00 | V |
| V_HYS | — | 30 | — | mV |

### Verdict: **marginal, not a clean pass**

The 2.93 V typical is the number this repo has quoted before (STRATEGY.md,
SAFETY_INTERLOCK_DESIGN.md) and it is correct — but it is **above** the 2.9 V
gate, not below it. Only the minimum-corner part (2.86–2.88 V) satisfies
"<2.9 V"; typical and maximum-corner parts (2.93 V, 3.00 V) do not. This is a
fixed-grade supervisor — the threshold cannot be trimmed with a resistor the
way OCP-01/THM-01 could. Whether "<2.9 V" is a strict ceiling or a nominal
target determines whether this is a real failure or a rounding-level
non-issue; that reading is a spec-interpretation question for whoever owns
`FUNCTIONAL_TEST_CRITERIA.md` §2.4, not something this document can resolve.

**Separately, `components.ato:468`'s own comment is wrong.** It states
`v_threshold = 3.08V # Reset at 3.08V`. No 3.08 V figure appears anywhere in
the verified datasheet table for `TPS3823-33` (or any TPS382x-33 variant at
either temperature range). The correct value is 2.93 V typ, 2.86–3.00 V
worst-case. This should be corrected in source; not done here per the
no-`elec/`-changes constraint.

### What remains

- **Decide** whether 2.93 V typ against a "<2.9 V" gate is acceptable
  (nominal-target reading) or requires a different part (strict-ceiling
  reading — no TPS382x-33 grade goes lower; the next grade down, -30, trips
  at 2.63 V typ but changes the RESET_N behavior contract elsewhere in the
  latch and hasn't been checked against it).
- Confirm at receiving inspection that the marking is `TPS3823-33` and not
  `TPS3823A-33` (same threshold, extended temperature range only — no change
  to this verdict) or a different suffix (`-25`/`-30`/`-50`, which are
  materially different thresholds).
- No bench measurement changes this: it is vendor-guaranteed silicon, and the
  question is which guarantee, not whether one exists.

---

## Review record (2026-07-26)

Independently verified before acceptance.

**Confirmed locally:**

| Claim | Check |
|---|---|
| `components.ato:468` states `v_threshold = 3.08V` | confirmed — and it matches **no** value in the TI table |
| `SAFETY_INTERLOCK_DESIGN.md:304–305` cites 7.6/8.1 V and 10.5/11.5 V | confirmed present |
| `IGBT_DESATURATION_PROTECTION.md` names UCC21551 (×5) and UCC21553 (×1) | confirmed |

**Confirmed against the TI datasheet** (SLVS165G, package information table):
`TPS3823-33DBVR → threshold voltage 2.93 V`. The repo's 3.08 V is wrong.

**Additional observation on the SAFETY_INTERLOCK figures.** Beyond not matching
a real grade row, they are internally implausible: VCCI is the *primary-side
input* supply (a few volts) yet is listed at 10.5/11.5 V, while VCC — the
~15 V output-side supply — is listed at 7.6/8.1 V. The two look transposed.
`SAFETY_INTERLOCK_DESIGN.md:313` then concludes "No external UVLO circuit is
required" from those figures.

**On the UVL-02 verdict.** The reviewer initially disputed "marginal fail",
reading `<2.9 V` as *"must trip before the rail falls below 2.9 V"* (under
which 2.93 V passes). That reading is wrong because it is **inconsistent with
UVL-01**: the same phrasing there (`<12.0 V`) is satisfied by a 7.7–8.9 V
threshold, which only works if the spec means *"the threshold shall be below
the stated value"*. Applied consistently, 2.93 V typ / 3.00 V max exceeds
2.9 V and the gate does not cleanly pass. The document's verdict stands.

**One consequence worth adding:** at a 3.00 V worst-case threshold, a 3.3 V
rail sagging 10% reaches 2.97 V — *below* the supervisor threshold. If the
logic rail is specified at ±10% anywhere in the design, this part can assert
reset during a tolerated sag. Worth checking against the actual rail
tolerance before selecting a replacement.

# IGBT Desaturation Protection — Decision Brief

**Date:** 2026-07-26
**Decision required:** design DESAT, or remove the 19 BOM lines that cost it.
**Recommendation:** **de-scope.** Reasoning below; a human should accept or
reject it explicitly before either the BOM or `IGBT_DESATURATION_PROTECTION.md`
is touched.

---

## What DESAT does

Desaturation detection watches an IGBT's collector-emitter voltage (VCE)
*while it is supposed to be on*. A healthy, saturated IGBT holds VCE near
1.5–2.5 V; if it is forced into the linear region by a shoot-through, a
shorted load, or a lost gate drive, VCE rises toward the bus voltage while
full current still flows — dissipation in the die goes from watts to
kilowatts in microseconds. DESAT senses that rise directly at the device and
disables the gate drive before the junction cooks. It is standard on
hard-switched IGBT/SiC mains inverters precisely because it is the only
protection that is co-located with the failure: it does not depend on current
having propagated to wherever a CT or shunt happens to sit.

## Does the gate driver in use support it? **No — checked against the TI
datasheet, not assumed.**

`elec/src/components.ato:27` uses `UCC21550BDW`. I read the TI datasheet
(SLUSE89C, May 2023, rev. Aug 2024) pin-function table directly: 16 pins —
`INA, INB, VCCI×2, GND, DIS, DT, NC×3, VDDA, OUTA, VSSA, VDDB, OUTB, VSSB`.
**No DESAT pin exists.** `docs/hardware/IGBT_DESATURATION_PROTECTION.md`
already states this correctly for the UCC21550.

That document then recommends "upgrading to UCC21551" as a path to integrated
DESAT. **This is wrong, and matters to the decision.** I read the UCC21551
datasheet (SLUSEW9D, May 2023, rev. June 2024) pin table directly: it is
pin-for-pin identical to the UCC21550 (`EN` replaces `DIS`; otherwise the same
16/14-pin layout). **No DESAT pin.** It is the same dual-channel family with a
different control-pin polarity, not a DESAT-capable part. `UCC21553`, also
named in that document, does not appear as a TI product at all in TI's own
catalog search — it is not a real orderable part.

TI's actual DESAT-capable isolated gate drivers are a different, single-
channel family entirely — `UCC21710`, `UCC21732`, `UCC21750` — with
integrated current-source DESAT sensing, programmable blanking, and Miller
clamp. Adopting DESAT via silicon, not a discrete front-end, means **replacing
the gate driver architecture**: one IC per switch instead of one dual-channel
IC per half-bridge, different pinout, different isolation topology, a
from-scratch schematic and layout section, and re-verification of everything
already built around the `UCC21550` (dead-time resistor, bootstrap diode,
DIS/latch wiring). That is a materially bigger job than "swap a part number,"
and the document that proposed it got the part family wrong.

The alternative — a discrete DESAT front-end (diode, blanking cap, divider,
comparator) ahead of the existing `UCC21550`'s `DIS` pin — is what
`IGBT_DESATURATION_PROTECTION.md` actually designs. That design is not
usable as written: its own body contains two abandoned, self-contradicted
derivations ("Wait, that's wrong!", "WAIT — this is too low!") before landing
on divider values. It would need to be redone, not merely implemented.

## What already exists, and what it does not catch

- **OCP-01** (tank CT + comparator): fixed 2026-07-25, trips at **50.1 A**
  (45–55 A window), sensing the resonant-tank current.
- **OCP-02** (DC-bus shunt + INA240 + comparator, `docs/hardware/OCP02_DESIGN.md`):
  designed, not yet implemented (blocked on the INA240 pinout), targets
  **60 A** trip, **<1 µs** using `TLV3201` per that document's own timing
  table — faster than the 5 µs gate requires.

Both are genuine, independent overcurrent paths — different sensing element,
different physical location, which is the point of having two. **What
neither catches, specifically:**

1. **Detection speed at the failure origin.** OCP-01/02 measure current that
   has already propagated through the tank or the DC-bus return. DESAT
   measures VCE at the device itself. In a fast short (e.g., the resonant cap
   shorting, or a bootstrap/gate-drive failure letting the high side
   partially conduct), current can rise at a rate set by loop inductance
   alone — it is plausible for the die to be well into destructive dissipation
   before the CT or shunt signal has crossed 50–60 A and propagated through
   OCP-01/02's own delay chain (comparator + OR + latch + driver, ~100–200 ns
   by the numbers in `SAFETY_INTERLOCK_DESIGN.md` §9, itself unverified on
   this board).
2. **Shoot-through specifically.** If both IGBTs conduct simultaneously, the
   fault current path is a bus-to-bus short through the two devices. Whether
   that current registers on the tank CT (which sees tank current, not
   cross-conduction current) or the DC-bus shunt depends on exact topology and
   is not established anywhere in this repo. DESAT, sensing each IGBT
   individually, does not have this ambiguity.
3. **Gate-drive loss.** A degraded bootstrap supply or lost negative bias can
   leave an IGBT partially enhanced without tripping either OCP path at all,
   since current stays below the 45–65 A window while the device still
   overheats from VCE × IC in the linear region.

These are real gaps, not manufactured ones. They are also **narrow**: the
dominant fault mode on this board (bulk overcurrent from a shorted pan load or
tank fault) is exactly what OCP-01/02 are built for, and they will both exist
once OCP-02's INA240 blocker clears.

## Cost of each option

| | Design DESAT (discrete, HS+LS) | De-scope |
|---|---|---|
| Parts | ~19 lines, ~$2.50/board raw (per the existing doc's own estimate — unverified independently, but the parts are cheap passives + 2 diodes + 1 comparator) | 0 — remove 19 BOM lines |
| Board area | 2× 1200 V-rated diodes and HV-referenced dividers per switch, placed near the 340 V switching nodes — the board is HV-area-constrained already (the CST3015 swap alone forced a re-layout and a measured shorts regression, STRATEGY.md "Rung 1b") | none |
| Design effort | Redo the reference circuit from scratch (its math is broken as committed), then verify blanking time against real switching dv/dt, then simulate, then lay out with HV clearance | none now; documented as deferred |
| Cert (IEC 60335-1) | Strengthens the abnormal-operation/single-fault position for the narrow shoot-through/gate-loss case; does not by itself satisfy a specific clause not already addressed by OCP-01/02 — I did not find or read a 60335-1 clause in this repo or externally that names DESAT specifically, so this is a general strengthening argument, not a compliance requirement | OCP-01 (fixed) + OCP-02 (designed) remain the sanctioned overcurrent/short-circuit case for cert purposes |

## Recommendation — de-scope this revision

**Remove the 19 DESAT BOM lines now.** Keep OCP-01 and OCP-02 as the
sanctioned short-circuit/overcurrent protection chain, and record the
shoot-through/gate-loss gap above as a known, bounded residual risk rather
than an unmitigated one.

Reasoning: the gate driver already in the design structurally cannot support
DESAT without a driver-family change TI does not offer within the UCC2155x
line — the one path this repo's own documentation proposed for it (UCC21551)
is factually wrong. The discrete alternative is not a implementation task but
a redesign, on a board where HV area is already tight enough that the last
component swap regressed routing. Against that cost, OCP-02 alone — once its
one remaining blocker (INA240 pinout) clears — already delivers a second,
independent, sub-microsecond overcurrent path that covers the dominant fault
mode. The residual gap DESAT would close is real but narrow, and this project
has higher-value open items (OCP-02's blocker, the BOM/source reconciliation,
OVP-01-class ambiguities elsewhere) competing for the same one-track WIP
limit. Revisit DESAT as a **next-revision** item, scoped correctly next time
as a driver-family decision (`UCC21710`/`UCC21732` vs. discrete) rather than
a part-number swap.

This is a recommendation, not a decision: a human should accept or reject it,
and either way the BOM's 19 phantom lines should not survive un-actioned.

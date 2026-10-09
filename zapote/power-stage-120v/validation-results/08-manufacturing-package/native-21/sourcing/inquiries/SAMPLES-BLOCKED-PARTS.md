# Inquiries 3–5: samples or allocation for the three parts with no stocked equivalent

Status: drafts, **not sent**. Prepared 2026-10-09 for the owner to send.

Basis: in the 2026-10-09 alternates search, none of these three parts had a stocked, functionally equivalent substitute; DECISIONS.md 2026-10-09 summarises it. Each draft asks for the approved part first and names the same-footprint fallback.

**Quantities:**
- Lot of 5 boards, 2 spares per board, as in the procurement brief.
- A 2-board bench build needs only the first number in brackets.

---

## 3. TDK: B32656G0275J000 (DC-link film), via a distributor FAE or TDK sales

> **Subject:** Sample / allocation request: B32656G0275J000 (or B32656G0275M000), 20 pcs
>
> We are building a prototype lot of a 120 V induction-heating power stage. Our approved DC-link capacitor is **TDK B32656G0275J000** (2.7 µF ±5 %, 1000 VDC, 4-pin, 37.5 × 20.3 mm). It shows no distributor stock (Mouser: non-stocked, quote only). Please quote:
> 1. samples or a small allocation of **20 pcs** (4 for a first 2-board build), with lead time;
> 2. if J000 is unavailable, **B32656G0275M000** (±20 %, same pads) under the same terms;
> 3. the typical ESL / impedance curve for the part you can supply. Our layout model uses 19.2 nH.
>
> Delivery to [address]. Thank you.

**Fallback if neither is available in time:** B32676G1905K000 (9 µF / 750 V, same pads, 547 at Digi-Key on 2026-10-09). It is a recorded deviation: the bus becomes 18.4 µF, and BUS-CAP-SCREEN, F6, inrush and LINE_ZC must be re-run before power-up.

---

## 4. Würth Elektronik Midcom: 750320775 (SN6507 push-pull transformer, WE-PPTI EP7 HV)

> **Subject:** Sample request: 750320775, 20 pcs
>
> We use **750320775** (WE-PPTI EP7 HV, 1.2:1, for TI SN6507) in a prototype induction power stage. Distributors show 0 stock, with factory lead time around 16 weeks (Digi-Key incoming March 2027). Please supply **20 pcs** as samples or a factory allocation (4 for a first 2-board build), and confirm:
> 1. the lead time;
> 2. the insulation rating that applies to this part number (functional / basic / reinforced, working voltage);
> 3. the typical and maximum interwinding capacitance.
>
> Delivery to [address]. Thank you.

**Fallback:** 750315240 (reinforced, UL E205930, 90 in stock). It needs a footprint ECO (6-pad), a ≥ 150 V rectifier, an SN6507 current re-check and an F6 rerun with Cww 18 pF (../ALTERNATES-2026-10-09.md §2).

---

## 5. Microchip: MRT130KP295CV (DC-link TVS)

> **Subject:** Sample request: MRT130KP295CV, 15 pcs
>
> We use **MRT130KP295CV** (TVS, 295 V standoff) as the DC-link clamp in a 120 V induction power stage. Distributors show 0 stock, and Microchip direct quotes multiples of 100 at about 42 weeks. Please advise:
> 1. whether **15 pcs** (3 for a first build) can be supplied as samples;
> 2. whether **MRT130KP295CVE3** is electrically identical and available sooner;
> 3. the clamping voltage at ~100 A, 8/20 µs and 10/1000 µs.
>
> Delivery to [address]. Thank you.

**Fallback:** Littelfuse AK3-380C-Y (71 in stock) or Bourns PTVS3-380C-TH. Either needs a 24.15 mm-pitch footprint ECO, with R4 moving about 3 mm. Neither vendor publishes a clamp at 100 A or long-pulse energy data, so vendor data or a bench pulse is needed before the clamp claim (../ALTERNATES-2026-10-09.md §4; DC-LINK-CLAMP.md forbids silent substitution).

---

**Not needed for these lines:** C1/C2 (now R463N410050N1K, in stock), U1/U2 (Mouser 4,540), ISO7710DW (Digi-Key 1,961), T1 (Coilcraft direct), the TDK B32654 resonant bank (Digi-Key 2,669), KLDR025.TXP (Digi-Key 88) and its 01250003H clips (Digi-Key 9,223).

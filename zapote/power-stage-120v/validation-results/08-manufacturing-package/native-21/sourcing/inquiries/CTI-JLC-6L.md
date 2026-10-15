# Inquiry 1b: laminate CTI for native-21 on six layers (and four), to JLCPCB

Status: owner approved sending on 2026-10-14 (DECISIONS 39, item 5). Question 6 was added after the Gerber quote
(DECISIONS 40), so the text changed after the approval. Not sent yet: the inquiry form needs a name and a reply address.
Send log at the end.

It replaces the unsent four-layer draft [`CTI-JLC.md`](CTI-JLC.md), whose findings still apply: every listed JLC FR-4
laminate with a findable datasheet is PLC 3 (CTI 175–249 V, group IIIa), and JLC names no laminate for a stackup ID. One
message asks about both stackups, so the answer serves whichever one is adopted (six layers is candidate 33, accepted on
the data, adoption pending).

Six-layer stack: JLC061622-1080A, 1.6 mm, 2 oz outer and inner (`native-21/stackup-6L.json`). From JLC's API it is
1080 ×3 prepreg / 0.30 mm core / 1080 + 2116 + 1080 prepreg / 0.30 mm core / 1080 ×3 prepreg, with no laminate brand
given. The Gerber job file gives 1.678 mm.

Channel: the PCB/Stencil Inquiry form ([jlcpcb.com/help/contact](https://jlcpcb.com/help/contact)), for a written record.
Live chat is the fallback, with the reply requested by email.

## Message

**Subject:** Pre-order: laminate CTI confirmation for 6-layer JLC061622-1080A (and 4-layer JLC041622-7628), 2/2 oz

> Hello JLCPCB team,
>
> We are about to order a power board and need written answers on the laminate first. It will be one of:
> - 6 layers, FR-4, 1.6 mm, 2 oz outer and inner, stackup **JLC061622-1080A** (our preferred option); or
> - 4 layers, FR-4, 1.6 mm, 2 oz outer and inner, stackup **JLC041622-7628**.
>
> The board is 290 × 190 mm, ENIG, with epoxy-filled and capped vias. It carries 120 V mains, and our safety design
> requires laminate with a **Comparative Tracking Index of at least 175 V** (material group IIIa, IEC 60112), or
> equivalently **UL PLC 3 or better (PLC ≤ 3)**.
>
> 1. **Laminate.** Which laminate brand and grade (cores and prepregs) is used for each stackup when ordered as
>    (a) "FR4-Standard TG 135-140", (b) "FR-4 TG155" and (c) Shengyi S1000-2M TG170? Is it fixed, or can it vary
>    between production lots?
> 2. **CTI.** What is that laminate's CTI per IEC 60112, or its UL 746A PLC? Please attach its datasheet or UL card if
>    possible.
> 3. **Guarantee.** Can you guarantee laminate with CTI ≥ 175 V (PLC ≤ 3) on our order? If so, how should we specify it
>    (TG option, a named material, an order remark, or UL marking with a Material Type), and is there an extra cost or
>    lead time?
> 4. **Documentation.** Can the laminate brand, grade and CTI / PLC be stated on the Certificate of Conformance or a
>    material certificate shipped with the order?
> 5. **Thickness.** Can you hold a finished thickness of **1.60–1.76 mm** on each stackup? Our through-hole terminals
>    need at least 1.6 mm.
>
> 6. **Unspecified stackup.** If we leave "Specify Stackup" at "No requirement" for a 6-layer, 1.6 mm, 2 oz / 2 oz
>    board, is the build always the stack your quote page displays for it (0.35 mm cores, two-ply outer prepreg), or
>    can it be any of JLC061622-1080 / -1080A / -1080B / -2116 / -2116A, or something else? The same question for
>    4 layers, where the page displays a 3313 / 0.96 mm core build.
>
> If neither stackup can be guaranteed at CTI ≥ 175 V, please tell us which 6-layer or 4-layer 2 oz / 2 oz stackup and
> material option can be.
>
> Thank you.

## After the reply

As in `CTI-JLC.md` "After the reply": record the date, agent and ticket in FAB-NOTE.md, put the exact wording in the
order remark and ask for it on the CoC. If JLC cannot guarantee it, D5-BASIS treats the laminate as group IIIb, and
the board needs either a fab with a specified high-CTI laminate or re-designed creepage. The certifier still has to
accept a PLC 3 rating as evidence of IEC 60664-1 group IIIa (CERTIFIER-PACKET A3).

## Send log

| Date | Channel | Ticket / reference | By | Result |
|---|---|---|---|---|

# Certifier emails A1–A6 (drafts, not sent), 2026-10-20

Send as **one email** to the lab's engineering or preliminary-review contact. Recommended lab: Intertek (ETL), via the Contact Intertek form on [intertek.com/appliances](https://www.intertek.com/appliances/functional-safety/); ask for North America household appliances, UL 858. UL Solutions is the fallback. Do not send the same email to several labs (`F1-CERTIFIER.md`). A7 (JLC) is already send-ready in `zapote/power-stage-120v/validation-results/08-manufacturing-package/native-21/owner-items/JLC-LAMINATE-QUESTION.md`. The F1 fuse questions are in `.../sourcing/inquiries/F1-CERTIFIER.md`; attach them as a second section if you want one round trip.

Fill the `[ ]` fields. Facts below come from the repo (sources in brackets); nothing is bench-measured.

**Subject:** Pre-submission questions: cord-and-plug 120 V induction cooktop (UL 858), six closed questions

> Hello,
>
> We are preparing a countertop, cord-and-plug induction cooktop for certification in the US and Canada: 120–127 V~ 60 Hz, NEMA 5-15P, 15 A input limit, one circular coil, resonant full-bridge stage, ESP32-S3 controller, glass top, built-in blower. We are at prototype stage and would like closed answers before we freeze the design. If a question is out of scope for a free pre-submission contact, please tell us which need a quoted preliminary review.
>
> **Q1 (standard).** We are working to UL 858 (and CSA C22.2 No. 61 for Canada, which we understand covers household ranges; No. 64 excludes them). Is UL 858 correct for a portable induction cooktop of this kind, or does UL 1026 or another standard apply?
>
> **Q2 (new oil-ignition clause).** Intertek's notice for UL 858 Ed. 16 lists clause 60A, a cooking-oil ignition test for induction units of 350 W or more, effective 2 August 2026. (a) Does it apply to a portable unit with one circular coil? (b) What cast-iron pan and oil are specified, and where is the pan placed? (c) Our firmware holds a frying set-point of 230 °C (pan-glass) and trips a runaway fault at about 308 °C; under 60A.8.4, is a temperature limiter built into the appliance evaluated with the specified pan, and would our limiter be evaluated as a closed-loop control or as a single-fault protection?
>
> **Q3 (supply modules).** Our two internal AC–DC supply modules are Mean Well MPM-20-24 and MPM-65-15ST. Their datasheets list IEC/EN 60601-1 and UL ANSI/AAMI ES60601 (2 × MOPP); we found no UL 62368-1 or UL 1950 file for these exact parts. Will you accept a medical-approved module as a component inside a cooking appliance, or must it be Recognized under a different standard? What documentation do you want?
>
> **Q4 (stuck-on stage).** For UL 858 25.3.1, the only firmware-independent cut for a power stage stuck on is a thermal cut-off (TCO) loop that opens the supply to the gate drivers; it does not open the mains path. Over-current, over-voltage, and bus-fault trips are separate. Is a gate-drive-only cut acceptable as the backstop for a stuck-on solid-state control, or do you require a power-path device (relay or contactor) in the mains line?
>
> **Q5 (insulation at the heat sink).** The switching devices (HOT, up to 400 V bus, tank envelope 345–362 V rms with a pan, 818 V pk worst fault) are electrically insulated from the grounded sink by aluminium-nitride tiles plus thermal compound. (a) Is reinforced insulation required at that interface? (b) On what working-voltage basis: line-cycle RMS, or carrier-crest? (c) Do you accept a ceramic of our supplier's datasheet rating, or must it be UL-Recognized?
>
> **Q6 (firmware-only protections).** Several protections are firmware-only: the 15 A line-current limit (estimated, about ±10 %), the runaway trip, and the no-pan shutoff (2.0 s; UL 858 47.8 allows up to 30 s). (a) Which of these require a hardware backup, and which can rely on software evaluated to a software class (UL 1998, UL 60730-1 Annex H, or other)? (b) For 47.8, may a pan returned within the allowed time restart without a manual reset?
>
> Happy to send a block diagram, the protection list, the state-machine table, and the stack-up drawing. Please tell us what format and under what NDA.
>
> Best regards,
> [Name], [Company], [email] · [phone]

**Attachments to prepare (all exist in the repo):** one-page block diagram (from `zapote/power-stage-120v/README.md` and `FAULT-INTERFACE.md`); protection list (`FAULT-INTERFACE.md`, `OPEN-ITEMS.md` S15); `firmware/transition_table.yaml`; heat-sink stack-up (`PWR-22`, `D5-BASIS.md`).

**Things in the email to check before sending:**
- Fry hold of 230 °C and runaway trip of about 308 °C come from the checklist (FW rows); the ignition margin is not analysed (`ASKS-AND-HEDGES.md` section 3).
- Q1's claim that C22.2 No. 64 excludes ranges is from a search result, not the standard text. Rephrase as a question if you prefer.
- Q5 numbers: DECISIONS.md:248, 257 and `owner-items/m6m10/coil-voltage-28a/`.

**Rows answered by the replies:** Q1 → CMP-01; Q2 → CMP-28, FW-16; Q3 → CMP-09, CMP-10; Q4 → CMP-12, PWR-58; Q5 → CMP-14, CMP-15; Q6 → CMP-13, FW-34.
**Chase** after 1 week. If no answer in 3 weeks, proceed on the fallbacks in `ASKS-AND-HEDGES.md` section 4.

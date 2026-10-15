# Draft DECISIONS item (candidate 35)

The number is assigned at merge. The brief named it 43, but the integration branch has since used 43 for track geometry
(`2a649f73a`). Do not paste this into DECISIONS.md from this branch.

```
4x. **Coil terminals J2 / J5 → Würth REDCUBE SMT 7466004R (stage 35, candidate 35; accepted, 2026-10-15).**
    - **What:** both coil terminals change from the THR 74650074 to the WP-SMBU SMT 7466004R (M4 internal through-hole
      thread, 50 A at 20 °C, 1.2 N·m, −55…+150 °C, tape and reel; rev 001.003, 2023-07-03).
      - Footprint: Ø8.5 / Ø5.7 copper ring round a Ø5.2 NPTH, with four paste segments.
      - Copper: 20 land vias per terminal, 0.85 / 0.3 (`patches21.add_stage35`), on stage 32's routed copper; nothing
        else moves.
      - Closes DECISIONS 42. The datasheet has no PCB-thickness limit, so the 1.6–2.0 mm conflict with JLC's ±10 % goes
        away. The order remark from item 42 can be dropped once this is the board of record.
    - **Why:**
      - JLC can assemble it: tape and reel on the standard SMT line, via Global Sourcing from DigiKey (8,856 in stock).
        The THR part cannot be wave soldered (Würth), and JLC publishes no through-hole reflow or pin-in-paste service
        (assembly capabilities page), so it would be hand-soldered and is unverified.
      - Cheaper: $206.44 against $208.08 per board at 500, and $311.47 against $313.28 at 5. One fewer hand / consign
        line and one fewer THT line.
    - **Evidence:**
      - Chain `native21s35` (board fba59ef3) gave CHAIN_DONE: DRC 0, RES_A outer F 20.393 / B 13.375 mm (unchanged),
        DFM 750 vias, FIT clean, Kelvin 67.77–116.44 A.
      - Scorecard ACCEPT against s32 (cheaper parts_usd_at_500 and hand_or_consign_lines; nothing worse) and against
        19c.
      - Necks 0.993 and OCP pickup 4.17 A, both the same as s32. Track geometry is identical to s32 (104 / 206 / 44 /
        704.4 mm).
      - `validation-results/11-candidates/c35-smt-terminals/README.md`.
    - **Model change:** task 04 (`run_board.sink_contacts`) now sinks a stud ring land, i.e. a pad with a hole and no
      drill, at 24 equipotential points on its ring.
      - Before, it used the custom-pad anchor, a single point on the ring's edge. That forced the whole terminal current
        through one point and read the SMT terminal 13–42 K hot.
      - The new model is within 1 % of sinking every node under the Ø7 body. Drilled leads (the THR, every other part)
        are unchanged (`scripts/terminal_sink.py`).
    - **Cost:**
      - Terminal copper is 0.5–3.7 K warmer than with the THR at every B3 point (c28_h25 J5 74.6 / J2 75.2 °C, against
        72.3 / 73.9). The board peak is unchanged.
      - Ledger check T: 103.45 / 150 °C at c28_h10, a gap. Contact and lug heat are a bench item.
      - The lug seat rises 2.5 mm (5.0 mm body), so the R26 coil-lead screen and the screw length go to the enclosure
        session (`ENCLOSURE-REQUEST.md`).
      - Pull rating is 300–410 N (design guide p.9); a bench pull and torque test is needed.
      - 150 µm paste at J2 / J5 needs a stencil choice.
      - The J2 / J5 CPL rows are NEEDS-PREVIEW.
    - **Reverses if:** the bench shows the soldered terminal failing the lug pull or torque, or running hotter at 28 A
      than the THR by more than the model's few kelvin; or JLC's file review refuses the part, the 150 µm paste or the
      height.
```

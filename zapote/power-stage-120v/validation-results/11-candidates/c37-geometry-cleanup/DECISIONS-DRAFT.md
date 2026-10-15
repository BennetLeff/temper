NN. **Track-geometry cleanup pass (stage 37, candidate 37; DECISIONS 43's planned fix); proved on s35, to run last
    after the island lanes merge (2026-10-15; board `1900b038f54a9b0b1effac574c0cb4aa733dc6a2a186ef6371fe360840ff7ae5`,
    copper.json `321c66db…`, schematic and frozen netlist unchanged from s35, Gerber ZIP `f6756eba…`; tag `native21s37`;
    `11-candidates/c37-geometry-cleanup/`; layout only).**
    - **What:** `native-21/layout/track_cleanup21.py` is a post-route transform of a finished copper.json. Its obstacle
      model is the export of the board built from that copper (pad shapes, fills, outline), and it refuses any other
      export. In order, each step repeated to a fixpoint:
      - fold-backs: a free tip is removed; a tip on a pad or via is de-duplicated;
      - acute corners: opened by an octilinear tangent mitre, or at pad / via tips by a square T;
      - right angles: mitred to 2 × 135°, with a leg of 3 × the width and at least 0.5 mm, down to the width;
      - any-angle segments: replaced by octilinear doglegs.
    - **Edit checks:** an edit is kept only if:
      - its added copper clears every other-net item and fill under rules21 + 0.02 mm;
      - it is no closer than before to the other side of the barrier or the RES_A 12.6 mm pair;
      - no fill can grow near the barrier or into the SELV-spine region;
      - the net's KiCad-rule connectivity partition is unchanged;
      - the geometry counts improve in severity order.
      res_a and the OCP sense nets are never edited. Pads, vias, zones, widths and parts never move. There are 45
      controls in `test_track_cleanup21.py`.
    - **On s35:** 625 edits.
      - Right angles 104 → 50, acute 206 → 23, fold-backs 44 → 3, any-angle 704.4 → 308.4 mm.
      - Track length −101.9 mm.
      - Chain CHAIN_DONE:
        - DRC 0 / 0 with the s35 warning set;
        - barrier 0; RES_A outer F 20.393 / B 13.375; D5 8.047 / 8.507 (all unchanged);
        - DFM 750 vias; SPINE_LOCK PASS; FIT clean;
        - Kelvin 67.77–116.44 A; necks 0.993; OCP pickup 4.17 A;
        - task 04 within 0.011 %;
        - B3 ratings margins −56.3 / −38.8 K (s35 −56.4 / −38.9).
      - Scorecard ACCEPT against s35 (better on the four geometry metrics and both B3 margins, nothing worse) and
        against s32. Against 19c it is ACCEPT; s35 was REJECT there, on item 43's ratchets only.
      - A second run on the s37 export makes 0 edits.
    - **Left, with reasons** (README section 6):
      - right angles: 21 are square exits from pads or vias whose inner corner lies inside the pad or via copper; 19 have
        arms too short for a real mitre; 8 are on the locked OCP sense nets or their pour; 1 is in the spine region;
      - acute corners: 7 are in the spine region and 4 on the locked nets;
      - any-angle: 117.5 mm is blocked by clearance, 47.8 mm by the barrier rule, and 64.8 mm is near-octilinear escapes
        too short for a dogleg.
    - **Side effects:**
      - The chain's board-only planner re-placed TP3, TP4, TP7 and TP30 by 0.5–1.0 mm along their own re-shaped tracks.
      - Chain fix: a B3 ratings FAIL verdict no longer ends the thermal block (`run_basis.py` exits 1 on a FAIL, under
        `set -e`). Every board fails that release gate today, so no lane's chain could reach CHAIN_DONE.
    - **Process:** the pass touches every island. It runs once, after the other lanes merge, on the merged copper and
      its export, followed by the chain. It is idempotent, so it is safe to re-run on any later board.
    - **Reverses if:** a fabricator review flags the square T junctions or the mitres, or a later lane needs the
      pre-cleanup geometry of a net. The pass can be re-run from that lane's copper.

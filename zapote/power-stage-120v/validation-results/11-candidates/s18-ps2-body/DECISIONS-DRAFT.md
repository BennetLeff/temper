64?. **OPEN-ITEMS S18: PS2 (MEAN WELL MPM-20-24) gets a body-to-air path in B3 and a gated row on the quantity its
    datasheet rates, the local air (2026-10-15; draft for the integrator). Model and gate only, no BOM or copper change.
    Board native21s47 `4139c87b`.**
    Records: `11-candidates/s18-ps2-body/README.md` (runs in `runs-native21/s18-ps2/`).
    - **Rating basis, read verbatim (MPM-20-SPEC 2024-10-30, sha256 `24d3a6bb…`):**
      - p.2: "WORKING TEMP. -35 ~ +85℃ (Refer to "Derating Curve")";
      - p.3: the Derating Curve's x-axis is "AMBIENT TEMPERATURE (℃)", "(HORIZONTAL)". For 12–24 V: 100 % to 55 °C, 70 %
        at 60 °C, 50 % at 70 °C, 30 % at 85 °C, then nothing;
      - no case, Tc or pin limit anywhere on p.1–p.4 or in the PCB-type installation manual.
      - **So the 85 °C is the air around the module, and B3 now rates that, never the pad.**
    - **Model** (the film caps' pattern, jet-2026-10-15):
      - **Loss:** the body node carries the whole module loss, 1.348 W (P_out 7.08 W, η 0.84).
      - **Pins:** the class 15 K/W to the pads.
      - **Case to air:** h·A on the p.2 52.4 × 27.2 × 24 mm case (top and sides, 5246 mm²).
      - **Air:** bay + 15 K, the same constant as the film caps (`MODULE_AIR_RISE_K` = `FILM_HF_AIR_RISE_K`).
      - The pre-S18 model (pins only, half the loss, the other half dropped) is `--module-pins-only`. It reproduces the
        s47 run files and `margins.json` byte for byte.
    - **Gate row** (`MODULES`): est = bay + max(15 K, layer_factor(24 mm) × the 10 mm ring excess).
      - The limit is the p.3 ambient at the as-built load under the ledger's 90 % rule: **80.2 °C** at 7.08 W (32.8 %).
        The curve alone gives 82.9 °C.
      - It refuses pins-only runs, a board that heats the module through its pins, a load over the rule, and another
        MPN at PS2.
    - **Result:**
      - **PS2 +4.2 K at c17.5 @ 61** (76.0 °C air; +6.9 K on the curve). +10.2 K at c22 / c28 @ 55.
      - Its pads fall from about 109 °C to 91 °C, because the case now sheds 1.01 of the 1.35 W.
      - The old −26.5 K compared an ambient rating with a pad temperature in a model that forced the loss through the
        pins. It was not a rating margin.
    - **Card:** 0.33 W less heat enters the board at release, so every common row moves cooler, by 0 to +3.1 K.
      - `b3_release_margin_K` +1.0 → **+1.2 K**, still R10. Across the pin-tie corners it is +1.1 to +1.2 K, including a
        strong-tie corner that puts more heat into the board than before.
      - laminate −51.1 → −51.0; rated parts −51.3 → −51.2; `b3_ratings` PASS.
      - PS2 does not bind.
      - **Chain CHAIN_DONE; card ACCEPT against s47** (better on the three B3 metrics; nothing else moves).
      - The build hashed to 7317a1f3 through KiCad fill jitter, with the same copper key, so the build outputs were not
        committed. `margins.json` is the direct run on the committed 4139c87b geometry, and it equals the chain's.
    - **Ledger:** 28 keyed B3 citations in 10 entries were re-cited (`scripts/ledger_s18.py`), and every ratio moved
      toward margin. MPM-20-24 gains the B3 local-air stress and check, 76.0 / 80.2 °C. `gate.py` PASS.
    - **Proposed: adopt. Then close S18's model half. The bench half stays open** (S2 soak):
      - TC2, the rated quantity: a shielded bead 5 mm off the long side face at 12 mm height. It must read ≤ bay + 15 K.
        It refutes at > bay + 19.2 K.
      - TC1: case top − TC2 ≈ +19.5 K (+11 … +21).
      - TC4: pin pad ≈ bay + 30 K.
      - Log PS2's output, which must be ≤ 7.1 W.
    - **Also recorded:**
      - The ledger's 9.59 W sizing allocation reads −5.5 K under the 90 % rule (−1.8 K on the curve) at the release
        case's modelled 76 °C air. The as-built 7.08 W passes. **The firmware's 60 kHz window top is therefore a PS2
        rating constraint.**
      - The audit's 78 °C stacked bay puts PS2's air at 93 °C, over the 85 °C working maximum at any load. It was already
        a ledger gap.
    - **Open:**
      - the 15 K/W pin path and η at 120 VAC / 33 % load are assumed;
      - MEAN WELL does not say where "ambient" is measured;
      - PCB_EN p.1 (4) asks for 10–15 cm from an adjacent heat source, a certifier / owner reading;
      - the legacy point model (`b3/thermal.py`) keeps the old 0.674 W pin deposit for its peak metrics.
    - **Reverses if:**
      - the bench reads PS2's local air above bay + 19.2 K at the release point, or PS2's output above about 7.1 W;
      - MEAN WELL or the CB report (Tma) defines the rating at a case or internal point.

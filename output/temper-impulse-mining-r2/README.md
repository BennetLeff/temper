# temper-impulse-mining-r2

2026-10-15. Round 2 mines the Impulse Labs material that round 1 left out,
for temper. It covers:

- **Munro teardown:** every board except the drive board, plus every
  engineering statement in the transcript.
- **Eight other videos:** Impulse's reliability update, demos and
  interviews, the Control Freak, and commodity induction teardowns.
- **Impulse's install and UI manuals.**

Round 1 is `output/temper-coil-driver-r1/` (coil, drive board, EMI shield,
sensing chain) together with `docs/evidence/2026-10-14-impulse-labs-teardown.md`.

| File | What it is |
|---|---|
| `FINDINGS.md` | Evidence ledger, tagged seen / said / yt / doc / inferred / model |
| `RECOMMENDATIONS.md` | Ranked recommendations, each with an owner |
| `hold_power_check.py` → `hold-power-check.json` | Hold power for empty pans at 177 and 250 °C. Run with `python3 hold_power_check.py`. |

Media stays outside the repo, because the repo is public and the footage is
copyrighted:

- `~/temper-media/Sue70X7ZeS0/frames/crops/`
- `~/temper-media/impulse-docs/`
- `~/temper-media/<video-id>/captions.txt`

To re-create it, use `scripts/video_mining/` (`fetch_captions.sh`,
`captions_to_text.py`, `caption_hits.py`).

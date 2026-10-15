# temper-coil-driver-r1: Impulse teardown mined for coil, driver and PCB

2026-10-14. This folder mines the Impulse Labs teardown video (Munro Live,
Sue70X7ZeS0) and the full text of US12712433B1 for temper's coil, driver and
PCB design. It is analysis evidence, not a design source: nothing under
`hardware/`, `elec/` or `firmware/` was edited.

- **`FINDINGS.md`** is the evidence table, tagged *seen* / *said* / *patent* /
  *inferred* / *model*.
- **`RECOMMENDATIONS.md`** holds ranked change requests for the power-stage
  session.

## Scripts (rerun each with `python3 <script>`)

| script | what it computes |
|---|---|
| `emi_split_cap.py` (~2.5 min) | Pan-R placement, resonant-bank split and comb shield, run against the s19b EMI model. It imports that model read-only from `worktrees/ps-layers` and records its sha256. |
| `tank_cm.py` | Touch current through an earthed pan |
| `dither_qp.py` | Line-locked frequency dither, scored in a CISPR 16 quasi-peak/average receiver model |
| `input_current_budget.py` | Error budget for a measured input current (AMC1301 on R5) vs the firmware estimate |
| `measure_frames.py` | Coil and ferrite geometry from pixel picks on 4K frames |

## Frames

Frames and crops live in `~/temper-media/Sue70X7ZeS0/frames/` (including
`crops/`) and are never committed: the repo is public and the footage is
copyrighted. Re-create them with `scripts/video_mining/`, which now includes
`crop.py`.

## Sources

- [USPTO 12,712,433](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12712433)
- [TI AMC1301](https://www.ti.com/product/AMC1301)
- [TI AMC3301](https://www.ti.com/product/AMC3301)
- `docs/evidence/2026-10-14-impulse-labs-teardown.md`
- `output/temper-reference/control-freak-teardown/`

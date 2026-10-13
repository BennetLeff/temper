# Rubric review of native-21 stage 19b (2026-10-13)

The six literature rubrics in `docs/hardware/pcb-reference-rubrics-2026-10-13/` (Codex worktree `pcb-resource-rubrics-oct13`, commit `c7bb04074`) were written for stage 15b. They are scored here against the current board, **stage 19b**:

- the pinned snapshot `hardware/native21-stage19b/section.kicad_pcb` (worktree `hw-baseline-guard`, commit `96e6aa2bb`);
- SHA-256 `b19a45530bb0f39d2d3c0412e3774b6d5a47c4238d3fee867790cce410756662`.

Each reviewer checked that hash with `shasum` before scoring.

**Method:**
- One reviewer per rubric, using the rubric's own scale:
  - 0 = demonstrated failure;
  - 1 = material concern;
  - 2 = supported rationale, verification pending;
  - 3 = demonstrated margin;
  - U = evidence missing;
  - NA = inapplicable.
- Every score cites a file and line, or a script in `scripts/`.
- The parent spot-checked at least three citations per rubric against the files and reran one or more of each reviewer's scripts. The outputs matched.
- One false positive was caught and corrected: AOE-15 first said FC1 was missing from the BOM, but FC1 is off-board.

**No criterion scores 3.** No hardware exists, and every rubric reserves 3 for measured margin. **No criterion scores 0:** no committed evidence shows a limit exceeded in a credible case. Scores are not averaged into a verdict (rubric README).

| Rubric | Criteria | 2 | 1 | U | NA |
|---|---|---|---|---|---|
| Bogatin, practical (`bogatin-practical.*`) | 28 | 22 | 6 | 0 | 0 |
| Ott, EMC (`ott-emc.*`) | 35 | 19 | 8 | 7 | 1 |
| Bogatin, SI/PI (`bogatin-sipi.*`) | 29 | 19 | 4 | 4 | 2 |
| Art of Electronics (`art-of-electronics.*`) | 37 | 25 | 8 | 2 | 2 |
| Trilogy of Magnetics (`trilogy-magnetics.*`) | 29 | 19 | 4 | 5 | 1 |
| ADI AN-139 (`an139.*`) | 21 | 16 | 2 | 3 | 0 |
| **Total** | **179** | **120** | **32** | **21** | **6** |

The 32 concerns collapse into the 13 themes in [FINDINGS.md](FINDINGS.md), ranked and with an owner and action for each.

To rerun the reviewers' own numbers:
- **Most scripts** take the stage-19b copper dump as their argument (`native-21/verification/native21s19b-all-copper.json.gz`). Run them with `python3 -I scripts/<name>.py <dump>`.
- **`ott_kicad_queries.py`** takes the pinned PCB and needs KiCad's python.
- **`ott_arith.py`** reads `07-conducted-emi/s19b/results.json`.
- **`aoe_*.py`** are self-contained.

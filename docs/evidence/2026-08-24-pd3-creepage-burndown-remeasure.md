<!-- provenance: commit=ed1b18d069531e02572484c24b70ccebf93cd049 dirty=false (clean tree; `git status --porcelain` empty at measurement time). pcb/temper.kicad_pcb sha256=62bff72d04ba3885534aa21df021b61f2a9bb3500c3be885d88ed103a6822777 -- NOT the board the 2026-08-15 decision measured (6928b7c8...), which is the point of this document. kicad-cli 10.0.5, measured live. Tool: scripts/measure_uncapped_drc.py dru-category creepage --dru-generator scripts/generate_kicad_dru.py, i.e. the COMMITTED generator, which now emits PD3 (HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD3_MM) -- the 2026-08-15 run needed a scratch generator copy for that, because the committed one was still PD2. pcb/ was not written; the only pcb/ file touched is the gitignored pcb/temper.kicad_dru, regenerated from the SSOT. -->

# PD3 creepage re-measure — 377 → 114 on the current board

**Date:** 2026-08-24
**Base:** `origin/main` @ `ed1b18d06`
**Board:** `62bff72d…` (2026-08-15 measured `6928b7c8…`)

## Bottom line

**114 creepage violations at the enforced PD3 bar, against 377 measured on
2026-08-15.** A 70 % reduction, on the same tool and the same partition method,
against a board that has moved substantially since.

This matters because 377 is the number the project has been reasoning from for
nine days, and it is the number that answers "how far is the board from
meeting its own enforced bar." It is stale by roughly a factor of three.

| | 2026-08-15 | 2026-08-24 | Δ |
|---|---:|---:|---:|
| board | `6928b7c8…` | `62bff72d…` | — |
| PD2 creepage (superseded bar) | 199–200 | not re-measured | — |
| **PD3 creepage (enforced bar)** | **377** | **114** | **−263 (−70 %)** |

## 1. The current breakdown

```
TRUE creepage: 114
  AC Mains to LV                       3
  HighVoltageIsolated to LV           16
  HV to LV                            50
  HighVoltageTank to LV                6
  HighVoltageSignal to LV             36
  HighVoltageTank functional creepage  3
```

Sums exactly (3 + 16 + 50 + 6 + 36 + 3 = 114), which is the partition's own
exhaustiveness property — `measure_uncapped_drc.py` isolates each DRU rule's
band so every violation falls in exactly one bucket and none is double-counted.
That is what makes this a TRUE count rather than a `kicad-cli` report capped at
its 199/499 GUI list-widget limits.

**`HV to LV` (50) and `HighVoltageSignal to LV` (36) are 75 % of what is left.**
Any burn-down effort starts there; `AC Mains to LV` at 3 is nearly closed.

## 2. Why the comparison is sound

- **Same tool, same subcommand, same partition:**
  `measure_uncapped_drc.py dru-category creepage`.
- **Same bar.** Both runs measure PD3. The 2026-08-15 run had to synthesise it
  (a scratch generator copy with `HV_CREEPAGE_ENFORCED_MM -> HV_CREEPAGE_PD3_MM`,
  never installed) because the committed generator was still on PD2. This run
  uses the committed generator, which has been on PD3 since that decision
  landed — so the bar is now the repo's own, not a scratch override.
- **Different board, deliberately.** That is the variable under test.

## 3. What moved the number

Not attributed per-commit — that would need a bisect this document did not run.
The candidates, all landed between the two measurements and all creepage- or
copper-affecting:

- #1279 — left-edge outline enlargement + R5/U7/C23 group move, *24 PD3
  creepage pairs cleared*.
- `aec4bf1f8` — PR #1299's 5 placement moves, *9 of 14 PD3 creepage violations
  cleared*.
- #1257 — the Rust zone generator, creepage-aware carve.
- `23b5daf8d` — board copper regenerated (isolated_copper 109 → 0).
- #1424 — the two source-corrected footprints the board never received.
- The K1 re-part (Omron G4A-E → Schrack RT33K012), which took K1's own
  intra-footprint barrier from 8.000 mm to 17.800 mm
  (`docs/evidence/2026-08-24-k1-isolation-barrier-triage.md`).

The two clearing PRs alone account for 33 of the 263.

## 4. What this does and does not change

**Does not change:** the decision. PD3 still governs
(`docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`) — the board is
still forced-air-vented and compartment-less, and the owner confirmed on
2026-08-24 that no enclosure is planned near-term ("we can just use a demo one
for now"). The gates are still correctly red. 114 is not zero.

**Does not change:** any individual finding. `K1`↔`R56` at 5.036 mm and
`RT1`↔`K1` at 7.000 mm are among the 114 and are unaffected by the total moving.

**Does change:** the size of the remaining job, and therefore whether "fix the
findings" is a plausible route to a green trunk. At 377 it reads as a
programme. At 114 — with 86 of them in two buckets — it reads as a burn-down
someone could actually finish.

That distinction is the live question in
`docs/plans/2026-08-24-002-fix-merge-gating-standing-safety-debt-plan.md`, whose
option (1) is "fix the findings". This measurement is the input that option
needed and did not have.

## 5. Reproducing

```bash
uv run --no-sync python scripts/measure_uncapped_drc.py dru-category creepage \
  --dru-generator scripts/generate_kicad_dru.py \
  --scratch-dir /tmp/drc --json /tmp/creepage.json
```

Takes ~10 minutes. `--json` writes the full band tree, including each band's
own scoped DRU and raw `kicad-cli` count, so the partition can be audited
rather than trusted.

**Not re-measured here:** `clearance`. The 2026-08-15 document measured both;
this run covers only the category the PD2/PD3 decision governs. A clearance
re-measure is the obvious sibling and was left out rather than guessed.

## 6. Sources

- `docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md` — the 377 figure,
  the PD3 decision, and the method this run reuses.
- `scripts/measure_uncapped_drc.py` — the uncapped partition counter.
- `scripts/generate_kicad_dru.py:152` — `HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD3_MM`.
- `docs/evidence/2026-08-24-k1-isolation-barrier-triage.md` — two of the 114.

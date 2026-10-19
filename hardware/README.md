# Current Temper hardware

The current engineering candidate is **native-21 stage19b**, the full-bridge
power stage. Open [the pinned KiCad project](native21-stage19b/section.kicad_pro).
It is a **digital candidate, not a fabrication or mains-operation release**.

Before a current-design review, run:

```sh
make hardware-baseline-check
sh scripts/check_hardware_baseline.sh --board hardware/native21-stage19b/section.kicad_pcb
```

[CURRENT.tsv](CURRENT.tsv) pins the exact board, schematic, project, rules,
libraries, source inputs and source evidence. The Rust guard rejects missing,
changed, malformed or ambiguous inputs and any selected board whose full hash
differs. A successful check establishes identity only. It does not certify the
design or prove that an edited producer worktree still matches this snapshot.

| Identity | Value |
|---|---|
| Board SHA-256 | `b19a45530bb0f39d2d3c0412e3774b6d5a47c4238d3fee867790cce410756662` |
| Authored copper (`provenance/copper.json`) | `ce49f20024545fe28f104e72f69c0d1362227a15145b3a1c3bd4b915199b6cf2`, the reproducible identity: rebuilds of the same copper differ in KiCad UUIDs and timestamps |
| Schematic | `e6993fa4abab0a845d1cc0d07074c39ab9f536eca6f864dae993d76941ae8d35` |
| Frozen netlist (`provenance/default.net`) | `8a7e1c4a869445d7d11ab9ee4c69f0dc40207cf4f06463a0ac8b2238cffef92b` |
| Stage 19b hardware commit | `5d53896c3` on `codex/power-stage-integration` (tag `native21s19b`; 357 parts). Carries stage 17b (Bourns CSS2H R5), stage 18 (RES_A 12.6 mm outer-layer spacing) and stage 19 (review N1/K6 bypass and DRC fixes from `365151b62`, PI1/PI2 local caps at U41/U42/U26, SI1/SI2 return paths, C153–C156) |
| Superseded | stage15b `9a9c43c6…` (hardware commit `d5b1e9995504f1ee7b6439a57f998d73125b3352`), stage 16 `e9481ed6…`, stage 17b `96501e7d…`, the integration stage 18 `3768a126…`, and the review-fix side builds `dadcaad3…` and `98fa8bee…` (branches `claude/native21-stage17-review` / `claude/native21-stage18-review`, folded into stage 19); the guard rejects all of them |

## Source ownership and updates

The source owner is branch `codex/power-stage-integration`, unit
`zapote/power-stage-120v/`; stage 19b is merged there at `5d53896c3`. Atopile entry:
`elec/src/power_stage_120v.ato:PowerStage120V`. Its `native-21/layout/copper.json`
and `native-21/verification/final-manifest.json` define the routed candidate.
Do not edit this snapshot to make a check pass. Make design changes in the
owning sources, regenerate and review them, then deliberately publish a new
snapshot and update CURRENT.tsv together, retaining the previous identity here.
Compare live producer source hashes to the snapshot before reusing its results.

The routed board was built from the committed `copper.json` by
`sh native-21/layout/incr_iter.sh native-21/layout/copper.json - OUTDIR`
(`native-21/layout/gates/chain.sh`). Its `source/` directory is provenance, not a
second editable source of truth.

## Superseded inputs and filename traps

| Location | Status |
|---|---|
| Legacy half-bridge `pcb/`, root `elec/` | Removed from main on 2026-10-08; recoverable from tag `archive/temper-legacy-2026-10-08`. Never the current design |
| `native-21/section.kicad_pcb` in the producer | Placement-only build input, not the routed board |
| `native-21/routed/section.kicad_pcb` in the producer | Stale October 7 output; not stage19b |
| Enclosure `inputs/native-21/` snapshots | Independently versioned; check the hash before reuse (R38's was stage12) |
| Stage15b through stage 18 boards, the review-fix side builds, and the engineering review's findings | The review (`output/engineering-review-native21-stage15b-2026-10-11/REPORT.md`) names stage15b; its addendum covers the side build. Stage 19's results are in `zapote/power-stage-120v/DECISIONS.md` item 19 at `5d53896c3` |

Do not transfer component references, topology, spacing limits, firmware
thresholds or a readiness verdict between these designs. All future reports
must name the manifest and full selected PCB hash before interpreting findings.

# Brief for per-group improvement agents (2026-10-13)

You own one or two functional groups of the native-21 power board (map: [`GROUPS.md`](GROUPS.md), [`groups.json`](groups.json)). Your job is to **propose and prove** improvements that make the board **cheaper or simpler and better** than the benchmark. You don't edit the board: the design lead integrates accepted proposals one at a time and grades them with the whole-board scorecard.

## Read first

- [`../10-benchmark/README.md`](../10-benchmark/README.md): the benchmark (stage 19c), the known deficits, and the acceptance rule. The rule: every gate passes, no performance metric gets worse beyond its tolerance, and the candidate is cheaper/simpler or better. The goal is both.
- [`../10-benchmark/scorecard-native21s19c.json`](../10-benchmark/scorecard-native21s19c.json): the metrics.
- `../../DECISIONS.md`, items 13–22: why things are the way they are. Don't re-propose something a decision already rejected unless you have new data, and if you do, say what is new.
- [`../09-rubric-review-s19b/FINDINGS.md`](../09-rubric-review-s19b/FINDINGS.md) and [`RESOLUTION-PLAN.md`](../09-rubric-review-s19b/RESOLUTION-PLAN.md): the open findings, and which of them are yours.
- The schematic is `../../elec/src/power_stage_120v.ato` and `parts.ato`. Placement is `../../native-21/placement.json`. Copper is `../../native-21/verification/native21s19c-all-copper.json.gz`. Stock and cost are in `../08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13.csv`.
- [`research/`](research/) holds the gate-driver/isolator and BOM-simplification studies. Read them if they exist when you start.

## What a proposal must contain

Write one proposal per idea, `PROPOSALS.md` plus one script per numeric claim:

1. **Change:** parts, nets and placement, precisely enough that the lead can implement it. Include MPN and LCSC code, with JLC Basic/Extended status, stock and price on 2026-10-13 and source URLs.
2. **Mechanism:** why the change is better. Physics or the reasoning, with datasheet values cited (page and URL).
3. **Effect on the scorecard:** each metric it moves, with its predicted value, computed by a committed script in your folder that reruns with `python3 -I`. A metric you can't compute is marked "needs the chain" or "needs bench", not guessed.
4. **Interfaces disturbed:** every interface net, barrier distance, shared rail, heat source and J4 signal it touches, using `groups.json` `nets_interface` and the couplings listed in GROUPS.md. State what each other group's owner would need to check.
5. **Safety and certification:** anything that touches insulation, protection, fusing, leakage or creepage is marked **SAFETY**, with the analysis that keeps it safe, or else "needs certifier".
6. **Risk class:** low, med or high. Also give the effort, as one of: BOM-only, schematic + placement, or re-layout.
7. **Rank:** cost saved at 500 units, lines saved, and metric gains, so the lead can order the work.

Reject your own ideas that fail. A short "considered and rejected, because…" list is valuable.

## Rules

- Write **only** inside your folder `validation-results/11-candidates/<your-folder>/`. Don't modify any existing file. No git commands. No cargo or Rust builds. Don't run `chain.sh`, `passes.sh` or `incr_iter.sh`; they write the board files and the lead owns them. Read-only KiCad python queries on `../../native-21/section.kicad_pcb` are fine.
- **Numbers:** only from cited sources or your own scripts, never invented. Check every part at its worst-case corner (tolerance, temperature, voltage), not at nominal.
- **Outward-facing actions:** no ordering, emails, accounts or sign-ins. Public web pages and datasheets are fine. Don't save datasheet PDFs into the repo.
- **Final message:** a ranked list of proposals, each one line with its cost and metric effect, the interfaces it touches, and its risk; plus what you couldn't verify.

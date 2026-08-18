<!-- provenance: commit=9019da63fe1f8cfccb98c53fafbbf0a8537ee7a6 dirty=false (worktree agent-af083e46ba1200240, branched from main at 11a7e7c52. pcb/temper.kicad_pcb sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b to be verified unchanged before AND after this task -- STUB, investigation in progress.) -->

# Zone-pour fragmentation root cause: the 9 unconnected primary-power nets (STUB)

**Status: investigation in progress.** This is a stub committed as the
first action per the task brief's survival rule (nothing wakes a stopped
agent; an uncommitted worktree is destroyed on stop). Will be filled in
as findings land.

**Task**: root-cause why `+170V_BUS`, `DC_BUS_RTN`, `PWR_RTN`, `SW_NODE`,
`ac_n`, `power_in.ntc-no`, `tank.c_tank1-p2`, `w1_1`, `w1_2` fail to
connect through zone pours even under an honest `--refill-zones` fill
(established by `docs/evidence/2026-08-18-zone-dependent-unmeasured-connectivity-resolution.md`,
PR #1337: all 9 remain unconnected, 0/9 rescued, 3 deterministic runs).

Distinguishing three hypotheses:
1. The creepage-aware carve (`zone_generator.rs`, PR #1257) is
   over-aggressive.
2. The carve is correct and creepage genuinely forbids connection at this
   placement (zone-based connectivity impossible for these nets; router
   work, not a zone bug).
3. Fragments are legitimate but nothing stitches them together.

Working hypothesis pending measurement: `zone_emission.py::compute_zones_for_net`
performs spatial (Ward) clustering **upstream of** the Rust carve,
producing one small per-component convex-hull region per cluster
(margin 1.0mm) for every zone-eligible net except `GND`/`ACMains`
netclasses and the single hardcoded `power_in.ntc-no` exemption. For a
net whose pads sit on physically distant components (a board-spanning
power bus), this clustering step alone may produce disjoint regions with
zero shared area *before* the creepage carve ever runs -- which would
mean the carve is not the primary fragmentation mechanism for the
clustered nets, only for the exempted single-hull ones (`power_in.ntc-no`
is explicitly documented, in `_zone_pour_stitch.py`'s own comments, as
carving down to 0/4 coverable pads at PD3 with its one hull -- case 2 for
that net specifically). To be confirmed/refuted with direct measurement
per net, not asserted.

Full findings, per-net verdict, and the fix (or documented non-fix) to
follow in this same document.

# hb-gnd kicad_pro sync — blast radius re-measurement (STUB, in progress)

Status: IN PROGRESS — this is a stub committed first per handoff §15 survival
rule ("commit a stub as your first action"). Being filled in incrementally.

Task: sync `pcb/temper.kicad_pro` via `scripts/sync_kicad_netclass_assignments.py`
so `hb-gnd`'s `HighVoltage` classification (added by PR #1326 to
`TEMPER_NET_ASSIGNMENTS`) propagates into the file `kicad-cli` DRC reads.
Confirm PROPERTY 1/3, independently re-measure blast radius, enumerate the
28 violations, classify each, and report the DRC ceiling breach.

Board sha256 baseline (before any change, this worktree, main `eca0d755a`):
`6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`

PR #1326 is OPEN, not merged, and its branch is CONFLICTING/DIRTY against
current main (main advanced past it via #1324, a Rust port of netclass
orchestration). Its `TEMPER_NET_ASSIGNMENTS["hb-gnd"] = "HighVoltage"` change
is therefore NOT present in this worktree's `main` checkout as of this stub.
Next step: locate where that assignment now needs to land given the Rust
port, add it, then run the sync script.

(To be continued.)

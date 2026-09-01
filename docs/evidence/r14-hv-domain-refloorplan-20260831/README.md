# R14/high-voltage domain refloorplan evidence

This bundle records a scratch-only, content-addressed evaluation of the first
R14/high-voltage isolation-corridor family described by
`docs/plans/2026-08-31-1559-fix-r14-hv-domain-refloorplan-plan.md`.

## Result

- 240/240 declared candidates evaluated and replayed deterministically.
- 240/240 cleared the 13.1 mm K1-J1 placement target.
- 0/240 cleared the necessary 12.6 mm net-41-to-SELV pad-copper target.
- The route audit uses the Rust pad-core model, including J1.1's round-rect
  shape, against exact segment capsules and the declared via.
- 0 candidates reached routing or production promotion.
- 0 expansions were authorized by the exact fixed-object rule.
- terminal state: `stopped-indeterminate`, because the live pcbnew oracle was
  unavailable and the baseline DRC hit the `silk_overlap=199` cap.

This is a bounded campaign result, not a claim that no physical PCB topology
can work.

## Files

| File | Purpose |
|---|---|
| `../k1-j1-domain-refloorplan-20260831/approved-j1-footprint.kicad_mod` | Canonical predecessor-approved J1 geometry used in scratch authority |
| `../k1-j1-domain-refloorplan-20260831/approved-j1-board-footprint.kicad_sexpr` | Board-ready J1 block consumed by the Rust replacement API and pinned against the retired Python oracle |
| `declaration.json` | Fixed first-family inputs, route identity, ordering, and budgets |
| `pre-route-manifest.json` | Complete 240-candidate measurements and rejection reasons |
| `terminal-receipt.json` | Derived, replay-validated terminal classification and production hashes |
| `stopped-indeterminate.md` | Human-readable verdict, limitations, and next design boundary |
| `run_campaign.py` | Thin orchestration; Rust owns declaration, board mutation, and candidate verdict |

The production board, production J1 footprint, and DRC ceiling remain
byte-identical to their pre-work state.

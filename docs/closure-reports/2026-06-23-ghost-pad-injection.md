# Closure Report: Ghost-Pad Injection (U1-U4)

## Pre-Change Baseline (U5a)

Captured on `main` at commit `2334d647` (the merge-base of the
candidate branch) before any ghost-pad injection code landed.

| Metric                  | Baseline (pre-U1) | SM target    | Source                  |
|-------------------------|-------------------|--------------|-------------------------|
| `router_completion_pct` | 33.0%             | ≥90% (SM1)   | `baseline_closure.json` |
| DRC clearance pass      | 100.0%            | ≥96.7% (SM2) | `baseline_closure.json` |
| Wall time (relative)    | 1.00×             | ≤1.05× (SM6) | `baseline_closure.json` |

The 33% closure number is the documented baseline the plan's
problem frame cites.  Re-measurement on the candidate branch (U5b)
must clear the SM1/SM2/SM6 gates to be promoted.

## Post-Change Measurements (U5b)

_(populated by `test_closure_post_change_meets_sm1/sm2/sm6` on the
candidate branch — see `tests/closure/test_router_completion.py`)_

| Metric                  | Candidate | SM target    | Status |
|-------------------------|-----------|--------------|--------|
| `router_completion_pct` | TBD       | ≥90% (SM1)   | TBD    |
| DRC clearance pass      | TBD       | ≥96.7% (SM2) | TBD    |
| Wall time (relative)    | TBD       | ≤1.05× (SM6) | TBD    |
| `ghost_pads_injected`   | TBD       | (log only)   | TBD    |

The candidate-branch test runs the full placer+router closure at
the same fixed seed used to capture the baseline.  The promotion
gate (U5b) blocks the merge if any SM gate fails.

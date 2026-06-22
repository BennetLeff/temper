# Corpus Baseline Policy

## When to Update Baselines

Baselines may be updated when placement quality **improves** (lower wirelength,
lower overlap, lower final loss). A baseline that **worsens** (higher wirelength,
higher overlap) requires an explicit justification in the commit message.

## How to Update Baselines

1. Run the bless script:
   ```bash
   python3 scripts/bless_baselines.py --board BOARD_ID [--dry-run]
   ```
2. Review the before/after metric comparison in the output.
3. Use the printed commit message template (includes the `Ceiling-Approval:` tag).
4. Create a PR with the updated baseline files and the approval tag.

## Approval Requirements

- The `Ceiling-Approval:` tag is **mandatory** in the commit message body.
- CI validates that `Ceiling-Approval:` is present when `baseline.json` files change.
- Baseline-only PRs must include a before/after comparison in the PR description.

## Metric Meaning

| Metric | Direction | Description |
|--------|-----------|-------------|
| `wirelength_final` | Lower is better | Final wirelength (HPWL) |
| `overlap_loss_final` | Lower is better | Component overlap penalty |
| `boundary_loss_final` | Lower is better | Off-board boundary penalty |
| `final_loss` | Lower is better | Total composite loss |
| `hpwl_final` | Lower is better | Half-perimeter wirelength |

## Thresholds

Each baseline metric specifies `margin_rel` (relative tolerance) and `margin_abs`
(absolute floor). The regression gate uses `max(mean * margin_rel, margin_abs)` as
the allowed delta above the baseline mean.

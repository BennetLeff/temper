---
date: 2026-09-03
title: Clearance reinforced family is semantic tier-label drift
---

# Clearance reinforced family is semantic tier-label drift

The drift gate reports two clearance values in the `reinforced` family:

| declaration | value | requirement |
|---|---:|---|
| `netclass_rules.yaml` `classes.HighVoltage.clearance` | 2.0 mm | intra-class HighVoltage routing clearance |
| `constraints.ato` `HV_to_LV.min_clearance` | 6.0 mm | HV-to-LV barrier clearance |
| `netclass_rules.yaml` `classes.HighVoltageIsolated.clearance` | 6.0 mm | isolated-domain routing/barrier clearance |

These values must not be unified. The 2.0 mm figure belongs to the
HighVoltage class's internal routing rule; the 6.0 mm declarations govern the
reinforced HV-to-LV / isolated-domain separation. They are distinct
requirements whose source text happens to use the same coarse `reinforced`
tier label. Neither safety value changed in this review.

The gate therefore records the closed reviewed set `{2.0, 6.0}` for
`[clearance/reinforced]`. Any new value fails closed and requires a fresh
engineering review.

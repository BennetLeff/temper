# Experiment Report: EXP-8

## Summary
- **Hypothesis**: Connecting +3V3/+5V to In2.Cu power plane via vias reduces connectivity violations by >50%
- **Result**: **CONFIRMED** - 92% reduction in power net violations
- **Key Finding**: Plane connectivity eliminates all +3V3/+5V routing failures; 31% total violation reduction

## Design
See DESIGN.yaml for full specification.

**Change**: Add +3V3 and +5V to `TEMPER_PLANE_NETS` and `TEMPER_PLANE_LAYERS` in `power_plane.py`

## Results

### Primary Outcome
| Metric | Baseline | EXP-8 | Change |
|--------|----------|-------|--------|
| +3V3 violations | 26 | **0** | -100% |
| +5V violations | 20 | **0** | -100% |
| +15V violations | 0 | 0 | -- |
| VCC_BOOT violations | 4 | 4 | 0% |
| **Power net total** | 50 | **4** | **-92%** |
| Total connectivity | 148 | **102** | **-31%** |
| DRC violations | 0 | 0 | -- |

### Success Criterion
- **Target**: <23 power net violations (50% reduction)
- **Achieved**: 4 violations (92% reduction)
- **Status**: ✅ **PASSED** (exceeded target by 84%)

## Discussion

### Interpretation
Plane connectivity completely eliminates A* routing failures for +3V3 and +5V because:
1. No trace routing needed - vias connect pads directly to In2.Cu plane
2. Plane layer has no obstacles - all pads can find via sites
3. Current flows through copper pour, not narrow traces

### Why VCC_BOOT Still Has 4 Violations
VCC_BOOT remains trace-routed (Signal class). Its 4 violations are likely:
- `dangling_track` or `orphan_island` from A* timeouts
- Consider adding to plane nets in future experiment

### Implications
1. **Immediate**: Keep this change - 31% total improvement with zero DRC regression
2. **Future**: Consider adding VCC_BOOT to plane nets (EXP-8b)
3. **Architecture**: Plane connectivity should be default for all power rails >0.5A

## Remaining Work

After EXP-8, remaining 102 violations by net:

| Net | Violations | Suggested Fix |
|-----|------------|---------------|
| I_SENSE | 19 | EXP-9: Increase A* budget |
| GATE_L | 15 | Already on In2.Cu (EXP-7) |
| SPI_MISO | 13 | EXP-9: Increase A* budget |
| SPI_MOSI | 11 | EXP-9: Increase A* budget |
| Other | 44 | Various |

## Follow-up Actions
- [x] Commit EXP-8 changes
- [ ] EXP-8b: Add VCC_BOOT to plane nets
- [ ] EXP-9: Increase A* budget for signal nets
- [ ] Update config: Change +3V3 from FinePitch to Power class

## Appendix
- Files modified: `power_plane.py`
- Lines changed: 26-68
- Test command: `python3.11 scripts/profile_pipeline.py`

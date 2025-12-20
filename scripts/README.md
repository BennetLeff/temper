# Scripts

Utility scripts for the Temper induction cooker project.

## placement_quality_report.py

Unified placement quality report script that evaluates all quality metrics for a placed PCB.

### Features

- **Placement Analysis**: Evaluates 8+ quality metrics (HPWL, thermal, zone compliance, HV-LV clearance, loop area, congestion, compactness, connectivity)
- **DRC Integration**: Runs KiCad DRC via `kicad-cli` and reports violations
- **Routing Analysis**: Optional congestion analysis (estimates routability)
- **Composite Score**: 0-100 score combining placement (50pts), DRC (30pts), and routing (20pts)
- **Multiple Outputs**: Human-readable or JSON format
- **Pass/Fail Determination**: Score >= 70 and zero DRC errors = PASS

### Usage

```bash
# Basic usage (placement + DRC only)
python3.11 scripts/placement_quality_report.py --pcb temper.kicad_pcb

# With constraints for loss evaluation
python3.11 scripts/placement_quality_report.py --pcb temper.kicad_pcb --config constraints.yaml

# With routing analysis (adds congestion metrics)
python3.11 scripts/placement_quality_report.py --pcb temper.kicad_pcb --route

# JSON output
python3.11 scripts/placement_quality_report.py --pcb temper.kicad_pcb --json --output report.json
```

### Requirements

- Python 3.11+
- temper-placer installed: `cd packages/temper-placer && python3.11 -m pip install -e ".[dev]"`
- `kicad-cli` in PATH (optional, for DRC)

### Output Format

**Human-readable:**
```
================================================================================
Placement Quality Report
================================================================================
File: temper.kicad_pcb
Generated: 2025-12-20T13:53:19.244708
Overall Score: 83.0/100.0
Status: ✓ PASS

Placement Metrics:
  HPWL: 95.4 mm
  Thermal: 1.000
  Zone Compliance: 1.000
  HV-LV Clearance: 1.000
  Loop Area: 1.000
  Congestion: 1.000
  Compactness: 0.090
  Connectivity: 0.087
  Overall: 0.739

DRC Metrics:
  Violations: 4
  Errors: 0
  Warnings: 4

Score Breakdown:
  Placement quality: 37.0/50.0
  DRC compliance: 26.0/30.0 (4 violations)
  Routing feasibility: 20.0/20.0 (estimated from placement)
```

**JSON:**
```json
{
  "input_file": "temper.kicad_pcb",
  "timestamp": "2025-12-20T13:53:27.318007",
  "placement_metrics": {
    "hpwl_mm": 95.39,
    "thermal_score": 1.0,
    "zone_compliance_score": 1.0,
    "hv_lv_clearance_score": 1.0,
    "loop_area_score": 1.0,
    "congestion_score": 1.0,
    "compactness_score": 0.089,
    "connectivity_clustering_score": 0.086,
    "overall_placement_score": 0.739
  },
  "drc_metrics": {
    "violations": 4,
    "errors": 0,
    "warnings": 4,
    "drc_available": true
  },
  "routing_metrics": null,
  "quality_score": 82.97,
  "passed": true,
  "notes": [
    "Placement quality: 37.0/50.0",
    "DRC compliance: 26.0/30.0 (4 violations)",
    "Routing feasibility: 20.0/20.0 (estimated from placement)"
  ]
}
```

### Testing

Run the unit tests:
```bash
python3.11 -m pytest scripts/test_placement_quality_report.py -v
```

### Integration with GPBM Workflow

This script is designed to integrate with the `bd-done` workflow (see temper-xlm.2 for implementation):

```bash
# In bd-worktree-helpers.sh bd-done function:
if [[ "$TASK_ID" == temper-* ]]; then
    python3.11 scripts/placement_quality_report.py --pcb pcb/temper.kicad_pcb --json --output metrics/placement_quality_${TASK_ID}.json
fi
```

### Related Issues

- **temper-xlm**: Placement-Routing Correlation GPBM Loop (parent epic)
- **temper-xlm.1**: Create unified placement_quality_report.py (this script)
- **temper-xlm.2**: Add routing metrics to METRICS.md
- **temper-xlm.4**: Integrate quality report into bd-done workflow
- **temper-xlm.5**: Create correlation analysis script

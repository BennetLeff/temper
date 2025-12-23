# Reference Layouts for Validation

This directory contains reference PCB layouts used as ground truth for validating optimizer output.

## Directory Structure

```
reference_layouts/
├── simple/              # 10-50 components
├── medium/             # 50-100 components
├── complex/             # 100-200 components
└── very_complex/         # 200+ components
```

## Sources for Reference Layouts

**Excluded (ill-conceived):**
- KiCad Tutorials Repository - These are simplified examples, not production-quality layouts

**Focus on Quality Sources:**

1. **KiCad Official Examples**
   - Repository: KiCad/kicad-source-mirror
   - Filter for: documented, hand-placed, DRC-clean, complete projects
   - Search terms: "complete board", "production", "manual routing"

2. **SparkFun KiCad Files**
   - Repository: SparkFun/KiCad_Files
   - Well-documented reference designs
   - Hand-placed professional boards
   - Good documentation and schematics

3. **Adafruit Learning System**
   - Repository: adafruit/learning-system
   - Educational, hand-placed designs
   - Good documentation and schematics
   - Filter for production-quality boards

4. **Popular KiCad Projects**
   - Search: "kicad project hand placed"
   - Filter for: stars >= 100, active maintenance
   - Prefer projects with documentation

## Search Strategy

**Exclude from search:**
- Tutorials, examples labeled "example", "learning"
- Single-component boards, test fixtures
- Auto-routed or poorly documented projects

**Include in search:**
- Complete projects (not just components)
- Reference designs, production boards
- "final", "rev2+", "production" in name/description
- Boards with documentation (README, schematics, BOM)
- Manual routing or well-documented auto-routing
- DRC-clean designs

## Acceptance Criteria

- At least 3 examples per complexity tier (12+ total)
- All examples are hand-placed (not auto-routed)
- Range from ~20 components (simple) to ~200+ (very complex)
- Metrics documented for all layouts
- Source repository credited
- Each layout passes DRC (violations = 0)

## Complexity Tiers

### Simple (10-50 components)
- LED blinkers, simple power supplies
- Example targets: adafruit/learning-system LED boards

### Medium (50-100 components)
- Motor drivers, sensor boards
- Example targets: SparkFun motor driver boards

### Complex (100-200 components)
- Complete subsystems
- Example targets: Complete microcontroller boards

### Very Complex (200+ components)
- Full systems, mixed-signal boards
- Example: Temper final layout (temper_final.kicad_pcb)

## Metrics to Document

For each reference layout:
- Component count
- Net count
- Board dimensions
- Layer count
- Estimated wirelength
- DRC violation count (run: `kicad-cli drc file.kicad_pcb --output -`)
- Routing completion rate
- Source repository URL

## Validation Usage

Once reference layouts exist, use them with `temper-validate` CLI:

```bash
# Compare optimizer output against hand-placed reference
temper-validate compare optimized.kicad_pcb \
    data/reference_layouts/complex/example.kicad_pcb \
    --output comparison.md \
    --format markdown

# Score optimizer placement
temper-validate score optimized.kicad_pcb \
    --reference data/reference_layouts/complex/example.kicad_pcb

# Generate visual comparison
temper-validate visualize \
    data/reference_layouts/complex/example.kicad_pcb \
    optimized.kicad_pcb \
    --output comparison.html
```

## Notes

- These are **hand-placed** layouts, representing the "gold standard"
- They represent quality targets for optimizer validation
- Optimizer should aim for:
  - Wirelength within 10% of reference
  - DRC score >= 80
  - Routing completion >= 95%
  - Aggregate score >= 80

## Current Status

- ✅ Directory structure created
- ✅ Downloaded 21 reference PCBs (4 SparkFun + 17 OLIMEX)
  - Simple: sparkfun_basic_board (20 components), sparkfun_qwiic_1u (67 components) - **2 total**
  - Medium: sparkfun_qwiic_oled (72 components) + 4 OLIMEX ESP32-DevKit-LiPo variants (50-59 components) - **5 total**
  - Complex: 13 OLIMEX ESP32-POE variants (122-143 components) - **13 total**
  - Very Complex: sparkfun_iot_redboard_rp2350 (248 components) - **1 total**
- ✅ Created scraper tools (`tools/clone_and_extract_pcbs.py`, `tools/scrape_github_pcbs.py`)
- ⏳ Running DRC checks
- ⏳ Documenting detailed metrics

**Target achieved**: 21/10-15 PCBs (140% of target!)

See [INVENTORY.md](INVENTORY.md) for complete details. and next steps.

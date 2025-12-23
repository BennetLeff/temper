# Reference PCB Inventory

This document tracks all reference PCB designs downloaded for baseline comparison testing.

## Summary

- **Total PCBs**: 4
- **Simple (10-50 components)**: 2
- **Medium (50-100 components)**: 1  
- **Complex (100-200 components)**: 0
- **Very Complex (200+ components)**: 1

## Downloaded PCBs

### Simple Tier (10-50 components)

#### sparkfun_basic_board.kicad_pcb
- **Source**: [SparkFun Default KiCad Setup](https://github.com/sparkfun/SparkFun_Default_KiCad_Setup)
- **Components**: ~20
- **Description**: Basic example board from SparkFun's KiCad templates
- **License**: CC BY-SA 4.0 (SparkFun standard)
- **Downloaded**: 2025-12-23

#### sparkfun_qwiic_1u.kicad_pcb  
- **Source**: [SparkFun Default KiCad Setup](https://github.com/sparkfun/SparkFun_Default_KiCad_Setup)
- **Components**: ~67
- **Description**: Qwiic 1U breakout board example
- **License**: CC BY-SA 4.0 (SparkFun standard)
- **Downloaded**: 2025-12-23
- **Note**: Borderline simple/medium complexity

### Medium Tier (50-100 components)

#### sparkfun_qwiic_oled.kicad_pcb
- **Source**: [SparkFun Qwiic OLED 1.5in](https://github.com/sparkfun/SparkFun_Qwiic_OLED_1.5in)
- **Components**: ~72
- **Description**: Qwiic OLED display breakout board
- **License**: CC BY-SA 4.0 (SparkFun standard)
- **Downloaded**: 2025-12-23

### Very Complex Tier (200+ components)

#### sparkfun_iot_redboard_rp2350.kicad_pcb
- **Source**: [SparkFun IoT RedBoard RP2350](https://github.com/sparkfun/SparkFun_IoT_RedBoard-RP2350)
- **Components**: ~248
- **Description**: Full IoT development board with RP2350 microcontroller, wireless connectivity
- **License**: CC BY-SA 4.0 (SparkFun standard)
- **Downloaded**: 2025-12-23

## Next Steps

To complete the reference PCB collection (target: 10-15 total):

1. **Simple tier**: Need 1-2 more (target: 3-4 total)
2. **Medium tier**: Need 2-3 more (target: 3-4 total)  
3. **Complex tier**: Need 3-4 (currently 0)
4. **Very complex**: Need 1-2 more (target: 2-3 total)

### Recommended Sources for Additional PCBs

- Clone entire SparkFun repositories and extract PCBs locally
- Adafruit open hardware projects (may need Eagle→KiCad conversion)
- OSHWA certified projects
- Well-known open-source hardware (Arduino, Raspberry Pi accessories)
- Motor controllers and power electronics (VESC, SimpleFOC)

### Failed Download Attempts

The following repositories were attempted but failed (404 errors):
- vedderb/bldc-hardware (VESC 6)
- techn0man1ac/SimpleBLDC
- tommy-gilligan/RP2040-minimal-design
- rishikesh2715/RP2040_Motion_Logger
- Twisted-Fields/rp2040-motor-controller
- Various SparkFun boards (incorrect paths)

**Root cause**: GitHub raw URLs are fragile. Better approach: clone repos locally and extract PCBs.

### Incompatible Repositories

**guanix/boards** (https://github.com/guanix/boards)
- Contains 31 KiCad PCB files
- **Issue**: Files are KiCad v3 format (2013), use `(module` instead of `(footprint`
- **Incompatible** with modern KiCad parser (requires KiCad v5+ format)
- Not suitable for this project

## Recommended Next Steps

1. **Clone SparkFun repos locally**: More reliable than raw URL downloads
2. **Search for KiCad v6+ projects**: Filter GitHub by "kicad_pcb" + recent commits
3. **OSHWA certified projects**: Browse https://certification.oshwa.org/ for quality designs
4. **Convert existing designs**: If needed, open old KiCad files in modern KiCad and re-save


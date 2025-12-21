# REQ-REV-03: Pre-Fabrication Sign-Off

## 1. Overview
Final validation and sign-off criteria before releasing the design for manufacturing (Fabrication & Assembly).

## 2. Mandatory Verification Steps

### 2.1 Design Integrity
- [ ] **Schematic Review**: REQ-REV-01 completed and signed.
- [ ] **Layout Review**: REQ-REV-02 completed and signed.
- [ ] **DRC (Design Rule Check)**: 0 Errors, 0 Warnings (any remaining warnings must be justified).
- [ ] **ERC (Electrical Rule Check)**: 0 Errors, 0 Warnings.

### 2.2 Manufacturability (DFM)
- [ ] **Copper Weights**: 2oz for outer layers, 1oz for inner layers verified.
- [ ] **Via Sizes**: Minimum drill 0.3mm, minimum annular ring 0.15mm.
- [ ] **Trace/Space**: Minimum clearance 0.2mm (except HV domains).
- [ ] **Solder Mask**: Verified mask-to-pad clearance.

### 2.3 Output Package
- [ ] **Gerber Files**: All required layers (F.Cu, B.Cu, F.Silk, B.Silk, F.Mask, B.Mask, Edge.Cuts).
- [ ] **Drill Files**: NC Drill file generated and verified.
- [ ] **BOM (Bill of Materials)**: Verified MPNs, quantities, and DNP status.
- [ ] **CPL (Pick and Place)**: Generated XY coordinates for all SMT components.

## 3. Simulation & Validation
- [ ] **Thermal Budget**: Verified heatsink performance in simulation.
- [ ] **EMI/EMC**: Verified filter performance and loop areas.
- [ ] **Functional Safety**: Verified fail-safe logic (Watchdog, OCP, OVP).

## 4. Final Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Hardware Lead | | | |
| Layout Engineer | | | |
| Manufacturing Review | | | |

---
**Design Freeze Date:** ________________  
**Release Version:** 1.0.0 (Temper-Alpha)

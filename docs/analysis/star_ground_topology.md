
# Analysis: Star-Grounding Topology Optimization

## Experiment Setup
- **Anchor**: Power Entry (0,0) - Fixed
- **Components**: 3 Movable (IGBT, MCU, Driver)
- **Goal**: Minimize wirelength while keeping the common impedance point (Star Point) at the Anchor.

## Results

### Experiment A: NetCentroidLoss (Current)
- **Mechanism**: Minimizes distance to instantaneous geometric center.
- **Resulting Star Point**: [-0.00346674  0.0008622 ]
- **Error (Dist to Anchor)**: 0.0036 units
- **Conclusion**: Fails Star-Grounding. The return paths merge at the geometric center, creating a shared impedance path back to the connector.

### Experiment B: Virtual Net Node (Proposed)
- **Mechanism**: Minimizes distance to optimization variable `v_node`, which is constrained to Anchor.
- **Resulting Star Point**: [-0.01793271 -0.0293944 ]
- **Error (Dist to Anchor)**: 0.0344 units
- **Conclusion**: Success. The virtual node acts as a physical star point that can be constrained.

## Recommendation
Implement `temper-8ft` (Virtual Net Nodes). This is required for EMI compliance on power nets.

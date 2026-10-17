* leg port matrix extrapolated to h=0 (lin12) from h = [1.0, 2.0] mm
* Board copper only; add component inductance separately (see PACKAGE-INDUCTANCE.md).
.SUBCKT LEGA_BOARD_LIN12 P1_C38_a P1_C38_b P2_C39_a P2_C39_b P3_gate_high_a P3_gate_high_b P4_gate_low_a P4_gate_low_b
L_P1_C38 P1_C38_a P1_C38_b 28.2423n
L_P2_C39 P2_C39_a P2_C39_b 26.4809n
L_P3_gate_high P3_gate_high_a P3_gate_high_b 25.9656n
L_P4_gate_low P4_gate_low_a P4_gate_low_b 36.3715n
K_P1_C38_P2_C39 L_P1_C38 L_P2_C39 0.620844
K_P1_C38_P3_gate_high L_P1_C38 L_P3_gate_high 0.134147
K_P1_C38_P4_gate_low L_P1_C38 L_P4_gate_low 0.164910
K_P2_C39_P3_gate_high L_P2_C39 L_P3_gate_high 0.127616
K_P2_C39_P4_gate_low L_P2_C39 L_P4_gate_low 0.174519
K_P3_gate_high_P4_gate_low L_P3_gate_high L_P4_gate_low -0.006573
.ENDS LEGA_BOARD_LIN12

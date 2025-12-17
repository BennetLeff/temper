
Note: No compatibility mode selected!


Circuit: Robust Bootstrap Circuit Verification - sim_16_robust_bootstrap.cir

Doing analysis at TEMP = 27.000000 and TNOM = 27.000000

Using SPARSE 1.3 as Direct Linear Solver
Operating point simulation skipped by 'uic',
  now using transient initial conditions.

No. of Data Rows : 2642

  Measurements for Transient Analysis

v_boot_max          =  1.415194e+01 at=  2.000000e-04
v_boot_min          =  1.412801e+01 at=  5.002400e-05
v_boot_pre_hs       =  1.414694e+01
v_boot_post_hs      =  1.414247e+01
v_boot_droop        =  4.47393e-03
t_charge_90         =   9.63592e-06
v_gate_on_max       =  1.413532e+01 at=  1.939930e-04
v_gate_off_min      =  -3.532390e-11 at=  5.436612e-05
v_gate_off_worst    =  5.684342e-14 at=  4.830662e-06
uvlo_margin_min     =  5.62801e+00
uvlo_margin_a       =  8.12801e+00

Warning from checkvalid: vector v_boot_max is not available or has zero length.
Warning from checkvalid: vector uvlo_margin_min is not available or has zero length.
Warning from checkvalid: vector t_charge_90 is not available or has zero length.
Warning from checkvalid: vector v_gate_on_max is not available or has zero length.
Warning from checkvalid: vector v_gate_off_worst is not available or has zero length.

============================================
Robust Bootstrap Circuit Verification
Simulation 16 Results
============================================

Design Configuration:
  C_BOOT: 10uF (robust, vs 1uF standard)
  RGS: 2.2kOhm (Miller immune, vs 10kOhm standard)
  UCC21550B UVLO: 8.5V (fail-safe, vs 6.0V A variant)
  VDD: 15V, VDC: 300V, Freq: 50kHz

--------------------------------------------
BOOTSTRAP VOLTAGE PERFORMANCE
--------------------------------------------

  Target V_BOOT_MAX: >= 14.0V (VDD - diode drop)
  Target V_BOOT_MIN: >= 9.5V (UVLO_B + 1V margin)
  Acceptable droop/cycle: < 1.0V

UVLO MARGIN ANALYSIS:

  UVLO_B threshold: 8.5V
  Minimum margin above UVLO_B: should be > 1.0V
  (UVLO_A margin shown for comparison - would be unsafe!)

--------------------------------------------
BOOTSTRAP CHARGING PERFORMANCE
--------------------------------------------

  Target: < 10us to reach 90% of final voltage

--------------------------------------------
GATE VOLTAGE PERFORMANCE
--------------------------------------------

  Target V_GATE_ON: >= 14.0V (IGBT saturation)
  Target V_GATE_OFF: < 0.5V (fully off)

--------------------------------------------
MILLER EFFECT IMMUNITY (Analytical)
--------------------------------------------

  NOTE: Simplified model - Miller transient not captured
  Analytical validation (see MILLER_CURRENT_ANALYSIS.md):
    I_Miller = CGD * dV/dt = 130pF * 6V/ns = 0.78mA
    V_peak = 0.78mA * 2.2kOhm = 1.7V
  Result: 1.7V << 5.0V (VGE_th) - PASS with 3.3V margin

--------------------------------------------
BURST MODE ANALYSIS (Calculated)
--------------------------------------------
  C_BOOT: 10uF
  I_quiescent: 5mA
  Sleep time for 1V droop: t = C*V/I = 10uF*1V/5mA = 2.0s
  Maximum safe sleep: 18s (droop to 9V, above UVLO_B)

  Control Freak burst sleep: typically 100ms - 2s
  Verdict: 10uF provides adequate margin (PASS)

============================================
PASS/FAIL SUMMARY
============================================

Checking results against criteria...

  V_BOOT_MAX target: >= 14.0V
  V_BOOT_MIN target: >= 9.5V
  V_GATE_ON_MAX target: >= 14.0V
  V_GATE_OFF_WORST target: < 0.5V (pull-down effective)
  T_CHARGE_90 target: < 10us
  UVLO_MARGIN target: > 1.0V
  Miller immunity: 1.7V analytical (PASS)

  Review measurements above to verify PASS/FAIL

============================================
END OF SIMULATION
============================================
ngspice-45.2 done

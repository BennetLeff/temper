"""Stage 28 (DECISIONS 30): F2 = Schurter UMT-H 3403.0279.23 + R130 = Vishay AC05 0.15 ohm. Conservative numbers for the ledger.
Run: python3 -I bounds.py"""
V = 139.7                 # V rms, 127 V + 10 % (f2_variants.py:6)
R = 0.15                  # ohm, R130 (5 % part: 0.1425 at its low limit)
R_LOW = R * 0.95
UMTH_BREAK = 1500.0       # A, UL 1500 A @ 277 VAC / IEC 1500 A @ 250 VAC (Schurter UMT-H data sheet, note 2)
UMTH_DROP = 0.175         # V at 1.0 In = 3.15 A typ (same sheet): cold resistance ~0.0556 ohm
I_LOAD = 1.42             # A, PS3 input at 108 V (11-candidates/g06-g08-g10-supplies-sense-io/PROPOSALS.md P2)
CAP_AC05 = 125.0          # A2s at 0.15 ohm (Vishay AC pulse chart, 11-candidates/g06-g08-g10-supplies-sense-io/f2/parts_calc.py:33)
I2T_MELT = 39.0           # A2s at 10 In, UMT-H 3.15 A (data sheet)
I2T_CLEAR_CL = 67.0       # A2s, upper current-limiting clearing estimate (f2/PARTS-2026-10-13.md s1)
I2T_DESIGN = 3 * I2T_MELT # A2s, 3x melting design point (no clearing I2t is published)
ik_bound = V / R_LOW                                   # no source, fuse or copper impedance: an upper bound
ik_with_fuse = V / (R_LOW + UMTH_DROP / 3.15)
print(f"Ik bound (R130 at -5 % alone): {ik_bound:.0f} A -> {ik_bound / UMTH_BREAK:.4f} of 1.5 kA")
print(f"Ik with the fuse's cold resistance: {ik_with_fuse:.0f} A -> {ik_with_fuse / UMTH_BREAK:.4f}")
print(f"R130 continuous: {I_LOAD ** 2 * R:.3f} W of 5 W -> {I_LOAD ** 2 * R / 5:.4f}")
print(f"R130 pulse vs melting {I2T_MELT} A2s: {I2T_MELT / CAP_AC05:.4f}; vs current-limiting clearing {I2T_CLEAR_CL}: "
      f"{I2T_CLEAR_CL / CAP_AC05:.4f}; vs 3x melting {I2T_DESIGN}: {I2T_DESIGN / CAP_AC05:.4f}")
print(f"F2 load {I_LOAD} A of 3.15 A -> {I_LOAD / 3.15:.4f}; line {V} V of 277 VAC -> {V / 277:.4f}")

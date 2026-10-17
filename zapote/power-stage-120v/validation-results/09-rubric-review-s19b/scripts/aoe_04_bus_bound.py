# AOE-04: upper bound on bus peak if ALL coil energy at turn-off lands in the bus caps (ignores Cres and TVS).
import math
for C in (18.8e-6, 0.9*18.8e-6):
  for V0 in (198.0,286.0):
    for I in (110.0,155.4,178.1):
      E=0.5*77e-6*I*I
      print("C=%.2fuF V0=%3.0f Ioff=%5.1f E=%.3fJ -> Vbus<=%.0f V"%(C*1e6,V0,I,E,math.sqrt(V0*V0+2*E/C)))

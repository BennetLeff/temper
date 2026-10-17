# AOE-02: C5/C6 self-heating scaled from 22 A (ALT-C5C6.md:126-128: dT 7.8 K at 22 A, allowed 9.8 K at 85 C ambient)
for a in (22,26,28): print(a,"A tank: dT = %.1f K (allowed 9.8 K at 85 C, 20 K at 70 C)"%(7.8*(a/22)**2))

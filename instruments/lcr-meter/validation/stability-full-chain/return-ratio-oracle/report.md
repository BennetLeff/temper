# Independent return-ratio oracle

The matrix inverse/de-embedding calculation is independent of the determinant expression under review. Fixture Y11=1/1000+s·1nF;Y22=1/2000+s·2nF;Y12=2mS;Y21=10mS/(1+s·10µs). Therefore T=(Y12+Y21)/(Y11+Y22). The fixture includes reverse transmission and actual port loading.

| Bridge Ω | Samples | Max relative error vs analytic | Max disagreement with determinant shortcut |
|---:|---:|---:|---:|
| 1 | 1441 | 1.567104e-10 | 4.905973e-13 |
| 10 | 1441 | 1.183933e-12 | 5.984168e-14 |
| 100 | 1441 | 1.519298e-14 | 5.884193e-15 |
| 1000 | 1441 | 2.997602e-15 | 8.881792e-16 |

## Known-pole analytical regressions

W is counterclockwise winding of F=1+T for frequency −∞→+∞. Z=P−W. P is supplied from the independently known denominator; a winding without P is not a stability verdict.

| Fixture | P | W | Z | Unity directions |
|---|---:|---:|---:|---|
| one_pole_stable | 0 | 0 | 0 | Down |
| three_pole_unstable | 0 | -2 | 2 | Down |
| rhp_open_stabilized | 1 | 1 | 0 | Down |
| notch_stable_multiple | 0 | 0 | 0 | Down / Up / Down |
| notch_unstable_multiple | 0 | -2 | 2 | Down / Up / Down |

one_pole_stable crossings (local angle; not conventional PM):

- 1.58357169Hz Down; unwrapped -84.2608°; principal -84.2608°; signed separation from −1 95.7392°.

three_pole_unstable crossings (local angle; not conventional PM):

- 0.45015815Hz Down; unwrapped -211.5863°; principal 148.4137°; signed separation from −1 -31.5863°.

rhp_open_stabilized crossings (local angle; not conventional PM):

- 0.27566442Hz Down; unwrapped -120.0000°; principal -120.0000°; signed separation from −1 60.0000°.

notch_stable_multiple crossings (local angle; not conventional PM):

- 1.45236443Hz Down; unwrapped -174.7378°; principal -174.7378°; signed separation from −1 5.2622°.
- 1.78082710Hz Up; unwrapped -356.2429°; principal 3.7571°; signed separation from −1 -176.2429°.
- 15.58623940Hz Down; unwrapped -437.6359°; principal -77.6359°; signed separation from −1 102.3641°.

notch_unstable_multiple crossings (local angle; not conventional PM):

- 1.51855144Hz Down; unwrapped -183.3472°; principal 176.6528°; signed separation from −1 -3.3472°.
- 1.67650521Hz Up; unwrapped -346.6744°; principal 13.3256°; signed separation from −1 -166.6744°.
- 31.67023493Hz Down; unwrapped -443.9005°; principal -83.9005°; signed separation from −1 96.0995°.

Stable notch fixture: T=100(s²−0.2s+100)/[(s+1)(s²+20s+100)]. Closed polynomial s³+121s²+100s+10100 is Hurwitz because all coefficients are positive and121·100>10100. Its three unity crossings include an upward crossing with a negative local signed phase separation and a final downward crossing whose unwrapped phase is below−360°. It is nevertheless stable. At K=200,221·80<20100 and two closed poles are in the RHP.

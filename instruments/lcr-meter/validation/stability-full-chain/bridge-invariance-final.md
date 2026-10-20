# Final-network bridge invariance

Exact declared bridge values are checked in each accepted deck. The physical DC-node comparison excludes the inserted probe node and compares the same source/follower/TIA/FDA nodes. All four bridge values must agree in near-unity return ratio and unity-crossing angles; the all-frequency numerical limit is reported below.

| RF compensation | Fixture each terminal | Maximum DC-node change | Maximum normalized complex-return change (all / near-unity band) | Maximum crossing-angle change |
|---|---|---:|---:|---:|
| 0.0 pF | 0 pF | 1.51153e-9 V | 1.90538e-2 / 1.91163e-6 | 0.0000000° |
| 0.0 pF | 100 pF | 1.51153e-9 V | 2.11167e-2 / 1.76668e-6 | 0.0000000° |
| 2.2 pF | 0 pF | 1.51153e-9 V | 1.79365e-2 / 2.44424e-6 | 0.0000000° |
| 2.2 pF | 100 pF | 1.51153e-9 V | 1.79243e-2 / 1.58008e-6 | 0.0000000° |
| 4.7 pF | 0 pF | 1.51153e-9 V | 1.86134e-2 / 2.08087e-6 | 0.0000000° |
| 4.7 pF | 100 pF | 1.51153e-9 V | 1.75928e-2 / 9.37797e-7 | 0.0000000° |
| 10.0 pF | 0 pF | 1.51153e-9 V | 1.80267e-2 / 2.40951e-6 | 0.0000000° |
| 10.0 pF | 100 pF | 1.51153e-9 V | 1.89402e-2 / 2.97630e-6 | 0.0000000° |

At very high low-frequency loop gain, finite-precision cancellation in de-embedding a small bridge gives percent-level complex-return variation. The table reports that limitation rather than calling the whole curve invariant. The near-unity band is0.01<|T|<100; its error and every crossing angle are checked separately. Together with independent ideal-GM cuts, this supports the reported margins; it is not an all-frequency Nyquist proof.

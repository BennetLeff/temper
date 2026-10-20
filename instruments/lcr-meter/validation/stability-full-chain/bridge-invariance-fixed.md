# Final-network bridge invariance

Exact declared bridge values are checked in each accepted deck. The physical DC-node comparison excludes the inserted probe node and compares the same source/follower/TIA/FDA nodes. All four bridge values must agree in near-unity return ratio and unity-crossing angles; the all-frequency numerical limit is reported below.

| RF compensation | Fixture each terminal | Maximum DC-node change | Maximum normalized complex-return change (all / near-unity band) | Maximum crossing-angle change |
|---|---|---:|---:|---:|
| 100.0 pF | 0 pF | 1.51153e-9 V | 1.52380e-2 / 1.74286e-6 | 0.0000000° |
| 100.0 pF | 100 pF | 1.51153e-9 V | 1.47666e-2 / 1.34273e-6 | 0.0000000° |

At very high low-frequency loop gain, finite-precision cancellation in de-embedding a small bridge gives percent-level complex-return variation. The table reports that limitation rather than calling the whole curve invariant. The near-unity band is0.01<|T|<100; its error and every crossing angle are checked separately. Together with independent ideal-GM cuts, this supports the reported margins; it is not an all-frequency Nyquist proof.

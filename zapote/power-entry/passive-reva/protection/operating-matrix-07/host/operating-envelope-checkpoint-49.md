# Operating-envelope checkpoint 49

Status: **eight parent-accepted modeled normal points consolidated** under
`event-aware-normal-v1`. This report was built from the current per-case
`acceptance.json` and `parent-evidence.json` files. It does not mutate those
authoritative receipts, re-read raw archives, or claim a continuous envelope.

The nominal baseline remains separate: 120 V RMS, 190 ohm, acceptance receipt
`accepted-baseline-11/acceptance.json` (SHA-256
`18ce2902682b4cedb2880e260c15e731e599df4224dc842a70c85e9cadb6cf22`). Its
full-precision cycle-mean drift recomputes to `0.002730860843038929`, matching
the receipt within the recorded rounding tolerance.

## Accepted points

Each entry below gives line RMS, load resistance, modeled power/current, bus
range, drift, whole-prefix voltage peaks, and the report-only inductor peak.
The JSON companion carries the complete metrics, all margins, source closure,
acceptance SHA, parent-evidence SHA, and raw SHA/size/row count.

- **LL01** — 108 V, 416.460488957 ohm. Irms 3.869202 A; Pin 405.389658 W;
  Pload 359.070534 W; PF 0.970125. Bus 385.675669–387.716140 V, mean
  386.715892 V; drift 0.0014985231183201424. Peaks VD 387.776829 V,
  VB 387.716140 V, VDS 389.022540 V, |VGS| 14.982205 V; IL 25.067335 A
  report-only. Acceptance SHA `a4e09215acac4b80920257ceebfa96e4a9f7f618732cd24c778cca34f24105c7`;
  parent evidence SHA `095a25d663966afa53a9b2791275a3d7b1f566e9e103ab7b9c9a4d5dd6ade00f`.
  Raw SHA `734239f1c5f8ef65ea7ce356560931155a7bb3e0f6f96d91470513482739d29d`
  (2,151,465,343 bytes; 29,955,738 rows).

- **LL02** — 108 V, 208.230244479 ohm. Irms 7.509729 A; Pin 802.223598 W;
  Pload 705.399729 W; PF 0.989116. Bus 381.307658–385.188525 V, mean
  383.282760 V; drift 0.002726077553707517. Peaks VD 385.299212 V,
  VB 385.188525 V, VDS 386.595233 V, |VGS| 14.982208 V; IL 25.777695 A
  report-only. Acceptance SHA `542318b9fa0a061fa05af1616844320441f1ba59ac4a70275b14266c69c82eb2`;
  parent evidence SHA `a1a206357464554938c0e7ef0b476574e078f53b1b10839aa18dcb9efd05b341`.
  Raw SHA `dda21485b1b83e8bd19be8c6401e77f13e067e5744f70d5c725d9ffb5a9249c7`
  (2,132,735,226 bytes; 29,682,485 rows).

- **LL03** — 108 V, 115.683469155 ohm. Irms 13.412054 A; Pin 1438.880040 W;
  Pload 1242.516057 W; PF 0.993357. Bus 375.857870–382.392349 V, mean
  379.173791 V; drift 0.004155816804530984. Peaks VD 382.584396 V,
  VB 382.392349 V, VDS 383.958912 V, |VGS| 14.982208 V; IL 30.039218 A
  report-only. Acceptance SHA `224ac1a30d64b05b9b06d3319bb2a6dfaa3ce45330277fb97f8f50e82385041d`;
  parent evidence SHA `fcd2d43a5031f8507bcf872e9b5f8100476f7ed32a616ccc13de122dc1a7ea3e`.
  Raw SHA `c02cc9ede0e1bfe0c1aacbc5beabc025a8ab160d200a138a0acd52858a0e400c`
  (2,114,596,110 bytes; 29,479,028 rows).

- **LL04** — 120 V, 374.814440062 ohm. Irms 3.843647 A; Pin 445.943798 W;
  Pload 398.199053 W; PF 0.966842. Bus 385.201839–387.442138 V, mean
  386.344874 V; drift 0.0016527920840997289. Peaks VD 387.506047 V,
  VB 387.442138 V, VDS 388.751460 V, |VGS| 14.982215 V; IL 29.777999 A
  report-only. Acceptance SHA `f4a6ba5435add8b2946712b957d6f222cbc0384e28ccdd32980863249acdddfc`;
  parent evidence SHA `0e5f9d0bf84a64ab0b3ec307fa8432ee78981e5156b2a14fd7cb91ea95d2c4e0`.
  Raw SHA `a29f82eb7733ddb69a218dc6ba0299ff33c08b4e215d73f4efdcce842086f84b`
  (2,189,160,539 bytes; 30,400,545 rows).

- **LL05** — 120 V, 187.407220031 ohm. Irms 7.420222 A; Pin 880.539980 W;
  Pload 783.847484 W; PF 0.988897. Bus 381.211753–385.347086 V, mean
  383.302734 V; drift 0.0027487461221968558. Peaks VD 385.458665 V,
  VB 385.347086 V, VDS 386.758245 V, |VGS| 14.982213 V; IL 30.704239 A
  report-only. Acceptance SHA `44859f112de35192015ace76a4c1d0619c4689533eaceea62b8834b04c8f4206`;
  parent evidence SHA `07af7ef9cd10c6dcd1455a9ea1aecb1600a449c4d35bd536e03752b0bf26586d`.
  Raw SHA `7b1c540e3bdfd6f1741d13f872311ff92a12ceb84e2aaa42aeff3e77dd8642df`
  (2,167,895,869 bytes; 30,103,973 rows).

- **LL06** — 120 V, 104.115122239 ohm. Irms 13.198676 A; Pin 1574.420283 W;
  Pload 1383.936186 W; PF 0.994052. Bus 376.244081–382.998346 V, mean
  379.640270 V; drift 0.0038727265958028788. Peaks VD 383.190576 V,
  VB 382.998346 V, VDS 384.563792 V, |VGS| 14.982199 V; IL 32.104756 A
  report-only. Acceptance SHA `6eb356547ab348e16353cc9ec86cc3c520835f45ace8b5c8b6f1fddc921221a9`;
  parent evidence SHA `7792df142e38a7b156e2b24306108b1c52aa55ea6e22780c17112fa73dbe6298`.
  Raw SHA `eb1f88c49a5a6ef3d66f5c3853d35200430b5c765c55ce183403aab76d7bfd67`
  (2,145,942,203 bytes; 29,845,886 rows).

- **LL07** — 132 V, 374.814440062 ohm. Irms 3.505044 A; Pin 442.290077 W;
  Pload 398.384114 W; PF 0.955960. Bus 385.328039–387.506868 V, mean
  386.434659 V; drift 0.001562650118357812. Peaks VD 387.566527 V,
  VB 387.506868 V, VDS 388.809757 V, |VGS| 14.982226 V; IL 34.364070 A
  report-only. Acceptance SHA `b87c23441b4e55a5e46ec4ec19bfba3bd8fa02a456a9bbdb4aed0c41a0cc7b69`;
  parent evidence SHA `b6a4be20e03bd20d751e9df4bc32dec1fd8767f7d032a565f9cbea9d2fd501dd`.
  Raw SHA `5a507b1753deae083b438cd813dbdc3baac0bf90d123afab075218669ff72284`
  (2,220,002,011 bytes; 30,812,694 rows).

- **LL08** — 132 V, 187.407220031 ohm. Irms 6.698508 A; Pin 872.226383 W;
  Pload 785.858708 W; PF 0.986455. Bus 381.772480–385.749283 V, mean
  383.794262 V; drift 0.002508127779727223. Peaks VD 385.852732 V,
  VB 385.749283 V, VDS 387.146217 V, |VGS| 14.982220 V; IL 35.376249 A
  report-only. Acceptance SHA `8c6f8fb701395ecb95cbdfd980fc9a2f94ca1417a456542a18d39e460c3e8fdd`;
  parent evidence SHA `ab0821a4acf365b6a460e3066c5873a56d94dc343f3b93645c0afb8833e83ac6`.
  Raw SHA `dfd490459db468fd235d17a2c4d973ecac0624b9ac331fe42c89c41dc7efe8de`
  (2,192,811,017 bytes; 30,447,163 rows).

All eight receipts recompute cycle drift as
`(cycle_mean_3 - cycle_mean_1) / cycle_mean_1`; each matches its stored drift
within `1e-15`. The baseline matches within `1e-12` because its stored value is
rounded to fewer digits. Each declared parent-evidence SHA matches the current
SHA of its evidence file, and every case's five include hashes match the
baseline closure; only the generated `cold.cir` carries the authorized
VAC_RMS/RLOAD substitutions.

## Tightest observed margins across these eight points

- Source lower bound: 0.001 V, tied at LL01–LL03.
- Source upper bound: 0.001 V, tied at LL07–LL08.
- Settled bus lower envelope: 5.723620 V at LL03.
- Settled bus upper envelope: 21.379610 V at LL01.
- Cycle drift: 0.000844183 at LL03.
- Input Irms: 1.587946 A at LL03.
- VD peak: 112.223171 V at LL01.
- VB peak: 62.283860 V at LL01.
- VDS peak: 260.977460 V at LL01.
- Absolute VGS peak: 10.017774 V at LL07.
- Energy residual above its lower screen: 30.259155083 W at LL07.

The unchanged screens are source 107.999–132.001 V RMS, settled bus
370.134250–409.095750 V, drift below 0.005, Irms at most 15 A, VD at most
500 V, VB at most 450 V, VDS at most 650 V, absolute VGS at most 25 V, armed
and on fractions at least 0.99, and `Pin-Pload-dE/dt >= -max(1 W, 0.005 Pin)`.

## Excluded point and limits

LL09 is the declared 132 V / 104.115122239 ohm point. It is excluded from this
snapshot because it is live or not accepted at checkpoint time. These eight
points are discrete modeled samples; they do not establish behavior between
points, inductor-current or SOA limits, thermal performance, measured losses,
fault/protection behavior, or hardware qualification. Repeated timestamps
remain recorded strict-check rejections; complete event audit and metrics are
the basis of each scoped modeled acceptance.

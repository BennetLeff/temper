# PFC copper repair operation — 2026-09-12

Source revision was `cb80a1df1246cd9227431baa57d9f42381489fd9`. The [independent
PFC oracle](../../../validation/p1-current/oracle-2026-09-12/README.md) was
reviewed before editing: five determined 15 A RMS screening
findings were present, with 4.0 mm capacity 14.6513 A and 2.5 mm capacity
10.4205 A at 70 um copper and 20 C rise. The clean native baseline DRC used
KiCad 10.0.4 and reported zero violations.

The completed routing-only repair is the `minus` F.Cu segment
`e45ca754-66c7-4204-987e-e69d5ed1af44`, from (71.1,132) to (75.3,132), widened
from 4.0 mm to 6.0 mm. It attaches to the existing U12 pad and the existing
6 mm B.Cu branch. Native DRC and ERC both exit 0 with zero reported violations
after this edit.

The four remaining findings are centered bridge terminal stubs at the GBU
5.08 mm pitch: `1a8c9e36` B.Cu (30,115)-(30,123.5), `6be299ab` F.Cu
(35.08,115)-(35.08,124), `44d2e757` B.Cu (40.16,109)-(40.16,115), and
`e7dc2c72` F.Cu (45.24,115)-(45.24,108). Their original 2.5 mm widths were
retained. Centered uniform-width enlargement was tested at 6.0, 4.2, and
3.2 mm; each attempt aborted KiCad 10.0.4 with rc=134 before producing a DRC
result. Those aborted attempts are not treated as clearance findings. The
analytic geometry bound remains: a 2 mm clearance floor with 3.0 mm
neighboring land width leaves at most about 3.16 mm trace width at the pad
centerline, below the approximately 4.13 mm uniform-width screen needed for
15 A. No endpoint offset, pad modification, threshold change, or indeterminate
finding was used to hide that conflict. Exact before/after hashes for attempts
2 and 3 were not captured and are intentionally not reconstructed.

The repaired UUID remains determined at 15 A RMS, with final scalar capacity
`19.6580883186 A`; the four original bridge findings remain determined
failures in the unchanged-width stubs.

Final candidate hash: `84f4b325b25e4be71fcf990d9420ddb4346687ca1c28be63fb44a0d661fa2317`
(also recorded in `operation-manifest.json`).
Attempt stderr, native extraction, DRC, and ERC receipts are retained beside
this report. Hardware thermal qualification remains outside this screening
operation.

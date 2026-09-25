# Interface physical candidate 15 — reset hardware

This directory records a concrete source-capture and isolated permission
candidate. It uses the existing `SN74HCS74PWR`/`SN74LVC1G08DBVR` logic family,
the already screened `ISO7741F` 3-forward/1-reverse channel budget, and the
existing HOT-side `permit_safe → clear_ok → enable_good` chain.

The source-side HCS74 captures a low health condition asynchronously and
holds permission low. Recovery requires a source-health return, HOT reset
observation, a newer session/fresh intent, and a separate re-arm clock edge.
The processor's reset GPIO is not treated as an independent safety device.

The exact wiring and pin map are in [design.md](design.md). ISO7741-Q1 Rev G
is used as the pin-map authority for review; the exact ISO7741F orderable must
be checked before a schematic is captured. TI datasheet timing numbers are
component figures under their stated test load, not a qualified PFC stop
time. No PCB, firmware, production schematic, or BOM changed.

Primary references:

- https://www.ti.com/lit/ds/symlink/iso7741-q1.pdf
- https://www.ti.com/lit/ds/symlink/sn74hcs74.pdf
- https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf
- https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf
- https://www.ti.com/lit/ds/symlink/ucc27511a.pdf

The pin map is copied from TI's ISO7741-Q1 Rev G drawing because it is the
available current primary drawing for the same 3-forward/1-reverse topology;
the exact ISO7741F non-Q1 orderable and its timing table must be checked before
the candidate is promoted.

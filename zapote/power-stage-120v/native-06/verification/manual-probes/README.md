# Captured review probes

These are the one-shot inspection/orchestration scripts used for this review,
retained verbatim with historical absolute paths. They are not production
engineering-rule implementations. Production spacing, pad escape, stackup,
parity and authored-copper decisions belong to the Rust validators.

The hardware probe compares the provisional front-side exposed-metal envelopes
against all F.Cu pads, tracks, vias and filled zones; it reuses the pinned
geometry oracle. It does not model vertical assembly geometry or hidden metal.
The connectivity probe asks KiCad for connected pad UUIDs and retains the raw
clusters; the same zone UUID can represent disconnected filled islands.

The gate lengths sum the unbranched driver-output net up to the series resistor;
they exclude the resistor-to-MOSFET gate stub and are not loop inductance.

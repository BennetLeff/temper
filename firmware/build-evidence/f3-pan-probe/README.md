# F3 pan-probe analysis scripts (coil study, 2026-10-18)

Standalone time-domain RLC scripts behind the F3 decision (no pre-start pan probe on today's
hardware). The committed, gating evidence is `test_start_transient_evidence` in
`firmware/test/test_tank_freq.c` (ceca71cdc); these are the exploratory scripts it was distilled
from, kept so the figures in that commit's message can be re-derived.

- `bus_start.py`: start transient with the film bus charged to the line peak (continuous start at 60 kHz).
- `burst.py`: N-pulse bursts (one 8.3 µs pulse stays under every trip; two do not).
- `above.py`: start transient at the 59.97 kHz (80 MHz / 1334) start frequency against the 40.975 A firmware peak trip.
- `ringdown.py`: the recommended primitive (one pulse, then both low sides on; count CT_ZC-like crossings).
- `zc.py`: single-pulse peak and crossings per load.

Run with `python3 -I <script>.py`; standard library only.

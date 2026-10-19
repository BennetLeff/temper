# F3 pan-probe analysis scripts (coil study, 2026-10-18)

Standalone time-domain RLC scripts behind the F3 decision (no pre-start pan probe on today's
hardware). The committed, gating evidence is `test_start_transient_evidence` in
`firmware/test/test_tank_freq.c` (ceca71cdc); these are the exploratory scripts it was distilled
from, kept so the figures in that commit's message can be re-derived.

- `bus_start.py`: start transient with the film bus charged to the line peak (continuous start at 60 kHz).
- `burst.py`: N-pulse bursts (one 8.3 µs pulse stays under every trip; two do not).
- `above.py`: starts above resonance per pan class.
- `ringdown.py`, `zc.py`: the recommended primitive (short pulse, low sides on, count CT_ZC edges).

Run with `python3 -I <script>.py`; standard library only.

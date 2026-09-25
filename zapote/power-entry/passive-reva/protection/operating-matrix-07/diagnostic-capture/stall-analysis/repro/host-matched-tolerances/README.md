# Independent boundary rerun

Host review found that the worker report claimed the production tolerances,
but its decks set only `numdgt`. The original report has been corrected.
These copied fixtures explicitly set `method=trap reltol=2e-4 abstol=1e-10
vntol=1e-7 trtol=1`, matching the full run's analog tolerances and the
XSPICE-selected truncation setting. The isolated fixture has no XSPICE
devices and does not reproduce their event interaction.

All three simulator runs and strict Rust reductions exit zero. The early
edge has a minimum timestamp separation of 1.50291e-16 s; both late-edge
fixtures have a minimum of 1.96315e-12 s. None has duplicate timestamps.
This is a negative reproduction result, not a validated repair or an
operating-point acceptance. See individual `.stats` and `results.json`.

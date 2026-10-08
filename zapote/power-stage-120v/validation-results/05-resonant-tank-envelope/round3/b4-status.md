# B4 — ZVS map remains blocked

The completed event table has 91,905 ideal switching events. Of these,
45,360 are below A1's 120 V minimum bus domain. A1's required inductance
independence check failed, including a 450 ns ZVS case, and B1 stopped at
its first heuristic-scenario stress failure. Thus no validated board ZVS
threshold surface covers these events.

`outputs/switching-events.csv` retains the bus voltage, current and direction
at each event; its threshold field stays empty and its pending verdict is
not interpreted as either ZVS or hard switching. No `zvs_map.png` with
invented zeroes or extrapolated thresholds is issued.

To finish, first qualify the board/gate/common-source inductance mapping
and switching behavior. Obtain thresholds over the rectified bus domain
(including below 120 V), validate any interpolation and dead-time behavior,
then join those thresholds to the saved event records. The tank model's
ideal frequency-control events also need the stated finite-dead-time and
protection limitations retained.

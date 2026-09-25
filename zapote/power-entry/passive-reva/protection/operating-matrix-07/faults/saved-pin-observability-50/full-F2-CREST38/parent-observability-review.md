# Saved ISENSE observation — F2-CREST38

The complete saved trace was scanned without another solver run or large output.
All 32,237,324 rows, including 61 repeated-time intervals, were retained. All
three pipeline children exited0; the original raw hash is unchanged.

The modeled pin ranged from **-0.306538 V to +0.000116321 V**. No saved row
exceeded TI's cited absolute voltage limits. The strict recommended-voltage
comparison does not pass: 1,241,371 rows are above0 V, reaching0.116321 mV.
These are sample counts, not durations; they do not establish a physical
failure or justify changing the comparison tolerance after the measurement.

Both modeled PCL request and PCL hold remained zero throughout. This case
therefore does not exercise peak-current limiting or a large negative clamp
excursion. It cannot qualify the clamp. The trace lacks diode current and
bridge-minus voltage, and the selected Vishay low-current VF versus
temperature/lot guarantee remains unavailable. Neither silicon input-current
compliance nor hardware behavior is established.

The companion parent review binds the input, tool and output identities to the
existing exact F2-CREST38 acceptance. This is a diagnostic observation, not a
new circuit acceptance or a resolution of the selected-part gap.

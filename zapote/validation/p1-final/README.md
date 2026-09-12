# P1 candidate coverage and remaining model work

The current adapter inventories PFC rectifier, choke, boost-switch, bus,
auxiliary/control and protective-earth nets, plus gate output, bias and Kelvin
return nets. Native objects are candidates, not a solved branch-current graph.

Every selected native via receives a candidate record. Missing waveform,
plating and current-density bounds produce per-candidate INDETERMINATE results.
The optional analytical barrel screen uses pi × drill × plating and an authored
RMS current-density bound. Equal shares must sum to one. This does not establish
current distribution, pulse heating or physical qualification.

Pads are associated with a nearby same-net trace as candidates. This does not
prove copper contact or entry width. The proposed rectangular pad projection
was rejected during coordinator review: full pad width can conceal a narrow
trace, and rectangular envelopes do not establish actual copper intersection.
The candidate validator therefore cannot PASS entry geometry. Exact native
polygon/chord modeling and branch-current extraction remain software work.

The proposed additional scalar surface-path validator was removed. It
duplicated the existing supplied-evidence comparison without implementing a
surface path. Actual creepage modeling, material/cutout authority and an
independent oracle remain open. No package-size or clearance substitution is
accepted as creepage evidence.

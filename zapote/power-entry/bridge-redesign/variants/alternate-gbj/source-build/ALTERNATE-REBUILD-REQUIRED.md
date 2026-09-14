# GBJ alternate source input

This directory is a source-build input copy of canonical `source-build-22`. The resolved bridge identity is changed to Diodes GBJ2510-F with pin map 1=plus, 2=ac1, 3=ac2, 4=minus, and the CSV footprint is changed to `Diode_THT:Diode_Bridge_GBJ2510`. It is not a completed Atopile build: the source compiler and strict design-bundle bridge must be rerun after the GBJ component declaration is made authoritative. The copied build receipt is retained only as provenance for the starting graph.

The board draft rotates the footprint 180 degrees and binds local pin 1 to
`plus` and local pin 4 to `minus`, matching the Diodes drawing. The regenerated
source/native bundle must preserve that pin map.

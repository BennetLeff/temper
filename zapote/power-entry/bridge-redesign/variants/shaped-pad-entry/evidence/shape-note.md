# Shaped pad-entry evidence

The four bridge branches retain the frozen GBU2510A package and net identity.
Each branch now has a short 3.0 mm section at the pad followed by a 4.2 mm
transition into the existing 6 or 8 mm route. The transition is explicit in
the saved KiCad board; it is not a pad-area or current-capacity proxy.

Native KiCad 10 checks on `section.kicad_pcb`:

* ERC: 0 violations
* DRC (`--all-track-errors --schematic-parity --severity-all`): 0 violations,
  0 unconnected, 0 schematic-parity issues

The retained native/manufacturing JSON was generated before this geometry edit
and is deliberately not presented as fresh evidence. A native extraction must
be rerun before the Rust current screen or thermal model can accept this
candidate. Until then the candidate status is `indeterminate`.


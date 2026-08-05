"""Internal: trace, via, and segment extraction from KiCad board objects.

Migrated to the Rust parse engine (``temper_design_bundle_python.parse_engine``,
Wave 4 Phase 3 candidate 3) — ``_extract_traces_from_pcb`` /
``_extract_vias_from_pcb`` now run inside ``parse_kicad_pcb`` on the Rust side.
This module exists as the migration boundary marker; it imports no kiutils and
exposes no names (the only historical consumer, ``io.kicad_parser``, delegates
to the engine directly).
"""

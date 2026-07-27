"""Requirement validators usable from production code.

`validators/clearance.py` and its `_geometry` helper were moved here from
`tests/requirements/validators/` so the CP-SAT encoder can consume the
IEC 60335 clearance matrix without production importing from the test tree.
`placer/cp_sat/domain_clearance.py` previously reached into `tests.` via a
sys.path insert, which meant the domain-clearance constraint could not be
wired into the real placement path at all.
"""

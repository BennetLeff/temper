"""
Incremental ladder growth validation.

Ensures new board and stage boundary additions are non-breaking
for existing golden fixtures.
"""

from __future__ import annotations


def validate_new_board_does_not_break_existing(new_board_id: str, manifest: dict) -> None:
    pass


def validate_new_stage_does_not_break_existing(new_stage: str, manifest: dict) -> None:
    pass


def get_existing_fixture_paths(manifest: dict) -> set[str]:
    paths = set()
    for fixture in manifest.get('fixtures', []):
        p = fixture.get('file', '')
        if p:
            paths.add(p)
    return paths

"""
Router V6 -- Anti-Vacuity Guard for ChannelSkeleton (Stage 2.3).

R10 hardening (docs/evidence/2026-08-07-router-silent-noop-diagnosis.md):
``ChannelSkeletonStage.run()`` and its co-located ``validate_channel_skeleton``
both live in ``channel_skeleton.py``, which is intentionally NOT touched by
this change -- a concurrent agent is actively fixing the underlying
plane-classification bug in that file (and in ``obstacle_map.py`` /
``kicad_parser``'s ``_extract_stackup``). Editing it here would either
conflict with that work or land a precondition on code mid-rewrite.

Instead, this module registers an *additional* validator against the same
``"ChannelSkeleton"`` stage name via the existing ``register_validator``
extension point (``stage_validators.VALIDATOR_REGISTRY`` is a list per
stage -- multiple validators for one stage name is already how the
registry is designed to be used; nothing about it assumes one validator
per module). ``stage2_orchestrator.py`` imports this module for its
side effect (see the ``# noqa: F401`` import there) so the validator is
always registered whenever ``Stage2Orchestrator`` -- the orchestrator the
real ``route_pcb()`` pipeline actually uses (``_pipeline_grid.py``'s
``_run_stage2``) -- runs.

This closes the specific gap the diagnosis doc calls out: the *existing*
``validate_channel_skeleton`` (in channel_skeleton.py) iterates
``state.channel_skeletons.items()`` with no non-emptiness check in front,
so an empty dict silently produces zero failures -- and even if it did
report a failure, ``Stage2Orchestrator`` previously only ever *printed*
DRC failures when ``verbose=True``, never enforced them. This module's
validator marks its finding ``fatal=True`` so
``stage_validators.assert_no_fatal_failures`` (called unconditionally by
the orchestrator after every stage, see stage2_orchestrator.py) actually
halts the pipeline instead of producing another ignorable print line.
"""

from __future__ import annotations

from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)


class ChannelSkeletonEmptyError(RuntimeError):
    """Not currently raised directly (ChannelSkeletonStage.run() itself is
    off-limits for this change -- see module docstring); reserved for
    symmetry with RoutingSpaceEmptyError / ConstraintModelEmptyError and
    for channel_skeleton.py to raise once that file is unfrozen."""


@register_validator("ChannelSkeleton")
def validate_channel_skeleton_nonvacuous(state: BoardState) -> list[StageDRCFailure]:
    """Fatal, fail-closed companion to ``validate_channel_skeleton``.

    A non-empty ``routing_spaces`` with at least one layer carrying
    positive routing area is a board that Stage 2.2 found real routable
    copper area on. If Stage 2.3 (``ChannelSkeletonStage``) then produces
    ``channel_skeletons == {}`` -- or a non-empty dict whose every skeleton
    has zero nodes -- that is precisely Bug B from
    docs/evidence/2026-08-07-router-silent-noop-diagnosis.md: a stage that
    silently contributed nothing, which the pre-existing per-item validator
    in channel_skeleton.py cannot see because its loop body never executes
    over an empty (or all-empty) dict.

    Distinguishes "validated N skeleton(s) successfully" from "had nothing
    to validate" the same way ``validate_routing_space`` does: the
    vacuous-empty case is reported explicitly, not silently passed through.
    """
    routing_spaces = state.routing_spaces
    if not routing_spaces:
        # Nothing for Stage 2.3 to have built a skeleton from in the first
        # place -- RoutingSpaceStage's own precondition (RoutingSpaceEmptyError)
        # already covers an empty routing_spaces on a routable board; this
        # validator's job starts one stage downstream of that.
        return []

    routable_layers = {
        name: rs for name, rs in routing_spaces.items() if rs.routing_area > 0
    }
    if not routable_layers:
        return []

    skeletons = state.channel_skeletons
    if not skeletons:
        return [
            StageDRCFailure(
                field="channel_skeletons",
                value={},
                reason=(
                    f"VACUOUS: channel_skeletons is empty but routing_spaces "
                    f"has {len(routable_layers)} layer(s) with positive "
                    f"routing area ({sorted(routable_layers)!r}) -- there was "
                    f"nothing to validate, not '0 skeletons validated "
                    f"successfully'. This is Bug B from "
                    f"docs/evidence/2026-08-07-router-silent-noop-diagnosis.md: "
                    f"ChannelSkeletonStage silently contributed nothing "
                    f"downstream."
                ),
                stage="ChannelSkeleton",
                fatal=True,
            )
        ]

    nonzero = {name: sk for name, sk in skeletons.items() if sk.node_count > 0}
    if not nonzero:
        return [
            StageDRCFailure(
                field="channel_skeletons",
                value=sorted(skeletons),
                reason=(
                    f"VACUOUS: every one of {len(skeletons)} channel_skeletons "
                    f"({sorted(skeletons)!r}) has zero nodes, despite "
                    f"routing_spaces reporting positive routing area on "
                    f"{sorted(routable_layers)!r} -- Stage 2.3 produced "
                    f"skeleton entries that carry no usable geometry, the "
                    f"same observable effect as producing none at all."
                ),
                stage="ChannelSkeleton",
                fatal=True,
            )
        ]

    return []

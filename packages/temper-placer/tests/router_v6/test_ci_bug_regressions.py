"""
Bug-fix regression guards: 4 pre-existing CI failures.

Each test pins one of the bugs that the closure-rate plan surfaced
when running the closure test on a freshly-cloned main.  None of
these bugs were caught by the existing test suite because:

  Bug 1: ``python -m temper-placer regression`` was never run as
         part of the unit suite.
  Bug 2: the corpus subcommand ``args.boards`` mismatch was hidden
         by a click-based wrapper that did not use ``argparse`` for
         the corpus subcommand.
  Bug 3: the closure test path requires the full PCB, parser,
         and router stack to be present -- the existing unit
         tests stub these out.
  Bug 4: the duplicate ``_segment_search`` masked the first one
         because the second definition (without ``congestion_tensor``)
         shadows the first; ``_astar_route_multilayer`` then passes
         ``congestion_tensor=`` and crashes with a TypeError.
"""
from __future__ import annotations

import inspect


def test_segment_search_accepts_congestion_tensor():
    """Bug 4 regression guard: ``_segment_search`` must accept
    ``congestion_tensor`` as a keyword argument.  Two definitions
    of the function used to coexist; the second (without the kwarg)
    shadowed the first, breaking ``_astar_route_multilayer`` with
    a TypeError whenever routing was actually exercised end-to-end.
    """
    from temper_placer.router_v6.astar_pathfinding import _segment_search

    sig = inspect.signature(_segment_search)
    assert "congestion_tensor" in sig.parameters, (
        f"_segment_search must accept congestion_tensor kwarg; "
        f"got parameters {list(sig.parameters)}"
    )


def test_astar_grid_imports_pin_world_helpers():
    """Bug 3 regression guard: ``_extract_pad_centers_per_net`` in
    ``router_v6/astar_grid.py`` uses ``pin_world_position``,
    ``pin_world_radius``, and ``pin_world_layer`` but the module
    did not import them.  The closure test crashed with
    ``name 'pin_world_position' is not defined`` as a result.
    """
    import temper_placer.router_v6.astar_grid as mod

    src = inspect.getsource(mod)
    for name in ("pin_world_position", "pin_world_radius", "pin_world_layer"):
        assert name in src, (
            f"router_v6/astar_grid.py must reference {name} as an "
            f"imported name (or call site); the closure test path "
            f"crashes without it"
        )


def test_corpus_cli_uses_singular_board_attr():
    """Bug 2 regression guard: ``run_corpus`` (called by
    ``temper-placer regression run-corpus --board <name>``) used
    to read ``args.boards`` (plural) while the argparse subcommand
    defined ``--board`` (singular).  The function crashed with
    ``AttributeError: 'Namespace' object has no attribute 'boards'``.
    """
    from temper_placer.regression.cli import run_corpus

    src = inspect.getsource(run_corpus)
    # The function must read ``args.board`` (singular) -- the
    # argparse subcommand defines ``--board`` singular.
    assert "args.board" in src, (
        "run_corpus must read args.board (singular) to match the "
        "argparse subcommand's --board option"
    )
    # And it must NOT read the (unrelated) ``args.boards`` plural.
    assert "args.boards" not in src, (
        "run_corpus reads args.boards (plural) but the argparse "
        "subcommand defines --board (singular) -- this was Bug 2"
    )


def test_temper_placer_top_level_main_loads():
    """Bug 1 regression guard: ``python -m temper-placer <subcmd>``
    requires a ``temper_placer/__main__.py`` at the module root.
    Without it, the install reports
    ``No module named temper-placer.__main__`` and the CI fails."""
    import importlib

    mod = importlib.import_module("temper_placer.__main__")
    assert hasattr(mod, "main"), (
        "temper_placer/__main__.py must expose a callable 'main' "
        "(dispatcher to the click CLI)"
    )
    assert callable(mod.main), "temper_placer.__main__.main must be callable"

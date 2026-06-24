"""Top-level __main__ for the ``temper_placer`` package.

Enables ``python -m temper_placer <subcommand>`` invocations from
the CLI's installed entry point.  Mirrors
``temper_placer/cli/__main__.py`` so the hyphenated distribution
name (``temper-placer``) and the underscored module name
(``temper_placer``) both dispatch to the same Click command tree.
"""

from temper_placer.cli import main

if __name__ == "__main__":
    main()

"""Temper PCB router — console entry point.

Entry point: ``temper-route`` (pyproject.toml: ``temper_tools.routing.route:main``).
"""


def main(*, pcb: str | None = None, output: str | None = None) -> None:
    """Route a PCB using the internal router."""
    raise NotImplementedError("temper_tools.routing.route.main is not yet implemented")

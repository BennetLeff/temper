"""Initial ordinary Python helpers; pcb is supplied by the isolated worker."""


def inspect_board():
    return pcb.call('inspect', {})  # noqa: F821


def check_board():
    return pcb.call('check', {})  # noqa: F821

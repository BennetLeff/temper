"""Signal handling utilities for the CLI (interrupt guard)."""

from __future__ import annotations

import signal
from contextlib import contextmanager
from typing import Generator


class InterruptGuard:
    """Manages a SIGINT handler that sets an interrupted flag.

    Usage in the optimize command:
        guard = InterruptGuard()
        try:
            # long-running work
            if guard.interrupted:
                raise KeyboardInterrupt()
        finally:
            guard.restore()
    """

    def __init__(self) -> None:
        self.interrupted = False
        self._original = None

    def __enter__(self) -> "InterruptGuard":
        self._original = signal.signal(signal.SIGINT, self._handler)
        return self

    def __exit__(self, *args: object) -> None:
        self.restore()

    def _handler(self, sig: int, frame: object) -> None:
        self.interrupted = True

    def restore(self) -> None:
        if self._original is not None:
            signal.signal(signal.SIGINT, self._original)
            self._original = None


@contextmanager
def with_interrupt_guard() -> Generator[InterruptGuard, None, None]:
    """Context manager that installs a SIGINT handler and restores on exit."""
    guard = InterruptGuard()
    try:
        yield guard
    finally:
        guard.restore()


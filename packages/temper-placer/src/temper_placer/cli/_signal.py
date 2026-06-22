"""Signal handling utilities for the CLI (interrupt guard)."""
from __future__ import annotations
import signal

class InterruptGuard:
    def __init__(self):
        self.interrupted = False
        self._original = None
    def __enter__(self):
        self._original = signal.signal(signal.SIGINT, self._handler)
        return self
    def __exit__(self, *args):
        self.restore()
    def _handler(self, sig, frame):
        self.interrupted = True
    def restore(self):
        if self._original is not None:
            signal.signal(signal.SIGINT, self._original)
            self._original = None

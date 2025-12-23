"""Functional, immutable trace for explainability.

This module provides a composable, immutable trace system for recording
decisions throughout the placement and routing pipeline.

Key features:
- Immutable: Trace objects are frozen, operations return new traces
- Monoid: Traces compose via + operator with identity element
- Lazy: Natural language generation only when queried
- Simple: Just (subject, value, because) tuples

Example:
    >>> trace = Trace.empty()
    >>> trace = trace.add("Q1", (45.2, 12.3), "Minimize commutation loop")
    >>> trace = trace.add("Q1", (43.8, 11.9), "Thermal edge constraint")
    >>> print(trace.why("Q1"))
    Q1 is at (43.8, 11.9) because:
      - Minimize commutation loop
      - Thermal edge constraint
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Entry:
    """Single trace entry.
    
    Attributes:
        subject: Component ref, net name, or other identifier
        value: The decided value (position, path, layer, etc.)
        because: Natural language reason (from PCL constraint or algorithm)
    """
    subject: str
    value: Any
    because: str
    
    def __repr__(self) -> str:
        return f"Entry({self.subject!r}, {self.value!r}, {self.because!r})"


@dataclass(frozen=True)
class Trace:
    """Immutable, composable trace.
    
    A Trace is a monoid over Entry tuples:
    - Identity: Trace.empty()
    - Operation: trace1 + trace2
    - Associativity: (a + b) + c == a + (b + c)
    - Identity law: empty() + x == x == x + empty()
    
    Traces are immutable - all operations return new Trace objects.
    
    Example:
        >>> trace1 = Trace.empty().add("Q1", (10, 20), "Initial placement")
        >>> trace2 = Trace.empty().add("Q2", (30, 40), "Adjacent to Q1")
        >>> combined = trace1 + trace2
        >>> len(combined.entries)
        2
    """
    entries: tuple[Entry, ...] = ()
    
    @staticmethod
    def empty() -> "Trace":
        """Return empty trace (monoid identity).
        
        Returns:
            Empty trace with no entries
        """
        return Trace(())
    
    def add(self, subject: str, value: Any, because: str) -> "Trace":
        """Add entry to trace, returning NEW trace (immutable).
        
        Args:
            subject: Component ref, net name, etc.
            value: The decided value
            because: Natural language reason
            
        Returns:
            New trace with entry appended
            
        Example:
            >>> trace = Trace.empty()
            >>> trace = trace.add("Q1", (45.2, 12.3), "Proximity constraint")
            >>> len(trace.entries)
            1
        """
        return Trace(self.entries + (Entry(subject, value, because),))
    
    def __add__(self, other: "Trace") -> "Trace":
        """Compose traces (monoid operation).
        
        Args:
            other: Trace to append
            
        Returns:
            New trace with combined entries
            
        Example:
            >>> trace1 = Trace.empty().add("Q1", (10, 20), "Reason 1")
            >>> trace2 = Trace.empty().add("Q2", (30, 40), "Reason 2")
            >>> combined = trace1 + trace2
            >>> len(combined.entries)
            2
        """
        return Trace(self.entries + other.entries)
    
    def for_subject(self, subject: str) -> "Trace":
        """Filter trace to specific subject.
        
        Args:
            subject: Subject to filter by
            
        Returns:
            New trace containing only entries for this subject
            
        Example:
            >>> trace = Trace.empty()
            >>> trace = trace.add("Q1", (10, 20), "Reason 1")
            >>> trace = trace.add("Q2", (30, 40), "Reason 2")
            >>> trace = trace.add("Q1", (15, 25), "Reason 3")
            >>> q1_trace = trace.for_subject("Q1")
            >>> len(q1_trace.entries)
            2
        """
        return Trace(tuple(e for e in self.entries if e.subject == subject))
    
    def why(self, subject: str, max_reasons: int = 3) -> str:
        """Generate natural language explanation for subject.
        
        This is lazy - NL is only generated when queried, not when
        entries are added.
        
        Args:
            subject: Subject to explain
            max_reasons: Maximum number of reasons to show (default 3)
            
        Returns:
            Natural language explanation string
            
        Example:
            >>> trace = Trace.empty()
            >>> trace = trace.add("Q1", (45.2, 12.3), "Minimize commutation loop")
            >>> trace = trace.add("Q1", (43.8, 11.9), "Thermal edge constraint")
            >>> print(trace.why("Q1"))
            Q1 is at (43.8, 11.9) because:
              - Minimize commutation loop
              - Thermal edge constraint
        """
        entries = self.for_subject(subject).entries
        
        if not entries:
            return f"No decisions recorded for {subject}"
        
        # Get final value
        final = entries[-1]
        
        # Format value nicely
        if isinstance(final.value, tuple) and len(final.value) == 2:
            value_str = f"({final.value[0]:.1f}, {final.value[1]:.1f})"
        else:
            value_str = str(final.value)
        
        # Build explanation
        lines = [f"{subject} is at {value_str} because:"]
        
        # Show top N reasons
        for entry in entries[:max_reasons]:
            lines.append(f"  - {entry.because}")
        
        # Indicate if there are more
        if len(entries) > max_reasons:
            lines.append(f"  ... and {len(entries) - max_reasons} more reasons")
        
        return "\n".join(lines)
    
    def __len__(self) -> int:
        """Return number of entries in trace."""
        return len(self.entries)
    
    def __bool__(self) -> bool:
        """Return True if trace has entries."""
        return len(self.entries) > 0
    
    def __repr__(self) -> str:
        return f"Trace({len(self.entries)} entries)"

# Make voltage spacing part of the construction contract

A native DRC pass under a 0.2 mm default does not validate a PFC layout's
high-voltage spacing. Classify every elevated net, including intermediate
feedback taps, and check each physical layer against the declared profile.
Keep package-terminal geometry visible: this attempt used larger feedback
resistors and revised bridge lands rather than suppressing pad failures.

Do not trust inherited exact-part numbers. The donor's B32671L6474K000
claim did not match TDK's ordering table. Source22 uses the independently
verified B32672P6474K000. Transfer the verification procedure, not these exact
parts or numeric spacing floors, to a different unit.

Preserve both source-graph and copper-connectivity checks. The historical
unrouted fixture and the new routed fixture distinguish correct pin assignments
from actual connected copper. A mutation test must start from a passing source;
a source already rejected for a different change is a vacuous counterexample.

The routed unit passes construction checks but remains INDETERMINATE for
hardware qualification. Neither DRC, memory notes, nor a native 3D render
establishes current capacity, thermal performance or product safety. No measured
agent-memory improvement is claimed by this attempt.

# Correction to completion-audit-114

Audit114 made one material arithmetic error. The stated 1,800 W target is
**nominal mains input**, so PMP10948's efficiency must not be applied to it.
At 120 VAC, 1,800 W input is 15.0 A only under ideal power factor. At 108 VAC,
the unchanged 15 A screen permits at most 1,620 W input under ideal power
factor. Any PF below one raises current. These are arithmetic comparisons to
the existing model screen, not hardware limits, and do not justify changing
the screen. The TI references provide context only; no TI efficiency is
inherited by the target or local model.

The remaining audit conclusions stand. SW-SHORT is legitimately
**INDETERMINATE** because its saved attempt stops before the .662 s endpoint;
it lacks a complete fault envelope even though it contains pre-fault rows.
The smallest useful next evidence, without rerunning a solver, is a
parent-approved prefix-only audit of the immutable partial archive through the
last sample at or before .650 s. That audit must independently report its
selected endpoint, row and finite/nondecreasing checks, electrical extrema,
drift, phase/neighbor evidence, and ARM/PERMIT/q/en prefix. It would document
whether the attempted fault had an accepted starting condition, but it cannot
waive the missing post-fault endpoint or upgrade the whole attempt.

No other material mismatch was found in audit114: the normal matrix remains
modeled-only; DIODE remains an event-window failure; BOTH remains a completed
transport with an all-row node-screen failure and pending parent prefix/legacy
closure; BYPASS and the final reproducibility report/index remain open. Model
and component limits remain explicit and unqualified.

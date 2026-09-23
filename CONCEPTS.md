# Concepts

Shared domain vocabulary for this project — entities, named processes, and
status concepts with project-specific meaning. Seeded with core domain
vocabulary, then accretes as ce-compound and ce-compound-refresh process
learnings; direct edits are fine. Glossary only, not a spec or catch-all.

## PCB safety and floorplanning

### Voltage domain

A set of electrically related nets assigned the same safety-potential class so
the board can derive which copper boundaries require functional, basic, or
reinforced insulation.

### Isolation barrier

A physical board region that separates high-voltage and extra-low-voltage
copper across every copper layer; a declared domain boundary or a passing
after-the-fact distance check is not itself an isolation barrier.

### Domain-first floorplan

A board-layout process that partitions voltage domains and reserves their
isolation corridors before individual component placement and routing are
optimized.

### Safety signature

A documentation-and-evidence identity for one clearance or creepage finding,
including the involved components, metric, insulation boundary, and pair kind,
used as a set so resolving one hazard cannot hide the introduction of another.

### DRC ceiling

A board-content-bound, measured upper limit for each design-rule-check
category that acts as a regression ratchet, not as evidence that the design
debt below the limit is acceptable.

### Bounded candidate study

A predeclared staged family of scratch placement variants, with routing only
for candidates that survive earlier vetoes, evaluated against the applicable
independent safety, connectivity, mechanical, and DRC gates before any
production-board change is allowed.

Its reported denominator includes only candidates produced by a validated
family and authoritative measurement instruments; a calibration run that uses
the wrong coordinate convention or offers no physically admissible option is
retained as diagnostic evidence but excluded from the design verdict.

### Stopped-indeterminate

A bounded candidate study terminal state in which useful scoped measurements
exist but a required instrument, route, or evidence condition cannot support
either promotion or a conclusive negative certificate.

It preserves the measured family result while forbidding uncertainty from
authorizing wider scope or being restated as physical impossibility.

## Power entry

### Power-entry authorization session

One receiver-issued, durably identified preparation and start opportunity. A
captured HOT fault, STOP, reset, or expired transaction invalidates it; detector
recovery or replayed commands cannot restore it. A later start requires physical
disarm, a new identifier, controlled revalidation, and a fresh user press.

## Simulation evidence

### Development cross-check

A simulation case used to expose or diagnose a model defect, then rerun after
the model changes; it remains useful evidence about the model but is no longer
a blind holdout or independent qualification receipt.

### Behavioral model evidence boundary

The explicit limit between what a runnable approximate model can support (such
as feedback, power-path, convergence, and restart checks) and claims that need
independent model or hardware evidence (such as transient accuracy, stability,
efficiency, thermal behavior, and fault performance).

## Measurement and evidence

### Evidence class

The provenance category a reported number may claim, in descending strength:
measured, source-bound, modelled, assumed. A number is never reported under a
stronger class than its provenance supports.

Agreement between two implementations of the same model does not upgrade a
class: two models agreeing is still modelled, and a discrepancy between them is
a condition-specific finding rather than a correction factor.

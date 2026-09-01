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

### Isolation authority role

The purpose and decision weight of one clearance or creepage value, such as a scoped standards derivation, a project design floor, a fabrication constraint, or a governing production requirement. Values with different roles are not interchangeable merely because they share a metric or insulation-tier label.

### DRC ceiling

A board-content-bound, measured upper limit for each design-rule-check
category that acts as a regression ratchet, not as evidence that the design
debt below the limit is acceptable.

### Bounded candidate study

A predeclared staged family of scratch placement variants, with routing only
for candidates that survive earlier vetoes, evaluated against the applicable
independent safety, connectivity, mechanical, and DRC gates before any
production-board change is allowed.

A candidate inherits only the authority of the stage it passed. In particular,
a clearance/creepage prefilter result is neither route-ready nor a complete
hard-veto survivor; those labels require the later materialized connectivity,
mechanical, containment, safety-signature, and DRC verdicts.

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

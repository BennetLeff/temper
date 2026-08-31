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

A predeclared finite family of scratch placement-and-routing variants evaluated
against independent safety, connectivity, mechanical, and DRC vetoes before
any production-board change is allowed.

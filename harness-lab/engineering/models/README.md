# Simulation models

Use the [LMR51430X datasheet model](lmr51430-datasheet/README.md) for circuit
development with the current part. On September 10 the user explicitly chose
datasheet-based modeling over waiting for a vendor download or changing the
regulator. Vendor authorship is not a prerequisite for using a model.
The [verified development replay](../../audits/buck-final-20260910/datasheet-model-development/README.md)
records actual results and limitations with the current BOM assumptions.

A model must still be independently qualified for the claims it supports before
Stage 3 can pass. Datasheet-derived models are eligible for that review; their
parameter sources, assumptions, supported operating range and comparison
evidence must be explicit. Running a model is useful before that qualification.
The checked-in `simulation/models/LMR51430_avg.lib` is a
negative control only: it uses a 0.8 V reference and has no switching or
credible loss path. No model in this directory is currently qualified.

Retain every model's source, exact bytes, device and orderable variant identity,
simulator compatibility, executed decks and raw outputs. For third-party model
code retain its license as well. Track development checks separately from
independent qualification evidence; the development runner does not mint an
approval receipt or consume scored harness slots.

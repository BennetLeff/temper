# Simulation models

An exact, independently qualified `LMR51430XDDCR` model is required before
Stage 3 can pass. The checked-in `simulation/models/LMR51430_avg.lib` is a
negative control only: it uses a 0.8 V reference and has no switching or
credible loss path. No model in this directory is currently qualified.

Do not add a vendor model without retaining its license/source, exact bytes,
device and orderable variant identity, simulator compatibility, and external
qualification evidence.

# RTD transient model qualification contract

User-authorized implementation, 2026-09-11. Circuit intent is assumed. The
board, schematic, placement, routing, parts and 2 ms detector allocation stay
fixed. This contract qualifies model evidence; it does not authorize hardware
acceptance or replace physical characterization.

## Required mathematical coverage

The complete adopted external resistor network has dynamic states at MAX31865
RTDIN_P and RTDIN_N. Include the reference/force/sense paths, independent
1 Mohm diagnostic resistors, shared 100 kohm comparator input branch and both
threshold dividers. Cover four individually opened conductors and a shorted
RTD (0 through 10 ohm), each from healthy equilibria over RTD 100 through
194.1 ohm and four independently varying lead resistances of 1 through 50 ohm.
Include the declared independent component tolerance/temperature, source,
leakage and capacitance envelopes. A sampled corner maximum is not a
continuous-range proof without an extremum or enclosure argument.

The reference envelope uses the retained REF20 SBOS600F maximum regulation
values and 5 V accuracy test condition. An omitted nonlinear behavior or
additional dynamic node must be identified as a model applicability condition.

A valid timing certificate must expose enough numeric evidence for Rust to
recompute its bound. It must establish final fault overdrive, cover all required
faults and parameter ranges, and reject malformed or unsupported coverage.
Do not retain the earlier hardcoded scalar endpoint pairing or increase the
2 ms allocation to hide a failed proof. A conservative proof unable to meet
that allocation remains unqualified; it is not a measured hardware failure.

## Rust acceptance boundary

The regular unit validation path must require qualification evidence. Missing
qualification is INDETERMINATE. Malformed, stale, incomplete or contradicted
claims cannot pass. Producer labels and hashes alone do not prove a bound.
Bind the evidence to the actual source/board/model identities and test deliberate
mutations through the authoritative validation function.

Report mathematical network qualification separately from device applicability.
The ideal comparator offset/leakage/delay and parasitic allocations require
explicit scope: TI's TLV3201 electrical limits have common-mode/supply/load
conditions; typical capacitance or hysteresis is not a guaranteed maximum.
A successful passive network proof must not erase those limits, the outstanding
supervisor timing condition, or the NOT RUN hardware status.

## Verification and artifacts

Retain the model, complete parameter envelope, mathematical derivation,
independently authored ngspice transient checks, Rust tests and end-to-end
unit report. Preserve the historical acceptance bundle. Write a new bound
input/report; never rewrite old evidence to make prior claims appear qualified.

Implementation workers use isolated worktrees. Root owns canonical integration,
independent numerical/proof review, replay and closeout. No purchase, fabrication,
CAD edit, commit or publication is part of this implementation request.

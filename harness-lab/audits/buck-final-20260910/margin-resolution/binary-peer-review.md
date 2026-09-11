# Binary capture implementation peer review — 2026-09-10

This is a read-only review of the completed binary capture path. It does not
change the startup protocol, model, requirements, or implementation. The
native 21 ms capture is treated as the intended artifact; the findings below
concern parser and host boundaries only.

## Findings

### P1 — bounded file size still permits a large retained-signal allocation

The streaming reader is correct for raw-file I/O. However,
`harness-lab/src/simulation_validation.rs:681-698` allocates one `Vec<f64>`
for every selected signal, with capacity equal to the declared point count.
The parser allows up to 100,000,000 rows (`:627-629`) and up to five selected
signals (`:682-697`), so a syntactically valid file can request roughly 4 GB
of retained f64 samples. This is an explicit decoded-data ceiling rather than
a claim of constant-memory operation; it should remain documented and be
resource-tested against the planned native capture size before widening it.

### P2 — canonicalize-then-open leaves a symlink replacement race

`harness-lab/src/simulation_validation.rs:577-585` canonicalizes the root and
waveform path, then opens the canonical pathname at `:585`. A process able to
modify the raw directory can replace a path component after canonicalization
and before `File::open`, causing the opened bytes to differ from the checked
contained path; the later hash catches content substitution but does not
prevent reads outside the intended root. For an evidence directory shared
with an untrusted writer, open the already-resolved file descriptor without a
followable pathname (or enforce an equivalent no-follow/descriptor-relative
open). This is a host-integrity boundary; ordinary single-process collection
does not exercise it.

## Checks that passed review

The parser checks real format, header dimensions, variable census and units,
exact byte length, finite values, trailing bytes, SHA-256, required signals,
and strictly increasing time (`:612-745`). `measure` binds the scenario format
and rejects dual ASCII/binary inputs (`:752-799`). The Python collector verifies
deck/model artifacts, uses `-r` for binary output, removes the ASCII override,
hashes the completed raw file, and enforces the 8 GiB collector ceiling
(`harness-lab/simulation_host.py:206-289`). The engineering host passes the
resolved simulation root explicitly to the judge and rejects symlink artifacts
from its evidence inventory (`harness-lab/engineering_host.py:32-42,53-73`).

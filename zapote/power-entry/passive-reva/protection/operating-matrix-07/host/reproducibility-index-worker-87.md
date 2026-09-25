# Reproducibility index 87

This index resolves campaign evidence from the actual campaign root and binds
small regular files by SHA-256. It does not reread large waveform archives;
those entries are marked `receipt-reported` or missing when the archive path is
not present. The repository/worktree identity is contextual only: source and
include hashes in the source-bound receipts remain authoritative for these
uncommitted model files.

The accepted baseline, the nine normal points recorded by checkpoint53, the
F2-START receipt, F2-CREST acceptance plus its prefix and phase receipts, and
F2-ZERO recovery plus its prefix and phase receipts are listed in the JSON
index. Their raw archive identities must be taken from those receipts rather
than from a new archive read. SW-SHORT is explicitly `INDETERMINATE`: campaign
verdict86 and tail review85 bind the incomplete endpoint and diagnostic tail;
they do not create a fault acceptance. DIODE-SHORT remains live/prepared, and
BOTH-SHORT and BYPASS-NEG remain prepared and uncompleted.

The DIODE-SHORT, BOTH-SHORT, and BYPASS-NEG packet reviews are listed with
their exact parent-review paths and hashes so their prepared state cannot be
mistaken for a completed case.

The entrypoint list records existing commands and paths without running them.
The F2-ZERO postcapture and legacy commands are source-pinned by their
preflight/source identity and tools pin list. The F2-CREST build, prefix scan,
and phase test commands are retained as documented entrypoints under their
existing directories. No command in this indexing pass was executed.

Manufacturer and model-boundary evidence is linked through the controller
binding/corner documents, the selected-inductor audits 72/73, and the
simulation-to-prototype decisions report. These documents constrain claims;
they do not establish hardware, thermal, SOA, fuse, or production
qualification.

Broken or missing references are reported explicitly in the JSON. No path was
guessed, and no FIFO, solver, recursive raw scan, or unrelated file edit was
performed.

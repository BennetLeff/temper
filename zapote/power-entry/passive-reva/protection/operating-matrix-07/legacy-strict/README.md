# F2-CREST38 legacy strict-check record

This is a diagnostic record only. `run_legacy.py` streamed the immutable
`faults/settled-direct-capture-38/F2-CREST/raw.trace.raw.gz` through the frozen
pigz, fault42 decoder, prefault selector, normalizer, and strict checker. It
used a new `run/` output directory, a 900 s deadline, a 10 GiB free-space
floor, and a separate process group for bounded cleanup. The raw SHA-256 was
verified before and after the run.

The checker rejected the expected repeated timestamp at line 22,760,505:
`REJECTED: line 22760505: time not strictly increasing`. The recorded pipeline
statuses, in order `pigz decoder selector normalizer checker`, are
`141 1 1 1 1`; the upstream errors are broken-pipe consequences of the frozen
checker stopping at the duplicate. This is not an acceptance result and no
deduplication or timestamp adjustment was applied.

Reproduce only into a fresh sibling output directory:

```text
python3 legacy-strict/run_legacy.py
```

See `run/receipt.json`, `run/pipeline.exit`, each stage's stderr, and
`run/command.sh` for the exact recorded command and hashes.

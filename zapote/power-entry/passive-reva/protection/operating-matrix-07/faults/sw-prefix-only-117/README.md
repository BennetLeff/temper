# SW-SHORT prefix-only diagnostic packet

This packet is a parent-review candidate for the complete **normal prefix** of
the saved SW-SHORT partial capture. It does not run a solver and does not
claim a full fault result, phase evidence, protection behavior, or hardware
qualification. The declared full simulation endpoint is 0.662 s, but the
immutable capture stopped at 0.6544026486296868 s; that incomplete endpoint is
preserved as a rejection. No phase43 or observability55 pass is included.

The wrapper verifies the terminal runner/monitor records, successful stage-1
host and pigz export, exact SW source identity, complete fault42 export for
the partial trace, the recorded stop disposition, raw SHA-256 and byte count,
the 10-GiB space floor, tool pins, and a fresh no-clobber output. It then
reuses the frozen selector, normal15 event audit, normal metrics, and legacy
strict checker. Every pipeline exit is retained. The legacy result remains
diagnostic and cannot turn the incomplete full case into an acceptance.

Immutable input identity:

- raw: 5,088,782,620 bytes, SHA-256
  `726acb2f278c1e53fda082da6f4e504b116c9a4b398e4490cfb9ddc4bbac60aa`
- rows: 30,686,230; exported schema: fault42, 42 columns
- source `case.cir`: `3ba13389962a9550edcc7ca5486109f4793c6082e94a50fe18f0bc1f6f889ace`
- source `manifest.json`:
  `840b9fbbf83bc91a8138bfd18101b55306146e21445968ccbbaa3864068679ad`
- manifest timing: fault `.6541666666667`, declared stop `.662`, switch-short

The prefix selector is allowed to consume the partial trace because the
observed stop is after `.65`. It must report one marker edge, a selected last
sample at or before `.65`, and a gap no larger than 1 microsecond. Audit and
metrics use that exact selected endpoint. Their outputs remain diagnostic;
the packet is marked `accepted=false` and `PARENT_REVIEW_REQUIRED`.

Static validation completed:

```text
bash -n faults/sw-prefix-only-117/run.sh       PASS
shellcheck faults/sw-prefix-only-117/run.sh    PASS
run.sh SHA-256: b6c65ef09467ab7cc78af37e4a9fc4c96d9c41eb70fb0d577d72cd80f28de3a4
```

No raw archive, FIFO, solver, or numerical checker was run while preparing
this packet.

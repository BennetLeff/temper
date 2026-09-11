# Full-scenario collection readiness

The binary collection path and corrected startup protocol are implemented.
One [native startup case](native-startup-15v-500ma/protocol-v2/README.md)
has passed the real evaluator. The [thirteen-case schedule](schedule.json)
is still a proposal, not a qualified or completed matrix.

## Verified native result

The unchanged datasheet model was exercised at 15 V and 0.5 A with a 1 us
discharged hold, then a 1 ms VIN ramp. The native capture contains 4,015,356
samples through 21.001 ms, with maximum time spacing 20 ns. The evaluator
accepted the actual ramp, voltage-compliant load, rise, overshoot, final
voltage, settling and capture duration. Its final mean was 3.314811 V and
10–90% rise time was 3.254885 ms.

[Host verification](native-startup-15v-500ma/protocol-v2/host-verification.json)
records 13.31 seconds and 174,440,448 bytes maximum resident memory on this
Mac (about 166.4 MiB). This measurement covers that four-million-row capture,
not the maximum supported file size. The judge itself exited zero; overall
simulation status remains blocked by absent model approval and the incomplete
matrix. [The exact result](native-startup-15v-500ma/protocol-v2/verified-judge-result.json)
retains those findings separately from the passing startup scenario.

The earlier capture without an initial hold was correctly rejected because
ngspice's first saved point was after ramp start. Its earlier settings hash
also exposed different Python/Rust exponent serialization. Both failures are
retained in the parent capture directory; the new fixture fixes timing, and
the host now supplies exact settings-manifest text whose digest and parsed
values are checked independently by Rust. The first timing wrapper could not
read a sandboxed sysctl; the later host-verification record uses Python's
child-process resource accounting and confirms the judge's zero exit status.

## Collection contract

Reviewed scenarios opt in with raw_format = ngspice-binary-le64. The host
uses native binary output, a relative raw_file and its full SHA-256; raw
bytes are not embedded in JSON. The trusted host supplies the collection
root through TEMPER_SIMULATION_RAW_ROOT. Rust rejects absolute paths,
traversal, static symlink escapes, conflicting formats and dual input forms.
The collector owns the evidence directory during judging; this is not an
OS-level sandbox against another process racing filesystem namespace changes.

Rust reads a header bounded to 64 KiB and decodes the same opened stream it
hashes. It validates every column, exact file length, finite values and the
timebase, while retaining only the five evaluator signals. Hard ceilings are
8 GiB of binary data and 100 million rows, with checked allocations. This
is bounded in-memory measurement after streaming decoding, not constant-memory
measurement: five retained columns can occupy about 4 GB at the row ceiling,
plus evaluator working memory. The maximum-size allocation has not been
stress-tested. Normal full-resolution captures no longer require ASCII token
copies or all internal simulator vectors in the evaluator.

Binary scenario runtime is bounded to 3600 seconds; the simulation judge has
a separate 3600-second bound. The old small ASCII control path retains its
32 MiB / one-million-row caps and caller timeout. Artifact inventory hashing
also streams data. No sample decimation, shortened pulse holds, loosened
electrical limits or approval-registry bypass was added.

## Remaining runs

The six load cases require three bidirectional pulses, 100 ms initial/final
plateaus and at least 100 ms between rising edges. A 411 ms capture at maximum
20 ns spacing requires at least 20.55 million samples; actual switching
breakpoints add more. The passing startup case demonstrates the reader at a
realistic startup size, not completion of those longer cases.

Input variation still has generic span/window checks, with no adopted
line-edge sequence. The remaining matrix is unrun while the known model
transient discrepancy and claim-specific model accuracy remain unresolved.
No development or reserved evaluation slots were consumed.

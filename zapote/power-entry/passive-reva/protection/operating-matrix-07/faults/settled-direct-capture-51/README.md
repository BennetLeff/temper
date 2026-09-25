# F2-ZERO settled direct-capture launch packet

Status: **prepared, unlaunched, and blocked**. This directory contains only
launch materials. No solver, native host, decoder, adapter, validator, raw
trace, or acceptance result was started or copied here.

F2-ZERO is the prepared-24 compact-pacer source at
[`../settled-compact-prep-24/prepared/F2-ZERO`](../settled-compact-prep-24/prepared/F2-ZERO).
The launch wrapper materializes its eight-file source closure into a fresh
`full-F2-ZERO` directory only after the gates pass, then invokes the
parent-reviewed runner-45 with direct-fault37, the parent decoder/adapter/
validation-22 tools, and `host/resource-monitor-37.sh`'s five-second samples.
The prepared files are never edited or used as the writable run directory.

The immutable timing contract is `t_fault=0.6583333333333 s`, `TSTOP=0.682 s`,
10 ms prefault/event/observation windows, 2 us turnoff, and a 25 ns capture
maximum gap. Runner-45 maps only the outer adapter/validator bound to 1 us;
the local capture and frozen checker remain at 25 ns. This is native
`f2-zero` with the `f2-open` validator and no bypass flag.

`launch.sh` refuses to proceed unless the campaign filesystem has at least
16 GiB free: 10 GiB is the runner floor and 6 GiB is a prospective archive
reserve. It also uses a numeric-only `ps -axo pid=,comm=` inventory and fails
closed on an unavailable or empty inventory. Known solver/campaign names
include ngspice, the direct fault/normal hosts, the fault host, runner-45, and
the active LL09 runner. Thus this packet cannot overlap LL09 or another full
solver. The preparation measurement was 11.436 GiB free and process inventory
was unavailable in the restricted preparation shell, so the packet is not
launch approved.

The case manifest declares that the compact PWL endpoint differs from the
finite materializer endpoint. A future run must retain its actual final
sample, source listing, fault42 transport, prefault phase/crest neighbors,
all event rows, and parent review. No F2-CREST trace, phase, endpoint, or
checker result may be reused. Runner exit or validator success alone is not
an electrical or protection acceptance.

Parent launch review should verify the source/tool hashes in
[`source-tool-binding.json`](source-tool-binding.json), rerun the gates in
[`parent-launch-gates.json`](parent-launch-gates.json), and only then execute
`./launch.sh`. The script preserves runner and monitor exit receipts even when
a child exits nonzero; a failed or incomplete run remains evidence, not a
protection verdict.

# LL09 direct-export retry launch packet

Status: **prepared, not launched; blocked while LL08 is still processing**.
This packet owns only the launch materials in `line-load-direct-retry-47/`.
It does not copy a source deck, trace, or solver output.

LL09 is the declared 132 VAC RMS / 104.115122239 ohm point from
[`line-load-prep/manifest.json`](../line-load-prep/manifest.json). The command
uses the accepted baseline receipt, the reviewed parent runner
`/private/tmp/matrix07-line-load-native-runner27-parent`, the reviewed direct
normal worker `/private/tmp/matrix07-direct-normal37-parent`, and the existing
normalizer/checker/native decoder/event tools pinned in
[`parent-launch-gates.json`](parent-launch-gates.json). It requests one worker,
650 ms, a 3600 s wall limit, first-invalid snapshots, and
`host/resource-monitor-37.sh` at its existing 5 s sampling interval.

The copied launch script performs two fail-closed checks immediately before
starting the runner: `df -Pk` must report at least 12.2 GiB (2.2 GiB
prospective archive plus the 10 GiB floor), and `ps -axo pid=,comm=` must show
no `ngspice`, `matrix07-direct-normal37-parent`, or
`matrix07-direct-fault37-parent` process. This bounded known-name inventory
catches Rust hosts linked to libngspice while leaving read-only analyzers
unblocked; an unavailable inventory fails closed. It also refuses an existing
`full-LL09` output directory.
The recorded 12.5338 GiB measurement was taken while LL08 was still processing,
so it is evidence for the packet only; it is not launch approval. Existing
archives are already reflected in `df` and are not subtracted twice.

## Pinned inputs

The parent gate records hashes for runner-27, direct-normal-37, the accepted
six include files, baseline acceptance, manifest, ngspice `spinit`, pigz, and
all normal capture tools. The source substitutions and model closure remain
the runner's responsibility; no source file is edited by this packet.

## Launch command

Run `./launch.sh` only after LL08 has terminated and the parent rechecks the
launch gates in the approved host environment. The script writes launch and
resource-monitor receipts under `line-load-direct-retry-47/` and invokes only
LL09. A solver or runner result must receive its own source-bound event audit,
normal screens, and parent review; this packet makes no acceptance claim.

## Preparation verification

```sh
shellcheck launch.sh
sha256sum launch.sh parent-launch-gates.json README.md
```

No solver was started while preparing this packet.

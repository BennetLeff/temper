# LL08 direct-export retry packet

Status: **prepared, not launched**. This packet owns no copied source, trace,
or executable. It binds the accepted baseline and existing runner/tool paths by
hash, and leaves launch to the parent review.

LL08 is 132 VAC RMS, RLOAD 187.407220031 ohm, endpoint 0.65 s. The prior
LL08 attempt (session 50666) was an incomplete resource-guard failure with only
a 10-byte gzip header and no electrical result; that artifact remains retained.

The direct-export review (host/direct-native-export-parent-37/parent-review.json)
passed 11 normal tests and 10 fault tests, compared 99,366 stopped-plot values
bit-for-bit with zero mismatches, and verified normal/fault anonymous-pipe
payload/header identity. It removes an avoidable selected-vector copy but keeps
the solver's full simulation arrays. The first full fault38 capture subsequently succeeded: 5,297,726,667 bytes,
export61.643s, minimum observed free13.8979GiB, no increase in systemwide swap.
This supports a serialized normal retry; no electrical acceptance is implied.

## Launch command

Run only after the parent rechecks free space and approves one solver. The
conservative budget is a 2.2 GiB LL08 archive plus the 10 GiB floor. Existing retained archives are already deducted
from the measured free space; do not subtract them twice. The preflight `df` sample in this
packet reported 15,511,764 KiB (14.793 GiB), while the earlier launch-gate
receipt recorded 18.885 GiB; use the current measurement immediately before
launch. The command must run in the approved environment because the runner's
dynamic `/dev/fd` descriptor is not usable in the restricted filesystem
sandbox.

```sh
set -eu
BASE=/private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07
SOURCE="$BASE/accepted-baseline-11"
BASELINE="$BASE/accepted-baseline-11/acceptance.json"
MANIFEST="$BASE/line-load-prep/manifest.json"
OUT="$BASE/line-load-direct-retry-41/full-LL08"
RUNNER=/private/tmp/matrix07-line-load-native-runner27-parent
TRACKED=/private/tmp/matrix07-direct-normal37-parent
NORMALIZE=/private/tmp/matrix07-normalize
CHECKER=/private/tmp/matrix07-checker
DECODER=/private/tmp/matrix07-native-stream-host
EVENT_METRICS=/private/tmp/matrix07-event-metrics-host
EVENT_AUDIT=/private/tmp/matrix07-normal15-event-audit-host
SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts
PIGZ=/opt/homebrew/Cellar/pigz/2.8_1/bin/pigz
test ! -e "$OUT"
df -Pk "$BASE"
"$RUNNER" \
  --source "$SOURCE" --baseline "$BASELINE" --manifest "$MANIFEST" \
  --output "$OUT" --tracked "$TRACKED" --normalize "$NORMALIZE" \
  --checker "$CHECKER" --decoder "$DECODER" \
  --event-metrics "$EVENT_METRICS" --event-audit "$EVENT_AUDIT" \
  --spice-scripts "$SPICE_SCRIPTS" --pigz "$PIGZ" \
  --workers 1 --wall-limit 3600 --end-s 0.65 \
  --first-invalid-snapshot --cases LL08
```

The unchanged normalizer, checker, native decoder, event metrics, event audit,
SPICE script directory, source closure, and endpoint remain mandatory. A
complete source-bound receipt and parent review are required before LL08 can
be called accepted. Do not widen screens or relabel an incomplete export.

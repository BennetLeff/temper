# Probe provenance addendum

The retained artifacts in this directory describe the final versions of six
short probes. Two probe directories were edited in place during exploration:

| directory | earlier parent observation | retained final case |
|---|---:|---|
| `no-diode-sense` | 1 mV diode-source variant failed after 24,920 rows | direct `Dboost1/2 sw vd`, both zero-V diode sense sources removed, diode saved fields removed; 10 ms completed, 142,410 rows |
| `no-f2-sense` | zero-V diode sources plus F2 1 mV variant failed after 24,758 rows | same direct diode restoration/removal, plus `Vf2sense` 0 V -> 1 mV and diode fields removed; 10 ms completed, 142,492 rows |

The earlier files and logs were overwritten. Their row counts are parent
observations retained for history only; they have no case or log digest and
must not be cited as reproducible tests or one-change controls.

The retained final log digests are recorded in `verification.json`. The final
case digests are recorded in `manifest.json`. The directory `no-marker` is
also a historical name: its final case changes `Vbody` from 0 V to 1 mV and
retains the marker. No marker-removal experiment is present.

These probes are diagnostic only. The passing combined transformations do not
establish whether convergence changed because of source topology, the removed
branch fields, or their interaction. No protection acceptance, thermal claim,
hardware qualification, or adopted repair follows from them.

# Storage checkpoint 23

Measured 2026-09-21T04:15:50.341114+00:00.
This supersedes earlier *capacity forecasts*, not raw evidence or acceptance receipts.

Four completed normal cases retain 7.998 GiB total.
Their compressed native15 archives range from 1.969 to 2.039 GiB per case.
Five grid archives remain to be written, including the currently running LL05.
Using that observed range gives 9.847–10.194 GiB additional normal evidence; this is a forecast, not a hard bound.

Free space at this snapshot: 15.038 GiB. The 10 GiB floor leaves
5.038 GiB usable before pending exports. LL05 has not yet exported its archive.
No second normal case should be launched without accounting for LL05's pending export.

The completed 89 ms startup-fault native42 archive is 877,149,765 bytes
(0.817 GiB); its full capture is retained and reanalysis writes only small reports.
Its startup and dense-event sampling mix is not a reliable size forecast for a 662–682 ms settled fault.
The six remaining settled fault archives have not yet been measured.
The earlier roughly 6.6 GiB-per-settled-fault forecast remains an uncertain planning placeholder,
not a measured native42 compression ratio. One full settled trace must replace that estimate
before committing to all six. There is currently insufficient headroom for that forecast
plus the pending LL05 export while retaining the 10 GiB floor.

The 32 MiB compression probe demonstrated lossless round trips and about 20.5% savings
for xz on that early prefix, but it does not establish whole-campaign savings.
No canonical archive was converted, deleted, or moved. The user has no alternate drive
and may free space; check actual free space rather than assuming any cleanup happened.

# Nine-point normal-operation result

All nine declared normal points have parent acceptance under `event-aware-normal-v1`. The nominal120V/190Ω baseline remains separately accepted. These are discrete authored-model results; they do not establish performance between points or hardware qualification.

| Case | Mains RMS | Load output | Bus min–max | Input RMS | Three-cycle drift |
| --- | ---: | ---: | ---: | ---: | ---: |
| LL01 | 108V | 359.07W | 385.676–387.716V | 3.869A | 0.1499% |
| LL02 | 108V | 705.40W | 381.308–385.189V | 7.510A | 0.2726% |
| LL03 | 108V | 1242.52W | 375.858–382.392V | 13.412A | 0.4156% |
| LL04 | 120V | 398.20W | 385.202–387.442V | 3.844A | 0.1653% |
| LL05 | 120V | 783.85W | 381.212–385.347V | 7.420A | 0.2749% |
| LL06 | 120V | 1383.94W | 376.244–382.998V | 13.199A | 0.3873% |
| LL07 | 132V | 398.38W | 385.328–387.507V | 3.505A | 0.1563% |
| LL08 | 132V | 785.86W | 381.772–385.749V | 6.699A | 0.2508% |
| LL09 | 132V | 1392.35W | 377.461–384.029V | 11.890A | 0.3551% |

The tightest current, low-bus and drift margins occur at LL03:1.587946A to the15A screen,5.723620V to the low-bus screen, and0.000844183 in fractional drift to the0.005 limit. These are margins to the campaign screens, not component or thermal ratings.

LL09 completed30,141,001rows to650ms; its archive is2,168,688,596bytes, SHA-256 `84812ef89e0c987d28343078c9fd17a5468a019a71505595023f74d4e064e2ba`. The original strict checker rejected repeated time at line22822239. The complete event-aware audits retained all rows and found52equal-time groups,73repeated intervals, no backwards time, logic change or cycle-boundary ambiguity, and negligible representative-choice sensitivity relative to the original screen margins.

The companion JSON binds every acceptance receipt and includes all recorded metrics, margins, raw identities and source hashes. Each per-case receipt remains the acceptance authority.

Five settled fault cases remain. The next prepared F2-ZERO launch requires16GiB free; about10.45GiB was free after LL09. No new solver was launched. The selected clamp’s low-current VF versus temperature/lot is still unbounded by manufacturer evidence. This normal-operation milestone does not complete the broader goal.

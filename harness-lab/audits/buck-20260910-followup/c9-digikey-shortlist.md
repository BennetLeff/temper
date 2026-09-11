# C9 replacement shortlist — 2026-09-10

The user prefers a standard part readily available from DigiKey. This is a
procurement and engineering shortlist, not a BOM change or qualification receipt.
Current C9 remains GRM32ER71E106KA12L in the feature worktree.

**Preferred candidate after comparison: Samsung CL32B106KBJZW6E.** It has
the strongest observed DigiKey inventory, current manufacturer identity and
lifecycle evidence, and an accessible exact-part bias curve. It remains a
proposed replacement until the combined operating-condition and assembly
checks are resolved; no qualification pass is implied.

## Candidates with live DigiKey stock

| Part | Nominal specification | Live DigiKey stock / unit price (USD) | Evidence and limits |
|---|---|---|---|
| Samsung CL32B106KBJZW6E | 10 µF ±10%, 50 V, X7R, 1210; soft termination | 175,622 / $1.05 | Manufacturer Mass Production; exact bias, AC-amplitude, temperature and ripple-heating graphs available. Preferred candidate. |
| TDK CNC6P1X7R1H106K250AE | 10 µF ±10%, 50 V, X7R, 1210; low-resistance soft termination | 16,656 / $1.31 | Manufacturer status Production; exact DC-bias, temperature and ripple-heating graphs are available. Strong candidate, with assembly details to resolve below. |
| KEMET C1210C106K5RACTU | 10 µF ±10%, 50 V, X7R, 1210; conventional commercial MLCC | 44,132 / $1.88 | Standard procurement alternative; exact bias curve has not yet been reviewed. |
| Würth 885012209073 | 10 µF ±10%, 50 V, X7R, 1210; general-purpose MLCC | 34,395 / $0.76 | Exact manufacturer datasheet retrieved; exact bias curve has not yet been reviewed. |

Stock and prices were read from the live DigiKey browser UI on September 10,
including the substitute table on the TDK C3225X7R1H106K250AC page. They are
snapshots, not reservations. The ordinary C3225X7R1H106K250AC itself showed
zero stock, superseding older cached search results with positive inventory.

Sources:

- [Samsung DigiKey page](https://www.digikey.com/en/products/detail/samsung-electro-mechanics/CL32B106KBJZW6E/7320694)
- [Samsung exact product and graphs](https://product.samsungsem.com/mlcc/CL32B106KBJZW6.do)
- [TDK CNC DigiKey page](https://www.digikey.com/en/products/detail/tdk/CNC6P1X7R1H106K250AE/10240642)
- [TDK exact product and characteristic graphs](https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=CNC6P1X7R1H106K250AE)
- [DigiKey live comparison](https://www.digikey.com/en/products/detail/tdk-corporation/C3225X7R1H106K250AC/10413509)
- [KEMET DigiKey page](https://www.digikey.com/en/products/detail/kemet/C1210C106K5RACTU/4918885)
- [KEMET manufacturer series datasheet](https://yageogroup.com/content/datasheet/asset/file/KEM_C1002_X7R_SMD)
- [Würth exact datasheet](https://www.we-online.com/components/products/datasheet/885012209073.pdf)

## Electrical and assembly screening

Samsung explicitly lists packaged MPN CL32B106KBJZW6E under base
CL32B106KBJZW6. Its dimensions are 3.2 ±0.3 × 2.5 ±0.2 × 2.5 ±0.2 mm.
The exact rendered DC-bias curve suggests approximately 7–8 µF at 16.5 V
(visual estimate, LCR meter 1 kHz / 1 Vrms). The separate AC-amplitude curve
shows further change below 1 Vrms; neither curve alone is a combined
low-amplitude, biased, temperature/tolerance/aging minimum. The displayed
bias-temperature curve uses 25 V DC. Keep the effective-capacitance gate
open until its actual conditions are supported. Its E packaging suffix is
normal embossed 7-inch reel packaging, not the Z/R low-acoustic packaging
option described in Samsung's generic note.

The Samsung body matches C9's nominal 1210 size. Its land-pattern and
soft-termination assembly requirements still require an explicit review;
package-code equality alone is not a footprint qualification.

50 V exceeds twice the 16.5 V input-envelope maximum, following the voltage
selection guidance in TI LMR51430 section 9.2.2.6. Voltage rating alone does
not establish effective capacitance.

The rendered TDK CNC exact-part DC-bias graph shows roughly 6–7 µF near
16.5 V. This is a visual estimate of typical data, not a numeric export or
qualified minimum. Do not apply an invented tolerance/temperature/aging
factor and promote the result to guaranteed evidence. TDK also presents a
temperature curve at 25 V bias; that is not a combined 16.5 V corner result.
The published LTspice ZIP link returned HTTP 403 through curl; the browser
graph itself rendered successfully. A CSV click did not yield a retained
local artifact in this session.

C9's existing KiCad 1210 pads are 1.15 × 2.7 mm, centered at ±1.475 mm,
giving a 1.8 mm inner gap. TDK lists recommended PA 2.0–2.4 mm, PB 1.0–1.2
mm, PC 1.9–2.5 mm. Package size matches, but this is not an exact match to
the recommended land dimensions. Assembly review must establish acceptance
of the generic IPC footprint or propose a revised candidate footprint.

The linked CNC series specification also requires mounting the underside
toward the board. Its March 2026 cover contains radar-only applicability
wording despite the product page describing commercial general equipment.
This inconsistency must be resolved before treating that specification as
the qualification authority for Temper. It does not mean the part is
electrically unsuitable; it prevents an unconditional replacement claim.

No source MPN, active circuit contract, production PCB, frozen fixture, or
approved-evidence registry was changed by this shortlist.

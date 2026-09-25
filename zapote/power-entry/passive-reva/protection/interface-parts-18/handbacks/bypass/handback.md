# Revision 18 downstream-bypass capacitor screen

## Result

PCBParts searches and exact-part lookups completed. These are procurement
candidates, not accepted electrical selections: none of the PCBParts result
records includes a guaranteed capacitance-vs-DC-bias curve, ripple/lifetime
guarantee, or aging bound. The manufacturer pages explicitly label the MLCC
graphs as typical/reference data. The parent must obtain the manufacturer
curve/model at the actual bias and temperature before assigning an effective
minimum.

| Use | Candidate | LCSC | Package | PCBParts record | Conditional zero-bias screen |
|---|---|---:|---:|---|---|
| TPS54202 VIN bypass, 10 uF | TDK C3225X7R2A106KT000E | C49296968 | 1210 | 100 V, X7R, +/-10%, stock 1,939 | 9.0--11.0 uF before DC-bias/temperature/aging; 100 V rating is preferable at 16.76 V rail |
| Alternative VIN bypass | Taiyo Yuden UMK325AB7106KMHP | C386166 | 1210 | 50 V, X7R, +/-10%, stock 186,038 | 9.0--11.0 uF before DC-bias/temperature/aging; bias margin is less attractive than 100 V candidate |
| UCC27511A bulk, 1 uF | Samsung CL31B105KBHNNNE (PCBParts model CL31B105KBHNNNE) | C1848 | 1206 | 50 V, X7R, +/-10%, stock 658,419 | 0.90--1.10 uF before DC-bias/temperature/aging |
| UCC27511A bulk alternative | Samsung CL21B105KBFNNNE | C28323 | 0805 | 50 V, X7R, +/-10%, stock 2,717,807 | 0.90--1.10 uF before DC-bias/temperature/aging; smaller package likely has more bias loss |
| UCC27511A HF, 100 nF | Samsung CL31B104KBCNNNC | C24497 | 1206 | 50 V, X7R, +/-10%, stock 1,952,583 | 90--110 nF before DC-bias/temperature/aging |
| UCC27511A HF alternative | Samsung CL21B104KCFNNNE | C28233 | 0805 | 100 V, X7R, +/-10%, stock 1,831,579 | 90--110 nF before DC-bias/temperature/aging |

The existing PFC VCC part was re-found and should be preserved: KEMET
C0805C105K5RACTU, LCSC C3018567, 0805, 1 uF, 50 V, X7R, +/-10%.

## Ceramic census and LT4363 ratio

Using only catalog tolerance as a conditional arithmetic screen, the known
four bypasses have 12.1 uF nominal and 13.31 uF initial maximum:

```
10.0*1.10 + 1.0*1.10 + 1.0*1.10 + 0.1*1.10 = 13.31 uF
```

The LT4363 requirement is Cbulk,min >= max(22 uF, 10*Cceramic,max). Thus the
ratio term is 133.1 uF under this zero-bias conditional maximum. It is not a
guaranteed effective maximum: DC bias will usually reduce MLCC capacitance,
while temperature, tolerance, aging and measurement conditions must be
combined from the selected manufacturer data. Do not use 133.1 uF as a final
acceptance number until each selected part's curves/models are evaluated.

If the optional 0.1 uF TPS54202 HF bypass is added, its catalog-tolerance
maximum adds 0.11 uF and the same conditional census becomes 13.42 uF; the
ratio term becomes 134.2 uF. It is not included in the current integrated
candidate because the README says the optional bypass is not fitted merely
because TI mentions it.

## Manufacturer evidence and limitations

* Samsung CL31B105KBHNNN (1206, 1 uF, 50 V, X7R, -55 to +125 C) official page:
  https://product.samsungsem.com/mlcc/CL31B105KBHNNN.do . It exposes DC-bias,
  temperature and bias-TCC graphs, but states the data are typical/reference;
  the page does not provide a guaranteed effective-minimum table.
* Samsung CL31B106KBHNNN (nearby 1206, 10 uF, 50 V X7R family) official page:
  https://product.samsungsem.com/mlcc/CL31B106KBHNNN.do . It confirms the
  family temperature range, tolerance and rating and again labels the graphs
  typical. It is not used as the preferred VIN candidate because 50 V gives
  less bias margin than the TDK 100 V option.
* Samsung's MLCC catalog warns that Class-II MLCC selection must include DC
  voltage, temperature and aging characteristics; it does not turn a typical
  curve into a guarantee:
  https://product.samsungsem.com/resources/file/product-catalog/MLCC_Automotive_2512.pdf
* Existing KEMET C0805C105K5RACTU official specification: 1 uF, +/-10%, 50 V,
  X7R, -55 to +125 C, 15% TCC reference condition and 3% aging loss/decade
  hour; the public spec does not supply a guaranteed DC-bias effective value:
  https://search.kemet.com/component-documentation/download/specsheet/C0805C105K5RACTU

The provisional -40..105 C screen is inside the cited -55..125 C ratings, but
it is an analysis envelope only; no product environmental requirement has been
inferred. Ripple current, self-heating, ESR, pulse duty, mechanical fit and
assembly clearance remain unqualified.

## Recommendation to parent

Carry TDK C3225X7R2A106KT000E (1210, 100 V) as the preferred VIN-bypass
candidate, Samsung CL31B105KBHNNNE (1206) for driver 1 uF, and Samsung
CL31B104KBCNNNC (1206) for driver 100 nF, subject to curve/model review.
Keep the KEMET PFC part unchanged. Treat all numerical effective limits above
as conditional zero-bias/tolerance bounds, not accepted part guarantees.

The TPS54202 datasheet/application text saying input capacitance should be
greater than 10 uF is an application recommendation, not a guaranteed
effective-capacitance minimum for every operating corner. Selecting a nominal
22 uF buck capacitor without a system-level decision would be coupled to the
LT4363 10x-ceramic ratio and the 300 uF total-output ceiling: its tolerance
maximum would add to the ceramic census and its physical/effective maximum
would consume bulk budget. Keep 10 uF as the current candidate and report any
22 uF option as a separate trade study, not an automatic upgrade.

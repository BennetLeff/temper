# Exact-part selection packet

Status: waiting for the user's PCBParts/Zenode connection. Package flexibility
question remains unanswered; current footprints are placeholders. No distributor
stock, availability, price or assembly-fit claim has been made.

| Item | Existing target/identity | Required evidence before selection |
| --- | --- | --- |
|Clamp C4 |220uF/50V low-ESR target | Effective minimum≥max(22uF,10×qualified ceramic maximum); effective maximum compatible with300uF total; ESR versus temperature/frequency, ripple duty, lifetime and dimensions/pitch |
|Clamp C3 |1.5uF/63V target | Effective minimum≥1.35uF and maximum≤1.65uF across applied gate-node voltage, temperature and aging; dielectric/bias data; pulse duty and package |
|Clamp C2 |100nF timer target | Effective90–110nF over its actual voltage/temperature/life; leakage small enough for timing-current allocation |
|Buck VIN |10uF generic | Effective minimum for TPS54202 application; effective maximum for LT4363 ratio; voltage rating and bias curves; current TI application text recommends greater than10uF with optional0.1uF bypass |
|PFC VCC |C0805C105K5RACTU,1uF | Verify existing exact part's effective min/max and ratings; do not silently substitute |
|Driver bypass |1uF local bulk in1210 +100nF HF | Resolve exact parts, effective min/max and pulse/temperature performance |

The known direct bypass sum12.1uF is nominal. Do not assume it is an upper
bound. If a new0.1uF buck bypass is fitted, add it to both the ceramic census
and total-output maximum; it is not fitted merely because TI recommends it.

Record manufacturer MPN, datasheet revision/page/table, package drawing,
applicable operating envelope and min/max conditions separately from stock.
If vendor tools provide only typical curves, retain that limitation. A parts
search result is not a full-temperature/lifetime electrical guarantee.

There are two independent startup budgets: physical output capacitance charges
directly, while the buck's output capacitance and all5V consumers appear as
input power/current through the buck. Do not add5V capacitance directly in
parallel with15V capacitance or omit its startup current.

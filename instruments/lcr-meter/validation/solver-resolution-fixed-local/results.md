# Fixed local 100 pF transient results

All cases below use the full coupled source/TIDA/FDA network, official unmodified TI models, actual FDA DC input loading, and static ADC RC loading. This is finite-window modeled behavior, not measured hardware accuracy or a universal stability proof.

|Case|TIA DC step / peak (µV)|Rising overshoot (%)|Rise / fall 1% settling (ns)|ADC pin min / max (V)|
|---|---:|---:|---:|---:|
|matched100|-49.998764 / 59.624865|0.000218|45.572884 / 45.643843|2.025157 / 2.025589|
|matched5k|-2499.992159 / 2520.891480|0.000087|2300.503477 / 2299.896017|2.023919 / 2.026800|
|matched100k|-50000.056552 / 49899.309915|0.000000|45980.624542 / 45952.244976|1.999962 / 2.050219|
|open100p|-99.998716 / 107.676412|0.260932|26.968498 / 27.315959|2.025124 / 2.025632|
|coil100p|-0.497494 / 97.237253|NA|2285.297936 / 2285.188274|2.025034 / 2.025710|
|open100p_low|-99.998716 / 107.547130|0.732536|23.711959 / 24.000268|2.024999 / 2.025508|
|open100p_high|-99.998716 / 107.801906|0.068068|30.511157 / 30.483678|2.025248 / 2.025755|
|uncompensated5k|-2499.992159 / 4864.001291|94.560662|292.907279 / 292.515075|2.023891 / 2.026837|

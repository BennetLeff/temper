# Final FDA full-chain verification

All rows require finite saved values, true FDA MID DC, AC-coupled source DC, output-current KCL and complete requested AC/transient analyses. Final FDA is 22 Ω inside feedback, 1 kΩ || 100 pF feedback and 4.32 Ω ADC isolation. Nominal input source: 50 kHz.

|Case|KCL max pA|AC rows|Transient rows|ADC min/max V|
|---|---:|---:|---:|---|
|revc_100r_cap100n|1.059457|561|12113|1.179315/2.890687|
|revc_100r_cap500n|1.059457|561|12113|1.164679/2.905648|
|revc_100r_cap9u|1.059457|561|12115|1.186978/2.867818|
|revc_100r_coil50u-selected|1.018424|561|12082|1.197621/2.850175|
|revc_5k_resistor-selected|1.402667|561|12814|1.604485/2.446259|
|revc_100k_resistor-selected|1.563132|561|12112|1.606038/2.446042|

## 10 mV common-mode step, 10 ns edge

|Case|A common-mode overshoot %|B common-mode overshoot %|A/B differential glitch µV|
|---|---:|---:|---|
|cm100r|45.6932|45.6923|0.290876/0.149805|
|cm5k_cf10|45.6922|45.6922|0.395332/0.251879|
|cm100k|45.6926|45.6924|0.420303/0.175722|

These are macromodel checks with passive static ADC loading; the independent switched-ADC stress analysis covers sampling charge. They do not establish physical-board accuracy, noise floor or stability outside the tested fixture envelope.

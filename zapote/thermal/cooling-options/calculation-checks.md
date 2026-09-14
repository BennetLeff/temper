# Independent calculation receipt

Checked 2026-09-14 with Python 3.11 using only the values in
[`envelope.json`](envelope.json) and the proposal records.  No solver output or
board acceptance result is used here.

```text
P_bridge(15 A RMS, VF=1.0 V) = 2*1.0*(2*sqrt(2)/pi)*15 = 27.01 W
air capacity(100 CFM) = 1.2*0.0471947*1005 = 56.92 W/K
air rise(105 W, 100 CFM) = 105/56.92 = 1.84 K
Rsa required for 15 K headroom at 105 W = (110-40-1.84-60)/105 = 0.078 °C/W
```

With `Ta=40 °C`, `P=40 W`, `Rjc=1.25 °C/W` and `Rcs=0.25 °C/W`:

```text
395-1AB: 40 + 40*(0.50 + 0.25 + 1.25) = 120.0 °C (5.0 K margin)
396-1AB: 40 + 40*(1.07 + 0.25 + 1.25) = 142.8 °C (-17.8 K margin)
392-120AB bridge-only: 40 + 40*(0.16 + 0.25 + 1.25) = 106.4 °C (18.6 K margin)
392-120AB distributed 105 W screen: sink=40+105*0.16=56.8 °C;
  bridge case=56.8+40*0.25=66.8 °C; bridge junction=66.8+40*1.25=116.8 °C;
  adding 1.84 K inlet heating gives 118.64 °C.  This assumes the catalog
  resistance applies to the total distributed load and is not a system proof.
```

The shared-load calculation keeps the total sink heat and bridge junction rise
separate.  A 105 W total load cannot be represented by applying a bridge-only
resistance to the bridge case; local spreading and airflow still need CFD or
measurement.

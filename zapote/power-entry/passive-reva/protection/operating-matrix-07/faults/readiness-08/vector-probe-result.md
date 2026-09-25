# Branch-vector probe receipt

Command:

```sh
ngspice -b -o /tmp/temper07-vector-probe.log vector-probe.cir
```

Simulator: ngspice 45.2 (KLU build). Exit status: `0`. The 20 ns smoke deck
completed 260 rows.

The first version attempted `i(Ssf2)`, `i(Dboost1)`, and `i(Dboost2)` and
ngspice reported that those vectors were unavailable. The revised deck puts
ideal 0-V sources in series with each branch. The active-vector listing then
contained:

```text
vbody#branch
vchannel#branch
vdboost1sense#branch
vdboost2sense#branch
vf2sense#branch
```

The `i(V...)` branch-current vectors are therefore the portable contract for
this ngspice build. This receipt covers only vector availability; it says
nothing about the power-stage circuit or any fault behavior.

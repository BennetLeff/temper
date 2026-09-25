# DIODE-SHORT source-grounded strategy follow-up

This is a topology and measurement review. It does not select a device,
change the model, approve hardware, or treat the completed DIODE-SHORT run as
accepted.

The declared fault was injected at 0.6541666667 s, while the adapter observed
the detector rise about 3.121 ms later, outside the 2 ms event window. The
validator therefore failed its detector-event contract. A late detector edge
can be recorded, but this run does not identify which comparator or network
condition caused it, and it does not establish a causal protection strategy.

The deck's healthy power topology is explicit. The bridge/source feeds
`Lboost`, then the switch node `sw`. `Clocal` (19.8 uF) is on `vd`. `Cbank`
(2240 uF) is on `vb`, with the normally closed modeled F2 path `vd` to `vb`
(`Vf2ctl=5 V`). DIODE-SHORT adds a 1 mOhm modeled switch from `sw` to
`d1_path`; the zero-volt `Vdboost1sense` source ties `d1_path` to `vd`.
Msw remains gate-controlled. Thus a healthy MOS may turn off while a diode
terminal short and residual VD/VB/local-storage paths remain; this is
different from SW-SHORT/BOTH-SHORT, whose failed MOS branch is gate-independent
and source-fed around F2.

`protection.inc` does not sense diode current directly. It builds VD and VB
divider comparisons (`ch_vd`, `ch_vb`) and forward/reverse divider comparisons,
ORs them into `fault_raw`, then applies RC qualification and health/clear
logic. Those comparisons can detect a voltage mismatch or overvoltage, but the
late edge cannot be attributed to one comparator from this receipt. A future
defensible strategy needs each comparator input and transition timestamp,
alongside VD/VB voltage and the injected edge, within the declared event
window.

`Risense` sits between `bridge_minus` and `isense`, feeding the UCC28180
current-loop input. It is therefore source/bridge-side instrumentation in this
netlist. It does not necessarily see bank discharge: a local `VB -> F2 -> VD`
loop through diode/short and capacitances may circulate without traversing the
bridge-minus shunt. Any return through the mains path depends on instantaneous
switch states and impedances. The source alone does not justify treating
ISENSE as Cbank or Clocal discharge current.

Future work should separately measure source/bridge current, the switch/VD
path, F2/bank current, and VD/VB capacitor voltages, while retaining the
detector comparator channels and exact event timing. Stored energy and residual
discharge paths must be bounded before any interrupter strategy is qualified.
Requirements for the failed-MOS SW-SHORT/BOTH-SHORT source-fed branch and
restart behavior remain separate from this healthy-MOS diode-terminal case.
No causal mechanism for the 3.121 ms detector delay is claimed here.

Source bindings: case SHA-256
`d5a78e2c878447110a13c54cc3052b3dff7e862dc3e79a5fbd8e973257ac5f78`,
`protection.inc` SHA-256
`61385002bc7c55313814b7ea606c1198129da20a1f76cd44fe197de0468a70e8`, and
manifest SHA-256
`fd5c7f9e9703a5d0004bcd523798644068d0b378081361580bcda5c29b67baa9`.

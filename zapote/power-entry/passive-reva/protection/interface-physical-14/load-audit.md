# Supply load audit

The historical 75 mA AUX and 75 mA logic5 allocations remain requirements,
not a complete bound derived from all installed consumers. `load_audit.rs`
records the arithmetic below independently of the AUX worker calculator.

The worst rail corners in the proposed resistor experiment require evaluating
the buck at its actual protected input, 14.25 V, and its allowed 5.25 V output.
The resulting conditional load is 114.473684 mA. The earlier 111.630037 mA
number used 14.625 V and nominal 5 V. Both assume at least 70% efficiency and
both exclude a new receiver and isolation circuitry. The all-path resistance
ceiling becomes 3.275862 Ω before any switch, wire or connector allocation.

## What the existing 75 mA must cover

The compiled revision-11 source connects the relay coil through 91 Ω to AUX,
and uses a 1 kΩ AUX pullup at the driver's disable input. At 15.75 V, assuming
1% total resistor error and zero switch drop, the latter consumes up to
15.909091 mA while enabled. The relay corner at 23°C consumes 38.035210 mA
using its 360 Ω minus 10% coil resistance. Together these leave only
21.055699 mA of the 75 mA allocation for everything else. These are partial
upper screens; this does not prove that actual total load exceeds 75 mA.

[TE RT1 Inrush Rev 4, coil table](https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocFormat=pdf&DocLang=English&DocNm=RT1_Inrush&DocType=Data+Sheet&PartCntxt=2-1393240-3)
sets 360 Ω ±10% for coil code 012 at 23°C without pre-energization. It does not
make this a full-temperature current bound. Colder coil resistance, relay
pickup and steady thermal conditions still need their own budget.

[ST STW65N65DM2AG, Table 5](https://www.st.com/resource/en/datasheet/stw65n65dm2ag.pdf)
lists **120 nC typical**, with no maximum, at VGS 0–10 V, VDD 520 V and ID 60 A.
It is not a maximum at the present 15 V gate drive. At the source model's
nominal 129.107 kHz, 120 nC would draw 15.492840 mA on average. This example
is deliberately labelled typical/conditional; it must not become a guaranteed
load bound. Remaining-current sensitivity for hypothetical other loads of
5, 10 and 15 mA is recorded in the CSV.

[TI UCC28180 §7.5](https://www.ti.com/lit/ds/symlink/ucc28180.pdf)
specifies an 8.8 mA maximum operating-current datum with 4.7 nF GATE load.
It is not a bare quiescent term to add to another full model of that same
controller output load. The actual controller-to-driver input network,
frequency tolerance and driver bias must be budgeted at their own conditions.
[TI UCC27511A §6.3.2](https://www.ti.com/lit/ds/symlink/ucc27511a.pdf)
separates driver bias, gate-charge current and input-pullup current. None can
be silently omitted. Its disable propagation tests also do not bound the
complete external MOSFET turnoff path.

The 220 Ω logic bleeder alone screens at 24.104683 mA at 5.25 V and −1%
resistance. Remaining logic demand includes the existing ICs, output loads,
new transport/reset functions and startup charging. The source has not yet
proved a 75 mA maximum for that collection.

## Transient window

`transient_window.rs` uses the exact no-load RC relation for an ideal stiff
fault source, with R=3.275862 Ω, initial rail=15.75 V and target=18 V:

`t18 = R C ln((Vfault − 15.75)/(Vfault − 18))`

For 10 µF effective downstream capacitance, the result is 9.609670 µs at
24.6 V and 4.071822 µs at 35 V. This is a conditional sensitivity calculation,
not measured IRM behavior, an actual capacitor selection, or a permissible
shutdown time. Less resistance/capacitance, higher initial voltage or
parasitic feedthrough can make the available interval shorter. All detection
and turnoff charge must be counted from fault onset. A finite capacitor and
resistor do not protect indefinitely against a persistent overvoltage.

The practical decision is to require a complete load envelope and an active
protection design before adopting parts. There is no demonstrated spare
75 mA budget into which a new HOT processor can simply be placed.

Independent arithmetic oracle: ngspice 45.2 ran `rc-oracle.cir` with 1 ns
maximum output step and explicit 15.75 V initial capacitor voltage. Its
threshold measurements are 4.07182 µs and 9.60967 µs, agreeing with the Rust
closed form at the recorded precision. This confirms the ideal RC arithmetic,
not applicability of an ideal source to the actual supply.

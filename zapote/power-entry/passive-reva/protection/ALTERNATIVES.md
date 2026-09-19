# F2 alternatives with published DC data

The Mersen A70QS50-14F remains the retained candidate, but
its retained catalogue does not publish a DC capacitor-discharge clearing
I²t. A source search found one concrete comparison candidate:

| Candidate | Published data | Why it is not accepted yet |
| --- | --- | --- |
| **SIBA 5020526.16.0**, 14 x 51 mm gPV | 16 A, 1000 Vdc, 30 A²s pre-arcing I²t, 200 A²s total I²t at 1000 Vdc, 30 kA dc breaking capacity | The captured public product record does not state the discharge L/R, minimum breaking current, or whether its total-I²t test waveform applies to this 179 J bank. Normal 9 A RMS, startup/inrush derating and holder compatibility also remain open. |

This is useful because it demonstrates that DC total-I²t data exists for a
14 x 51 fuse class; it is not a license to transfer the 200 A²s number into
the board model. The data came from the public product record for
[SIBA 5020526.16.0](https://www.technoteam.eu/en/fuses-for-photovoltaic-applications/17022-fuse-14x51-1000vdc-gpv-con-terminals-16a.html)
and needs confirmation from SIBA's exact datasheet before selection.

The SIBA candidate also changes the design problem: its 16 A rating leaves
less margin than the 50 A A70QS at the approximately 9 A RMS boost-diode
current at the retained 120 V operating point, and
it needs a SIBA-compatible 14 x 51 / 1000 Vdc holder. It should therefore be
screened against the normal-current and maximum-temperature contract before
it is considered a replacement for A70QS.

## Decision

Keep A70QS50-14F + Mersen US141 as the primary construction candidate and add
SIBA 5020526.16.0 as an unconfirmed distributor sourcing lead. Do not promote either to
`CoordinationDemonstrated` without exact-part DC application data tied to the
fault waveform and a withstand calculation. The SIBA record narrows the
sourcing search; it does not close the physical protection gate by itself.

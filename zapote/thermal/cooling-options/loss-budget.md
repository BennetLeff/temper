# Bridge loss and thermal-resistance budget

This is a screening calculation for the three assembly proposals.  It keeps
the maintained 40 W bridge allowance until a waveform-bound model and the
package/lead heat split are available.  It must not be read as a measured loss
or as an acceptance rating.

## Exact diode evidence

The exact bridge is Yangjie `GBU2510A`, not a GBJ or another supplier suffix.
The manufacturer family sheet (`GBU25005A THRU GBU2510A`, S-B407, Rev 2.5,
09-Apr-2024) gives a maximum per-diode forward voltage of 1.0 V at 12.5 A,
25 A average rectified current with a heatsink at `Tc=100 °C`, 3.5 A without a
heatsink at `Ta=25 °C`, `RθJC=1.0 °C/W` on a 75 × 45 × 5.5 mm aluminum plate,
`RθJA=25 °C/W` without a heatsink, `Tj=-55…150 °C`, and 350 A one-cycle surge.
The sheet's Figure 3 contains typical `Tj=25 °C` and `Tj=125 °C` forward
curves, but does not provide a guaranteed curve envelope.  The exact source
record, retained PDF hash and origin retrieval limitation are in
[`sources/yangjie-gbu2510a-web-cache.md`](sources/yangjie-gbu2510a-web-cache.md).

## Current-waveform screen

For an ideal sinusoidal 15 A RMS bridge input, two diodes conduct and the
mean absolute current is `2√2/π · I_RMS = 13.50 A`.  Applying the published
1.0 V maximum point gives:

```text
P = 2 · 1.0 V · (2√2/π) · 15 A = 27.01 W
```

The 21.2 A waveform peak is above the 12.5 A test point.  Temperature changes
the forward curve, the PFC waveform may not be sinusoidal, and tolerances are
not specified as a full curve.  Therefore 27.01 W is a reproducible point
screen, not an upper bound.  The 40 W allowance remains the design input until
the physical-model owner binds an actual waveform and heat partition.

## Series budget

The following series values use the retained v1 **legacy screening assumption**
`RθJC=1.25 °C/W` and `RθCS=0.25 °C/W`, with `Ta=40 °C` and `P=40 W`.  The
exact Yangjie sheet gives `RθJC=1.0 °C/W` for the device mounted on its
specified aluminum plate, but does not provide a whole-bridge aggregate or
the lead/solder/barrel heat partition.  The 1.25 value is therefore a
conservative comparison input, not a datasheet-derived whole-bridge rating.
The compact rejection and the 0.078 °C/W target below are conditional on this
legacy screen and remain provisional until the physical model binds the
per-element heat paths:

| Proposal | `RθSA` input | Sink °C | Case °C | Junction °C | Margin to 125 °C |
|---|---:|---:|---:|---:|---:|
| Baseline 395-1AB at 500 LFM | 0.50 | 60.0 | 70.0 | 120.0 | 5.0 K |
| Compact 396-1AB at 500 LFM | 1.07 | 82.8 | 92.8 | 142.8 | −17.8 K |
| Shared 392-120AB, bridge-only at 100 CFM | 0.16 | 46.4 | 56.4 | 106.4 | 18.6 K |

The Wakefield catalog values are typical values at the stated airflow and are
not guarantees for our mounting.  The shared value is for a bridge-only load;
it cannot be applied to all cooker heat by simple addition.

## Shared-load and airflow bound

The shared concept carries a provisional `65 W` allowance for the PFC switch,
boost diode, inductor and shunt in addition to the 40 W bridge allowance.  At
100 CFM, air heat capacity is approximately
`1.2 kg/m³ · 0.0472 m³/s · 1005 J/(kg·K) = 56.92 W/K`, so 105 W would raise
the stream by about 1.84 K if all air crossed the sink once.  Applying the
catalog `0.16 °C/W` to the 105 W distributed sink load gives sink 56.8 °C;
the bridge then screens at 116.8 °C junction (118.64 °C with the 1.84 K inlet
rise).  This is a conditional distributed-load screen, not a prediction: a
system CFD model or measurement must prove local spreading, airflow and heat
partition while all concurrent loads are present.
To hit the proposed 15 K junction headroom target with this 105 W total load
and a 1.84 K inlet rise, the effective bridge-zone `RθSA` would need to be at
most about `0.078 °C/W` (`(110−40−1.84−60)/105`).

The first shared-fan proposal used two Sunon `MF80251V1-1000U-G99` units.  Each
is rated 41 CFM in free air, so the pair has at most 82 CFM before any duct or
fin pressure loss and cannot establish the Wakefield 100 CFM catalog point.
The revised candidate uses one Sanyo Denki `9RA1212E1001`, whose retained
manufacturer catalog gives 120 CFM maximum airflow and 100 Pa maximum static
pressure.  The page-183 12 V curve supports a plausible 100 CFM point only at
low system pressure (initial design budget approximately 30 Pa); this is a
screening requirement for the duct, not a measured installed flow.

## Contact and PCB path

The `RθCS` value includes bridge case-to-spreader grease, spreader-to-pad
interface, flatness and mounting pressure.  The 0.229 mm SIL PAD TSP 1800
typical area-normalized impedance is about 0.119 °C/W over an ideal
75 × 45 mm contact, but real bolt holes and spreading increase it.  No design
may credit the pad value without specifying clamp force, fastener insulation,
surface flatness and a supported heat path that does not load the soldered
bridge leads.  The local PCB model's 107.86 °C peak and 2.14 K margin remain
separate from the case/junction calculation.

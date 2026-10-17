# Recovery evidence and what it can constrain

Sources accessed 2026-10-05. The selected artifact is the Round-17 best FEM
matrix and current D2 circuit at c09244caa7588bb72d786a8b1b884390003a5caf,
with IPW65R018CFD7 L1 library version 1007 (2022-10-27). This study changes no
native board. The 443 ns parameter is the requested effective D2 command gap;
it is not a claim that a resistor or driver produces exactly that gap.

| Quantity | Evidence | Usable constraint and limit |
| --- | --- | --- |
| Selected-part Qrr | Infineon **IPW65R018CFD7, Rev. 2.0, 2021-04-19**, Table 7, printed p. 6: typical 2.30 µC, maximum 4.60 µC | Applies at 400 V, 58.2 A, 100 A/µs and 25°C. No minimum. Typical is not a lower bound. |
| Selected-part trr / Irrm | Same Table 7: trr typical 236 ns, maximum 354 ns; Irrm typical 15 A, no maximum | Same conditions. These three scalar quantities do not prescribe a tail waveform. |
| Definition | Same datasheet Table 8, printed p. 11; section defaults p. 5 | trr ends at descending 10% Irrm. D24 uses `tb10/ta`, with ta zero-to-peak and tb10 peak-to-10%. No numerical softness range is specified. |
| Family Qrr/trr/Irrm comparison | Infineon **AN_2009_PL52_2010_130022**, V1.3, 2023-04-27, pp. 7–8, Figs. 5–6 | Comparison concerns IPW65R041CFD7 versus IPW65R041CFD at 100 A/µs; Fig. 6 names 16.4 A. It does not establish statistical limits or a high-slew/hot softness range for the selected 18 mΩ part. |
| Family hard-commutation mechanism | Same application note p. 6 §2.1.1 and p. 11 Fig. 9 | Discusses induced overshoot and re-turn-on, and nonlinear output charge. Mechanism evidence, not a selected-part S4 pass/fail bound. |
| Published double-pulse circuit | Infineon **AN_2103_PL52_2104_114225**, V1.0, 2021-03-31, pp. 7–11, Figs. 6–10 | CFD7 half-bridge with an added pre-charge circuit. Fig. 8 is a timing illustration; Fig. 10 is explicitly simulated. Neither is an unmodified IPW65R018CFD7 high-slew recovery tolerance. |
| Published recovery measurements | Siemieniec et al., **600 V power device technologies for highly efficient power supplies**, EPE 2021, DOI 10.23919/EPE21ECCEEurope50061.2021.9570498, §3.8, Figs. 18–19; author-uploaded full text | Shows recovery-current comparison and explains dependence on temperature, current density and diode conduction time. Different technology/part comparison, not a production softness distribution for IPW65R018CFD7 at D24 corners. No transferable quantitative softness bound claimed. |
| L1 model parameter | Pinned library lines 67–68, 88–93, 113–120, 133–159, 308–325 | fpar20=50 ns supplies standard diode TT. There is no separate softness control. Model values are a nominal simulation implementation, not an evidence-backed production range. |
| S4 acceptance screen | D24 brief; existing `d2/grid.py` hot screen | die VDS ≤520 V and off-gate VGS <1.9 V. The latter is the project hot screen at both tested temperatures, not a guaranteed device turn-on threshold. |

Primary links:

- [Selected-part datasheet](https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipw65r018cfd7-datasheet-en.pdf). The existing committed copy is `validation-results/03-loss-thermal-budget/round3/sources/ipw65r018cfd7.pdf` under the power-stage root.
- [650 V CFD7 family application note](https://www.infineon.com/assets/row/public/documents/24/42/infineon-mosfet-coolmos-cfd7-650v-applicationnotes-en.pdf).
- [CFD7 pre-charge double-pulse application note](https://www.infineon.com/dgdl/Infineon-Evaluationboard_EVAL_3K3W_TP_PFC_CC-ApplicationNotes-v02_01-EN.pdf?fileId=5546d46278d64ffd01793608aec42696).
- [EPE 2021 author full text, §3.8 / Figs. 18–19](https://www.researchgate.net/publication/357974551_600_V_power_device_technologies_for_highly_efficient_power_supplies).
- [Publisher DOI](https://doi.org/10.23919/EPE21ECCEEurope50061.2021.9570498).
- [Pinned Infineon simulation-library archive](https://www.infineon.com/assets/row/public/documents/24/50/infineon-power-coolmos-cfd7-mosfet-650v-spice-simulationmodels-en.zip).

Searches included `CFD7 recovery softness`, `CFD7 softness factor`,
`CFD7 reverse recovery IEEE`, and `CFD7 double pulse recovery`; the result is a
bounded literature search, not a proof that no unpublished or unindexed data
exist. The author full text is primary research; its waveform is not digitized
or converted into an invented 18 mΩ production bound. PDF downloads of the two
application notes returned empty bodies in the shell; the official documents
were inspected through the web PDF reader instead. Empty cache files are not
evidence and are not committed.

## Parameter map (line numbers in the pinned original library)

| Parameter / model block | Lines | Role | Treatment |
| --- | --- | --- | --- |
| `cool_tech_w3.fpar20`, diode `TT` | 90, 157 | Transit-time storage parameter; affects reverse-current magnitude, duration and shape together | Only swept parameter. Record before/after values and each derived model hash. |
| `fpar18`, `dRdi`, `G_Rdio`, diode series resistance | 88, 113, 157–159 | Forward/conductive resistance and series response of the body path | Fixed. Changing it would also change forward characteristic, not independently vary softness. |
| `fpar19`, `fpar21` → `IS`, `N` | 89–91, 157 | Diode exponential characteristic; affects storage via forward junction state | Fixed. No part-specific tolerance supplied. |
| `fpar22`, junction temperature input | 92, 158, 323 | Series-path temperature exponent and global TEMP feed | Fixed exponent; `.temp` runs at requested junction values without self-heating. |
| `fpar23`, `Cdio`, diode `m` | 93, 114, 157 | Body-junction depletion capacitance | Fixed, not used as a softness knob. |
| `fpar33…37`, `Cds0`, `Cds1`, nonlinear charge functions | 103–107, 119–120, 133–144 | Nonlinear output-capacitance charge contributes to terminal current and abrupt voltage rise | Fixed. Zero TT removes transit-time storage, **not** output charge or terminal recovery current. |
| Cgd/gate path/package | 94–102, 115–118, 130–139, 308–325 | Miller coupling and terminal/die parasitics determine gate rebound | Fixed; scope is recovery sensitivity with original D2 driver approximation. |
| Independent softness parameter | absent in technology subcircuit, lines 67–167 | Cannot independently set tail fall slope or `tb10/ta` while retaining charge and capacitance | No fictitious knob added. The reported softness is a measured output of each run. |

No licensed equations or model bodies are included here. All modified libraries
are local, ignored derivatives of the verified original. Parameter-space
restriction to TT is deliberate: accepting arbitrary capacitance, diode-law,
or external-current-source edits as silicon recovery corners would exceed the
available evidence. Consequently this study cannot establish a physically
exhaustive plausible range at 27/150°C and the much faster board commutation.

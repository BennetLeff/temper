# RTD passive-network energy bound

This derivation supplies the inequalities independently implemented by the model
and the Rust validator. The bound is conditional on the adopted two-state
external network; see ../applicability-review.json for device behavior outside it.

Let C dx/dt + Gx=b be the full resistor network reduced to the two ADC pins.
For a fixed post-fault circuit, z=x-x_inf, E=z'Gz. For positive C,
E'=-2 z'G C^-1 Gz <= -2 lambda E. Any C <= Cmax and G >= Gmin give
lambda >= lambda_min(Gmin,Cmax). A zero ground capacitance case follows by
the passive algebraic limit, including initial fast relaxation. For output
margin m=m_inf+c'z, |c'z| <= sqrt(c'G^-1c * E0) exp(-lambda*t).
Thus with E0<=Emax, dual<=Dmax, and m_inf<=-(0.020+remaining),
t <= max(0,ln(sqrt(Emax*Dmax)/remaining))/lambda. Add the conditional
55ns comparator and10ns logic allocations; do not equate allocations to
qualified physical-device limits.

Gmin can be the Schur complement of the post-fault network with every passive
resistance at its largest allowed value, including RTD at194.1 for opens or10
for shorts. Ground the ideal voltage sources and zero independent current
sources for G. Dirichlet minimum-energy property proves this Loewner bound.
For a universal Gmax, use the diagonal full-node incident conductance maxima
at the two ADC pins: no larger than diag(1/leadSPmin+1/RdiagPmin+1/Rwinmin,
1/leadSNmin+1/RdiagNmin+1/RLBmin). Schur elimination subtracts a PSD matrix,
so this diagonal is a valid upper bound, despite ignoring actual coupling.
For SENSE+ and SENSE- the post-fault G is diagonal; exploit exact independent
branch structure to tighten the upper bound below.

All resistors: use multiplicative tolerance and TCR endpoints or outward
rounded encompassing intervals. Suggested broad R13[98000,102000],
Rdiag each[944000,1057000]. CDmax1.10nF, CGP/CGMmax200pF independently
is a superset of <=200pF total parasitic. Capacitor minima do not enter this
energy bound (Cmax in Loewner order covers smaller capacitors).

Leak sum L=14nA+14nA+20nA+5nA+5nA=58nA bounds all external independent
sinks/sources (offset is an observation threshold, not a node current).
For a node with a resistive path of resistance Rpath to any ideal voltage
source, maximum principle and transfer-resistance reciprocity give voltage
in [min(sourceV)-L*Rpath, max(sourceV)+L*Rpath]. Ground counts as source0V.
Healthy: Rp=leadSPmax+RTDmax+leadFNmax+Rreturn=294.101ohm;
Rn=leadSNmax+leadFNmax+Rreturn=100.001ohm. Thus healthy pin voltage lies
inside[-L*Ri, VBmax+L*Ri]. This also bounds removed-edge currents.

SENSE+:
PostG diagonal. Gmin diagonal can use[1/RdiagPmax,1/Rn] (other grounded
conductance only increases it). Gmax diagonal[1/RdiagPmin,
1/leadSNmin+1/RdiagNmin+1/(RLTmin+RLBmin)].
Postp=VB-RdiagP*(ImaxP+Iwindow), hence p in
[VBmin-RdiagPmax*34nA,VBmax+RdiagPmax*34nA]. deltaP is max distance to
healthy p interval. Removed SENSE+ current has bound
Isp=(VBmax+L*Rp)/RdiagPmin+34nA. Its effect at retained senseM is bounded
by transfer resistance Rn: deltaM<=Isp*Rn. This follows subtracting the
pre/post nodal equations, injecting the removed branch current at its
retained terminal; the other terminal is resistively disconnected.
Emax=GmaxPP*deltaP^2+GmaxMM*deltaM^2.
c=(-1,0), Dmax=1/GminPP.
Final fault remaining=windowPmin-highThresholdMax-offsetMax-0.020;
windowPmin=VBmin-RdiagPmax*34nA-RwinMax*20nA;
highThresholdMax=VREFmax*RHBmax/(RHTmin+RHBmax)
 +5nA*(RHTmax||RHBmax).

SENSE-:
PostG diagonal. Gmin diag[1/Rp,
1/RdiagNmax+1/(RLTmax+RLBmax)]. Gmax diag[
1/leadSPmin+1/RdiagPmin,
1/RdiagNmin+1/(RLTmin+RLBmin)].
Post senseM is weighted average of VB andVREF plus current correction;
its enclosure is [VREFmin-19nA/GminMM,VBmax+19nA/GminMM]. deltaM is max
distance to healthy senseM interval. Removed SENSE- current has bound
Isn=(VBmax+L*Rn)/RdiagNmin
 +max(VREFmax+L*Rn,VBmax+L*Rn-VREFmin)/(RLTmin+RLBmin)+19nA.
deltaP<=Isn*Rp. Emax as above. c=(1,-alpha),
alphaMax=RLTmax/(RLTmax+RLBmin); Dmax=1/GminPP+alphaMax^2/GminMM.
Final main sensorP voltage upper from unloaded force-divider:
VBmax*(RTDmax+leadFNmax+Rreturn)/(RREFmin+leadFPmin+RTDmax+leadFNmax+Rreturn)
plus [VBmax/RdiagPmin+L]*Rp. This deliberately overbounds diagnostic
injection using VBmax and total leak budget. Then add RwinMax*20nA for
windowPmax. Final lowThresholdMin>=VREFmin-19nA/GminMM
 -5nA*(RLTmax||RLBmax). Final remaining=lowThresholdMin-windowPmax
 -offsetMax-0.020.

Other cases: use Gmin full post-fault network as above; universal diagonal
Gmax is loose but time constants are tiny. For deltaP/M bound initial and
final states by maximum-principle voltage ranges. Post FORCE+ andshort
retain ground paths Rp/Rn (use RTDmax194.1 globally conservatively).
Post FORCE- has paths to VB: pinP leadSP+leadFP+RREF and pinM
leadSN+RTD+leadFP+RREF. Use max paths and L to obtain global delta.
Take Emax=sum Gmaxii*delta_i^2. LOW output dual can bound
c'Gmin^-1c <= [1,alphaMax]' abs(Gmin^-1) [1,alphaMax]. HIGH uses
Gmin^-1_PP. Exact c endpoints can tighten but absolute bound is safe.

FORCE+ final remaining:
LowThresholdMin=VREFmin*RLBmin/(RLTmax+RLBmin)
 -alphaMax*L*Rn -5nA*(RLTmax||RLBmax).
With FORCE+ removed only diagnosticpulls and LOW-divider source feed the
main resistor network. Injection upper J=2*VBmax/RdiagMin
 +VREFmax/(RLTmin+RLBmin)+L.
windowPmax=J*Rp+RwinMax*20nA.
remaining=LowThresholdMin-windowPmax-offsetMax-0.020.

FORCE- final remaining:
VB is the remaining bias reference, with the LOW divider loading towardVREF.
Global no-leak nodes are inside[VREFmin,VBmax]. Total pull-down current
J=(VBmax-VREFmin)/(RLTmin+RLBmin)+L (diagnostic toVB is not a sink belowVB).
windowPmin=VBmin-J*(RREFmax+leadFPmax+leadSPmax)-RwinMax*20nA.
remaining=windowPmin-highThresholdMax-offsetMax-0.020.

SHORT final LOW remaining needs differential bound, not global windowP:
IforceMax=VBmax/(RREFmin+leadFPmin+leadFNmin+Rreturn).
Extra injection J=2*VBmax/RdiagMin+VREFmax/(RLTmin+RLBmin)+L.
SensorP-SensorN <=(IforceMax+J)*SHORTmax.
SenseP-SensorP <=(VBmax/RdiagMin+34nA)*leadSPmax.
SensorN-SenseM <=[VBmax/RdiagMin+VREFmax/(RLTmin+RLBmin)+19nA]*leadSNmax.
Thus WminusMmax=sum three bounds+RwinMax*20nA.
SenseMmax=VBmax*(leadFNmax+Rreturn)/(RREFmin+leadFPmin+leadFNmax+Rreturn)
 +J*Rn (RTD0 maximizes this divider voltage).
LowThresholdMinusMmin=betaMin*(VREFmin-SenseMmax)
 -5nA*(RLTmax||RLBmax), betaMin=RLBmin/(RLTmax+RLBmin).
remaining=LowThresholdMinusMmin-WminusMmax-offsetMax-0.020.

Review bounds numerically against independent model states/randoms/ngspice.
Do not confuse successful sample tests with proof; all continuous coverage
comes from these inequalities and the fixed circuit graph. A producer cannot
choose smaller J, delta, Gbox or biggerremaining in Rust unchallenged.

## Fixed-envelope and numerical implementation boundary

Version 2 supports this reviewed source topology and these exact parameter
intervals. A changed source manifest or envelope requires renewed review. The
fixed source-manifest hash is a topology version boundary, not proof that any
arbitrary hash describes the same graph. Native/source correspondence is also
checked by the ordinary unit validator.

Fast-case state displacements use 2.1 V. Before and after FORCE+ and SHORT,
each state has a ground path no larger than 294.101 ohm. After FORCE-, a
path to BIAS is no larger than 774.4450645 ohm. Maximum-principle bounds
therefore put both endpoints between -58 nA * 774.4450645 ohm and
2.06 V + 58 nA * 774.4450645 ohm: their separation is below 2.1 V.
This bound includes the healthy initial RTD range even when the final short
resistance is smaller.

For Cground=0, the algebraic fast relaxation minimizes G-energy subject to
the capacitor charge constraint, so the positive-capacitance limit does not
add energy. The certificate bounds settling past the required fault margin
even if the observed margin is not monotone. SHORT=0 uses the limiting
merged-node circuit; 10 ohm sets the lower conductance envelope. A tiny
resistor simulation alone is not evidence of an exact zero-ohm case.

Rust uses a stable two-by-two generalized eigenvalue formula and checks the
independently supplied matrix and scalar values at tight relative tolerance.
This is an engineering analytical certificate evaluated in floating point,
not a machine-checked interval-arithmetic proof. The independent solver and
mutation tests address implementation errors; their sample count does not
establish continuous coverage.

The proof starts from a healthy equilibrium at fixed component/source values
and applies one permanent open or RTD short. It does not cover simultaneous
faults, time-varying BIAS, cable inductance, comparator hysteresis or internal
MAX31865 protected force-path dynamics. Those omissions cannot be relabeled
qualified by changing a producer status field.

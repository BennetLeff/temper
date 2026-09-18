# Manufacturer application-review handoff

Prepared 2026-09-18. **Draft, not sent.** Refer to the
[current decision and qualification plan](../CLOSEOUT.md) for design status.

Recipient role: Mersen applications engineering. No recipient or response is
invented here. The project owner can send this with the linked packet after
confirming the application's voltage, temperature and startup envelope with the
responsible engineer.

Subject: A70QS50-14F capacitor-discharge application review — 400 V nominal PFC bus

We are evaluating A70QS50-14F in series between a boost diode cathode and a DC
capacitor bank. The proposed fuse would interrupt bank discharge if the boost
diode and boost switch both fail short. We also need to cover a diode short while
the switch is still healthy and conducting. The existing line fuse and current
shunt are outside this internal discharge loop.

The bank is nominally 2240.47 µF at 400 V, approximately 179.24 J. These are nominal
values, not upper limits; capacitance tolerance, maximum bus voltage and operating
temperature must be included in final coordination. We have a conditional R–L
sensitivity study, not established fault impedances or measured waveforms. The
proposed fuse is not yet installed or qualified.

Could you confirm, for this exact fuse:

1. The meaning of the capacitor-discharge rating's 2.5 ms time constant and its
   applicability to oscillatory discharge.
2. The applicable capacitor-discharge current limit, including peak and waveform
   conditions, rather than the general DC breaking rating.
3. Minimum breaking current and treatment of a high-impedance fault.
4. Capacitor-discharge total clearing/let-through data suitable for comparison
   with the bank, conductors and devices. We have not applied the 700 VAC I²t
   figure to this case.

Please also identify the required holder, temperature/duty derating and startup
pulse information for an application approval. If this part is unsuitable, a
supported part/arrangement and the data needed to qualify it would be useful.

Attachments to review:

- [Detailed application packet](../loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-MERSEN/manufacturer-packet/A70QS50-14F-application-review.md).
- [Representative R–L cases](../loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-MERSEN/manufacturer-packet/representative-cases.json), explicitly illustrative constant-R calculations, not measured discharge data.
- [Fault cases and proposed fuse location](../CLOSEOUT.md#3-proposed-f2-topology-and-fault-cases).

Record the reply verbatim with its date, exact part/revision and applicability
conditions. Update Q1/Q2 in the closeout from that evidence. A general product
recommendation does not establish board coordination, and lack of a reply must
not become a pass.

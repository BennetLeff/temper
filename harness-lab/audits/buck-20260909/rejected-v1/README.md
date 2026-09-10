# Rejected development artifacts

These drafts and reports are diagnostic history, not current model evidence.
The initial voltage-mode draft did not implement a credible power path or
peak-current/PFM controller. The Luna latch checkpoint required subsequent
host fixes to switching events, low-side commutation, reset, and soft start.

`../scenarios/*-attempt/` records early missing-model and failed attempts;
`../scenarios/*-new/` contains intermediate runs and does not correspond to
the current model. `../measured-v2/` freezes a later rejected revision whose
10 Meg integrator leakage caused a load-dependent DC error (4.759 V in the
5 V example). Its receipt and model snapshot explain why it was superseded.
Only the explicitly identified revision in `../model-simulation.md` supplies
the reported current measurements. Raw waveform files remain local and ignored.

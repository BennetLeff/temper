# Startup KLU candidate 17

This is an unexecuted numerical-solver candidate for the existing F2-START
startup deck. It is copied from `faults/startup-candidate-13` (the prepared
0.010 s healthy, 0.075 s fault, 0.089 s endpoint case) and adds exactly one
line to `case.cir`: `.options klu`. The five included model files and
`cold.cir` are byte-identical to that source closure; tolerances, electrical
values, `.save` lists, and the 25 ns pacing source are unchanged.

The parent source candidate halted in the SPARSE solver at about 4.41687 ms.
This directory only prepares the KLU variant so the parent can compare solver
behavior after the separate native 10 ms probe. No simulation was launched,
and no protection or normal-operation acceptance is implied.

Review gates before execution:

* verify the accepted source/event selection and the native capture contract;
* run the independent 10 ms startup probe first;
* compare KLU stop reason, endpoint, callback progress, and finite/monotone
  trace evidence against the source candidate; and
* keep any result diagnostic until the normal/fault acceptance checks pass.

The source manifest records the copied closure hashes and the one-line deck
mutation. There are no old run outputs in this directory.

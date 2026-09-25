# Completion requirements audit 85

The campaign goal remains active and incomplete. Checkpoint81 records nine
accepted source-bound normal points, an incomplete SW-SHORT attempt, an active
DIODE-SHORT launch, and prepared BOTH-SHORT and BYPASS-NEG packets. The
normal-operation table is a discrete authored-model result; it does not close
the fault campaign or establish hardware behavior.

The next required work is to finish the existing prepared cases under their
reviewed handles and packets. DIODE-SHORT must complete its own capture and
postcapture prefix, phase, fault/current split, legacy witness, and parent
checks. BOTH-SHORT then needs the same independent treatment. BYPASS-NEG must
run as a negative control and retain a validator rejection; a clean simulator
exit cannot turn it into a pass. Each complete trace must satisfy the
fault-matrix gate: accepted cold-start prefix, strict finite complete endpoint,
declared event window, phase/neighbor evidence, current-channel split, and
retained-off/no-rearm observation.

SW-SHORT is a different status. Its saved run stopped at 0.6544026486296868 s
before the required 0.662 s endpoint, with adapter and validator endpoint
rejections and unknown numerical cause. The fault matrix explicitly permits a
bounded timestep-abort attempt to remain `INDETERMINATE` when its evidence is
retained. It does not require retrying until a pass. A retry would need a
parent-reviewed discriminating cause or source change. The active goal still
needs an explicit SW-SHORT disposition in the final report, and the partial
archive cannot receive a protective pass.

After those case dispositions, the final reproducible report must bind the
source/deck and tool hashes, commands, raw/report hashes, screen margins, and
all failure or indeterminate reasons. Its strategy implications must preserve
the graph ownership rules: failed-short and combined-short paths receive no
gate-interruption credit; a healthy switch can interrupt only its own path; and
the bypass negative control must fail closed.

The report must keep the known model bounds visible: the selected diode's
low-current VF envelope is not guaranteed by the retained manufacturer data;
the controller is an authored surrogate; the MOS/diode/F2 and inductor models
do not establish device SOA, saturation, thermal, fuse-clearing, or physical
interruption behavior. Those limitations need explicit disposition or bounds,
not conversion of modeled screens into ratings.

Unrequested hardware redesign, ECO work, and qualification claims are outside
this goal. Prototype instrumentation and physical correlation remain future
implications and cannot replace the pending source-bound simulation cases.

The audit is read-only with respect to campaign evidence; no archive scan,
solver run, FIFO read, or case edit was performed.

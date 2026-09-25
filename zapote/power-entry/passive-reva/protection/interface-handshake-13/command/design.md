# Interface handshake 13 — logical candidate

This is a tested, standalone logical protocol for the future SELV coordinator to
request HOT-domain start. It is not a schematic, transport decoder, isolator
model, MCU implementation, timing proof, or safety acceptance. The Rust model
in `handshake.rs` operates on already-decoded logical frames.

## Protocol

The HOT receiver requires a persistent, monotonic session counter. Fault,
PERMIT loss and health loss invalidate its session and leave it offline. An
external recovery caller invokes `boot()` to allocate a new
`(session_number, nonce_tag)` and begin qualification. No automatic recovery
caller is implemented. The nonce tag is a deterministic unique
session label, not cryptographic randomness or authentication. Allocation fails
closed at counter exhaustion; the counter must survive receiver power cycles. A
reset that reuses an old session number is outside this protocol and must be
treated as an integration failure.

The receiver emits `Challenge(session)`, then qualifies at least two healthy
idle samples while PERMIT is high. The source must accept a newer challenge than
its persisted last session, then require a new local start intent event before
emitting `Request(session,intent)`. A held ARM level, an old request, or an
automatic retry after source reset is not a fresh intent. The receiver replies
with `Ack(session,intent)`; only the source that receives that matching ACK may
emit `Start(session,intent)`. The receiver enters RUN only for that exact
outstanding request. Duplicate requests are ACKed for loss recovery; duplicate
or stale START frames are rejected.

PERMIT is independent and maintained. A low PERMIT resets the receiver before
frame interpretation and clears RUN. Frame validity never overrides it.

## State table

| Receiver state | Accepted event | Next state | Output |
| --- | --- | --- | --- |
| qualifying | healthy idle sample until the bound | idle | challenge remains current |
| idle | matching fresh Request | await-start | matching Ack |
| await-start | matching Start | running | RUN |
| await-start | duplicate matching Request | await-start | repeat Ack |
| any active state | PERMIT low, health loss, link fault | offline; explicit boot required for recovery | RUN cleared, old frames stale |
| any state | stale/mismatched/reordered frame | unchanged or fail-closed | no new RUN transition |

A dropped ACK is recoverable by retransmitting the same Request in the same
session, but retries do not extend the fixed handshake deadline (eight model
ticks). A dropped Challenge can be replayed in the same session. A source
reset, receiver reset, decoder/link fault, health loss, or PERMIT loss requires
a new challenge and a new local intent after fault observation and recovery.
Frames from an invalidated session or with the wrong intent cannot initiate RUN.
An otherwise valid START delayed within the current deadline remains acceptable;
this includes the source-reset observation window described below.

## Physical boundary and remaining integration

The model intentionally does not equate valid frames with GPIO waveforms. A
transport/framing decoder, MCU firmware, command-side reset defaults, physical
isolation, and HOT-side receiver must be designed and tested separately. The
existing ISO7740FDWR shortlist is four forward channels only. ISO7741F is the
3-forward/1-reverse family member, but either part still needs an actual
bidirectional transport (or source/receiver implementation) to map challenge
and ACK frames. The existing revision-11 one-bit ARM input cannot implement
this by itself. A HOT processor or equivalent state machine is an additional
function; no such processor is assumed installed.

The receiver must reset on PERMIT, health loss, and decoder/link fault without
waiting for valid transport traffic; `observe_inputs` and `link_fault` are the
model's explicit event hooks. The caller supplies `tick()` to enforce the fixed
deadline; a real implementation needs a watchdog clock and must specify
challenge lifetime, idle qualification, retransmission, and cable/isolator
settling. Source `timeout()`/reset cannot retract an already transmitted START
before the receiver observes a reset or link fault; that detection latency is
an explicit physical assumption. A physical producer that remains asserted
through reconnection is outside the fresh-intent contract; no one-bit observer
can infer whether a low was an open wire or an intentional command.

Persistence is a prerequisite, not implemented storage: receiver counter and
source last-session fields live in memory in this model. Source `reset()` keeps
its last-session field; constructing `Source::new()` does not restore it after
a real power cycle. Both endpoints need qualified nonvolatile recovery or an
equivalent uniqueness mechanism before physical adoption. Source `timeout()` is
an explicit event supplied by the caller, not an implemented source clock.

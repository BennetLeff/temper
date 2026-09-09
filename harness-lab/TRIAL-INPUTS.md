# Model-run payload and authorization

On September 9 the user approved **Muse Spark 1.3 Contributor Free through
OpenCode Zen**, including Meta's permission to use prompts/completions for
training. That approval covers this U3/C9 experiment. The Zen runner sends the
same geometry/task/tool surface described below; its exact requests and
responses are preserved in the [experiment evidence](EXPERIMENT-00-RESULTS.md).
It sends complete conversation history (`store: false`) for protocol
compatibility; this setting does not revoke the Contributor training terms.

## Earlier Codex proposal (still deferred)

Destination: **OpenAI**, through the installed Codex CLI using the existing
ChatGPT login. One inspection-only preflight, then three fresh scored trials;
each is limited to five minutes, with at most ten placement edits per trial.

The agent receives the short task instructions, the three tool definitions,
and the geometry, pad/net names, constraints, and resulting measurements for
**U3 and C9 only**. The tool data includes IDs/content hashes and timing.
The ordinary Codex runtime also provides its session metadata.

[Exact prompts, tool definitions, constraints, and all three initial geometry
packets](evidence/trial-inputs.json). Subsequent tool responses have the same
geometry fields plus the actual DRC findings and changed-state receipts.

The model chooses its own coordinates. The known-valid qualification witness
is not included in its instructions. Its working directory is fresh and empty;
the candidate is owned by the MCP host. The configured runtime disables shell,
web, apps, plugins, image tools, memory, other agents, and repository instructions.
The external preflight must verify the resulting tool access before scoring.

**Codex/OpenAI route: still deferred.**
Automatic approval review first rejected the preflight because it required
explicit approval for the payload and OpenAI destination. The user chose local
work only at that point, and no Codex model request ran. The later authorization
above selects Zen/Meta; it does not authorize the earlier Codex runner.

## Routing increment 00R

The user explicitly approved the expanded routing payload with **“send it”**
after being asked to authorize one preflight and three five-minute Muse
routing trials under the Contributor training terms. The earlier automatic
approval rejection preceded this authorization; it did not send any data.

The destination and Contributor terms match the placement trials.
Each run receives the fixed U3/C9 geometry, net names,
0.25 mm/F.Cu constraints, native connectivity, tracks, DRC findings and state
receipts. No routing witness is supplied to the model.

The exact four tools and task instructions are in `routing_host.py`; the
frozen input identity is in `fixtures/routing-contract.json`. An
inspection-only preflight precedes three fresh five-minute repetitions, each
with at most ten routing edits. Actual provider payloads are preserved in the routing trace archive.
The initial board hash is pinned separately from the
protected-state hash, so a pre-routed fixture cannot be substituted unnoticed.

## Synthetic obstacle increment 00R-O

The user explicitly approved the obstacle payload with **“do it”** after being
asked to authorize one preflight and three Muse/Zen routing trials under the
same Contributor terms. This resolved the earlier automatic approval block,
which had rejected the command before execution and sent no obstacle data.
The new context is a synthetic F.Cu track keepout polygon between the same
U3/C9 pads. [Prepared inputs](evidence/obstacle-trial-inputs.json) contain the
instructions, unchanged four tool schemas, fixed contract and native initial
geometry. The approved destination and Contributor terms remain Muse Spark
through OpenCode Zen, for one inspection preflight and three five-minute,
ten-edit trials. The valid qualification detour is not included in the inputs.

## Stream diagnostic on the same obstacle fixture

On September 9 the user said **“go for it”** to the proposed longer-wait,
no-immediate-retry diagnostic. [The declared batch](STREAM-DIAGNOSTIC.md)
uses the same obstacle inputs, model and Contributor terms for one new
inspection preflight and three sequential five-minute, ten-edit trials.
The transport policy and recording change; the board task and validators do
not. Fresh qualification and preflight receipts bind the revised source.

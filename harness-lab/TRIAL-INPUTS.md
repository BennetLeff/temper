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

## Seeded repair experiment 00R-R

The user approved the proposed three-case repair experiment with **“ok continue”**
on September 9, following the completed stream diagnostic. The same Muse Spark
1.3 Contributor Free / OpenCode Zen destination and accepted Contributor terms
apply to one inspection preflight and three sequential five-minute, ten-edit
trials. The new inputs are existing copper with one seeded keepout intrusion,
clearance violation, or physical gap, plus native inspection/validation feedback.

[Prepared inputs for review](evidence/repair-trial-inputs.json) contain the common
prompt, tool catalog, frozen contract and all three initial observations.
[The plan](REPAIR-EXPERIMENT.md) states exact acceptance and limits. The model
receives only the unchanged prompt and normal tool outputs for its own start;
case diagnoses, scripted reference repairs and other trials are not supplied.

## Combined placement and routing 00PR

The user approved continuing to combined U3/C9 placement and routing with
**“that all looks great, continue”** on September 9. Use the same Muse Spark
1.3 Contributor Free model through OpenCode Zen under the accepted Contributor
terms, for one inspection preflight and three sequential five-minute trials.
The new tool catalog adds C9 placement to inspect/route/remove/check; all
edits share one ten-edit budget. Native placement leaves existing copper fixed.

[Prepared inputs](evidence/combined-trial-inputs.json) and [the predeclared
plan](COMBINED-EXPERIMENT.md) record the exact tools, constraints and three
initial board observations. Only the trial's current state is shown to the
model. Scripted witness poses and routes from qualification are withheld.


## Full-buck continual harness

The September 9 refinement plan preserves the approved Muse Spark 1.3
Contributor Free / OpenCode Zen destination. The construction catalog contains
inspect, check, place, replace_copper, and execute. A separate refiner receives
only its own bounded native trajectory, current notes/skills, observation, and
instructions; its sole tool returns replacement artifact contents. Neither
solver nor refiner receives witnesses, repository access, other-trial runtime
state, or provider-switching tools.

Live development and evaluation remain subject to current engineering and
qualification admission. Local scripted controls do not constitute live trials
or qualify hardware. See [the continual harness](CONTINUAL-HARNESS.md) for
budgets, frozen inheritance, output receipts, and optional metadata-only tracing.

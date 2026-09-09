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

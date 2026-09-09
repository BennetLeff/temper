# Proposed model-run payload

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

**State: deferred by the user on September 9; keep the experiment local.**
Automatic approval review first rejected the preflight because it required
explicit approval for the payload and OpenAI destination. The user chose local
work only. No model request from this experiment ran. These are proposed inputs,
not authorization to execute the external runner.

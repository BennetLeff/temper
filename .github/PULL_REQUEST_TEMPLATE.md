## Summary

<!-- What does this change and why? -->

## How did you test this change?

<!--
If you leave this empty, your PR will be closed. Include the exact commands
you ran and their output.
-->

## Checklist

- [ ] `cmake -B firmware/test/build firmware/test && cmake --build firmware/test/build && ./firmware/test/build/test_state_machine_only` passes
- [ ] `uv run python scripts/import_linter_gate.py` passes
- [ ] If I changed `firmware/config.yaml`, I regenerated `firmware/config.h` and committed it
- [ ] If I changed `firmware/transition_table.yaml`, I regenerated `firmware/main/transition_table.h` and `firmware/test/test_transition_table_generated.c` and committed them
- [ ] If I added a new `scripts/*.py` file, I added an entry to `scripts/manifest.yaml`
- [ ] I reviewed the diff for secrets, debug prints, and unintended changes

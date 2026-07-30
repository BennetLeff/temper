---
module: workflow
tags: [ci, required-checks]
problem_type: workflow
---

# Required-checks post-merge probe

Disposable docs-only probe for verifying that the always-on required-check
aggregator reports a legitimate skip when no Python Tests trigger path is
changed. This file is removed when the probe PR is closed.

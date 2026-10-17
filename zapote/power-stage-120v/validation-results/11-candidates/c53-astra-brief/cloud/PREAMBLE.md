# Preamble for every cloud task (paste first)

You are a Codex cloud agent on the `temper` environment. The repository is public; the work is on a branch you must fetch.

1. **Get the right code.** Tasks start on `main`, which is far behind. Run:
   `git fetch origin cloud/s53-order-items && git checkout -b work/<task> FETCH_HEAD`, then
   `git merge-base --is-ancestor 0b3668245 HEAD && echo OK`. If it does not print OK, stop and report; do not work on `main`.
2. **Read your instructions** from `zapote/power-stage-120v/validation-results/11-candidates/c53-astra-brief/BRIEF.md`: the
   "Hard limits" and "Report format" sections, and the item sections named in your task. Ignore everything there about
   the remote box, `taskset`, Elmer, `~/WS` and ssh: you are in the cloud, not on the box. Your results go under
   `zapote/power-stage-120v/validation-results/11-candidates/c53-astra-results/<task>/` in the branch you return.
3. **No outreach, no order, no spend, no credentials, no design edits** (BRIEF.md hard limits 1-4). Do not push anywhere except
   the branch the cloud UI returns.
4. **Environment honesty.** Gitignored vendor models and the enclosure CAD may be absent here. If a needed input is missing or
   the internet is off, record BLOCKED with the exact missing path or URL; never fill the gap from memory or invent a number.
5. **KiCad policy.** The image's `kicad-cli` is 10.99, not the repo's pinned 10.0.5. Print `kicad-cli version` beside any DRC/ERC
   number; such numbers are exploratory. Never edit a ceiling or baseline file.
6. **Evidence.** Every number cites a file path, a URL with the read date, or a script you ran and committed. Search-snippet
   facts are labelled `SNIPPET, unverified`.
7. **Finish** with `SUMMARY.md` in your results folder: per item DONE / PARTIAL / BLOCKED, what the owner must do next, anything
   surprising. Commit as you go with the item number in each message.

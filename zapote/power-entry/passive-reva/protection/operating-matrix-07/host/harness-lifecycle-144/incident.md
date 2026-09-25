# Stale campaign processes: diagnosis and cleanup

The user correctly identified abandoned harness jobs. Completion receipts for the current simulations did not inventory those older shell process groups; the final campaign assessment and runtime cleanup are distinct checks.

At the fresh process-table inspection, two wildcard `sha256sum` commands had been alive for about 22 hours 41 minutes, each using only 0.01 seconds of accumulated CPU. Their argument lists included `normal-hysteretic-driver-candidate/trace.fifo`. Opening a FIFO for reading blocks until a writer appears. The hash commands had no timeout or regular-file restriction, leaving both parent shells and `head` consumers waiting. These jobs were stale but were not consuming the CPU attributed to the long simulations.

An older ad-hoc export-probe process group had been alive for about 25 hours 46 minutes. Its command launched FIFO readers, changed into the deck directory, and then constructed the executable from the changed `$PWD`, producing a nonexistent path. There was no child cleanup on producer failure. The originally named FIFOs were already absent when inspected, so no claim is made about their current pathname identity or the contents of the subsequently overwritten probe log. The live command text and its blocked descendants establish the abandoned lifecycle; later successful probe files do not close that original shell group.

## Cleanup evidence

`processes-before.json` captures the exact process identities, parents, groups, age, CPU time and commands. `path-inspection.json` records `lstat` results without opening any campaign FIFO. `cleanup-receipt.json` records SIGTERM to groups 61540, 92154 and 92326 only after checking every member's working directory and group identity. All eleven targeted processes disappeared. No source or trace was deleted. `runtime-after-cleanup.json` found no remaining processes with the known solver, pipeline, compressor or hash executable names.

## Current BYPASS result

The user's live-processing snapshot predates completion. The latest BYPASS metadata records 32,287,070 samples, 62 repeated-time intervals, zero backward intervals and no nonfinite callback time. `first_invalid=true` is a legacy non-increasing-time flag; the capture deliberately retained duplicates for the versioned event-aware observable audits. The strict legacy checker still rejects them, and that rejection is preserved. Duplicate timestamps alone neither establish electrical failure nor authorize acceptance.

Postcapture analysis completed with all five pipeline exit lists zero. Parent review accepted the own normal prefix and crest phase. The complete fault remains **FAIL** because VD reached 651.173012 V above the unchanged 500 V screen. The independent sampled observations establish the intended absence of external latched shutdown when bypassed. This is conditional authored-model diagnostic evidence, not hardware or complete physical trace qualification. See `../campaign-report-139.md` and `../../faults/settled-bypass-neg-66/full-BYPASS-NEG/campaign-verdict-138.json`.

## Prevention scope

The frozen runner45 already owns and reaps its direct children and has capture/export timeouts. The launch and postcapture shell wrappers lack a complete outer interruption/timeout lifecycle. New future-command tooling in this packet supervises a dedicated process group and rejects nonregular hash inputs. It does not modify the frozen sources, checker criteria or earlier acceptance receipts. It must be used for future command launches; it does not retrofit an already-running job or handle supervisor SIGKILL, machine failure, or descendants that deliberately detach into another session.

No new circuit simulation was launched. Approximately 21 GiB remained free (95% filesystem usage) at inspection. Process cleanup alone does not reclaim the retained raw archives. Large raw evidence has not been deleted or claimed backed up to Google Drive.

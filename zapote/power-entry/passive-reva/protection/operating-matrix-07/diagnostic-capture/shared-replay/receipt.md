# Shared 400 ms diagnostic receipt

This run used the canonical cold-start electrical deck unchanged, with only
the `.control` block removed for shared-library control. The canonical deck
hash is `e9a9cb849b92513665ad7852ccafcea867a1094b664d4e48458f4ff5f8f4257b`;
the shared deck hash is
`4bd17284fbcd8e0ccfacaacf38b9be3d47fc5ef8d191e655a8bf1e2b0f46d3b7`. The
controller include is the verified PWM-latch model (`d98f3890...`).

The headless shared API ran to the requested stop at
`0.351490000000000025 s` after 764.573 s wall/simulation runtime. The
pre-stall export has 501,348 rows and 45 columns and was checked finite and
strictly increasing before compression. At its final sample:

```
VB=364.4469728 V  VCOMP=2.84894516 V  ICOMP=2.49226366 V
raw=5 V  pwm_hold=5 V  phase=6.346906e-6 s  M1=.4907198  M2=1.3403205
```

After `bg_resume`, the run advanced to
`0.373498343395387178 s` during the 60.015 s bounded observation and was then
intentionally halted with `bg_halt`; this is an observed continuation point,
not a claim of numerical stall. The latest scalar print was:

```
VB=369.3117246 V  VCOMP=2.85372414 V  ICOMP=2.54385703 V
raw=5 V  pwm_hold=2.49999993 V  phase=1.941186e-6 s  M1=.4922157  M2=1.3457798
```

The post-halt export is retained as a diagnostic-only 45-column trace. Its
strict-time checker found a real duplicate timestamp at row 502,304:
`0.351508835331273084 s`. The immediately preceding row has `v(pwm)=0`,
while both duplicate rows have `v(pwm)=15`; the duplicate rows themselves
also differ in analog values. The maintained header shows `v(permit)` remains
its 5 V PWL level. The rows were preserved and not deduplicated. This trace is
therefore rejected by the strict checker and is evidence of the shared run's
discontinuity/export behavior, not an accepted normal witness.

Lossless archives (the uncompressed SHA is listed first):

* `before-stall-shared.tsv.gz`: uncompressed
  `86e39b93761aa9143b4c83bfec0c2949b59eed098ad91b473d8dc91e683c8c85`,
  archive `315517c2c6157cd398fc23a7f4e2d99b420432a254cf107342c4f8dc3382c1fe`.
* `post-stall-halt.tsv.gz`: uncompressed
  `21a34d945a318cf8dff10e8eb87044a4356edadb4c441c470f5528ec74999295`,
  archive `c714eb50c9f671522216e0ffd7c61a78f7a1ed95f00a7578e8c1ed00bb158ce5`.

The run log is `4a34ce4aa069480b4cdd84b80a1cce669755409144b40c66bebe6a0d634cab17`;
the shared transport source is `5184bb96b052b3bfe1454a0201713bdd1f3258249b5b555decd83de0fdecd8c8`.

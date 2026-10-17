# SPI series-resistor tolerance proposal

This is a source-only proposal for the circuit owner. The canonical
`elec/src/modules.ato` file is intentionally unchanged in this worktree.

```diff
-    r_sclk.value = 33ohm +/- 5%
+    r_sclk.value = 33ohm +/- 1%
-    r_mosi.value = 33ohm +/- 5%
+    r_mosi.value = 33ohm +/- 1%
-    r_cs.value = 33ohm +/- 5%
+    r_cs.value = 33ohm +/- 1%
-    r_miso.value = 33ohm +/- 5%
+    r_miso.value = 33ohm +/- 1%
```

The exact YAGEO MPN `RC0603FR-0733RL` is a 33 ohm, ±1%, 0.1 W, 0603 thick
film resistor with ±100 ppm/°C TCR. Either accept this proposal in the source
or select an MPN whose tolerance is actually ±5% before the release BOM is
frozen.

# Revision 08 feedback candidate

This is a new simulation candidate, not an accepted converter run or a circuit
installed on the retained PCB. It copies the six electrical source files from
`operating-matrix-07/accepted-baseline-11` and changes exactly one electrical line:

```diff
-Rfb1 vb vsense 1meg
+Rfb1 vd vsense 1meg
```

The unchanged five includes retain the authored controller, independent external
VD/VB protection, gate enable/standby behavior and assumed BAV23C clamp. The
healthy F2 path remains closed. No F1 clearing law or ideal source disconnect
has been introduced. Full file hashes are in `../source-identity.json`.

The separate `../feedback-fixture/` isolates what the feedback relocation does
to the controller's modeled OVP under forced VD/VB inputs. It does not execute
this complete deck or validate its startup, compensation, load response,
F2-open dynamics or silicon timing. No full transient launch is authorized by
the existence of this file alone; follow the revision plan's preceding gates.

The retained physical 54-part source senses VB, has a different clamp mapping,
and does not integrate these experimental protection additions. Historical
source-build-07 must not be used to assert physical parity: it was rejected.

# Feature Request/Bug: `.required` attribute for interfaces is not enforced in v0.2.69

## Description
I observed that the `.required` attribute is used in the `atopile` codebase (e.g., `src/faebryk/library/i2c_pulls_weak.ato`), which suggests a mechanism to enforce that specific interfaces must be connected.

However, when testing with `atopile` v0.2.69, adding `.required = True` to an interface only results in an "Implicit Declaration" warning, and **does not** raise an error if the interface is left unconnected.

## Reproduction
```python
# test_required.ato
import HighVoltageBus from "interfaces.ato"

module TestSafety:
    hv = new HighVoltageBus
    hv.required = True

module TestUnconnected:
    comp = new TestSafety
    # hv unconnected - Should fail build, but passes
```

**Output:**
```
WARNING  Implicit Declaration Future Deprecation Warning
         Field 'required' not declared for ... Declaring implicitly for now...
```

## Context
For safety-critical designs (like the Temper induction heater), we need a way to enforce that safety interlocks and thermal shutdowns are strictly connected at compile time.

## Questions
1. Is `.required` supported in v0.2.x, or is it a feature for a future `faebryk`-based release?
2. Is there a different syntax (e.g., `must_connect = True`) available now to enforce connection?
3. If not, consider this a formal feature request to add `.required` enforcement to the compiler.
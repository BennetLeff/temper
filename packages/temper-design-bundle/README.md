# temper-design-bundle

`temper-design-bundle` is the validated Rust boundary between Atopile design
intent, authored PCL constraints, and future placement, routing, and validation
stages. It builds an immutable `DesignBundle` only after identity, geometry,
constraint-reference, and safety-floor checks pass.

The crate deliberately does not run placement or routing. Python may call the
optional PyO3 normalization function, but cannot use a partially validated
bundle as mutable pipeline state.

## Verification

```sh
cargo test --manifest-path packages/temper-design-bundle/Cargo.toml
cargo check --manifest-path packages/temper-design-bundle/Cargo.toml --features python
```

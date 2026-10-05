# R5 validation verification

Final CAD/thermal receipt verified after thermal agent's completed run: all four full SHA256 checks pass for original kernel, thermal source, final CAD scalar export and current comparison output. The runner requires each of these four receipt paths exactly once; missing or stale receipt/data aborts.

- 11 Rust tests pass, including an independent ring quadrature, fourth-power roof radius scaling, Faraday loop scale, conservative bias bounds, rejection of empty current thermal data and failed joint screen for NaN t90-pan.
- rustfmt and direct clippy-driver with warnings denied pass.
- 36 current R5 thermal comparison rows consumed directly. No row meets both proposed whole-system planning bound<2°C and t90-pan<2s after adding the hypothetical1°C reserve. Minimum bound is2.442073°C.
- Uniform nominal force0.218182N and href2000 rows: D8 t90-pan3.44s, thermal bias−2.437675°C, full planning bound3.437675°C; D6 t90-pan2.94s, thermal bias−2.474231°C, full planning bound3.474231°C. These are model results, not measurements.
- Additional outputs:54 CAD roof sensitivities,36 loop pickup sensitivities,6 illustrative error allocations and20 single-pole ramp scales. These have explicit SIMULATED labels and limited scope.
- All nine gap records retain physical_result=NOT_RUN. Original bench empty acquisition template rechecked and rejected; rejection saved in results/inherited-template-rejection.txt.

No firmware, physical cartridge, sealing, induction, endurance or certification test was executed. No hardware is enabled by this package.

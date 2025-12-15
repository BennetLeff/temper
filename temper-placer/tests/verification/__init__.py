"""
Verification tests for temper-placer mathematical correctness.

This package contains tests that verify:
- Ground-truth: Known-answer tests with analytically computed expected values
- Gradient correctness: JAX autodiff matches finite differences
- Numerical stability: Edge cases don't produce NaN/Inf
- Optimizer convergence: Trivial problems converge to known solutions
"""

"""
Optimizer module for temper-placer.

This module implements the JAX-based gradient descent optimizer with:
- Adam optimizer via optax with learning rate scheduling
- Gumbel-Softmax temperature annealing for rotation
- Curriculum learning with progressive constraint introduction
- Periodic validation-in-the-loop (DRC, ngspice)
- Checkpoint saving and resumption
- Early stopping and convergence detection

The optimizer coordinates:
1. Forward pass: compute placement state → losses
2. Backward pass: compute gradients via JAX autodiff
3. Update step: apply optimizer (optax.adam)
4. Validation: periodically run KiCad DRC and ngspice
5. Logging: emit metrics for visualization

Training Phases (Curriculum):
1. Spread only - distribute components
2. Add wirelength - optimize connectivity
3. Add overlap/boundary - enforce hard constraints
4. Add thermal/EMI - optimize performance
5. Add DRC/validation - ensure manufacturability
"""

# Imports will be added as modules are implemented
# from temper_placer.optimizer.core import Optimizer, OptimizerConfig
# from temper_placer.optimizer.scheduler import TemperatureScheduler, LRScheduler
# from temper_placer.optimizer.curriculum import CurriculumSchedule
# from temper_placer.optimizer.validation import run_drc, run_ngspice_validation

__all__ = []

"""Predefined experiment matrices for ablation studies."""

from pathlib import Path

from temper_placer.ablation.config import (
    AblationStudyConfig,
    ComponentToggle,
    ExperimentConfig,
    LossToggle,
)


def create_baseline_experiment() -> ExperimentConfig:
    """Create the baseline experiment with all features enabled."""
    return ExperimentConfig(
        name="baseline",
        description="Full pipeline with all heuristics, techniques, and losses enabled.",
        components=ComponentToggle(),
        losses=LossToggle(),
        tags=["baseline"]
    )

def create_minimal_experiment() -> ExperimentConfig:
    """Create a minimal experiment with only hard constraints."""
    return ExperimentConfig(
        name="minimal",
        description="Minimal pipeline with only hard constraints (overlap, boundary).",
        components=ComponentToggle.all_disabled(),
        losses=LossToggle.hard_constraints_only(),
        tags=["minimal"]
    )

def create_heuristic_ablation_matrix() -> list[ExperimentConfig]:
    """Create experiments that ablate each heuristic one by one."""
    experiments = [create_baseline_experiment()]

    heuristics = ComponentToggle().get_enabled_heuristics()
    for h in heuristics:
        components = ComponentToggle()
        setattr(components, h, False)

        experiments.append(ExperimentConfig(
            name=f"ablate_{h}",
            description=f"Baseline with '{h}' heuristic disabled.",
            components=components,
            losses=LossToggle(),
            tags=["ablation", "heuristic"]
        ))

    return experiments

def create_technique_ablation_matrix() -> list[ExperimentConfig]:
    """Create experiments that ablate each technique one by one."""
    experiments = [create_baseline_experiment()]

    techniques = ComponentToggle().get_enabled_techniques()
    for t in techniques:
        components = ComponentToggle()
        setattr(components, t, False)

        experiments.append(ExperimentConfig(
            name=f"ablate_{t}",
            description=f"Baseline with '{t}' technique disabled.",
            components=components,
            losses=LossToggle(),
            tags=["ablation", "technique"]
        ))

    return experiments

def create_loss_ablation_matrix() -> list[ExperimentConfig]:
    """Create experiments that ablate each non-hard loss function."""
    experiments = [create_baseline_experiment()]

    all_losses = LossToggle().get_enabled_losses()
    hard_constraints = {"overlap", "boundary", "clearance"}

    for loss_name in all_losses:
        if loss_name in hard_constraints:
            continue

        losses = LossToggle()
        setattr(losses, loss_name, False)

        experiments.append(ExperimentConfig(
            name=f"ablate_{loss_name}",
            description=f"Baseline with '{loss_name}' loss function disabled.",
            components=ComponentToggle(),
            losses=losses,
            tags=["ablation", "loss"]
        ))

    return experiments

def create_full_ablation_matrix() -> list[ExperimentConfig]:
    """Create full matrix ablating all components one by one."""
    return (
        create_heuristic_ablation_matrix() +
        create_technique_ablation_matrix()[1:] +
        create_loss_ablation_matrix()[1:]
    )

def create_component_addition_matrix() -> list[ExperimentConfig]:
    """Create experiments adding components one by one to a minimal baseline."""
    experiments = [create_minimal_experiment()]

    # Add heuristics
    heuristics = ComponentToggle().get_enabled_heuristics()
    for h in heuristics:
        components = ComponentToggle.all_disabled()
        setattr(components, h, True)
        experiments.append(ExperimentConfig(
            name=f"add_{h}",
            description=f"Minimal with '{h}' heuristic added.",
            components=components,
            losses=LossToggle.hard_constraints_only(),
            tags=["addition", "heuristic"]
        ))

    # Add techniques
    techniques = ComponentToggle().get_enabled_techniques()
    for t in techniques:
        components = ComponentToggle.all_disabled()
        setattr(components, t, True)
        experiments.append(ExperimentConfig(
            name=f"add_{t}",
            description=f"Minimal with '{t}' technique added.",
            components=components,
            losses=LossToggle.hard_constraints_only(),
            tags=["addition", "technique"]
        ))

    # Add losses
    all_losses = LossToggle().get_enabled_losses()
    hard_constraints = {"overlap", "boundary", "clearance"}
    for loss_name in all_losses:
        if loss_name in hard_constraints:
            continue
        losses = LossToggle.hard_constraints_only()
        setattr(losses, loss_name, True)
        experiments.append(ExperimentConfig(
            name=f"add_{loss_name}",
            description=f"Minimal with '{loss_name}' loss added.",
            components=ComponentToggle.all_disabled(),
            losses=losses,
            tags=["addition", "loss"]
        ))

    return experiments

def create_standard_study(
    study_name: str,
    test_cases: list[Path],
    seeds: list[int] | None = None,
    output_dir: Path = Path("ablation_results")
) -> AblationStudyConfig:
    """Create a standard ablation study with the full ablation matrix."""
    if seeds is None:
        seeds = [42, 123, 456, 789, 1024]
    return AblationStudyConfig(
        study_name=study_name,
        experiments=create_full_ablation_matrix(),
        seeds=seeds,
        test_cases=test_cases,
        output_dir=output_dir
    )

import importlib.util
import json
import os
from typing import Any


def _load_memory_profiler():
    """Safely load the memory profiler module from temper-placer."""
    try:
        # Get the current directory
        cur_dir = os.path.dirname(os.path.abspath(__file__))

        # Construct path to memory_profiler.py
        memory_profiler_path = os.path.join(
            cur_dir,
            "..",
            "..",
            "..",
            "temper-placer",
            "src",
            "temper_placer",
            "scale",
            "memory_profiler.py",
        )

        # Check if file exists
        if not os.path.exists(memory_profiler_path):
            print(f"Warning: memory_profiler.py not found at {memory_profiler_path}")
            return None

        # Load the module
        spec = importlib.util.spec_from_file_location("memory_profiler", memory_profiler_path)
        if spec is None:
            print("Warning: Could not create module spec for memory_profiler")
            return None

        module = importlib.util.module_from_spec(spec)
        try:
            if spec.loader is not None:
                spec.loader.exec_module(module)
                return module
            else:
                print("Warning: spec.loader is None")
                return None
        except Exception as e:
            print(f"Warning: Could not execute module: {e}")
            return None
    except Exception as e:
        print(f"Warning: Could not load memory_profiler: {e}")
        return None


def discover_packages() -> list[str]:
    """Discover all packages in the project."""
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    packages_dir = os.path.join(os.path.dirname(cur_dir), "packages")
    packages = []

    if os.path.exists(packages_dir):
        for item in os.listdir(packages_dir):
            item_path = os.path.join(packages_dir, item)
            # Check if it's a Python package
            if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "pyproject.toml")):
                packages.append(item_path)

    return packages


def run_profiling(
    target: str | None,
    output_dir: str,
    profile_type: str = "all",
    _include_dependencies: bool = False,
    _config_file: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Run automated profiling on target package(s)."""

    # Load the memory profiler
    memory_profiler = _load_memory_profiler()

    # Validate if memory profiling is available
    has_memory_profiling = False
    if memory_profiler is not None:
        try:
            # Test if we can access the required function
            if hasattr(memory_profiler, "profile_optimizer_memory") and callable(
                memory_profiler.profile_optimizer_memory
            ):
                has_memory_profiling = True
            else:
                print(
                    "Warning: Memory profiler loaded but missing profile_optimizer_memory function"
                )
        except Exception as e:
            print(f"Warning: Error accessing memory_profiler attributes: {e}")
            has_memory_profiling = False  # noqa: F821
    if memory_profiler is not None:
        try:
            # Test if we can access the required function
            if hasattr(memory_profiler, "profile_optimizer_memory") and callable(
                memory_profiler.profile_optimizer_memory
            ):
                has_memory_profiling = True
            else:
                print(
                    "Warning: Memory profiler loaded but missing profile_optimizer_memory function"
                )
        except Exception as e:
            print(f"Warning: Error accessing memory_profiler attributes: {e}")
            has_memory_profiling = False

    # Determine targets
    targets = []
    if target:
        targets.append(target)
    else:
        # Discover all packages
        targets = discover_packages()

    results = {}

    for target_path in targets:
        package_name = os.path.basename(target_path)
        print(f"Profiling {package_name}...")

        package_results = {}

        # Run memory profiling if requested or 'all'
        if has_memory_profiling and (profile_type == "memory" or profile_type == "all"):
            try:
                # Run memory profiling with different scales
                components_to_test = [50, 100, 200, 500]
                memory_results = {}

                for n_components in components_to_test:
                    print(f"  Testing {n_components} components...")
                    # Create output path for this test
                    test_output = os.path.join(
                        output_dir, package_name, "memory", f"{n_components}_components"
                    )
                    os.makedirs(test_output, exist_ok=True)

                    # Run profiling
                    try:
                        profile = memory_profiler.profile_optimizer_memory(
                            n_components=n_components, epochs=100, seed=42
                        )  # type: ignore

                        # Save detailed results
                        try:
                            profile.save_json(os.path.join(test_output, "profile.json"))
                        except Exception as e:
                            print(f"Error saving profile JSON: {e}")

                        # Store summary
                        try:
                            memory_results[f"{n_components}_components"] = {
                                "peak_rss_mb": getattr(profile, "peak_rss_mb", None),
                                "jax_device_mb": getattr(profile, "jax_device_mb", None),
                                "memory_growth_mb_per_100_epochs": getattr(
                                    profile, "memory_growth_mb_per_100_epochs", None
                                ),
                                "gc_collections": getattr(profile, "gc_collections", None),
                                "runtime_seconds": getattr(profile, "runtime_seconds", None),
                            }
                        except Exception as e:
                            print(f"Error extracting profile attributes: {e}")

                    except Exception as e:
                        print(f"Error running profile_optimizer_memory: {e}")

                if memory_results:
                    package_results["memory"] = memory_results

                # Save report

                # Save report
                memory_profiles = []
                for n_components in components_to_test:
                    test_output = os.path.join(
                        output_dir,
                        package_name,
                        "memory",
                        f"{n_components}_components",
                        "profile.json",
                    )
                    if os.path.exists(test_output):
                        try:
                            # Load profile using MemoryProfile.load_json
                            if hasattr(memory_profiler, "MemoryProfile") and callable(
                                getattr(memory_profiler.MemoryProfile, "load_json", None)
                            ):
                                profile = memory_profiler.MemoryProfile.load_json(test_output)
                                memory_profiles.append(profile)
                        except Exception as e:
                            print(f"Error loading profile from {test_output}: {e}")

                if (
                    memory_profiles
                    and hasattr(memory_profiler, "MemoryProfile")
                    and callable(getattr(memory_profiler.MemoryProfile, "save_report", None))
                ):
                    try:
                        memory_profiler.MemoryProfile.save_report(
                            memory_profiles,
                            os.path.join(output_dir, package_name, "memory", "memory_report.json"),
                        )
                    except Exception as e:
                        print(f"Error saving memory report: {e}")

            except Exception as e:
                print(f"Error in memory profiling section: {e}")

        # Store results for this package
        results[package_name] = package_results

        # Save package results
        package_output_dir = os.path.join(output_dir, package_name)
        os.makedirs(package_output_dir, exist_ok=True)
        with open(os.path.join(package_output_dir, "results.json"), "w") as f:
            json.dump(package_results, f, indent=2)

    # Save overall results
    with open(os.path.join(output_dir, "results_summary.json"), "w") as f:
        json.dump(results, f, indent=2)

    return results

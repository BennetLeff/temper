# temper-autoprof

Automated profiling infrastructure for the Temper project

## Overview

`temper-autoprof` is a toolkit for automated profiling of Python packages in the Temper project. It provides:

- Automated memory and CPU profiling
- Integration with the temper-placer optimizer
- Detailed reporting and comparison capabilities

## Installation

```bash
cd packages/temper-autoprof
pip install -e .
```

## Usage

```bash
# Run profiling on a specific package
temper-autoprof run --target ../temper-placer --profile-type memory

# Run profiling on all packages
temper-autoprof run

# Generate a report
temper-autoprof report

# Compare results across runs
temper-autoprof compare
```

## Architecture

The automated profiling infrastructure consists of:

1. **Discovery** - Finds all packages in the project
2. **Profiling** - Executes memory and CPU profiling
3. **Reporting** - Generates detailed reports and visualizations
4. **Integration** - Hooks into CI/CD and development workflows

## Integration with temper-placer

`temper-autoprof` leverages the existing memory profiler in `temper-placer` to measure:

- Peak RSS memory usage
- JAX device memory
- Memory growth over epochs
- Garbage collection statistics
- Runtime performance

These metrics are used to:

- Detect memory leaks
- Validate memory efficiency at scale
- Enforce memory budgets
- Track memory growth over epochs

## Configuration

Configuration is done via a YAML file that specifies:

- Profiling parameters (epochs, component counts)
- Memory thresholds
- Output formats
- Reporting options

Example `.temper-autoprof.yaml`:
```yaml
# Configuration for temper-autoprof
memory:
  components: [50, 100, 200, 500]
  epochs: 100
  thresholds:
    peak_rss_mb: 1500
    memory_growth_mb_per_100_epochs: 500

cpu:
  profile: false

report:
  formats: [text, json, html]
  output_dir: profiling-results
```

## Future Work

- Add CPU profiling capabilities
- Implement flame graph generation
- Add pre-commit hook integration
- Create GitHub Actions workflow
- Add support for historical comparison
- Implement anomaly detection
- Add web-based dashboard

## License

MIT License

## Development

For development, install in editable mode:

```bash
pip install -e .[dev]
```

Run tests with:

```bash
pytest
cov: --cov=temper_autoprof
cov: --cov-report=term

# Run with specific markers
pytest -m unit
test marks: unit, integration, e2e
```

## Contributing

Contributions are welcome! Please open an issue or pull request on GitHub.
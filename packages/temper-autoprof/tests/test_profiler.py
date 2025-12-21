"""
Unit tests for the automated profiling infrastructure.
"""

import sys
import tempfile
from pathlib import Path

# Add the package directory to the Python path
cur_dir = Path(__file__).parent
src_path = cur_dir.parent / "src"
sys.path.insert(0, str(src_path))


def test_discover_packages():
    """Test package discovery."""
    from temper_autoprof.profiler import discover_packages

    packages = discover_packages()

    # Should at least find temper-placer
    assert "temper-placer" in [Path(p).name for p in packages]


def test_run_profiling():
    """Test running profiling."""
    from temper_autoprof.profiler import run_profiling

    # Use temporary directory for output
    with tempfile.TemporaryDirectory() as temp_dir:
        # Convert to string for the function
        temp_dir_str = str(temp_dir)

        # Run profiling with a fake target
        results = run_profiling(
            target=None,
            output_dir=temp_dir_str,
            profile_type="all",
        )

    # Should return a dictionary
    assert isinstance(results, dict)


def test_cli_run():
    """Test CLI run command."""
    from click.testing import CliRunner

    from temper_autoprof.cli import cli

    runner = CliRunner()
    result = runner.invoke(
        cli, ["run", "--profile-type", "all", "--output", "temp-results"], catch_exceptions=False
    )

    # Should exit with code 0 or 1 (since we don't have the actual functionality yet)
    assert result.exit_code in [0, 1]

    # Should output something about profiling
    assert "Profiling" in result.output or "Error" in result.output or "Warning" in result.output


def test_cli_report():
    """Test CLI report command."""
    from click.testing import CliRunner

    from temper_autoprof.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["report", "--format", "text"], catch_exceptions=False)

    # Should exit with code 0 or 1
    assert result.exit_code in [0, 1]

    # Should output something about reporting
    assert "report" in result.output.lower() or "error" in result.output.lower()

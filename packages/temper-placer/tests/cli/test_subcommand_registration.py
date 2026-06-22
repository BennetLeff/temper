"""Smoke tests verifying all entry_points subcommands are registered."""
from importlib.metadata import entry_points

from click.testing import CliRunner
from temper_placer.cli import main


def test_all_entry_points_registered():
    eps = entry_points(group="temper_placer.cli.subcommands")
    ep_names = {ep.name for ep in eps}
    registered = set(main.commands.keys())
    missing = ep_names - registered
    extra = registered - ep_names
    assert not missing, f"Subcommands in entry_points but not registered: {missing}"
    if extra:
        print(f"Note: {extra} registered but not in entry_points group")


def test_each_subcommand_help_exits_zero():
    runner = CliRunner()
    for name in sorted(main.commands.keys()):
        result = runner.invoke(main, [name, "--help"])
        assert result.exit_code == 0, f"{name} --help exited with {result.exit_code}: {result.output[:200]}"


def test_count_matches():
    eps = entry_points(group="temper_placer.cli.subcommands")
    assert len(main.commands) >= len(eps), (
        f"Registered {len(main.commands)} commands, "
        f"but {len(eps)} entry_points exist"
    )

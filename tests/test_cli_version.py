"""CLI version flag and package version consistency tests."""

import importlib
import re
from pathlib import Path

import pytest

import agentconfig

# NOTE: `agentconfig.cli.__init__` re-exports a `main` function, which shadows
# the `agentconfig.cli.main` module attribute — use importlib to reach the
# actual module.
main_module = importlib.import_module("agentconfig.cli.main")
create_parser = main_module.create_parser


def test_version_flag_prints_version(capsys):
    """`agentconfig --version` prints the version and exits 0."""
    with pytest.raises(SystemExit) as excinfo:
        create_parser().parse_args(["--version"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("agentconfig ")


def test_package_version_matches_pyproject():
    """__version__ must never drift from the declared package version."""
    pyproject = Path(agentconfig.__file__).resolve().parent.parent / "pyproject.toml"
    match = re.search(
        r'^version\s*=\s*"([^"]+)"',
        pyproject.read_text(encoding="utf-8"),
        re.M,
    )
    assert match is not None
    assert agentconfig.__version__ == match.group(1)

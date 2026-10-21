"""Prints the eval report after the run: pytest captures output inside tests, and
ruff bans print."""

import pytest

REPORT = pytest.StashKey[list[str]]()


@pytest.fixture(scope="session")
def report(pytestconfig: pytest.Config) -> list[str]:
    """Lines to print in pytest's terminal summary."""
    return pytestconfig.stash.setdefault(REPORT, [])


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    lines = config.stash.get(REPORT, None)
    if lines:
        terminalreporter.write_sep("=", "eval report")
        for line in lines:
            terminalreporter.write_line(line)

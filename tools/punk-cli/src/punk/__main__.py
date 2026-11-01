"""Executable entry point for Python and standalone builds."""

# internal
from punk import cli

# use the same command group in module and bundled entry points.
if __name__ == "__main__":
    cli.main()

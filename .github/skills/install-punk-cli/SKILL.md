---
name: install-punk-cli
description: "Use when asked to install, reinstall, upgrade, or set up the punk command-line interface from this repository, either as a standalone binary built with PyInstaller or as a Python package installed with pip."
---

# Install punk cli

The punk cli lives in `tools/punk-cli` (distribution `punk-records`, console
script `punk`, Python `>=3.10`). Run every command below from that directory.

## Choose an install method

- **Standalone binary** (default): builds a single-file executable with
  PyInstaller and copies it to `~/.local/bin` (or a chosen directory). Use this
  when the user wants `punk` available globally without a Python environment.
- **Python package**: installs `punk` into a virtual environment. Use this for
  development (`-e`) or when the user explicitly asks for a pip install.

Ask the user only if the intent is unclear; otherwise use the standalone binary.

## Standalone binary

1. Create an isolated build environment and install build dependencies:

   ```sh
   python3 -m venv .venv
   .venv/bin/python -m pip install --upgrade pip
   .venv/bin/python -m pip install ".[build]"
   ```

   On Windows use `.venv\Scripts\python.exe` instead of `.venv/bin/python`.

2. Build and install the binary:

   ```sh
   .venv/bin/python scripts/build.py --install
   ```

   Add `--install-dir <dir>` to install somewhere other than `~/.local/bin`.
   The binary is built at `dist/punk` (`dist/punk.exe` on Windows), and the
   script exits non-zero if the build or copy fails.

3. If the install directory is not on `PATH`, tell the user how to add it
   (for example `export PATH="$HOME/.local/bin:$PATH"` in their shell profile)
   instead of editing shell profiles without permission.

## Python package

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
```

Drop `-e` and `[dev]` for a non-editable, runtime-only install. The command is
then available as `.venv/bin/punk`, or as `punk` after activating the venv.

## Verify

Confirm the installed command runs and reports the expected version:

```sh
punk --version
```

Use the full path (for example `~/.local/bin/punk` or `.venv/bin/punk`) if its
directory is not on `PATH`. Running `punk` without the `config` or `init`
subcommands creates a default configuration file on first start, so prefer
`--version` for verification.

## Rules

- Never install into the system Python or use `sudo pip`; always use a venv.
- Do not commit `.venv/`, `build/`, or `dist/` output.
- Report the installed path and the `punk --version` output to the user.

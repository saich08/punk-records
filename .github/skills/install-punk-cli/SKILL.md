---
name: install-punk-cli
description: "Use when asked to install, reinstall, upgrade, or set up the punk command-line interface from this repository, either as a standalone binary built with PyInstaller or as a Python package installed with pip."
---

# Install punk cli

The punk cli lives in `tools/punk-cli` (distribution `punk-records`, console
script `punk`, Python `>=3.10`). Run every command below from that directory.

## Choose an install method

- **Standalone binary** (default): builds a single-file executable with
  PyInstaller and installs it to `/usr/local/bin`, so every user, including
  root and `sudo`, can run it. Use this when the user wants `punk` available
  globally without a Python environment.
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

2. Build the binary as the current user (never with `sudo`, which would leave
   root-owned files in `.venv/`, `build/`, and `dist/`):

   ```sh
   .venv/bin/python scripts/build.py
   ```

   The binary is built at `dist/punk` (`dist/punk.exe` on Windows), and the
   script exits non-zero if the build fails.

3. Install it system-wide, using `sudo -A` so the password is requested
   through the secure prompt:

   ```sh
   sudo -A install -m 755 dist/punk /usr/local/bin/punk
   ```

   `/usr/local/bin` is on the default `PATH` and on sudo's `secure_path`, so
   no shell profile changes are needed. If the user explicitly wants a
   per-user install without sudo, use
   `.venv/bin/python scripts/build.py --install` instead, which copies to
   `~/.local/bin` (or `--install-dir <dir>`).

4. On Windows, skip step 3 and use `scripts/build.py --install`.

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
command -v punk
punk --version
sudo -A punk --version
```

Confirm `command -v punk` prints `/usr/local/bin/punk`. If it prints another
path, such as a stale `~/.local/bin/punk` that shadows it, tell the user
instead of deleting that file. Skip the `sudo` check for venv installs. Running `punk` without the `config` or `init`
subcommands creates a default configuration file on first start, so prefer
`--version` for verification.

## Rules

- Never install into the system Python or use `sudo pip`; always use a venv.
- Use `sudo` only for the final `install` into `/usr/local/bin`.
- Running `punk` as root uses root's own config (`/root/.config/punk/`), not
  the invoking user's; mention this when the user plans to run it with sudo.
- Do not commit `.venv/`, `build/`, or `dist/` output.
- Report the installed path and the `punk --version` output to the user.

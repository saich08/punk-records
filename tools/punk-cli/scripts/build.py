"""Build a standalone punk executable and optionally install it."""

# builtin
import os
import sys
import shutil
import pathlib
import argparse
import subprocess

# keep project paths stable when invoked outside the project directory.
ROOT = pathlib.Path(__file__).resolve().parents[1]


def build_binary() -> pathlib.Path:
    """Build a standalone executable and return its expected output path.

    Returns:
        The expected standalone executable path for the current platform.

    Raises:
        OSError: Build directories or the build process cannot be created.
        subprocess.CalledProcessError: PyInstaller exits unsuccessfully.
    """

    # derive all build paths from the project rather than the working directory.
    build_dir = ROOT / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--name",
            "punk",
            "--distpath",
            str(ROOT / "dist"),
            "--workpath",
            str(build_dir / "pyinstaller"),
            "--specpath",
            str(build_dir),
            "--paths",
            str(ROOT / "src"),
            "--copy-metadata",
            "punk-records",
            str(ROOT / "src" / "punk" / "__main__.py"),
        ],
        cwd=ROOT,
        check=True,
    )

    return ROOT / "dist" / ("punk.exe" if os.name == "nt" else "punk")


def main(argv: list[str] | None = None) -> int:
    """Build and optionally install the executable.

    Args:
        argv: Command-line arguments, or None to read the process arguments.

    Returns:
        Zero on success, or one if building or installation fails.
    """

    # reject installation options that would otherwise have no effect.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--install",
        action="store_true",
        help="Copy the built binary to the installation directory.")
    parser.add_argument("--install-dir",
                        type=pathlib.Path,
                        help="Installation directory (default: ~/.local/bin).")
    args = parser.parse_args(argv)
    if args.install_dir is not None and not args.install:
        parser.error("--install-dir requires --install")

    # do not install or report success unless the expected binary exists.
    try:
        binary = build_binary()
        if not binary.is_file():
            raise FileNotFoundError(
                f"Build did not produce the expected binary: {binary}")
        print(f"Built {binary}")

        # optional installation must never precede a verified build output.
        if args.install:
            # copying onto the build output itself must remain a no-op.
            install_dir = (args.install_dir
                           or pathlib.Path.home() / ".local" / "bin")
            install_dir = install_dir.expanduser()
            install_dir.mkdir(parents=True, exist_ok=True)
            destination = install_dir / binary.name
            if destination.resolve() != binary.resolve():
                shutil.copy2(binary, destination)
            print(f"Installed {destination}")
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Build/install failed: {error}", file=sys.stderr)

        return 1

    return 0


# propagate build and installation failures to the command-line exit status.
if __name__ == "__main__":
    sys.exit(main())

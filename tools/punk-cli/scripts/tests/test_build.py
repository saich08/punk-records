"""Tests for standalone builds and installation."""

# builtin
import io
import os
import pathlib
import tempfile
import unittest
import contextlib
import subprocess
from unittest import mock

# internal
from scripts import build


class BuildTests(unittest.TestCase):
    """Exercise standalone build arguments and installation."""

    def setUp(self) -> None:
        # isolate filesystem state and restore patches after each test.
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = pathlib.Path(directory.name)
        root = mock.patch.object(build, "ROOT", self.root)
        root.start()
        self.addCleanup(root.stop)
        self.binary = self.root / "dist" / ("punk.exe"
                                            if os.name == "nt" else "punk")

    def make_binary(self) -> None:
        # provide an executable fixture without invoking the bundler.
        self.binary.parent.mkdir()
        self.binary.write_bytes(b"test executable")
        self.binary.chmod(0o755)

    def test_build_command(self) -> None:
        # inspect build arguments without spawning the actual bundler.
        with mock.patch.object(build.subprocess, "run") as run:
            result = build.build_binary()

        # retain package metadata and project-relative entry paths.
        self.assertEqual(result, self.binary)
        args = run.call_args.args[0]
        self.assertEqual(args[:3], [build.sys.executable, "-m", "PyInstaller"])
        self.assertIn("--onefile", args)
        self.assertEqual(args[args.index("--copy-metadata") + 1],
                         "punk-records")
        self.assertEqual(args[-1],
                         str(self.root / "src" / "punk" / "__main__.py"))
        self.assertEqual(run.call_args.kwargs, {
            "cwd": self.root,
            "check": True
        })

    def test_build_without_install(self) -> None:
        # a build-only invocation must not create installation directories.
        self.make_binary()
        with mock.patch.object(build, "build_binary", return_value=self.binary):
            with contextlib.redirect_stdout(io.StringIO()):
                result = build.main([])

        # successful bundling alone must not create installation directories.
        self.assertEqual(result, 0)
        self.assertFalse((self.root / ".local").exists())

    def test_install_default_and_custom_directories(self) -> None:
        # copy both bytes and executable permissions to either destination.
        self.make_binary()
        for args, destination in (
            (["--install"], self.root / ".local" / "bin"),
            (["--install", "--install-dir",
              str(self.root / "custom")], self.root / "custom"),
        ):
            with self.subTest(args=args):
                with mock.patch.object(build,
                                       "build_binary",
                                       return_value=self.binary):
                    with mock.patch.object(build.pathlib.Path,
                                           "home",
                                           return_value=self.root):
                        with contextlib.redirect_stdout(io.StringIO()):
                            result = build.main(args)

                # preserve executable contents and permission bits.
                installed = destination / self.binary.name
                self.assertEqual(result, 0)
                self.assertEqual(installed.read_bytes(),
                                 self.binary.read_bytes())
                self.assertEqual(installed.stat().st_mode,
                                 self.binary.stat().st_mode)

    def test_install_replaces_existing_binary(self) -> None:
        # installation must replace an old executable rather than retain it.
        self.make_binary()
        destination = self.root / "installed"
        destination.mkdir()
        installed = destination / self.binary.name
        installed.write_bytes(b"old executable")
        with mock.patch.object(build, "build_binary", return_value=self.binary):
            with contextlib.redirect_stdout(io.StringIO()):
                result = build.main(
                    ["--install", "--install-dir",
                     str(destination)])

        # the installed file must contain the new build rather than stale bytes.
        self.assertEqual(result, 0)
        self.assertEqual(installed.read_bytes(), self.binary.read_bytes())

    def test_install_failure_is_reported(self) -> None:
        # a denied copy must return failure and preserve the error detail.
        self.make_binary()
        with mock.patch.object(build, "build_binary", return_value=self.binary):
            with mock.patch.object(build.shutil,
                                   "copy2",
                                   side_effect=PermissionError("Denied")):
                with contextlib.redirect_stdout(io.StringIO()):
                    with contextlib.redirect_stderr(io.StringIO()) as output:
                        result = build.main([
                            "--install", "--install-dir",
                            str(self.root / "installed")
                        ])

        # copy failures must retain diagnostics and a failing exit status.
        self.assertEqual(result, 1)
        self.assertIn("Build/install failed: Denied", output.getvalue())

    def test_build_failure_prevents_installation(self) -> None:
        # failed bundling must not attempt to copy any executable.
        with mock.patch.object(build,
                               "build_binary",
                               side_effect=subprocess.CalledProcessError(
                                   1, "PyInstaller")):
            with mock.patch.object(build.shutil, "copy2") as copy:
                with contextlib.redirect_stderr(io.StringIO()) as output:
                    result = build.main(["--install"])

        # bundling failure must not copy an old or nonexistent executable.
        self.assertEqual(result, 1)
        self.assertIn("Build/install failed", output.getvalue())
        copy.assert_not_called()

    def test_missing_binary_is_reported(self) -> None:
        # a successful build call is insufficient when its output is missing.
        with mock.patch.object(build, "build_binary", return_value=self.binary):
            with contextlib.redirect_stderr(io.StringIO()) as output:
                result = build.main([])

        # missing output must fail even when the build call itself succeeded.
        self.assertEqual(result, 1)
        self.assertIn("did not produce the expected binary", output.getvalue())

    def test_install_directory_requires_install(self) -> None:
        # reject destination options that would otherwise be silently ignored.
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                build.main(["--install-dir", str(self.root)])

        # invalid destination options must use the parser error status.
        self.assertEqual(error.exception.code, 2)

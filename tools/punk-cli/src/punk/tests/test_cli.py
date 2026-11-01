"""Tests for the punk command-line entry point."""

# builtin
import json
import pathlib
import tempfile
import unittest
from unittest import mock
import importlib.metadata

# third-party
from click import testing

# internal
from punk import cli
from punk import config


class CliTests(unittest.TestCase):
    """Exercise CLI configuration and setup without external effects."""

    def setUp(self) -> None:
        # isolate filesystem state and restore patches after each test.
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.config_dir = pathlib.Path(directory.name) / "punk"
        self.config_path = self.config_dir / "config.json"
        app_dir = mock.patch("punk.config.click.get_app_dir",
                             return_value=str(self.config_dir))
        app_dir.start()
        self.addCleanup(app_dir.stop)

    def test_version(self) -> None:
        # version lookup must not create application state.
        result = testing.CliRunner().invoke(cli.main, ["--version"])

        # metadata lookup must succeed without initializing config.
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(
            result.output,
            f"punk, version {importlib.metadata.version('punk-records')}\n")
        self.assertFalse(self.config_dir.exists())

    def test_help(self) -> None:
        # help must remain safe to request before configuration exists.
        result = testing.CliRunner().invoke(cli.main, ["--help"])

        # public help must not expose implementation docstring sections.
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--version", result.output)
        self.assertIn("config", result.output)
        self.assertIn("The punk command-line interface.", result.output)
        self.assertNotIn("Args:", result.output)
        self.assertFalse(self.config_dir.exists())

    def test_unknown_command_is_rejected(self) -> None:
        # reject unknown commands without creating configuration.
        result = testing.CliRunner().invoke(cli.main, ["unknown"])

        # invalid commands must fail before application state is created.
        self.assertEqual(result.exit_code, 2)
        self.assertIn("No such command", result.output)
        self.assertFalse(self.config_dir.exists())

    def test_init_defaults(self) -> None:
        # check the serialized defaults, not just command success.
        result = testing.CliRunner().invoke(cli.main, ["config", "init"])

        # persist all default fields with their json value types.
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(str(self.config_path), result.output)
        self.assertEqual(
            json.loads(self.config_path.read_text(encoding="utf-8")),
            {
                "management_tool": "ollama",
                "models": ["llama3.2"],
                "enable_web_interface": False,
                "enable_internet_access": False,
            },
        )

    def test_init_custom_settings(self) -> None:
        # repeated model options must retain their supplied order.
        result = testing.CliRunner().invoke(
            cli.main,
            [
                "config",
                "init",
                "--management-tool",
                "custom",
                "--model",
                "model-a",
                "--model",
                "model-b",
            ],
        )

        # custom values must replace defaults without reordering models.
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(
            json.loads(self.config_path.read_text(encoding="utf-8")),
            {
                "management_tool": "custom",
                "models": ["model-a", "model-b"],
                "enable_web_interface": False,
                "enable_internet_access": False,
            },
        )

    def test_startup_creates_defaults(self) -> None:
        # ordinary startup should initialize the same defaults as config init.
        result = testing.CliRunner().invoke(cli.main, [])

        # implicit and explicit startup must store identical defaults.
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(
            json.loads(self.config_path.read_text(encoding="utf-8")),
            {
                "management_tool": "ollama",
                "models": ["llama3.2"],
                "enable_web_interface": False,
                "enable_internet_access": False,
            },
        )

    def test_existing_config_is_preserved(self) -> None:
        # existing user settings must survive every non-forced startup path.
        self.config_dir.mkdir()
        original = '{"management_tool": "custom", "models": ["my-model"]}\n'
        self.config_path.write_text(original, encoding="utf-8")

        # exercise each startup path against the same preexisting config file.
        for args in (
            ["config", "init"],
            [
                "config", "init", "--enable-web-interface", "--model",
                "replacement"
            ],
            [
                "config", "init", "--enable-web-interface",
                "--enable-internet-access"
            ],
            [],
        ):
            with self.subTest(args=args):
                result = testing.CliRunner().invoke(cli.main, args)

                # non-forced commands must leave the original bytes intact.
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual(self.config_path.read_text(encoding="utf-8"),
                                 original)

    def test_force_replaces_entire_config_with_defaults(self) -> None:
        # forced defaults must also discard unknown keys and old settings.
        self.config_dir.mkdir()
        self.config_path.write_text(
            '{"management_tool": "custom", "models": ["old"], '
            '"enable_web_interface": true, "enable_internet_access": true, '
            '"extra": 1}',
            encoding="utf-8",
        )

        # force defaults over existing custom and unknown values.
        result = testing.CliRunner().invoke(cli.main,
                                            ["config", "init", "--force"])

        # replacement must drop unknown keys and clean temporary files.
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Wrote config", result.output)
        self.assertEqual(
            json.loads(self.config_path.read_text(encoding="utf-8")),
            {
                "management_tool": "ollama",
                "models": ["llama3.2"],
                "enable_web_interface": False,
                "enable_internet_access": False,
            },
        )
        self.assertEqual(list(self.config_dir.iterdir()), [self.config_path])

    def test_force_replaces_malformed_config_with_supplied_options(
            self) -> None:
        # replacement must not depend on parsing the previous configuration.
        self.config_dir.mkdir()
        self.config_path.write_text("{", encoding="utf-8")

        # replace invalid json using explicit model and web-interface options.
        result = testing.CliRunner().invoke(
            cli.main,
            [
                "config",
                "init",
                "--force",
                "--management-tool",
                "custom",
                "--model",
                "one",
                "--model",
                "two",
                "--enable-web-interface",
            ],
        )

        # new options must fully replace the malformed content.
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(
            json.loads(self.config_path.read_text(encoding="utf-8")),
            {
                "management_tool": "custom",
                "models": ["one", "two"],
                "enable_web_interface": True,
                "enable_internet_access": False,
            },
        )

    def test_force_creates_config_when_missing(self) -> None:
        # forcing creation must also work without a prior destination file.
        result = testing.CliRunner().invoke(cli.main,
                                            ["config", "init", "--force"])

        # forcing creation must yield a complete default configuration.
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(self.config_path.is_file())
        self.assertEqual(
            json.loads(self.config_path.read_text(encoding="utf-8"))["models"],
            ["llama3.2"],
        )

    def test_force_write_failure_preserves_config_and_cleans_up(self) -> None:
        # simulate a partial write before the atomic replacement can happen.
        self.config_dir.mkdir()
        original = '{"management_tool": "ollama", "models": ["old"]}\n'
        self.config_path.write_text(original, encoding="utf-8")
        factory = tempfile.NamedTemporaryFile

        def failing_file(*args, **kwargs):
            # interrupt the temporary write before the original can be replaced.
            temporary_file = factory(*args, **kwargs)
            temporary_file.write = mock.Mock(side_effect=OSError("Disk full"))

            return temporary_file

        # inject a disk failure before atomic replacement can occur.
        with mock.patch("punk.config.tempfile.NamedTemporaryFile",
                        side_effect=failing_file):
            result = testing.CliRunner().invoke(cli.main,
                                                ["config", "init", "--force"])

        # a partial write must retain the original and clean scratch data.
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Disk full", result.output)
        self.assertNotIn("Wrote config", result.output)
        self.assertEqual(self.config_path.read_text(encoding="utf-8"), original)
        self.assertEqual(list(self.config_dir.iterdir()), [self.config_path])

    def test_force_replace_failure_preserves_config_and_cleans_up(self) -> None:
        # a denied replacement must retain the original and clean scratch data.
        self.config_dir.mkdir()
        original = '{"management_tool": "ollama", "models": ["old"]}\n'
        self.config_path.write_text(original, encoding="utf-8")

        # deny the atomic replacement after the temporary file has been written.
        with mock.patch("punk.config.pathlib.Path.replace",
                        side_effect=PermissionError("Denied")):
            result = testing.CliRunner().invoke(cli.main,
                                                ["config", "init", "--force"])

        # failed replacement must retain the original and clean up.
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Denied", result.output)
        self.assertEqual(self.config_path.read_text(encoding="utf-8"), original)
        self.assertEqual(list(self.config_dir.iterdir()), [self.config_path])

    def test_force_invalid_options_preserve_config(self) -> None:
        # invalid forced options must fail before touching existing settings.
        self.config_dir.mkdir()
        original = '{"management_tool": "ollama", "models": ["old"]}\n'
        self.config_path.write_text(original, encoding="utf-8")

        # force must not bypass model-name validation.
        result = testing.CliRunner().invoke(
            cli.main, ["config", "init", "--force", "--model", " "])

        # invalid options must leave existing settings unchanged.
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(self.config_path.read_text(encoding="utf-8"), original)

    def test_force_rejects_directory_at_config_path(self) -> None:
        # never treat an existing directory as replaceable config data.
        self.config_path.mkdir(parents=True)

        # attempt replacement without removing the existing directory.
        result = testing.CliRunner().invoke(cli.main,
                                            ["config", "init", "--force"])

        # failed replacement must retain the directory and clean up.
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Could not initialize config", result.output)
        self.assertTrue(self.config_path.is_dir())
        self.assertEqual(list(self.config_dir.iterdir()), [self.config_path])

    def test_config_web_interface_flag(self) -> None:
        # verify that a persisted web-interface option reaches setup.
        result = testing.CliRunner().invoke(
            cli.main, ["config", "init", "--enable-web-interface"])

        # the stored web-interface setting must be a boolean, not a string.
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIs(
            json.loads(self.config_path.read_text(
                encoding="utf-8"))["enable_web_interface"],
            True,
        )
        with mock.patch("punk.cli.setup.setup") as setup:
            result = testing.CliRunner().invoke(cli.main, ["init"])
        self.assertEqual(result.exit_code, 0, result.output)
        setup.assert_called_once_with(
            config.AppConfig("ollama", ("llama3.2",), True))

    def test_explicit_disable_web_interface_flag(self) -> None:
        # serialize the disabled flag as a boolean rather than a string.
        result = testing.CliRunner().invoke(
            cli.main, ["config", "init", "--disable-web-interface"])

        # an explicit disable option must serialize as the json false value.
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIs(
            json.loads(self.config_path.read_text(
                encoding="utf-8"))["enable_web_interface"],
            False,
        )

    def test_internet_access_flag_and_setup(self) -> None:
        # verify that saved search settings reach the setup boundary.
        result = testing.CliRunner().invoke(
            cli.main,
            [
                "config", "init", "--enable-web-interface",
                "--enable-internet-access"
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIs(
            json.loads(self.config_path.read_text(
                encoding="utf-8"))["enable_internet_access"],
            True,
        )
        with mock.patch("punk.cli.setup.setup") as setup:
            result = testing.CliRunner().invoke(cli.main, ["init"])
        self.assertEqual(result.exit_code, 0, result.output)
        setup.assert_called_once_with(
            config.AppConfig("ollama", ("llama3.2",), True, True))

    def test_force_enables_and_disables_internet_access(self) -> None:
        # both boolean flag directions must replace the saved search setting.
        for flag, enabled in (
            ("--enable-internet-access", True),
            ("--disable-internet-access", False),
        ):
            with self.subTest(flag=flag):
                result = testing.CliRunner().invoke(cli.main, [
                    "config", "init", "--force", "--enable-web-interface", flag
                ])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIs(
                    json.loads(self.config_path.read_text(
                        encoding="utf-8"))["enable_internet_access"],
                    enabled,
                )

    def test_internet_access_requires_web_interface_without_writing(
            self) -> None:
        # invalid search options must not create or replace configuration.
        result = testing.CliRunner().invoke(
            cli.main, ["config", "init", "--enable-internet-access"])
        self.assertEqual(result.exit_code, 2)
        self.assertIn("requires --enable-web-interface", result.output)
        self.assertFalse(self.config_path.exists())

        # repeat invalid search options after creating a valid existing config.
        testing.CliRunner().invoke(cli.main, ["config", "init"])
        original = self.config_path.read_bytes()
        result = testing.CliRunner().invoke(
            cli.main, ["config", "init", "--force", "--enable-internet-access"])
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(self.config_path.read_bytes(), original)

    def test_legacy_webui_config_defaults_internet_access_to_disabled(
            self) -> None:
        # legacy configuration must stay byte-for-byte unchanged after loading.
        self.config_dir.mkdir()
        original = json.dumps({
            "management_tool": "ollama",
            "models": ["model"],
            "enable_web_interface": True,
        })
        self.config_path.write_text(original, encoding="utf-8")
        with mock.patch("punk.cli.setup.setup") as setup:
            result = testing.CliRunner().invoke(cli.main, ["init"])
        self.assertEqual(result.exit_code, 0, result.output)
        setup.assert_called_once_with(
            config.AppConfig("ollama", ("model",), True, False))
        self.assertEqual(self.config_path.read_text(encoding="utf-8"), original)

    def test_config_help_does_not_initialize(self) -> None:
        # nested help commands must not initialize configuration either.
        for args in (
            ["config"],
            ["config", "--help"],
            ["config", "init", "--help"],
            ["config", "init", "--force", "--help"],
            ["config", "init", "--enable-internet-access", "--help"],
        ):
            with self.subTest(args=args):
                result = testing.CliRunner().invoke(cli.main, args)

                # help must not write config or expose implementation details.
                self.assertIn("Usage:", result.output)
                self.assertNotIn("Args:", result.output)
                self.assertFalse(self.config_dir.exists())

    def test_init_reports_filesystem_error(self) -> None:
        # surface permission failures instead of reporting successful creation.
        with mock.patch("punk.config.pathlib.Path.mkdir",
                        side_effect=PermissionError("Permission denied")):
            result = testing.CliRunner().invoke(cli.main, ["config", "init"])

        # filesystem failures must retain their diagnostic detail.
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Could not initialize config", result.output)
        self.assertIn("Permission denied", result.output)

    def test_init_rejects_directory_at_config_path(self) -> None:
        # exclusive creation must not overwrite an existing directory.
        self.config_path.mkdir(parents=True)

        # exclusive creation must fail without modifying the existing directory.
        result = testing.CliRunner().invoke(cli.main, ["config", "init"])

        # an existing directory must cause failure, not claimed success.
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Error:", result.output)

    def test_init_rejects_blank_names(self) -> None:
        # reject whitespace-only options before creating the config directory.
        for option in ("--management-tool", "--model"):
            with self.subTest(option=option):
                result = testing.CliRunner().invoke(
                    cli.main, ["config", "init", option, " "])

                # reject blank options without creating config directories.
                self.assertEqual(result.exit_code, 2)
                self.assertIn("must not be blank", result.output)
                self.assertFalse(self.config_dir.exists())

    def test_setup_creates_and_uses_default_config(self) -> None:
        # intercept setup to verify defaults without contacting external tools.
        with mock.patch("punk.cli.setup.setup") as setup:
            result = testing.CliRunner().invoke(cli.main, ["init"])

        # setup must receive the same defaults that were persisted to disk.
        self.assertEqual(result.exit_code, 0, result.output)
        setup.assert_called_once_with(config.AppConfig("ollama", ("llama3.2",)))
        self.assertTrue(self.config_path.is_file())

    def test_setup_uses_saved_config(self) -> None:
        # setup must consume saved models without rewriting their source file.
        self.config_dir.mkdir()
        original = '{"management_tool": "ollama", "models": ["one", "two"]}\n'
        self.config_path.write_text(original, encoding="utf-8")
        with mock.patch("punk.cli.setup.setup") as setup:
            result = testing.CliRunner().invoke(cli.main, ["init"])

        # setup must retain saved models and leave their file unchanged.
        self.assertEqual(result.exit_code, 0, result.output)
        setup.assert_called_once_with(config.AppConfig("ollama",
                                                       ("one", "two")))
        self.assertEqual(self.config_path.read_text(encoding="utf-8"), original)

    def test_setup_help_does_not_initialize(self) -> None:
        # setup help must not create config or invoke the setup implementation.
        with mock.patch("punk.cli.setup.setup") as setup:
            result = testing.CliRunner().invoke(cli.main, ["init", "--help"])

        # setup help must retain its public wording without triggering setup.
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(
            "Set up models and the optional web interface from "
            "application configuration.",
            " ".join(result.output.split()),
        )
        self.assertNotIn("Args:", result.output)
        self.assertFalse(self.config_dir.exists())
        setup.assert_not_called()

    def test_setup_rejects_invalid_config_before_side_effects(self) -> None:
        # exercise malformed shapes and values before any setup operation runs.
        self.config_dir.mkdir()
        invalid_configs = (
            "{",
            "[]",
            "{}",
            '{"management_tool": 42, "models": ["one"]}',
            '{"management_tool": " ", "models": ["one"]}',
            '{"management_tool": "ollama", "models": []}',
            '{"management_tool": "ollama", "models": "one"}',
            '{"management_tool": "ollama", "models": [" "]}',
            '{"management_tool": "ollama", "models": [1]}',
            '{"management_tool": "ollama", "models": ["one"], '
            '"enable_web_interface": "true"}',
            '{"management_tool": "ollama", "models": ["one"], '
            '"enable_web_interface": 1}',
            '{"management_tool": "ollama", "models": ["one"], '
            '"enable_web_interface": null}',
            '{"management_tool": "ollama", "models": ["one"], '
            '"enable_internet_access": "true"}',
            '{"management_tool": "ollama", "models": ["one"], '
            '"enable_internet_access": 1}',
            '{"management_tool": "ollama", "models": ["one"], '
            '"enable_internet_access": null}',
            '{"management_tool": "ollama", "models": ["one"], '
            '"enable_internet_access": true}',
        )
        for content in invalid_configs:
            with self.subTest(content=content):
                self.config_path.write_text(content, encoding="utf-8")
                with mock.patch("punk.cli.setup.setup") as setup:
                    result = testing.CliRunner().invoke(cli.main, ["init"])

                # invalid config must remain untouched and never reach setup.
                self.assertEqual(result.exit_code, 1, result.output)
                self.assertIn(str(self.config_path), result.output)
                setup.assert_not_called()
                self.assertEqual(self.config_path.read_text(encoding="utf-8"),
                                 content)

    def test_setup_reports_config_read_error(self) -> None:
        # valid destination paths can still have unreadable contents.
        with mock.patch("punk.config.pathlib.Path.read_text",
                        side_effect=PermissionError("Denied")):
            result = testing.CliRunner().invoke(cli.main, ["init"])

        # reading failures must produce an explicit initialization error.
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Could not read config", result.output)

    def test_setup_rejects_unsupported_tool(self) -> None:
        # unsupported managers must fail before executable discovery begins.
        self.config_dir.mkdir()
        self.config_path.write_text(
            '{"management_tool": "custom", "models": ["one"]}',
            encoding="utf-8")
        with mock.patch("punk.setup.shutil.which") as which:
            result = testing.CliRunner().invoke(cli.main, ["init"])

        # unsupported managers must fail before executable discovery.
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Only 'ollama' is supported", result.output)
        which.assert_not_called()

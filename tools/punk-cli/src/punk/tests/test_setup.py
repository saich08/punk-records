"""Tests for model setup and managed Open WebUI."""

# builtin
import io
import pathlib
import tempfile
import unittest
import contextlib
import subprocess
import urllib.error
from unittest import mock

# third-party
import click

# internal
from punk import setup
from punk import config


class SetupTests(unittest.TestCase):
    """Exercise model installation and server lifecycle boundaries."""

    def test_existing_ollama_pulls_all_configured_models(self) -> None:
        # mock external tools while preserving the ordered model-pull contract.
        with mock.patch.object(setup.shutil,
                               "which",
                               return_value="/bin/ollama"):
            with mock.patch.object(setup, "install_ollama") as install:
                with mock.patch.object(setup, "ensure_server") as server:
                    with mock.patch.object(setup, "run_command") as run:
                        with contextlib.redirect_stdout(io.StringIO()):
                            setup.setup(
                                config.AppConfig("ollama", ("one", "two")))

        # reuse the installed tool and retain the configured model-pull order.
        install.assert_not_called()
        server.assert_called_once_with("/bin/ollama")
        self.assertEqual(
            run.call_args_list,
            [
                mock.call(["/bin/ollama", "pull", "--", "one"],
                          "Pulling model 'one'"),
                mock.call(["/bin/ollama", "pull", "--", "two"],
                          "Pulling model 'two'"),
            ],
        )

    def test_missing_ollama_is_installed_before_setup(self) -> None:
        # subsequent setup steps must use the newly installed executable.
        with mock.patch.object(setup.shutil, "which", return_value=None):
            with mock.patch.object(setup,
                                   "install_ollama",
                                   return_value="/bin/ollama") as install:
                with mock.patch.object(setup, "ensure_server") as server:
                    with mock.patch.object(setup, "run_command") as run:
                        with contextlib.redirect_stdout(io.StringIO()):
                            setup.setup(config.AppConfig("ollama", ("one",)))

        # server startup and model pulls must use the installed executable.
        install.assert_called_once_with()
        server.assert_called_once_with("/bin/ollama")
        run.assert_called_once_with(["/bin/ollama", "pull", "--", "one"],
                                    "Pulling model 'one'")

    def test_model_failure_stops_setup(self) -> None:
        # a failed pull must prevent later pulls and the completion message.
        with mock.patch.object(setup.shutil,
                               "which",
                               return_value="/bin/ollama"):
            with mock.patch.object(setup, "ensure_server"):
                with mock.patch.object(
                        setup.subprocess,
                        "run",
                        side_effect=subprocess.CalledProcessError(
                            1, "pull")) as run:
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        with self.assertRaisesRegex(
                                click.ClickException,
                                "Pulling model 'one' failed"):
                            setup.setup(
                                config.AppConfig("ollama", ("one", "two")))

        # a failed pull must suppress later pulls and the completion message.
        run.assert_called_once()
        self.assertNotIn("setup complete", output.getvalue())

    def test_missing_executable_error_is_explicit(self) -> None:
        # convert process-launch errors into actionable cli failures.
        with mock.patch.object(setup.subprocess,
                               "run",
                               side_effect=FileNotFoundError("missing")):
            with self.assertRaisesRegex(click.ClickException,
                                        "failed: missing"):
                setup.run_command(["missing"], "Test")

    def test_installer_downloads_official_script_and_cleans_up(self) -> None:
        # keep the installer local to a temporary directory that is cleaned up.
        response = io.BytesIO(b"#!/bin/sh\n")
        with mock.patch.object(setup.sys, "platform", "linux"):
            with mock.patch.object(setup.urllib.request,
                                   "urlopen",
                                   return_value=response) as download:
                with mock.patch.object(setup.shutil,
                                       "which",
                                       return_value="/bin/ollama"):
                    with mock.patch.object(setup, "run_command") as run:
                        with contextlib.redirect_stdout(io.StringIO()):
                            executable = setup.install_ollama()

        # use the official installer and remove its temporary directory.
        self.assertEqual(executable, "/bin/ollama")
        download.assert_called_once_with("https://ollama.com/install.sh",
                                         timeout=60)
        command = run.call_args.args[0]
        self.assertEqual(command[0], "sh")
        self.assertFalse(pathlib.Path(command[1]).parent.exists())

    def test_installer_download_failure_is_reported(self) -> None:
        # an offline download must not attempt to execute a missing installer.
        with mock.patch.object(setup.sys, "platform", "linux"):
            with mock.patch.object(
                    setup.urllib.request,
                    "urlopen",
                    side_effect=urllib.error.URLError("offline")):
                with mock.patch.object(setup, "run_command") as run:
                    with contextlib.redirect_stdout(io.StringIO()):
                        with self.assertRaisesRegex(click.ClickException,
                                                    "offline"):
                            setup.install_ollama()

        # failed downloads must not invoke an installer command.
        run.assert_not_called()

    def test_installer_failure_stops_setup(self) -> None:
        # failed installation must prevent server startup.
        with mock.patch.object(setup.shutil, "which", return_value=None):
            with mock.patch.object(
                    setup,
                    "install_ollama",
                    side_effect=click.ClickException("install failed")):
                with mock.patch.object(setup, "ensure_server") as server:
                    with self.assertRaisesRegex(click.ClickException,
                                                "install failed"):
                        setup.setup(config.AppConfig("ollama", ("one",)))

        # installation failure must prevent any server startup attempt.
        server.assert_not_called()

    def test_installer_reports_missing_binary_after_install(self) -> None:
        # successful script execution alone does not establish a usable install.
        with mock.patch.object(setup.sys, "platform", "linux"):
            with mock.patch.object(setup.urllib.request,
                                   "urlopen",
                                   return_value=io.BytesIO(b"script")):
                with mock.patch.object(setup, "run_command"):
                    with mock.patch.object(setup.shutil,
                                           "which",
                                           return_value=None):
                        with contextlib.redirect_stdout(io.StringIO()):
                            with self.assertRaisesRegex(click.ClickException,
                                                        "not on PATH"):
                                setup.install_ollama()

    def test_unsupported_install_platform_has_actionable_error(self) -> None:
        # unsupported platforms should receive the manual download location.
        with mock.patch.object(setup.sys, "platform", "darwin"):
            with self.assertRaisesRegex(click.ClickException,
                                        "https://ollama.com/download"):
                setup.install_ollama()

    def test_running_server_is_reused(self) -> None:
        # a responsive server must not cause another process to be launched.
        with mock.patch.object(setup, "server_status", return_value=(True, "")):
            with mock.patch.object(setup.subprocess, "Popen") as start:
                setup.ensure_server("/bin/ollama")

        # a successful readiness probe must not spawn a replacement server.
        start.assert_not_called()

    def test_server_status_checks_and_timeout(self) -> None:
        # both unsuccessful probes and timeouts must retain useful diagnostics.
        with mock.patch.object(setup.subprocess,
                               "run",
                               return_value=mock.Mock(returncode=1,
                                                      stderr="offline",
                                                      stdout="")) as run:
            self.assertEqual(setup.server_status("/bin/ollama", 5),
                             (False, "offline"))
        self.assertEqual(run.call_args.args[0], ["/bin/ollama", "list"])
        with mock.patch.object(setup.subprocess,
                               "run",
                               side_effect=subprocess.TimeoutExpired(
                                   "ollama", 5)):
            ready, error = setup.server_status("/bin/ollama", 5)
        self.assertFalse(ready)
        self.assertIn("Timed out", error)

    def test_stopped_server_starts_and_waits_until_ready(self) -> None:
        # startup must retain a log and leave a ready server running.
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(setup.app_config,
                                   "get_config_path",
                                   return_value=pathlib.Path(directory) /
                                   "config.json"):
                with mock.patch.object(setup,
                                       "server_status",
                                       side_effect=[(False, "offline"),
                                                    (True, "")]):
                    with mock.patch.object(setup.subprocess, "Popen") as start:
                        with contextlib.redirect_stdout(io.StringIO()):
                            setup.ensure_server("/bin/ollama")

            # startup logs must exist before their temporary path disappears.
            self.assertTrue((pathlib.Path(directory) / "ollama.log").is_file())
        self.assertEqual(start.call_args.args[0], ["/bin/ollama", "serve"])
        self.assertTrue(start.call_args.kwargs["start_new_session"])
        start.return_value.terminate.assert_not_called()

    def test_server_exit_is_reported_with_log_path(self) -> None:
        # an early process exit must direct the user to the startup log.
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(setup.app_config,
                                   "get_config_path",
                                   return_value=pathlib.Path(directory) /
                                   "config.json"):
                with mock.patch.object(setup,
                                       "server_status",
                                       return_value=(False, "offline")):
                    with mock.patch.object(setup.subprocess, "Popen") as start:
                        start.return_value.poll.return_value = 1
                        with contextlib.redirect_stdout(io.StringIO()):
                            with self.assertRaisesRegex(click.ClickException,
                                                        "ollama.log"):
                                setup.ensure_server("/bin/ollama")

    def test_server_timeout_terminates_only_the_started_process(self) -> None:
        # the startup deadline must clean up only the process it created.
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(setup.app_config,
                                   "get_config_path",
                                   return_value=pathlib.Path(directory) /
                                   "config.json"):
                with mock.patch.object(setup,
                                       "server_status",
                                       return_value=(False, "offline")):
                    with mock.patch.object(setup.time,
                                           "monotonic",
                                           side_effect=[0, 31]):
                        with mock.patch.object(setup.subprocess,
                                               "Popen") as start:
                            start.return_value.poll.return_value = None
                            with contextlib.redirect_stdout(io.StringIO()):
                                with self.assertRaisesRegex(
                                        click.ClickException,
                                        "Could not start Ollama"):
                                    setup.ensure_server("/bin/ollama")

        # timeout cleanup must target the new process and wait for its exit.
        start.return_value.terminate.assert_called_once_with()
        start.return_value.wait.assert_called_once_with(timeout=5)

    def test_frozen_binary_restores_external_library_environment(self) -> None:
        # external programs must not inherit the standalone bundle's libraries.
        with mock.patch.object(setup.sys, "frozen", True, create=True):
            with mock.patch.dict(
                    setup.os.environ,
                {
                    "LD_LIBRARY_PATH": "/bundle",
                    "LD_LIBRARY_PATH_ORIG": "/original"
                },
                    clear=True,
            ):
                self.assertEqual(setup.command_env(),
                                 {"LD_LIBRARY_PATH": "/original"})
            with mock.patch.dict(setup.os.environ,
                                 {"LD_LIBRARY_PATH": "/bundle"},
                                 clear=True):
                self.assertEqual(setup.command_env(), {})


class WebUISetupTests(unittest.TestCase):
    """Exercise managed container settings and readiness."""

    def setUp(self) -> None:
        # replace docker calls and isolate host environment settings.
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.dict(setup.os.environ, {}, clear=True))
        self.output = stack.enter_context(
            contextlib.redirect_stdout(io.StringIO()))
        self.run = stack.enter_context(mock.patch.object(setup, "run_command"))
        self.run.return_value = subprocess.CompletedProcess([],
                                                            0,
                                                            stdout="",
                                                            stderr="")
        self.inspect = stack.enter_context(
            mock.patch.object(setup, "inspect_webui"))
        self.inspect.return_value = self.container()

    def container(self) -> dict[str, object]:
        # model the ownership and storage contract required for reuse.
        return {
            "Config": {
                "Labels": {
                    setup.WEBUI_LABEL: "true"
                },
                "Image":
                    setup.WEBUI_IMAGE,
                "Env":
                    setup.webui_environment() + [
                        "ENABLE_WEB_SEARCH=false",
                        "WEB_SEARCH_ENGINE=duckduckgo",
                        "ENABLE_PERSISTENT_CONFIG=false",
                    ],
            },
            "HostConfig": {
                "NetworkMode": "host"
            },
            "Mounts": [{
                "Type": "volume",
                "Name": setup.WEBUI_CONTAINER,
                "Destination": "/app/backend/data",
            }],
            "State": {
                "Running": True,
                "Health": {
                    "Status": "healthy"
                }
            },
        }

    def test_disabled_skips_docker_and_webui(self) -> None:
        # disabled web integration must not require docker or touch containers.
        with mock.patch.object(setup.shutil,
                               "which",
                               return_value="/bin/ollama"):
            with mock.patch.object(setup, "ensure_server"):
                with mock.patch.object(setup, "require_docker") as docker:
                    with mock.patch.object(setup, "ensure_webui") as webui:
                        setup.setup(config.AppConfig("ollama", ("model",)))

        # disabled integration must not perform either docker or web setup.
        docker.assert_not_called()
        webui.assert_not_called()

    def test_enabled_configures_webui_after_models(self) -> None:
        # observe the model pull at the exact moment web setup starts.
        with mock.patch.object(setup.shutil,
                               "which",
                               return_value="/bin/ollama"):
            with mock.patch.object(setup, "ensure_server"):
                with mock.patch.object(setup,
                                       "require_docker",
                                       return_value="/bin/docker"):
                    with mock.patch.object(setup, "ensure_webui") as webui:
                        webui.side_effect = lambda _, **_kw: self.assertEqual(
                            self.run.call_args.args[0],
                            ["/bin/ollama", "pull", "--", "model"])
                        setup.setup(config.AppConfig("ollama", ("model",),
                                                     True))

        # pass the docker path while retaining disabled search by default.
        webui.assert_called_once_with("/bin/docker",
                                      enable_internet_access=False)
        self.assertIn("setup complete", self.output.getvalue())

    def test_webui_failure_does_not_report_setup_complete(self) -> None:
        # overall completion must not hide a web-interface startup failure.
        with mock.patch.object(setup.shutil,
                               "which",
                               return_value="/bin/ollama"):
            with mock.patch.object(setup, "ensure_server"):
                with mock.patch.object(setup,
                                       "require_docker",
                                       return_value="/bin/docker"):
                    with mock.patch.object(
                            setup,
                            "ensure_webui",
                            side_effect=click.ClickException("failed")):
                        with self.assertRaisesRegex(click.ClickException,
                                                    "failed"):
                            setup.setup(
                                config.AppConfig("ollama", ("model",), True))

        # a failed web startup must not produce an overall completion message.
        self.assertNotIn("setup complete", self.output.getvalue())

    def test_model_failure_does_not_start_webui(self) -> None:
        # web startup depends on all configured models being available.
        self.run.side_effect = click.ClickException("pull failed")
        with mock.patch.object(setup.shutil,
                               "which",
                               return_value="/bin/ollama"):
            with mock.patch.object(setup, "ensure_server"):
                with mock.patch.object(setup,
                                       "require_docker",
                                       return_value="/bin/docker"):
                    with mock.patch.object(setup, "ensure_webui") as webui:
                        with self.assertRaisesRegex(click.ClickException,
                                                    "pull failed"):
                            setup.setup(
                                config.AppConfig("ollama", ("model",), True))

        # model-pull failure must prevent any web-interface startup attempt.
        webui.assert_not_called()

    def test_missing_docker_has_actionable_error(self) -> None:
        # missing docker should explain how to install it or disable web setup.
        with mock.patch.object(setup.shutil, "which", return_value=None):
            with self.assertRaisesRegex(click.ClickException, "Install Docker"):
                setup.require_docker()

    def test_docker_preflight_checks_daemon(self) -> None:
        # an executable on the path is insufficient without daemon access.
        with mock.patch.object(setup.shutil,
                               "which",
                               return_value="/bin/docker"):
            self.assertEqual(setup.require_docker(), "/bin/docker")

        # preflight must check daemon access with a bounded captured command.
        self.run.assert_called_once_with(
            ["/bin/docker", "info"],
            "Checking Docker (ensure its daemon is running and accessible)",
            capture_output=True,
            timeout=10,
        )

    def test_docker_failure_prevents_ollama_setup(self) -> None:
        # fail docker preflight before model setup can introduce side effects.
        with mock.patch.object(
                setup,
                "require_docker",
                side_effect=click.ClickException("daemon offline")):
            with mock.patch.object(setup, "ensure_server") as server:
                with self.assertRaisesRegex(click.ClickException,
                                            "daemon offline"):
                    setup.setup(config.AppConfig("ollama", ("model",), True))

        # failed preflight must prevent both server startup and model commands.
        server.assert_not_called()
        self.run.assert_not_called()

    def test_new_container_has_local_bind_storage_and_ollama(self) -> None:
        # inspect actual docker arguments for local access and persistent data.
        setup.ensure_webui("/bin/docker")

        # check actual container arguments for networking, storage, and secrets.
        command = self.run.call_args_list[1].args[0]
        self.assertEqual(command[:3], ["/bin/docker", "run", "--detach"])
        self.assertEqual(command[command.index("--network") + 1], "host")
        self.assertEqual(command[command.index("--volume") + 1],
                         "punk-open-webui:/app/backend/data")
        self.assertIn("HOST=127.0.0.1", command)
        self.assertIn("PORT=8080", command)
        self.assertIn("OLLAMA_BASE_URL=http://127.0.0.1:11434", command)
        self.assertIn(
            "WEBUI_SECRET_KEY_FILE=/app/backend/data/.webui_secret_key",
            command)
        self.assertIn("unless-stopped", command)
        self.assertEqual(command[-1], setup.WEBUI_IMAGE)
        self.assertIn("http://127.0.0.1:8080", self.output.getvalue())

    def test_existing_container_is_reused(self) -> None:
        # a matching healthy container must not trigger any creation command.
        self.run.return_value.stdout = "existing-id"

        # inspect the existing managed container without changing its settings.
        setup.ensure_webui("/bin/docker")

        # matching containers need inspection but no modifying commands.
        self.run.assert_called_once()
        self.assertEqual(self.inspect.call_count, 2)

    def test_internet_access_requires_webui_before_side_effects(self) -> None:
        # validate the option dependency even when setup bypasses the cli.
        with mock.patch.object(setup, "require_docker") as docker:
            with self.assertRaisesRegex(click.ClickException,
                                        "requires enable_web_interface"):
                setup.setup(config.AppConfig("ollama", ("model",), False, True))
        docker.assert_not_called()
        self.run.assert_not_called()

    def test_internet_access_is_passed_to_webui_setup(self) -> None:
        # the saved search flag must reach the container setup boundary.
        with mock.patch.object(setup.shutil,
                               "which",
                               return_value="/bin/ollama"):
            with mock.patch.object(setup, "ensure_server"):
                with mock.patch.object(setup,
                                       "require_docker",
                                       return_value="/bin/docker"):
                    with mock.patch.object(setup, "ensure_webui") as webui:
                        setup.setup(
                            config.AppConfig("ollama", ("model",), True, True))
        webui.assert_called_once_with("/bin/docker",
                                      enable_internet_access=True)

    def test_search_environment_enabled_and_disabled(self) -> None:
        # both search states must override persisted web-interface settings.
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                self.run.reset_mock()
                setup.ensure_webui("/bin/docker",
                                   enable_internet_access=enabled)
                command = self.run.call_args_list[1].args[0]
                self.assertIn(f"ENABLE_WEB_SEARCH={str(enabled).lower()}",
                              command)
                self.assertIn("WEB_SEARCH_ENGINE=duckduckgo", command)
                self.assertIn("ENABLE_PERSISTENT_CONFIG=false", command)

    def test_search_changes_recreate_container_without_deleting_data(
            self) -> None:
        # search changes may recreate the container but never its data volume.
        for previous, enabled in ((None, False), (None, True), (False, True),
                                  (True, False)):
            with self.subTest(previous=previous, enabled=enabled):
                self.run.reset_mock()
                self.run.return_value.stdout = "existing-id"
                existing = self.container()
                existing["Config"]["Env"] = setup.webui_environment()
                if previous is not None:
                    existing["Config"]["Env"] += [
                        f"ENABLE_WEB_SEARCH={str(previous).lower()}",
                        "WEB_SEARCH_ENGINE=duckduckgo",
                        "ENABLE_PERSISTENT_CONFIG=false",
                    ]
                self.inspect.return_value = existing
                setup.ensure_webui("/bin/docker",
                                   enable_internet_access=enabled)
                commands = [entry.args[0] for entry in self.run.call_args_list]
                self.assertEqual(commands[1],
                                 ["/bin/docker", "stop", setup.WEBUI_CONTAINER])
                self.assertEqual(commands[2],
                                 ["/bin/docker", "rm", setup.WEBUI_CONTAINER])
                self.assertIn("punk-open-webui:/app/backend/data", commands[3])
                self.assertIn(f"ENABLE_WEB_SEARCH={str(enabled).lower()}",
                              commands[3])
                self.assertNotIn("--volumes", commands[2])
                self.assertNotIn("-v", commands[2])

    def test_matching_search_enabled_container_is_reused(self) -> None:
        # matching enabled search settings must not cause needless recreation.
        self.run.return_value.stdout = "existing-id"
        container = self.container()
        container["Config"]["Env"][4] = "ENABLE_WEB_SEARCH=true"
        self.inspect.return_value = container
        setup.ensure_webui("/bin/docker", enable_internet_access=True)
        self.run.assert_called_once()

    def test_reconfiguration_failure_does_not_create_another_container(
            self) -> None:
        # a failed stop must halt reconfiguration before container creation.
        self.run.side_effect = [
            subprocess.CompletedProcess([], 0, stdout="existing-id"),
            click.ClickException("stop failed"),
        ]
        with self.assertRaisesRegex(click.ClickException, "stop failed"):
            setup.ensure_webui("/bin/docker", enable_internet_access=True)
        self.assertEqual(self.run.call_count, 2)

    def test_search_change_does_not_replace_unmanaged_container(self) -> None:
        # search changes must not authorize replacing unrelated containers.
        self.run.return_value.stdout = "existing-id"
        existing = self.container()
        existing["Config"]["Labels"] = {}
        self.inspect.return_value = existing
        with self.assertRaisesRegex(click.ClickException, "will not replace"):
            setup.ensure_webui("/bin/docker", enable_internet_access=True)
        self.run.assert_called_once()

    def test_recreation_failure_does_not_remove_persistent_volume(self) -> None:
        # failed recreation must preserve the old named volume for recovery.
        self.run.side_effect = [
            subprocess.CompletedProcess([], 0, stdout="existing-id"),
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0),
            click.ClickException("creation failed"),
        ]
        with self.assertRaisesRegex(click.ClickException, "creation failed"):
            setup.ensure_webui("/bin/docker", enable_internet_access=True)
        commands = [entry.args[0] for entry in self.run.call_args_list]
        self.assertEqual(commands[2],
                         ["/bin/docker", "rm", setup.WEBUI_CONTAINER])
        self.assertIn("punk-open-webui:/app/backend/data", commands[3])
        self.assertNotIn("is ready", self.output.getvalue())

    def test_stopped_container_is_started(self) -> None:
        # a compatible stopped container should be started rather than replaced.
        self.run.return_value.stdout = "existing-id"
        stopped = self.container()
        stopped["State"] = {"Running": False}
        self.inspect.side_effect = [stopped, self.container()]

        # exercise the matching-container restart path rather than creation.
        setup.ensure_webui("/bin/docker")

        # restart the matching container without replacing its state.
        self.assertEqual(
            self.run.call_args_list[1],
            mock.call(["/bin/docker", "start", setup.WEBUI_CONTAINER],
                      "Starting Open WebUI"),
        )

    def test_conflicting_container_is_never_replaced(self) -> None:
        # ownership, network, storage, and image conflicts must all block reuse.
        self.run.return_value.stdout = "existing-id"
        for field, replacement in (
            ("Config", {
                "Labels": {},
                "Image": setup.WEBUI_IMAGE,
                "Env": setup.webui_environment()
            }),
            ("HostConfig", {
                "NetworkMode": "bridge"
            }),
            ("Mounts", []),
            ("Config", {
                "Labels": {
                    setup.WEBUI_LABEL: "true"
                },
                "Image": "other",
                "Env": []
            }),
        ):
            with self.subTest(field=field, replacement=replacement):
                container = self.container()
                container[field] = replacement
                self.inspect.return_value = container
                self.run.reset_mock()
                with self.assertRaisesRegex(click.ClickException,
                                            "will not replace"):
                    setup.ensure_webui("/bin/docker")
                self.run.assert_called_once()

    def test_waits_for_health_before_reporting_ready(self) -> None:
        # a running container is not ready until its health check succeeds.
        starting = self.container()
        starting["State"] = {"Running": True, "Health": {"Status": "starting"}}
        self.inspect.side_effect = [starting, self.container()]
        with mock.patch.object(setup.time, "sleep"):
            setup.ensure_webui("/bin/docker")

        # report readiness only after the healthy probe succeeds.
        self.assertEqual(self.inspect.call_count, 2)
        self.assertIn("is ready", self.output.getvalue())

    def test_stopped_or_unhealthy_container_reports_logs(self) -> None:
        # failed readiness should point to container logs instead of success.
        for state in (
            {
                "Running": False
            },
            {
                "Running": True,
                "Health": {
                    "Status": "unhealthy"
                }
            },
        ):
            with self.subTest(state=state):
                container = self.container()
                container["State"] = state
                self.inspect.return_value = container
                with self.assertRaisesRegex(click.ClickException,
                                            "docker logs punk-open-webui"):
                    setup.ensure_webui("/bin/docker")

        # neither stopped nor unhealthy states may produce a readiness message.
        self.assertNotIn("is ready", self.output.getvalue())

    def test_paused_container_is_not_reported_ready(self) -> None:
        # a paused container is unusable even if its last health check passed.
        container = self.container()
        container["State"] = {
            "Running": True,
            "Paused": True,
            "Health": {
                "Status": "healthy"
            }
        }
        self.inspect.return_value = container

        # a stale healthy result must not override the paused state.
        with self.assertRaisesRegex(click.ClickException, "docker unpause"):
            setup.ensure_webui("/bin/docker")

    def test_health_timeout_is_explicit(self) -> None:
        # advance the clock without sleeping to exercise the readiness deadline.
        with mock.patch.object(setup.time, "monotonic", side_effect=[0, 121]):
            with self.assertRaisesRegex(click.ClickException, "120 seconds"):
                setup.ensure_webui("/bin/docker")

        # exceeding the deadline must never report the web interface as ready.
        self.assertNotIn("is ready", self.output.getvalue())

    def test_docker_errors_do_not_fall_back_to_container_creation(self) -> None:
        # inspection failures must not be mistaken for an absent container.
        self.run.side_effect = click.ClickException("Docker failure")

        # propagate lookup failure rather than assume container absence.
        with self.assertRaisesRegex(click.ClickException, "Docker failure"):
            setup.ensure_webui("/bin/docker")

        # a failed lookup must halt setup before any container creation command.
        self.run.assert_called_once()

    def test_ollama_host_settings(self) -> None:
        # normalize shorthand and wildcard addresses into reachable endpoints.
        for host, expected in (
            ("localhost:12345", "http://localhost:12345"),
            ("http://0.0.0.0:11434", "http://127.0.0.1:11434"),
            ("http://[::]:11434", "http://[::1]:11434"),
            ("https://remote.example:443", "https://remote.example:443"),
            (":11435", "http://127.0.0.1:11435"),
        ):
            with self.subTest(host=host):
                with mock.patch.dict(setup.os.environ, {"OLLAMA_HOST": host}):
                    self.assertIn(f"OLLAMA_BASE_URL={expected}",
                                  setup.webui_environment())

    def test_invalid_ollama_host_is_explicit(self) -> None:
        # invalid ports must be reported before constructing docker arguments.
        with mock.patch.dict(setup.os.environ,
                             {"OLLAMA_HOST": "http://localhost:bad"}):
            with self.assertRaisesRegex(click.ClickException,
                                        "Invalid OLLAMA_HOST"):
                setup.webui_environment()


class WebUIInspectionTests(unittest.TestCase):
    """Exercise Docker response and failure handling."""

    def test_inspection_parses_docker_json(self) -> None:
        # parse the single-object response requested by the inspection command.
        result = subprocess.CompletedProcess(
            [], 0, stdout='{"State": {"Running": true}}')
        with mock.patch.object(setup, "run_command", return_value=result):
            self.assertEqual(setup.inspect_webui("docker"),
                             {"State": {
                                 "Running": True
                             }})

    def test_invalid_inspection_is_explicit(self) -> None:
        # reject malformed json and valid json with the wrong top-level shape.
        for content in ("{", "[]"):
            with self.subTest(content=content):
                result = subprocess.CompletedProcess([], 0, stdout=content)
                with mock.patch.object(setup,
                                       "run_command",
                                       return_value=result):
                    with self.assertRaisesRegex(click.ClickException,
                                                "Invalid Docker"):
                        setup.inspect_webui("docker")

    def test_captured_docker_errors_are_reported(self) -> None:
        # captured stderr must survive conversion to a cli exception.
        failure = subprocess.CalledProcessError(1,
                                                "docker",
                                                stderr="permission denied")
        with mock.patch.object(setup.subprocess, "run", side_effect=failure):
            with self.assertRaisesRegex(click.ClickException,
                                        "permission denied"):
                setup.run_command(["docker", "info"],
                                  "Checking Docker",
                                  capture_output=True)

    def test_command_timeout_is_reported(self) -> None:
        # surface subprocess timeouts through the same cli error boundary.
        with mock.patch.object(setup.subprocess,
                               "run",
                               side_effect=subprocess.TimeoutExpired(
                                   "docker", 10)):
            with self.assertRaisesRegex(click.ClickException, "timed out"):
                setup.run_command(["docker", "info"],
                                  "Checking Docker",
                                  timeout=10)

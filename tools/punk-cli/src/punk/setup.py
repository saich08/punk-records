"""Install and initialize the configured model management tool."""

# builtin
import os
import sys
import json
import time
import shutil
import pathlib
import tempfile
import subprocess
import urllib.error
import urllib.parse
import urllib.request

# third-party
import click

# internal
from punk import config as app_config

# identify managed containers before allowing reuse or reconfiguration.
WEBUI_CONTAINER = "punk-open-webui"
WEBUI_IMAGE = "ghcr.io/open-webui/open-webui:main"
WEBUI_LABEL = "io.punk-records.managed"


def command_env() -> dict[str, str]:
    """Return an environment suitable for invoking external programs.

    Returns:
        A copy of the host environment with bundled library overrides removed.
    """

    # do not expose pyinstaller's bundled libraries to external programs.
    env = dict(os.environ)
    if getattr(sys, "frozen", False):
        original = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if original is None:
            env.pop("LD_LIBRARY_PATH", None)
        else:
            env["LD_LIBRARY_PATH"] = original

    return env


def run_command(
    command: list[str],
    action: str,
    *,
    capture_output: bool = False,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run an external command, reporting actionable CLI errors.

    Args:
        command: Executable and arguments.
        action: Human-readable action used in error messages.
        capture_output: Whether to capture standard output and error.
        timeout: Maximum run time in seconds, or None for no limit.

    Returns:
        The completed process, including any captured output.

    Raises:
        click.ClickException: The process cannot start, fails, or times out.
    """

    # child processes need the host environment, not bundled library overrides.
    try:

        return subprocess.run(
            command,
            check=True,
            env=command_env(),
            text=True,
            capture_output=capture_output,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as error:
        # retain captured diagnostics that would be absent from cli errors.
        detail = str(error)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            detail = f"{detail}: {error.stderr.strip()}"

        raise click.ClickException(f"{action} failed: {detail}") from error


def install_ollama() -> str:
    """Install Ollama on Linux and return its executable path.

    Returns:
        The installed executable's path as discovered on the host PATH.

    Raises:
        click.ClickException: Installation is unsupported or unsuccessful.
    """

    # the official automated installer is supported only on linux.
    if sys.platform != "linux":
        raise click.ClickException(
            "Automatic Ollama installation is currently supported only on "
            "Linux. Install Ollama from https://ollama.com/download and "
            "rerun punk init.")

    # remove the downloaded installer after both successful and failed runs.
    click.echo("Installing Ollama using https://ollama.com/install.sh "
               "(may require sudo).")
    try:
        with tempfile.TemporaryDirectory(prefix="punk-ollama-") as directory:
            installer = pathlib.Path(directory) / "install.sh"
            with urllib.request.urlopen("https://ollama.com/install.sh",
                                        timeout=60) as response:
                with installer.open("wb") as output:
                    shutil.copyfileobj(response, output)
            run_command(["sh", str(installer)], "Ollama installation")
    except (OSError, urllib.error.URLError) as error:
        raise click.ClickException(
            f"Could not download/run the Ollama installer: {error}") from error

    # installation can succeed without making the executable discoverable.
    executable = shutil.which("ollama")
    if executable is None:
        raise click.ClickException(
            "Ollama installation finished, but ollama is not on PATH. "
            "Add its installation directory to PATH and rerun punk init.")

    return executable


def server_status(executable: str, timeout: float) -> tuple[bool, str]:
    """Check whether the Ollama server responds.

    Args:
        executable: Path to the Ollama executable.
        timeout: Maximum probe time in seconds.

    Returns:
        Whether the probe succeeded and its diagnostic output.
    """

    # a failed probe is expected while the server is still starting.
    try:
        result = subprocess.run(
            [executable, "list"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=command_env(),
        )
    except subprocess.TimeoutExpired:
        return False, "Timed out waiting for Ollama to respond."

    return result.returncode == 0, (result.stderr.strip()
                                    or result.stdout.strip())


def ensure_server(executable: str) -> None:
    """Reuse a running Ollama server or start one and wait for readiness.

    Args:
        executable: Path to the Ollama executable.

    Raises:
        click.ClickException: The server cannot be contacted or started.
    """

    # preserve servers that were started outside this cli invocation.
    try:
        ready, _ = server_status(executable, timeout=5)
        if ready:
            return

        # detach only a new server and retain its output for diagnosis.
        log_path = app_config.get_config_path().parent / "ollama.log"
        click.echo(f"Starting Ollama in the background; logs: {log_path}")
        with log_path.open("ab") as log:
            process = subprocess.Popen(
                [executable, "serve"],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=command_env(),
            )

        # bound each probe by the remaining startup deadline.
        deadline = time.monotonic() + 30
        error = "Ollama did not become ready."
        ready = False
        try:
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                ready, error = server_status(executable,
                                             timeout=max(
                                                 0.01, min(5, remaining)))
                if ready:
                    return
                if process.poll() is not None:
                    break
                time.sleep(min(0.5, max(0, deadline - time.monotonic())))
        finally:
            # failed startup must terminate only this run's new process.
            if not ready and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

        raise click.ClickException(
            f"Could not start Ollama: {error} See {log_path}.")
    except OSError as error:

        raise click.ClickException(
            f"Could not start or contact Ollama: {error}") from error


def require_docker() -> str:
    """Return the Docker executable after verifying daemon access.

    Returns:
        The Docker executable's path as discovered on the host PATH.

    Raises:
        click.ClickException: Docker is missing or its daemon is unavailable.
    """

    # verify daemon access before model installation can introduce side effects.
    executable = shutil.which("docker")
    if executable is None:
        raise click.ClickException(
            "Open WebUI requires Docker. Install Docker and start its daemon, "
            "or set enable_web_interface to false.")

    # an installed client is insufficient unless its daemon is accessible.
    run_command(
        [executable, "info"],
        "Checking Docker (ensure its daemon is running and accessible)",
        capture_output=True,
        timeout=10,
    )

    return executable


def webui_environment() -> list[str]:
    """Build local WebUI settings using the configured Ollama endpoint.

    Returns:
        Container environment assignments.

    Raises:
        click.ClickException: The Ollama endpoint is not a valid HTTP(S) URL.
    """

    # accept ollama's shorthand host syntax before parsing it as a url.
    host = os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
    if host.startswith(":"):
        host = f"127.0.0.1{host}"
    if "://" not in host:
        host = f"http://{host}"

    # reject credentials and unsupported schemes before composing the endpoint.
    try:
        url = urllib.parse.urlsplit(host)
        hostname = url.hostname
        port = url.port or 11434
        if (url.scheme not in ("http", "https") or not hostname
                or url.username is not None):
            raise ValueError("expected an HTTP(S) host")

        # wildcard listen addresses must become reachable loopback destinations.
        if hostname == "0.0.0.0":
            hostname = "127.0.0.1"
        elif hostname == "::":
            hostname = "::1"

        # url authorities require brackets around ipv6 address literals.
        if ":" in hostname:
            hostname = f"[{hostname}]"
        base_url = urllib.parse.urlunsplit(
            (url.scheme, f"{hostname}:{port}", url.path, "", ""))
    except ValueError as error:
        raise click.ClickException(
            f"Invalid OLLAMA_HOST for Open WebUI: {error}") from error

    # bind access locally while keeping secrets on the persistent data volume.
    return [
        "HOST=127.0.0.1",
        "PORT=8080",
        f"OLLAMA_BASE_URL={base_url}",
        "WEBUI_SECRET_KEY_FILE=/app/backend/data/.webui_secret_key",
    ]


def docker_object(value: object) -> dict[str, object]:
    """Require a JSON object from Docker inspection.

    Args:
        value: Parsed Docker inspection data.

    Returns:
        The inspection object.

    Raises:
        click.ClickException: The supplied value is not a dictionary.
    """

    # nested inspection fields must be objects before reading their keys.
    if not isinstance(value, dict):
        raise click.ClickException(
            "Invalid Docker inspection response: expected an object.")

    return value


def inspect_webui(docker: str, timeout: float = 10) -> dict[str, object]:
    """Read the managed WebUI container's inspection data.

    Args:
        docker: Path to the Docker executable.
        timeout: Maximum inspection time in seconds.

    Returns:
        The parsed container object.

    Raises:
        click.ClickException: Inspection fails or returns invalid JSON.
    """

    # request one container object rather than docker's default list response.
    result = run_command(
        [docker, "inspect", "--format", "{{json .}}", WEBUI_CONTAINER],
        "Inspecting Open WebUI",
        capture_output=True,
        timeout=timeout,
    )

    # reject invalid json before callers access container properties.
    try:
        container = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise click.ClickException(
            f"Invalid Docker inspection response: {error}") from error

    return docker_object(container)


def ensure_webui(docker: str, *, enable_internet_access: bool = False) -> None:
    """Create or reuse managed WebUI and wait for a healthy container.

    Args:
        docker: Path to the Docker executable.
        enable_internet_access: Whether to enable DuckDuckGo web search.

    Raises:
        click.ClickException: Settings conflict or container startup fails.
    """

    # disable persisted overrides so configured search flags take effect.
    base_environment = webui_environment()
    search_environment = [
        f"ENABLE_WEB_SEARCH={str(enable_internet_access).lower()}",
        "WEB_SEARCH_ENGINE=duckduckgo",
        "ENABLE_PERSISTENT_CONFIG=false",
    ]
    environment = base_environment + search_environment

    # match the exact managed name rather than unrelated container names.
    result = run_command(
        [
            docker,
            "container",
            "ls",
            "--all",
            "--filter",
            f"name=^/{WEBUI_CONTAINER}$",
            "--format",
            "{{.ID}}",
        ],
        "Finding Open WebUI",
        capture_output=True,
        timeout=10,
    )
    create_container = not result.stdout.strip()

    # never replace a container whose ownership or persistent data differs.
    if not create_container:
        container = inspect_webui(docker)
        settings = docker_object(container.get("Config") or {})
        network = docker_object(container.get("HostConfig") or {})
        labels = docker_object(settings.get("Labels") or {})
        saved_environment = settings.get("Env")
        mounts = container.get("Mounts") or []
        if (labels.get(WEBUI_LABEL) != "true"
                or settings.get("Image") != WEBUI_IMAGE
                or not isinstance(saved_environment, list)
                or not set(base_environment).issubset(saved_environment)
                or network.get("NetworkMode") != "host"
                or not isinstance(mounts, list) or not any(
                    isinstance(mount, dict) and mount.get("Type") == "volume"
                    and mount.get("Name") == WEBUI_CONTAINER
                    and mount.get("Destination") == "/app/backend/data"
                    for mount in mounts)):
            raise click.ClickException(
                f"Container {WEBUI_CONTAINER!r} already exists with "
                "different settings. Resolve the conflict manually; "
                "Punk will not replace it or delete its data.")

        # recreate only the managed container, retaining its named volume.
        if not set(search_environment).issubset(saved_environment):
            click.echo("Updating Open WebUI search settings; "
                       "retaining the data volume...")
            run_command([docker, "stop", WEBUI_CONTAINER],
                        "Stopping Open WebUI for reconfiguration")
            run_command([docker, "rm", WEBUI_CONTAINER],
                        "Removing the old Open WebUI container")
            create_container = True
        elif not docker_object(container.get("State") or {}).get("Running"):
            run_command([docker, "start", WEBUI_CONTAINER],
                        "Starting Open WebUI")

    # host networking lets the container reach the local ollama server.
    if create_container:
        click.echo("Creating Open WebUI container "
                   "(the image download may take a while)...")
        command = [
            docker,
            "run",
            "--detach",
            "--name",
            WEBUI_CONTAINER,
            "--label",
            f"{WEBUI_LABEL}=true",
            "--restart",
            "unless-stopped",
            "--network",
            "host",
            "--volume",
            f"{WEBUI_CONTAINER}:/app/backend/data",
        ]
        for setting in environment:
            command.extend(["--env", setting])
        command.append(WEBUI_IMAGE)
        run_command(command, "Creating Open WebUI")

    # report readiness only after docker's health check succeeds.
    click.echo("Waiting for Open WebUI to become healthy...")
    deadline = time.monotonic() + 120
    failure = "did not become healthy within 120 seconds"
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        container = inspect_webui(docker, timeout=max(0.01, min(10, remaining)))
        state = docker_object(container.get("State") or {})
        health = docker_object(state.get("Health") or {}).get("Status")

        # paused containers can retain a stale healthy status.
        if state.get("Paused"):
            raise click.ClickException(
                "Open WebUI is paused. "
                f"Run 'docker unpause {WEBUI_CONTAINER}' and retry.")

        # a healthy probe is usable only while the container is running.
        if state.get("Running") and health == "healthy":
            click.echo("Open WebUI is ready at http://127.0.0.1:8080")
            if enable_internet_access:
                click.echo(
                    "Internet access enabled through Open WebUI web search "
                    "(DuckDuckGo).")

            return

        # a stopped container cannot become ready through further polling.
        if not state.get("Running"):
            failure = "container stopped before becoming healthy"
            break

        # expose failed health checks instead of waiting for the full deadline.
        if health == "unhealthy":
            failure = "container is unhealthy"
            break

        # keep polling delays within the remaining startup deadline.
        time.sleep(min(1, max(0, deadline - time.monotonic())))

    raise click.ClickException(f"Open WebUI {failure}. "
                               f"Check 'docker logs {WEBUI_CONTAINER}' "
                               "and ensure Docker host networking is enabled.")


def setup(config: app_config.AppConfig) -> None:
    """Initialize the configured models and optional WebUI.

    Args:
        config: Validated model and web-interface settings.

    Raises:
        click.ClickException: Options are unsupported or a setup step fails.
    """

    # reject search settings that cannot work without the web interface.
    if config.enable_internet_access and not config.enable_web_interface:
        raise click.ClickException(
            "enable_internet_access requires enable_web_interface.")

    # unsupported managers must fail before any executable discovery.
    if config.management_tool != "ollama":
        raise click.ClickException(
            f"Unsupported management tool {config.management_tool!r}. "
            "Only 'ollama' is supported.")

    # fail docker preflight before model setup can introduce side effects.
    docker = require_docker() if config.enable_web_interface else None

    # reuse existing tools and servers before pulling each configured model.
    executable = shutil.which("ollama")
    if executable is None:
        executable = install_ollama()

    # a responsive server is required before any configured model can be pulled.
    ensure_server(executable)

    # preserve the configured model order and stop at the first failed pull.
    for model in config.models:
        click.echo(f"Pulling model {model}...")
        run_command([executable, "pull", "--", model],
                    f"Pulling model {model!r}")
    # the web interface starts only after all model pulls succeed.
    if docker is not None:
        ensure_webui(docker,
                     enable_internet_access=config.enable_internet_access)

    # report completion only after all requested setup steps have succeeded.
    click.echo("Ollama setup complete.")

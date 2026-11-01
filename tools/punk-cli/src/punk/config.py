"""Application configuration initialization."""

# builtin
import json
import pathlib
import tempfile
import dataclasses

# third-party
import click


@dataclasses.dataclass(frozen=True)
class AppConfig:
    """Validated application settings.

    Attributes:
        management_tool: Model manager used for setup.
        models: Model names to pull.
        enable_web_interface: Whether to configure Open WebUI.
        enable_internet_access: Whether to enable Open WebUI web search.
    """

    # disabled web defaults preserve compatibility with older configurations.
    management_tool: str
    models: tuple[str, ...]
    enable_web_interface: bool = False
    enable_internet_access: bool = False


def get_config_path() -> pathlib.Path:
    """Return the configuration path in the platform's application directory."""

    # delegate platform-specific config placement to click.
    return pathlib.Path(click.get_app_dir("punk")) / "config.json"


def init_config(
    management_tool: str = "ollama",
    models: tuple[str, ...] = ("llama3.2",),
    enable_web_interface: bool = False,
    *,
    enable_internet_access: bool = False,
    force: bool = False,
) -> tuple[pathlib.Path, bool]:
    """Write defaults and options, preserving existing settings unless forced.

    Args:
        management_tool: Model manager to record.
        models: Model names to record.
        enable_web_interface: Whether to configure Open WebUI.
        enable_internet_access: Whether to enable Open WebUI web search.
        force: Whether to replace existing configuration atomically.

    Returns:
        The configuration path and whether a file was written.

    Raises:
        click.ClickException: The configuration cannot be written.
    """

    # serialize the complete replacement before touching the destination file.
    path = get_config_path()
    content = json.dumps(
        {
            "management_tool": management_tool,
            "models": list(models),
            "enable_web_interface": enable_web_interface,
            "enable_internet_access": enable_internet_access,
        },
        indent=2,
    ) + "\n"

    # exclusive creation and atomic replacement protect existing settings.
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if force:
            # keep the original file intact until its replacement is complete.
            temporary_file = tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            )
            temporary_path = pathlib.Path(temporary_file.name)
            try:
                with temporary_file as temporary_stream:
                    temporary_stream.write(content)
                temporary_path.replace(path)
            finally:
                temporary_path.unlink(missing_ok=True)
        else:
            # exclusive creation preserves configuration written by another run.
            with path.open("x", encoding="utf-8") as config_file:
                config_file.write(content)
    except FileExistsError as error:
        if not force and path.is_file():
            return path, False

        raise click.ClickException(
            f"Config path is not a file: {path}") from error
    except OSError as error:
        raise click.ClickException(
            f"Could not initialize config at {path}: {error}") from error

    return path, True


def load_config() -> AppConfig:
    """Load and validate configuration, creating defaults if missing.

    Returns:
        Validated settings with defaults for optional legacy fields.

    Raises:
        click.ClickException: Configuration cannot be read or is invalid.
    """

    # read defaults through the same initialization path used by the cli.
    path, _ = init_config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise click.ClickException(
            f"Could not read config at {path}: {error}") from error

    # validate the container shape before accessing individual settings.
    if not isinstance(data, dict):
        raise click.ClickException(
            f"Invalid config at {path}: expected a JSON object.")

    # missing optional fields retain compatibility with older configurations.
    management_tool = data.get("management_tool")
    models = data.get("models")
    enable_web_interface = data.get("enable_web_interface", False)
    enable_internet_access = data.get("enable_internet_access", False)

    # require a usable manager name before exposing configuration to setup.
    if not isinstance(management_tool, str) or not management_tool.strip():
        raise click.ClickException(f"Invalid config at {path}: "
                                   "management_tool must be a nonblank string.")

    # reject empty lists and invalid individual names before pulling models.
    if (not isinstance(models, list) or not models
            or any(not isinstance(model, str) or not model.strip()
                   for model in models)):
        raise click.ClickException(
            f"Invalid config at {path}: "
            "models must be a nonempty list of nonblank strings.")

    # feature flags must be actual booleans rather than truthy json values.
    if not isinstance(enable_web_interface, bool):
        raise click.ClickException(
            f"Invalid config at {path}: enable_web_interface must be a boolean."
        )

    # web search uses its own independently validated feature flag.
    if not isinstance(enable_internet_access, bool):
        raise click.ClickException(f"Invalid config at {path}: "
                                   "enable_internet_access must be a boolean.")

    # web search cannot be configured without the web interface that hosts it.
    if enable_internet_access and not enable_web_interface:
        raise click.ClickException(
            f"Invalid config at {path}: "
            "enable_internet_access requires enable_web_interface.")

    # expose immutable model names only after all stored fields are validated.
    return AppConfig(
        management_tool=management_tool,
        models=tuple(models),
        enable_web_interface=enable_web_interface,
        enable_internet_access=enable_internet_access,
    )

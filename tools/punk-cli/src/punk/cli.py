"""Click entry point for punk."""

# third-party
import click

# internal
from punk import setup
from punk import config as app_config


@click.group(
    invoke_without_command=True,
    help="The punk command-line interface.",
)
@click.version_option(package_name="punk-records", prog_name="punk")
@click.pass_context
def main(ctx: click.Context) -> None:
    """Run the CLI, initializing defaults only for ordinary startup.

    Args:
        ctx: Click context identifying the requested subcommand.
    """

    # let configuration and setup commands control their own initialization.
    if ctx.invoked_subcommand not in ("config", "init"):
        path, created = app_config.init_config()
        if created:
            click.echo(f"Created config at {path}")

    # bare startup must initialize defaults before showing help.
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command(
    "init",
    help=("Set up models and the optional web interface from "
          "application configuration."),
)
def initialize() -> None:
    """Set up models and the optional web interface from saved configuration."""

    # validate saved settings before invoking any external setup tools.
    config = app_config.load_config()

    # run external setup only after the saved configuration has been validated.
    click.echo(f"Using configuration at {app_config.get_config_path()}")
    setup.setup(config)


@main.group()
def config() -> None:
    """Manage application configuration."""


@config.command(help="Create configuration, or replace it with --force.")
@click.option(
    "--management-tool",
    default="ollama",
    show_default=True,
    help="Model management tool to use.",
)
@click.option(
    "--model",
    "models",
    multiple=True,
    default=("llama3.2",),
    show_default=True,
    help="Model to use. Repeat to configure multiple models.",
)
@click.option(
    "--enable-web-interface/--disable-web-interface",
    default=False,
    show_default=True,
    help="Set up Open WebUI with Docker when punk init runs.",
)
@click.option(
    "--enable-internet-access/--disable-internet-access",
    default=False,
    show_default=True,
    help="Enable Open WebUI web search (requires --enable-web-interface).",
)
@click.option(
    "--force",
    is_flag=True,
    help="Replace existing config with the supplied options and defaults.",
)
def init(
    management_tool: str,
    models: tuple[str, ...],
    enable_web_interface: bool,
    enable_internet_access: bool,
    force: bool,
) -> None:
    """Create configuration, or replace it with --force.

    Args:
        management_tool: Model manager to record in configuration.
        models: Model names to pull during setup.
        enable_web_interface: Whether setup should start Open WebUI.
        enable_internet_access: Whether Open WebUI should enable web search.
        force: Whether to replace the entire existing configuration.

    Raises:
        click.UsageError: An option is blank or requires the web interface.
    """

    # reject incompatible options before any configuration file is written.
    if not management_tool.strip() or any(
            not model.strip() for model in models):
        raise click.UsageError(
            "Management tool and model names must not be blank.")

    # reject web-search options that have no web interface to serve them.
    if enable_internet_access and not enable_web_interface:
        raise click.UsageError(
            "--enable-internet-access requires --enable-web-interface.")

    # forced initialization replaces all settings rather than merging them.
    path, written = app_config.init_config(
        management_tool,
        models,
        enable_web_interface,
        enable_internet_access=enable_internet_access,
        force=force,
    )

    # distinguish preserved settings from a successful configuration write.
    if written:
        action = "Wrote" if force else "Created"
        click.echo(f"{action} config at {path}")
    else:
        click.echo(f"Config already exists at {path}; left unchanged. "
                   "Use --force to replace it.")

import typer

from miniops.core.entities import require_name


def model_name(name: str) -> str:
    """Check the name of a model given on the command line, so a bad one is a usage error."""
    try:
        require_name("model", name)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    return name

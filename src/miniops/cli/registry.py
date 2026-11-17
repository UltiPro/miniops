from typing import Annotated

import typer

from miniops.adapters.stores import open_stores
from miniops.cli.output import columns, when
from miniops.cli.paths import current_directory
from miniops.config.project import find_project
from miniops.core.entities import VersionStatus
from miniops.core.registry import CatalogEntry, find_model, list_catalog

registry_app = typer.Typer(help="Look at the models and their versions.", no_args_is_help=True)


@registry_app.command("list")
def list_models(
    model: Annotated[
        str | None, typer.Argument(help="Name of a model, to list its versions.")
    ] = None,
) -> None:
    """List the models of the project, or the versions of one model."""
    with open_stores(find_project(current_directory())) as stores:
        if model is not None:
            typer.echo(_versions(find_model(stores.metadata, model)))
        elif entries := list_catalog(stores.metadata):
            typer.echo(_models(entries))
        else:
            typer.echo("No models yet. Create one with `miniops new`.")


@registry_app.command("show")
def show(
    model: Annotated[str, typer.Argument(help="Name of the model.")],
    version: Annotated[str, typer.Option(help="Number of the version, or an alias.")],
) -> None:
    """Show one version of a model."""
    with open_stores(find_project(current_directory())) as stores:
        entry = find_model(stores.metadata, model)
    found = entry.find_version(version)
    base = found.base
    typer.echo(
        columns(
            [
                ("Model", entry.model.name),
                ("Flavor", entry.model.flavor),
                ("Task", entry.model.task),
                ("Version", str(found.number)),
                ("Status", found.status),
                ("Base", "-" if base is None else f"{base.number} ({base.digest})"),
                ("Created", when(found.created_at)),
                ("Released", when(found.released_at)),
                ("Digest", found.content_digest or "-"),
                ("Run", str(found.released_run_id or "-")),
                ("Aliases", ", ".join(entry.aliases_of(found)) or "-"),
            ]
        )
    )


def _models(entries: list[CatalogEntry]) -> str:
    rows = [("Model", "Flavor", "Task", "Released", "Drafts")]
    for entry in entries:
        statuses = [version.status for version in entry.versions]
        rows.append(
            (
                entry.model.name,
                entry.model.flavor,
                entry.model.task,
                str(statuses.count(VersionStatus.RELEASED)),
                str(statuses.count(VersionStatus.DRAFT)),
            )
        )
    return columns(rows)


def _versions(entry: CatalogEntry) -> str:
    if not entry.versions:
        return f"The model {entry.model.name!r} has no versions."
    rows = [("Version", "Status", "Base", "Created", "Released", "Aliases")]
    for version in entry.versions:
        rows.append(
            (
                str(version.number),
                version.status,
                "-" if version.base is None else str(version.base.number),
                when(version.created_at),
                when(version.released_at),
                ", ".join(entry.aliases_of(version)) or "-",
            )
        )
    return columns(rows)

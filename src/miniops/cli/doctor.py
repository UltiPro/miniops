from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import typer

from miniops.adapters.stores import store_schema
from miniops.cli.output import describe
from miniops.cli.paths import current_directory
from miniops.config.project import Project, find_project, find_root
from miniops.core.errors import MiniopsError
from miniops.tools import find_tool, git_config, tool_version

type _Status = Literal["ok", "warning", "problem"]


@dataclass(frozen=True)
class _Check:
    status: _Status
    message: str
    fix: tuple[str, ...] = ()


def doctor() -> None:
    """Check that uv, git and the project are ready for miniOPs."""
    root = find_root(current_directory())
    checks = [_uv(), *_git()]
    if root is not None:
        checks += _project(root)
    for check in checks:
        first, *more = check.message.splitlines() or [""]
        typer.echo(f"{check.status:<9}{first}")
        for line in [*more, *check.fix]:
            typer.echo(f"{'':9}{line}")
    statuses = [check.status for check in checks]
    typer.echo(f"\n{_summary(statuses)}")
    if root is None:
        typer.echo("Not in a miniOPs project, so no project or store was checked.")
    if "problem" in statuses:
        raise typer.Exit(1)


def _uv() -> _Check:
    uv = find_tool("uv")
    if uv is None:
        return _Check(
            "problem",
            "uv was not found. miniOPs needs it to create the environment of a model. Install it:",
            ("https://docs.astral.sh/uv/getting-started/installation/",),
        )
    try:
        return _Check("ok", f"uv {tool_version(uv)}")
    except OSError as error:
        return _failed("problem", error)


def _git() -> list[_Check]:
    git = find_tool("git")
    if git is None:
        return [
            _Check(
                "warning",
                "git was not found. miniOPs reads the author of runs and releases from it. "
                "Install it:",
                ("https://git-scm.com/downloads",),
            )
        ]
    try:
        version = tool_version(git)
    except OSError as error:
        return [_failed("warning", error)]
    return [_Check("ok", f"git {version}"), _author(git)]


def _author(git: Path) -> _Check:
    try:
        name, email = git_config(git, "user.name"), git_config(git, "user.email")
    except OSError as error:
        return _failed("warning", error)
    if name and email:
        return _Check("ok", f"author {name} <{email}>")
    missing = [key for key, value in (("name", name), ("email", email)) if not value]
    keys = " and ".join(f"user.{key}" for key in missing)
    return _Check(
        "warning",
        f"git has no {keys}, which miniOPs records as the author of runs and releases. "
        f"Set {'them' if len(missing) > 1 else 'it'} with:",
        tuple(f'git config --global user.{key} "<{key}>"' for key in missing),
    )


def _project(root: Path) -> list[_Check]:
    try:
        project = find_project(root)
    except (MiniopsError, OSError) as error:
        return [_failed("problem", error)]
    name = project.config.project.name
    return [_Check("ok", f"project {name} ({project.root})"), _store(project)]


def _store(project: Project) -> _Check:
    try:
        schema = store_schema(project)
    except (MiniopsError, OSError) as error:
        return _failed("problem", error)
    version, newest = schema.version, schema.newest
    if version is None:
        return _Check("ok", "store not created yet")
    if version > newest:
        return _Check(
            "problem",
            f"store schema version {version}, but this miniOPs reads up to version {newest}. "
            "Upgrade miniOPs to use this store.",
        )
    upgrade = f", upgraded to {newest} by the next command" if version < newest else ""
    return _Check("ok", f"store schema version {version}{upgrade}")


def _failed(status: _Status, error: MiniopsError | OSError) -> _Check:
    return _Check(status, describe(error) if isinstance(error, OSError) else str(error))


def _summary(statuses: list[_Status]) -> str:
    problems, warnings = statuses.count("problem"), statuses.count("warning")
    if not problems and not warnings:
        return "No problems found."
    parts = [_count(problems, "problem") if problems else "No problems"]
    if warnings:
        parts.append(_count(warnings, "warning"))
    return ", ".join(parts) + "."


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"

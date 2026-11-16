from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from miniops.adapters.stores import open_stores
from miniops.cli import app
from miniops.cli.output import columns, when
from miniops.config.project import Project, init_project
from miniops.core.entities import (
    Alias,
    ArtifactRef,
    ModelVersion,
    Run,
    RunStatus,
    Task,
    VersionRef,
)
from miniops.core.errors import ConfigError, NotFoundError
from miniops.core.registry import create_model
from miniops.core.versions import SemVer
from miniops.ports import MetadataStore

runner = CliRunner()
RELEASED_AT = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
DIGEST = "b" * 64


def release(metadata: MetadataStore, version: ModelVersion) -> ModelVersion:
    run = Run(id=uuid4(), version_id=version.id, started_at=RELEASED_AT, miniops_version="0.1.0")
    metadata.add_run(run)
    artifact = ArtifactRef(key="runs/7c1e/model.skops", digest="a" * 64, size=1)
    run = run.finish(RunStatus.SUCCEEDED, RELEASED_AT, artifact=artifact)
    metadata.update_run(run)
    released = version.release(run, DIGEST, RELEASED_AT)
    metadata.update_version(released)
    return released


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Project:
    """A project with a model that has a draft, and one with a released version and a new draft."""
    project = init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    with open_stores(project) as stores:
        metadata = stores.metadata
        create_model(metadata, tmp_path / "models" / "demand", "demand", "sklearn", Task.REGRESSION)
        first = create_model(
            metadata, tmp_path / "models" / "churn", "churn", "sklearn", Task.BINARY_CLASSIFICATION
        )
        released = release(metadata, first)
        metadata.set_alias(
            Alias(
                model_id=first.model_id,
                name="champion",
                version_id=first.id,
                updated_at=RELEASED_AT,
            )
        )
        metadata.add_version(
            ModelVersion(
                id=uuid4(),
                model_id=first.model_id,
                number=SemVer(1, 1, 0),
                created_at=RELEASED_AT,
                base=VersionRef(number=released.number, digest=DIGEST),
            )
        )
    return project


def versions_of(project: Project, name: str) -> dict[str, ModelVersion]:
    with open_stores(project) as stores:
        model = stores.metadata.get_model(name)
        assert model is not None
        return {str(version.number): version for version in stores.metadata.list_versions(model.id)}


def test_registry_list_says_when_there_are_no_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["registry", "list"])

    assert result.exit_code == 0
    assert result.stdout == "No models yet. Create one with `miniops new`.\n"


@pytest.mark.usefixtures("project")
def test_registry_list_shows_the_models_of_the_project() -> None:
    result = runner.invoke(app, ["registry", "list"])

    assert result.exit_code == 0
    assert result.stdout == (
        columns(
            [
                ("Model", "Flavor", "Task", "Released", "Drafts"),
                ("churn", "sklearn", "binary_classification", "1", "1"),
                ("demand", "sklearn", "regression", "0", "1"),
            ]
        )
        + "\n"
    )


def test_registry_list_shows_the_versions_of_a_model(project: Project) -> None:
    versions = versions_of(project, "churn")

    result = runner.invoke(app, ["registry", "list", "churn"])

    assert result.exit_code == 0
    assert result.stdout == (
        columns(
            [
                ("Version", "Status", "Base", "Created", "Released", "Aliases"),
                ("1.1.0", "draft", "1.0.0", when(RELEASED_AT), "-", "-"),
                (
                    "1.0.0",
                    "released",
                    "-",
                    when(versions["1.0.0"].created_at),
                    when(RELEASED_AT),
                    "champion",
                ),
            ]
        )
        + "\n"
    )


def test_registry_list_shows_a_deleted_version_and_every_alias(project: Project) -> None:
    released = versions_of(project, "churn")["1.0.0"]
    with open_stores(project) as stores:
        stores.metadata.set_alias(
            Alias(
                model_id=released.model_id,
                name="best",
                version_id=released.id,
                updated_at=RELEASED_AT,
            )
        )
        stores.metadata.update_version(released.delete())

    versions = runner.invoke(app, ["registry", "list", "churn"])
    models = runner.invoke(app, ["registry", "list"])

    assert versions.stdout.splitlines()[2].split()[:2] == ["1.0.0", "deleted"]
    assert versions.stdout.splitlines()[2].endswith("best, champion")
    assert models.stdout.splitlines()[1].split() == [
        "churn",
        "sklearn",
        "binary_classification",
        "0",
        "1",
    ]


def test_registry_list_says_when_a_model_has_no_versions(project: Project) -> None:
    draft = versions_of(project, "demand")["1.0.0"]
    with open_stores(project) as stores:
        stores.metadata.delete_version(draft.id)

    result = runner.invoke(app, ["registry", "list", "demand"])

    assert result.exit_code == 0
    assert result.stdout == "The model 'demand' has no versions.\n"


def test_registry_show_shows_a_draft(project: Project) -> None:
    draft = versions_of(project, "demand")["1.0.0"]

    result = runner.invoke(app, ["registry", "show", "demand", "--version", "1.0.0"])

    assert result.exit_code == 0
    assert result.stdout == (
        columns(
            [
                ("Model", "demand"),
                ("Flavor", "sklearn"),
                ("Task", "regression"),
                ("Version", "1.0.0"),
                ("Status", "draft"),
                ("Base", "-"),
                ("Created", when(draft.created_at)),
                ("Released", "-"),
                ("Digest", "-"),
                ("Run", "-"),
                ("Aliases", "-"),
            ]
        )
        + "\n"
    )


def test_registry_show_finds_a_released_version_by_its_alias(project: Project) -> None:
    released = versions_of(project, "churn")["1.0.0"]

    result = runner.invoke(app, ["registry", "show", "churn", "--version", "champion"])

    assert result.exit_code == 0
    assert result.stdout == (
        columns(
            [
                ("Model", "churn"),
                ("Flavor", "sklearn"),
                ("Task", "binary_classification"),
                ("Version", "1.0.0"),
                ("Status", "released"),
                ("Base", "-"),
                ("Created", when(released.created_at)),
                ("Released", when(RELEASED_AT)),
                ("Digest", DIGEST),
                ("Run", str(released.released_run_id)),
                ("Aliases", "champion"),
            ]
        )
        + "\n"
    )


@pytest.mark.usefixtures("project")
def test_registry_show_names_the_base_of_a_version() -> None:
    result = runner.invoke(app, ["registry", "show", "churn", "--version", "1.1.0"])

    assert result.exit_code == 0
    assert f"Base      1.0.0 ({DIGEST})\n" in result.stdout


@pytest.mark.usefixtures("project")
@pytest.mark.parametrize(
    "arguments",
    [
        ["registry", "list", "fraud"],
        ["registry", "show", "fraud", "--version", "1.0.0"],
        ["registry", "show", "churn", "--version", "2.0.0"],
        ["registry", "show", "churn", "--version", "challenger"],
        ["registry", "show", "churn", "--version", "1.0"],
    ],
)
def test_registry_says_what_it_cannot_find(arguments: list[str]) -> None:
    result = runner.invoke(app, arguments)

    assert result.exit_code == 1
    assert isinstance(result.exception, NotFoundError)


@pytest.mark.usefixtures("project")
def test_registry_show_needs_a_version() -> None:
    result = runner.invoke(app, ["registry", "show", "churn"])

    assert result.exit_code == 2


def test_registry_needs_a_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["registry", "list"])

    assert result.exit_code == 1
    assert isinstance(result.exception, ConfigError)
    assert list(tmp_path.iterdir()) == []

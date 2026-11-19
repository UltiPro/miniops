import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from typer.testing import CliRunner

from miniops.adapters.local import schema
from miniops.adapters.stores import open_stores
from miniops.cli import app, doctor, main
from miniops.config.project import Project, init_project

runner = CliRunner()

TOOLS = [
    "ok       uv 0.13.6",
    "ok       git 2.51.0",
    "ok       author Jan Kowalski <jan@example.com>",
]


@dataclass
class Machine:
    versions: dict[str, str] = field(default_factory=lambda: {"uv": "0.13.6", "git": "2.51.0"})
    config: dict[str, str] = field(
        default_factory=lambda: {"user.name": "Jan Kowalski", "user.email": "jan@example.com"}
    )
    broken: set[str] = field(default_factory=set)


@pytest.fixture(autouse=True)
def machine(monkeypatch: pytest.MonkeyPatch) -> Machine:
    machine = Machine()

    def find_tool(name: str) -> Path | None:
        return Path(name) if name in machine.versions else None

    def tool_version(tool: Path) -> str:
        if tool.name in machine.broken:
            raise OSError(f"{tool} does not run: Permission denied")
        return machine.versions[tool.name]

    def git_config(git: Path, key: str) -> str | None:
        if "config" in machine.broken:
            raise OSError(f"{git} exited with code 128: fatal: bad config line 1")
        return machine.config.get(key)

    monkeypatch.setattr(doctor, "find_tool", find_tool)
    monkeypatch.setattr(doctor, "tool_version", tool_version)
    monkeypatch.setattr(doctor, "git_config", git_config)
    return machine


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Project:
    project = init_project(tmp_path, "retail-models")
    with open_stores(project):
        pass
    monkeypatch.chdir(tmp_path)
    return project


def run_doctor() -> tuple[int, list[str]]:
    result = runner.invoke(app, ["doctor"])
    return result.exit_code, result.stdout.splitlines()


def test_a_ready_project_has_no_problems(project: Project) -> None:
    code, lines = run_doctor()

    assert code == 0
    assert lines == [
        *TOOLS,
        f"ok       project retail-models ({project.root})",
        f"ok       store schema version {schema.newest_version()}",
        "",
        "No problems found.",
    ]


def test_outside_a_project_only_the_programs_are_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    code, lines = run_doctor()

    assert code == 0
    assert lines == [
        *TOOLS,
        "",
        "No problems found.",
        "Not in a miniOPs project, so no project or store was checked.",
    ]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.usefixtures("project")
def test_without_uv_there_is_a_problem(machine: Machine) -> None:
    del machine.versions["uv"]

    code, lines = run_doctor()

    assert code == 1
    assert lines[:2] == [
        "problem  uv was not found. miniOPs needs it to create the environment of a model. "
        "Install it:",
        "         https://docs.astral.sh/uv/getting-started/installation/",
    ]
    assert lines[-1] == "1 problem."


@pytest.mark.usefixtures("project")
def test_a_uv_that_does_not_run_is_a_problem(machine: Machine) -> None:
    machine.broken.add("uv")

    code, lines = run_doctor()

    assert code == 1
    assert lines[0] == "problem  uv does not run: Permission denied"
    assert lines[-1] == "1 problem."


def test_without_git_there_is_only_a_warning(project: Project, machine: Machine) -> None:
    del machine.versions["git"]

    code, lines = run_doctor()

    assert code == 0
    assert lines[1:4] == [
        "warning  git was not found. miniOPs reads the author of runs and releases from it. "
        "Install it:",
        "         https://git-scm.com/downloads",
        f"ok       project retail-models ({project.root})",
    ]
    assert lines[-1] == "No problems, 1 warning."


def test_a_git_that_does_not_run_is_only_a_warning(project: Project, machine: Machine) -> None:
    machine.broken.add("git")

    code, lines = run_doctor()

    assert code == 0
    assert lines[1:3] == [
        "warning  git does not run: Permission denied",
        f"ok       project retail-models ({project.root})",
    ]


@pytest.mark.usefixtures("project")
@pytest.mark.parametrize(
    ("config", "lines_about_it"),
    [
        (
            {"user.name": "Jan Kowalski"},
            [
                "warning  git has no user.email, which miniOPs records as the author of runs and "
                "releases. Set it with:",
                '         git config --global user.email "<email>"',
            ],
        ),
        (
            {},
            [
                "warning  git has no user.name and user.email, which miniOPs records as the author "
                "of runs and releases. Set them with:",
                '         git config --global user.name "<name>"',
                '         git config --global user.email "<email>"',
            ],
        ),
    ],
)
def test_a_git_without_the_author_is_a_warning(
    machine: Machine, config: dict[str, str], lines_about_it: list[str]
) -> None:
    machine.config = config

    code, lines = run_doctor()

    assert code == 0
    assert lines[2 : 2 + len(lines_about_it)] == lines_about_it
    assert lines[-1] == "No problems, 1 warning."


@pytest.mark.usefixtures("project")
def test_a_git_configuration_that_cannot_be_read_is_a_warning(machine: Machine) -> None:
    machine.broken.add("config")

    code, lines = run_doctor()

    assert code == 0
    assert lines[2] == "warning  git exited with code 128: fatal: bad config line 1"


def test_a_configuration_that_is_not_valid_is_a_problem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "miniops.toml").write_text("[project\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    code, lines = run_doctor()

    assert code == 1
    assert lines[3].startswith(f"problem  {tmp_path / 'miniops.toml'} is not valid TOML")
    assert lines[4:] == ["", "1 problem."]


def test_every_line_of_a_long_message_stays_in_its_column(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "miniops.toml"
    config.write_text('[project]\nname = "retail"\ncolour = "blue"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    code, lines = run_doctor()

    assert code == 1
    assert lines[3] == f"problem  {config} is not valid:"
    assert lines[4].startswith("           project.colour: ")


def test_a_file_where_the_stores_belong_is_a_problem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_project(tmp_path, "retail-models")
    (tmp_path / ".miniops").write_text("not a directory", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    code, lines = run_doctor()

    assert code == 1
    assert lines[4] == (
        f"problem  {tmp_path / '.miniops'} is not a directory, so the stores cannot be "
        "created in it."
    )


def test_a_store_that_does_not_exist_yet_is_not_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_project(tmp_path, "retail-models")
    monkeypatch.chdir(tmp_path)

    code, lines = run_doctor()

    assert code == 0
    assert lines[4] == "ok       store not created yet"
    assert not (tmp_path / ".miniops").exists()


def test_an_older_store_is_left_for_the_next_command_to_upgrade(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    older = schema.newest_version()
    monkeypatch.setattr(
        schema, "MIGRATIONS", (*schema.MIGRATIONS, "CREATE TABLE deployments (id TEXT);")
    )

    code, lines = run_doctor()

    assert code == 0
    assert lines[4] == (
        f"ok       store schema version {older}, upgraded to {older + 1} by the next command"
    )
    assert [path.name for path in (project.root / ".miniops").iterdir()] == ["metadata.db"]


def test_a_store_from_a_newer_miniops_is_a_problem(project: Project) -> None:
    newer = schema.newest_version() + 1
    with closing(sqlite3.connect(project.root / ".miniops" / "metadata.db")) as connection:
        connection.execute(f"PRAGMA user_version = {newer}")

    code, lines = run_doctor()

    assert code == 1
    assert lines[4] == (
        f"problem  store schema version {newer}, but this miniOPs reads up to version "
        f"{newer - 1}. Upgrade miniOPs to use this store."
    )
    assert lines[-1] == "1 problem."


def test_a_damaged_store_is_a_problem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    init_project(tmp_path, "retail-models")
    database = tmp_path / ".miniops" / "metadata.db"
    database.parent.mkdir()
    database.write_bytes(b"not a database, but long enough to have a header" * 10)
    monkeypatch.chdir(tmp_path)

    code, lines = run_doctor()

    assert code == 1
    assert lines[4] == f"problem  Cannot use the store {database}: file is not a database"


def test_problems_and_warnings_are_counted(project: Project, machine: Machine) -> None:
    del machine.versions["uv"]
    machine.config = {}
    project.root.joinpath("miniops.toml").write_text("[project\n", encoding="utf-8")

    code, lines = run_doctor()

    assert code == 1
    assert lines[-1] == "2 problems, 1 warning."


def test_a_problem_found_by_the_doctor_leaves_no_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, machine: Machine
) -> None:
    init_project(tmp_path)
    del machine.versions["uv"]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["miniops", "doctor"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    assert not (tmp_path / ".miniops").exists()

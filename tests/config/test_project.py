from pathlib import Path

import pytest

from miniops.config.project import Target, find_project, find_root, init_project
from miniops.core.errors import AlreadyExistsError, ConfigError


def write_config(root: Path, text: str) -> None:
    (root / "miniops.toml").write_text(text, encoding="utf-8")


def test_init_writes_a_config_that_reads_back(tmp_path: Path) -> None:
    project = init_project(tmp_path, "retail-models")

    assert project == find_project(tmp_path)
    assert project.root == tmp_path
    assert project.config.project.name == "retail-models"
    assert project.config.project.default_target is Target.LOCAL


def test_the_config_file_is_the_same_on_every_system(tmp_path: Path) -> None:
    init_project(tmp_path, "retail-models")

    assert (tmp_path / "miniops.toml").read_bytes() == (
        b'[project]\nname = "retail-models"\ndefault_target = "local"\n'
    )


def test_a_project_is_named_after_its_directory(tmp_path: Path) -> None:
    root = tmp_path / "retail models"
    root.mkdir()

    assert init_project(root).config.project.name == "retail models"


def test_a_name_with_quotes_and_backslashes_survives(tmp_path: Path) -> None:
    name = 'the "best" models \\ zażółć'

    init_project(tmp_path, name)

    assert find_project(tmp_path).config.project.name == name


def test_a_project_needs_a_name(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="needs a name"):
        init_project(tmp_path, "   ")


def test_a_directory_becomes_a_project_once(tmp_path: Path) -> None:
    init_project(tmp_path)

    with pytest.raises(AlreadyExistsError, match="already a miniOPs project"):
        init_project(tmp_path)


def test_a_project_cannot_be_created_inside_another(tmp_path: Path) -> None:
    init_project(tmp_path)
    inner = tmp_path / "models"
    inner.mkdir()

    with pytest.raises(AlreadyExistsError, match="already a miniOPs project"):
        init_project(inner)
    assert not (inner / "miniops.toml").exists()


def test_init_keeps_local_state_out_of_git(tmp_path: Path) -> None:
    init_project(tmp_path)

    assert (tmp_path / ".gitignore").read_bytes() == b".miniops/\n"


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (b".venv/\n", b".venv/\n.miniops/\n"),
        (b".venv/", b".venv/\n.miniops/\n"),
        (b".venv/\r\ndist/\r\n", b".venv/\r\ndist/\r\n.miniops/\r\n"),
        (b".venv/\r\ndist/", b".venv/\r\ndist/\r\n.miniops/\r\n"),
    ],
)
def test_init_adds_one_line_to_an_existing_gitignore(
    tmp_path: Path, before: bytes, after: bytes
) -> None:
    (tmp_path / ".gitignore").write_bytes(before)

    init_project(tmp_path)

    assert (tmp_path / ".gitignore").read_bytes() == after


@pytest.mark.parametrize("line", [b".miniops/", b".miniops", b"/.miniops/", b"  .miniops/  "])
def test_init_leaves_a_gitignore_that_already_ignores_the_state(
    tmp_path: Path, line: bytes
) -> None:
    before = b".venv/\n" + line + b"\n"
    (tmp_path / ".gitignore").write_bytes(before)

    init_project(tmp_path)

    assert (tmp_path / ".gitignore").read_bytes() == before


def test_a_project_is_found_from_a_directory_inside_it(tmp_path: Path) -> None:
    init_project(tmp_path, "retail-models")
    inside = tmp_path / "models" / "churn"
    inside.mkdir(parents=True)

    assert find_project(inside).root == tmp_path


def test_the_root_is_found_without_reading_the_config(tmp_path: Path) -> None:
    write_config(tmp_path, "[project\nname = ")
    inside = tmp_path / "models"
    inside.mkdir()

    assert find_root(inside) == tmp_path
    assert find_root(tmp_path.parent) is None


def test_outside_a_project_the_error_says_how_to_start(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="miniops init"):
        find_project(tmp_path)


def test_default_target_is_local(tmp_path: Path) -> None:
    write_config(tmp_path, '[project]\nname = "retail-models"\n')

    assert find_project(tmp_path).config.project.default_target is Target.LOCAL


def test_broken_toml_is_reported_with_its_file(tmp_path: Path) -> None:
    write_config(tmp_path, "[project\nname = ")

    with pytest.raises(ConfigError, match=r"miniops\.toml is not valid TOML"):
        find_project(tmp_path)


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("", "project: Field required"),
        ("[project]\n", r"project\.name: Field required"),
        ('[project]\nname = ""\n', r"project\.name: String should have at least 1 character"),
        ('[project]\nname = "x"\ndefault_target = "moon"\n', r"project\.default_target: Input"),
        ('[project]\nname = "x"\ndefault_targett = "local"\n', r"project\.default_targett: Extra"),
        ('[project]\nname = "x"\n\n[projectt]\n', "projectt: Extra"),
    ],
)
def test_a_config_that_is_not_valid_says_where_and_why(
    tmp_path: Path, text: str, problem: str
) -> None:
    write_config(tmp_path, text)

    with pytest.raises(ConfigError, match=problem):
        find_project(tmp_path)

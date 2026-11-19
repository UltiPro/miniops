import os
import shutil
import sys
import time
from pathlib import Path

import pytest

from miniops import tools
from miniops.tools import find_tool, git_config, tool_version

WINDOWS = sys.platform == "win32"


def program(
    directory: Path, name: str, stdout: str = "", stderr: str = "", code: int = 0, then: str = ""
) -> Path:
    """Write a program that prints, runs ``then`` and exits.

    It is a batch file on Windows and a shell script elsewhere.
    """
    if WINDOWS:
        path, lines = directory / f"{name}.bat", ["@echo off"]
        lines += [f"echo {stdout}"] if stdout else []
        lines += [f"echo {stderr} 1>&2"] if stderr else []
        lines += [then, f"exit /b {code}"]
    else:
        path, lines = directory / name, ["#!/bin/sh"]
        lines += [f"echo '{stdout}'"] if stdout else []
        lines += [f"echo '{stderr}' >&2"] if stderr else []
        lines += [then, f"exit {code}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def bin_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "bin"
    directory.mkdir()
    monkeypatch.setenv("PATH", str(directory))
    if WINDOWS:
        monkeypatch.setenv("PATHEXT", ".EXE;.BAT")
    return directory


@pytest.fixture
def git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    found = find_tool("git")
    if found is None:
        pytest.skip("git is not installed")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.chdir(tmp_path)
    return found


def test_a_program_on_the_path_is_found(bin_dir: Path) -> None:
    uv = program(bin_dir, "uv")

    assert find_tool("uv") == uv
    assert find_tool("git") is None


def test_a_program_in_the_current_directory_is_never_taken(
    tmp_path: Path, bin_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program(tmp_path, "uv")
    monkeypatch.chdir(tmp_path)
    # The default of Windows, where shutil.which looks in the current directory first.
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    monkeypatch.setenv("PATH", os.pathsep.join([os.curdir, str(bin_dir)]))

    assert shutil.which("uv") is not None
    assert find_tool("uv") is None


@pytest.mark.parametrize(
    ("printed", "version"),
    [
        ("uv 0.13.6 (2b5d65e61 2026-11-01)", "0.13.6"),
        ("git version 2.39.5 (Apple Git-154)", "2.39.5"),
        ("nightly", "nightly"),
    ],
)
def test_the_version_is_the_first_number_that_a_program_prints(
    bin_dir: Path, printed: str, version: str
) -> None:
    assert tool_version(program(bin_dir, "tool", stdout=printed)) == version


def test_a_program_that_fails_says_how(bin_dir: Path) -> None:
    uv = program(bin_dir, "uv", stderr="error: unexpected argument", code=2)

    with pytest.raises(OSError, match=r"exited with code 2: error: unexpected argument$") as error:
        tool_version(uv)
    assert str(error.value).startswith(str(uv))


def test_a_program_that_fails_without_a_word_says_its_code(bin_dir: Path) -> None:
    uv = program(bin_dir, "uv", code=3)

    with pytest.raises(OSError, match=r"exited with code 3\.$"):
        tool_version(uv)


def test_a_program_that_cannot_run_says_so(bin_dir: Path) -> None:
    # Windows refuses a file that is not a program, Linux and macOS one that is not executable.
    broken = bin_dir / ("uv.exe" if WINDOWS else "uv")
    broken.write_bytes(b"not a program")

    with pytest.raises(OSError, match="does not run: ") as error:
        tool_version(broken)
    assert str(error.value).startswith(str(broken))
    assert "%1" not in str(error.value)


def test_a_program_that_does_not_answer_is_given_up_in_time(
    bin_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tools, "_TIMEOUT_SECONDS", 2)
    # Like git.exe in Git\cmd on Windows, the program waits for a child of its own.
    slow = program(bin_dir, "slow", then=f'"{sys.executable}" -c "import time; time.sleep(8)"')
    start = time.monotonic()

    with pytest.raises(OSError, match="did not answer within 2 seconds"):
        tool_version(slow)
    assert time.monotonic() - start < 6


def test_a_value_of_the_git_configuration_is_read_as_utf_8(git: Path, tmp_path: Path) -> None:
    (tmp_path / "gitconfig").write_text('[user]\n\tname = "Zoë Łukasiewicz"\n', encoding="utf-8")

    assert git_config(git, "user.name") == "Zoë Łukasiewicz"


def test_a_value_that_is_not_set_or_empty_is_none(git: Path, tmp_path: Path) -> None:
    (tmp_path / "gitconfig").write_text('[user]\n\temail = ""\n', encoding="utf-8")

    assert git_config(git, "user.name") is None
    assert git_config(git, "user.email") is None


def test_a_git_configuration_that_cannot_be_read_is_reported(git: Path, tmp_path: Path) -> None:
    (tmp_path / "gitconfig").write_text("[user\n", encoding="utf-8")

    with pytest.raises(OSError, match="exited with code"):
        git_config(git, "user.name")

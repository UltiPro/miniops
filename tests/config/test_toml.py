from pathlib import Path

import pytest

from miniops.config.toml import Table, load
from miniops.core.errors import ConfigError


class Settings(Table):
    name: str


def settings_file(directory: Path, content: bytes) -> Path:
    path = directory / "settings.toml"
    path.write_bytes(content)
    return path


def test_a_file_is_read_and_checked(tmp_path: Path) -> None:
    path = settings_file(tmp_path, b'name = "churn"\n')

    assert load(path, Settings) == Settings(name="churn")


def test_a_byte_order_mark_at_the_start_is_fine(tmp_path: Path) -> None:
    path = settings_file(tmp_path, b'\xef\xbb\xbfname = "churn"\r\n')

    assert load(path, Settings).name == "churn"


def test_a_missing_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="does not exist"):
        load(tmp_path / "settings.toml", Settings)


def test_a_file_in_another_encoding_is_a_config_error(tmp_path: Path) -> None:
    # Windows PowerShell 5 writes UTF-16 with ">".
    path = settings_file(tmp_path, 'name = "churn"\n'.encode("utf-16"))

    with pytest.raises(ConfigError, match="not saved as UTF-8"):
        load(path, Settings)


def test_a_file_that_is_not_toml_is_a_config_error(tmp_path: Path) -> None:
    path = settings_file(tmp_path, b"name = \n")

    with pytest.raises(ConfigError, match="is not valid TOML"):
        load(path, Settings)


def test_a_file_that_does_not_fit_names_the_problem(tmp_path: Path) -> None:
    path = settings_file(tmp_path, b'name = "churn"\nlevel = 3\n')

    with pytest.raises(ConfigError, match=r"is not valid:\n  level: "):
        load(path, Settings)

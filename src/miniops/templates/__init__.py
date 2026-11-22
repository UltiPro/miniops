import json
import keyword
import re
import sys
from importlib import resources
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from string import Template
from urllib.parse import unquote, urlparse

from miniops import __version__
from miniops.core.entities import Task
from miniops.core.errors import NotFoundError

_SUFFIX = ".tmpl"


def write_model_files(directory: Path, name: str, flavor: str, task: Task) -> None:
    """Write the files of a new model into ``directory``, from the template of its flavor.

    Raises:
        NotFoundError: If miniOPs has no template for the flavor.
    """
    template = resources.files(__name__) / flavor
    if not (template / f"model.toml{_SUFFIX}").is_file():
        raise NotFoundError(f"There is no model template for the flavor {flavor!r}.")
    values = {
        "name": name,
        "flavor": flavor,
        "task": task,
        "estimator": "Regressor" if task is Task.REGRESSION else "Classifier",
        "miniops_version": __version__,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "sources": _sources(),
    }
    # The class name is filled in by a second pass, which must leave a "$" of a value alone.
    escaped = {key: value.replace("$", "$$") for key, value in values.items()}
    files = {
        file.name.removesuffix(_SUFFIX): Template(file.read_text("utf-8")).safe_substitute(escaped)
        for file in template.iterdir()
    }
    code = "".join(text for file_name, text in files.items() if file_name.endswith(".py"))
    class_name = _class_name(name, taken=code)
    for file_name, text in files.items():
        text = Template(text).substitute(class_name=class_name).rstrip("\n") + "\n"
        (directory / file_name).write_text(text, encoding="utf-8", newline="\n")


def _class_name(name: str, taken: str) -> str:
    words = "".join(word.capitalize() for word in name.split("-"))
    # "none" would become None, and "pipeline" would hide the imported Pipeline.
    if keyword.iskeyword(words) or re.search(rf"\b{words}\b", taken):
        return f"{words}Model"
    return words


def _sources() -> str:
    """Tell uv where this miniOPs came from, unless it came from an index such as PyPI.

    The version alone would take the release of that number, which a development version from
    a directory, a git repository or a built wheel is not.
    """
    try:
        text = distribution("miniops-ml").read_text("direct_url.json")
    except PackageNotFoundError:
        return ""
    origin = json.loads(text) if text else {}
    url = origin.get("url", "")
    source: dict[str, str | bool]
    if "vcs_info" in origin:
        if origin["vcs_info"].get("vcs") != "git":
            return ""
        source = {"git": url, "rev": origin["vcs_info"].get("commit_id", "")}
    elif url.startswith("file:"):
        source = {"path": _local_path(url)}
        if "dir_info" in origin:
            source["editable"] = bool(origin["dir_info"].get("editable"))
    elif "archive_info" in origin:
        source = {"url": url}
    else:
        return ""
    table = ", ".join(f"{key} = {_toml(value)}" for key, value in source.items() if value != "")
    return f"\n[tool.uv.sources]\nminiops-ml = {{ {table} }}"


def _toml(value: str | bool) -> str:
    # Without ensure_ascii: TOML refuses the surrogate pairs that JSON writes for some letters.
    return str(value).lower() if isinstance(value, bool) else json.dumps(value, ensure_ascii=False)


def _local_path(url: str) -> str:
    parts = urlparse(url)
    path = unquote(parts.path)
    # A Windows drive comes after a slash in a file URL: file:///D:/miniops.
    if re.match(r"/[A-Za-z]:", path):
        path = path[1:]
    # A host in a file URL is a network share, like file://server/share/miniops.
    return path if parts.netloc in ("", "localhost") else f"//{parts.netloc}{path}"

import keyword
import re
from importlib import resources
from pathlib import Path
from string import Template

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
    }
    files = {
        file.name.removesuffix(_SUFFIX): Template(file.read_text("utf-8")).safe_substitute(values)
        for file in template.iterdir()
    }
    class_name = _class_name(name, taken="".join(files.values()))
    for file_name, text in files.items():
        text = Template(text).substitute(class_name=class_name)
        (directory / file_name).write_text(text, encoding="utf-8", newline="\n")


def _class_name(name: str, taken: str) -> str:
    words = "".join(word.capitalize() for word in name.split("-"))
    # "none" would become None, and "pipeline" would hide the imported Pipeline.
    if keyword.iskeyword(words) or re.search(rf"\b{words}\b", taken):
        return f"{words}Model"
    return words

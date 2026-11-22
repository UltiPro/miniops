import importlib
import inspect
import logging
import platform
import sys
from pathlib import Path
from types import ModuleType

import polars as pl

from miniops import __version__
from miniops.core.errors import ConfigError, MiniopsError, describe
from miniops.flavors.base import FlavorModel
from miniops.runner.protocol import (
    RESULT_FILE,
    Environment,
    Failure,
    Result,
    TrainJob,
    read_job,
    write_result,
)

logger = logging.getLogger(__name__)

MODEL_DIR = "model"


def run(job_file: Path) -> Result:
    """Run the job in ``job_file`` and write its result into the output directory of the job.

    A job that fails leaves a result too, which says why. The files of a trained model go to
    the directory ``model`` there. The output directory must not exist yet, so that the files
    of two jobs never mix.

    Raises:
        ProtocolError: If the job file cannot be read.
        OSError: If the job file cannot be read, the output directory exists or the result
            cannot be written.
    """
    job = read_job(job_file)
    base = job_file.parent
    output = (base / job.output).resolve()
    output.mkdir(parents=True)
    try:
        result = _train(job, base, output / MODEL_DIR)
    except (Exception, SystemExit) as error:
        logger.exception("The training failed")
        result = Result(environment=_environment(), failure=_failure(error))
    write_result(result, output / RESULT_FILE)
    return result


def load_model_class(directory: Path, entrypoint: str) -> type[FlavorModel]:
    """Import the class that ``entrypoint`` names, like ``model.py:Churn``, from ``directory``.

    The directory goes first on ``sys.path``, so the model can import its other modules, and
    the types that it defines can be found again when the model is loaded.

    Raises:
        ConfigError: If the file is missing or has the name of a module in use, or the class is
            missing or not a model that can be made.
    """
    file_name, class_name = entrypoint.split(":")
    path = directory / file_name
    if not path.is_file():
        raise ConfigError(f"{path} does not exist, but the entrypoint in model.toml names it.")
    module_name = path.stem
    loaded = sys.modules.get(module_name)
    if module_name in sys.stdlib_module_names or (
        loaded is not None and not _is_file_of(loaded, path)
    ):
        raise ConfigError(
            f"{file_name} has the name of a Python module that is in use. Rename the file and "
            "the entrypoint in model.toml."
        )
    if sys.path[:1] != [str(directory)]:
        sys.path.insert(0, str(directory))
    found = getattr(importlib.import_module(module_name), class_name, None)
    if found is None:
        raise ConfigError(
            f"{file_name} has no class {class_name}, which the entrypoint in model.toml names."
        )
    if not (isinstance(found, type) and issubclass(found, FlavorModel)):
        raise ConfigError(
            f"{class_name} in {file_name} is not a model class: it has to subclass the base "
            "class of a flavor, like SklearnModel."
        )
    if inspect.isabstract(found):
        missing = ", ".join(sorted(found.__abstractmethods__))
        raise ConfigError(f"{class_name} in {file_name} does not implement {missing}.")
    return found


def _is_file_of(module: ModuleType, path: Path) -> bool:
    file = getattr(module, "__file__", None)
    return file is not None and Path(file).resolve() == path.resolve()


def _failure(error: BaseException) -> Failure:
    if isinstance(error, SystemExit):
        message = f"The model code called sys.exit({error.code!r})."
    elif isinstance(error, OSError):
        message = describe(error)
    else:
        message = str(error)
    return Failure(
        type=type(error).__name__, message=message, reported=isinstance(error, MiniopsError)
    )


def _train(job: TrainJob, base: Path, directory: Path) -> Result:
    model_class = load_model_class((base / job.model).resolve(), job.entrypoint)
    data = pl.read_parquet((base / job.data).resolve())
    logger.info(
        "Training %s for %s on %d rows of %s", job.entrypoint, job.task, len(data), job.data
    )
    model = model_class(job.task)
    signature = model.fit(data, job.target, job.params)
    directory.mkdir()
    model.save(directory)
    files = sorted(
        path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()
    )
    logger.info("Saved %s", ", ".join(files))
    return Result(
        environment=_environment(),
        signature=signature,
        files=tuple(files),
        untrusted_types=tuple(model_class.untrusted_types(directory)),
    )


def _environment() -> Environment:
    return Environment(
        miniops=__version__,
        python=platform.python_version(),
        platform=platform.platform(),
        machine=platform.machine(),
    )

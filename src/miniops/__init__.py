"""miniOPs: a lightweight, polars-native MLOps CLI."""

import logging
from importlib.metadata import version

__version__ = version("miniops-ml")

__all__ = ["__version__"]

# Without any handler, Python prints the warnings and errors of a library to stderr itself.
logging.getLogger(__name__).addHandler(logging.NullHandler())

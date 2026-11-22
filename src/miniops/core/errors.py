def describe(error: OSError) -> str:
    """Return the message of a problem of the system, with its files as they are."""
    # str() adds the number of the error and shows a path as Python code, with every
    # backslash doubled on Windows.
    if error.strerror is None:
        return str(error)
    files = (error.filename, error.filename2)
    names = " -> ".join(str(name) for name in files if name is not None)
    return f"{error.strerror}: {names}" if names else error.strerror


class MiniopsError(Exception):
    """Base class for errors that miniOPs reports to the user."""


class InvalidStateError(MiniopsError):
    """An operation does not fit the current state, like releasing a released version."""


class AlreadyExistsError(MiniopsError):
    """Something with the same identity is already in the store."""


class NotFoundError(MiniopsError):
    """The store has no such model, version, run or artifact."""


class IntegrityError(MiniopsError):
    """Stored content does not match the digest recorded for it."""


class IncompatibleStoreError(MiniopsError):
    """The store was written by a newer miniOPs than the one that opened it."""


class StoreBusyError(MiniopsError):
    """Another process is using the store."""


class ConfigError(MiniopsError):
    """A configuration file is missing or not valid."""


class DataError(MiniopsError):
    """Data does not fit what a model needs, like a column that is missing."""


class UntrustedTypesError(MiniopsError):
    """A saved model needs types that the caller did not trust."""


class ProtocolError(MiniopsError):
    """A job or result file is damaged, or newer than this miniOPs."""


class ToolError(MiniopsError):
    """A program that miniOPs runs, like uv, is missing or failed."""

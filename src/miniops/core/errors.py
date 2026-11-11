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
